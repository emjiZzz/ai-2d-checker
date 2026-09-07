"""What the matcher report counts, and what it refuses to count.

`summarise` is pure so the aggregation is checkable without a database. The tests that matter
here are the ones about restraint: this report exists to make a parked corpus legible, and a
legible-but-wrong number would be worse than the silence it replaces.
"""

from tools.matcher_status import summarise


def _row(verb="mispaired_wrong_match", **over):
    snap = {
        "category": "drawing_views",
        "feature": "dimensions",
        "ref_coord": [1.0, 2.0],
        "rev_coord": [3.0, 4.0],
        **(over.pop("snapshot", None) or {}),
    }
    return {
        "human_corrected_status": verb,
        "human_comment": None,
        "retracted_at": None,
        "finding_snapshot": snap,
        **over,
    }


def test_only_matcher_verbs_are_counted():
    """`dismissed` and `confirmed_change` train the verdict head and are reported by
    `label_status.py`. Counting them here would double-count the corpus in two tools."""
    s = summarise([_row(), _row("dismissed"), _row("confirmed_change"), _row("verdict_matched")])
    assert s["matcher_rows"] == 1
    assert s["rows_live"] == 4


def test_a_retracted_row_is_excluded():
    # A retraction is the engineer withdrawing the complaint. Counting it would report a defect
    # they took back.
    s = summarise([_row(), _row(retracted_at="2026-08-18T00:00:00Z")])
    assert s["matcher_rows"] == 1


def test_the_two_verbs_are_kept_apart():
    """They are different failures. `missing_counterpart` is pairing RECALL — no candidate was
    offered at all — and `wrong_match` is discrimination. A learned matcher addresses the second
    and does nothing for the first, so collapsing them would hide which problem you have."""
    s = summarise([_row("mispaired_missing_counterpart"), _row("mispaired_wrong_match"), _row("mispaired_wrong_match")])
    assert s["by_verb"] == {"mispaired_wrong_match": 2, "mispaired_missing_counterpart": 1}


def test_concentration_is_reported_by_category_and_feature_together():
    # The pair is the useful unit: "drawing_views" alone is too coarse to act on, and
    # "dimensions" alone would merge a dimension in a view with one in a table.
    s = summarise(
        [
            _row(),
            _row(),
            _row(snapshot={"category": "title_block", "feature": "scale"}),
        ]
    )
    top = s["top_category_feature"][0]
    assert (top["category"], top["feature"], top["count"]) == ("drawing_views", "dimensions", 2)


def test_a_missing_feature_is_named_rather_than_dropped():
    """`unclassified` rather than silence: 10 real rows have no feature, and a bucket that
    vanished would make the percentages add to less than 100 with nothing to explain it."""
    s = summarise([_row(snapshot={"category": "notes_section", "feature": None})])
    assert s["by_feature"] == {"unclassified": 1}


def test_the_trainable_subset_is_the_rows_carrying_a_counterpart():
    """The number the whole plan turns on. 3 of 102 in the live corpus — which is why Step 2
    changes the capture, and why Stage 3 cannot simply be built on what is already there."""
    s = summarise([_row(), _row(human_comment="should pair with the 145 above"), _row(human_comment="   ")])
    assert s["with_counterpart"] == 1, "whitespace is not a counterpart"


def test_rows_with_one_coordinate_are_not_counted_as_having_both():
    # `match_distance` is derivable only from a pair of coordinates. Reporting a row with one as
    # measurable would overstate what a future model has to work with.
    s = summarise(
        [
            _row(),
            _row(snapshot={"category": "drawing_views", "feature": "dimensions", "ref_coord": [1.0, 2.0], "rev_coord": None}),
        ]
    )
    assert s["with_both_coords"] == 1


def test_an_empty_corpus_reports_zero_rather_than_dividing_by_it():
    s = summarise([])
    assert s["matcher_rows"] == 0
    assert s["by_verb"] == {}


def test_no_rate_is_reported_anywhere():
    """The deliberate omission, asserted so nobody adds one later.

    `audit_feedback` records rejections and never the total pairings attempted, so this
    collection contains no denominator. A percentage-of-pairings figure would have to be
    invented, and it would look exactly as authoritative as a measured one.
    """
    s = summarise([_row(), _row("mispaired_missing_counterpart")])
    for key in s:
        assert "rate" not in key and "pct" not in key and "percent" not in key
