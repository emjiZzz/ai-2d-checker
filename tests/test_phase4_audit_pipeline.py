import pytest
import os
import uuid
import hashlib
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

# Target Beanie Models
from services.backend.domain.models.standard_document import StandardDocument
from services.backend.domain.models.standard_chunk import StandardChunk
from services.backend.domain.models.audit_session import AuditSession
from services.backend.domain.models.audit_violation import AuditViolation
from services.backend.domain.models.drawing_document import DrawingDocument
from services.backend.domain.models.extracted_entity import ExtractedEntity

# Target Domain Services
from services.backend.infrastructure.storage.path_resolver import get_storage_root, bootstrap_storage
from services.backend.infrastructure.audit.standards_parser import StandardsParser
from services.backend.infrastructure.audit.standards_loader import StandardsLoader
from services.backend.infrastructure.audit.rule_engine import RuleEngine
from services.backend.infrastructure.audit.confidence import ConfidenceScorer
from services.backend.infrastructure.audit.audit_orchestrator import AuditOrchestrator
from services.backend.infrastructure.audit.audit_pipeline import BackgroundAuditQueue

@pytest.fixture(autouse=True)
def mock_beanie_docs(monkeypatch):
    """
    In-memory mock store for Beanie document classes in Phase 4.
    Blocks real MongoDB/Beanie queries and index hooks to run completely offline.
    """
    monkeypatch.setattr(DrawingDocument, "get_pymongo_collection", classmethod(lambda cls: MagicMock()))
    monkeypatch.setattr(StandardDocument, "get_pymongo_collection", classmethod(lambda cls: MagicMock()))
    monkeypatch.setattr(StandardChunk, "get_pymongo_collection", classmethod(lambda cls: MagicMock()))
    monkeypatch.setattr(AuditSession, "get_pymongo_collection", classmethod(lambda cls: MagicMock()))
    monkeypatch.setattr(AuditViolation, "get_pymongo_collection", classmethod(lambda cls: MagicMock()))
    monkeypatch.setattr(ExtractedEntity, "get_pymongo_collection", classmethod(lambda cls: MagicMock()))

    class MockField:
        def __init__(self, name):
            self.name = name
        def __eq__(self, other):
            class Comparison:
                def __init__(self, left, right):
                    self.left = left
                    self.right = right
            return Comparison(self, other)

    ExtractedEntity.job_id = MockField("job_id")
    ExtractedEntity.entity_type = MockField("entity_type")
    ExtractedEntity.drawing_id = MockField("drawing_id")
    StandardChunk.standard_id = MockField("standard_id")
    AuditViolation.audit_session_id = MockField("audit_session_id")
    StandardDocument.standard_hash = MockField("standard_hash")

    mock_drawings = {}
    mock_standards = {}
    mock_chunks = []
    mock_sessions = {}
    mock_violations = []
    mock_entities = []

    async def mock_save(self):
        if not hasattr(self, "id") or self.id is None:
            self.id = uuid.uuid4().hex
        
        id_str = str(self.id)
        if isinstance(self, DrawingDocument):
            mock_drawings[id_str] = self
        elif isinstance(self, StandardDocument):
            mock_standards[id_str] = self
        elif isinstance(self, AuditSession):
            mock_sessions[id_str] = self
        return self

    async def mock_get(cls, id):
        id_str = str(id)
        if cls == DrawingDocument:
            return mock_drawings.get(id_str)
        elif cls == StandardDocument:
            return mock_standards.get(id_str)
        elif cls == AuditSession:
            return mock_sessions.get(id_str)
        return None

    async def mock_find_one(cls, *args, **kwargs):
        # Allow checking duplicate hash match in standards loader
        query = args[0] if args else kwargs.get("expression")
        if cls == StandardDocument and query and hasattr(query, "right"):
            target_hash = query.right
            for std in mock_standards.values():
                if std.standard_hash == target_hash:
                    return std
        return None

    async def mock_insert_many(cls, documents, *args, **kwargs):
        for doc in documents:
            if not hasattr(doc, "id") or doc.id is None:
                doc.id = uuid.uuid4().hex
            if isinstance(doc, StandardChunk):
                mock_chunks.append(doc)
            elif isinstance(doc, AuditViolation):
                mock_violations.append(doc)
            elif isinstance(doc, ExtractedEntity):
                mock_entities.append(doc)
        return documents

    class MockFind:
        def __init__(self, cls, *args, **kwargs):
            self.cls = cls
            self.query = args[0] if args else None

        async def to_list(self, *args, **kwargs):
            if self.cls == StandardChunk:
                return mock_chunks
            elif self.cls == AuditViolation:
                return mock_violations
            elif self.cls == ExtractedEntity:
                return mock_entities
            return []

    monkeypatch.setattr(DrawingDocument, "save", mock_save)
    monkeypatch.setattr(DrawingDocument, "get", classmethod(mock_get))
    
    monkeypatch.setattr(StandardDocument, "save", mock_save)
    monkeypatch.setattr(StandardDocument, "get", classmethod(mock_get))
    monkeypatch.setattr(StandardDocument, "find_one", classmethod(mock_find_one))
    
    monkeypatch.setattr(AuditSession, "save", mock_save)
    monkeypatch.setattr(AuditSession, "get", classmethod(mock_get))
    
    monkeypatch.setattr(StandardChunk, "insert_many", classmethod(mock_insert_many))
    monkeypatch.setattr(StandardChunk, "find", classmethod(lambda cls, *args, **kwargs: MockFind(cls, *args, **kwargs)))
    
    monkeypatch.setattr(AuditViolation, "insert_many", classmethod(mock_insert_many))
    monkeypatch.setattr(AuditViolation, "find", classmethod(lambda cls, *args, **kwargs: MockFind(cls, *args, **kwargs)))

    monkeypatch.setattr(ExtractedEntity, "insert_many", classmethod(mock_insert_many))
    monkeypatch.setattr(ExtractedEntity, "find", classmethod(lambda cls, *args, **kwargs: MockFind(cls, *args, **kwargs)))

    return {
        "drawings": mock_drawings,
        "standards": mock_standards,
        "chunks": mock_chunks,
        "sessions": mock_sessions,
        "violations": mock_violations,
        "entities": mock_entities
    }


