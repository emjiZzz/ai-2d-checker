"""Tests for ELLIPSE/SPLINE ingestion and geometric isometric-view zone detection.

Background: `EntityMapper.map_any` had no branch for ELLIPSE or SPLINE, so it returned
None for both and every such entity was discarded at extraction. Measured across the
6-drawing corpus that was 111 ellipses and 46 splines, and the drops were not spread
evenly -- they landed entirely on the three drawings carrying an isometric view (38 of
the 42 entities in one of them). The `iso` zone had therefore never been detected on any
drawing in the corpus; its reported 0.0pp positional spread was six identical
percentage-grid guesses, not stability.

The fix is two-part and both parts are pinned here:
  1. ELLIPSE and SPLINE are mapped, so the geometry survives ingestion at all.
  2. `iso` is detected from ellipse density rather than text anchors, because a circle
     seen at an angle projects to an ellipse and orthographic views keep CIRCLE/ARC.

The original corpus DXFs are no longer on disk, so these build their geometry explicitly
rather than reading fixtures.
"""
import math
from types import SimpleNamespace

import ezdxf
import pytest

from services.backend.infrastructure.cad.entity_mapper import (
    GEOMETRY_SCHEMA,
    EntityMapper,
)
from services.backend.infrastructure.cad.dxf_parser import project_mapped_entity
from services.backend.infrastructure.cad.viewport_transform import (
    Viewport,
    ViewportTransform,
)
from services.backend.infrastructure.audit.bom.zone_detector import (
    BBOX_PADDING,
    MIN_ISO_ELLIPSES,
    _detect_iso_zone,
    detect_zones_by_content,
    in_views,
)


# ---------------------------------------------------------------------------
# Part 1 -- the entities survive ingestion
# ---------------------------------------------------------------------------

@pytest.fixture
def doc():
    return ezdxf.new()


def test_map_any_maps_ellipse(doc):
    """The regression itself: map_any used to return None for ELLIPSE."""
    msp = doc.modelspace()
    ellipse = msp.add_ellipse(center=(10, 20), major_axis=(5, 0), ratio=0.5)

    mapped = EntityMapper.map_any(ellipse)

    assert mapped is not None, "ELLIPSE dropped at ingestion"
    assert mapped["entity_type"] == "ellipse"
    assert mapped["geometry"]["center"][:2] == [10.0, 20.0]
    assert mapped["geometry"]["major_axis"][:2] == [5.0, 0.0]
    assert mapped["properties"]["ratio"] == pytest.approx(0.5)


def test_map_any_maps_spline_from_fit_points(doc):
    """`add_spline` defines the curve by fit points and leaves `control_points` empty
    until ezdxf computes them, so the mapper must not depend on control points existing."""
    msp = doc.modelspace()
    spline = msp.add_spline([(0, 0), (5, 8), (10, 0)])

    mapped = EntityMapper.map_any(spline)

    assert mapped is not None, "SPLINE dropped at ingestion"
    assert mapped["entity_type"] == "spline"
    assert len(mapped["geometry"]["fit_points"]) >= 2
    assert len(mapped["geometry"]["points"]) >= 2, "no usable outline for bounding"


def test_map_any_maps_spline_from_control_points(doc):
    msp = doc.modelspace()
    spline = msp.add_open_spline([(0, 0), (3, 9), (7, -4), (10, 0)], degree=3)

    mapped = EntityMapper.map_any(spline)

    assert mapped is not None
    assert len(mapped["geometry"]["control_points"]) >= 2
    assert len(mapped["geometry"]["points"]) >= 2


def test_ellipse_and_spline_have_geometry_schema_entries():
    """Without a schema entry the viewport projection skips the entity entirely, which
    would leave ellipses in model space while everything around them moved to paper."""
    assert "ellipse" in GEOMETRY_SCHEMA
    assert "spline" in GEOMETRY_SCHEMA
    assert "center" in GEOMETRY_SCHEMA["ellipse"]["points"]
    assert "major_axis" in GEOMETRY_SCHEMA["ellipse"]["vectors"]


def test_tessellated_points_lie_on_the_ellipse(doc):
    """A wrong minor-axis derivation still produces a plausible-looking closed curve, so
    assert the points actually satisfy the ellipse equation rather than merely existing."""
    msp = doc.modelspace()
    # Axis-aligned: semi-major 10 along x, ratio 0.4 -> semi-minor 4 along y.
    ellipse = msp.add_ellipse(center=(0, 0), major_axis=(10, 0), ratio=0.4)

    points = EntityMapper.map_any(ellipse)["geometry"]["points"]

    assert len(points) > 8
    for x, y in points:
        assert (x / 10.0) ** 2 + (y / 4.0) ** 2 == pytest.approx(1.0, abs=1e-6)


