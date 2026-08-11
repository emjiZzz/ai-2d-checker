"""Phase 1 foundation tests: entity model fidelity + invertible viewport transform.

These cover the three defects Phase 1 exists to fix:
  1. lineweight/linetype were never extracted, so hidden and centre lines rendered
     solid and every stroke resolved to width 1.0.
  2. The model->paper projection was one-way (the scale was discarded) and was only
     applied to 6 of the 11 geometry-bearing entity types.
  3. Text bbox failed silently to None.
"""

import math
from pathlib import Path

import ezdxf
import pytest

from services.backend.infrastructure.cad.dxf_parser import DXFParser, project_mapped_entity
from services.backend.infrastructure.cad.entity_mapper import GEOMETRY_SCHEMA, EntityMapper
from services.backend.infrastructure.cad.viewport_transform import (
    NO_VIEWPORT,
    TRANSFORM_VERSION,
    Viewport,
    ViewportTransform,
)
from services.backend.infrastructure.storage.path_resolver import bootstrap_storage, get_storage_root

EPSILON = 1e-6


@pytest.fixture(scope="module", autouse=True)
def setup_storage():
    bootstrap_storage()
    yield


def _viewport(index=0, scale_num=200.0, view_height=100.0):
    return Viewport(
        index=index,
        handle=f"VP{index}",
        paper_center_x=200.0,
        paper_center_y=150.0,
        paper_width=300.0,
        paper_height=scale_num,
        view_anchor_x=50.0,
        view_anchor_y=25.0,
        view_height=view_height,
        scale=scale_num / view_height,
    )


# --------------------------------------------------------------------------
# 1. Transform invertibility -- the property that unblocks CAD writeback
# --------------------------------------------------------------------------

def test_identity_transform_round_trips():
    t = ViewportTransform()
    assert t.is_identity
    for x, y in [(0.0, 0.0), (-15.5, 900.25), (1e6, -1e6)]:
        fwd = t.project(x, y)
        back = t.unproject(fwd.x, fwd.y, fwd.viewport_index)
        assert fwd.viewport_index == NO_VIEWPORT
        assert math.isclose(back.x, x, abs_tol=EPSILON)
        assert math.isclose(back.y, y, abs_tol=EPSILON)


def test_single_viewport_round_trips():
    t = ViewportTransform("Layout1", [_viewport()])
    for x, y in [(0.0, 0.0), (50.0, 25.0), (-120.0, 480.0), (99.9, -3.25)]:
        fwd = t.project(x, y)
        back = t.unproject(fwd.x, fwd.y, fwd.viewport_index)
        assert math.isclose(back.x, x, abs_tol=EPSILON), f"x drift for {(x, y)}"
        assert math.isclose(back.y, y, abs_tol=EPSILON), f"y drift for {(x, y)}"


def test_multi_viewport_round_trips_when_index_is_carried():
    """Overlapping viewports make point->viewport ambiguous, so the recorded index
    is what makes the inverse exact. This is why entities persist `viewport_index`."""
    vp_a = _viewport(index=0, scale_num=200.0, view_height=100.0)
    vp_b = Viewport(
        index=1, handle="VP1",
        paper_center_x=600.0, paper_center_y=150.0,
        paper_width=300.0, paper_height=200.0,
        view_anchor_x=50.0, view_anchor_y=25.0,
        view_height=400.0, scale=0.5,
    )
    t = ViewportTransform("Layout1", [vp_a, vp_b])

    for index in (0, 1):
        for x, y in [(10.0, 10.0), (50.0, 25.0), (-200.0, 300.0)]:
            fwd = t.project(x, y, viewport_index=index)
            assert fwd.viewport_index == index
            back = t.unproject(fwd.x, fwd.y, viewport_index=index)
            assert math.isclose(back.x, x, abs_tol=EPSILON)
            assert math.isclose(back.y, y, abs_tol=EPSILON)


