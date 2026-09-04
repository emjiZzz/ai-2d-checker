"""Regression: the title-block comparison must not report a field as REMOVED/ADDED when the
'missing' value is actually present in the other drawing's title region.

The title-block extractor is heuristic and scale-sensitive, so it frequently reads a field on
one side and returns NONE on the other (e.g. "DWG. No. M7452A1N01 vs NONE" when BOTH sheets are
M7452A1N01). Those are extraction misses, not edits. `inject_title_block_markings` now
corroborates a one-sided value against the other side's title region and downgrades to MATCHED
when found — but only when genuinely present, so real one-sided edits survive.

See docs/title-block-false-findings-implementation-plan.md.
"""
from types import SimpleNamespace

from services.backend.infrastructure.audit.comparison.marking_builder import (
    inject_title_block_markings,
)

TITLE_BBOX = (0.0, 0.0, 500.0, 200.0)


def _text_entity(text: str, x: float, y: float, layer: str = "TITLE"):
    return SimpleNamespace(
        entity_type="text",
        layer=layer,
        geometry={"insert": [x, y, 0.0]},
        properties={"text": text, "height": 3.0},
    )


def _find(markings, needle):
    return next(m for m in markings if needle in m["details"])


def test_one_sided_value_present_on_other_side_is_matched():
    # ref has the DWG No; rev extraction returned NONE for it, but the value IS on the rev sheet.
    markings: list = []
    inject_title_block_markings(
        clean_markings=markings,
        ref_title_fields={"DWG NO": {"value": "M7452A1N01"}},
        rev_title_fields={},  # → NONE for every field
        ref_entities=[],
        rev_entities=[_text_entity("M7452A1N01", 100, 50)],  # present in rev title region
        ref_title_bbox=TITLE_BBOX,
        rev_title_bbox=TITLE_BBOX,
    )
    m = _find(markings, "DWG. No.")
    assert m["status"] == "MATCHED", m


def test_genuine_one_sided_value_stays_flagged():
    # A value read on one side that is genuinely absent from the other stays REMOVED.
    # (2589/9324 are real values from the M7452A1N01 pair, but they belong to Job No., not
    # Previous Dwg. No. — the ruled cell grid puts them in the 工事番号 cell. They are used here
    # only as representative one-sided strings.)
    markings: list = []
    inject_title_block_markings(
        clean_markings=markings,
        ref_title_fields={"PREVIOUS DWG NO": {"value": "2589"}},
        rev_title_fields={},
        ref_entities=[],
        rev_entities=[_text_entity("9324", 100, 50)],  # different value
        ref_title_bbox=TITLE_BBOX,
        rev_title_bbox=TITLE_BBOX,
    )
    m = _find(markings, "Previous Dwg. No.")
    assert m["status"] == "REMOVED", m


def test_single_char_value_is_not_corroborated_inside_a_longer_token():
    """Regression (marker M019): a mis-extracted Previous Dwg. No. of '1' was "corroborated"
    against the '1' inside 'M7452A1N01' — the level-2 substring pass only required non-DIGIT
    neighbours, and there the neighbours are letters. A bad read became a green MATCHED tick.
    A value this short must match as a whole token or not at all."""
    markings: list = []
    inject_title_block_markings(
        clean_markings=markings,
        ref_title_fields={"PREVIOUS DWG NO": {"value": "1"}},
        rev_title_fields={},
        ref_entities=[],
        # The only '1' on the rev sheet is a character inside the drawing number.
        rev_entities=[_text_entity("M7452A1N01", 100, 50)],
        ref_title_bbox=TITLE_BBOX,
        rev_title_bbox=TITLE_BBOX,
    )
    m = _find(markings, "Previous Dwg. No.")
    assert m["status"] in ("REMOVED", "ADDED"), m


def test_short_numeric_value_outside_region_does_not_falsely_corroborate():
    # A short numeric title value must not be "corroborated" by an unrelated dimension elsewhere.
    markings: list = []
    inject_title_block_markings(
        clean_markings=markings,
        ref_title_fields={"QTY": {"value": "4"}},
        rev_title_fields={},
        ref_entities=[],
        # "4" exists only OUTSIDE the title bbox (a stray dimension) → must not match.
        rev_entities=[_text_entity("4", 900, 900, layer="DIM")],
        ref_title_bbox=TITLE_BBOX,
        rev_title_bbox=TITLE_BBOX,
    )
    m = _find(markings, "T. Q'ty")
    assert m["status"] in ("REMOVED", "ADDED"), m


def test_machine_and_unit_code_share_one_checklist_item():
    """機器記号 and ユニット記号 are ONE card, the way the DWG No. is one card for its
    ruled sub-cells.

    The marking already carried the combined label " Mach. code /  Unit Code" — the extractor
    widens its search across both cells precisely because the value spans them on this client's
    sheets (`FSRS2` runs under both headers) — but `title_feature_map` had no entry for it, so
    the finding was tagged OTHER_FEATURE_KEY and rendered under "Other / Unclassified" instead
    of in the title-block section.

    `feature` travels on the cached marking, which is why this needed a cache bump (v51).
    """
    markings: list = []
    inject_title_block_markings(
        clean_markings=markings,
        # Not a prefix of any drawing number, so the COMPONENT_OF_DWG_NO_FIELDS suppression
        # does not fire — this is the shape the owner reported.
        ref_title_fields={"MACHINE CODE": {"value": "FSRS2"}},
        rev_title_fields={"MACHINE CODE": {"value": "FSRS3"}},
        ref_entities=[],
        rev_entities=[],
        ref_title_bbox=TITLE_BBOX,
        rev_title_bbox=TITLE_BBOX,
    )
    m = _find(markings, "Mach. code")
    assert m["feature"] == "machine_unit_code", (
        f"expected the combined title-block item, got {m['feature']!r} — an unmapped field "
        f"falls to OTHER and renders outside the title-block section"
    )
    assert "Unit Code" in m["details"], "one card must name both cells"


def test_machine_code_that_is_a_dwg_no_prefix_still_gets_no_card():
    """The new item must not undo the DWG No. segment suppression.

    A machine code that genuinely IS the drawing number's prefix is already carried by the
    DWG No. card; giving it a second card was the defect behind
    "Gotcha - Drawing Number Segments Reported as Separate Fields".
    """
    markings: list = []
    inject_title_block_markings(
        clean_markings=markings,
        ref_title_fields={"MACHINE CODE": {"value": "M745"}, "DWG NO": {"value": "M745203N01"}},
        rev_title_fields={"MACHINE CODE": {"value": "M745"}, "DWG NO": {"value": "M745203N01"}},
        ref_entities=[],
        rev_entities=[],
        ref_title_bbox=TITLE_BBOX,
        rev_title_bbox=TITLE_BBOX,
    )
    assert not [m for m in markings if "Mach. code" in m["details"]], (
        "a machine code corroborated as the DWG No. prefix must stay suppressed"
    )