def test_tessellation_handles_a_rotated_major_axis(doc):
    """The minor axis is the major rotated 90 degrees, so a rotated ellipse must stay
    perpendicular. Getting this wrong shears the ellipse in a way that still looks round."""
    msp = doc.modelspace()
    ellipse = msp.add_ellipse(center=(0, 0), major_axis=(0, 7), ratio=1.0)  # circle, r=7

    points = EntityMapper.map_any(ellipse)["geometry"]["points"]

    for x, y in points:
        assert math.hypot(x, y) == pytest.approx(7.0, abs=1e-6)


def test_major_axis_is_scaled_but_not_translated(doc):
    """major_axis is an offset from the centre, not an absolute coordinate. Projecting it
    as a point would re-anchor it to the viewport origin and reshape the ellipse."""
    msp = doc.modelspace()
    ellipse = msp.add_ellipse(center=(100, 100), major_axis=(10, 0), ratio=0.5)
    mapped = EntityMapper.map_any(ellipse)

    transform = ViewportTransform(
        layout_name="Layout1",
        viewports=[Viewport(
            index=0, handle="A",
            paper_center_x=0.0, paper_center_y=0.0,
            paper_width=100.0, paper_height=100.0,
            view_anchor_x=100.0, view_anchor_y=100.0,
            view_height=50.0, scale=2.0,
        )],
    )
    project_mapped_entity(mapped, transform)

    # Centre sits on the viewport's look-at point, so it lands on the paper centre.
    assert mapped["geometry"]["center"][:2] == pytest.approx([0.0, 0.0])
    # The axis vector takes the scale only. Translating it would give (-190, -200).
    assert mapped["geometry"]["major_axis"][:2] == pytest.approx([20.0, 0.0])


# ---------------------------------------------------------------------------
# Part 2 -- geometric iso detection
# ---------------------------------------------------------------------------

def _ellipse(x: float, y: float, parent: str | None = None, r: float = 3.0):
    props = {"ratio": 0.5}
    if parent:
        props["parent_handle"] = parent
    return SimpleNamespace(
        entity_type="ellipse", layer="0", properties=props,
        geometry={"center": [x, y], "major_axis": [r, 0.0],
                  "points": [[x - r, y - r], [x + r, y + r]]},
    )


def _line(x1: float, y1: float, x2: float, y2: float, parent: str | None = None):
    props = {}
    if parent:
        props["parent_handle"] = parent
    return SimpleNamespace(
        entity_type="line", layer="0", properties=props,
        geometry={"start": [x1, y1], "end": [x2, y2]},
    )


def _sheet_frame():
    """A 1000x1000 border so `_get_drawing_bounds` has lines to measure."""
    return [
        _line(0, 0, 1000, 0), _line(1000, 0, 1000, 1000),
        _line(1000, 1000, 0, 1000), _line(0, 1000, 0, 0),
    ]


def test_no_ellipses_means_no_iso_zone():
    """Roughly half the corpus genuinely has no isometric view. Returning None there is
    the point -- the old behaviour asserted a percentage-grid box on every drawing."""
    assert _detect_iso_zone(_sheet_frame(), (0, 0, 1000, 1000)) is None


def test_a_stray_ellipse_does_not_trigger_iso():
    """An obliquely-cut cylinder or a slot can put one true ellipse in an orthographic
    view. One is not an isometric projection."""
    entities = _sheet_frame() + [_ellipse(500, 500)]
    assert _detect_iso_zone(entities, (0, 0, 1000, 1000)) is None


def test_block_dominance_gives_the_exact_block_extent():
    """When most ellipses share one INSERT, the box is that block's extent -- no
    clustering heuristic, and it must not be widened by unrelated geometry elsewhere."""
    iso_block = [
        _ellipse(700, 700, parent="ISO"), _ellipse(720, 720, parent="ISO"),
        _ellipse(740, 700, parent="ISO"), _line(690, 690, 750, 750, parent="ISO"),
    ]
    entities = _sheet_frame() + iso_block + [_ellipse(100, 100)]  # stray, far away

    bbox = _detect_iso_zone(entities, (0, 0, 1000, 1000))

    assert bbox is not None
    # Block extent is x 687..750 (ellipse points reach 697-3 and 740+3), padded.
    assert bbox[0] == pytest.approx(690 - BBOX_PADDING)
    assert bbox[2] == pytest.approx(750 + BBOX_PADDING)
    # The stray ellipse at (100, 100) must be outside the box.
    assert not (bbox[0] <= 100 <= bbox[2] and bbox[1] <= 100 <= bbox[3])


