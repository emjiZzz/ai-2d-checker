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
