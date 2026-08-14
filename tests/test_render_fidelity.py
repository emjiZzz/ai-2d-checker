"""Extraction-side guards for vector render fidelity.

Each test pins a defect that produced a plausible-looking drawing rather than an error, and
each was found by measuring the canvas against the backend's own ezdxf raster with
`tools/render_audit.py` rather than by looking at it. Counts quoted are from M745221N01.

See `docs/vault/06 - Gotchas & Debugging Lessons/Gotcha - A Blurry CAD Canvas and Its Four
Causes.md`.
"""

from pathlib import Path
from unittest.mock import MagicMock

import ezdxf
import pytest

from services.backend.domain.models.extracted_entity import ExtractedEntity
from services.backend.infrastructure.cad.dxf_parser import DXFParser, resolve_dash_pattern
from services.backend.infrastructure.cad.entity_mapper import EntityMapper
from services.backend.infrastructure.rendering.geometry_serializer import GeometrySerializer
from services.backend.infrastructure.storage.path_resolver import get_storage_root


@pytest.fixture(autouse=True)
def mock_beanie_collections(monkeypatch):
    monkeypatch.setattr(
        ExtractedEntity, "get_pymongo_collection", classmethod(lambda cls: MagicMock())
    )


def _entity(**kwargs) -> ExtractedEntity:
    props = kwargs.pop("properties", {})
    return ExtractedEntity(
        drawing_id="dwg",
        job_id="job",
        entity_type=kwargs.pop("entity_type", "line"),
        layer=kwargs.pop("layer", "0"),
        geometry=kwargs.pop("geometry", {"start": [0, 0], "end": [1, 1]}),
        properties=props,
    )


# ---------------------------------------------------------------------------
# Dimension text: the ⌀ prefix lives in the rendered block, not on the DIMENSION
# ---------------------------------------------------------------------------


def test_dimension_carries_the_block_text_that_holds_the_diameter_prefix():
    """`dimpost` bakes the prefix into the anonymous block, never onto `dimension.dxf.text`.

    On M745221N01 three of the four dimensions read '%%c145' / '%%c100' / '%%c125' inside their
    block while `dxf.text` is a bare '<>', so rebuilding the string from `actual_measurement`
    dropped the ⌀ and the canvas showed "145" where iCAD SX shows "φ145".
    """
    doc = ezdxf.new(setup=True)
    dim = doc.modelspace().add_linear_dim(
        base=(0, 20), p1=(0, 0), p2=(100, 0), override={"dimpost": "%%c<>"}
    )
    dim.render()

    mapped = EntityMapper.map_dimension(dim.dimension)

    assert mapped["properties"]["render_text"].startswith("%%c")
    # The frontend's `cleanCadText` turns %%c into the real symbol; the backend must leave the
    # escape intact because `transcode_value` re-encodes every string as latin-1 afterwards.
    assert "⌀" not in mapped["properties"]["render_text"]


def test_dimension_render_text_does_not_disturb_the_comparison_field():
    """`properties["text"]` must stay byte-identical.

    `context_builder` pools dimensions into the comparison entity set by that field, so
    overwriting it would invalidate every cached audit and force a COMPARISON_CACHE_VERSION
    bump. The prefix rides along in a separate key for exactly that reason.
    """
    doc = ezdxf.new(setup=True)
    dim = doc.modelspace().add_linear_dim(
        base=(0, 20), p1=(0, 0), p2=(100, 0), override={"dimpost": "%%c<>"}
    )
    dim.render()

    mapped = EntityMapper.map_dimension(dim.dimension)

    assert mapped["properties"]["text"] == "<>"
    assert mapped["properties"]["render_text"] != mapped["properties"]["text"]


def test_dimension_recovers_the_width_factor_from_its_block():
    """`\\W` and `\\T` live on the block's MTEXT; the DIMENSION entity never records them."""
    doc = ezdxf.new(setup=True)
    dim = doc.modelspace().add_linear_dim(base=(0, 20), p1=(0, 0), p2=(100, 0))
    dim.render()

    # Mutate the BLOCK DEFINITION, not a virtual entity: `virtual_entities()` yields throwaway
    # copies, so editing those changes nothing the mapper will later see.
    block = doc.blocks.get(dim.dimension.dxf.geometry)
    for child in block:
        if child.dxftype() == "MTEXT":
            child.text = "\\W0.800000;\\T0.875000;100"
            break

    mapped = EntityMapper.map_dimension(dim.dimension)

    assert mapped["properties"]["width_factor"] == pytest.approx(0.8)
    assert mapped["properties"]["tracking"] == pytest.approx(0.875)


