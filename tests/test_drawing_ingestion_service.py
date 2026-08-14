"""
Ingestion service under the room-owned-drawings model.

Two invariants replace the old hash-dedup behavior:
  1. Every upload is its own fresh DrawingDocument — re-uploading the same bytes
     yields a NEW distinct record with a unique on-disk filename, re-queued for
     parsing (no cache reuse). This is what kills the re-ingest trap.
  2. purge_drawing() is the single source of truth for deletion: it removes the
     record, its file, and its caches, and fires entity/job deletes.

Runs fully offline: Beanie document I/O, the processing queue, and the cache
manager are all mocked; the file operations run against a pytest tmp dir.
"""

import uuid
from unittest.mock import MagicMock

import pytest

from services.backend.domain.models.drawing_document import DrawingDocument
from services.backend.domain.models.extracted_entity import ExtractedEntity
from services.backend.domain.models.extraction_job import ExtractionJob
from services.backend.infrastructure.ingestion import drawing_ingestion_service as svc
from services.backend.infrastructure.ingestion.drawing_ingestion_service import DrawingIngestionService
from services.backend.infrastructure.audit.comparison.cache_manager import ComparisonCacheManager
from services.backend.infrastructure.cad.processing_queue import processing_queue

pytestmark = pytest.mark.asyncio


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


@pytest.fixture
def storage(tmp_path, monkeypatch):
    """Redirect all get_storage_root() calls in the service to a throwaway dir."""
    for sub in ("temp", "uploads", "cache", "renderings"):
        (tmp_path / sub).mkdir()
    monkeypatch.setattr(svc, "get_storage_root", lambda: tmp_path)
    return tmp_path


@pytest.fixture
def mock_db(monkeypatch):
    """In-memory Beanie doubles + queue/cache recorders (offline)."""
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

    ExtractionJob.drawing_id = MockField("drawing_id")
    ExtractedEntity.drawing_id = MockField("drawing_id")

    drawings: dict[str, DrawingDocument] = {}
    jobs: dict[str, ExtractionJob] = {}
    calls: dict[str, list] = {"enqueue": [], "cache_clear": []}

    async def mock_save(self):
        if not getattr(self, "id", None):
            self.id = uuid.uuid4().hex
        if isinstance(self, DrawingDocument):
            drawings[str(self.id)] = self
        elif isinstance(self, ExtractionJob):
            jobs[str(self.id)] = self
        return self

    async def mock_delete(self):
        drawings.pop(str(self.id), None)

    async def mock_get(cls, doc_id):
        return drawings.get(str(doc_id))

    def _target_drawing_id(args):
        for arg in args:
            if hasattr(arg, "right"):
                return arg.right
        return None

    class MockFind:
        def __init__(self, store, drawing_id):
            self._store = store
            self._drawing_id = drawing_id

        async def delete(self):
            for key in [k for k, v in self._store.items()
                        if getattr(v, "drawing_id", None) == self._drawing_id]:
                del self._store[key]

    def mock_entity_find(cls, *args, **kwargs):
        return MockFind({}, _target_drawing_id(args))  # entities untracked; delete is a no-op

    def mock_job_find(cls, *args, **kwargs):
        return MockFind(jobs, _target_drawing_id(args))

    async def mock_enqueue(drawing_id, job_id):
        calls["enqueue"].append((drawing_id, job_id))

    def mock_clear_cache(cls, drawing_id):
        calls["cache_clear"].append(drawing_id)

    monkeypatch.setattr(DrawingDocument, "save", mock_save)
    monkeypatch.setattr(ExtractionJob, "save", mock_save)
    monkeypatch.setattr(DrawingDocument, "delete", mock_delete)
    monkeypatch.setattr(DrawingDocument, "get", classmethod(mock_get))
    monkeypatch.setattr(ExtractedEntity, "find", classmethod(mock_entity_find))
    monkeypatch.setattr(ExtractionJob, "find", classmethod(mock_job_find))
    monkeypatch.setattr(processing_queue, "enqueue", mock_enqueue)
    monkeypatch.setattr(ComparisonCacheManager, "clear_cache_for_drawing", classmethod(mock_clear_cache))

    return {"drawings": drawings, "jobs": jobs, "calls": calls}


async def test_reupload_creates_a_new_distinct_drawing(storage, mock_db):
    """No hash dedup: the same bytes uploaded twice become two separate drawings,
    each with its own unique file, each re-queued for parsing."""
    content = b"fake dxf drawing bytes"

    d1, _j1, dup1 = await DrawingIngestionService.process_ingestion(_FakeUploadFile("bracket.dxf", content))
    d2, _j2, dup2 = await DrawingIngestionService.process_ingestion(_FakeUploadFile("bracket.dxf", content))

    assert dup1 is False and dup2 is False          # is_duplicate is vestigial, always False
    assert d1.id != d2.id                            # distinct records, no dedup
    assert d1.file_path != d2.file_path              # unique on-disk filenames
    assert d1.status == "queued" and d2.status == "queued"
    assert (storage / d1.file_path).exists()
    assert (storage / d2.file_path).exists()
    assert len(mock_db["drawings"]) == 2
    assert len(mock_db["calls"]["enqueue"]) == 2      # both queued for fresh parsing


