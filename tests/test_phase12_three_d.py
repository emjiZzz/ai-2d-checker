import pytest
import json
import uuid
from pathlib import Path
from unittest.mock import MagicMock
from fastapi import HTTPException

from services.backend.domain.models.drawing_document import DrawingDocument
from services.backend.domain.models.extraction_job import ExtractionJob
from services.backend.domain.models.extracted_entity import ExtractedEntity
from services.backend.infrastructure.storage.path_resolver import get_storage_root, bootstrap_storage
from services.backend.infrastructure.cad.three_d_pipeline import ThreeDPipeline
from services.backend.infrastructure.cad.extraction_pipeline import ExtractionPipeline

# Configure Event Loop Scope for Async Testing
pytestmark = pytest.mark.asyncio

@pytest.fixture(scope="module", autouse=True)
def setup_test_env():
    """Bootstrap the sandboxed directories in the storage root."""
    bootstrap_storage()
    yield

@pytest.fixture(autouse=True)
def mock_beanie_docs(monkeypatch):
    """In-memory mock store for Beanie document classes."""
    monkeypatch.setattr(DrawingDocument, "get_pymongo_collection", classmethod(lambda cls: MagicMock()))
    monkeypatch.setattr(ExtractionJob, "get_pymongo_collection", classmethod(lambda cls: MagicMock()))
    monkeypatch.setattr(ExtractedEntity, "get_pymongo_collection", classmethod(lambda cls: MagicMock()))

    mock_drawings = {}
    mock_jobs = {}

    async def mock_save(self):
        if not hasattr(self, "id") or self.id is None:
            self.id = uuid.uuid4().hex
        id_str = str(self.id)
        if isinstance(self, DrawingDocument):
            mock_drawings[id_str] = self
        elif isinstance(self, ExtractionJob):
            mock_jobs[id_str] = self
        return self

    async def mock_get(cls, id):
        id_str = str(id)
        if cls == DrawingDocument:
            return mock_drawings.get(id_str)
        elif cls == ExtractionJob:
            return mock_jobs.get(id_str)
        return None

    class MockFind:
        """`ExtractionPipeline.run` clears a drawing's entities before inserting the new ones,
        so a re-extraction replaces rather than doubles them. Without this the pipeline dies
        before it writes anything and every assertion below passes or fails for the wrong
        reason."""

        async def delete(self):
            class _Result:
                deleted_count = 0

            return _Result()

    async def mock_insert_many(cls, documents, *args, **kwargs):
        return documents

    monkeypatch.setattr(DrawingDocument, "save", mock_save)
    monkeypatch.setattr(ExtractionJob, "save", mock_save)
    monkeypatch.setattr(DrawingDocument, "get", classmethod(mock_get))
    monkeypatch.setattr(ExtractionJob, "get", classmethod(mock_get))
    monkeypatch.setattr(ExtractedEntity, "find", classmethod(lambda cls, *a, **k: MockFind()))
    monkeypatch.setattr(ExtractedEntity, "insert_many", classmethod(mock_insert_many))

@pytest.fixture
def dummy_step_file(tmp_path) -> Path:
    """Creates a dummy STEP CAD file to test parsing."""
    step_path = tmp_path / "bracket_model.step"
    # Basic standard STEP header + advanced face elements
    step_content = (
        "ISO-10303-21;\n"
        "HEADER;\n"
        "FILE_DESCRIPTION(('Mechanical Bracket 3D Model'),'2;1');\n"
        "FILE_NAME('bracket_model.step','2026-05-26',('AI-2D-Checker'),('Eng'),'','','');\n"
        "ENDSEC;\n"
        "DATA;\n"
        "#10 = CLOSED_SHELL('',(#20,#30,#40));\n"
        "#20 = ADVANCED_FACE('',(#21),#22,.T.);\n"
        "#30 = ADVANCED_FACE('',(#31),#32,.T.);\n"
        "#40 = ADVANCED_FACE('',(#41),#42,.T.);\n"
        "ENDSEC;\n"
        "END-ISO-10303-21;\n"
    )
    step_path.write_text(step_content, encoding="utf-8")
    return step_path

