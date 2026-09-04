"""Capturing WHICH entity the engine should have paired with — step 2 of the matcher plan.

Measured 2026-08-19: of 106 `mispaired_*` corrections, 3 carried the counterpart. It was an
optional free-text box and was rationally skipped, so 103 rows record a rejection with no
correction — and a matcher cannot be trained on negatives, because there is no target to learn
toward. Those rows are not recoverable. This is the capture changing so the next ones are.

See `docs/vault/01 - Architecture/Matcher Feedback — Making the Parked Corpus Count.md`.
"""

import pytest
from pydantic import ValidationError

from services.backend.api.schemas import AuditFeedbackRequest, CorrectedCounterpart
from services.backend.domain.models.audit_feedback import AuditFeedbackDocument
from services.backend.infrastructure.learning.trainer import (
    MATCHER_FEEDBACK,
    VERDICT_ONE,
    VERDICT_ZERO,
)


def _request(**over):
    return AuditFeedbackRequest(
        session_id="s1",
        drawing_id="d1",
        entity_text="60",
        category="drawing_views",
        original_status="REMOVED",
        human_corrected_status="mispaired_missing_counterpart",
        **over,
    )


# ── the shape ────────────────────────────────────────────────────────────────────────


def test_a_counterpart_carries_side_handle_text_and_coordinate():
    c = CorrectedCounterpart(side="rev", handle="1B2A", text="60", coordinates=[1.0, 2.0])
    assert c.model_dump() == {
        "side": "rev",
        "handle": "1B2A",
        "text": "60",
        "coordinates": [1.0, 2.0],
    }


def test_a_counterpart_without_a_handle_is_valid():
    """Block-exploded content carries no handle, and that is the NORMAL case on a reference
    sheet — 0.8–13% coverage measured over three pairs. Requiring one would refuse the counterpart
    for most of the side where REMOVED findings live, which is most of what gets mispaired."""
    c = CorrectedCounterpart(side="ref", text="60", coordinates=[1.0, 2.0])
    assert c.handle is None
    assert c.text == "60"


def test_the_side_is_constrained_to_the_two_that_exist():
    # A free string would let 'reference' and 'ref' both appear and be counted as different
    # sides, which no consumer would notice until the counts disagreed.
    with pytest.raises(ValidationError):
        CorrectedCounterpart(side="reference", text="60")


def test_it_is_a_fixed_shape_not_a_bare_dict():
    # The reasoning behind CLAUDE.md constraint 1, one layer down: an open-ended object lets
    # every client invent its own key names, and nothing fails until a trainer reads them.
    assert set(CorrectedCounterpart.model_fields) == {"side", "handle", "text", "coordinates"}


# ── it is optional, and absence means "not recorded" ─────────────────────────────────


def test_a_correction_without_a_counterpart_is_still_valid():
    """The 249 rows written before this field stay valid and unmigrated. A required field here
    would have made every one of them unreadable."""
    assert _request().corrected_counterpart is None


def test_the_document_defaults_it_to_none():
    assert AuditFeedbackDocument.model_fields["corrected_counterpart"].default is None


def test_a_correction_with_a_counterpart_round_trips():
    req = _request(
        corrected_counterpart=CorrectedCounterpart(side="ref", handle="9F", text="60")
    )
    assert req.corrected_counterpart.side == "ref"
    assert req.corrected_counterpart.handle == "9F"


# ── the verbs are untouched ──────────────────────────────────────────────────────────


def test_the_mispaired_verbs_still_train_nothing():
    """Step 2 changes what is CAPTURED and nothing about what is learned.

    `trainer.py` maps neither verb to a verdict label, and the restraint stays correct until
    there are positives: label 0 would suppress a finding that may be genuine, label 1 would
    affirm a pairing the human just rejected. Turning that on is Stage 3's decision, made from
    evidence, not a side effect of adding a field.
    """
    assert MATCHER_FEEDBACK == {"mispaired_missing_counterpart", "mispaired_wrong_match"}
    assert not (MATCHER_FEEDBACK & VERDICT_ZERO)
    assert not (MATCHER_FEEDBACK & VERDICT_ONE)
