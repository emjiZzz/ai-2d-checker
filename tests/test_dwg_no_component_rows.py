"""Machine Type/Code, Unit No./Unit Code and Part No. are segments of the drawing number.

`M745203N01` is `M745` + `203` + `N01`, each in its own ruled sub-cell under the bottom
title block's DWG No. header, so the checklist listed four items for one identifier — and three
of them cannot change without the DWG No. changing too.

They are suppressed only when the DWG No. is shown to account for them. That check is the
point: unconditional suppression would mean a changed segment goes unreported on any sheet
where the DWG No. fails to extract, and it does fail — the live KEMCO revision reads NONE.

The UPPER-LEFT table's `Unit No.` and `Part No.` are different cells that happen to share
these names, and they are genuine standalone fields — they must keep their own items. They
are produced by a separate path (`extract_title_ul_kv` → the `title_ul_table`, tagged
`zone: 'title_upper_left'` and prefixed `Title Block (Upper-Left)`), never by
`build_title_block_table` or `inject_title_block_markings`. The collision is the hazard this
file exists to pin: on the live KEMCO sheet the UL `Part No.` reads `203`, which *is* the
middle segment of `M745203N01`, so extending the suppression to the UL table would silently
delete a real field.

See docs/vault/06 - Gotchas & Debugging Lessons/
  Gotcha - Drawing Number Segments Reported as Separate Fields.md
"""
from services.backend.infrastructure.audit.comparison.marking_builder import (
    inject_title_block_markings,
)
from services.backend.infrastructure.utils.text import (
    COMPONENT_OF_DWG_NO_FIELDS,
    build_title_block_table,
    is_component_of_dwg_no,
)

# Measured from the live KEMCO audit: DWG No. M745203N01 on the reference, NONE on the
# revision (the field genuinely fails to extract there).
DWG_NO = "M745203N01"


def _fields(**kw) -> dict:
    base = {
        "QTY": "NONE", "STOCK QTY": "NONE", "DRAWN": "NONE", "DESIGNED": "NONE",
        "SCALE": "NONE", "TITLE": "NONE", "JOB NO": "NONE", "DWG NO": "NONE",
        "MACHINE CODE": "NONE", "UNIT NO": "NONE", "PART NO": "NONE",
    }
    base.update(kw)
    return {k: {"value": v, "coordinates": None} for k, v in base.items()}


# --- the containment rule ------------------------------------------------------------------

def test_each_segment_is_recognised_at_its_own_position():
    assert is_component_of_dwg_no("M745", DWG_NO, "prefix") is True  # Machine Type / Mach. code
    assert is_component_of_dwg_no("203", DWG_NO, "infix") is True    # Unit No. / Unit Code
    assert is_component_of_dwg_no("N01", DWG_NO, "suffix") is True   # Part No.


def test_a_blank_component_is_trivially_accounted_for():
    assert is_component_of_dwg_no("NONE", DWG_NO, "prefix") is True
    assert is_component_of_dwg_no("", DWG_NO, "suffix") is True
    # Even with no drawing number to compare against — there is nothing to report either way.
    assert is_component_of_dwg_no("NONE", "NONE", "infix") is True


def test_position_rejects_a_match_that_straddles_a_segment_boundary():
    # THE reason this is positional rather than a substring test: `45` sits inside `M745`203N01
    # without being a segment of anything. A plain containment check calls it corroborated and
    # silently drops the row. This codebase has already shipped one green tick that way — a
    # `Previous Dwg. No.` of `1` matched against the `1` in `M7452A1N01`.
    assert is_component_of_dwg_no("45", DWG_NO, "prefix") is False
    assert is_component_of_dwg_no("452", DWG_NO, "suffix") is False
    assert is_component_of_dwg_no("X99", DWG_NO, "prefix") is False