def test_transform_survives_serialization():
    t = ViewportTransform("Layout1", [_viewport(), _viewport(index=1)])
    restored = ViewportTransform.from_dict(t.to_dict())
    assert restored.layout_name == "Layout1"
    assert len(restored.viewports) == 2
    fwd = t.project(33.0, 44.0)
    fwd2 = restored.project(33.0, 44.0)
    assert math.isclose(fwd.x, fwd2.x, abs_tol=EPSILON)
    assert math.isclose(fwd.y, fwd2.y, abs_tol=EPSILON)


def test_transform_version_mismatch_falls_back_to_identity():
    payload = ViewportTransform("Layout1", [_viewport()]).to_dict()
    payload["version"] = TRANSFORM_VERSION + 99
    assert ViewportTransform.from_dict(payload).is_identity


# --------------------------------------------------------------------------
# 2. Projection covers every geometry-bearing entity type
# --------------------------------------------------------------------------

def _build_mapped(entity_type, geometry, properties=None):
    return {
        "entity_type": entity_type,
        "layer": "0",
        "properties": properties or {},
        "geometry": geometry,
    }


ENTITY_GEOMETRY_SAMPLES = {
    "line": {"start": [10.0, 20.0, 0.0], "end": [30.0, 40.0, 0.0]},
    "circle": {"center": [10.0, 20.0, 0.0], "radius": 5.0},
    "arc": {"center": [10.0, 20.0, 0.0], "radius": 5.0},
    "polyline": {"points": [[0.0, 0.0, 0.0], [10.0, 10.0, 0.0]]},
    "dimension": {
        "def_point": [1.0, 2.0, 0.0], "text_point": [3.0, 4.0, 0.0],
        "ext1_point": [5.0, 6.0, 0.0], "ext2_point": [7.0, 8.0, 0.0],
        # The flattened contents of the dimension's anonymous geometry block. Present
        # here so the existing projection guards below cover them: anchors that move to
        # paper space while the arrowheads stay in model space would draw a dimension
        # with its value in one place and its arrows in another.
        "render_paths": [[[9.0, 10.0], [11.0, 12.0]]],
        "render_fills": [[[13.0, 14.0], [15.0, 16.0], [17.0, 18.0]]],
    },
    "text": {"insert": [12.0, 13.0, 0.0]},
    "block": {"insert": [14.0, 15.0, 0.0]},
    "tolerance": {"insert": [16.0, 17.0, 0.0]},
    "leader": {"vertices": [[1.0, 1.0, 0.0], [2.0, 2.0, 0.0]]},
    "multileader": {"insert": [3.0, 3.0, 0.0], "vertices": [[4.0, 4.0, 0.0]]},
    "hatch": {"paths": [[[0.0, 0.0], [1.0, 0.0], [0.0, 0.0]]], "boundary_points": [[0.0, 0.0]]},
}


@pytest.mark.parametrize("entity_type", sorted(ENTITY_GEOMETRY_SAMPLES))
def test_every_entity_type_is_projected(entity_type):
    """Regression guard for the five types the old inline projector skipped
    (hatch, tolerance, leader, multileader, block), which left them in model space
    while everything else moved to paper space."""
    import copy

    transform = ViewportTransform("Layout1", [_viewport()])
    original = copy.deepcopy(ENTITY_GEOMETRY_SAMPLES[entity_type])
    mapped = _build_mapped(entity_type, copy.deepcopy(original))

    viewport_index, scale = project_mapped_entity(mapped, transform)

    assert viewport_index != NO_VIEWPORT, f"{entity_type} resolved no viewport"
    assert scale != 1.0, f"{entity_type} was not scaled"
    assert mapped["geometry"] != original, f"{entity_type} geometry was left unprojected"


