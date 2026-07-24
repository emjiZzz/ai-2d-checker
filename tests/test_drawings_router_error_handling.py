import pytest
from fastapi import HTTPException, UploadFile

from services.backend.api.routers.drawings import upload_drawing
from services.backend.domain.services.drawing_ingestion_service import DrawingIngestionService

pytestmark = pytest.mark.asyncio


class _FakeUploadFile:
    """Minimal stand-in for FastAPI's UploadFile; process_ingestion is mocked below
    so this never actually needs to be read."""

    def __init__(self, filename: str):
        self.filename = filename


async def test_unexpected_service_error_becomes_structured_500_with_correlation_id(monkeypatch):
    """
    Audit finding #7 (docs/refactoring-audit-2026-07-23.md): before this fix, upload_drawing()
    had no try/except around DrawingIngestionService.process_ingestion(), so any unexpected
    exception raised inside the service layer (such as the Finding #1 ValidationError, before it
    was fixed in Phase A) propagated as a raw, unhandled 500 with no correlation ID — inconsistent
    with every other error path in this router.

    This test forces process_ingestion() to raise a generic, unexpected exception and asserts the
    router now degrades it to a structured HTTPException(500) referencing a correlation ID, instead
    of letting the raw exception (and its message) escape uncaught.
    """
    async def boom(cls, file):
        raise RuntimeError("simulated unexpected service-layer failure")

    monkeypatch.setattr(DrawingIngestionService, "process_ingestion", classmethod(boom))

    with pytest.raises(HTTPException) as exc_info:
        await upload_drawing(file=_FakeUploadFile("bracket.dxf"))

    assert exc_info.value.status_code == 500
    assert "Reference:" in exc_info.value.detail
    assert "simulated unexpected service-layer failure" not in exc_info.value.detail


async def test_http_exception_from_service_passes_through_unchanged(monkeypatch):
    """
    Deliberate HTTPExceptions raised by the service layer (e.g. unsupported file format,
    file-too-large) must pass through the router's new try/except unchanged, not get
    rewrapped into a generic 500.
    """
    async def raise_400(cls, file):
        raise HTTPException(status_code=400, detail="Unsupported file format.")

    monkeypatch.setattr(DrawingIngestionService, "process_ingestion", classmethod(raise_400))

    with pytest.raises(HTTPException) as exc_info:
        await upload_drawing(file=_FakeUploadFile("bracket.xyz"))

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Unsupported file format."