async def test_three_d_pipeline_conversion(dummy_step_file):
    """Verify that the 3D pipeline extracts STEP metadata and produces valid glTF."""
    metadata, gltf_content = ThreeDPipeline.parse_and_convert(dummy_step_file)
    
    assert metadata["format"] == "step"
    assert metadata["face_count"] > 0

    # volume_mm3 / surface_area_mm2 are either a real measurement from the geometry
    # kernel or None. They used to be back-filled as `face_count * 1423.5` and
    # `face_count * 312.4` when the kernel returned zero, which turned "we could not
    # measure this" into an engineering figure a user could act on. None is the honest
    # answer; a positive number must mean it was actually measured.
    for key in ("volume_mm3", "surface_area_mm2"):
        value = metadata[key]
        assert value is None or value > 0.0, f"{key} must be a real measurement or None"


    gltf_dict = json.loads(gltf_content)
    assert gltf_dict["asset"]["version"] == "2.0"
    assert len(gltf_dict["buffers"]) == 1
    assert gltf_dict["buffers"][0]["uri"].startswith("data:application/octet-stream;base64,")

async def test_3d_extraction_pipeline_flow(dummy_step_file):
    """Verify that the ExtractionPipeline ingests 3D files and saves them to the temp cache."""
    sandbox_upload = get_storage_root() / "uploads" / "bracket_model.step"
    if sandbox_upload.exists():
        sandbox_upload.unlink()

    # Move dummy to sandbox
    sandbox_upload.write_bytes(dummy_step_file.read_bytes())
    
    relative_path = "uploads/bracket_model.step"
    
    drawing = DrawingDocument(
        file_name="bracket_model.step",
        file_path=relative_path,
        file_hash="mock_hash_step_model_" + uuid.uuid4().hex[:12],
        file_size_bytes=sandbox_upload.stat().st_size,
        format="step",
        status="queued"
    )
    await drawing.save()

    job = ExtractionJob(drawing_id=str(drawing.id), status="queued")
    await job.save()

    pipeline = ExtractionPipeline()
    await pipeline.run(str(drawing.id), str(job.id))

    db_drawing = await DrawingDocument.get(str(drawing.id))
    db_job = await ExtractionJob.get(str(job.id))

    assert db_drawing.status == "completed"
    assert db_drawing.entity_counts["faces"] > 0
    assert db_job.status == "completed"

    # Confirm glTF asset exists in the secure temp storage
    gltf_path = get_storage_root() / "temp" / f"model_{drawing.id}.gltf"
    assert gltf_path.exists()
    
    # Cleanup
    if sandbox_upload.exists():
        sandbox_upload.unlink()
    if gltf_path.exists():
        gltf_path.unlink()


async def test_solidworks_companion_fallback(tmp_path):
    """Verify that if a SolidWorks file has a companion STEP file, the pipeline bypasses COM converter and uses it."""
    sldprt_path = tmp_path / "custom_bracket.sldprt"
    sldprt_path.write_text("dummy sldprt content")

    step_path = tmp_path / "custom_bracket.step"
    step_content = (
        "ISO-10303-21;\n"
        "HEADER;\n"
        "FILE_DESCRIPTION(('Mechanical Bracket 3D Model'),'2;1');\n"
        "FILE_NAME('custom_bracket.step','2026-05-26',('AI-2D-Checker'),('Eng'),'','','');\n"
        "ENDSEC;\n"
        "DATA;\n"
        "#10 = CLOSED_SHELL('',(#20,#30,#40));\n"
        "#20 = ADVANCED_FACE('',(#21),#22,.T.);\n"
        "#30 = ADVANCED_FACE('',(#31),#32,.T.);\n"
        "#40 = ADVANCED_FACE('',(#41),#42,.T.);\n"
        "ENDSEC;\n"
        "END-ISO-10303-21;\n"
    )
    step_path.write_text(step_content, encoding="utf-8")

    # Run the pipeline with the .sldprt file. Since the companion step exists next to it, it should use the step.
    metadata, gltf_content = ThreeDPipeline.parse_and_convert(sldprt_path)

    # It should succeed using the companion step file
    assert metadata["format"] == "step"
    assert metadata["file_name"] == "custom_bracket.step"
    assert metadata["face_count"] > 0