@pytest.mark.parametrize("entity_type", sorted(ENTITY_GEOMETRY_SAMPLES))
def test_projected_entity_geometry_round_trips(entity_type):
    """The roadmap's Phase 1 acceptance criterion, per entity type:
    unproject(project(p)) == p for every coordinate the entity carries."""
    import copy

    transform = ViewportTransform("Layout1", [_viewport()])
    original = copy.deepcopy(ENTITY_GEOMETRY_SAMPLES[entity_type])
    mapped = _build_mapped(entity_type, copy.deepcopy(original))
    viewport_index, _ = project_mapped_entity(mapped, transform)

    schema = GEOMETRY_SCHEMA[entity_type]
    geometry = mapped["geometry"]

    def check_point(projected, source, label):
        back = transform.unproject(projected[0], projected[1], viewport_index)
        assert math.isclose(back.x, source[0], abs_tol=1e-6), f"{label} x drift"
        assert math.isclose(back.y, source[1], abs_tol=1e-6), f"{label} y drift"

    for key in schema.get("points", ()):
        if key in geometry:
            check_point(geometry[key], original[key], f"{entity_type}.{key}")

    for key in schema.get("point_lists", ()):
        if key in geometry:
            for i, pt in enumerate(geometry[key]):
                check_point(pt, original[key][i], f"{entity_type}.{key}[{i}]")

    for key in schema.get("point_list_groups", ()):
        if key in geometry:
            for g, group in enumerate(geometry[key]):
                for i, pt in enumerate(group):
                    check_point(pt, original[key][g][i], f"{entity_type}.{key}[{g}][{i}]")


def test_entity_is_pinned_to_one_viewport():
    """An entity straddling two viewports must not be torn: every coordinate uses
    the viewport resolved by the first point."""
    vp_a = _viewport(index=0)
    vp_b = Viewport(
        index=1, handle="VP1",
        paper_center_x=900.0, paper_center_y=150.0,
        paper_width=300.0, paper_height=200.0,
        view_anchor_x=5000.0, view_anchor_y=25.0,
        view_height=100.0, scale=2.0,
    )
    transform = ViewportTransform("Layout1", [vp_a, vp_b])

    # Second point sits inside vp_b's model window; it must still use vp_a.
    mapped = _build_mapped("line", {"start": [50.0, 25.0, 0.0], "end": [5000.0, 25.0, 0.0]})
    viewport_index, _ = project_mapped_entity(mapped, transform)

    assert viewport_index == 0
    expected_end = vp_a.to_paper(5000.0, 25.0)
    assert math.isclose(mapped["geometry"]["end"][0], expected_end[0], abs_tol=EPSILON)


def test_lengths_and_sizes_scale_with_the_viewport():
    transform = ViewportTransform("Layout1", [_viewport()])  # scale == 2.0
    mapped = _build_mapped("circle", {"center": [50.0, 25.0, 0.0], "radius": 5.0}, {"radius": 5.0})
    project_mapped_entity(mapped, transform)
    assert math.isclose(mapped["geometry"]["radius"], 10.0, abs_tol=EPSILON)
    # properties.radius is kept in step with geometry.radius -- they were previously
    # two sources of truth, with only the geometry copy scaled.
    assert math.isclose(mapped["properties"]["radius"], 10.0, abs_tol=EPSILON)


# --------------------------------------------------------------------------
# 3. Entity model fidelity
# --------------------------------------------------------------------------

@pytest.fixture
def rich_dxf(tmp_path) -> Path:
    """A DXF exercising the attributes and entity types Phase 1 adds."""
    doc = ezdxf.new("R2018", setup=True)
    msp = doc.modelspace()

    hidden = doc.layers.add("HIDDEN_EDGES")
    hidden.dxf.linetype = "DASHED"
    hidden.dxf.lineweight = 50

    msp.add_line((0, 0), (100, 0), dxfattribs={"layer": "HIDDEN_EDGES", "lineweight": 35})
    msp.add_line((0, 0), (0, 50), dxfattribs={"linetype": "DASHED"})
    msp.add_circle((50, 25), radius=10)
    msp.add_text("HELLO", dxfattribs={"insert": (10, 10), "height": 5.0})

    dim = msp.add_linear_dim(base=(0, 60), p1=(0, 0), p2=(100, 0))
    dim.render()

    hatch = msp.add_hatch(color=2)
    hatch.paths.add_polyline_path([(10, 10), (30, 10), (30, 30), (10, 30)], is_closed=True)

    block = doc.blocks.new(name="TITLEBLOCK")
    block.add_line((0, 0), (20, 0))
    block.add_attdef("DWG_NO", (1, 1), text="")
    insert = msp.add_blockref("TITLEBLOCK", (200, 200))
    insert.add_auto_attribs({"DWG_NO": "ABC-123"})

    path = tmp_path / "rich.dxf"
    doc.saveas(str(path))
    return path


