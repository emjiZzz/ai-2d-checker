"""Stage 0d — the scorer.

The scorer is itself a differ, and the staged plan names that as a risk: a bug here does not
fail a build, it produces a precision or recall number that is wrong in a specific direction
and gets believed. Two real bugs were caught by hand-auditing its output on two pairs, and
both are pinned below.

`test_bom_row_reported_cell_by_cell_counts_as_over_reporting` is the one to read first — it
encodes a *guideline* decision (one edited BOM row is one finding) as a scoring rule, so a
future change that quietly forgives cell-level over-reporting has to argue with a test.
"""

import pytest

from services.backend.infrastructure.eval.corpus import (
    GUIDELINE_VERSION,
    CorpusPair,
    ExpectedFinding,
    PairLabels,
    PairSide,
)
from services.backend.infrastructure.eval.scorer import (
    CorpusScore,
    Prediction,
    format_report,
    score_pair,
)
from services.backend.infrastructure.eval.serialize import EvalEntity


def _entity(handle, text, x=0.0, y=0.0):
    return EvalEntity(
        entity_type="text",
        layer="0",
        handle=handle,
        properties={"text": text, "handle": handle},
        geometry={"insert": [float(x), float(y)]},
    )


def _side():
    return PairSide(
        drawing_id="D",
        file_name="a.dxf",
        file_hash="H",
        drawing_sha256="",
        entities_sha256="",
        entity_count=0,
    )


def _pair(findings, pair_id="P", provenance="mutation"):
    return CorpusPair(
        pair_id=pair_id,
        provenance=provenance,
        held_out=False,
        label_state="labelled",
        ref=_side(),
        rev=_side(),
        labels=PairLabels(
            pair_id=pair_id,
            guideline_version=GUIDELINE_VERSION,
            annotator="test",
            annotated_at="2026-08-05",
            findings=findings,
        ),
    )


def _prediction(category, status, text, handle=None, old="", coords=None):
    return Prediction(
        category=category,
        status=status,
        handle=handle,
        new_text=text,
        old_text=old,
        coordinates=coords,
    )


# ─── the two bugs the hand-audit caught ───────────────────────────────────────────────


def test_category_is_a_preference_not_a_filter_when_matching():
    """Expected `bill_of_materials` cell `a` must not match a `drawing_views` prediction
    `Ａ` while the genuine BOM prediction sits unmatched.

    `Ａ` is fullwidth and NFKC-folds to `a`. Ignoring category entirely let short strings
    collide across the sheet; the first audited pair got both precision and recall wrong,
    in opposite directions, on one pair.
    """
    expected = ExpectedFinding(
        "REV#0", "bill_of_materials", "CHANGED", ref_text="a", rev_text="aB"
    )
    pair = _pair([expected])
    predictions = [
        _prediction("drawing_views", "ADDED", "Ａ", handle="REV-278"),
        _prediction("bill_of_materials", "REMOVED", "a"),
    ]
    score = score_pair(pair, predictions, [], [_entity(None, "aB")])

    assert len(score.matches) == 1
    match = score.matches[0]
    assert match.prediction.category == "bill_of_materials", (
        "the same-category candidate must win over a cross-category text collision"
    )
    assert not match.status_agrees  # CHANGED reported as REMOVED: a downgrade
    assert [p.category for p in score.spurious] == ["drawing_views"]


def test_a_category_error_is_still_a_match_not_a_miss():
    """The other extreme. Requiring category equality would count one category error as a
    miss *and* a false positive, double-charging it and hiding attribution entirely."""
    expected = ExpectedFinding(
        "REV#0", "notes_section", "CHANGED", ref_text="注記", rev_text="注記2"
    )
    pair = _pair([expected])
    predictions = [_prediction("title_block", "CHANGED", "注記2", old="注記")]
    score = score_pair(pair, predictions, [], [_entity(None, "注記2")])

    assert len(score.matches) == 1
    assert not score.matches[0].category_agrees
    assert score.missed == [] and score.spurious == []

    corpus = CorpusScore([score])
    assert corpus.counts()["tp"] == 1
    assert corpus.category_attribution()["accuracy"] == 0.0


def test_duplicates_require_the_same_handle_or_text_not_mere_proximity():
    """Proximity-based duplicate detection made the duplicate/spurious split depend on
    whether a candidate happened to carry coordinates — BOM findings mostly do not."""
    expected = ExpectedFinding(
        "REV#0", "drawing_views", "CHANGED", ref_text="120", rev_text="125"
    )
    pair = _pair([expected])
    predictions = [
        _prediction("drawing_views", "CHANGED", "125", old="120", coords=(10.0, 10.0)),
        # Same category, 1mm away, completely different text: a different finding.
        _prediction("drawing_views", "ADDED", "999", coords=(11.0, 10.0)),
    ]
    score = score_pair(pair, predictions, [], [_entity(None, "125", 10, 10)])

    assert len(score.matches) == 1
    assert len(score.spurious) == 1 and not score.duplicates, (
        "a nearby but textually unrelated finding is a false positive, not a duplicate"
    )


