"""Tests for collapsing REMOVED/ADDED pairs that are one unchanged item reported twice.

Background, measured on the M7452A0N01 pair: the reference lays its notes out in two columns
and the revision in one. `notes` is detected per drawing (correctly -- it genuinely moves), so
the detected notes box captured a different subset of the same block on each side. Every line
that landed in a different bucket was diffed against a pool that could not contain it, and was
emitted twice:

    drawing_views  REMOVED  完成時、バリ、キリ粉はなきこと
    notes_section  ADDED    完成時、バリ、キリ粉はなきこと

Five unchanged lines produced ten findings, about a quarter of the whole report.
"""
import pytest

from services.backend.infrastructure.audit.comparison.marking_reconciler import (
    reconcile_relocated_markings,
)

# The real lines from the corpus pair.
NOTES_LINES = [
    "完成時、バリ、キリ粉はなきこと",
    "タップ、キリ穴は面取り仕上げのこと",
    "指示なき角部は糸面取りのこと",
]


def _removed(text, category="drawing_views", coords=(10.0, 20.0)):
    return {
        "entity_id": f"REF-{text[:4]}",
        "text_content": text,
        "status": "REMOVED",
        "details": "Original element missing in trace",
        "category": category,
        "ref_coordinates": list(coords),
    }


def _added(text, category="notes_section", coords=(30.0, 40.0)):
    return {
        "entity_id": f"REV-{text[:4]}",
        "text_content": text,
        "status": "ADDED",
        "details": "New element traced/added",
        "category": category,
        "coordinates": list(coords),
    }


def _statuses(markings):
    out = {}
    for m in markings:
        out.setdefault(m["status"], []).append(m["text_content"])
    return out


def test_the_corpus_case_collapses_ten_findings_into_three():
    markings = [_removed(t) for t in NOTES_LINES] + [_added(t) for t in NOTES_LINES]

    out = reconcile_relocated_markings(markings)

    assert len(out) == 3
    by_status = _statuses(out)
    assert sorted(by_status["MATCHED"]) == sorted(NOTES_LINES)
    assert "ADDED" not in by_status
    assert "REMOVED" not in by_status


def test_merged_marking_keeps_both_coordinate_sets():
    """The finding still has to pin on both canvases."""
    markings = [
        _removed("完成時、バリ、キリ粉はなきこと", coords=(11.0, 22.0)),
        _added("完成時、バリ、キリ粉はなきこと", coords=(33.0, 44.0)),
    ]

    out = reconcile_relocated_markings(markings)

    assert len(out) == 1
    assert out[0]["coordinates"] == [33.0, 44.0], "revision coordinate lost"
    assert out[0]["ref_coordinates"] == [11.0, 22.0], "reference coordinate lost"


def test_merged_marking_takes_the_revision_category():
    """The revision describes the drawing as it now stands."""
    markings = [
        _removed("完成時、バリ、キリ粉はなきこと", category="drawing_views"),
        _added("完成時、バリ、キリ粉はなきこと", category="notes_section"),
    ]

    out = reconcile_relocated_markings(markings)

    assert out[0]["category"] == "notes_section"
    assert "relocated between zones" in out[0]["details"]
    assert "drawing_views" in out[0]["details"] and "notes_section" in out[0]["details"]


def test_same_category_long_move_is_also_collapsed():
    """The zone partition is not the only way to get this shape -- content that simply moved
    further than the differ's widened radius produces it too."""
    markings = [
        _removed("SECTION A-A", category="drawing_views"),
        _added("SECTION A-A", category="drawing_views"),
    ]

    out = reconcile_relocated_markings(markings)

    assert len(out) == 1
    assert out[0]["status"] == "MATCHED"
    assert "relocated within" in out[0]["details"]


def test_ambiguous_repeated_text_is_left_alone():
    """A '1' deleted from the BOM and an unrelated '1' added in the title block must not be
    merged into 'unchanged' — that would silently destroy a real deletion."""
    markings = [
        _removed("1", category="bill_of_materials"),
        _removed("1", category="drawing_views"),
        _added("1", category="title_block"),
    ]

    out = reconcile_relocated_markings(markings)

    assert len(out) == 3
    assert _statuses(out)["REMOVED"] == ["1", "1"]
    assert _statuses(out)["ADDED"] == ["1"]