def _parse(dxf_path: Path):
    sandbox = get_storage_root() / "temp" / f"phase1_{dxf_path.stem}.dxf"
    sandbox.write_bytes(dxf_path.read_bytes())
    try:
        return DXFParser().parse_file(sandbox)
    finally:
        if sandbox.exists():
            sandbox.unlink()


def test_lineweight_and_linetype_are_extracted(rich_dxf):
    """geometry_serializer.py has always read these two keys; no mapper ever wrote
    them, so dashes never applied and every stroke was width 1.0."""
    entities, layers, _, _ = _parse(rich_dxf)

    lines = [e for e in entities if e["entity_type"] == "line"]
    assert lines, "no lines extracted"
    for line in lines:
        assert "lineweight" in line["properties"]
        assert "linetype" in line["properties"]
        assert "ltscale" in line["properties"]

    assert any(l["properties"]["lineweight"] == 35 for l in lines), "explicit lineweight lost"
    assert any(l["properties"]["linetype"] == "DASHED" for l in lines), "explicit linetype lost"

    # Layers carry them too, so BYLAYER (-1) entities can resolve a real stroke.
    hidden = next(l for l in layers if l["layer"] == "HIDDEN_EDGES")
    assert hidden["properties"]["lineweight"] == 50
    assert hidden["properties"]["linetype"] == "DASHED"


def test_dimension_carries_extension_line_geometry(rich_dxf):
    entities, _, _, _ = _parse(rich_dxf)
    dims = [e for e in entities if e["entity_type"] == "dimension"]
    assert dims, "no dimension extracted"
    geo = dims[0]["geometry"]
    assert "def_point" in geo and "text_point" in geo
    # The measured feature endpoints -- without these a dimension can only be
    # anchored to a point, never drawn or spatially reasoned about.
    assert "ext1_point" in geo and "ext2_point" in geo
    assert dims[0]["properties"]["dimstyle"], "dimstyle missing"


def test_hatch_boundary_is_a_closed_loop(rich_dxf):
    """The old mapper collected only `edge.start`, capped at 20 points, flattened
    across paths -- and skipped polyline paths entirely, since they expose
    `.vertices` rather than `.edges`."""
    entities, _, _, _ = _parse(rich_dxf)
    hatches = [e for e in entities if e["entity_type"] == "hatch"]
    assert hatches, "no hatch extracted"

    paths = hatches[0]["geometry"]["paths"]
    assert len(paths) == 1
    loop = paths[0]
    assert len(loop) >= 5, "polyline hatch path was not captured"
    assert loop[0] == loop[-1], "hatch boundary was not closed"
    assert hatches[0]["properties"]["path_count"] == 1


def test_text_bbox_is_populated_with_a_recorded_source(rich_dxf):
    entities, _, _, _ = _parse(rich_dxf)
    texts = [e for e in entities if e["entity_type"] == "text" and e["properties"].get("text")]
    assert texts, "no text extracted"
    for t in texts:
        assert t["properties"]["bbox"] is not None, "bbox silently absent"
        assert t["properties"]["bbox_source"] in ("ezdxf", "estimated")


