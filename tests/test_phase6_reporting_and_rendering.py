import pytest
import math
from unittest.mock import MagicMock

from services.backend.infrastructure.rendering.block_exploder import BlockExploder
from services.backend.infrastructure.reporting.report_builder import ReportBuilder
from services.backend.domain.models.extracted_entity import ExtractedEntity
from services.backend.domain.models.audit_violation import AuditViolation

@pytest.fixture(autouse=True)
def mock_beanie_collections(monkeypatch):
    monkeypatch.setattr(ExtractedEntity, "get_pymongo_collection", classmethod(lambda cls: MagicMock()))
    monkeypatch.setattr(AuditViolation, "get_pymongo_collection", classmethod(lambda cls: MagicMock()))

def create_mock_entity(id_val: str, type_val: str, geo: dict, block_name: str = None) -> ExtractedEntity:
    props = {}
    if block_name:
        props["block_name"] = block_name
        
    ent = ExtractedEntity(
        drawing_id="dwg_123",
        job_id="job_1",
        entity_type=type_val,
        layer="0",
        geometry=geo,
        properties=props
    )
    ent.id = id_val
    return ent

def test_block_explosion_translation_and_scale():
    """
    Verify INSERT entities properly apply scale and translation to nested primitives.
    """
    base_line = create_mock_entity("base_1", "line", {"start": [0,0], "end": [10,10]})
    block_defs = {"DOOR_BLOCK": [base_line]}
    
    # Insert block at [50, 50] with scale 2.0
    insert_ent = create_mock_entity("ins_1", "insert", {
        "insert": [50.0, 50.0],
        "scale_x": 2.0,
        "scale_y": 2.0,
        "rotation": 0.0
    }, block_name="DOOR_BLOCK")
    
    exploded = BlockExploder.explode_insert(insert_ent, block_defs)
    
    assert len(exploded) == 1
    geo = exploded[0].geometry
    
    # Expected Start: (0*2)+50 = 50, (0*2)+50 = 50
    assert geo["start"] == [50.0, 50.0]
    # Expected End: (10*2)+50 = 70, (10*2)+50 = 70
    assert geo["end"] == [70.0, 70.0]

def test_block_explosion_rotation():
    """
    Verify INSERT entities properly apply rotation matrices.
    """
    base_line = create_mock_entity("base_1", "line", {"start": [10, 0], "end": [20, 0]})
    block_defs = {"ROT_BLOCK": [base_line]}
    
    # Insert block rotated 90 degrees
    insert_ent = create_mock_entity("ins_1", "insert", {
        "insert": [0.0, 0.0],
        "scale_x": 1.0,
        "scale_y": 1.0,
        "rotation": 90.0
    }, block_name="ROT_BLOCK")
    
    exploded = BlockExploder.explode_insert(insert_ent, block_defs)
    geo = exploded[0].geometry
    
    # Expected Start: [0, 10]
    assert math.isclose(geo["start"][0], 0.0, abs_tol=1e-9)
    assert math.isclose(geo["start"][1], 10.0, abs_tol=1e-9)
    
def test_report_builder_schema():
    """
    Verify report builder orchestrates the correct JSON schema for PDF exports.
    """
    class MockDoc:
        def __init__(self, _id):
            self.id = _id
            
    v1 = MockDoc("viol_1")
    a1 = MockDoc("ann_1")
    
    schema = ReportBuilder.build_report_schema("sess_123", [v1], [a1])
    
    assert schema["session_id"] == "sess_123"
    assert len(schema["violations"]) == 1
    assert schema["violations"][0]["id"] == "viol_1"
    assert len(schema["annotations"]) == 1
