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

import math
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional, Sequence

from ...domain.models.ground_truth import EntityAddress
from ...logger import logger
from ..audit.bom.zone_detector import _entity_points
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
    """Best available (x, y) for an entity, from whichever geometry key it carries.

    Retained as the last-resort fallback for an entity that contributes no drawable geometry
    at all. **It is not what tier 4 measures against** -- see `_entity_distance`.
    """
    geometry = getattr(entity, "geometry", None) or {}
    for key in ("insert", "text_point", "def_point", "start", "center"):
        raw = geometry.get(key)
        if isinstance(raw, (list, tuple)) and len(raw) >= 2:
            try:
                return float(raw[0]), float(raw[1])
            except (TypeError, ValueError):
                continue
    return None


def _xy(raw: Any) -> tuple[float, float] | None:
    if isinstance(raw, (list, tuple)) and len(raw) >= 2:
        try:
            return float(raw[0]), float(raw[1])
        except (TypeError, ValueError):
            return None
    return None


def _point_to_segment(
    point: tuple[float, float], a: tuple[float, float], b: tuple[float, float]
) -> float:
    """Distance from `point` to the segment `a`-`b`, not to its endpoints."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    if dx == 0.0 and dy == 0.0:
        return math.hypot(point[0] - a[0], point[1] - a[1])
    t = ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(point[0] - (a[0] + t * dx), point[1] - (a[1] + t * dy))


def _entity_distance(entity: Any, target: tuple[float, float]) -> float | None:
    """How far `target` is from the geometry this entity actually DRAWS.

    ## Why this is not `distance(target, _entity_point(entity))`

    `EntityAddress.point` is **where the engineer clicked** -- `useEntityPicking` sends the
    pointer's world position verbatim. `_entity_point` returns the entity's *canonical anchor*
    (`start` for a line, `center` for an arc). For text and inserts those nearly coincide,
    which is why nothing surfaced this: measured 2026-08-20 over 3611 real reference entities,
    every one of the 1541 TEXT entities resolved correctly.

    For a line they diverge without limit. Clicking the middle of an 831-unit border line puts
    the click 415 units from that line's own `start`, so the entity the engineer actually
    picked fails `COORDINATE_TOLERANCE` and is not even a candidate -- while any unrelated line
    whose `start` happens to sit near the click is returned instead. On `M745204N01` one such
    click resolved to the wrong line at **distance 0.0**: the strongest possible match, and the
    wrong entity. 31 of 33 mis-resolutions measured had exactly this shape.

    This is the same defect the vault records for zone scoping in
    "A Dimension Scoped by Its Span Midpoint" -- collapsing an entity to one derived point
    produces a phantom location where nothing is drawn. There it dropped a dimension from the
    comparison pool; here it silently attributes a person's judgement to the wrong entity.

    So: measure to the drawn geometry. A click lands *on* what it selected, by definition.

    WARNING: an arc is measured to its full circumference. The payload carries only `center`
    and `radius` -- no angular sweep -- so a click on the empty side of an arc reads as on it.
    Over-permissive by exactly the span the file does not record; the ambiguity refusal in
    `_nearest` is what keeps that from becoming a wrong answer.
    """
    geometry = getattr(entity, "geometry", None) or {}
    best: float | None = None

    def offer(value: float | None) -> None:
        nonlocal best
        if value is not None and (best is None or value < best):
            best = value

    # Segments: an explicit start/end pair, and every polyline-shaped run of points. A
    # dimension's `render_paths` is included because that is the geometry it puts on the sheet.
    start, end = _xy(geometry.get("start")), _xy(geometry.get("end"))
    if start and end:
        offer(_point_to_segment(target, start, end))

    runs: list[Any] = []
    for key in ("points", "vertices", "fit_points", "boundary_points", "control_points"):
        sequence = geometry.get(key)
        if isinstance(sequence, list):
            runs.append(sequence)
    paths = geometry.get("render_paths")
    if isinstance(paths, list):
        runs.extend(path for path in paths if isinstance(path, list))

    for run in runs:
        points = [p for p in (_xy(raw) for raw in run) if p is not None]
        for first, second in zip(points, points[1:], strict=False):
            offer(_point_to_segment(target, first, second))
        if len(points) == 1:
            offer(math.hypot(target[0] - points[0][0], target[1] - points[0][1]))

    # Curves: distance to the circumference, not to the centre. Clicking a circle means
    # clicking its outline, and for a large circle the centre is nowhere near it.
    center, radius = _xy(geometry.get("center")), geometry.get("radius")
    if center is not None and radius is not None:
        try:
            offer(abs(math.hypot(target[0] - center[0], target[1] - center[1]) - float(radius)))
        except (TypeError, ValueError):
            pass

    if best is not None:
        return best

    # Nothing drawable. Fall back to every point the entity contributes -- `_entity_points`
    # rather than a second opinion about which keys carry coordinates, because that helper
    # already had to learn the exotic ones (ellipses and splines) the hard way.
    for point in (p for p in (_xy(raw) for raw in _entity_points(entity)) if p is not None):
        offer(math.hypot(target[0] - point[0], target[1] - point[1]))
    return best


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


#: Two candidates whose distances differ by less than this are treated as indistinguishable
#: rather than ranked. Ties here are not floating-point noise -- they are real coincident
#: geometry (three concentric arcs of a corner round, two border lines meeting at a corner),
#: where the stored address genuinely does not say which one the engineer meant.
_DISTANCE_EPSILON = 1e-9


def _nearest(candidates: Sequence[Any], address: EntityAddress) -> Optional[Any]:
    """The one candidate the click identifies, or None if none does -- or if several do.

    **A tie is refused, not broken.** Ranking by `<` alone silently returned whichever
    coincident entity came first in payload order, which is a guess wearing the costume of a
    measurement. Measured 2026-08-20 across the eight human pairs: 101 of 1737 coordinate-tier
    resolutions were ambiguous, and order-breaking got 44 of them wrong.

    Refusing costs the 57 that order-breaking happened to get right. That is the trade this
    module's docstring already committed to -- an unresolved marking is a known, countable gap;
    a mis-resolved one corrupts the dataset in a way nothing downstream can detect.
    """
    if not candidates or address.point is None:
        return None

    target = (address.point.x, address.point.y)
    best: float | None = None
    winner: Any = None
    tied = False
    for entity in candidates:
        distance = _entity_distance(entity, target)
        if distance is None:
            continue
        if best is None or distance < best - _DISTANCE_EPSILON:
            best, winner, tied = distance, entity, False
        elif abs(distance - best) <= _DISTANCE_EPSILON:
            tied = True

    if best is None or best > COORDINATE_TOLERANCE:
        return None
    if tied:
        logger.debug(
            f"[ground_truth] several entities are equally close to the stored point on drawing "
            f"{address.drawing_id}; refusing to guess which was meant."
        )
        return None
    return winner