def test_text_bbox_falls_back_to_estimated_metrics():
    """When ezdxf cannot measure the entity, an estimated box beats None -- every
    consumer would otherwise invent its own fallback."""
    box = EntityMapper._estimate_text_bbox([10.0, 20.0], "ABCDE", 5.0, 0.0)
    assert box is not None
    (xmin, ymin), (xmax, ymax) = box
    assert math.isclose(xmin, 10.0) and math.isclose(ymin, 20.0)
    assert xmax > xmin and ymax > ymin
    assert math.isclose(ymax - ymin, 5.0, abs_tol=EPSILON)

    rotated = EntityMapper._estimate_text_bbox([0.0, 0.0], "ABCDE", 5.0, 90.0)
    assert rotated is not None
    # A 90-degree rotation swaps the envelope's aspect.
    assert (rotated[1][1] - rotated[0][1]) > (rotated[1][0] - rotated[0][0])

    assert EntityMapper._estimate_text_bbox([0.0, 0.0], "", 5.0, 0.0) is None


def test_mtext_height_comes_from_char_height(tmp_path):
    """MTEXT has no `height` attribute -- ezdxf *raises* DXFAttributeError for it, so a
    `hasattr` guard silently reports False and every MTEXT took the 2.5 fallback. On a
    real customer drawing with 16 distinct text heights, 246 of 252 MTEXT entities were
    stored as 2.5: text size was effectively not extracted at all."""
    doc = ezdxf.new("R2018", setup=True)
    msp = doc.modelspace()
    for size in (1.75, 5.0, 10.0):
        msp.add_mtext(f"size {size}", dxfattribs={"char_height": size, "insert": (0, size * 10)})
    path = tmp_path / "mtext_heights.dxf"
    doc.saveas(str(path))

    entities, _, _, _ = _parse(path)
    heights = sorted(
        round(e["properties"]["height"], 2)
        for e in entities
        if e["entity_type"] == "text" and e["properties"].get("source_dxftype") == "MTEXT"
    )
    assert heights == [1.75, 5.0, 10.0], f"MTEXT char_height not recovered, got {heights}"


def test_plain_text_height_still_uses_height_attribute(tmp_path):
    doc = ezdxf.new("R2018", setup=True)
    doc.modelspace().add_text("plain", dxfattribs={"insert": (0, 0), "height": 7.5})
    path = tmp_path / "text_height.dxf"
    doc.saveas(str(path))

    entities, _, _, _ = _parse(path)
    text = next(e for e in entities if e["entity_type"] == "text")
    assert text["properties"]["height"] == 7.5


def test_mtext_width_factor_and_tracking_are_captured():
    """\\W (horizontal width factor) and \\T (tracking) are how the file states the
    glyph scaling it wants. `strip_mtext` removes them during cleaning, so they are
    parsed out first -- inferring the same scaling back from the bounding box is the
    wrong way round."""
    width_factor, tracking = EntityMapper._parse_mtext_formatting(r"\A1;\W0.866025;\T0.75;text")
    assert math.isclose(width_factor, 0.866025, abs_tol=1e-6)
    assert math.isclose(tracking, 0.75, abs_tol=1e-6)

    # Absent codes default to 1.0 rather than 0.
    assert EntityMapper._parse_mtext_formatting("plain text") == (1.0, 1.0)
    assert EntityMapper._parse_mtext_formatting("") == (1.0, 1.0)
    # A malformed value must not crash or yield a nonsense zero scale.
    assert EntityMapper._parse_mtext_formatting(r"\Wabc;text") == (1.0, 1.0)


def test_mtext_bbox_is_labelled_as_a_column_box(tmp_path):
    """ezdxf reports the declared MTEXT column box, not the glyph ink extent. Measured
    on a real drawing, 228 of 232 boxes equalled the column width exactly, with natural
    glyph width ranging 0.13x to 3.56x of it. `bbox_source` records the difference so a
    consumer cannot mistake a column box for a text extent and scale strings into it."""
    doc = ezdxf.new("R2018", setup=True)
    doc.modelspace().add_mtext(
        "short", dxfattribs={"char_height": 2.5, "insert": (0, 0), "width": 200.0}
    )
    path = tmp_path / "mtext_column.dxf"
    doc.saveas(str(path))

    entities, _, _, _ = _parse(path)
    text = next(e for e in entities if e["entity_type"] == "text")
    props = text["properties"]

    assert props["bbox_source"] == "mtext_column"
    assert math.isclose(props["column_width"], 200.0, abs_tol=1e-6)
    bbox_width = props["bbox"][1][0] - props["bbox"][0][0]
    assert math.isclose(bbox_width, 200.0, abs_tol=1e-3), "bbox should equal the column width"


