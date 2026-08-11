import pytest
import os
import json
from pathlib import Path
from unittest.mock import MagicMock

# Target Domain Services
from services.backend.infrastructure.rendering.geometry_serializer import GeometrySerializer
from services.backend.infrastructure.rendering.viewport_generator import ViewportGenerator
from services.backend.infrastructure.rendering.overlay_builder import OverlayBuilder
from services.backend.infrastructure.rendering.comparison_engine import ComparisonEngine
from services.backend.infrastructure.rendering.render_cache import RenderCache

# Target Beanie Models
from services.backend.domain.models.extracted_entity import ExtractedEntity
from services.backend.domain.models.audit_violation import AuditViolation

@pytest.fixture(autouse=True)
def mock_beanie_collections(monkeypatch):
    monkeypatch.setattr(ExtractedEntity, "get_pymongo_collection", classmethod(lambda cls: MagicMock()))
    monkeypatch.setattr(AuditViolation, "get_pymongo_collection", classmethod(lambda cls: MagicMock()))

def create_mock_entity(id_val: str, layer: str, type_val: str, geo: dict) -> ExtractedEntity:
    ent = ExtractedEntity(
        drawing_id="dwg_123",
        job_id="job_1",
        entity_type=type_val,
        layer=layer,
        geometry=geo,
        properties={"color": 1, "lineweight": 25} # Red, 0.25mm
    )
    ent.id = id_val
    return ent

def test_geometry_serialization():
    """
    Verify entities are normalized, grouped by layer, and colors are hex-mapped.
    """
    ent1 = create_mock_entity("e1", "0", "line", {"start": [0,0], "end": [10,10]})
    ent2 = create_mock_entity("e2", "AM_DIM", "dimension", {"start": [5,5], "end": [15,15]})
    
    payload = GeometrySerializer.serialize_entities([ent1, ent2])
    
    assert "layers" in payload
    assert "0" in payload["layers"]
    assert "AM_DIM" in payload["layers"]
    
    # Check color mapping (color index 1 -> #FF0000)
    assert payload["layers"]["0"][0]["style"]["stroke"] == "#FF0000"


def _entity(layer: str, entity_type: str = "line", **props) -> ExtractedEntity:
    ent = ExtractedEntity(
        drawing_id="dwg_123",
        job_id="job_1",
        entity_type=entity_type,
        layer=layer,
        geometry={"start": [0, 0], "end": [1, 1]},
        properties=props,
    )
    ent.id = f"e_{layer}_{entity_type}_{len(props)}"
    return ent


def test_bylayer_resolves_against_the_layer_colour():
    """ACI 256 is BYLAYER -- an instruction to look at the layer, not a colour.

    Mapping it straight to white flattened the overwhelming majority of a real drawing,
    since almost everything is BYLAYER. Invisible while the raster path was hiding the
    vector renderer.
    """
    layer_rec = _entity("OUTLINE", entity_type="layer", color=2)  # yellow
    line = _entity("OUTLINE", color=256)

    payload = GeometrySerializer.serialize_entities([layer_rec, line])
    strokes = {e["type"]: e["style"]["stroke"] for e in payload["layers"]["OUTLINE"]}

    assert strokes["line"] == "#FFFF00"


def test_byblock_and_unknown_layer_fall_back_without_crashing():
    payload = GeometrySerializer.serialize_entities([_entity("NO_LAYER_RECORD", color=0)])
    # No layer record, and no recoverable parent, so this falls through to ACI 7 -- white on
    # a dark canvas. This is the orphan case; the inheritance case is below.
    assert payload["layers"]["NO_LAYER_RECORD"][0]["style"]["stroke"] == "#FFFFFF"


def test_byblock_inherits_from_the_insert_not_the_layer():
    """BYBLOCK means "take the colour of the INSERT that placed me", not the layer's.

    Regression for the surface-finish symbol on M745221N01_FSRS2_KMTI. It is the drawing's
    ONLY BYBLOCK entity: a polyline on layer `0` (layer colour ACI 7, white) inside an INSERT
    with ACI 1. Resolving BYBLOCK against the layer -- documented at the time as a deliberate
    shortcut because "a block's contents are usually BYLAYER anyway" -- painted a symbol the
    drawing specifies as RED in white, on the one entity that exercised the sentinel.
    """
    layer_rec = _entity("0", entity_type="layer", color=7)
    insert = _entity("0", entity_type="block", color=1, handle="2AF")
    child = _entity("0", entity_type="polyline", color=0, parent_handle="2AF")

    payload = GeometrySerializer.serialize_entities([layer_rec, insert, child])
    strokes = {e["type"]: e["style"]["stroke"] for e in payload["layers"]["0"]}

    assert strokes["polyline"] == "#FF0000", "BYBLOCK child must take the INSERT's red"
    assert strokes["layer"] == "#FFFFFF", "the layer record itself is unaffected"