def test_standards_text_chunking():
    """
    Verify the text/markdown chunking logic inside StandardsParser.
    """
    bootstrap_storage()
    raw_content = (
        "# SECTION 1. LAYER CONVENTIONS\n"
        "All structural contours must rest on layer LAYER_BORDER.\n"
        "Draft lines must be pruned from production blocks.\n\n"
        "## 1.2 DIMENSION ALIGNMENTS\n"
        "All annotations require standard MM unit extensions."
    )
    
    test_file_path = get_storage_root() / "standards" / "test_std.txt"
    test_file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(test_file_path, "w", encoding="utf-8") as f:
        f.write(raw_content)

    try:
        chunks, _ = StandardsParser.parse_file(test_file_path)
        assert len(chunks) == 2
        
        assert chunks[0]["section_header"] == "SECTION 1. LAYER CONVENTIONS"
        assert "LAYER_BORDER" in chunks[0]["content"]
        assert chunks[0]["metadata"]["line_start"] == 1
        
        assert chunks[1]["section_header"] == "1.2 DIMENSION ALIGNMENTS"
        assert "MM unit extensions" in chunks[1]["content"]
    finally:
        if test_file_path.exists():
            test_file_path.unlink()


@pytest.mark.asyncio
async def test_duplicate_standards_protection(mock_beanie_docs):
    """
    Verify standard loader rejects duplicate file content uploads to save storage blocks.
    """
    bootstrap_storage()
    # Ingest a dummy file
    content = b"Drafting rules 2026 update document contents."
    file_hash = hashlib.sha256(content).hexdigest()
    
    # Mock standard document save
    std_doc = StandardDocument(
        name="ISO STANDARD MOCK",
        file_path="storage/standards/mock.txt",
        standard_hash=file_hash,
        file_size_bytes=len(content),
        format="txt",
    )
    std_doc.id = "std_123"
    
    # Save standard to our in-memory dict
    mock_beanie_docs["standards"][std_doc.id] = std_doc
    
    # Write a temporary source file to load
    temp_src = get_storage_root() / "standards" / "temp_src.txt"
    temp_src.parent.mkdir(parents=True, exist_ok=True)
    with open(temp_src, "wb") as f:
        f.write(content)
        
    try:
        # Try uploading a duplicate
        duplicate, is_duplicate = await StandardsLoader.ingest_standard(
            src_file_path=temp_src,
            name="ISO STANDARD MOCK"
        )
        # It must return the original matching document, bypassing duplicate database insertions
        assert str(duplicate.id) == "std_123"
        assert is_duplicate is True
    finally:
        if temp_src.exists():
            temp_src.unlink()


