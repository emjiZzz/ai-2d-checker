"""`ExtractionPipeline.run` must REPLACE a drawing's entities, never append to them.

`run` had no delete for as long as it was only ever reached once per drawing, straight after
upload. The re-extract route (`POST /drawings/{id}/reextract`) reaches it a second time, and a
requeued job always could — so without a delete every entity silently DOUBLES.

That failure mode is the dangerous kind this project keeps paying for: a doubled payload is not
an error. It renders as a drawing (every line drawn twice, pixel-identical) and compares as a
drawing (every text matched against its own duplicate), so nothing anywhere reports a problem.

Ordering is the other half of the property and is asserted separately: the delete sits
immediately before the insert, *after* conversion, parsing and rendering have all succeeded. A
parse that throws must leave the previous extraction intact, because a drawing that renders
nothing is worse than one rendering slightly stale geometry.
"""

import os
import uuid
from unittest.mock import MagicMock

import ezdxf
import pytest

from services.backend.domain.models.drawing_document import DrawingDocument
from services.backend.domain.models.extracted_entity import ExtractedEntity
from services.backend.domain.models.extraction_job import ExtractionJob
from services.backend.infrastructure.cad.extraction_pipeline import ExtractionPipeline
from services.backend.infrastructure.cad.summarization_queue import summarization_queue
from services.backend.infrastructure.storage.path_resolver import (
    bootstrap_storage,
    get_storage_root,
)

pytestmark = pytest.mark.asyncio


def _dxf_bytes() -> bytes:
    doc = ezdxf.new(setup=True)
    msp = doc.modelspace()
    msp.add_line((0, 0), (100, 0))
    msp.add_text("BRACKET").set_placement((10, 10))
    path = get_storage_root() / "temp" / f"replacement_{uuid.uuid4().hex}.dxf"
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(path)
    payload = path.read_bytes()
    path.unlink()
    return payload


@pytest.fixture
def harness(monkeypatch):
    """In-memory Beanie doubles that actually track the entity store, so append-vs-replace
    is observable rather than asserted through a mock call count."""
    for model in (DrawingDocument, ExtractionJob, ExtractedEntity):
        monkeypatch.setattr(
            model, "get_pymongo_collection", classmethod(lambda cls: MagicMock())
        )

    class MockField:
        def __init__(self, name):
            self.name = name

        def __eq__(self, other):
            class Comparison:
                def __init__(self, left, right):
                    self.left = left
                    self.right = right

            return Comparison(self, other)

    ExtractedEntity.drawing_id = MockField("drawing_id")

    drawings: dict[str, DrawingDocument] = {}
    jobs: dict[str, ExtractionJob] = {}
    entities: list = []

    async def mock_save(self):
        if not getattr(self, "id", None):
            self.id = uuid.uuid4().hex
        if isinstance(self, DrawingDocument):
            drawings[str(self.id)] = self
        elif isinstance(self, ExtractionJob):
            jobs[str(self.id)] = self
        return self

    async def mock_get(cls, doc_id):
        if cls is DrawingDocument:
            return drawings.get(str(doc_id))
        if cls is ExtractionJob:
            return jobs.get(str(doc_id))
        return None

    async def mock_find_one(cls, *args, **kwargs):
        return None

    async def mock_insert_many(cls, documents, *args, **kwargs):
        entities.extend(documents)
        return documents

    class MockDeleteResult:
        def __init__(self, deleted_count):
            self.deleted_count = deleted_count

    class MockFind:
        def __init__(self, drawing_id):
            self._drawing_id = drawing_id

        async def delete(self):
            doomed = [e for e in entities if e.drawing_id == self._drawing_id]
            for e in doomed:
                entities.remove(e)
            return MockDeleteResult(len(doomed))

    def mock_entity_find(cls, *args, **kwargs):
        target = next((a.right for a in args if hasattr(a, "right")), None)
        return MockFind(target)

    async def noop_enqueue(drawing_id):
        return None

    monkeypatch.setattr(DrawingDocument, "save", mock_save)
    monkeypatch.setattr(ExtractionJob, "save", mock_save)
    monkeypatch.setattr(DrawingDocument, "get", classmethod(mock_get))
    monkeypatch.setattr(ExtractionJob, "get", classmethod(mock_get))
    monkeypatch.setattr(DrawingDocument, "find_one", classmethod(mock_find_one))
    monkeypatch.setattr(ExtractedEntity, "insert_many", classmethod(mock_insert_many))
    monkeypatch.setattr(ExtractedEntity, "find", classmethod(mock_entity_find))
    monkeypatch.setattr(summarization_queue, "enqueue", noop_enqueue)

    return {"drawings": drawings, "jobs": jobs, "entities": entities}