def test_a_segment_at_the_wrong_position_is_not_corroborated():
    # The Part No. is a suffix; finding `M745` there is not evidence about the Part No.
    assert is_component_of_dwg_no("M745", DWG_NO, "suffix") is False
    assert is_component_of_dwg_no("N01", DWG_NO, "prefix") is False
    # An infix must be strictly interior, so neither end counts.
    assert is_component_of_dwg_no("M745", DWG_NO, "infix") is False
    assert is_component_of_dwg_no("N01", DWG_NO, "infix") is False


def test_an_unextracted_drawing_number_corroborates_nothing():
    # The failure mode the guard exists for: DWG No. read NONE, so it cannot vouch for a
    # populated segment and the segment must keep its row.
    assert is_component_of_dwg_no("M745", "NONE", "prefix") is False
    assert is_component_of_dwg_no("M745", "", "prefix") is False


def test_matching_folds_width_case_and_separators():
    assert is_component_of_dwg_no("m745", DWG_NO, "prefix") is True
    assert is_component_of_dwg_no("M-745", DWG_NO, "prefix") is True
    # fullwidth, as this corpus writes — see the fullwidth-callout gotcha
    assert is_component_of_dwg_no("Ｍ７４５", DWG_NO, "prefix") is True


# --- the checklist table -------------------------------------------------------------------

def test_component_rows_are_absent_when_the_drawing_number_accounts_for_them():
    table = build_title_block_table(
        _fields(**{"DWG NO": DWG_NO, "MACHINE CODE": "M745", "UNIT NO": "203", "PART NO": "N01"}),
        _fields(**{"DWG NO": DWG_NO, "MACHINE CODE": "M745", "UNIT NO": "203", "PART NO": "N01"}),
    )
    assert "MACHINE CODE" not in table
    assert "UNIT NO" not in table
    assert "PART NO" not in table
    # The identifier itself is still reported.
    assert "DWG NO (Drawing Number)" in table
    assert DWG_NO in table


def test_all_none_component_rows_are_absent():
    # The live KEMCO case: all three read NONE while DWG No. carries the value. Nothing is
    # lost by dropping them and the panel stops showing three permanently-empty items.
    table = build_title_block_table(_fields(**{"DWG NO": DWG_NO}), _fields())
    assert "MACHINE CODE" not in table
    assert "UNIT NO" not in table
    assert "PART NO" not in table


def test_an_uncorroborated_component_keeps_its_row():
    # DWG No. failed to extract on both sides but Machine Code read a value — it is carrying
    # information nothing else reports, so suppressing it would be a false negative.
    table = build_title_block_table(
        _fields(**{"MACHINE CODE": "M745"}),
        _fields(**{"MACHINE CODE": "M999"}),
    )
    assert "MACHINE CODE / UNIT CODE" in table
    assert "M745" in table and "M999" in table


def test_a_component_that_disagrees_with_the_drawing_number_keeps_its_row():
    # Part No. reads N02 while the DWG No. says ...N01. Whichever is right, that is a real
    # discrepancy and it must reach the reviewer.
    table = build_title_block_table(
        _fields(**{"DWG NO": DWG_NO, "PART NO": "N01"}),
        _fields(**{"DWG NO": DWG_NO, "PART NO": "N02"}),
    )
    assert "PART NO (Part Number)" in table


def test_non_component_rows_are_untouched():
    table = build_title_block_table(
        _fields(**{"SCALE": "1:1", "DRAWN": "中川"}),
        _fields(**{"SCALE": "1/1", "DRAWN": "ZHR"}),
    )
    for label in ("QTY (Quantity)", "STOCK QTY", "DRAWN (Drawn By)", "DESIGNED (Designed By)",
                  "SCALE (Sheet Scale)", "TITLE (Drawing Title)", "JOB NO (Job Number)",
                  "DWG NO (Drawing Number)"):
        assert label in table


# --- the canvas cards ----------------------------------------------------------------------