def test_dimension_text_anchors_on_the_block_mtext_not_on_text_midpoint():
    """`text_midpoint` sits ON the dimension line; the block's MTEXT is offset off it.

    Anchoring the measurement on `text_midpoint` drew every value straight through its own
    dimension line, so the line looked broken where the glyphs crossed it. Measured on
    M745221N01's revision (model units): the ⌀145 line is at x −105.70 and its MTEXT at
    −110.02, ⌀100 at −93.80 against −98.06, the horizontal `6` at y −439.05 against −434.79 —
    a uniform ~4.3 offset perpendicular to the line.

    Asserted by moving the block's MTEXT rather than by trusting a generated dimension to
    reproduce the offset: ezdxf's renderer *writes* `text_midpoint` to wherever it placed the
    text, so on a doc it authored the two points coincide and no fixture can tell them apart.
    iCAD SX is the one that offsets them, which is the whole reason this went unnoticed.
    """
    doc = ezdxf.new(setup=True)
    dim = doc.modelspace().add_linear_dim(base=(0, 20), p1=(0, 0), p2=(100, 0))
    dim.render()

    block = doc.blocks.get(dim.dimension.dxf.geometry)
    for child in block:
        if child.dxftype() == "MTEXT":
            child.dxf.insert = (child.dxf.insert.x, child.dxf.insert.y + 4.26)
            break

    mapped = EntityMapper.map_dimension(dim.dimension)
    on_line = mapped["geometry"]["text_point"]
    beside = mapped["geometry"]["render_text_point"]

    assert beside[0] == pytest.approx(on_line[0], abs=1e-6)
    assert beside[1] - on_line[1] == pytest.approx(4.26, abs=1e-6)


def test_dimension_without_a_block_mtext_keeps_the_old_anchor():
    """No harvested point means the renderer falls back to `text_point`, as it did before.

    Extraction-time fields do not reach drawings already ingested — there is no re-extract
    endpoint — so the absent case is the common one, not an edge case.
    """
    doc = ezdxf.new(setup=True)
    dim = doc.modelspace().add_linear_dim(base=(0, 20), p1=(0, 0), p2=(100, 0))
    dim.render()

    block = doc.blocks.get(dim.dimension.dxf.geometry)
    for child in list(block):
        if child.dxftype() in ("MTEXT", "TEXT"):
            block.delete_entity(child)

    mapped = EntityMapper.map_dimension(dim.dimension)

    assert "render_text_point" not in mapped["geometry"]
    assert mapped["geometry"]["text_point"] is not None


def test_dimension_text_anchor_lands_in_geometry_so_it_gets_projected():
    """In `properties` it would stay in model coordinates and place the text off the sheet.

    `text_point` is projected through the viewport transform because the dimension schema lists
    it under `points`; `render_text_point` has to be in the same place to get the same treatment.
    """
    doc = ezdxf.new(setup=True)
    dim = doc.modelspace().add_linear_dim(base=(0, 20), p1=(0, 0), p2=(100, 0))
    dim.render()

    mapped = EntityMapper.map_dimension(dim.dimension)

    assert "render_text_point" not in mapped["properties"]

    from services.backend.infrastructure.cad.entity_mapper import GEOMETRY_SCHEMA

    assert "render_text_point" in GEOMETRY_SCHEMA["dimension"]["points"]


def test_dimension_text_anchor_does_not_disturb_the_comparison_anchor():
    """`text_point` must keep reading `text_midpoint`.

    The comparison scopes entities by their points, so moving `text_point` by the text gap
    would shift dimensions between zones and stale every cached audit. Same split as
    `render_text` vs `text`: add a field for the renderer, never repoint the existing one.
    """
    doc = ezdxf.new(setup=True)
    dim = doc.modelspace().add_linear_dim(base=(0, 20), p1=(0, 0), p2=(100, 0))
    dim.render()

    expected = dim.dimension.dxf.text_midpoint
    mapped = EntityMapper.map_dimension(dim.dimension)

    assert mapped["geometry"]["text_point"][0] == pytest.approx(expected.x)
    assert mapped["geometry"]["text_point"][1] == pytest.approx(expected.y)


