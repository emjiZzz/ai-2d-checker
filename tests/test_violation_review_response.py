"""The supervisor review endpoint must tell a client REJECTED apart from never-reviewed.

**Why this file exists.** `AuditViolation` carries two fields that look redundant and are not:

    is_resolved:     bool          False for "nobody looked" AND for "a human rejected it"
    resolution_type: str | None    None | APPROVED | REJECTED

`AuditViolationResponse` shipped without `resolution_type`, so both API responses collapsed those
three states into two. A rejected finding serialized identically to an unreviewed one, which means
a review queue filtered on what the client can see would show every rejected finding forever — the
queue never empties, and the reviewer's work appears not to have happened.

The failure mode that makes this worth a test rather than a code comment: `resolution_type` has a
default of `None` on the response model, so a construction site that simply **forgets to pass it**
raises nothing, fails no type check, and returns a well-formed response asserting the violation is
unreviewed. There are two such construction sites. Both are covered below, and both assertions
were verified to fail before the field was threaded through.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from services.backend.api.routers import audits
from services.backend.api.schemas import AuditViolationResponse
from services.backend.domain.models.audit_violation import (
    RESOLUTION_APPROVED,
    RESOLUTION_REJECTED,
    AuditViolation,
)

pytestmark = pytest.mark.asyncio


def _violation(vid: str, resolution: str | None = None, remarks: str = "") -> AuditViolation:
    violation = AuditViolation.model_construct(
        audit_session_id="session-1",
        severity="high",
        category="comparison_notes_section",
        description="[CHANGED] 板厚 12 -> 14",
        recommendation="Resolve discrepancy against the reference drawing.",
        source="physical_comparison",
        affected_entities=[],
        confidence=0.95,
        coordinates=None,
        standard_reference=None,
        pen_type="ai_red",
        resolution_type=resolution,
        is_resolved=resolution == RESOLUTION_APPROVED,
        resolved_at=datetime.now(UTC) if resolution else None,
        checker_remarks=remarks,
        created_at=datetime.now(UTC),
    )
    violation.id = vid
    return violation


@pytest.fixture
def offline_review(monkeypatch):
    """Run `review_violation` with no database and no index rebuild.

    Returns the violation the endpoint will load, so a test can inspect what was persisted on it
    as well as what came back over the wire.
    """
    violation = _violation("v1")

    async def fake_get_or_404(_model, _id, _msg):
        return violation

    async def fake_save(self):
        return self

    async def fake_rebuild():
        return None

    monkeypatch.setattr(audits, "get_or_404", fake_get_or_404)
    monkeypatch.setattr(AuditViolation, "save", fake_save, raising=False)
    monkeypatch.setattr(audits, "rebuild_lessons_index", fake_rebuild)
    return violation


async def test_rejecting_a_finding_is_visible_as_rejected_not_as_unreviewed(offline_review):
    """The whole point. `is_valid=False` must come back as REJECTED, not as a null verdict."""
    response = await audits.review_violation(
        "v1", audits.ViolationReviewRequest(is_valid=False, remarks="stale label, not a change")
    )

    assert response.data.resolution_type == RESOLUTION_REJECTED, (
        "A rejected violation came back with resolution_type "
        f"{response.data.resolution_type!r}. A client cannot distinguish that from a violation "
        "nobody has reviewed, so it stays in the review queue permanently."
    )
    # is_resolved alone is exactly the ambiguity this field exists to remove: it reads False here
    # and it also reads False for an untouched violation.
    assert response.data.is_resolved is False
    assert response.data.checker_remarks == "stale label, not a change"


async def test_approving_a_finding_is_visible_as_approved(offline_review):
    response = await audits.review_violation(
        "v1", audits.ViolationReviewRequest(is_valid=True, remarks="")
    )

    assert response.data.resolution_type == RESOLUTION_APPROVED
    assert response.data.is_resolved is True


async def test_the_listing_endpoint_reports_each_violations_verdict(monkeypatch):
    """The second construction site. Listing is where a review queue actually reads from."""
    stored = [
        _violation("v-none", None),
        _violation("v-ok", RESOLUTION_APPROVED, "confirmed against the revision"),
        _violation("v-no", RESOLUTION_REJECTED, "false positive"),
    ]

    class MockQuery:
        async def to_list(self):
            return stored

    # `AuditViolation.audit_session_id` at class level is a Beanie field accessor that only exists
    # after `init_beanie`, so building the query raises AttributeError offline. Same shim as
    # test_lessons_index_write_path.py; raising=False so monkeypatch removes it on teardown rather
    # than leaking the stub onto the class.
    class MockField:  # noqa: PLW1641 — __eq__ builds a query object; never hashed
        def __eq__(self, other):
            return ("audit_session_id", other)

    monkeypatch.setattr(AuditViolation, "audit_session_id", MockField(), raising=False)
    monkeypatch.setattr(
        AuditViolation, "find", classmethod(lambda cls, *a, **k: MockQuery()), raising=False
    )

    response = await audits.get_session_violations("session-1")
    verdicts = {v.id: v.resolution_type for v in response.data}

    assert verdicts == {
        "v-none": None,
        "v-ok": RESOLUTION_APPROVED,
        "v-no": RESOLUTION_REJECTED,
    }, (
        "The listing endpoint flattened the three review states. A queue built on this response "
        "cannot tell a reviewed-and-rejected finding from one that has never been looked at."
    )


def test_the_response_model_keeps_the_verdict_field():
    """Guards the field itself: removing it would make both tests above pass vacuously via the
    default, since Pydantic drops unknown kwargs only in strict mode and `None` is the default."""
    assert "resolution_type" in AuditViolationResponse.model_fields, (
        "AuditViolationResponse lost `resolution_type`. Without it, REJECTED and unreviewed are "
        "the same value on the wire."
    )