def _markings(ref_fields: dict, rev_fields: dict) -> list:
    out: list = []
    inject_title_block_markings(out, ref_fields, rev_fields, [], [])
    return out


def test_no_machine_code_card_when_the_drawing_number_accounts_for_it():
    marks = _markings(
        _fields(**{"DWG NO": DWG_NO, "MACHINE CODE": "M745"}),
        _fields(**{"DWG NO": DWG_NO, "MACHINE CODE": "M745"}),
    )
    assert not [m for m in marks if "Mach. code" in m["details"]]
    # The DWG No. card survives and no longer advertises the sub-cells it dropped.
    dwg_cards = [m for m in marks if "DWG. No." in m["details"]]
    assert len(dwg_cards) == 1
    for absent in ("Machine Type", "Unit No.", "Part No.", "Branch"):
        assert absent not in dwg_cards[0]["details"]


def test_uncorroborated_machine_code_still_gets_a_card():
    marks = _markings(_fields(**{"MACHINE CODE": "M745"}), _fields())
    assert [m for m in marks if "Mach. code" in m["details"]]


# --- the upper-left table is a different set of fields with the same names -----------------

def test_suppression_is_scoped_to_bottom_title_block_field_keys():
    # The rule is keyed on extract_title_block's own dict keys. The upper-left table never
    # produces these keys — its rows carry the sheet's own header text ("Unit No. / ユニットNo.",
    # "Part No. / コードNo.") — so it cannot be reached by this suppression.
    assert set(COMPONENT_OF_DWG_NO_FIELDS) == {"MACHINE CODE", "UNIT NO", "PART NO"}


def test_upper_left_fields_are_produced_by_a_different_path():
    # inject_title_block_markings owns only the bottom title block. If an upper-left row ever
    # starts coming through here, the suppression above would begin deleting real fields.
    marks = _markings(
        _fields(**{"DWG NO": DWG_NO, "MACHINE CODE": "M745"}),
        _fields(**{"DWG NO": DWG_NO, "MACHINE CODE": "M745"}),
    )
    assert not [m for m in marks if "Upper-Left" in m["details"]]
    assert not [m for m in marks if m.get("zone") == "title_upper_left"]


def test_the_bottom_table_never_contains_upper_left_rows():
    # The two tables are concatenated downstream into one title_block checklist, but they are
    # built independently — build_title_block_table must not emit the UL labels itself.
    table = build_title_block_table(_fields(**{"DWG NO": DWG_NO}), _fields())
    for ul_label in ("ユニットNo.", "コードNo.", "Upper-Left", "在庫棚入庫"):
        assert ul_label not in table


def test_a_value_that_is_a_dwg_segment_is_still_a_real_upper_left_field():
    # Documents the trap concretely: the live KEMCO UL `Part No.` reads 203, which IS the
    # middle segment of M745203N01. It is nonetheless a genuine standalone field. This asserts
    # the containment rule would call it corroborated — which is exactly why the rule must
    # never be pointed at the upper-left table.
    assert is_component_of_dwg_no("203", DWG_NO, "infix") is True


def test_card_and_table_agree_about_what_was_dropped():
    # The two suppressions share one rule, so a reviewer never sees a row without its card or
    # a card without its row.
    ref = _fields(**{"DWG NO": DWG_NO, "MACHINE CODE": "M745"})
    rev = _fields(**{"DWG NO": DWG_NO, "MACHINE CODE": "M745"})
    assert "MACHINE CODE" not in build_title_block_table(ref, rev)
    assert not [m for m in _markings(ref, rev) if "Mach. code" in m["details"]]

    ref2 = _fields(**{"MACHINE CODE": "M745"})
    rev2 = _fields(**{"MACHINE CODE": "M745"})
    assert "MACHINE CODE / UNIT CODE" in build_title_block_table(ref2, rev2)
    assert [m for m in _markings(ref2, rev2) if "Mach. code" in m["details"]]