# ---------------------------------------------------------------------------
# A LEADER's hookline is not in its vertex list
# ---------------------------------------------------------------------------


def _leader(doc, vertices, **attribs):
    return doc.modelspace().add_leader(vertices, dxfattribs=attribs)


def test_leader_extends_its_landing_under_the_annotation_text():
    """A LEADER stores its path plus `has_hookline`/`text_width`, not the landing itself.

    Without extending it the callout's pointer stops in mid-air short of its own label.
    Measured on M745221N01's `6-9キリ`: our chain ended at paper x 125.0 while ezdxf's own
    rendering reached 107.9 — 17.1 units short, the entire landing.
    """
    doc = ezdxf.new(setup=True)
    leader = _leader(doc, [(0, 0), (-10, -10), (-14, -10)])
    leader.dxf.has_hookline = 1
    leader.dxf.text_width = 22.62

    mapped = EntityMapper.map_leader(leader)
    verts = mapped["geometry"]["vertices"]

    assert len(verts) == 4, "the landing segment was not appended"
    # The final segment runs in -x, so the landing continues in -x by exactly text_width.
    assert verts[-1][0] == pytest.approx(-14 - 22.62)
    assert verts[-1][1] == pytest.approx(-10)


def test_a_leader_without_a_hookline_is_left_alone():
    """The spec-default trap: ezdxf reads back `has_hookline=1` and `text_width=1` for a
    LEADER that declares neither, so reading them lengthens every plain leader by a phantom
    unit. This file's two section-callout tails were extended by exactly 1.0 before the
    presence check went in."""
    doc = ezdxf.new(setup=True)
    leader = _leader(doc, [(0, 0), (-10, -10), (-14, -10)])

    assert leader.dxf.has_hookline == 1, "precondition: ezdxf reports the spec default"
    assert not leader.dxf.hasattr("has_hookline"), "precondition: but the file never set it"

    mapped = EntityMapper.map_leader(leader)

    assert len(mapped["geometry"]["vertices"]) == 3
    assert mapped["properties"]["has_hookline"] is False


def test_dxf_is_set_separates_a_written_attribute_from_a_spec_default():
    """`_dxf_get` answers 'what is the effective value'; `_dxf_is_set` answers 'did the file
    say this'. The two disagree exactly where branching on presence matters."""
    from services.backend.infrastructure.cad.entity_mapper import _dxf_get, _dxf_is_set

    doc = ezdxf.new(setup=True)
    leader = _leader(doc, [(0, 0), (-10, -10), (-14, -10)])

    assert _dxf_get(leader.dxf, "has_hookline", 0) == 1     # readable...
    assert _dxf_is_set(leader.dxf, "has_hookline") is False  # ...but not written

    leader.dxf.has_hookline = 1
    assert _dxf_is_set(leader.dxf, "has_hookline") is True


def test_leader_landing_uses_the_annotation_width_not_the_declared_text_width():
    """`text_width` under-states the annotation it belongs to.

    On M745221N01's revision the leader declares 22.62 while the MTEXT it points from is 28.56
    wide — 5.94 short, which leaves the landing ending *inside* the text instead of spanning it.
    `annotation_handle` is a hard reference to that MTEXT, so the real width is one lookup away.
    """
    doc = ezdxf.new(setup=True)
    mtext = doc.modelspace().add_mtext("6-9キリ")
    mtext.dxf.width = 28.56
    leader = _leader(doc, [(0, 0), (-10, -10), (-14, -10)])
    leader.dxf.has_hookline = 1
    leader.dxf.text_width = 22.62
    leader.dxf.annotation_handle = mtext.dxf.handle

    verts = EntityMapper.map_leader(leader)["geometry"]["vertices"]

    assert verts[-1][0] == pytest.approx(-14 - 28.56), "the landing used the leader's short width"


def test_leader_falls_back_to_text_width_when_no_annotation_is_linked():
    """A leader naming no annotation still gets a landing — just the declared one."""
    doc = ezdxf.new(setup=True)
    leader = _leader(doc, [(0, 0), (-10, -10), (-14, -10)])
    leader.dxf.has_hookline = 1
    leader.dxf.text_width = 22.62

    verts = EntityMapper.map_leader(leader)["geometry"]["vertices"]

    assert verts[-1][0] == pytest.approx(-14 - 22.62)


