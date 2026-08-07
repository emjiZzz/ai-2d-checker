"""
Zone Template Resolver.

Applies human hand-aligned zone templates (`ZoneTemplateDocument`) to the comparison
pipeline. A zone the user has pinned takes priority over keyword-anchor detection; zones
absent from the template keep detecting, so a partially-aligned template is still useful.

See docs/zone-template-alignment-implementation-plan.md and
docs/vault/06 - Gotchas & Debugging Lessons/Gotcha - Zone Detection Accuracy & Stability.md
"""

from typing import Any, Dict, Optional, Sequence, Tuple

from ....domain.models.zone_template import (
    MIN_ZONE_POINTS,
    ZoneTemplateDocument,
    zone_signature,
)
from ....logger import logger
from .zone_geometry import ZONE_POLYGONS_KEY


def _as_fraction_dict(fractions: Any) -> Optional[dict]:
    """Normalizes a ZoneFractions model or plain dict into a dict, or None if unusable."""
    if hasattr(fractions, "model_dump") and callable(fractions.model_dump):
        return fractions.model_dump()
    if isinstance(fractions, dict):
        return fractions
    return None


def fractions_to_absolute_bbox(
    fractions: Any,
    render_bounds: Sequence[float],
) -> Optional[Tuple[float, float, float, float]]:
    """Converts Y-DOWN template fractions to an absolute CAD bbox (xmin, ymin, xmax, ymax).

    ## The Y axis is flipped here, deliberately

    Template fractions are **Y-DOWN**: `yMin = 0` is the *top* of the sheet, matching screen
    orientation and the client's `customRegions` convention. CAD coordinates are **Y-UP**.
    So the conversion measures down from `by1` (the top), and min/max swap:

        cad_ymin = by1 - yMax * h        cad_ymax = by1 - yMin * h

    Computing `by0 + yMin * h` instead mirrors every pinned zone vertically. That failure is
    not obvious on screen — most zones sit near the sheet's vertical centre, so a mirrored
    box lands plausibly. Concretely, a title block pinned at 79.5-92.3% down from the top
    resolves to 14.1% down when the flip is dropped: it lands on the BOM table. Because
    `title` and `tolerance` are safe zones *excluded* from comparison, that would exclude the
    wrong regions and feed the real title block into the diff as drawing geometry.

    This mirrors `apps/desktop/src/utils/zoneFractions.ts::fractionsToZoneBox` exactly. Keep
    the two in step.

    ## render_bounds, not the detected frame

    `render_bounds` is the rectangle the fractions were authored against — the canvas renders
    the drawing into it and the editor divides by it. It comes from matplotlib's autoscale
    (`dxf_background_renderer.py`) and is ~4.5% larger than `compute_drawing_bounds()`, which
    returns only the extent of drawing lines. Converting against the latter shifts and scales
    every pinned box by that difference.
    """
    f = _as_fraction_dict(fractions)
    if not f or not render_bounds or len(render_bounds) != 4:
        return None

    try:
        x_min_f = float(f["xMin"])
        x_max_f = float(f["xMax"])
        y_min_f = float(f["yMin"])
        y_max_f = float(f["yMax"])
        bx0, by0, bx1, by1 = (float(v) for v in render_bounds)
    except (KeyError, TypeError, ValueError) as err:
        logger.warning(f"[zone_template] Unusable zone fractions {fractions!r}: {err}")
        return None

    w = bx1 - bx0
    h = by1 - by0
    if w <= 0 or h <= 0:
        return None

    return (
        bx0 + x_min_f * w,
        by1 - y_max_f * h,
        bx0 + x_max_f * w,
        by1 - y_min_f * h,
    )


def fractions_to_absolute_polygon(
    fractions: Any,
    render_bounds: Sequence[float],
) -> Optional[list]:
    """Converts a zone's Y-DOWN outline to absolute CAD points, or None for a rectangle.

    ## The Y flip applies, the min/max swap does NOT

    `fractions_to_absolute_bbox` above swaps min and max as it flips, because "min" and "max"
    are names about magnitude and reversing the axis reverses which edge earns which name. A
    *vertex* has no such pair: it is the flip alone, `by1 - y * h`.

    Copying the box rule onto points (subtracting each y from `by1` and then re-sorting, or
    computing `by0 + y * h`) mirrors the outline vertically. The result is still a closed shape
    of the right size in the right bounding box, so nothing errors and the overlay looks
    plausible — it just excludes the opposite half of the zone from the comparison.

    Mirrors `apps/desktop/src/utils/zoneFractions.ts::fractionPointToCad`. Keep the two in step.
    """
    f = _as_fraction_dict(fractions)
    if not f or not render_bounds or len(render_bounds) != 4:
        return None

    points = f.get("points")
    if not isinstance(points, (list, tuple)) or len(points) < MIN_ZONE_POINTS:
        return None

    try:
        bx0, by0, bx1, by1 = (float(v) for v in render_bounds)
    except (TypeError, ValueError):
        return None

    w = bx1 - bx0
    h = by1 - by0
    if w <= 0 or h <= 0:
        return None

    absolute = []
    for point in points:
        p = _as_fraction_dict(point) or point
        try:
            px = float(p["x"]) if isinstance(p, dict) else float(p[0])
            py = float(p["y"]) if isinstance(p, dict) else float(p[1])
        except (KeyError, IndexError, TypeError, ValueError) as err:
            logger.warning(f"[zone_template] Unusable outline vertex {point!r}: {err}")
            return None
        absolute.append((bx0 + px * w, by1 - py * h))

    return absolute if len(absolute) >= MIN_ZONE_POINTS else None


