import pytest
import os
import uuid
import json
from unittest.mock import MagicMock, patch
from services.backend.domain.models.drawing_document import DrawingDocument
from services.backend.domain.models.extracted_entity import ExtractedEntity
from services.backend.domain.models.audit_session import AuditSession
from services.backend.domain.models.audit_violation import AuditViolation
from services.backend.domain.models.client import ClientDocument
from services.backend.domain.models.standard_document import StandardDocument
from services.backend.domain.models.standard_chunk import StandardChunk
from services.backend.api.schemas import PhysicalComparisonRequest, PhysicalComparisonResponse
from services.backend.api.routers.audits import perform_physical_comparison
from services.backend.infrastructure.audit.comparison.hallucination_guardrails import (
    is_title_block_category,
    is_bom_category,
    is_admin_bom_marking,
)

# Reuse the Beanie mock fixture pattern
@pytest.fixture(autouse=True)
def mock_beanie_docs(monkeypatch):
    monkeypatch.setattr(DrawingDocument, "get_pymongo_collection", classmethod(lambda cls: MagicMock()))
    monkeypatch.setattr(ExtractedEntity, "get_pymongo_collection", classmethod(lambda cls: MagicMock()))
    monkeypatch.setattr(AuditSession, "get_pymongo_collection", classmethod(lambda cls: MagicMock()))
    monkeypatch.setattr(AuditViolation, "get_pymongo_collection", classmethod(lambda cls: MagicMock()))
    monkeypatch.setattr(ClientDocument, "get_pymongo_collection", classmethod(lambda cls: MagicMock()))
    monkeypatch.setattr(StandardDocument, "get_pymongo_collection", classmethod(lambda cls: MagicMock()))
    monkeypatch.setattr(StandardChunk, "get_pymongo_collection", classmethod(lambda cls: MagicMock()))

    class MockField:
        def __init__(self, name):
            self.name = name
        def __eq__(self, other):
            return True

    ExtractedEntity.drawing_id = MockField("drawing_id")
    AuditViolation.audit_session_id = MockField("audit_session_id")

    mock_drawings = {}
    mock_entities = []
    mock_sessions = {}
    mock_violations = []

    async def mock_save(self):
        if not hasattr(self, "id") or self.id is None:
            self.id = uuid.uuid4().hex
        
        id_str = str(self.id)
        if isinstance(self, DrawingDocument):
            mock_drawings[id_str] = self
        elif isinstance(self, AuditSession):
            mock_sessions[id_str] = self
        return self

    async def mock_get(cls, id):
        id_str = str(id)
        if cls == DrawingDocument:
            return mock_drawings.get(id_str)
        elif cls == AuditSession:
            return mock_sessions.get(id_str)
        return None

    class MockFind:
        def __init__(self, cls, *args, **kwargs):
            self.cls = cls

        async def to_list(self, *args, **kwargs):
            if self.cls == ExtractedEntity:
                return mock_entities
            elif self.cls == AuditViolation:
                return mock_violations
            return []

    monkeypatch.setattr(DrawingDocument, "save", mock_save)
    monkeypatch.setattr(DrawingDocument, "get", classmethod(mock_get))
    monkeypatch.setattr(AuditSession, "save", mock_save)
    monkeypatch.setattr(AuditSession, "get", classmethod(mock_get))
    monkeypatch.setattr(AuditViolation, "save", mock_save)
    monkeypatch.setattr(ExtractedEntity, "find", classmethod(lambda cls, *args, **kwargs: MockFind(cls)))
    monkeypatch.setattr(AuditViolation, "find", classmethod(lambda cls, *args, **kwargs: MockFind(cls)))

    return {
        "drawings": mock_drawings,
        "entities": mock_entities,
        "sessions": mock_sessions,
        "violations": mock_violations
    }

def test_guardrails_pure_logic():
    # Test is_title_block_category
    assert is_title_block_category("Title Block") is True
    assert is_title_block_category("titleblock") is True
    assert is_title_block_category("drawing_views") is False

    # Test is_bom_category
    assert is_bom_category("BOM") is True
    assert is_bom_category("bill_of_materials") is True
    assert is_bom_category("notes_section") is False

    # Test is_admin_bom_marking
    # 1. Stock Qty/0 markings (should return True always)
    assert is_admin_bom_marking({"text_content": "stock qty", "details": "", "category": "notes_section"}) is True
    assert is_admin_bom_marking({"text_content": "0", "details": "", "category": "notes_section"}) is True
    
    # 2. Admin terms in BOM category
    assert is_admin_bom_marking({"text_content": "part no.", "details": "", "category": "bom"}) is True
    assert is_admin_bom_marking({"text_content": "remarks", "details": "", "category": "bom"}) is True
    
    # 3. Regular component description in BOM category (should return False)
    assert is_admin_bom_marking({"text_content": "Hex Bolt", "details": "Changed size", "category": "bom"}) is False

