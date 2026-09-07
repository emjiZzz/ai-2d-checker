"""Reshaped zones: a zone box is a rectangle until a node is inserted on one of its edges.

Two things are easy to get wrong here and neither raises:

1. The Y flip. Template fractions are Y-DOWN, CAD is Y-up. The *box* conversion swaps min
   and max as it flips; a *vertex* conversion is the flip alone. Applying the box rule to a
   point mirrors the outline vertically — still a closed shape, still the right size, still
   inside the right bounding box, just excluding the opposite half of the zone.

2. Excluding on the bounding box. A reshaped sibling zone that still excludes by its bbox
   drops content from the notch the user deliberately cut out of it, and that content lands in
   no category at all.

See docs/vault/06 - Gotchas & Debugging Lessons/
  Gotcha - A Reshaped Zone Is Not Its Bounding Box.md
"""
from types import SimpleNamespace

from services.backend.domain.models.zone_template import ZoneFractions
from services.backend.infrastructure.audit.bom.zone_detector import (
    scope_entities_to_views,
    views_exclusions,
)
from services.backend.infrastructure.audit.bom.zone_geometry import (
    ZONE_POLYGONS_KEY,
    is_polygon,
    point_in_any_shape,
    point_in_polygon,
    point_in_shape,
    polygon_bbox,
    polygon_for,
)
from services.backend.infrastructure.audit.bom.zone_template_resolver import (
    fractions_to_absolute_bbox,
    fractions_to_absolute_polygon,
)

# An L-shape: full square with the TOP-RIGHT quadrant cut out, in Y-DOWN fractions.
#   (0,0) ── (0.5,0)
#     │         │
#     │      (0.5,0.5) ── (1,0.5)
#     │                      │
#   (0,1) ────────────────  (1,1)
L_SHAPE = [
    {"x": 0.0, "y": 0.0},
    {"x": 0.5, "y": 0.0},
    {"x": 0.5, "y": 0.5},
    {"x": 1.0, "y": 0.5},
    {"x": 1.0, "y": 1.0},
    {"x": 0.0, "y": 1.0},
]
BOUNDS = (0.0, 0.0, 100.0, 100.0)  # square sheet keeps the arithmetic readable


# --- geometry ------------------------------------------------------------------------------

def test_point_in_polygon_separates_inside_from_the_notch():
    square = [(0, 0), (10, 0), (10, 10), (0, 10)]
    assert point_in_polygon(5, 5, square) is True
    assert point_in_polygon(15, 5, square) is False


def test_a_degenerate_outline_is_not_a_polygon():
    # Two points enclose no area. Treating them as a shape would make the zone contain
    # nothing at all, which is the silent direction.
    assert is_polygon([(0, 0), (1, 1)]) is False
    assert is_polygon([]) is False
    assert is_polygon(None) is False
    assert polygon_bbox([(0, 0), (1, 1)]) is None


def test_point_in_shape_falls_back_to_the_bbox_without_an_outline():
    bbox = (0, 0, 10, 10)
    assert point_in_shape(5, 5, bbox, None) is True
    assert point_in_shape(15, 5, bbox, None) is False


def test_point_in_shape_uses_the_outline_when_there_is_one():
    # L-shape in CAD units: the top-right quadrant is NOT part of the zone, but IS inside
    # the bounding box. This is the whole difference the feature turns on.
    l_cad = [(0, 0), (10, 0), (10, 5), (5, 5), (5, 10), (0, 10)]
    bbox = polygon_bbox(l_cad)
    assert bbox == (0, 0, 10, 10)
    assert point_in_shape(2, 2, bbox, l_cad) is True     # in the L
    assert point_in_shape(8, 8, bbox, l_cad) is False    # in the notch
    assert point_in_shape(8, 8, bbox, None) is True      # ...but inside the bbox


# --- the Y flip ----------------------------------------------------------------------------

def test_outline_conversion_flips_y_without_swapping_min_and_max():
    frac = ZoneFractions(xMin=0.0, xMax=1.0, yMin=0.0, yMax=0.5, points=L_SHAPE)
    outline = fractions_to_absolute_polygon(frac, BOUNDS)

    # Fraction y=0 is the TOP of the sheet, which in CAD (Y-up) is the LARGEST y.
    assert outline[0] == (0.0, 100.0)   # (0, 0) fraction -> top-left
    assert outline[4] == (100.0, 0.0)   # (1, 1) fraction -> bottom-right
    # If the box rule had been copied onto the vertices, y would read 0.0 and 100.0 the other
    # way round and the L would open toward the bottom instead of the top.
    assert outline[2] == (50.0, 50.0)   # the inner corner stays put on a symmetric sheet


