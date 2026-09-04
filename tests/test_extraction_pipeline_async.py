"""
Guards the event loop against `ExtractionPipeline.run`'s blocking work.

Same property, same proof technique, and same reason as
`tests/test_standards_loader_async.py` -- but for the *drawing* ingestion path, which had the
bug that one was written to prevent. `ExtractionPipeline.run` is `async`, and the background
queue that awaits it (`processing_queue._worker`) is a task on the same event loop that
serves HTTP. "Background" here means *not in the request*, not *not on the loop*. Anything
left inline therefore stalls every concurrent request for its full duration.

The user-visible symptom was a "Server Reconnection" banner on every upload: the desktop client
polls `/health` every 5s with a 3s timeout (`apps/desktop/src/stores/connectionStore.ts`), and
`render_dxf_background` -- a 24x18in matplotlib figure at 350 dpi, ~8400x6300 px -- blows
straight through that budget while the loop cannot answer.

Two steps were inline and are covered here:
  - `parse_file` (ezdxf / PyMuPDF geometry extraction), on all three of its call sites
  - `render_dxf_background` / `render_pdf_background` (matplotlib rasterisation)

The DWG (`ODAConverter.convert_dwg_to_dxf`) and 3D (`ThreeDPipeline.parse_and_convert`) steps
were already offloaded and were never part of the defect; the DWG branch reaches the same
`parse_file`/render pair covered below once conversion finishes.

Proof technique, unchanged from the standards test: record which OS thread the call actually
runs on. Same thread as the test = not offloaded (the bug). Different thread = `asyncio.to_thread`
handled it (the fix).

See `docs/vault/06 - Gotchas & Debugging Lessons/
Gotcha - The Background Queue Was Not a Background Thread.md`.
"""
import os
import threading
import uuid
from unittest.mock import MagicMock

import ezdxf
import pytest