def test_exploded_block_children_link_to_their_insert(rich_dxf):
    entities, _, _, _ = _parse(rich_dxf)

    blocks = [e for e in entities if e["entity_type"] == "block"]
    assert blocks, "INSERT container not recorded"
    insert_handle = blocks[0]["properties"]["handle"]
    assert blocks[0]["properties"]["is_container"] is True
    # The INSERT remains the only carrier of ATTRIB values -- virtual_entities()
    # does not yield attached attribs.
    assert blocks[0]["properties"]["attributes"].get("DWG_NO") == "ABC-123"

    children = [e for e in entities if e["properties"].get("parent_handle") == insert_handle]
    assert children, "exploded block content was not linked to its INSERT"


def test_metadata_persists_an_invertible_transform(rich_dxf):
    _, _, _, metadata = _parse(rich_dxf)
    assert metadata["transform_version"] == TRANSFORM_VERSION
    assert "viewport_transform" in metadata
    assert metadata["coordinate_space"] in ("model", "paper")
    # Rehydrating the persisted dict must produce a usable transform.
    restored = ViewportTransform.from_dict(metadata["viewport_transform"])
    fwd = restored.project(10.0, 20.0)
    back = restored.unproject(fwd.x, fwd.y, fwd.viewport_index)
    assert math.isclose(back.x, 10.0, abs_tol=EPSILON)
    assert math.isclose(back.y, 20.0, abs_tol=EPSILON)


def test_entities_record_their_coordinate_space(rich_dxf):
    entities, _, _, _ = _parse(rich_dxf)
    graphic = [e for e in entities if e["entity_type"] != "layer"]
    assert graphic
    for e in graphic:
        assert e["properties"]["space"] in ("model", "paper")
        assert "viewport_index" in e["properties"]


def test_paperspace_viewport_projection_end_to_end(tmp_path):
    """A model-space drawing plotted through a paper-space viewport: geometry must
    land in paper coordinates and be invertible back to what was authored."""
    doc = ezdxf.new("R2018", setup=True)
    msp = doc.modelspace()
    msp.add_line((0, 0), (100, 50))
    layout = doc.layout("Layout1")
    layout.add_viewport(
        center=(200, 150), size=(300, 200),
        view_center_point=(50, 25), view_height=100,
    )
    path = tmp_path / "vp.dxf"
    doc.saveas(str(path))

    entities, _, _, metadata = _parse(path)

    assert metadata["coordinate_space"] == "paper"
    transform = ViewportTransform.from_dict(metadata["viewport_transform"])
    assert not transform.is_identity

    line = next(e for e in entities if e["entity_type"] == "line")
    assert line["properties"]["space"] == "paper"
    index = line["properties"]["viewport_index"]
    assert index != NO_VIEWPORT

    start = transform.unproject(line["geometry"]["start"][0], line["geometry"]["start"][1], index)
    end = transform.unproject(line["geometry"]["end"][0], line["geometry"]["end"][1], index)
    assert math.isclose(start.x, 0.0, abs_tol=1e-6)
    assert math.isclose(start.y, 0.0, abs_tol=1e-6)
    assert math.isclose(end.x, 100.0, abs_tol=1e-6)
    assert math.isclose(end.y, 50.0, abs_tol=1e-6)


# ---------------------------------------------------------------------------
# DIMENSION rendered geometry
#
# A DIMENSION stores anchors, a `measurement` and a `dimstyle` -- nothing drawable.
# The dimension line, extension lines and arrowheads live in an anonymous block.
# Until that block was flattened, switching `renderMode` to 'vector' produced a sheet
# with every dimension silently deleted (measured: VIRTUALIZED 356/518).
# ---------------------------------------------------------------------------


