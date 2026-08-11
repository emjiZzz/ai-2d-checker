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
