"""3D coordinate preservation through DXF ingestion.

Two defects are pinned here:

* `project_point` returned `[result.x, result.y]`, so every Z was destroyed on any
  drawing with a paper-space viewport -- 6 of the 11 files in the local corpus. Drawings
  without a layout hit the identity early-return and kept theirs, so stored geometry had
  *mixed* arity and the loss was invisible to anything reading only `[0]` and `[1]`.
* `map_polyline` hardcoded `0.0` for LWPOLYLINE instead of reading `dxf.elevation`,
  flattening every one of them onto the origin plane.

The test that matters most here is `test_projected_xy_is_bit_identical_with_and_without_z`:
the fix has to be provably Z-only, because X/Y are what the comparison engine matches on.
"""

import ezdxf
import pytest

from services.backend.infrastructure.cad.dxf_parser import (
    UNMAPPED_3D_TYPES,
    project_mapped_entity,
    summarize_three_d,
)
from services.backend.infrastructure.cad.entity_mapper import EntityMapper
from services.backend.infrastructure.cad.viewport_transform import (
    NO_VIEWPORT,
    Viewport,
    ViewportTransform,
)

EPSILON = 1e-9

# scale=2.0 is deliberate: a Z that were (wrongly) run through the viewport scale would
# come back doubled, which no epsilon can hide.
VIEWPORT_SCALE = 2.0


def _transform() -> ViewportTransform:
    return ViewportTransform(
        "Layout1",
        [
            Viewport(
                index=0, handle="VP0",
                paper_center_x=200.0, paper_center_y=150.0,
                paper_width=300.0, paper_height=200.0,
                view_center_x=50.0, view_center_y=25.0,
                view_height=100.0, scale=VIEWPORT_SCALE,
            )
        ],
    )


def _line(start, end) -> dict:
    return {
        "entity_type": "line",
        "layer": "0",
        "properties": {},
        "geometry": {"start": list(start), "end": list(end)},
    }


# ── D1: Z survives the paper-space projection ────────────────────────────────────────

def test_projection_preserves_z_on_a_viewport_drawing():
    mapped = _line((50.0, 25.0, 7.5), (60.0, 35.0, -3.25))
    index, scale = project_mapped_entity(mapped, _transform())

    assert index == 0
    assert scale == VIEWPORT_SCALE
    assert len(mapped["geometry"]["start"]) == 3
    assert mapped["geometry"]["start"][2] == pytest.approx(7.5, abs=EPSILON)
    assert mapped["geometry"]["end"][2] == pytest.approx(-3.25, abs=EPSILON)


def test_z_is_carried_through_not_scaled():
    """A viewport is a window onto the XY plane; it has no Z axis to map into."""
    mapped = _line((50.0, 25.0, 10.0), (60.0, 35.0, 10.0))
    project_mapped_entity(mapped, _transform())

    # Would be 20.0 if Z had been run through the viewport scale.
    assert mapped["geometry"]["start"][2] == pytest.approx(10.0, abs=EPSILON)


def test_projected_xy_is_bit_identical_with_and_without_z():
    """The regression test: preserving Z must not perturb X or Y by even one ULP.

    X/Y are what spatial matching compares on, so any drift here would move findings.
    """
    with_z = _line((50.0, 25.0, 42.0), (60.0, 35.0, -17.0))
    without_z = _line((50.0, 25.0), (60.0, 35.0))

    project_mapped_entity(with_z, _transform())
    project_mapped_entity(without_z, _transform())

    for key in ("start", "end"):
        assert with_z["geometry"][key][:2] == without_z["geometry"][key][:2]


def test_projected_xy_matches_the_transform_directly():
    """Pin the actual projected values, not just their agreement with each other."""
    mapped = _line((50.0, 25.0, 9.0), (60.0, 35.0, 9.0))
    transform = _transform()
    expected = transform.project(50.0, 25.0, 0)

    project_mapped_entity(mapped, transform)

    assert mapped["geometry"]["start"][0] == pytest.approx(expected.x, abs=EPSILON)
    assert mapped["geometry"]["start"][1] == pytest.approx(expected.y, abs=EPSILON)


def test_two_component_points_stay_two_component():
    """Arity is preserved, not normalised to 3.

    `bbox` and the hatch/ellipse/spline tessellations are genuinely 2D. Padding them with
    a fabricated z=0 would invent an elevation that the source file never stated.
    """
    mapped = {
        "entity_type": "text",
        "layer": "0",
        "properties": {"bbox": [[50.0, 25.0], [60.0, 35.0]]},
        "geometry": {"insert": [50.0, 25.0]},
    }
    project_mapped_entity(mapped, _transform())

    assert len(mapped["geometry"]["insert"]) == 2
    assert all(len(corner) == 2 for corner in mapped["properties"]["bbox"])