def test_bom_row_reported_cell_by_cell_counts_as_over_reporting():
    """The annotation guideline: an edited BOM row is one finding, not one per cell.

    The engine reports the row's five cells separately. Four of those are over-reporting
    and must count against precision — forgiving them as duplicates would let a real
    usability defect score as clean.
    """
    expected = ExpectedFinding(
        "REV#0", "bill_of_materials", "CHANGED", ref_text="a", rev_text="aB"
    )
    pair = _pair([expected])
    predictions = [
        _prediction("bill_of_materials", "REMOVED", text)
        for text in ("a", "SS400 28×%%c185", "1", "5.91", "4.36")
    ]
    score = score_pair(pair, predictions, [], [_entity(None, "aB")])

    assert len(score.matches) == 1
    assert len(score.spurious) == 4
    assert CorpusScore([score]).metrics()["precision"] == pytest.approx(1 / 5)


# ─── the counting rule everything else rests on ───────────────────────────────────────


def test_matched_candidates_are_not_predictions():
    """`generate_deterministic_candidates` returns every checklist row, including items
    checked and found unchanged. A null pair comes back with 50 candidates and 0
    discrepancies; counting candidates would report precision near zero on a perfect run.

    The filter lives in `runner.run_pair`; this pins the contract it depends on.
    """
    from services.backend.infrastructure.audit.comparison.candidate import ComparisonCandidate

    assert "MATCHED" in ComparisonCandidate.model_fields["status"].annotation.__args__, (
        "If MATCHED ever stops being a candidate status, runner.run_pair's filter is "
        "silently wrong and every precision number with it."
    )


# ─── aggregation ──────────────────────────────────────────────────────────────────────


def test_zero_finding_pairs_are_kept_out_of_recall():
    """Recall is undefined when the denominator is zero. Folding these in would let 23
    perfect precision probes silently inflate a recall figure."""
    zero = score_pair(_pair([]), [], [], [])
    scored = score_pair(
        _pair([ExpectedFinding("REV#0", "notes_section", "ADDED", rev_text="new")]),
        [_prediction("notes_section", "ADDED", "new")],
        [],
        [_entity(None, "new")],
    )
    corpus = CorpusScore([zero, scored])

    assert zero.is_zero_finding and not scored.is_zero_finding
    assert corpus.counts() == {"tp": 1, "fn": 0, "fp": 0, "duplicates": 0}
    assert corpus.metrics()["recall"] == 1.0


def test_findings_reported_on_a_zero_finding_pair_are_counted_as_false_positives():
    zero = score_pair(_pair([]), [_prediction("drawing_views", "ADDED", "x")], [], [])
    assert CorpusScore([zero]).zero_finding_false_positives() == 1


def test_unresolvable_label_is_a_corpus_defect_not_a_miss():
    """A label pointing at no entity is the corpus being wrong. Counting it as a miss
    would blame the engine for it."""
    pair = _pair([ExpectedFinding("REV#99", "notes_section", "ADDED", rev_text="ghost")])
    score = score_pair(pair, [], [], [_entity(None, "only one entity")])

    assert score.unresolvable
    assert score.missed == [], "an unresolvable label must not land in the recall denominator"
    assert CorpusScore([score]).unresolvable_labels() == ["P:REV#99"]


def test_report_prints_counts_beside_every_rate():
    """At this corpus size every rate is a small fraction of a small number. `0.86` alone
    invites a confidence the sample cannot support."""
    scored = score_pair(
        _pair([ExpectedFinding("REV#0", "notes_section", "ADDED", rev_text="new")]),
        [_prediction("notes_section", "ADDED", "new")],
        [],
        [_entity(None, "new")],
    )
    report = format_report(CorpusScore([scored]))
    assert "(1/1)" in report
    assert "error bars" in report
    assert "cannot reveal a scoping bug" in report, (
        "the mutation-corpus limitation must be in the output, not only in a docstring"
    )


def test_match_tiers_are_reported():
    """A result resting on spatial matching deserves less trust than one resting on
    handles. Hiding that behind a single F1 is the easiest way to ship a wrong number."""
    by_handle = score_pair(
        _pair([ExpectedFinding("REV-1A", "notes_section", "CHANGED", ref_text="x", rev_text="y")]),
        [_prediction("notes_section", "CHANGED", "y", handle="REV-1A", old="x")],
        [],
        [_entity("1A", "y")],
    )
    assert CorpusScore([by_handle]).tier_breakdown()["handle"] == 1