def test_byblock_whose_insert_is_bylayer_uses_the_inserts_layer():
    """An INSERT can itself defer. The child then follows the INSERT's layer, not its own."""
    child_layer = _entity("0", entity_type="layer", color=7)
    insert_layer = _entity("SYMBOLS", entity_type="layer", color=3)
    insert = _entity("SYMBOLS", entity_type="block", color=256, handle="B1")
    child = _entity("0", entity_type="polyline", color=0, parent_handle="B1")

    payload = GeometrySerializer.serialize_entities([child_layer, insert_layer, insert, child])
    stroke = next(e for e in payload["layers"]["0"] if e["type"] == "polyline")["style"]["stroke"]
    assert stroke == "#00FF00", "ACI 3 from the INSERT's layer, not ACI 7 from the child's"


def test_nested_byblock_climbs_to_the_first_real_colour():
    outer = _entity("0", entity_type="block", color=5, handle="OUTER")
    inner = _entity("0", entity_type="block", color=0, handle="INNER", parent_handle="OUTER")
    child = _entity("0", entity_type="polyline", color=0, parent_handle="INNER")

    payload = GeometrySerializer.serialize_entities([outer, inner, child])
    stroke = next(e for e in payload["layers"]["0"] if e["type"] == "polyline")["style"]["stroke"]
    assert stroke == GeometrySerializer._aci_to_hex(5)


def test_a_byblock_parent_cycle_terminates_instead_of_hanging():
    """A malformed file must not hang a render. Depth-capped rather than cycle-tracked."""
    a = _entity("0", entity_type="block", color=0, handle="A", parent_handle="B")
    b = _entity("0", entity_type="block", color=0, handle="B", parent_handle="A")
    child = _entity("0", entity_type="polyline", color=0, parent_handle="A")

    payload = GeometrySerializer.serialize_entities([a, b, child])
    stroke = next(e for e in payload["layers"]["0"] if e["type"] == "polyline")["style"]["stroke"]
    assert stroke == "#FFFFFF"  # gave up, fell back to the layer default


def test_true_color_outranks_the_aci_index():
    payload = GeometrySerializer.serialize_entities([_entity("0", color=1, true_color=0x33AA77)])
    assert payload["layers"]["0"][0]["style"]["stroke"] == "#33AA77"


def test_near_black_is_lifted_to_white_for_the_dark_canvas():
    """ACI 250 is black-on-paper; drawn literally it is invisible on this canvas.

    The raster path got this from ezdxf's ColorPolicy.COLOR_SWAP_BW. The vector path has
    to do it itself.
    """
    payload = GeometrySerializer.serialize_entities([_entity("0", color=250)])
    assert payload["layers"]["0"][0]["style"]["stroke"] == "#FFFFFF"


def test_small_lineweights_are_scaled_not_passed_through():
    """Regression: `lineweight / 100 if lineweight > 10 else lineweight`.

    9 is a valid DXF lineweight meaning 0.09mm. The old guard passed it through unscaled,
    so it reached the renderer as a 9px slab among 0.25px hairlines.
    """
    payload = GeometrySerializer.serialize_entities([_entity("0", color=1, lineweight=9)])
    assert payload["layers"]["0"][0]["style"]["strokeWidth"] == 0.09


def test_decorated_linetype_names_still_render_dashed():
    """Real DXF linetype names are decorated (HIDDEN2, CENTERX2), so equality against a
    two-item list matched almost nothing and centre lines rendered solid."""
    payload = GeometrySerializer.serialize_entities([
        _entity("0", color=1, linetype="CENTERX2"),
        _entity("0", color=1, linetype="HIDDEN2"),
        _entity("0", color=1, linetype="Continuous"),
        _entity("0", color=1, linetype="BYLAYER"),
    ])
    dashes = [e["style"]["dash"] for e in payload["layers"]["0"]]
    assert dashes == [[5, 5], [5, 5], None, None]