def test_one_to_one_short_text_is_collapsed():
    """Unique on both sides is unambiguous regardless of length."""
    markings = [_removed("4", category="title_block"), _added("4", category="title_block")]

    out = reconcile_relocated_markings(markings)

    assert len(out) == 1 and out[0]["status"] == "MATCHED"


def test_normalization_matches_the_differs_own_rules():
    """Half-width vs full-width is the same value. If the differ would have paired them
    inside one pool, reconciliation must pair them across pools."""
    markings = [_removed("1", category="bill_of_materials"),
                _added("１", category="title_block")]

    out = reconcile_relocated_markings(markings)

    assert len(out) == 1
    assert out[0]["status"] == "MATCHED"


def test_genuine_removal_survives():
    markings = [_removed("DELETED NOTE"), _added("A COMPLETELY DIFFERENT NOTE")]

    out = reconcile_relocated_markings(markings)

    assert len(out) == 2
    assert _statuses(out)["REMOVED"] == ["DELETED NOTE"]
    assert _statuses(out)["ADDED"] == ["A COMPLETELY DIFFERENT NOTE"]


def test_matched_and_changed_findings_are_untouched():
    markings = [
        {"text_content": "8.65", "original_value": "8.7", "status": "CHANGED",
         "category": "bill_of_materials"},
        {"text_content": "S45C", "status": "MATCHED", "category": "bill_of_materials"},
    ]

    out = reconcile_relocated_markings(markings)

    assert out == markings


def test_original_value_is_dropped_from_a_merged_marking():
    """A MATCHED finding claiming an original_value would render as a change in the UI."""
    removed = _removed("NOTE")
    added = _added("NOTE")
    added["original_value"] = "stale"

    out = reconcile_relocated_markings([removed, added])

    assert "original_value" not in out[0]


def test_input_is_not_mutated():
    markings = [_removed("NOTE"), _added("NOTE")]
    snapshot = [dict(m) for m in markings]

    reconcile_relocated_markings(markings)

    assert markings == snapshot


def test_order_is_preserved_at_the_removed_position():
    """A report should not reshuffle just because reconciliation kicked in."""
    markings = [
        {"text_content": "first", "status": "MATCHED", "category": "drawing_views"},
        _removed("NOTE"),
        {"text_content": "third", "status": "MATCHED", "category": "drawing_views"},
        _added("NOTE"),
    ]

    out = reconcile_relocated_markings(markings)

    assert [m["text_content"] for m in out] == ["first", "NOTE", "third"]


@pytest.mark.parametrize("markings", [[], [{"text_content": "x", "status": "MATCHED"}]])
def test_degenerate_inputs(markings):
    assert reconcile_relocated_markings(markings) == markings


# ---------------------------------------------------------------------------
# Fuzzy pass: content that both moved AND changed
# ---------------------------------------------------------------------------

REF_BOUNDS = [-52.5, -37.125, 1102.5, 779.625]
REV_BOUNDS = [-21.0, -14.85, 441.0, 311.85]


def test_the_real_moved_and_changed_case_collapses():
    """From the corpus pair: the trailing 度 was dropped AND the line changed zone, so the
    per-zone diffs never compared the two. It stayed a deletion plus an unrelated addition,
    with the actual edit never stated anywhere."""
    markings = [
        _removed("素材調質施工　硬度HS35～38度", category="notes_section"),
        _added("素材調質施工　硬度ＨＳ３５～３８", category="drawing_views"),
    ]

    out = reconcile_relocated_markings(markings)

    assert len(out) == 1
    assert out[0]["status"] == "CHANGED"
    assert out[0]["original_value"] == "素材調質施工　硬度HS35～38度"
    assert "Edited and relocated" in out[0]["details"]


def test_unrelated_text_is_not_paired():
    markings = [_removed("完成時、バリ、キリ粉はなきこと"), _added("SECTION A-A")]

    out = reconcile_relocated_markings(markings)

    assert len(out) == 2
    assert {m["status"] for m in out} == {"REMOVED", "ADDED"}