async def test_purge_drawing_removes_record_file_and_caches(storage, mock_db):
    """purge_drawing() deletes the record, its upload file, its extraction job,
    and clears its caches — no orphans left behind."""
    content = b"fake dxf drawing bytes"
    drawing, _job, _ = await DrawingIngestionService.process_ingestion(_FakeUploadFile("bracket.dxf", content))
    drawing_id = str(drawing.id)
    upload_path = storage / drawing.file_path

    assert upload_path.exists()
    assert drawing_id in mock_db["drawings"]
    assert any(j.drawing_id == drawing_id for j in mock_db["jobs"].values())

    await DrawingIngestionService.purge_drawing(drawing_id)

    assert not upload_path.exists()                                    # file gone
    assert drawing_id not in mock_db["drawings"]                       # record gone
    assert not any(j.drawing_id == drawing_id for j in mock_db["jobs"].values())  # job gone
    assert mock_db["calls"]["cache_clear"] == [drawing_id]             # caches cleared


# ---------------------------------------------------------------------------
# Re-extraction: bringing a stale drawing current without losing its identity
# ---------------------------------------------------------------------------


async def test_reextract_queues_a_job_against_the_same_drawing(storage, mock_db):
    """The point of the route: the drawing keeps its id, its file and its record.

    Delete-and-re-upload was the only previous cure for a drawing ingested before an
    extraction-time field existed, and it discards the id every room slot and audit
    references.
    """
    drawing, first_job, _ = await DrawingIngestionService.process_ingestion(
        _FakeUploadFile("bracket.dxf", b"fake dxf drawing bytes")
    )
    drawing_id = str(drawing.id)
    drawing.status = "completed"
    await drawing.save()
    mock_db["calls"]["enqueue"].clear()

    same_drawing, job = await DrawingIngestionService.reextract_drawing(drawing_id)

    assert str(same_drawing.id) == drawing_id          # same record, not a new one
    assert (storage / drawing.file_path).exists()      # source file untouched
    assert str(job.id) != str(first_job.id)            # a fresh job to poll
    assert job.drawing_id == drawing_id
    assert same_drawing.status == "queued"
    assert mock_db["calls"]["enqueue"] == [(drawing_id, str(job.id))]


async def test_reextract_clears_cached_comparisons_before_queueing(storage, mock_db):
    """A cache hit returns in ~0.14s and would bypass the whole re-extraction.

    Cached audits were computed against the entities this run replaces, so leaving them
    serves findings whose entities no longer exist. Cleared before the job is enqueued,
    so there is no window where a stale hit can be served against new entities.
    """
    drawing, _job, _ = await DrawingIngestionService.process_ingestion(
        _FakeUploadFile("bracket.dxf", b"fake dxf drawing bytes")
    )
    drawing_id = str(drawing.id)
    drawing.status = "completed"
    await drawing.save()

    await DrawingIngestionService.reextract_drawing(drawing_id)

    assert mock_db["calls"]["cache_clear"] == [drawing_id]


async def test_reextract_refuses_while_an_extraction_is_already_running(storage, mock_db):
    """Two concurrent runs would race on the same entity set."""
    from fastapi import HTTPException

    drawing, _job, _ = await DrawingIngestionService.process_ingestion(
        _FakeUploadFile("bracket.dxf", b"fake dxf drawing bytes")
    )
    drawing_id = str(drawing.id)

    for busy in ("queued", "processing"):
        drawing.status = busy
        await drawing.save()
        mock_db["calls"]["enqueue"].clear()

        with pytest.raises(HTTPException) as excinfo:
            await DrawingIngestionService.reextract_drawing(drawing_id)

        assert excinfo.value.status_code == 409
        assert mock_db["calls"]["enqueue"] == []       # nothing queued


async def test_reextract_refuses_when_the_source_file_is_gone(storage, mock_db):
    """Fail with a reason here rather than enqueue a job that dies in the worker.

    The worker's path error surfaces only in a log nobody reads, and the drawing sits at
    'queued' forever.
    """
    from fastapi import HTTPException

    drawing, _job, _ = await DrawingIngestionService.process_ingestion(
        _FakeUploadFile("bracket.dxf", b"fake dxf drawing bytes")
    )
    drawing_id = str(drawing.id)
    drawing.status = "completed"
    await drawing.save()
    (storage / drawing.file_path).unlink()
    mock_db["calls"]["enqueue"].clear()

    with pytest.raises(HTTPException) as excinfo:
        await DrawingIngestionService.reextract_drawing(drawing_id)

    assert excinfo.value.status_code == 422
    assert mock_db["calls"]["enqueue"] == []
    assert mock_db["calls"]["cache_clear"] == []       # nothing destroyed on the way out


async def test_reextract_rejects_an_unknown_drawing(storage, mock_db):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as excinfo:
        await DrawingIngestionService.reextract_drawing("does-not-exist")

    assert excinfo.value.status_code == 404


async def test_reextract_does_not_delete_entities_up_front(storage, mock_db):
    """Entity replacement belongs to the pipeline, immediately before its own insert.

    Deleting here would blank the canvas for as long as the job sits in the queue, and
    permanently if the parse then failed. Pinned because moving the delete into the service
    reads like the obvious tidy-up.
    """
    drawing, _job, _ = await DrawingIngestionService.process_ingestion(
        _FakeUploadFile("bracket.dxf", b"fake dxf drawing bytes")
    )
    drawing_id = str(drawing.id)
    drawing.status = "completed"
    await drawing.save()

    deletes: list[str] = []
    original_find = ExtractedEntity.find

    def recording_find(cls, *args, **kwargs):
        found = original_find(*args, **kwargs)
        deletes.append("called")
        return found

    ExtractedEntity.find = classmethod(recording_find)
    try:
        await DrawingIngestionService.reextract_drawing(drawing_id)
    finally:
        ExtractedEntity.find = original_find

    assert deletes == [], "the service must leave entity replacement to the pipeline"
