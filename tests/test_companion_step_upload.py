import io
import uuid
import pytest
from pathlib import Path
from unittest.mock import MagicMock
from fastapi import UploadFile

from services.backend.domain.models.drawing_document import DrawingDocument
from services.backend.domain.models.extraction_job import ExtractionJob
from services.backend.domain.models.extracted_entity import ExtractedEntity
from services.backend.infrastructure.storage.path_resolver import get_storage_root, bootstrap_storage
from services.backend.infrastructure.ingestion.drawing_ingestion_service import DrawingIngestionService
from services.backend.infrastructure.cad.extraction_pipeline import ExtractionPipeline

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module", autouse=True)
def setup_test_env():
    bootstrap_storage()
    yield


@pytest.fixture(autouse=True)
def mock_beanie_docs(monkeypatch):
    monkeypatch.setattr(DrawingDocument, "get_pymongo_collection", classmethod(lambda cls: MagicMock()))
    monkeypatch.setattr(ExtractionJob, "get_pymongo_collection", classmethod(lambda cls: MagicMock()))
    monkeypatch.setattr(ExtractedEntity, "get_pymongo_collection", classmethod(lambda cls: MagicMock()))

    async def mock_save(self):
        if not hasattr(self, "id") or self.id is None:
            self.id = uuid.uuid4().hex
        return self

    monkeypatch.setattr(DrawingDocument, "save", mock_save)
    monkeypatch.setattr(ExtractionJob, "save", mock_save)


async def test_companion_step_file_persisted(monkeypatch):
    """Verifies that when an upload includes a companion STEP file, it is persisted beside the drawing."""
    dxf_content = b"0\nSECTION\n2\nHEADER\n0\nENDSEC\n0\nEOF\n"
    dxf_file = UploadFile(filename="bracket.dxf", file=io.BytesIO(dxf_content))

    step_content = b"ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n"
    step_file = UploadFile(filename="bracket.stp", file=io.BytesIO(step_content))

    drawing, job, _ = await DrawingIngestionService.process_ingestion(
        file=dxf_file,
        companion_step=step_file,
        uploaded_by="test_engineer"
    )

    assert drawing.format == "dxf"
    drawing_file_path = get_storage_root() / drawing.file_path
    assert drawing_file_path.exists()

    companion_path = drawing_file_path.with_suffix(".stp")
    assert companion_path.exists()
    assert companion_path.read_bytes() == step_content