def _rendered_dim(msp, **override):
    opts = {"dimtsz": 0, "dimblk": "", "dimasz": 2.5}
    opts.update(override)
    d = msp.add_linear_dim(base=(0, 12), p1=(0, 0), p2=(100, 0), override=opts)
    d.render()
    return d.dimension


def test_dimension_yields_drawable_line_geometry():
    doc = ezdxf.new()
    mapped = EntityMapper.map_dimension(_rendered_dim(doc.modelspace()))
    paths = mapped["geometry"].get("render_paths")

    assert paths, "dimension produced no drawable geometry -- it would render as nothing"
    # Extension lines + dimension line at minimum.
    assert len(paths) >= 3
    assert all(len(p) >= 2 for p in paths)
    assert all(len(pt) == 2 for p in paths for pt in p)


def test_closed_filled_arrowheads_become_fills_not_strokes():
    """Arrowheads are SOLID entities. Stroking their outline instead of filling them
    draws hollow triangles, which is not what a dimension looks like."""
    doc = ezdxf.new()
    mapped = EntityMapper.map_dimension(_rendered_dim(doc.modelspace()))
    fills = mapped["geometry"].get("render_fills")

    assert fills, "closed-filled arrowheads produced no fill polygons"
    assert all(len(quad) >= 3 for quad in fills)


def test_radial_dimension_tessellates_its_arc():
    doc = ezdxf.new()
    msp = doc.modelspace()
    msp.add_circle((200, 0), radius=40)
    rd = msp.add_radius_dim(
        center=(200, 0), radius=40, angle=45,
        override={"dimtsz": 0, "dimblk": "", "dimasz": 2.5},
    )
    rd.render()

    mapped = EntityMapper.map_dimension(rd.dimension)
    assert mapped["geometry"].get("render_paths"), "radial dimension produced no geometry"


def test_dimension_text_height_is_harvested_from_the_rendered_block():
    """The DIMENSION entity does not carry the resolved text height -- it lives on the
    dimstyle. Without harvesting it the renderer has to guess, and guesses wrong."""
    doc = ezdxf.new()
    mapped = EntityMapper.map_dimension(_rendered_dim(doc.modelspace(), dimtxt=3.5))
    assert mapped["properties"].get("text_height") == pytest.approx(3.5)


def test_every_dimension_geometry_key_is_covered_by_the_projection_schema():
    """Regression guard for the coordinate space, not the drawing.

    `project_mapped_entity` is schema-driven: a geometry key absent from
    GEOMETRY_SCHEMA is silently left in model space while its siblings move to paper
    space. For a dimension that means anchors in one space and arrowheads in another.
    """
    doc = ezdxf.new()
    mapped = EntityMapper.map_dimension(_rendered_dim(doc.modelspace()))

    schema = GEOMETRY_SCHEMA["dimension"]
    covered = {key for group in schema.values() for key in group}
    uncovered = set(mapped["geometry"]) - covered

    assert not uncovered, f"dimension geometry keys not covered by GEOMETRY_SCHEMA: {uncovered}"


def test_real_dimension_geometry_is_projected_into_paper_space():
    """End-to-end companion to the parametrized projection guards above, using geometry
    that ezdxf actually produced rather than a hand-written sample."""
    import copy

    doc = ezdxf.new()
    mapped = EntityMapper.map_dimension(_rendered_dim(doc.modelspace()))
    before = copy.deepcopy(mapped["geometry"]["render_paths"])

    transform = ViewportTransform("Layout1", [_viewport()])
    viewport_index, scale = project_mapped_entity(mapped, transform)

    assert viewport_index != NO_VIEWPORT
    assert scale != 1.0
    assert mapped["geometry"]["render_paths"] != before, (
        "render_paths were left in model space while the anchors moved to paper space"
    )