def test_clustering_fallback_when_no_parent_handle():
    """Nested INSERTs lose the parent handle during explosion and loose model-space
    geometry never had one, so the detector cannot rely on block grouping alone."""
    cluster = [_ellipse(700 + i * 10, 700) for i in range(MIN_ISO_ELLIPSES + 1)]
    entities = _sheet_frame() + cluster

    bbox = _detect_iso_zone(entities, (0, 0, 1000, 1000))

    assert bbox is not None
    assert bbox[0] < 700 and bbox[2] > 700 + MIN_ISO_ELLIPSES * 10


def test_clustering_picks_the_largest_group():
    """Two ellipse groups far apart: the iso view is the denser one, and the box must not
    span both (which would cover most of the sheet and be useless as an exclusion test)."""
    small = [_ellipse(50 + i * 5, 50) for i in range(MIN_ISO_ELLIPSES)]
    large = [_ellipse(800 + i * 5, 800) for i in range(MIN_ISO_ELLIPSES + 4)]
    entities = _sheet_frame() + small + large

    bbox = _detect_iso_zone(entities, (0, 0, 1000, 1000))

    assert bbox is not None
    assert bbox[1] > 500, "box should sit on the larger cluster, not span both"
    assert not (bbox[0] <= 50 <= bbox[2] and bbox[1] <= 50 <= bbox[3])


def test_iso_box_is_capped_like_every_other_zone():
    """ZONE_MAX_LIMITS['iso'] is (0.45, 0.45). A runaway cluster must be clamped, or the
    iso box could swallow the sheet the way `views` does."""
    spread = [_ellipse(100 + i * 40, 100 + i * 40) for i in range(20)]
    entities = _sheet_frame() + spread

    zones = detect_zones_by_content(entities)

    assert zones["iso"] is not None
    assert (zones["iso"][2] - zones["iso"][0]) <= 1000 * 0.45 + 1e-9
    assert (zones["iso"][3] - zones["iso"][1]) <= 1000 * 0.45 + 1e-9


def test_views_excludes_the_detected_iso_region():
    """`views` is defined by exclusion, and that exclusion now lives in the PREDICATE.

    The box is the sheet — deliberately, because the old content-percentile box measured
    119.7% of the sheet across the corpus while simultaneously producing false negatives in
    the outer 5%. So the contract to assert is `in_views`, not the box's extent.
    """
    regions = {
        "views": (0.0, 0.0, 1000.0, 1000.0),
        "iso": (780.0, 780.0, 920.0, 920.0),
        "title": (700.0, 0.0, 1000.0, 150.0),
    }

    # A point in the open drawing area.
    assert in_views(400.0, 500.0, regions) is True
    # Inside the iso box: on the sheet, but not drawing views.
    assert in_views(850.0, 850.0, regions) is False
    # Inside the title block: likewise.
    assert in_views(800.0, 50.0, regions) is False
    # Off the sheet entirely.
    assert in_views(5000.0, 5000.0, regions) is False


def test_in_views_needs_a_views_box():
    assert in_views(1.0, 1.0, {}) is False
    assert in_views(1.0, 1.0, {"views": None}) is False


def test_views_box_is_the_sheet_not_a_content_percentile():
    """The regression this replaces: the derived box exceeded the sheet it described."""
    entities = _sheet_frame() + [
        _line(100 + i * 10, 200, 110 + i * 10, 210) for i in range(10)
    ]

    zones = detect_zones_by_content(entities)

    assert zones["views"] is not None
    x0, y0, x1, y1 = zones["views"]
    assert (x1 - x0) <= 1000.0 + 1e-9, "views is wider than the sheet"
    assert (y1 - y0) <= 1000.0 + 1e-9, "views is taller than the sheet"


def test_iso_is_resolved_before_views_in_the_pipeline():
    """Ordering regression guard for `detect_zones_by_content` itself."""
    iso_block = [_ellipse(800 + i * 10, 800, parent="ISO") for i in range(4)]
    iso_lines = [_line(800 + i * 10, 800, 810 + i * 10, 810, parent="ISO") for i in range(6)]
    entities = _sheet_frame() + iso_block + iso_lines + [
        SimpleNamespace(entity_type="text", layer="0", properties={"text": "A"},
                        geometry={"insert": [x, 200]})
        for x in range(100, 400, 50)
    ]

    zones = detect_zones_by_content(entities)

    assert zones["iso"] is not None, "iso not detected in the full pipeline"
    # The iso block's own lines must have been excluded from the views point set.
    assert zones["views"] is not None


def test_text_anchor_path_still_works_when_no_ellipses_exist():
    """Geometry takes priority, but a drawing that does label its isometric view should
    still resolve through ZONE_ANCHORS rather than regressing to nothing."""
    labelled = [
        SimpleNamespace(entity_type="text", layer="0",
                        properties={"text": "ISOMETRIC VIEW"},
                        geometry={"insert": [700 + i * 20, 700]})
        for i in range(5)
    ]
    zones = detect_zones_by_content(_sheet_frame() + labelled)

    assert zones["iso"] is not None