async def _ingest(payload: bytes) -> tuple[DrawingDocument, str]:
    bootstrap_storage()
    upload_path = get_storage_root() / "uploads" / f"replacement_{uuid.uuid4().hex}.dxf"
    upload_path.write_bytes(payload)
    drawing = DrawingDocument(
        file_name="bracket.dxf",
        file_path=os.path.relpath(upload_path, get_storage_root()),
        file_hash="mock_" + os.urandom(8).hex(),
        file_size_bytes=upload_path.stat().st_size,
        format="dxf",
        status="queued",
    )
    await drawing.save()
    return drawing, str(upload_path)


async def _run(drawing: DrawingDocument) -> ExtractionJob:
    job = ExtractionJob(drawing_id=str(drawing.id), status="queued")
    await job.save()
    await ExtractionPipeline().run(str(drawing.id), str(job.id))
    return await ExtractionJob.get(str(job.id))


async def test_a_second_extraction_replaces_the_entities_instead_of_doubling_them(harness):
    payload = _dxf_bytes()
    drawing, upload_path = await _ingest(payload)

    try:
        first = await _run(drawing)
        assert first.status == "completed", first.error_message
        after_first = len(harness["entities"])
        assert after_first > 0, "nothing extracted, so the replacement assertion proves nothing"

        second = await _run(drawing)
        assert second.status == "completed", second.error_message

        assert len(harness["entities"]) == after_first, (
            "a second extraction appended instead of replacing — every entity is now duplicated, "
            "which renders and compares as a plausible drawing rather than as an error"
        )
    finally:
        if os.path.exists(upload_path):
            os.unlink(upload_path)


async def test_only_this_drawings_entities_are_replaced(harness):
    """The delete is scoped by `drawing_id`; a sibling drawing must be untouched."""
    payload = _dxf_bytes()
    keep_drawing, keep_path = await _ingest(payload)
    target_drawing, target_path = await _ingest(payload)

    try:
        assert (await _run(keep_drawing)).status == "completed"
        keep_count = len(harness["entities"])

        assert (await _run(target_drawing)).status == "completed"
        total_after_target = len(harness["entities"])

        assert (await _run(target_drawing)).status == "completed"

        assert len(harness["entities"]) == total_after_target
        surviving_keep = [
            e for e in harness["entities"] if e.drawing_id == str(keep_drawing.id)
        ]
        assert len(surviving_keep) == keep_count
    finally:
        for path in (keep_path, target_path):
            if os.path.exists(path):
                os.unlink(path)


async def test_a_failed_parse_leaves_the_previous_extraction_intact(harness, monkeypatch):
    """The delete runs after parsing succeeds, so a throw must not blank the drawing.

    Deleting up front is the obvious shape and is wrong: a drawing that renders nothing is
    worse than one rendering slightly stale geometry, and the failure is silent on the canvas.
    """
    payload = _dxf_bytes()
    drawing, upload_path = await _ingest(payload)

    try:
        assert (await _run(drawing)).status == "completed"
        survivors = len(harness["entities"])
        assert survivors > 0

        def exploding_parse(*args, **kwargs):
            raise RuntimeError("corrupt DXF")

        monkeypatch.setattr(
            ExtractionPipeline().parser.__class__, "parse_file", exploding_parse
        )

        failed = await _run(drawing)

        assert failed.status == "failed"
        assert len(harness["entities"]) == survivors, (
            "a failed re-extraction destroyed the previous entities"
        )
    finally:
        if os.path.exists(upload_path):
            os.unlink(upload_path)
