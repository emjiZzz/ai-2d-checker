import pytest
import re
from typing import Any, List, Dict
import services.backend.infrastructure.audit.bom_analyzer as bom_analyzer_mod
from services.backend.infrastructure.audit.bom_analyzer import BOMAnalyzer

class MockEntity:
    def __init__(self, id_val: str, entity_type: str, layer: str = "", properties: Dict[str, Any] = None, geometry: Dict[str, Any] = None):
        self.id = id_val
        self.entity_type = entity_type
        self.layer = layer
        self.properties = properties or {}
        self.geometry = geometry or {}

class MockAuditViolation:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

@pytest.fixture(autouse=True)
def mock_audit_violation(monkeypatch):
    monkeypatch.setattr(bom_analyzer_mod, "AuditViolation", MockAuditViolation)

def test_extract_bom_rows_blocks():
    ent1 = MockEntity(
        id_val="ent1",
        entity_type="block",
        layer="bom",
        properties={"attributes": {"NO": "1", "NAME": "Shaft", "PARTNO": "SH-001", "QTY": "2"}},
        geometry={"insert": [10.0, 20.0]}
    )
    ent2 = MockEntity(
        id_val="ent2",
        entity_type="block",
        layer="bom",
        properties={"attributes": {"NO": "2", "NAME": "Gear", "PARTNO": "GE-002", "QTY": "1"}},
        geometry={"insert": [30.0, 40.0]}
    )
    ent3 = MockEntity(
        id_val="ent3",
        entity_type="block",
        layer="bom",
        properties={"attributes": {"NO": "1", "NAME": "Duplicate Shaft", "PARTNO": "SH-001-D", "QTY": "2"}},
        geometry={"insert": [10.0, 20.0]}
    )
    
    rows = BOMAnalyzer.extract_bom_rows([ent1, ent2, ent3])
    assert len(rows) == 2
    assert rows[0]["item_no"] == 1
    assert rows[0]["part_name"] == "Shaft"
    assert rows[0]["part_number"] == "SH-001"
    assert rows[0]["quantity"] == "2"
    assert rows[0]["position"] == [10.0, 20.0]
    
    assert rows[1]["item_no"] == 2
    assert rows[1]["part_name"] == "Gear"
    assert rows[1]["part_number"] == "GE-002"

def test_extract_bom_rows_texts_fallback():
    ent1 = MockEntity(
        id_val="txt1",
        entity_type="text",
        layer="border",
        properties={"text": "1"},
        geometry={"insert": [50.0, 60.0]}
    )
    ent2 = MockEntity(
        id_val="txt2",
        entity_type="text",
        layer="border",
        properties={"value": "2"},
        geometry={"insert": [70.0, 80.0]}
    )
    
    rows = BOMAnalyzer.extract_bom_rows([ent1, ent2])
    assert len(rows) == 2
    assert rows[0]["item_no"] == 1
    assert rows[0]["part_name"] == "Extracted Text Item"
    assert rows[0]["position"] == [50.0, 60.0]
    assert rows[1]["item_no"] == 2

def test_detect_balloons():
    circle_ent = MockEntity(
        id_val="circle1",
        entity_type="circle",
        layer="balloons",
        geometry={"center": [100.0, 100.0], "radius": 5.0}
    )
    text_ent = MockEntity(
        id_val="text1",
        entity_type="text",
        layer="balloons",
        properties={"text": "5"},
        geometry={"insert": [101.0, 101.0]}
    )
    
    balloons = BOMAnalyzer.detect_balloons([circle_ent, text_ent])
    assert len(balloons) == 1
    assert balloons[0]["item_no"] == 5
    assert balloons[0]["radius"] == 5.0
    assert balloons[0]["center"] == [100.0, 100.0]
    assert balloons[0]["entity_id"] == "circle1"

def test_reconcile():
    bom_rows = [
        {"item_no": 1, "part_name": "Shaft", "part_number": "SH-001", "quantity": "1", "entity_id": "ent1", "position": [10.0, 20.0]},
        {"item_no": 2, "part_name": "Gear", "part_number": "GE-002", "quantity": "2", "entity_id": "ent2", "position": [30.0, 40.0]}
    ]
    balloons = [
        {"item_no": 2, "radius": 5.0, "center": [30.0, 40.0], "entity_id": "c2"},
        {"item_no": 3, "radius": 5.0, "center": [50.0, 60.0], "entity_id": "c3"}
    ]
    
    violations = BOMAnalyzer.reconcile(bom_rows, balloons, "session_123")
    
    assert len(violations) == 2
    
    orphan_violation = next(v for v in violations if v.severity == "critical")
    assert orphan_violation.category == "bom_balloon_mismatch"
    assert "Orphan balloon callout detected" in orphan_violation.description
    assert orphan_violation.affected_entities == [{"id": "c3", "type": "circle"}]
    assert orphan_violation.coordinates == [50.0, 60.0]
    
    unlinked_violation = next(v for v in violations if v.severity == "high")
    assert unlinked_violation.category == "bom_balloon_mismatch"
    assert "Unlinked BOM row: Item definition #1" in unlinked_violation.description
    assert unlinked_violation.affected_entities == [{"id": "ent1", "type": "block"}]
    assert unlinked_violation.coordinates == [10.0, 20.0]

def test_extract_bom_table_empty():
    rows, is_assembly = BOMAnalyzer.extract_bom_table([])
    assert rows == []
    assert is_assembly is False

def test_extract_title_block_simple():
    # Use native fields parsing from block attributes to test simple title block extraction
    ent = MockEntity(
        id_val="b1",
        entity_type="block",
        properties={"attributes": {"DESIGN": "John Doe", "DWG_NO": "DWG-123", "TITLE": "Base Plate"}},
        geometry={"insert": [10.0, 20.0]}
    )
    fields = BOMAnalyzer.extract_title_block([ent])
    assert "DESIGNED" in fields
    assert fields["DESIGNED"]["value"] == "John Doe"
    assert fields["DWG NO"]["value"] == "DWG-123"
    assert fields["TITLE"]["value"] == "Base Plate"

def test_spatial_calculations():
    ent = MockEntity(
        id_val="t1",
        entity_type="text",
        properties={"text": "Test", "height": 3.0},
        geometry={"location": [10.0, 20.0]}
    )
    coords = BOMAnalyzer.find_drawing_text_coordinates([ent], "Test")
    assert coords is not None
    assert coords["coords"] is not None

    bom_bbox = BOMAnalyzer.compute_bom_bbox([ent])
    assert bom_bbox is None

    title_bbox = BOMAnalyzer.compute_title_block_bbox([ent])
    assert title_bbox is None or isinstance(title_bbox, tuple)
