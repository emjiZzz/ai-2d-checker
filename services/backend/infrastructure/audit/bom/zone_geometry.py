"""
zone_geometry.py
================
Containment for zone shapes, which are a rectangle **or** a polygon.

A zone is a rectangle until a user inserts a node on one of its edges in the alignment editor;
from then on it carries an explicit outline. Both forms answer exactly one question here — *is
this point inside this zone* — so the rest of the pipeline never branches on shape.

## Why `regions` values are still 4-tuples

The comparison reads zone geometry as `(xmin, ymin, xmax, ymax)` at ~29 sites: growth caps,
overlap logging, crop bounds, proximity windows. Every one of those wants the **bounding box**
and would be wrong or meaningless with an outline. So a polygon zone keeps its bounding box in
`regions[zone_key]` exactly as before, and the outline rides alongside under the reserved
`_zone_polygons` key — the same smuggle-an-extra-key pattern as `safe_zones`,
`_zone_confidence` and `_anchor_matches`.

Only the places that gate *content* consult the outline:
`scope_entities_to_views`, `views_exclusions` and the orchestrator's `is_in_bbox`.

## Coordinate space

Absolute CAD units, **Y-up**, same as every other bbox in `regions`. The Y-DOWN template
fractions are converted once, in `zone_template_resolver.fractions_to_absolute_polygon`, which
mirrors `apps/desktop/src/utils/zoneFractions.ts::fractionPointToCad`. A point conversion is
the flip ALONE (`by1 - y*h`) with no min/max swap — the swap in the *box* conversion is an
artifact of the names, not of the geometry. Getting that wrong mirrors the outline vertically
and still looks like a plausible zone.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional, Sequence

# Below this a polygon encloses no area, so it is not a shape and the bounding box is used.
MIN_ZONE_POINTS = 3

# One zone's shape as used for containment: a bbox 4-tuple, optionally refined by an outline.
ZonePolygon = Sequence[Sequence[float]]

# Reserved key in `regions` holding {zone_key: [(x, y), ...]} in absolute CAD units.
ZONE_POLYGONS_KEY = "_zone_polygons"


def is_polygon(points: Any) -> bool:
    """True when `points` is a usable outline rather than absent/degenerate."""
    return isinstance(points, (list, tuple)) and len(points) >= MIN_ZONE_POINTS


def polygon_bbox(points: ZonePolygon) -> Optional[tuple]:
    """Axis-aligned bounds of an outline, or None if it is not a usable one."""
    if not is_polygon(points):
        return None
    xs = [float(p[0]) for p in points]
    ys = [float(p[1]) for p in points]
    return (min(xs), min(ys), max(xs), max(ys))


def point_in_polygon(x: float, y: float, points: ZonePolygon) -> bool:
    """Ray-casting point-in-polygon.

    Mirrors `pointInShape` in `apps/desktop/src/utils/zoneFractions.ts`. The two decide the
    same question about the same outline, and if they disagree the canvas shows a region the
    audit is not using — which is the exact class of defect the views-overlay gotcha records.

    Boundary points are not guaranteed either way, and deliberately so: a zone edge drawn
    through a text insert is ambiguous by construction, and pretending otherwise would make
    the result depend on floating-point noise rather than on the drawing.
    """
    if not is_polygon(points):
        return False
    inside = False
    n = len(points)
    j = n - 1
    for i in range(n):
        xi, yi = float(points[i][0]), float(points[i][1])
        xj, yj = float(points[j][0]), float(points[j][1])
        if (yi > y) != (yj > y):
            # x of the edge at height y; strictly-less keeps the two half-open edges consistent
            # so a vertex shared by two edges is not counted twice.
            x_at_y = (xj - xi) * (y - yi) / (yj - yi) + xi
            if x < x_at_y:
                inside = not inside
        j = i
    return inside


def point_in_shape(x: float, y: float, bbox: Any, polygon: Any = None) -> bool:
    """Whether (x, y) is inside a zone: its outline when it has one, else its bbox.

    The bbox is checked FIRST even when an outline exists. That is not redundant — it is a
    cheap reject for the overwhelming majority of entities on a sheet, and the outline's
    bounding box is exactly the bbox, so it can never exclude a point the outline would keep.
    """
    if not bbox or len(bbox) != 4:
        return False
    if not (bbox[0] <= x <= bbox[2] and bbox[1] <= y <= bbox[3]):
        return False
    if is_polygon(polygon):
        return point_in_polygon(x, y, polygon)
    return True


def zone_polygons(regions: Optional[dict]) -> dict:
    """The `{zone_key: outline}` map smuggled into `regions`, or `{}`."""
    polygons = (regions or {}).get(ZONE_POLYGONS_KEY)
    return polygons if isinstance(polygons, dict) else {}


def polygon_for(regions: Optional[dict], zone_key: str) -> Optional[list]:
    """One zone's outline, or None when it is a plain rectangle."""
    points = zone_polygons(regions).get(zone_key)
    return points if is_polygon(points) else None


def point_in_any_shape(x: float, y: float, shapes: Iterable) -> bool:
    """True when (x, y) falls inside any `(bbox, polygon)` pair."""
    for shape in shapes or ():
        if not shape:
            continue
        bbox, polygon = shape if isinstance(shape, tuple) and len(shape) == 2 else (shape, None)
        if point_in_shape(x, y, bbox, polygon):
            return True
    return False


def is_in_bbox(entity: Any, bbox: Any, polygon: Any = None) -> bool:
    """Whether an entity's insert point is inside a zone.

    The entity-level counterpart to `point_in_shape`, and the reason it lives here rather
    than in the comparison layer: both `orchestrator` and `title_matcher` need it, and a
    second copy of "is this entity in this zone" is the drift shape this codebase has
    already paid for four times.

    `polygon` is the hand-drawn outline for a zone the user reshaped in the editor; when
    absent the bbox is the shape, which is every un-reshaped zone. Passing it matters most
    for the EXCLUSION calls in safe_filter: excluding on a reshaped zone's bounding box
    would drop content from the notch the user deliberately cut out of it, and that content
    belongs to no other category — a silent false negative.
    """
    if not bbox:
        return False
    geom = getattr(entity, "geometry", {})
    if not geom or "insert" not in geom or len(geom["insert"]) < 2:
        return False
    x, y = geom["insert"][0], geom["insert"][1]
    return point_in_shape(x, y, bbox, polygon)