def test_leader_annotation_that_is_not_mtext_is_ignored():
    """`annotation_type` also allows a block or a tolerance; only MTEXT carries a usable width."""
    doc = ezdxf.new(setup=True)
    msp = doc.modelspace()
    other = msp.add_line((0, 0), (1, 1))
    leader = _leader(doc, [(0, 0), (-10, -10), (-14, -10)])
    leader.dxf.has_hookline = 1
    leader.dxf.text_width = 22.62
    leader.dxf.annotation_handle = other.dxf.handle

    verts = EntityMapper.map_leader(leader)["geometry"]["vertices"]

    assert verts[-1][0] == pytest.approx(-14 - 22.62)


def test_leader_carries_the_arrow_size_from_its_dimstyle():
    """A LEADER has no arrowhead geometry; the size lives on the DIMSTYLE it names, as DIMASZ.

    Without it the pointer is a bare line that stops at the feature and reads as a leader that
    never arrives — ezdxf records two extra primitives at the tip that we drew none of.
    """
    doc = ezdxf.new(setup=True)
    doc.dimstyles.get("Standard").dxf.dimasz = 4.0
    leader = _leader(doc, [(0, 0), (-10, -10)])
    # Assigned after construction: `add_leader` forces `dimstyle='EZDXF'` and silently discards
    # a dimstyle passed through `dxfattribs`.
    leader.dxf.dimstyle = "Standard"

    props = EntityMapper.map_leader(leader)["properties"]

    assert props["arrow_size"] == pytest.approx(4.0), "read from the wrong dimstyle"
    assert props["has_arrowhead"] == 1


def test_leader_arrow_size_falls_back_to_the_dxf_default():
    """A leader naming a dimstyle the file never defines still gets an arrow."""
    doc = ezdxf.new(setup=True)
    leader = _leader(doc, [(0, 0), (-10, -10)])
    leader.dxf.dimstyle = "NoSuchStyle"

    assert EntityMapper.map_leader(leader)["properties"]["arrow_size"] == pytest.approx(2.5)


def test_arrow_size_is_scaled_with_the_viewport():
    """`arrow_size` is a length, so a leader inside a scaled viewport gets a scaled arrow.

    Measured on M745221N01: the reference's leader is paper-space and keeps DIMASZ 2.5, while
    the revision's runs through a 0.7143 viewport and resolves to 1.786.
    """
    from services.backend.infrastructure.cad.entity_mapper import SCALED_PROPERTY_KEYS

    assert "arrow_size" in SCALED_PROPERTY_KEYS


def test_leader_vertex_zero_is_the_arrow_tip():
    """DXF orders leader vertices FROM the arrow, so the head points along vertex 1 -> 0.

    Pinned because the chain reads naturally as text-to-feature, which is backwards, and an
    arrow drawn on the wrong end lands in the middle of the annotation.
    """
    doc = ezdxf.new(setup=True)
    leader = _leader(doc, [(100, 100), (80, 80), (70, 80)])

    verts = EntityMapper.map_leader(leader)["geometry"]["vertices"]

    assert verts[0][0] == pytest.approx(100) and verts[0][1] == pytest.approx(100)


def test_leader_landing_follows_the_final_segment_direction():
    """The landing continues the last segment, whatever its angle — not always horizontal."""
    doc = ezdxf.new(setup=True)
    leader = _leader(doc, [(0, 0), (30, 40)])   # final segment is a 3-4-5 diagonal
    leader.dxf.has_hookline = 1
    leader.dxf.text_width = 10.0

    verts = EntityMapper.map_leader(leader)["geometry"]["vertices"]

    assert verts[-1][0] == pytest.approx(30 + 6.0)   # 10 * 3/5
    assert verts[-1][1] == pytest.approx(40 + 8.0)   # 10 * 4/5


# ---------------------------------------------------------------------------
# MTEXT rotation lives in text_direction, not in dxf.rotation
# ---------------------------------------------------------------------------


def test_mtext_rotation_comes_from_the_text_direction_vector():
    """`dxf.rotation` reads 0.0 for an MTEXT that is actually vertical.

    Same wrong-but-plausible degradation as the documented `char_height` trap. Two strings on
    M745221N01 (the vertical "Standard" and "Job No." tolerance-table headers) drew horizontally
    and ran across the neighbouring cells.
    """
    doc = ezdxf.new(setup=True)
    mtext = doc.modelspace().add_mtext("Standard")
    mtext.dxf.insert = (0, 0)
    mtext.dxf.text_direction = (0, 1, 0)

    assert mtext.dxf.rotation == 0  # the trap
    assert EntityMapper.map_text(mtext)["properties"]["rotation"] == pytest.approx(90.0)