def test_outline_agrees_with_the_box_conversion_on_a_rectangle():
    # A 4-point outline of a rectangle must land exactly on the corners the box conversion
    # produces — if the two disagree, the overlay and the audit disagree.
    frac = ZoneFractions(
        xMin=0.2, xMax=0.8, yMin=0.1, yMax=0.6,
        points=[
            {"x": 0.2, "y": 0.1}, {"x": 0.8, "y": 0.1},
            {"x": 0.8, "y": 0.6}, {"x": 0.2, "y": 0.6},
        ],
    )
    bbox = fractions_to_absolute_bbox(frac, BOUNDS)
    outline = fractions_to_absolute_polygon(frac, BOUNDS)
    assert polygon_bbox(outline) == bbox


def test_no_outline_for_a_plain_rectangle():
    frac = ZoneFractions(xMin=0.0, xMax=1.0, yMin=0.0, yMax=1.0)
    assert fractions_to_absolute_polygon(frac, BOUNDS) is None


def test_a_too_short_outline_is_dropped_at_the_schema():
    # Reaches the DB as a rectangle rather than as a shape that contains nothing.
    frac = ZoneFractions(
        xMin=0, xMax=1, yMin=0, yMax=1, points=[{"x": 0, "y": 0}, {"x": 1, "y": 1}]
    )
    assert frac.points is None
    assert frac.outline() is None


def test_outline_vertices_are_clamped_like_the_scalars():
    frac = ZoneFractions(
        xMin=0, xMax=1, yMin=0, yMax=1,
        points=[{"x": -3.0, "y": 0.0}, {"x": 9.0, "y": 0.0}, {"x": 0.5, "y": 4.0}],
    )
    assert [(p.x, p.y) for p in frac.points] == [(0.0, 0.0), (1.0, 0.0), (0.5, 1.0)]


# --- the engine ----------------------------------------------------------------------------

def _text(x, y):
    return SimpleNamespace(
        entity_type="text", geometry={"insert": [x, y, 0.0]},
        properties={"text": "X"}, layer="0",
    )


L_CAD = [(0, 0), (100, 0), (100, 50), (50, 50), (50, 100), (0, 100)]


def test_views_scoping_drops_entities_in_the_notch():
    views_bbox = (0, 0, 100, 100)
    in_the_l = _text(10, 10)
    in_the_notch = _text(80, 80)

    kept_rect = scope_entities_to_views([in_the_l, in_the_notch], views_bbox, [], None)
    kept_poly = scope_entities_to_views([in_the_l, in_the_notch], views_bbox, [], L_CAD)

    assert kept_rect == [in_the_l, in_the_notch]   # rectangle keeps both
    assert kept_poly == [in_the_l]                 # reshaped keeps only the L


def test_a_reshaped_sibling_excludes_only_what_it_covers():
    # THE false-negative guard. `notes` is reshaped into an L; an entity in its notch is not
    # notes content, so `views` must keep it. Excluding on the bounding box would drop it and
    # no category would report it.
    regions = {
        "views": (0, 0, 100, 100),
        "notes": (0, 0, 100, 100),
        ZONE_POLYGONS_KEY: {"notes": L_CAD},
    }
    in_notes = _text(10, 10)
    in_the_notch = _text(80, 80)

    kept = scope_entities_to_views(
        [in_notes, in_the_notch], (0, 0, 100, 100), views_exclusions(regions), None
    )
    assert kept == [in_the_notch]


def test_views_exclusions_pairs_each_box_with_its_outline():
    regions = {
        "views": (0, 0, 100, 100),
        "notes": (0, 0, 100, 100),
        "bom": (0, 0, 10, 10),
        ZONE_POLYGONS_KEY: {"notes": L_CAD},
    }
    excl = views_exclusions(regions)
    assert ((0, 0, 100, 100), L_CAD) in excl
    assert ((0, 0, 10, 10), None) in excl
    # The reserved key is not itself a zone.
    assert all(bbox != regions[ZONE_POLYGONS_KEY] for bbox, _ in excl)


def test_point_in_any_shape_accepts_bare_boxes_too():
    # Existing callers pass plain bboxes; they must keep working.
    assert point_in_any_shape(5, 5, [(0, 0, 10, 10)]) is True
    assert point_in_any_shape(50, 50, [(0, 0, 10, 10)]) is False
    assert point_in_any_shape(80, 80, [((0, 0, 100, 100), L_CAD)]) is False


def test_polygon_for_returns_none_for_an_unreshaped_zone():
    regions = {"views": (0, 0, 100, 100), ZONE_POLYGONS_KEY: {"notes": L_CAD}}
    assert polygon_for(regions, "views") is None
    assert polygon_for(regions, "notes") == L_CAD
    assert polygon_for({}, "views") is None
    assert polygon_for(None, "views") is None