def test_wrapping_elliptical_arc_sweeps_forward_through_zero():
    """A DXF ellipse always sweeps counter-clockwise start_param -> end_param, so
    `end < start` means it wraps through 2pi rather than running backwards.

    Taking the raw difference swept the short way round and drew the arc on the
    opposite side of its own ellipse. Measured on a real isometric view: 9 of 33 arcs
    wrapped, so the flange rendered as a broken crescent while ezdxf drew closed rings
    from the same entities.
    """
    doc = ezdxf.new()
    msp = doc.modelspace()
    # 180 deg -> 0 deg: the lower half, sweeping through 270.
    ell = msp.add_ellipse(center=(0, 0), major_axis=(10, 0), ratio=0.5,
                          start_param=math.pi, end_param=0.0)

    pts = EntityMapper.map_ellipse(ell)["geometry"]["points"]

    assert len(pts) >= 8
    # Sweeping forward through 270 deg puts the arc BELOW the centre line.
    ys = [p[1] for p in pts]
    assert min(ys) < -1e-6, "wrapped arc was swept backwards, onto the upper half"
    assert max(ys) <= 1e-6, "wrapped arc leaked into the half it does not cover"
    # And it must actually reach the far side rather than stopping short.
    assert pts[0][0] == pytest.approx(-10.0, abs=1e-6)
    assert pts[-1][0] == pytest.approx(10.0, abs=1e-6)


def test_full_ellipse_is_reported_closed_when_params_wrap():
    doc = ezdxf.new()
    msp = doc.modelspace()
    ell = msp.add_ellipse(center=(0, 0), major_axis=(5, 0), ratio=0.5,
                          start_param=0.0, end_param=math.tau)
    assert EntityMapper.map_ellipse(ell)["properties"]["is_closed"] is True


def test_dimension_text_rotation_comes_from_mtext_text_direction():
    """MTEXT keeps its orientation in `text_direction`, not `rotation`.

    Reading `dxf.rotation` off an MTEXT yields None -> 0.0, which drew every rotated
    dimension's value horizontally. On a real sheet that stacked the vertical 145 and
    100 on top of each other. Same family as the documented map_text MTEXT trap.
    """
    doc = ezdxf.new()
    msp = doc.modelspace()
    # A vertical (90 deg) linear dimension: its text runs vertically.
    d = msp.add_linear_dim(base=(12, 0), p1=(0, 0), p2=(0, 100), angle=90,
                           override={"dimtsz": 0, "dimblk": "", "dimasz": 2.5})
    d.render()

    rot = EntityMapper.map_dimension(d.dimension)["properties"].get("text_rotation")
    assert rot is not None
    assert abs(rot) > 1.0, f"vertical dimension text reported rotation {rot} (degraded to 0)"


def test_geometry_outside_every_viewport_window_is_flagged_clipped():
    """`project` falls back to viewport 0 for model points outside every window, so the
    projected coordinate looks perfectly reasonable and cannot itself distinguish
    "visible" from "clipped away".

    A viewport shows only its own window, so such geometry is invisible in CAD and in the
    ezdxf raster. Rendering it put a phantom section label on the sheet in vector mode.
    """
    vp = _viewport()  # model window centred on (50, 25), view_height 100 -> y in [-25, 75]
    transform = ViewportTransform("Layout1", [vp])

    assert transform.covers_model_point(50.0, 25.0) is True
    assert transform.covers_model_point(50.0, 10_000.0) is False

    inside = _build_mapped("text", {"insert": [50.0, 25.0, 0.0]})
    project_mapped_entity(inside, transform)
    assert "outside_viewport" not in inside["properties"]

    outside = _build_mapped("text", {"insert": [50.0, 10_000.0, 0.0]})
    project_mapped_entity(outside, transform)
    assert outside["properties"].get("outside_viewport") is True
    # Still projected, not dropped: the coordinate remains the honest answer and the
    # comparison engines still receive the entity.
    assert outside["geometry"]["insert"] != [50.0, 10_000.0, 0.0]


def test_identity_transform_never_reports_clipping():
    """A drawing with no paper-space viewports has nothing to clip against."""
    t = ViewportTransform()
    assert t.covers_model_point(1e9, -1e9) is True
    mapped = _build_mapped("text", {"insert": [1e9, -1e9, 0.0]})
    project_mapped_entity(mapped, t)
    assert "outside_viewport" not in mapped["properties"]