def test_plain_text_rotation_still_reads_the_scalar_attribute():
    """TEXT has no `text_direction`; the fix must not break the ordinary path."""
    doc = ezdxf.new(setup=True)
    text = doc.modelspace().add_text("PLAIN")
    text.dxf.rotation = 30.0

    assert EntityMapper.map_text(text)["properties"]["rotation"] == pytest.approx(30.0)


# ---------------------------------------------------------------------------
# Linetype patterns
# ---------------------------------------------------------------------------

#: The real CENTER elements from M745221N01: long dash, gap, short dash, gap.
CENTER_ELEMENTS = [31.75, -6.35, 6.35, -6.35]
PATTERNS = {"CENTER": CENTER_ELEMENTS, "HIDDEN": [6.35, -3.175], "DOT": [0.0, -6.35]}
LAYER_LINETYPES = {"0": "Continuous", "CENTRELINES": "CENTER"}


def test_center_expands_to_its_real_dash_dot_pattern():
    """The old serializer emitted a flat [5, 5] for anything whose NAME looked dashed.

    CENTER is long-dash / gap / short-dash / gap; HIDDEN is even dashes. Rendering them
    identically is a semantic error on a mechanical drawing, not a cosmetic one.
    """
    dashes = resolve_dash_pattern("CENTER", "0", 1.0, PATTERNS, LAYER_LINETYPES, 1.0)

    assert dashes == [31.75, 6.35, 6.35, 6.35]
    assert dashes != resolve_dash_pattern("HIDDEN", "0", 1.0, PATTERNS, LAYER_LINETYPES, 1.0)


def test_dash_lengths_are_scaled_by_ltscale_and_the_entity_scale():
    """$LTSCALE on this drawing is 0.2315, which is the difference between a centre line and a
    solid-looking smear of 32-unit dashes."""
    dashes = resolve_dash_pattern("CENTER", "0", 2.0, PATTERNS, LAYER_LINETYPES, 0.5)

    assert dashes[0] == pytest.approx(31.75 * 0.5 * 2.0)


def test_bylayer_resolves_the_linetype_through_the_layer_table():
    assert resolve_dash_pattern(
        "BYLAYER", "CENTRELINES", 1.0, PATTERNS, LAYER_LINETYPES, 1.0
    ) == [31.75, 6.35, 6.35, 6.35]


@pytest.mark.parametrize("name", ["Continuous", "BYBLOCK", "", "NOT_IN_TABLE"])
def test_solid_linetypes_produce_no_dash(name):
    assert resolve_dash_pattern(name, "0", 1.0, PATTERNS, LAYER_LINETYPES, 1.0) is None


def test_a_dot_gets_a_drawable_length():
    """A DXF dot is a zero-length dash, and canvas `setLineDash` draws nothing for a 0."""
    dashes = resolve_dash_pattern("DOT", "0", 1.0, PATTERNS, LAYER_LINETYPES, 1.0)

    assert dashes is not None
    assert dashes[0] > 0


def test_an_odd_length_pattern_is_doubled_so_the_phase_stays_stable():
    """Canvas repeats an odd-length array with on/off swapped, inverting alternate cycles."""
    dashes = resolve_dash_pattern(
        "TRI", "0", 1.0, {"TRI": [3.0, -1.0, 1.0]}, LAYER_LINETYPES, 1.0
    )

    assert dashes == [3.0, 1.0, 1.0, 3.0, 1.0, 1.0]


# ---------------------------------------------------------------------------
# $LWDISPLAY — whether the drawing wants its lineweights drawn at all
# ---------------------------------------------------------------------------


def _parse_in_sandbox(doc, name: str):
    """`DXFParser` refuses paths outside the storage root, so round-trip through it."""
    sandbox = get_storage_root() / "temp" / f"fidelity_{name}.dxf"
    sandbox.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(str(sandbox))
    try:
        return DXFParser().parse_file(Path(sandbox))
    finally:
        if sandbox.exists():
            sandbox.unlink()