def overrides_from_template_zones(
    zones: Optional[Dict[str, Any]],
    render_bounds: Optional[Sequence[float]],
) -> Dict[str, Any]:
    """The pure half of `resolve_zone_overrides`: template fractions → absolute boxes.

    Split out so a caller that already holds a template can apply it **without a database**.
    The offline eval runner is the reason this exists: `resolve_zone_overrides` needs a
    Beanie session, an offline run has none, and `extract_dynamic_regions_async` then
    degrades to plain detection — correct for the app, silently wrong for a measurement.
    See docs/vault/06 - .../Gotcha - Zone Templates Vanish in Offline Eval.

    Deliberately takes the **fractions**, not resolved boxes, so an offline run exercises
    `fractions_to_absolute_bbox` and `fractions_to_absolute_polygon` exactly as the app
    does. Handing it pre-resolved boxes would bypass the Y-flip — the one conversion in this
    file whose failure mode is a plausible-looking mirrored zone — and the eval would be
    blind to a regression in it.
    """
    if not zones or not render_bounds:
        return {}

    overrides: Dict[str, Any] = {}
    polygons: Dict[str, list] = {}
    for zone_key, zone_frac in zones.items():
        bbox = fractions_to_absolute_bbox(zone_frac, render_bounds)
        if not bbox:
            continue
        overrides[zone_key] = bbox
        outline = fractions_to_absolute_polygon(zone_frac, render_bounds)
        if outline:
            polygons[zone_key] = outline

    # Reshaped zones ride alongside their bounding boxes under a reserved key, so `regions`
    # values stay 4-tuples for the ~29 sites that index them. See zone_geometry.py.
    if polygons:
        overrides[ZONE_POLYGONS_KEY] = polygons
    return overrides


async def resolve_zone_overrides(
    render_bounds: Optional[Sequence[float]],
    signature: Optional[str] = None,
) -> Dict[str, Tuple[float, float, float, float]]:
    """Returns `{zone_key: absolute_bbox}` for zones pinned in this sheet's template.

    Returns an empty dict when there is no template, no render bounds, or nothing pinned —
    all of which are normal, not errors. Takes no entity list on purpose: detection has
    already run by the time this is called, and re-running it here doubled the ~220ms zone
    pass for no benefit.
    """
    if not render_bounds or len(render_bounds) != 4:
        logger.warning("[zone_template] No render_bounds; cannot apply a zone template.")
        return {}

    # Derived from render_bounds so it matches the key the desktop client saves under
    # (`zoneSignature()` in drawingsApi.ts). Deriving it from the detected frame instead
    # would look up a different key and silently miss the template.
    signature = signature or zone_signature(list(render_bounds))
    if not signature:
        return {}

    try:
        template = await ZoneTemplateDocument.find_one(
            ZoneTemplateDocument.signature == signature
        )
        # No template for this sheet's exact signature — fall back to the global
        # default, if one is designated. A signature-specific template always wins
        # (this branch is only reached when the specific lookup came back empty),
        # so the default only fills gaps for sheets nobody has aligned directly.
        if not template:
            template = await ZoneTemplateDocument.find_one(
                ZoneTemplateDocument.is_default == True  # noqa: E712
            )
            if template:
                logger.info(
                    f"[zone_template] No template for '{signature}'; applying global "
                    f"default '{template.signature}'."
                )
    except Exception as err:
        logger.warning(f"[zone_template] Template lookup failed for '{signature}': {err}")
        return {}

    if not template or not template.zones:
        return {}

    overrides = overrides_from_template_zones(template.zones, render_bounds)
    polygons = overrides.get(ZONE_POLYGONS_KEY) or {}

    if overrides:
        applied = sorted(k for k in overrides if not k.startswith("_"))
        logger.info(
            f"[zone_template] Applied {len(applied)} hand-aligned zone(s) from template "
            f"'{signature}': {applied}"
            + (f"; reshaped: {sorted(polygons)}" if polygons else "")
        )
    return overrides