def test_viewport_bounds_calculation():
    """
    Verify accurate global bounding box derivation with padding.
    """
    ent1 = create_mock_entity("e1", "0", "line", {"start": [0,0], "end": [100,100]})
    ent2 = create_mock_entity("e2", "0", "line", {"start": [-50,20], "end": [20,150]})
    
    bounds = ViewportGenerator.calculate_bounds([ent1, ent2])
    
    # Actual geometric bounds: x=[-50, 100], y=[0, 150]
    # Padding: 5% of width (150) = 7.5, 5% of height (150) = 7.5
    assert bounds["min_x"] == -57.5
    assert bounds["max_x"] == 107.5
    assert bounds["min_y"] == -7.5
    assert bounds["max_y"] == 157.5
    assert bounds["center_x"] == 25.0

def test_violation_overlay_generation():
    """
    Verify audit violations map to semantic color overlays with transparency.
    """
    v1 = AuditViolation(
        audit_session_id="s1",
        severity="critical",
        category="missing_dimension",
        description="test",
        recommendation="test",
        source="rule_engine",
        coordinates=[[10, 10], [50, 50]]
    )
    v1.id = "v_999"
    
    overlays = OverlayBuilder.build_violation_overlays([v1])
    assert len(overlays) == 1
    assert overlays[0]["severity"] == "critical"
    assert overlays[0]["color"] == "#FF0000" # critical -> red
    assert overlays[0]["opacity"] == 0.5
    
def test_drawing_comparison_engine():
    """
    Verify detection of added and removed primitives between drawing versions.
    """
    base_line = create_mock_entity("e1", "0", "line", {"start": [0,0], "end": [10,10]})
    removed_line = create_mock_entity("e2", "0", "line", {"start": [20,20], "end": [30,30]})
    
    new_line = create_mock_entity("e3", "0", "line", {"start": [0,0], "end": [10,10]}) # Match base
    added_circle = create_mock_entity("e4", "0", "circle", {"center": [50,50], "radius": 5})
    
    base_set = [base_line, removed_line]
    new_set = [new_line, added_circle]
    
    diff = ComparisonEngine.compare_drawings(base_set, new_set)
    
    assert len(diff["added"]) == 1
    assert diff["added"][0].entity_type == "circle"
    
    assert len(diff["removed"]) == 1
    assert diff["removed"][0].id == "e2"
    
    assert diff["unmodified_count"] == 1

def test_render_cache_pipeline(tmp_path, monkeypatch):
    """
    Verify caching mechanism safely writes and reads serialized geometry payloads.
    """
    # Mock settings to use tmp_path
    class MockSettings:
        STORAGE_ROOT = str(tmp_path)
    monkeypatch.setattr("services.backend.config.settings", MockSettings())
    
    payload = {"layers": {"0": [{"id": "abc"}]}}
    RenderCache.set_cached_payload("dwg_test", payload)
    
    fetched = RenderCache.get_cached_payload("dwg_test")
    assert fetched is not None
    assert fetched["layers"]["0"][0]["id"] == "abc"
    
    RenderCache.invalidate("dwg_test")
    assert RenderCache.get_cached_payload("dwg_test") is None


def test_dimension_text_colour_is_exposed_separately_from_the_line_colour():
    """A dimension's lines and its measurement text routinely differ: on the reference
    corpus every DIMENSION is ACI 3 (green) while its MTEXT is ACI 2 (yellow).

    Falling back to `stroke` for the text painted every measurement green.
    """
    payload = GeometrySerializer.serialize_entities([
        _entity("DIMS", entity_type="dimension", color=3, text_color_index=2)
    ])
    style = payload["layers"]["DIMS"][0]["style"]
    assert style["stroke"] == "#00FF00"
    assert style["textStroke"] == "#FFFF00"


def test_dimension_text_colour_resolves_bylayer_like_any_other_stroke():
    payload = GeometrySerializer.serialize_entities([
        _entity("DIMS", entity_type="layer", color=2),
        _entity("DIMS", entity_type="dimension", color=3, text_color_index=256),
    ])
    dim = [e for e in payload["layers"]["DIMS"] if e["type"] == "dimension"][0]
    assert dim["style"]["textStroke"] == "#FFFF00"


def test_entities_without_dimension_text_colour_get_no_textstroke():
    payload = GeometrySerializer.serialize_entities([_entity("0", color=1)])
    assert "textStroke" not in payload["layers"]["0"][0]["style"]
