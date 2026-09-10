"""An .icd must reach the 2D DXF path, and must not ingest when it converts to nothing.

An iCAD SX .icd carries both a 3D model and 2D drawing content. It used to be routed to
`ThreeDPipeline` with the STEP/IGES formats, where `ICD2STP.exe` answers exit 102 on an
install without the batch-STEP licence, gmsh then fails to parse the binary, and the
pipeline substitutes a 1x1x1 placeholder cube and reports success. The 2D half -- the only
half the comparison engine reads -- never reached `dxf_parser` at all.

The vendor translator converts that 2D half faithfully, but reports success whether or not
the drawing had any content: on a 27-file production sample, 15 produced a structurally
valid DXF holding zero entities while the translator logged `09271 registered` and exited 0.
Ingesting one of those yields a blank drawing that compares clean against anything, so it
must fail loudly instead.

See `06 - .../Gotcha - iCAD .icd Converts Silently Empty.md`.
"""

import os
import uuid
from unittest.mock import MagicMock

import ezdxf
import pytest

from services.backend.domain.models.drawing_document import DrawingDocument
from services.backend.domain.models.extracted_entity import ExtractedEntity
from services.backend.domain.models.extraction_job import ExtractionJob
from services.backend.infrastructure.cad import extraction_pipeline as pipeline_module
from services.backend.infrastructure.cad.extraction_pipeline import ExtractionPipeline
from services.backend.infrastructure.cad.icd_converter import count_drawing_entities
from services.backend.infrastructure.cad.summarization_queue import summarization_queue
from services.backend.infrastructure.storage.path_resolver import (
    bootstrap_storage,
    get_storage_root,
)

def _dxf_with_title_block_in_a_block() -> bytes:
    """A drawing whose content is nested one INSERT deep, as iCAD's export produces."""
    doc = ezdxf.new(setup=True)
    block = doc.blocks.new(name="JZB_0001")
    for i in range(20):
        block.add_line((0, i), (100, i))
    block.add_text("DWG.No.").set_placement((5, 5))
    doc.modelspace().add_blockref("JZB_0001", (0, 0))
    return _to_bytes(doc)


def _empty_dxf() -> bytes:
    """What the translator writes for an .icd whose 2D drawing was never created."""
    return _to_bytes(ezdxf.new(setup=True))


def _to_bytes(doc) -> bytes:
    path = get_storage_root() / "temp" / f"icd_{uuid.uuid4().hex}.dxf"
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(path)
    payload = path.read_bytes()
    path.unlink()
    return payload


def test_the_entity_count_resolves_blocks():
    """A raw modelspace count reads 1 where the truth is 21.

    This is the check that decides whether a conversion was empty, so counting the INSERT
    rather than its children would classify every real iCAD drawing as empty.
    """
    bootstrap_storage()
    path = get_storage_root() / "temp" / f"icd_count_{uuid.uuid4().hex}.dxf"
    path.write_bytes(_dxf_with_title_block_in_a_block())
    try:
        doc = ezdxf.readfile(path)
        assert len(list(doc.modelspace())) == 1, "fixture should nest its content in a block"
        assert count_drawing_entities(path) == 21
    finally:
        path.unlink(missing_ok=True)


def test_an_empty_conversion_counts_zero():
    bootstrap_storage()
    path = get_storage_root() / "temp" / f"icd_empty_{uuid.uuid4().hex}.dxf"
    path.write_bytes(_empty_dxf())
    try:
        assert count_drawing_entities(path) == 0
    finally:
        path.unlink(missing_ok=True)


def test_icd_is_not_routed_to_the_three_d_pipeline():
    """Guards the routing itself, which is what silently produced a placeholder cube."""
    source = pipeline_module.__file__
    with open(source, encoding="utf-8") as fh:
        text = fh.read()
    three_d_branch = text.split("Initializing 3D pipeline")[0]
    assert '"icd"' not in three_d_branch.split("if drawing.format.lower() in")[-1], (
        "`.icd` is back in the 3D format tuple; its 2D content will never reach dxf_parser"
    )


@pytest.fixture
def harness(monkeypatch):
    """In-memory Beanie doubles, mirroring `tests/test_extraction_replacement.py`."""
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


async def _ingest_icd() -> tuple[DrawingDocument, str]:
    bootstrap_storage()
    upload_path = get_storage_root() / "uploads" / f"icd_{uuid.uuid4().hex}.icd"
    upload_path.write_bytes(b"MOD0\x40\x00\x00\x00placeholder-not-parsed-directly")
    drawing = DrawingDocument(
        file_name="BBLUQ001A.icd",
        file_path=os.path.relpath(upload_path, get_storage_root()),
        file_hash="mock_" + os.urandom(8).hex(),
        file_size_bytes=upload_path.stat().st_size,
        format="icd",
        status="queued",
    )
    await drawing.save()
    return drawing, str(upload_path)


async def _run_with_conversion(monkeypatch, drawing, dxf_payload: bytes) -> ExtractionJob:
    """Drive the pipeline with the translator stubbed out, so no licence is needed."""
    produced: list = []

    async def fake_convert(self, icd_path, dxf_output_dir, validate_sandbox=True):
        dxf_output_dir.mkdir(parents=True, exist_ok=True)
        out = dxf_output_dir / f"{icd_path.stem}.dxf"
        out.write_bytes(dxf_payload)
        produced.append(out)
        return out

    monkeypatch.setattr(
        "services.backend.infrastructure.cad.icd_converter.ICDConverter.convert_icd_to_dxf",
        fake_convert,
    )

    def explode(*args, **kwargs):
        raise AssertionError(
            "an .icd reached ThreeDPipeline, which yields a placeholder cube for it"
        )

    monkeypatch.setattr(pipeline_module.ThreeDPipeline, "parse_and_convert", explode)

    job = ExtractionJob(drawing_id=str(drawing.id), status="queued")
    await job.save()
    await ExtractionPipeline().run(str(drawing.id), str(job.id))
    return await ExtractionJob.get(str(job.id))


@pytest.mark.asyncio
async def test_an_icd_with_2d_content_extracts_through_the_dxf_parser(harness, monkeypatch):
    drawing, upload_path = await _ingest_icd()
    try:
        job = await _run_with_conversion(
            monkeypatch, drawing, _dxf_with_title_block_in_a_block()
        )
        assert job.status == "completed", job.error_message
        assert len(harness["entities"]) > 0, "nothing was extracted from a populated drawing"
    finally:
        if os.path.exists(upload_path):
            os.unlink(upload_path)


@pytest.mark.asyncio
async def test_an_icd_whose_2d_drawing_is_empty_fails_instead_of_ingesting_blank(
    harness, monkeypatch
):
    """The translator reports success for these, so the pipeline is the only thing that can
    stop a blank drawing that compares clean against anything."""
    drawing, upload_path = await _ingest_icd()
    try:
        job = await _run_with_conversion(monkeypatch, drawing, _empty_dxf())
        assert job.status == "failed", (
            "an .icd holding only a 3D model ingested as a valid empty drawing"
        )
        assert "no 2D content" in (job.error_message or "")
        assert harness["entities"] == []
    finally:
        if os.path.exists(upload_path):
            os.unlink(upload_path)
