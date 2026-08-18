"""Re-binds a stored `EntityAddress` to a live `ExtractedEntity`.

## Why this exists

A ground-truth marking outlives the extraction it was made against. `ExtractionPipeline.run`
deletes a drawing's entities and re-inserts them, so an entity id is valid only until the next
`POST /drawings/{id}/reextract` -- and `EXTRACTION_SCHEMA_VERSION` reaching 6 means that has
already happened six times for reasons unrelated to this feature. Resolution therefore has to
be done from durable keys, on demand, rather than by storing a pointer.

## The tiers, and why the order is what it is

1. **`handle`** -- written by the CAD application into the DXF, so it is identical across any
   number of re-extractions of the same file. Trustworthy, but absent for anything exploded
   out of a block, which on this client's reference sheets is nearly everything.
2. **`parent_handle` + type + layer + text** -- for block-exploded children, the owning
   INSERT's handle narrows the search to one block instance, and the text picks the child.
3. **type + layer + normalised text** -- no handle at all. Safe only when unique; a tie is
   reported as unresolved rather than guessed at.
4. **nearest by coordinate**, within a tolerance, among candidates of the same type.

**Every tier returns `None` rather than a plausible wrong answer.** An unresolved marking is a
known, countable gap. A mis-resolved one silently attributes a human's judgement to the wrong
entity, which is worse than losing it -- it corrupts the dataset in a way nothing downstream
can detect. `MatchTier` is returned alongside the entity so the caller can record *how* a
marking resolved, which is what makes "how far do handles actually carry us" measurable rather
than assumed.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional, Sequence

from ...domain.models.ground_truth import EntityAddress
from ...logger import logger
from ..audit.comparison.spatial_differ import SpatialDiffer

#: How close a coordinate has to be, in drawing units, before tier 4 will claim a match.
#: Deliberately tight: this tier exists to recover an entity that moved by rounding, not to
#: find "something near where the engineer clicked". Widening it trades unresolved markings
#: for mis-resolved ones, which is the wrong direction.
COORDINATE_TOLERANCE = 1.0


class MatchTier(str, Enum):
    """Which key actually resolved a marking. Recorded so the mix can be measured."""

    HANDLE = "handle"
    PARENT_HANDLE = "parent_handle"
    TEXT = "text"
    COORDINATE = "coordinate"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class Resolution:
    entity: Any | None
    tier: MatchTier

    @property
    def ok(self) -> bool:
        return self.entity is not None


def _norm(value: str | None) -> str:
    """Normalise text the way the comparison engine does, by calling the engine.

    `SpatialDiffer._normalize_text` is private and reaching for it crosses a module boundary
    on purpose -- the same trade `line_attribute_differ` makes when it calls
    `GeometrySerializer._resolve_lineweight`. The alternative is a second opinion about
    whether two strings are "the same text", and here that drift would be **invisible**: a
    marking that fails to resolve looks exactly like a marking whose entity genuinely went
    away, so nothing would ever surface the disagreement.
    """
    return SpatialDiffer._normalize_text(value or "")


def _entity_text(entity: Any) -> str:
    """The entity's text, MTEXT formatting already stripped -- again, the engine's answer."""
    return SpatialDiffer._get_entity_text(entity)


def _entity_point(entity: Any) -> tuple[float, float] | None:
    """Best available (x, y) for an entity, from whichever geometry key it carries."""
    geometry = getattr(entity, "geometry", None) or {}
    for key in ("insert", "text_point", "def_point", "start", "center"):
        raw = geometry.get(key)
        if isinstance(raw, (list, tuple)) and len(raw) >= 2:
            try:
                return float(raw[0]), float(raw[1])
            except (TypeError, ValueError):
                continue
    return None


def _same_shape(entity: Any, address: EntityAddress) -> bool:
    """Type and layer agree. Cheap filter applied before every fuzzy tier."""
    return (
        str(getattr(entity, "entity_type", "")).lower() == address.entity_type.lower()
        and str(getattr(entity, "layer", "")) == address.layer
    )


def resolve(address: EntityAddress, entities: Sequence[Any]) -> Resolution:
    """Find the entity `address` refers to among `entities`, or report that it cannot be found.

    `entities` is the drawing's *current* entity set -- the caller loads it, so this function
    stays free of database access and is directly testable against a list of fakes.
    """
    if not entities:
        return Resolution(None, MatchTier.UNRESOLVED)

    # Tier 1: the DXF handle. Unique within a drawing by definition.
    if address.handle:
        for entity in entities:
            if getattr(entity, "handle", None) == address.handle:
                return Resolution(entity, MatchTier.HANDLE)
        # A stored handle that no longer exists means the entity was genuinely removed from the
        # file, not that the address is stale. Falling through to text matching here would find
        # a *different* entity with the same string, so do not.
        logger.debug(
            f"[ground_truth] handle {address.handle} absent from drawing "
            f"{address.drawing_id}; treating as removed rather than searching by text."
        )
        return Resolution(None, MatchTier.UNRESOLVED)

    wanted_text = _norm(address.text)

    # Tier 2: block-exploded child, narrowed to its owning INSERT.
    if address.parent_handle:
        siblings = [
            e
            for e in entities
            if getattr(e, "parent_handle", None) == address.parent_handle and _same_shape(e, address)
        ]
        if wanted_text:
            hits = [e for e in siblings if _norm(_entity_text(e)) == wanted_text]
            if len(hits) == 1:
                return Resolution(hits[0], MatchTier.PARENT_HANDLE)
            if len(hits) > 1:
                # Several identical strings inside one block. Position decides, or nothing does.
                nearest = _nearest(hits, address)
                if nearest is not None:
                    return Resolution(nearest, MatchTier.COORDINATE)
        elif len(siblings) == 1:
            return Resolution(siblings[0], MatchTier.PARENT_HANDLE)

    # Tier 3: type + layer + text, and only when it is unambiguous.
    if wanted_text:
        hits = [
            e for e in entities if _same_shape(e, address) and _norm(_entity_text(e)) == wanted_text
        ]
        if len(hits) == 1:
            return Resolution(hits[0], MatchTier.TEXT)
        if len(hits) > 1:
            nearest = _nearest(hits, address)
            if nearest is not None:
                return Resolution(nearest, MatchTier.COORDINATE)
            logger.debug(
                f"[ground_truth] {len(hits)} entities match text {address.text!r} on drawing "
                f"{address.drawing_id} and none is near the stored point; leaving unresolved."
            )
            return Resolution(None, MatchTier.UNRESOLVED)

    # Tier 4: geometry with no text -- a line in an isometric view, say. Position is all there
    # is, so require the type to agree and the point to be genuinely close.
    nearest = _nearest([e for e in entities if _same_shape(e, address)], address)
    if nearest is not None:
        return Resolution(nearest, MatchTier.COORDINATE)

    return Resolution(None, MatchTier.UNRESOLVED)


def _nearest(candidates: Sequence[Any], address: EntityAddress) -> Optional[Any]:
    """Closest candidate to the address's stored point, or None if none is within tolerance."""
    if not candidates or address.point is None:
        return None

    target = (address.point.x, address.point.y)
    best: tuple[float, Any] | None = None
    for entity in candidates:
        point = _entity_point(entity)
        if point is None:
            continue
        distance = ((point[0] - target[0]) ** 2 + (point[1] - target[1]) ** 2) ** 0.5
        if best is None or distance < best[0]:
            best = (distance, entity)

    if best is None or best[0] > COORDINATE_TOLERANCE:
        return None
    return best[1]
