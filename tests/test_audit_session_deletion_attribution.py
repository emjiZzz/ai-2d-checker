import uuid
from unittest.mock import MagicMock

import pytest

from services.backend.api.routers.audits import delete_audit_session
from services.backend.core.auth import create_session_token
from services.backend.domain.models.audit_session import AuditSession
from services.backend.infrastructure.audit.comparison.cache_manager import ComparisonCacheManager

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def mock_beanie_docs(monkeypatch):
    monkeypatch.setattr(AuditSession, "get_pymongo_collection", classmethod(lambda cls: MagicMock()))
    monkeypatch.setattr(ComparisonCacheManager, "clear_cache_for_drawing", classmethod(lambda cls, drawing_id: None))

    mock_sessions: dict[str, AuditSession] = {}

    async def mock_save(self):
        if not hasattr(self, "id") or self.id is None:
            self.id = uuid.uuid4().hex
        mock_sessions[str(self.id)] = self
        return self

    async def mock_get(cls, id):
        return mock_sessions.get(str(id))

    monkeypatch.setattr(AuditSession, "save", mock_save)
    monkeypatch.setattr(AuditSession, "get", classmethod(mock_get))

    return mock_sessions


async def test_delete_audit_session_attributes_deleter_from_session_token(mock_beanie_docs):
    """
    Confirmed bug (not from this session's own refactor, flagged as a known-but-unverified
    gap in docs/security-remediation-implementation-plan.md, Phase A's completion log,
    item 3): delete_audit_session verified the API *bearer* token (Depends(get_auth_token))
    against verify_session_token(), which expects the per-user X-Session-Token header
    instead — a plain bearer secret is never a valid HMAC session token, so verification
    always threw, was silently swallowed by `except Exception: pass`, and `deleted_by`
    was permanently None regardless of who was logged in.

    This test proves the fix: with a real X-Session-Token supplied (as FastAPI would
    extract it from the header), deleted_by is correctly attributed.
    """
    session = AuditSession(drawing_id="dwg-1", status="completed")
    await session.save()

    session_token, _ = create_session_token({"username": "alice", "role": "admin"})

    result = await delete_audit_session(
        id=str(session.id),
        token="opaque-api-bearer-secret",  # never a valid session token; must NOT be used for attribution
        x_session_token=session_token,
    )

    assert result.success is True
    stored = await AuditSession.get(session.id)
    assert stored.deleted_by == "alice"
    assert stored.is_deleted is True


async def test_delete_audit_session_leaves_deleted_by_none_without_session_token(mock_beanie_docs):
    """
    No X-Session-Token supplied at all (e.g. an old/non-browser client) must still
    soft-delete successfully, just with no attribution — fails safe, not fails closed.
    """
    session = AuditSession(drawing_id="dwg-2", status="completed")
    await session.save()

    result = await delete_audit_session(
        id=str(session.id),
        token="opaque-api-bearer-secret",
        x_session_token=None,
    )

    assert result.success is True
    stored = await AuditSession.get(session.id)
    assert stored.deleted_by is None
    assert stored.is_deleted is True
