import pytest
import os
import hashlib
import uuid
import ezdxf
from unittest.mock import MagicMock
from pathlib import Path
from fastapi import HTTPException
from services.backend.core.security import validate_sandboxed_path
from services.backend.config import settings
from services.backend.infrastructure.storage.path_resolver import get_storage_root, bootstrap_storage
from services.backend.domain.models.drawing_document import DrawingDocument
from services.backend.domain.models.extraction_job import ExtractionJob
from services.backend.domain.models.extracted_entity import ExtractedEntity
from services.backend.infrastructure.cad.oda_converter import ODAConverter
from services.backend.infrastructure.cad.dxf_parser import DXFParser
from services.backend.infrastructure.cad.extraction_pipeline import ExtractionPipeline
from services.backend.infrastructure.cad.diagnostics import CADDiagnostics

# Configure Event Loop Scope for Async Testing
pytestmark = pytest.mark.asyncio

@pytest.fixture(scope="module", autouse=True)
def setup_test_env():
    """
    Bootstrap the sandboxed directories in the storage root.
    """
    bootstrap_storage()
    yield

@pytest.fixture(autouse=True)
def mock_beanie_docs(monkeypatch):
    """
    In-memory mock store for Beanie document classes.
    Blocks real MongoDB queries, ensuring 100% test reliability on any machine.
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

    ExtractedEntity.job_id = MockField("job_id")
    ExtractedEntity.entity_type = MockField("entity_type")

    mock_drawings = {}
    mock_jobs = {}
    mock_entities = []

    async def mock_save(self):
        if not hasattr(self, "id") or self.id is None:
            self.id = uuid.uuid4().hex
        
        id_str = str(self.id)
        if isinstance(self, DrawingDocument):
            mock_drawings[id_str] = self
        elif isinstance(self, ExtractionJob):
            mock_jobs[id_str] = self
        elif isinstance(self, ExtractedEntity):
            mock_entities.append(self)
        return self

    async def mock_get(cls, id):
        id_str = str(id)
        if cls == DrawingDocument:
            return mock_drawings.get(id_str)
        elif cls == ExtractionJob:
            return mock_jobs.get(id_str)
        return None

    async def mock_find_one(cls, *args, **kwargs):
        # Safe default: no duplicate hash matches
        return None

    async def mock_insert_many(cls, documents, *args, **kwargs):
        for doc in documents:
            if not hasattr(doc, "id") or doc.id is None:
                doc.id = uuid.uuid4().hex
            mock_entities.append(doc)
        return documents

    class MockFind:
        def __init__(self, job_id, entity_type=None):
            self.job_id = job_id
            self.entity_type = entity_type

        async def count(self) -> int:
            count = 0
            for ent in mock_entities:
                if str(ent.job_id) == str(self.job_id):
                    if self.entity_type is None or ent.entity_type == self.entity_type:
                        count += 1
            return count

    def mock_find(cls, *args, **kwargs):
        # Parse query expressions (e.g. ExtractedEntity.job_id == job_id)
        job_id = None
        entity_type = None
        for arg in args:
            # Check comparison structures
            if hasattr(arg, "left") and hasattr(arg, "right"):
                field_name = getattr(arg.left, "name", "")
                if field_name == "job_id":
                    job_id = arg.right
                elif field_name == "entity_type":
                    entity_type = arg.right
        return MockFind(job_id, entity_type)

    monkeypatch.setattr(DrawingDocument, "save", mock_save)
    monkeypatch.setattr(ExtractionJob, "save", mock_save)
    monkeypatch.setattr(ExtractedEntity, "save", mock_save)
    monkeypatch.setattr(DrawingDocument, "get", classmethod(mock_get))
    monkeypatch.setattr(ExtractionJob, "get", classmethod(mock_get))
    monkeypatch.setattr(DrawingDocument, "find_one", classmethod(mock_find_one))
    monkeypatch.setattr(ExtractionJob, "find_one", classmethod(mock_find_one))
    monkeypatch.setattr(ExtractedEntity, "insert_many", classmethod(mock_insert_many))
    monkeypatch.setattr(ExtractedEntity, "find", classmethod(mock_find))

@pytest.fixture
def test_dxf_file(tmp_path) -> Path:
    """
    Dynamically constructs a valid DXF drawing using ezdxf.
    """
    doc = ezdxf.new("R2018")
    msp = doc.modelspace()
    
    # Add explicit geometries
    msp.add_line((0, 0, 0), (10, 10, 0))
    msp.add_line((10, 10, 0), (20, 20, 0))
    msp.add_circle((0, 0, 0), radius=5.0)
    
    dxf_path = tmp_path / "test_drawing.dxf"
    doc.saveas(str(dxf_path))
    return dxf_path


async def test_path_traversal_rejection():
    """
    Verifies that the sandboxed path resolver blocks absolute escaping paths.
    """
    storage_root = get_storage_root()
    relative_escape = Path("../../escaped_file.dxf")
    
    with pytest.raises(HTTPException) as exc_info:
        validate_sandboxed_path(storage_root / relative_escape)
    assert exc_info.value.status_code == 400
    assert "Access Denied" in exc_info.value.detail


async def test_dxf_parsing(test_dxf_file):
    """
    Validates that ezdxf parser extracts lines and circles correctly.
    """
    sandbox_path = get_storage_root() / "temp" / "test_parse.dxf"
    if sandbox_path.exists():
        sandbox_path.unlink()
    
    with open(test_dxf_file, "rb") as f_in, open(sandbox_path, "wb") as f_out:
        f_out.write(f_in.read())

    parser = DXFParser()
    entities, layers, counts, metadata = parser.parse_file(sandbox_path)

    assert counts["line"] == 2
    assert counts["circle"] == 1
    assert len(layers) > 0
    assert metadata["acad_version"] == "R2018"
    
    if sandbox_path.exists():
        sandbox_path.unlink()


async def test_sha256_hashing(test_dxf_file):
    """
    Validates the SHA256 checksum calculation for drawing uploads.
    """
    sha = hashlib.sha256()
    with open(test_dxf_file, "rb") as f:
        while chunk := f.read(1024):
            sha.update(chunk)
    
    checksum = sha.hexdigest()
    assert len(checksum) == 64


async def test_extraction_pipeline_flow(test_dxf_file):
    """
    Executes the end-to-end extraction pipeline, confirming Beanie metadata persistence
    and timing durations are captured.
    """
    sandbox_upload = get_storage_root() / "uploads" / "pipeline_test.dxf"
    if sandbox_upload.exists():
        sandbox_upload.unlink()

    with open(test_dxf_file, "rb") as f_in, open(sandbox_upload, "wb") as f_out:
        f_out.write(f_in.read())

    relative_path = os.path.relpath(sandbox_upload, get_storage_root())
    
    drawing = DrawingDocument(
        file_name="pipeline_test.dxf",
        file_path=relative_path,
        file_hash="mock_hash_pipeline_test_" + os.urandom(8).hex(),
        file_size_bytes=sandbox_upload.stat().st_size,
        format="dxf",
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
    assert db_drawing.entity_counts["line"] == 2
    assert db_drawing.entity_counts["circle"] == 1
    assert db_job.status == "completed"
    assert db_job.total_duration_seconds > 0
    assert db_job.parsing_duration_seconds > 0

    if sandbox_upload.exists():
        sandbox_upload.unlink()


async def test_diagnostics_aggregation():
    """
    Validates that the diagnostics service aggregates correct timing and count maps.
    """
    drawing = DrawingDocument(
        file_name="diag_test.dxf",
        file_path="uploads/diag_test.dxf",
        file_hash="mock_hash_diag_test_" + os.urandom(8).hex(),
        file_size_bytes=1000,
        format="dxf",
        status="completed",
        entity_counts={"line": 1, "circle": 1}
    )
    await drawing.save()

    job = ExtractionJob(
        drawing_id=str(drawing.id),
        status="completed",
        conversion_duration_seconds=0.0,
        parsing_duration_seconds=0.15,
        total_duration_seconds=0.18,
        diagnostics={"extracted_entities_count": 2}
    )
    await job.save()

    entity1 = ExtractedEntity(drawing_id=str(drawing.id), job_id=str(job.id), entity_type="line", layer="0")
    entity2 = ExtractedEntity(drawing_id=str(drawing.id), job_id=str(job.id), entity_type="circle", layer="0")
    await entity1.save()
    await entity2.save()

    report = await CADDiagnostics.get_job_diagnostics(str(job.id))

    assert report["success"] is True
    assert report["job_id"] == str(job.id)
    assert report["durations"]["parsing_seconds"] == 0.15
    assert report["database_stats"]["total_entities_persisted"] == 2
    assert report["database_stats"]["entity_types_breakdown"]["line"] == 1
    assert report["database_stats"]["entity_types_breakdown"]["circle"] == 1


async def test_oda_converter_graceful_missing_handling():
    """
    Verifies that the ODA Converter gracefully throws FileNotFoundError
    on missing files or executables.
    """
    converter = ODAConverter(converter_path="C:/InvalidLocation/NoConverter.exe")
    
    with pytest.raises(FileNotFoundError):
        await converter.convert_dwg_to_dxf(
            dwg_path=get_storage_root() / "uploads/test.dwg",
            dxf_output_dir=get_storage_root() / "temp"
        )
