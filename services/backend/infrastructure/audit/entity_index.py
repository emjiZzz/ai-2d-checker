"""A queryable index over a drawing's extracted entities.

Two things need the same lookups over the same data, so they share one implementation
rather than each growing their own:

  * **Entity-grounded AI comparison** — the model is given a manifest of addressable
    entities and asked to cite a handle, instead of returning a normalized 0-1000
    `visual_bbox` that then has to be back-projected and sanity-checked. Handle lookup
    is the addressing scheme.
  * **A future standards rules engine** — "run predicates over the entities" is what a
    deterministic ISO 128 / JIS B 0001 checker is. Building the manifest as a general
    index rather than a one-off prompt helper costs nothing now and avoids a rewrite.

Handles are namespaced per side (`REV-1B2A` / `REF-1B2A`) because a comparison holds two
drawings at once and a bare handle is ambiguous between them. Callers may pass either
form; `by_handle` normalises. That normalisation currently lives inline in two places in
`coordinate_resolver.py`, which this is intended to replace.
"""

import re
from dataclasses import dataclass
from typing import Any, Iterable, Iterator

try:
    from ...logger import logger
except Exception:
    try:
        from logger import logger
    except Exception:
        import logging
        logger = logging.getLogger("entity_index")

# Sides of a comparison. Also the handle namespace prefix.
SIDE_REVISION = "REV"
SIDE_REFERENCE = "REF"

# Entity types that carry a value a finding can point at. Geometry-only types (line,
# circle, hatch) are indexed and queryable but excluded from the prompt manifest by
# default -- a finding cites the dimension text or note, not the arc under it.
TEXT_BEARING_TYPES = frozenset({"text", "mtext", "attrib", "dimension", "tolerance", "multileader", "block"})

# Guard against handing the model a manifest larger than the drawing warrants.
DEFAULT_MANIFEST_LIMIT = 400


