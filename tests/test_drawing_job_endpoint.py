from datetime import datetime
import pytest
from unittest.mock import MagicMock
from beanie import PydanticObjectId
from httpx import AsyncClient, ASGITransport

from services.backend.main import app
from services.backend.api.dependencies import get_auth_token
from services.backend.domain.models.drawing_document import DrawingDocument
from services.backend.domain.models.extraction_job import ExtractionJob


@pytest.mark.asyncio
async def test_get_drawing_job_returns_latest_job(monkeypatch):
    """GET /api/v1/drawings/{id}/job retrieves the latest extraction job for a drawing."""
    monkeypatch.setattr(DrawingDocument, "get_pymongo_collection", classmethod(lambda cls: MagicMock()))
    monkeypatch.setattr(ExtractionJob, "get_pymongo_collection", classmethod(lambda cls: MagicMock()))

    app.dependency_overrides[get_auth_token] = lambda: "test-token"

    mock_drawings = {}
    mock_jobs = []

    drawing_id = PydanticObjectId()
    job_id = PydanticObjectId()

    drawing = DrawingDocument(
        id=drawing_id,
        file_name="test.dxf",
        file_path="uploads/test.dxf",
        file_hash="hash",
        file_size_bytes=1024,
        format="dxf",
        status="processing",
    )
    mock_drawings[str(drawing_id)] = drawing

    job = ExtractionJob(
        id=job_id,
        drawing_id=str(drawing_id),
        status="processing",
        created_at=datetime.utcnow(),
    )
    mock_jobs.append(job)

    async def mock_get(cls, id):
        return mock_drawings.get(str(id))

    monkeypatch.setattr(DrawingDocument, "get", classmethod(mock_get))

    class MockFind:
        def __init__(self, query=None):
            pass

        def sort(self, *args, **kwargs):
            return self

        async def first_or_none(self):
            return mock_jobs[-1] if mock_jobs else None

    monkeypatch.setattr(ExtractionJob, "find", classmethod(lambda cls, *args, **kwargs: MockFind()))

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://localhost:8080") as client:
            res = await client.get(
                f"/api/v1/drawings/{drawing_id}/job",
                headers={"Authorization": "Bearer test-token"}
            )
            assert res.status_code == 200
            payload = res.json()
            assert payload["success"] is True
            assert payload["data"]["id"] == str(job_id)
            assert payload["data"]["status"] == "processing"
            assert payload["data"]["drawing_id"] == str(drawing_id)
    finally:
        app.dependency_overrides.pop(get_auth_token, None)