def test_identity_transform_leaves_z_alone():
    """A drawing with no paper-space viewport keeps its coordinates verbatim."""
    mapped = _line((1.0, 2.0, 3.0), (4.0, 5.0, 6.0))
    index, scale = project_mapped_entity(mapped, ViewportTransform())

    assert (index, scale) == (NO_VIEWPORT, 1.0)
    assert mapped["geometry"]["start"] == [1.0, 2.0, 3.0]
    assert mapped["geometry"]["end"] == [4.0, 5.0, 6.0]


# ── D3: LWPOLYLINE elevation ─────────────────────────────────────────────────────────

def test_lwpolyline_elevation_reaches_geometry():
    doc = ezdxf.new("R2000")
    msp = doc.modelspace()
    pline = msp.add_lwpolyline(
        [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)],
        format="xy",
        dxfattribs={"elevation": 12.5},
    )

    mapped = EntityMapper.map_polyline(pline)
    points = mapped["geometry"]["points"]

    assert len(points) == 3
    assert all(p[2] == pytest.approx(12.5, abs=EPSILON) for p in points)


def test_lwpolyline_without_elevation_is_flat():
    doc = ezdxf.new("R2000")
    pline = doc.modelspace().add_lwpolyline([(0.0, 0.0), (5.0, 5.0)], format="xy")

    mapped = EntityMapper.map_polyline(pline)

    assert all(p[2] == pytest.approx(0.0, abs=EPSILON) for p in mapped["geometry"]["points"])


# ── B3: the three_d metadata summary ─────────────────────────────────────────────────

def test_flat_drawing_reports_no_3d():
    summary = summarize_three_d([_line((0.0, 0.0, 0.0), (1.0, 1.0, 0.0))], {})

    assert summary["has_3d"] is False
    assert summary["renderable"] is False
    assert summary["nonzero_z"] == 0
    assert summary["entity_types"] == {}


def test_nonzero_z_is_reported_and_ranged():
    summary = summarize_three_d(
        [_line((0.0, 0.0, -4.0), (1.0, 1.0, 9.0)), _line((0.0, 0.0), (1.0, 1.0))],
        {},
    )

    assert summary["has_3d"] is True
    assert summary["renderable"] is True
    assert summary["nonzero_z"] == 2
    assert summary["z_range"] == [-4.0, 9.0]
    assert summary["entity_types"] == {"line": 2}


def test_dropped_solids_are_3d_but_not_renderable():
    """The distinction the whole summary exists for.

    A drawing full of 3DSOLIDs has no non-zero Z anywhere in its *mapped* entities,
    because the solids never became mapped entities at all. Reporting that as "flat"
    would make a silent ingestion drop look like a property of the drawing.
    """
    summary = summarize_three_d(
        [_line((0.0, 0.0, 0.0), (1.0, 1.0, 0.0))],
        {"3DSOLID": 3, "3DFACE": 128},
    )

    assert summary["has_3d"] is True
    assert summary["renderable"] is False
    assert summary["nonzero_z"] == 0
    assert summary["unmapped_types"] == {"3DSOLID": 3, "3DFACE": 128}


def test_ellipse_major_axis_is_not_counted_as_elevation():
    """`major_axis` is a direction vector from the centre, not a coordinate.

    Counting its third component would report a flat ellipse as 3D content.
    """
    summary = summarize_three_d(
        [{
            "entity_type": "ellipse",
            "layer": "0",
            "properties": {},
            "geometry": {
                "center": [0.0, 0.0, 0.0],
                "major_axis": [1.0, 0.0, 5.0],
                "points": [[0.0, 0.0], [1.0, 1.0]],
            },
        }],
        {},
    )

    assert summary["nonzero_z"] == 0
    assert summary["has_3d"] is False


def test_point_list_groups_are_walked():
    """Hatch paths are a list of lists; a naive walk misses them entirely."""
    summary = summarize_three_d(
        [{
            "entity_type": "hatch",
            "layer": "0",
            "properties": {},
            "geometry": {"paths": [[[0.0, 0.0, 3.0], [1.0, 1.0, 3.0]]], "boundary_points": []},
        }],
        {},
    )

    assert summary["nonzero_z"] == 2
    assert summary["entity_types"] == {"hatch": 2}


def test_unmapped_3d_types_covers_what_map_any_drops():
    """Guard against the list drifting out of step with `map_any`.

    If a mapper is added for one of these, it must come off this list -- otherwise the
    entity would be both mapped and reported as dropped.
    """
    doc = ezdxf.new("R2000")
    msp = doc.modelspace()
    face = msp.add_3dface([(0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)])

    assert face.dxftype() in UNMAPPED_3D_TYPES
    assert EntityMapper.map_any(face) is None
