"""Pairing feedback — the human says the engine matched the wrong entities.

Every pre-existing correction verb judges a finding's *verdict*, *category* or *value*, and all
of them assume the engine compared the right two entities and only got its conclusion wrong.
A finding like "NONE → 260" is usually neither: it is one half of a pair the matcher failed to
make. Nothing could express that until now.

The tests below mostly pin a restraint: these verbs are captured and deliberately left
unlabelled. Both available mappings would teach the verdict head something false, and the
temptation to map them anyway — "it's feedback, feed it to the model" — is exactly what needs a
test standing in front of it.
"""

from types import SimpleNamespace

import pytest

from services.backend.api.schemas import HumanCorrectedStatus
from services.backend.infrastructure.learning.trainer import (
    MATCHER_FEEDBACK,
    VERDICT_ONE,
    VERDICT_ZERO,
    build_bundle,
)


def _doc(status, text="260", category="drawing_views", original_status="ADDED", retracted_at=None):
    return SimpleNamespace(
        retracted_at=retracted_at,
        human_corrected_status=status,
        category=category,
        entity_text=text,
        original_status=original_status,
        corrected_category=None,
        corrected_value=None,
        created_at=None,
        finding_snapshot={"rev_text": text, "ref_text": "", "category": category},
    )


def test_the_new_verbs_are_accepted_by_the_api_schema():
    from typing import get_args

    for verb in MATCHER_FEEDBACK:
        assert verb in get_args(HumanCorrectedStatus), (
            f"{verb} is sent by CorrectionControls.tsx but the request schema rejects it"
        )


def test_pairing_feedback_is_not_a_verdict_label():
    """The restraint. Mapping to 0 would suppress a finding that may be genuine — "260 was
    reported ADDED but it has a counterpart" usually means there IS a change, described
    wrongly. Mapping to 1 would affirm a pairing the human just rejected."""
    assert not (MATCHER_FEEDBACK & VERDICT_ZERO)
    assert not (MATCHER_FEEDBACK & VERDICT_ONE)


@pytest.mark.parametrize("verb", sorted(MATCHER_FEEDBACK))
def test_pairing_feedback_trains_nothing_yet_but_is_counted(verb):
    bundle = build_bundle([_doc(verb)])

    assert bundle["n_total"] == 1, "the correction must still be recorded in the corpus"
    assert bundle["n_verdict"] == 0, (
        f"{verb} became a verdict label. It is a statement about the matcher, and there is no "
        f"matcher head to train until Stage 3."
    )
    assert not bundle["exact_matched"], "a mispairing must not become a suppression override"
    assert not bundle["exact_changed"]


def test_ordinary_verdict_feedback_still_trains():
    """Guards the obvious regression in the other direction: adding the new verbs must not
    stop the existing ones producing labels. At 21 of 40, none can be spared."""
    bundle = build_bundle([_doc("dismissed", text="LEGEND"), _doc("confirmed_change", text="Ø25")])

    assert bundle["n_verdict"] == 2
    assert bundle["exact_matched"] and bundle["exact_changed"]


def test_confirmed_valid_is_label_one():
    """`schemas.py` described this as label 0 while `trainer.py` put it in VERDICT_ONE. The
    prose ("this finding IS valid to report") agreed with the trainer, so the parenthetical was
    the error — corrected, and pinned here so the two cannot drift again."""
    assert "confirmed_valid" in VERDICT_ONE
    assert "confirmed_valid" not in VERDICT_ZERO


# ─── retraction ───────────────────────────────────────────────────────────────────────
#
# A correction clicked by mistake used to be permanent: it was persisted, it had already
# kicked a retrain, and the UI rendered a terminal "Taught: …". Retracting sets a timestamp
# rather than deleting, because this collection is both the training corpus and the record of
# who taught the model what.


def test_a_retracted_correction_trains_nothing():
    """Not even a row in the corpus count. A retracted correction is not a data point that
    happened to be reversed — it is a statement the human withdrew."""
    bundle = build_bundle([_doc("dismissed", text="LEGEND", retracted_at="2026-08-05T10:00:00Z")])

    assert bundle["n_total"] == 0
    assert bundle["n_verdict"] == 0
    assert not bundle["exact_matched"], "a retracted dismissal must not survive as a suppression"


def test_retracting_one_correction_leaves_the_others_training():
    docs = [
        _doc("dismissed", text="LEGEND", retracted_at="2026-08-05T10:00:00Z"),
        _doc("dismissed", text="KEEP-ME"),
        _doc("confirmed_change", text="Ø25"),
    ]
    bundle = build_bundle(docs)

    assert bundle["n_verdict"] == 2
    assert bundle["exact_changed"]
    # The retracted LEGEND is gone; the un-retracted dismissal remains.
    assert len(bundle["exact_matched"]) == 1


def test_a_compensating_record_was_not_the_chosen_design():
    """`confirmed_valid` already exists as "undo of a dismissal", and using it here was the
    obvious cheap option. It is wrong for training: `train_from_feedback` sorts by
    `created_at` so the later record does win the exact-match override, but the classifier
    rows are appended per document — an undone correction would contribute two rows with
    identical features and opposite labels. Retraction removes the row instead."""
    compensating = build_bundle([_doc("dismissed", text="X"), _doc("confirmed_valid", text="X")])
    retracted = build_bundle([_doc("dismissed", text="X", retracted_at="2026-08-05T10:00:00Z")])

    assert compensating["n_verdict"] == 2, "both rows would train, with opposite labels"
    assert retracted["n_verdict"] == 0, "retraction leaves the classifier nothing to learn from"