@dataclass(frozen=True)
class Region:
    """An axis-aligned query window in the drawing's own coordinate space."""

    xmin: float
    ymin: float
    xmax: float
    ymax: float

    def contains(self, x: float, y: float) -> bool:
        return self.xmin <= x <= self.xmax and self.ymin <= y <= self.ymax

    @classmethod
    def from_bbox(cls, bbox: Any) -> "Region | None":
        try:
            if bbox is None:
                return None
            if isinstance(bbox, Region):
                return bbox
            if len(bbox) == 4:
                return cls(float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
            if len(bbox) == 2:  # [[xmin, ymin], [xmax, ymax]]
                return cls(float(bbox[0][0]), float(bbox[0][1]), float(bbox[1][0]), float(bbox[1][1]))
        except (TypeError, ValueError, IndexError):
            return None
        return None


def entity_handle(entity: Any) -> str | None:
    """The source DXF handle, from the indexed column or the properties blob.

    Phase 1 promoted `handle` to a top-level indexed field; entities constructed
    elsewhere (or older in-memory dicts) still carry it only inside `properties`.
    """
    direct = getattr(entity, "handle", None)
    if direct:
        return str(direct)
    props = getattr(entity, "properties", None) or {}
    value = props.get("handle")
    return str(value) if value else None


def entity_text(entity: Any) -> str:
    props = getattr(entity, "properties", None) or {}
    return str(props.get("text") or "")


def entity_anchor(entity: Any) -> list[float]:
    """The point a marker for this entity should sit at.

    Delegates to `coordinate_resolver.calc_anchor`, which is the existing canonical
    formula (right edge of the text bbox, vertically centred). It is imported rather
    than reimplemented so the two cannot drift; when the bulk of `coordinate_resolver`
    is retired this function should move here rather than being duplicated.
    """
    try:
        from .comparison.coordinate_resolver import calc_anchor
        return calc_anchor(entity)
    except Exception:
        geometry = getattr(entity, "geometry", None) or {}
        point = (
            geometry.get("location")
            or geometry.get("insert")
            or geometry.get("text_point")
            or [0.0, 0.0]
        )
        return [float(point[0]), float(point[1])]


class EntityIndex:
    """Indexed access to one drawing's entities, scoped to one side of a comparison."""

    def __init__(self, entities: Iterable[Any], side: str = SIDE_REVISION):
        self.side = side.upper()
        self.entities: list[Any] = list(entities or [])

        self._by_handle: dict[str, Any] = {}
        self._by_type: dict[str, list[Any]] = {}
        self._by_layer: dict[str, list[Any]] = {}

        duplicates = 0
        for entity in self.entities:
            handle = entity_handle(entity)
            if handle:
                key = f"{self.side}-{handle}"
                if key in self._by_handle:
                    duplicates += 1
                self._by_handle[key] = entity

            etype = str(getattr(entity, "entity_type", "") or "").lower()
            self._by_type.setdefault(etype, []).append(entity)

            layer = str(getattr(entity, "layer", "") or "")
            self._by_layer.setdefault(layer, []).append(entity)

        if duplicates:
            # Exploded block children legitimately reuse their source handle; worth
            # knowing about, not worth failing over.
            logger.debug(f"EntityIndex[{self.side}]: {duplicates} duplicate handle(s) collapsed.")

    def __len__(self) -> int:
        return len(self.entities)

    def __iter__(self) -> Iterator[Any]:
        return iter(self.entities)

    @classmethod
    async def for_drawing(cls, drawing_id: str, side: str = SIDE_REVISION) -> "EntityIndex":
        """Load a drawing's entities from Mongo.

        Uses the compound `(drawing_id, entity_type)` index added in Phase 1.
        """
        from ...domain.models.extracted_entity import ExtractedEntity

        entities = await ExtractedEntity.find(ExtractedEntity.drawing_id == str(drawing_id)).to_list()
        return cls(entities, side=side)

    # -- lookup ------------------------------------------------------------

    def by_handle(self, handle: str | None) -> Any | None:
        """Resolve a handle, with or without its side prefix.

        The model is asked to cite `REV-1B2A`; some paths pass a bare `1B2A`. Both work,
        and a handle carrying the *other* side's prefix returns None rather than
        silently resolving against the wrong drawing.
        """
        if not handle:
            return None
        handle = str(handle).strip()
        if handle.startswith(f"{self.side}-"):
            return self._by_handle.get(handle)
        if "-" in handle[:4] and (handle.startswith(f"{SIDE_REVISION}-") or handle.startswith(f"{SIDE_REFERENCE}-")):
            return None  # explicitly the other side
        return self._by_handle.get(f"{self.side}-{handle}")

    @property
    def handles(self) -> set[str]:
        return set(self._by_handle)

    def anchor_for(self, handle: str | None) -> list[float] | None:
        entity = self.by_handle(handle)
        return entity_anchor(entity) if entity is not None else None

    # -- query -------------------------------------------------------------

    def query(
        self,
        *,
        entity_type: str | Iterable[str] | None = None,
        layer: str | Iterable[str] | None = None,
        region: Any = None,
        text_contains: str | None = None,
        text_regex: str | None = None,
        text_bearing_only: bool = False,
        limit: int | None = None,
    ) -> list[Any]:
        """Filter entities. All supplied criteria must match (logical AND).

        This is the predicate surface a rules engine would build on: "every dimension on
        layer DIM inside the title-block region whose text matches R\\d+".
        """
        if entity_type is None:
            candidates: list[Any] = self.entities
        else:
            types = {entity_type.lower()} if isinstance(entity_type, str) else {t.lower() for t in entity_type}
            candidates = [e for t in types for e in self._by_type.get(t, [])]

        if layer is not None:
            layers = {layer} if isinstance(layer, str) else set(layer)
            candidates = [e for e in candidates if str(getattr(e, "layer", "")) in layers]

        if text_bearing_only:
            candidates = [
                e for e in candidates
                if str(getattr(e, "entity_type", "")).lower() in TEXT_BEARING_TYPES and entity_text(e).strip()
            ]

        if text_contains:
            needle = text_contains.casefold()
            candidates = [e for e in candidates if needle in entity_text(e).casefold()]

        if text_regex:
            try:
                pattern = re.compile(text_regex)
                candidates = [e for e in candidates if pattern.search(entity_text(e))]
            except re.error as exc:
                logger.warning(f"EntityIndex: invalid text_regex {text_regex!r} ignored: {exc}")

        bounds = Region.from_bbox(region)
        if bounds is not None:
            inside = []
            for e in candidates:
                anchor = entity_anchor(e)
                if len(anchor) >= 2 and bounds.contains(anchor[0], anchor[1]):
                    inside.append(e)
            candidates = inside

        return candidates[:limit] if limit else candidates

    # -- prompt manifest ---------------------------------------------------

    def to_manifest(
        self,
        *,
        region: Any = None,
        limit: int = DEFAULT_MANIFEST_LIMIT,
        include_coordinates: bool = True,
    ) -> str:
        """Render addressable entities as compact lines for a model prompt.

        One line per entity, leading with the handle the model is expected to cite back:

            [ID: REV-1B2A] dimension @(123.4, 56.7) layer=DIM "45.5"

        Only text-bearing entities are listed: a finding cites the dimension text or the
        note, not the arc beneath it. Truncation is reported in-band rather than
        silently, so the model is never led to believe it saw the whole drawing.
        """
        matches = self.query(region=region, text_bearing_only=True)
        total = len(matches)
        shown = matches[:limit]

        lines: list[str] = []
        for entity in shown:
            handle = entity_handle(entity)
            if not handle:
                continue
            text = entity_text(entity).replace("\n", " ").strip()
            if len(text) > 80:
                text = text[:77] + "..."
            parts = [f"[ID: {self.side}-{handle}]", str(getattr(entity, "entity_type", "") or "?")]
            if include_coordinates:
                anchor = entity_anchor(entity)
                if len(anchor) >= 2:
                    parts.append(f"@({anchor[0]:.1f}, {anchor[1]:.1f})")
            layer = str(getattr(entity, "layer", "") or "")
            if layer:
                parts.append(f"layer={layer}")
            parts.append(f'"{text}"')
            lines.append(" ".join(parts))

        if total > len(shown):
            lines.append(
                f"... {total - len(shown)} further addressable entities omitted "
                f"(showing {len(shown)} of {total})."
            )

        return "\n".join(lines)


def build_comparison_indexes(
    ref_entities: Iterable[Any], rev_entities: Iterable[Any]
) -> tuple[EntityIndex, EntityIndex]:
    """Both sides of a comparison, correctly namespaced."""
    return (
        EntityIndex(ref_entities, side=SIDE_REFERENCE),
        EntityIndex(rev_entities, side=SIDE_REVISION),
    )