@pytest.mark.asyncio
async def test_perform_physical_comparison_endpoint(mock_beanie_docs, monkeypatch):
    # Set up drawings in mock DB
    ref_drawing = DrawingDocument(
        file_name="ref.dxf",
        file_path="uploads/ref.dxf",
        file_hash="ref_hash",
        file_size_bytes=100,
        format="dxf",
        status="completed",
        metadata={"render_bounds": [0, 0, 100, 100]}
    )
    ref_drawing.id = "ref_dwg_id"
    mock_beanie_docs["drawings"][ref_drawing.id] = ref_drawing

    rev_drawing = DrawingDocument(
        file_name="rev.dxf",
        file_path="uploads/rev.dxf",
        file_hash="rev_hash",
        file_size_bytes=100,
        format="dxf",
        status="completed",
        metadata={"render_bounds": [0, 0, 100, 100]}
    )
    rev_drawing.id = "rev_dwg_id"
    mock_beanie_docs["drawings"][rev_drawing.id] = rev_drawing

    # Set up mock entities
    mock_beanie_docs["entities"].append(
        ExtractedEntity(
            drawing_id="ref_dwg_id",
            job_id="job1",
            entity_type="text",
            layer="am_bor",
            properties={"text": "REV A"},
            geometry={"insert": [10.0, 10.0]}
        )
    )
    mock_beanie_docs["entities"].append(
        ExtractedEntity(
            drawing_id="rev_dwg_id",
            job_id="job2",
            entity_type="text",
            layer="am_bor",
            properties={"text": "REV B"},
            geometry={"insert": [10.0, 10.0]}
        )
    )
    
    # A genuine drawing-view component (NOT on a BOM/title layer, so safe_filter keeps it).
    # It sits at (50,50), inside the views box provided below.
    mock_beanie_docs["entities"].append(
        ExtractedEntity(
            drawing_id="rev_dwg_id",
            job_id="job2",
            entity_type="text",
            layer="outline",
            properties={"text": "M8 Bolt"},
            geometry={"insert": [50.0, 50.0]}
        )
    )

    # drawing_views is now scoped strictly to the `views` zone box (no residual fallback), so the
    # comparison needs a real views box covering the drawing. Zone detection on this synthetic
    # 3-entity sheet collapses to the (0,0,1000,1000) "no sheet bounds" placeholder — which
    # correctly yields an empty drawing_views under strict scoping — so pin a real one here.
    async def _fake_regions(entities, render_bounds=None, **kwargs):
        return {"views": [0.0, 0.0, 100.0, 100.0]}

    monkeypatch.setattr(
        "services.backend.infrastructure.audit.bom.table_extractor.extract_dynamic_regions_async",
        _fake_regions,
    )

    # Set up GEMINI_API_KEY environment variable for test execution
    monkeypatch.setenv("GEMINI_API_KEY", "mock_key")

    # Mock the google.genai.Client
    mock_client = MagicMock()
    mock_generate_content = MagicMock()
    
    gemini_json_response = {
        "drawing_views": {"status": "MATCHED", "difference_summary": "views OK"},
        "notes_section": {"status": "MATCHED", "difference_summary": "notes OK"},
        "bill_of_materials": {"status": "CHANGED", "difference_summary": "BOM modified"},
        "title_block": {"status": "CHANGED", "difference_summary": "Title block modified"},
        "isometric_view": {"status": "MATCHED", "difference_summary": "ISO OK"},
        "other_engineering_references": {"status": "MATCHED", "difference_summary": "other OK"},
        "canvas_markings": [
            {
                "text_content": "PART NO",
                "status": "CHANGED",
                "details": "Admin part no row header",
                # Make this bill_of_materials so it gets cleaned as expected
                "category": "bill_of_materials",
                "entity_id": "1A"
            },
            {
                "text_content": "M8 Bolt",
                "status": "CHANGED",
                "details": "M8 Bolt changed to M10",
                # Use drawing_views so it is not filtered as administrative/bom markup
                "category": "drawing_views",
                "entity_id": "2B"
            }
        ]
    }
    
    mock_response_obj = MagicMock()
    mock_response_obj.text = json.dumps(gemini_json_response)
    mock_generate_content.return_value = mock_response_obj
    mock_client.models.generate_content = mock_generate_content

    # Inject mock Client class constructor
    with patch("services.backend.api.routers.audits.genai.Client", return_value=mock_client):
        request = PhysicalComparisonRequest(
            reference_drawing_id="ref_dwg_id",
            drawing_id="rev_dwg_id"
        )
        
        response = await perform_physical_comparison(request)
        
        assert response.success is True
        assert response.data is not None
        
        # Verify guardrail filtering (PART NO is admin/BOM, should be removed; M8 Bolt is drawing view component, should remain)
        markings = response.data.canvas_markings
        text_contents = [m.text_content for m in markings]
        assert "M8 Bolt" in text_contents
        assert "PART NO" not in text_contents