from services.backend.domain.models.drawing_document import DrawingDocument
from services.backend.domain.models.extracted_entity import ExtractedEntity
from services.backend.domain.models.extraction_job import ExtractionJob
from services.backend.infrastructure.cad.dxf_parser import DXFParser
from services.backend.infrastructure.cad.extraction_pipeline import ExtractionPipeline
from services.backend.infrastructure.cad.pdf_parser import PDFParser
from services.backend.infrastructure.cad.summarization_queue import summarization_queue
from services.backend.infrastructure.rendering import (
    dxf_background_renderer,
    pdf_background_renderer,
)
from services.backend.infrastructure.storage.path_resolver import (
    bootstrap_storage,
    get_storage_root,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def mock_beanie_docs(monkeypatch):
    """In-memory Beanie doubles, so this runs fully offline (see test_phase3_cad_pipeline)."""
    for model in (DrawingDocument, ExtractionJob, ExtractedEntity):
        monkeypatch.setattr(
            model, "get_pymongo_collection", classmethod(lambda cls: MagicMock())
        )

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

    async def mock_get(cls, id):
        if cls is DrawingDocument:
            return mock_drawings.get(str(id))
        if cls is ExtractionJob:
            return mock_jobs.get(str(id))
        return None

    async def mock_find_one(cls, *args, **kwargs):
        return None

    async def mock_insert_many(cls, documents, *args, **kwargs):
        return documents

    class MockFind:
        """`run` clears a drawing's entities before inserting the new ones, so a re-extraction
        replaces rather than doubles them. The pipeline must survive that call or the thread
        assertions below prove nothing — which is exactly what `_run_pipeline`'s completion
        check exists to catch."""

        async def delete(self):
            class _Result:
                deleted_count = 0

            return _Result()

    monkeypatch.setattr(DrawingDocument, "save", mock_save)
    monkeypatch.setattr(ExtractionJob, "save", mock_save)
    monkeypatch.setattr(DrawingDocument, "get", classmethod(mock_get))
    monkeypatch.setattr(ExtractionJob, "get", classmethod(mock_get))
    monkeypatch.setattr(DrawingDocument, "find_one", classmethod(mock_find_one))
    monkeypatch.setattr(ExtractedEntity, "insert_many", classmethod(mock_insert_many))
    monkeypatch.setattr(ExtractedEntity, "find", classmethod(lambda cls, *a, **k: MockFind()))


@pytest.fixture(autouse=True)
def no_summarization(monkeypatch):
    """Step 8 enqueues AI summarisation; irrelevant here and left unconsumed otherwise."""

    async def noop(drawing_id):
        return None

    monkeypatch.setattr(summarization_queue, "enqueue", noop)


async def _run_pipeline(file_name: str, fmt: str, payload: bytes) -> None:
    """Drops `payload` into the sandbox as an upload and runs the pipeline over it."""
    bootstrap_storage()
    upload_path = get_storage_root() / "uploads" / file_name
    upload_path.write_bytes(payload)

    try:
        drawing = DrawingDocument(
            file_name=file_name,
            file_path=os.path.relpath(upload_path, get_storage_root()),
            file_hash="mock_hash_" + os.urandom(8).hex(),
            file_size_bytes=upload_path.stat().st_size,
            format=fmt,
            status="queued",
        )
        await drawing.save()

        job = ExtractionJob(drawing_id=str(drawing.id), status="queued")
        await job.save()

        await ExtractionPipeline().run(str(drawing.id), str(job.id))

        # A pipeline that died early would "pass" the thread assertions vacuously.
        completed = await ExtractionJob.get(str(job.id))
        assert completed.status == "completed", (
            f"pipeline did not complete, so the offload assertions prove nothing: "
            f"{completed.error_message}"
        )
    finally:
        if upload_path.exists():
            upload_path.unlink()


def _assert_all_offloaded(threads: dict[str, int], expected: set[str], main_thread_id: int):
    missing = expected - threads.keys()
    assert not missing, f"these steps were never called, so nothing was proven: {sorted(missing)}"

    offenders = [step for step, tid in threads.items() if tid == main_thread_id]
    assert not offenders, (
        f"These blocking steps ran on the event-loop thread instead of being offloaded via "
        f"asyncio.to_thread: {offenders}. The processing queue's worker task shares the event "
        "loop with the HTTP server, so this stalls /health and every other request for the "
        "duration of the parse/render -- which is what put the 'Server Reconnection' banner on "
        "screen for every upload."
    )


async def test_dxf_ingestion_offloads_blocking_work_off_the_event_loop_thread(monkeypatch):
    """DXF: ezdxf parsing and the matplotlib raster must both leave the event-loop thread."""
    main_thread_id = threading.get_ident()
    threads: dict[str, int] = {}

    real_parse = DXFParser.parse_file

    def recording_parse(self, file_path):
        threads["parse_file"] = threading.get_ident()
        return real_parse(self, file_path)

    def recording_render(dxf_path, drawing_id, metadata, entities):
        # Stubbed rather than wrapped: the real render is a 350 dpi rasterisation, far too slow
        # to run per-test. What is under test is the thread it lands on, not its output.
        threads["render_dxf_background"] = threading.get_ident()
        metadata["render_bounds"] = [0.0, 0.0, 1.0, 1.0]

    monkeypatch.setattr(DXFParser, "parse_file", recording_parse)
    monkeypatch.setattr(dxf_background_renderer, "render_dxf_background", recording_render)

    doc = ezdxf.new("R2018")
    msp = doc.modelspace()
    msp.add_line((0, 0, 0), (10, 10, 0))
    msp.add_circle((0, 0, 0), radius=5.0)
    scratch = get_storage_root() / "temp" / f"offload_src_{uuid.uuid4().hex}.dxf"
    scratch.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(str(scratch))
    try:
        payload = scratch.read_bytes()
    finally:
        scratch.unlink()

    await _run_pipeline(f"offload_test_{uuid.uuid4().hex}.dxf", "dxf", payload)

    _assert_all_offloaded(
        threads, {"parse_file", "render_dxf_background"}, main_thread_id
    )


async def test_pdf_ingestion_offloads_blocking_work_off_the_event_loop_thread(monkeypatch):
    """PDF: the branch the original analysis missed entirely. Same two steps, same rule."""
    main_thread_id = threading.get_ident()
    threads: dict[str, int] = {}

    def recording_parse(self, file_path):
        threads["parse_file"] = threading.get_ident()
        entities = [
            {
                "entity_type": "line",
                "layer": "0",
                "properties": {"handle": "1A"},
                "geometry": {"points": [[0.0, 0.0], [1.0, 1.0]]},
            }
        ]
        return entities, [], {"line": 1}, {}

    def recording_render(pdf_path, drawing_id, metadata):
        threads["render_pdf_background"] = threading.get_ident()
        metadata["render_bounds"] = [0.0, 0.0, 1.0, 1.0]

    monkeypatch.setattr(PDFParser, "parse_file", recording_parse)
    monkeypatch.setattr(pdf_background_renderer, "render_pdf_background", recording_render)

    await _run_pipeline(f"offload_test_{uuid.uuid4().hex}.pdf", "pdf", b"%PDF-1.4 stub")

    _assert_all_offloaded(
        threads, {"parse_file", "render_pdf_background"}, main_thread_id
    )