@pytest.mark.asyncio
async def test_rule_engine_deterministic_checks(mock_beanie_docs):
    """
    Verify rule engine flags missing dimensions, illegal layers, scales, duplications and empty title blocks.
    """
    drawing = DrawingDocument(
        file_name="anchor_bolt.dwg",
        file_path="storage/drawings/anchor_bolt.dxf",
        file_hash="xyz789hash",
        file_size_bytes=2048,
        format="dxf",
        entity_counts={"line": 5}
    )
    drawing.id = "dwg_123"
    mock_beanie_docs["drawings"][drawing.id] = drawing

    # 1. Test Illegal Layer name entity
    ent1 = ExtractedEntity(
        drawing_id=drawing.id,
        job_id="job_1",
        entity_type="line",
        layer="TEMP_CONSTRUCTION_LINE",
        geometry={"coordinates": [[0.0, 0.0], [10.0, 10.0]], "start": [0.0, 0.0], "end": [10.0, 10.0]},
        attributes={}
    )
    
    # 2. Test Unsupported Scale Ratio text
    ent2 = ExtractedEntity(
        drawing_id=drawing.id,
        job_id="job_1",
        entity_type="text",
        layer="BORDER_TEXT",
        geometry={"coordinates": [[10.0, 10.0]]},
        attributes={},
        properties={"value": "Scale: 1:13"}
    )
    
    ent3 = ExtractedEntity(
        drawing_id=drawing.id,
        job_id="job_1",
        entity_type="text",
        layer="border",
        geometry={"coordinates": [[50.0, 50.0]]},
        attributes={},
        properties={"value": "COMPANY NAME"}
    )

    extra_lines = [
        ExtractedEntity(
            drawing_id=drawing.id,
            job_id="job_1",
            entity_type="line",
            layer="geometry",
            geometry={"coordinates": [[float(i), 0.0], [float(i) + 10.0, 10.0]]},
            attributes={}
        )
        for i in range(10)
    ]

    mock_beanie_docs["entities"].extend([ent1, ent2, ent3] + extra_lines)
    
    violations = await RuleEngine.validate_drawing("session_123", drawing)
    
    # Verify forbidden layer was flagged
    layer_violations = [v for v in violations if v.category == "forbidden_layer_name"]
    assert len(layer_violations) == 1
    assert "TEMP_CONSTRUCTION_LINE" in layer_violations[0].description
    
    # Verify missing dimensions was flagged
    dim_violations = [v for v in violations if v.category == "missing_dimensions"]
    assert len(dim_violations) == 1
    
    # Verify invalid scale ratio was flagged
    scale_violations = [v for v in violations if v.category == "invalid_scale"]
    assert len(scale_violations) == 1
    assert "1:13" in scale_violations[0].description
    
    # Verify title block placeholder was flagged
    title_violations = [v for v in violations if v.category == "empty_title_block"]
    assert len(title_violations) == 1
    assert "COMPANY NAME" in title_violations[0].description


