import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from services.backend.api.dependencies import get_current_user
from services.backend.api.routers.auth import logout_user, revoke_user_sessions
from services.backend.core.auth import create_session_token
from services.backend.domain.models.user_account import UserAccountDocument
from services.backend.domain.models.user_session import UserSessionDocument

pytestmark = pytest.mark.asyncio


class MockField:
    def __init__(self, name):
        self.name = name

    def __eq__(self, other):
        class Comparison:
            def __init__(self, left, right):
                self.left = left
                self.right = right
        return Comparison(self, other)


@pytest.fixture(autouse=True)
def mock_beanie_docs(monkeypatch):
    monkeypatch.setattr(UserAccountDocument, "get_pymongo_collection", classmethod(lambda cls: MagicMock()))
    monkeypatch.setattr(UserSessionDocument, "get_pymongo_collection", classmethod(lambda cls: MagicMock()))

    UserAccountDocument.username = MockField("username")
    UserSessionDocument.token = MockField("token")
    UserSessionDocument.username = MockField("username")
    UserSessionDocument.active = MockField("active")

    mock_users: dict[str, UserAccountDocument] = {}
    mock_sessions: dict[str, UserSessionDocument] = {}

    async def mock_save(self):
        if not hasattr(self, "id") or self.id is None:
            self.id = uuid.uuid4().hex
        if isinstance(self, UserAccountDocument):
            mock_users[str(self.id)] = self
        elif isinstance(self, UserSessionDocument):
            mock_sessions[str(self.id)] = self
        return self

    def _matches(doc, comparisons):
        for comp in comparisons:
            field_name = getattr(comp.left, "name", None)
            if field_name is None or getattr(doc, field_name) != comp.right:
                return False
        return True

    async def mock_find_one_user(cls, *args, **kwargs):
        for u in mock_users.values():
            if _matches(u, args):
                return u
        return None

    async def mock_find_one_session(cls, *args, **kwargs):
        for s in mock_sessions.values():
            if _matches(s, args):
                return s
        return None

    class MockFind:
        def __init__(self, docs):
            self._docs = docs

        async def to_list(self, *args, **kwargs):
            return self._docs

    def mock_find_sessions(cls, *args, **kwargs):
        return MockFind([s for s in mock_sessions.values() if _matches(s, args)])

    monkeypatch.setattr(UserAccountDocument, "save", mock_save)
    monkeypatch.setattr(UserAccountDocument, "find_one", classmethod(mock_find_one_user))
    monkeypatch.setattr(UserSessionDocument, "save", mock_save)
    monkeypatch.setattr(UserSessionDocument, "find_one", classmethod(mock_find_one_session))
    monkeypatch.setattr(UserSessionDocument, "find", classmethod(mock_find_sessions))

    return {"users": mock_users, "sessions": mock_sessions}


async def _make_user_and_session(store, username="alice", role="user", active=True):
    user = UserAccountDocument(username=username, hashed_password="x", role=role, active=True)
    await user.save()

    token, expires_at = create_session_token({"username": username, "role": role})
    session = UserSessionDocument(
        token=token,
        user_id=str(user.id),
        username=username,
        role=role,
        expires_at=expires_at,
        active=active,
    )
    await session.save()
    return user, session, token


async def test_get_current_user_accepts_active_session(mock_beanie_docs):
    user, session, token = await _make_user_and_session(mock_beanie_docs)
    resolved = await get_current_user(x_session_token=token)
    assert resolved.username == "alice"


async def test_get_current_user_rejects_revoked_session_even_with_valid_signature(mock_beanie_docs):
    """
    Core of this fix: a cryptographically valid, non-expired session token must
    still be rejected once its UserSessionDocument.active flag is False.
    """
    user, session, token = await _make_user_and_session(mock_beanie_docs, active=False)

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(x_session_token=token)

    assert exc_info.value.status_code == 401
    assert "revoked" in exc_info.value.detail.lower()


async def test_get_current_user_rejects_token_with_no_matching_session_record(mock_beanie_docs):
    """A syntactically/cryptographically valid token whose session was never persisted
    (or was hard-deleted) must be rejected, not implicitly trusted."""
    token, _ = create_session_token({"username": "ghost", "role": "user"})

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(x_session_token=token)

    assert exc_info.value.status_code == 401


async def test_logout_deactivates_session_and_is_idempotent(mock_beanie_docs):
    user, session, token = await _make_user_and_session(mock_beanie_docs)

    result = await logout_user(x_session_token=token)
    assert result.success is True
    assert session.active is False

    # Calling logout again on an already-inactive session must not error.
    result2 = await logout_user(x_session_token=token)
    assert result2.success is True
    assert session.active is False


async def test_logout_unknown_token_still_succeeds(mock_beanie_docs):
    result = await logout_user(x_session_token="not-a-real-token")
    assert result.success is True


async def test_revoke_user_sessions_deactivates_all_active_sessions_for_user(mock_beanie_docs):
    user, session1, _ = await _make_user_and_session(mock_beanie_docs, username="bob")
    # A second active session for the same user (e.g. logged in on two machines).
    token2, expires_at2 = create_session_token({"username": "bob", "role": "user"})
    session2 = UserSessionDocument(
        token=token2, user_id=str(user.id), username="bob", role="user",
        expires_at=expires_at2, active=True,
    )
    await session2.save()

    result = await revoke_user_sessions("bob")

    assert result.success is True
    assert session1.active is False
    assert session2.active is False


async def test_revoke_user_sessions_404s_for_unknown_username(mock_beanie_docs):
    with pytest.raises(HTTPException) as exc_info:
        await revoke_user_sessions("nonexistent-user")
    assert exc_info.value.status_code == 404
