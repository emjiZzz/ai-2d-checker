"""One edited BOM row is ONE finding, not one per column.

The annotation guideline (`docs/vault/01 - Architecture/Eval Corpus Annotation Guideline.md`)
states it directly: *"A BOM row edited => 1 CHANGED per row, not per cell."* The builder used to
append a marking per column, so a row whose Code, Q'ty and Remark all moved as part of one edit
produced three checklist items where a checker sees one -- and where a human label will say one.

These tests exist because `tools/eval.py` cannot reach this path. Every BOM mutation operator
edits a single entity (`mutator.py` `_pick_zone` picks one target), so no mutation pair ever
produces a row with two changed cells, and the eval scores byte-identical with and without the
collapse. That is the same structural blindness recorded for the spatial constants in
[[Gotcha - Mutation Pairs Cannot Exercise a Spatial Constant]]: the corpus cannot exercise it, so
the assertion has to live here or nowhere.
"""

from services.backend.infrastructure.audit.comparison.marking_builder import (
    inject_bom_markings,
)


def _row(no, code, qty, remark="NONE", dimension="NONE", y=100.0):
    """A non-assembly BOM row. CODE must be populated or is_blank_spacer_local drops the row."""
    return {
        "NO": {"value": no, "coordinates": [0.0, y]},
        "CODE": {"value": code, "coordinates": [1.0, y]},
        "DIMENSION": {"value": dimension, "coordinates": [2.0, y]},
        "QTY": {"value": qty, "coordinates": [3.0, y]},
        "REMARK": {"value": remark, "coordinates": [4.0, y]},
    }


def _inject(ref_rows, rev_rows):
    clean: list = []
    inject_bom_markings(
        clean, ref_rows, rev_rows, is_assembly_drawing=False,
        ref_bom_bbox=None, rev_bom_bbox=None, ref_entities=[], rev_entities=[],
        used_ref_entities=set(), used_rev_entities=set(),
    )
    return clean


def _findings(markings):
    """The scored population. `eval/runner.py` builds predictions from status != MATCHED."""
    return [m for m in markings if m["status"] != "MATCHED"]


def test_a_row_changed_in_three_columns_is_one_finding():
    """The core assertion. Verified to fail against the per-cell builder, which emitted 3."""
    ref = [_row("1", code="ABC", qty="2", remark="old")]
    rev = [_row("1", code="XYZ", qty="3", remark="new")]

    findings = _findings(_inject(ref, rev))

    assert len(findings) == 1, (
        f"expected one row-level finding, got {len(findings)}: "
        f"{[f['details'] for f in findings]}"
    )
    assert findings[0]["status"] == "CHANGED"
    assert findings[0]["category"] == "bill_of_materials"


def test_the_collapsed_detail_names_every_changed_column():
    """Collapsing must not lose what a checker needs to act. All three values stay readable."""
    ref = [_row("1", code="ABC", qty="2", remark="old")]
    rev = [_row("1", code="XYZ", qty="3", remark="new")]

    details = _findings(_inject(ref, rev))[0]["details"]

    for value in ("ABC", "XYZ", "2", "3", "old", "new"):
        assert value in details, f"{value!r} missing from collapsed detail: {details!r}"
    assert "3 columns changed" in details


def test_a_single_changed_cell_keeps_the_original_wording():
    """The common case must be byte-identical to the pre-collapse engine, so the v42->v43 diff
    is auditable: only multi-column rows may read differently."""
    ref = [_row("1", code="ABC", qty="2")]
    rev = [_row("1", code="ABC", qty="3")]

    findings = _findings(_inject(ref, rev))

    assert len(findings) == 1
    assert findings[0]["details"] == "BOM [Item 1]  / Q'ty checked: 2 vs 3"
    assert findings[0]["feature"] == "quantity"
    assert findings[0]["original_value"] == "2"


def test_matched_cells_are_not_collapsed():
    """Deliberate non-collapse. MATCHED cells are per-column VERIFICATION rows, not findings;
    the guideline rule is about findings. Folding them away would delete the evidence a checker
    signs off on, which is a product regression dressed up as a metric win."""
    ref = [_row("1", code="ABC", qty="2", remark="same")]
    rev = [_row("1", code="ABC", qty="3", remark="same")]

    markings = _inject(ref, rev)
    matched = [m for m in markings if m["status"] == "MATCHED"]

    assert len(_findings(markings)) == 1
    # NO, CODE and REMARK were unchanged and each keeps its own row.
    matched_details = " ".join(m["details"] for m in matched)
    assert "No." in matched_details
    assert "Code" in matched_details
    assert "Remark" in matched_details


def test_the_finding_anchors_on_the_first_changed_column_in_bom_cols_order():
    """A deterministic anchor, matching the convention the guideline already uses for bulk
    findings, so the same edit always reports at the same place on the sheet. bom_cols order for
    a non-assembly drawing is NO, CODE, DIMENSION, QTY, ... so CODE anchors over QTY."""
    ref = [_row("1", code="ABC", qty="2")]
    rev = [_row("1", code="XYZ", qty="3")]

    finding = _findings(_inject(ref, rev))[0]

    assert finding["text_content"] == "XYZ"
    assert finding["coordinates"] == [1.0, 100.0]      # CODE's cell, not QTY's
    assert finding["ref_coordinates"] == [1.0, 100.0]
    assert finding["original_value"] == "ABC"
    assert finding["feature"] == "material_type"   # CODE's feature: 材質 / Code holds the material


def test_two_edited_rows_stay_two_findings():
    """The collapse is per row. It must not merge across rows -- that would hide a change."""
    ref = [_row("1", code="ABC", qty="2", y=100.0), _row("2", code="DEF", qty="5", y=80.0)]
    rev = [_row("1", code="XYZ", qty="3", y=100.0), _row("2", code="GHI", qty="6", y=80.0)]

    findings = _findings(_inject(ref, rev))

    assert len(findings) == 2
    assert {f["details"].split("]")[0] for f in findings} == {"BOM [Item 1", "BOM [Item 2"}


def test_an_unchanged_row_produces_no_finding():
    """The precision probe, at row level: identical rows must stay silent."""
    ref = [_row("1", code="ABC", qty="2", remark="same")]
    rev = [_row("1", code="ABC", qty="2", remark="same")]

    assert _findings(_inject(ref, rev)) == []