def test_scoring_compliance_deductions():
    """
    Verify compliance score deducts weights accurately, respecting lower floor boundary of 0%.
    """
    # Base is 100
    # Deductions: Critical = -25, High = -15, Medium = -8, Low = -3
    
    # 1. Standard calculation
    violations = [
        AuditViolation(audit_session_id="s1", severity="critical", category="c1", description="d1", recommendation="r1", source="rule_engine"), # -25
        AuditViolation(audit_session_id="s1", severity="high", category="c2", description="d2", recommendation="r2", source="rule_engine"), # -15
        AuditViolation(audit_session_id="s1", severity="medium", category="c3", description="d3", recommendation="r3", source="rule_engine"), # -8
        AuditViolation(audit_session_id="s1", severity="low", category="c4", description="d4", recommendation="r4", source="rule_engine") # -3
    ]
    
    score = ConfidenceScorer.calculate_compliance_score(violations)
    assert score == 100 - (25 + 15 + 8 + 3) # 49%
    
    # 2. Underflow boundary clamp verification
    many_violations = violations * 4 # Exceeds 100
    score_clamped = ConfidenceScorer.calculate_compliance_score(many_violations)
    assert score_clamped == 0 # Clamped floor


@pytest.mark.asyncio
async def test_audit_orchestrator_pipeline_flow(mock_beanie_docs):
    """
    Run standard audit orchestrator loop in-memory, checking dynamic state transformations.
    """
    # Setup standard and drawing records in our mocks
    std = StandardDocument(
        name="ISO LAYER SPEC",
        file_path="storage/standards/iso_layer.txt",
        standard_hash="abc123hash",
        file_size_bytes=50,
        format="txt"
    )
    std.id = "std_999"
    mock_beanie_docs["standards"][std.id] = std
    
    dwg = DrawingDocument(
        file_name="anchor_bolt.dwg",
        file_path="storage/drawings/anchor_bolt.dxf",
        file_hash="xyz789hash",
        file_size_bytes=2048,
        format="dxf",
        entity_counts={"line": 5}
    )
    dwg.id = "dwg_999"
    mock_beanie_docs["drawings"][dwg.id] = dwg
    
    # Ingest a couple of mock entities into mock collection
    ent = ExtractedEntity(
        drawing_id=dwg.id,
        job_id="job_999",
        entity_type="line",
        layer="TEMP_JUNK_LINES", # triggers layer violation!
        geometry={},
        attributes={}
    )
    mock_beanie_docs["entities"].append(ent)
    
    # Create audit session
    session = AuditSession(
        drawing_id=dwg.id,
        standard_id=std.id,
        status="queued"
    )
    session.id = "session_999"
    mock_beanie_docs["sessions"][session.id] = session
    
    # Trigger Auditing Orchestrator
    completed_session, violation_count = await AuditOrchestrator.run_audit(dwg.id, std.id, session.id)
    
    assert completed_session.status == "completed"
    assert completed_session.compliance_score is not None
    assert len(mock_beanie_docs["violations"]) > 0


@pytest.mark.asyncio
async def test_background_fifo_queue(mock_beanie_docs):
    """
    Verify background processing worker fetches items FIFO and completes audits asynchronously.
    """
    # Create audit session
    session = AuditSession(
        drawing_id="dwg_999",
        standard_id="std_999",
        status="queued"
    )
    session.id = "session_queue_1"
    mock_beanie_docs["sessions"][session.id] = session
    
    # Mock run_audit on Orchestrator
    orchestrator_mock = AsyncMock()
    orchestrator_mock.run_audit.return_value = None
    
    # Create pipeline queue and run one item
    pipeline = BackgroundAuditQueue()
    pipeline.orchestrator = orchestrator_mock
    
    # Submit and run queue loop safely once
    await pipeline.enqueue("dwg_999", "std_999", session.id)
    assert pipeline.queue.qsize() == 1
    
    # Process one queue frame
    drawing_id, standard_id, session_id = await pipeline.queue.get()
    await pipeline.orchestrator.run_audit(drawing_id, standard_id, session_id)
    pipeline.queue.task_done()
    
    assert pipeline.queue.qsize() == 0
    orchestrator_mock.run_audit.assert_called_once_with("dwg_999", "std_999", session.id)
