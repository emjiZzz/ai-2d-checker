import uuid
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from services.backend.domain.models.drawing_document import DrawingDocument
from services.backend.domain.models.extracted_entity import ExtractedEntity
from services.backend.domain.models.extraction_job import ExtractionJob
from services.backend.domain.services.drawing_ingestion_service import DrawingIngestionService
from services.backend.infrastructure.storage.path_resolver import bootstrap_storage

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module", autouse=True)
def setup_test_env():
    bootstrap_storage()
    yield


@pytest.fixture(autouse=True)
def mock_beanie_docs(monkeypatch):
    """
    In-memory mock store for Beanie document classes, following the same pattern
    used in test_phase3_cad_pipeline.py, so this runs fully offline.
    """
    monkeypatch.setattr(DrawingDocument, "get_pymongo_collection", classmethod(lambda cls: MagicMock()))
    monkeypatch.setattr(ExtractionJob, "get_pymongo_collection", classmethod(lambda cls: MagicMock()))
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

    DrawingDocument.file_hash = MockField("file_hash")
    ExtractionJob.drawing_id = MockField("drawing_id")
    ExtractedEntity.drawing_id = MockField("drawing_id")

    mock_drawings: dict[str, DrawingDocument] = {}
    mock_jobs: dict[str, ExtractionJob] = {}

    async def mock_save(self):
        if not hasattr(self, "id") or self.id is None:
            self.id = uuid.uuid4().hex
        if isinstance(self, DrawingDocument):
            mock_drawings[str(self.id)] = self
        elif isinstance(self, ExtractionJob):
            mock_jobs[str(self.id)] = self
        return self

    async def mock_find_one_drawing(cls, *args, **kwargs):
        target_hash = None
        for arg in args:
            if hasattr(arg, "left") and getattr(arg.left, "name", "") == "file_hash":
                target_hash = arg.right
        for d in mock_drawings.values():
            if d.file_hash == target_hash:
                return d
        return None

    async def mock_find_one_job(cls, *args, **kwargs):
        # No ExtractionJob exists for this drawing_id — reproduces the audit's
        # "completed drawing, missing job record" edge case unconditionally.
        return None

    class MockEntityFind:
        async def delete(self):
            return None

    def mock_entity_find(cls, *args, **kwargs):
        return MockEntityFind()

    monkeypatch.setattr(DrawingDocument, "save", mock_save)
    monkeypatch.setattr(ExtractionJob, "save", mock_save)
    monkeypatch.setattr(DrawingDocument, "find_one", classmethod(mock_find_one_drawing))
    monkeypatch.setattr(ExtractionJob, "find_one", classmethod(mock_find_one_job))
    monkeypatch.setattr(ExtractedEntity, "find", classmethod(mock_entity_find))

    return mock_drawings, mock_jobs


class _FakeUploadFile:
    """Minimal stand-in for FastAPI's UploadFile, chunked-read interface only."""

    def __init__(self, filename: str, content: bytes):
        self.filename = filename
        self._content = content
        self._sent = False

    async def read(self, size: int) -> bytes:
        if self._sent:
            return b""
        self._sent = True
        return self._content


async def test_reupload_of_completed_drawing_with_missing_job_returns_duplicate(mock_beanie_docs):
    """
    Audit finding #1 (docs/refactoring-audit-2026-07-23.md): re-uploading a drawing whose
    hash matches a `completed` DrawingDocument, but which has no matching ExtractionJob
    record (e.g. pruned/migrated), must return a synthetic duplicate job response instead
    of raising a Pydantic ValidationError from constructing ExtractionJob(id="dummy-...").
    """
    mock_drawings, _mock_jobs = mock_beanie_docs
    content = b"fake dxf drawing bytes"

    existing = DrawingDocument(
        file_name="bracket.dxf",
        file_path="uploads/existing.dxf",
        file_hash=__import__("hashlib").sha256(content).hexdigest(),
        file_size_bytes=len(content),
        format="dxf",
        status="completed",
    )
    await existing.save()

    upload = _FakeUploadFile("bracket.dxf", content)

    drawing, job, is_duplicate = await DrawingIngestionService.process_ingestion(upload)

    assert is_duplicate is True
    assert drawing.id == existing.id
    assert job.status == "completed"
    # Regression check: constructing this synthetic ExtractionJob must not raise
    # (the pre-fix code passed id=f"dummy-{existing_drawing.id}", which Beanie's
    # PydanticObjectId-typed `id` field rejects). It's never persisted here, so
    # `id` staying None is expected — same as any unsaved Beanie document.
    assert job.id is None
