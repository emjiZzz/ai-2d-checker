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


def test_empty_text_is_never_merged():
    """Blank strings would otherwise all collapse into each other."""
    markings = [_removed(""), _added("")]

    out = reconcile_relocated_markings(markings)

    assert len(out) == 2