def test_ambiguous_candidates_are_all_left_alone():
    """Two near-equally similar candidates mean the pairing is a guess. A wrong merge
    destroys a finding; a missed merge only leaves noise that was already there."""
    markings = [
        _removed("TOLERANCE CLASS A1"),
        _added("TOLERANCE CLASS A2"),
        _added("TOLERANCE CLASS A3"),
    ]

    out = reconcile_relocated_markings(markings)

    assert len(out) == 3
    assert sum(1 for m in out if m["status"] == "CHANGED") == 0


def test_one_added_cannot_claim_several_removeds():
    markings = [
        _removed("MATERIAL SPEC S45C"),
        _removed("MATERIAL SPEC S50C"),
        _added("MATERIAL SPEC S55C"),
    ]

    out = reconcile_relocated_markings(markings)

    assert sum(1 for m in out if m["status"] == "CHANGED") == 0


def test_short_strings_are_never_fuzzy_paired():
    """No threshold separates a real edit from a coincidence at this length: '8.7' vs '8.65'
    scores 0.57 and '45' vs '46' scores 0.5."""
    markings = [_removed("8.7", category="bill_of_materials"),
                _added("8.65", category="title_block")]

    out = reconcile_relocated_markings(markings)

    assert len(out) == 2
    assert {m["status"] for m in out} == {"REMOVED", "ADDED"}


def test_content_that_moved_across_the_whole_sheet_is_not_paired():
    """Content moves, but not from one corner to the other. The check runs in the normalized
    frame because the two drawings are 2.5x apart in raw units."""
    removed = _removed("素材調質施工　硬度HS35～38度", category="notes_section",
                       coords=(60.0, 740.0))          # top-left of the reference
    added = _added("素材調質施工　硬度ＨＳ３５～３８", category="drawing_views",
                   coords=(430.0, 10.0))              # bottom-right of the revision

    out = reconcile_relocated_markings(
        [removed, added], ref_bounds=REF_BOUNDS, rev_bounds=REV_BOUNDS,
    )

    assert len(out) == 2, "a sheet-wide jump is not a relocation"


def test_a_modest_move_is_still_paired_with_bounds_supplied():
    removed = _removed("素材調質施工　硬度HS35～38度", category="notes_section",
                       coords=(300.0, 600.0))
    added = _added("素材調質施工　硬度ＨＳ３５～３８", category="drawing_views",
                   coords=(126.0, 242.0))   # same relative spot, revision scale

    out = reconcile_relocated_markings(
        [removed, added], ref_bounds=REF_BOUNDS, rev_bounds=REV_BOUNDS,
    )

    assert len(out) == 1
    assert out[0]["status"] == "CHANGED"


def test_missing_coordinates_do_not_block_the_merge():
    """The distance test is a guard, not a requirement."""
    removed = {"text_content": "素材調質施工　硬度HS35～38度", "status": "REMOVED",
               "category": "notes_section", "details": ""}
    added = {"text_content": "素材調質施工　硬度ＨＳ３５～３８", "status": "ADDED",
             "category": "drawing_views", "details": ""}

    out = reconcile_relocated_markings([removed, added],
                                       ref_bounds=REF_BOUNDS, rev_bounds=REV_BOUNDS)

    assert len(out) == 1 and out[0]["status"] == "CHANGED"


def test_exact_matches_are_consumed_before_the_fuzzy_pass():
    """An identical pair must become MATCHED, not be stolen by a similar-but-different one."""
    markings = [
        _removed("完成時、バリ、キリ粉はなきこと", category="drawing_views"),
        _added("完成時、バリ、キリ粉はなきこと", category="notes_section"),
        _added("完成時、バリ、キリ粉はなきこ", category="notes_section"),
    ]

    out = reconcile_relocated_markings(markings)

    statuses = _statuses(out)
    assert "完成時、バリ、キリ粉はなきこと" in statuses.get("MATCHED", [])
    assert statuses.get("ADDED") == ["完成時、バリ、キリ粉はなきこ"]


def test_empty_text_is_never_merged():
    """Blank strings would otherwise all collapse into each other."""
    markings = [_removed(""), _added("")]

    out = reconcile_relocated_markings(markings)

    assert len(out) == 2
