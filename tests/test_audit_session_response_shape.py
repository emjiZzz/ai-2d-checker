"""`AuditSessionResponse` requires `created_at`, and every construction site must supply it.

Found by running the app, not by reading it. `GET /api/v1/audits/sessions` returned
`500 INTERNAL_SERVER_ERROR` on committed code:

    1 validation error for AuditSessionResponse
    created_at
      Field required [type=missing, ...]

The field is declared required on the response model, `AuditSession` has always had it, and not
one of the four construction sites passed it — so every endpoint returning a session 500'd. That
includes the session list the desktop app calls on load, which is why nothing downstream of it
could be reached.

The class of bug is worth naming, because a type checker does not catch it and neither did the
suite: a Pydantic model with a required field and no default fails at *construction* time, in a
router, at runtime. Adding a required field to a response model is a change to every place that
builds one, and nothing in this repo made that connection visible.

These tests construct each endpoint's response from a real model instance, which is the only thing
that exercises the validation. Verified to fail against the pre-fix code with exactly the error
above.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from services.backend.api.routers import audits
from services.backend.api.schemas import AuditSessionResponse
from services.backend.domain.models.audit_session import AuditSession



def _session(sid: str = "s1", deleted: bool = False) -> AuditSession:
    session = AuditSession.model_construct(
        drawing_id="d1",
        reference_drawing_id=None,
        standard_id=None,
        client_name="KMTI",
        status="completed",
        compliance_score=91.0,
        confidence_score=0.9,
        timings={},
        diagnostics={},
        created_at=datetime.now(UTC),
        started_at=None,
        completed_at=None,
        username="admin",
        is_deleted=deleted,
        deleted_at=None,
        deleted_by=None,
        is_restored=False,
    )
    session.id = sid
    return session


def test_the_response_model_still_requires_created_at():
    """If this ever gains a default the tests below stop meaning anything — they would pass
    vacuously on a `None`. Assert the requirement itself, so weakening it is a deliberate act."""
    with pytest.raises(ValidationError):
        AuditSessionResponse(
            id="s1", drawing_id="d1", status="completed", timings={}, diagnostics={}
        )


@pytest.mark.asyncio
async def test_listing_sessions_builds_a_valid_response(monkeypatch):
    """The endpoint the desktop app calls on load. This 500'd on committed code."""
    stored = [_session("s1"), _session("s2")]

    class MockQuery:
        async def to_list(self):
            return stored

    class MockField:  # noqa: PLW1641 — __eq__/__ne__ build query objects; never hashed
        def __ne__(self, other):
            return ("is_deleted", other)

        def __eq__(self, other):
            return ("is_deleted", other)

    monkeypatch.setattr(AuditSession, "is_deleted", MockField(), raising=False)
    monkeypatch.setattr(AuditSession, "find", classmethod(lambda cls, *a, **k: MockQuery()))

    response = await audits.list_audit_sessions()

    assert [s.id for s in response.data] == ["s1", "s2"]
    assert all(s.created_at is not None for s in response.data)


@pytest.mark.asyncio
async def test_listing_the_trash_builds_a_valid_response(monkeypatch):
    stored = [_session("s3", deleted=True)]

    class MockQuery:
        async def to_list(self):
            return stored

    class MockField:  # noqa: PLW1641
        def __eq__(self, other):
            return ("is_deleted", other)

    monkeypatch.setattr(AuditSession, "is_deleted", MockField(), raising=False)
    monkeypatch.setattr(AuditSession, "find", classmethod(lambda cls, *a, **k: MockQuery()))

    response = await audits.list_trash_sessions()

    assert response.data[0].id == "s3"
    assert response.data[0].created_at is not None


def test_every_construction_site_passes_created_at():
    """A source check, because the two endpoints above cover two of four sites and the other two
    (`launch_audit`, `update_session`) need a database and a queue to reach. The count is the
    property: if someone adds a fifth site without the field, that endpoint 500s at runtime and
    this fails at review time instead.
    """
    import inspect

    source = inspect.getsource(audits)
    built = source.count("AuditSessionResponse(")
    supplied = source.count("created_at=session.created_at") + source.count("created_at=s.created_at")

    assert built == supplied, (
        f"{built} AuditSessionResponse construction sites but only {supplied} pass `created_at`. "
        "The field is required with no default, so the shortfall is a 500 at runtime."
    )
