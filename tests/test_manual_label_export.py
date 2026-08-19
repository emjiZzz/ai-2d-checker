"""The bridge from a manual engineer check to an eval-corpus label.

The app and the corpus speak different dialects of the same idea, and the interesting cases are
all at the seam. No database and no corpus on disk: `build_draft` is pure so the mapping is
checkable directly, which is the whole reason it takes its entities as arguments.

What is at stake if this is wrong is not a crash. A mis-addressed label still SCORES — against
an entity nobody looked at — so it silently corrupts the recall figure that Stage 0b exists to
produce, and does so in a direction no one can see from the outside.
"""

from tools.export_manual_labels import build_draft


def _entity(text: str) -> dict:
    return {"entity_type": "text", "properties": {"text": text}, "handle": None}


def _marking(**over) -> dict:
    return {
        "status": "CHANGED",
        "category": "drawing_views",
        "ref_text": "60",
        "rev_text": "70",
        "notes": "",
        "is_bulk": False,
        "retracted_at": None,
        "ref_handle": "1B2A",
        "rev_handle": "2C3D",
        **over,
    }


def _draft(markings, ref=None, rev=None):
    return build_draft(
        markings,
        pair_id="M7452A1N01",
        annotator="imrysn",
        ref_entities=ref or [],
        rev_entities=rev or [],
    )


# ── the address, which is what the scorer matches on ─────────────────────────────────


def test_a_changed_anchors_on_the_revision():
    draft, skipped = _draft([_marking()])
    assert skipped == []
    assert draft["findings"][0]["entity_handle"] == "REV-2C3D"


def test_a_removed_anchors_on_the_reference():
    """A removal exists on the reference and nowhere else — the same rule as
    `ExpectedFinding.default_side`, applied here because the side decides which handle to read."""
    draft, _ = _draft([_marking(status="REMOVED")])
    assert draft["findings"][0]["entity_handle"] == "REF-1B2A"


def test_a_missing_handle_falls_back_to_a_unique_payload_index():
    """Block-exploded content carries no handle, and that is the NORMAL case on a reference
    sheet — 0.8–13% coverage measured over three pairs. Without this fallback almost every
    REMOVED would be unexportable, which is the half of the corpus recall depends on."""
    ref = [_entity("other"), _entity("60"), _entity("more")]
    draft, skipped = _draft([_marking(status="REMOVED", ref_handle=None)], ref=ref)
    assert skipped == []
    assert draft["findings"][0]["entity_handle"] == "REF#1"


def test_an_ambiguous_text_is_refused_rather_than_guessed():
    """Two entities read `60`; nothing here can say which one the engineer meant.

    A wrong address is worse than a missing one: it scores against an entity nobody looked at,
    and the resulting recall figure is wrong with no symptom.
    """
    ref = [_entity("60"), _entity("60")]
    draft, skipped = _draft([_marking(status="REMOVED", ref_handle=None)], ref=ref)
    assert draft["findings"] == []
    assert len(skipped) == 1
    assert "no unique text match" in skipped[0]


def test_an_unaddressable_marking_is_reported_not_dropped():
    # Silence here would mean an engineer's judgement vanishing between the app and the corpus,
    # which is the exact failure this whole tool exists to end.
    _, skipped = _draft([_marking(status="ADDED", rev_handle=None)])
    assert len(skipped) == 1


# ── the two vocabularies ─────────────────────────────────────────────────────────────


def test_matched_becomes_a_non_finding_with_its_reason():
    """The corpus has no MATCHED. Dropping it would lose real signal: the guideline asks for
    'deliberately not labelled, and why' precisely so a later false positive on that entity is
    attributable to a decision rather than to an oversight."""
    draft, skipped = _draft([_marking(status="MATCHED")])
    assert skipped == []
    assert draft["findings"] == []
    assert draft["not_findings"][0]["entity_handle"] == "REV-2C3D"
    assert "equivalent" in draft["not_findings"][0]["reason"]


def test_not_a_finding_becomes_a_non_finding_with_a_different_reason():
    # Both are non-findings and they are not the same statement: MATCHED says the sides agree,
    # NOT_A_FINDING says they differ and it does not matter. The reason keeps them apart.
    draft, _ = _draft([_marking(status="NOT_A_FINDING")])
    reason = draft["not_findings"][0]["reason"]
    assert "not a finding" in reason


def test_the_three_corpus_statuses_pass_through():
    draft, skipped = _draft(
        [_marking(status=s) for s in ("CHANGED", "ADDED", "REMOVED")]
    )
    assert skipped == []
    assert sorted(f["status"] for f in draft["findings"]) == ["ADDED", "CHANGED", "REMOVED"]


def test_a_retracted_marking_is_not_exported():
    # Retraction is the engineer withdrawing a judgement. Exporting it would put a statement
    # into the corpus that its author had taken back.
    draft, skipped = _draft([_marking(retracted_at="2026-08-18T00:00:00Z")])
    assert draft["findings"] == []
    assert skipped == []


# ── the envelope ─────────────────────────────────────────────────────────────────────


def test_the_draft_is_stamped_with_the_current_guideline():
    """`PairLabels.from_dict` refuses labels authored under an older guideline, and it is right
    to: mixing two definitions of 'one finding' corrupts every metric derived from the corpus.
    A draft written under the current one installs; a hand-edited stale one will not."""
    from services.backend.infrastructure.eval.corpus import GUIDELINE_VERSION

    draft, _ = _draft([_marking()])
    assert draft["guideline_version"] == GUIDELINE_VERSION
    assert draft["annotator"] == "imrysn"
    assert draft["pair_id"] == "M7452A1N01"


def test_bulk_and_texts_survive_the_crossing():
    # `is_bulk` is reported separately by the scorer, and the two texts are what a human reads
    # when re-adjudicating a disagreement. Losing any of them silently weakens the row.
    draft, _ = _draft([_marking(is_bulk=True, notes="checked against the ISO copy")])
    finding = draft["findings"][0]
    assert finding["is_bulk"] is True
    assert finding["ref_text"] == "60"
    assert finding["rev_text"] == "70"
    assert finding["notes"] == "checked against the ISO copy"


def test_the_draft_validates_against_the_real_schema():
    """The end-to-end guarantee: what this writes is what `eval_corpus label` accepts.

    Asserting on the dict shape alone would pass while `PairLabels.from_dict` rejected the file
    — and the failure would surface at install time, after the engineer thought they were done.
    """
    from services.backend.infrastructure.eval.corpus import PairLabels

    draft, _ = _draft(
        [
            _marking(status="CHANGED"),
            _marking(status="ADDED"),
            _marking(status="REMOVED"),
            _marking(status="MATCHED"),
        ]
    )
    labels = PairLabels.from_dict(draft)
    assert len(labels.findings) == 3
    assert len(labels.not_findings) == 1