@pytest.mark.parametrize("header_value, expected", [(1, True), (0, False)])
def test_lineweight_display_is_extracted_from_the_header(header_value, expected):
    """An entity can record 1.00mm and still be meant to draw as a hairline.

    $LWDISPLAY is 0 on both M745221N01 files, which is why iCAD SX shows uniform thin linework
    on a sheet carrying 1.00mm on 136 entities and 0.50mm on 331. Honouring the recorded weight
    regardless turned the whole template into slabs -- and it was invisible on the REFERENCE
    drawing next to it, which is a uniform 0.25mm.
    """
    doc = ezdxf.new(setup=True)
    doc.header["$LWDISPLAY"] = header_value
    doc.modelspace().add_line((0, 0), (10, 0), dxfattribs={"lineweight": 100})

    _, _, _, metadata = _parse_in_sandbox(doc, f"lwdisplay_{header_value}")

    assert metadata["lineweight_display"] is expected


def test_lineweight_display_defaults_to_off_when_the_header_is_absent():
    """The DXF default is 0, and off is the safe direction: too-thin reads as the old
    behaviour, too-thick reads as broken."""
    doc = ezdxf.new(setup=True)
    del doc.header["$LWDISPLAY"]
    doc.modelspace().add_line((0, 0), (10, 0), dxfattribs={"lineweight": 100})

    _, _, _, metadata = _parse_in_sandbox(doc, "lwdisplay_absent")

    assert "$LWDISPLAY" not in doc.header
    assert metadata["lineweight_display"] is False


# ---------------------------------------------------------------------------
# Serializer: millimetres, sentinels, and the unit space that travels with a dash
# ---------------------------------------------------------------------------


def test_lineweight_is_emitted_in_millimetres():
    payload = GeometrySerializer.serialize_entities(
        [_entity(properties={"color": 7, "lineweight": 100})]
    )

    assert payload["layers"]["0"][0]["style"]["strokeWidth"] == pytest.approx(1.0)


def test_bylayer_lineweight_resolves_against_the_layer_record():
    """-1 is a sentinel, not a width.

    Flattening it to 1.0 and dividing by 100 gave every inheriting entity 0.01mm -- below the
    hairline floor at any zoom, i.e. the thinnest line the canvas can draw. Same class of defect
    as the ACI 256 case this serializer already documents.
    """
    layer_record = _entity(
        entity_type="layer", layer="THICK", geometry={},
        properties={"color": 7, "lineweight": 50},
    )
    line = _entity(layer="THICK", properties={"color": 7, "lineweight": -1})

    payload = GeometrySerializer.serialize_entities([layer_record, line])
    widths = [e["style"]["strokeWidth"] for e in payload["layers"]["THICK"] if e["type"] == "line"]

    assert widths == [pytest.approx(0.5)]


def test_an_unresolvable_lineweight_falls_back_to_the_dxf_default():
    payload = GeometrySerializer.serialize_entities(
        [_entity(properties={"color": 7, "lineweight": -3})]
    )

    assert payload["layers"]["0"][0]["style"]["strokeWidth"] == pytest.approx(0.25)


def test_a_resolved_pattern_is_emitted_in_world_units():
    payload = GeometrySerializer.serialize_entities(
        [_entity(properties={"color": 7, "lineweight": 25,
                             "linetype": "CENTER", "linetype_pattern": [7.35, 1.47, 1.47, 1.47]})]
    )
    style = payload["layers"]["0"][0]["style"]

    assert style["dash"] == [7.35, 1.47, 1.47, 1.47]
    assert style["dashUnits"] == "world"


def test_a_payload_without_a_pattern_keeps_the_legacy_screen_space_fallback():
    """Drawings ingested before the LTYPE table was read must not silently go solid."""
    payload = GeometrySerializer.serialize_entities(
        [_entity(properties={"color": 7, "lineweight": 25, "linetype": "CENTERX2"})]
    )
    style = payload["layers"]["0"][0]["style"]

    assert style["dash"] == [5, 5]
    assert style["dashUnits"] == "screen"


def test_a_continuous_entity_has_no_dash_and_no_unit_space():
    payload = GeometrySerializer.serialize_entities(
        [_entity(properties={"color": 7, "lineweight": 25, "linetype": "Continuous"})]
    )
    style = payload["layers"]["0"][0]["style"]

    assert style["dash"] is None
    assert style["dashUnits"] is None
