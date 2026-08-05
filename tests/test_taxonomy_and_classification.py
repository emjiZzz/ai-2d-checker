"""
Unit coverage for the checklist-taxonomy-grouping plan's classification/tagging layer
(docs/checklist-taxonomy-grouping-implementation-plan.md, Phase 8) — taxonomy.py,
feature_classifier.py, marking_builder.py's feature-tagging additions, and
title_block_extractor.py's REVISION CODE extraction. These were only spot-checked with
inline sanity scripts during Phases 1-2; this file formalizes that into a permanent
regression suite, per Phase 8's own "unit-testable" checklist.
"""
from services.backend.infrastructure.audit.comparison import taxonomy
from services.backend.infrastructure.audit.comparison import feature_classifier as fc
from services.backend.infrastructure.audit.comparison.marking_builder import (
    inject_title_block_markings,
    inject_bom_markings,
    inject_ballooning_markings,
)
from services.backend.infrastructure.audit.bom.title_block_extractor import extract_title_block


class _FakeEntity:
    """Duck-typed stand-in for ExtractedEntity, same rationale as test_hybrid_pipeline.py's
    _FakeEntity — the real Beanie Document needs an initialized DB collection to construct,
    and none of the functions under test need more than .entity_type/.properties/.geometry/.id."""
    def __init__(self, entity_type, properties, geometry, id="fake"):
        self.entity_type = entity_type
        self.properties = properties
        self.geometry = geometry
        self.id = id


def _text_entity(text, x, y, height=3.0):
    return _FakeEntity(entity_type="text", properties={"text": text, "height": height}, geometry={"insert": [x, y, 0]})


def _circle_and_number(cx, cy, radius, number_text):
    circle = _FakeEntity(entity_type="circle", properties={}, geometry={"center": [cx, cy], "radius": radius}, id=f"circle_{number_text}")
    text = _FakeEntity(entity_type="text", properties={"text": number_text}, geometry={"insert": [cx, cy]})
    return circle, text


# ─── taxonomy.py ──────────────────────────────────────────────────────────────

def test_taxonomy_categories_non_empty_no_duplicate_keys():
    for category, items in taxonomy.TAXONOMY.items():
        assert len(items) > 0, f"{category} has no sub-items"
        keys = [item.key for item in items]
        assert len(keys) == len(set(keys)), f"duplicate feature keys in {category}"


def test_normalize_feature_exact_key_match():
    assert taxonomy.normalize_feature("title_block", "scale") == "scale"


def test_normalize_feature_label_match():
    assert taxonomy.normalize_feature("title_block", "Scale") == "scale"
    assert taxonomy.normalize_feature("drawing_views", "Chamfer / Radius") == "chamfer_radius"


def test_normalize_feature_key_with_spaces_match():
    assert taxonomy.normalize_feature("title_block", "job number") == "job_number"


def test_normalize_feature_falls_back_to_other_on_unknown_category():
    assert taxonomy.normalize_feature("nonexistent_category", "scale") == taxonomy.OTHER_FEATURE_KEY


def test_normalize_feature_falls_back_to_other_on_no_match():
    assert taxonomy.normalize_feature("title_block", "totally unrelated synonym") == taxonomy.OTHER_FEATURE_KEY


def test_normalize_feature_falls_back_to_other_on_none_or_empty():
    assert taxonomy.normalize_feature("title_block", None) == taxonomy.OTHER_FEATURE_KEY
    assert taxonomy.normalize_feature("title_block", "") == taxonomy.OTHER_FEATURE_KEY


def test_feature_label_known_and_fallback():
    assert taxonomy.feature_label("title_block", "scale") == "Scale"
    assert taxonomy.feature_label("title_block", "unknown_key") == taxonomy.OTHER_FEATURE_LABEL
    assert taxonomy.feature_label("title_block", None) == taxonomy.OTHER_FEATURE_LABEL


# ─── feature_classifier.py ────────────────────────────────────────────────────

def test_classify_drawing_view_feature_geometric_tolerances():
    assert fc.classify_drawing_view_feature("⊕0.02") == "geometric_tolerances"
    assert fc.classify_drawing_view_feature("170 +0/-0.1") == "geometric_tolerances"


def test_classify_drawing_view_feature_hole_properties():
    assert fc.classify_drawing_view_feature("4-キリ 8") == "hole_properties"
    assert fc.classify_drawing_view_feature("⌀10 drill") == "hole_properties"


def test_classify_drawing_view_feature_chamfer_radius():
    assert fc.classify_drawing_view_feature("C2") == "chamfer_radius"
    assert fc.classify_drawing_view_feature("R3") == "chamfer_radius"


def test_classify_drawing_view_feature_folds_fullwidth_callouts():
    """Regression: this corpus is Japanese CAD and writes callouts FULLWIDTH. Every pattern in
    the classifier is ASCII, so `Ｃ１` (U+FF23 U+FF11) missed the chamfer rule and a real
    chamfer callout was filed under "Other / Unclassified" — measured on the M7452A1N01 pair,
    where the reference writes `C1` and the revision `Ｃ１` for the same chamfer.

    SpatialDiffer._normalize_text already NFKC-folds, so the differ *paired* the two correctly;
    this classifier was the one place that did not, so the finding was matched but mislabelled.
    """
    for fullwidth, halfwidth in (("Ｃ１", "C1"), ("Ｒ５", "R5")):
        assert fc.classify_drawing_view_feature(fullwidth) == "chamfer_radius", fullwidth
        assert fc.classify_drawing_view_feature(fullwidth) == fc.classify_drawing_view_feature(halfwidth)

    # The same gap hid fullwidth dimensions and tolerances.
    assert fc.classify_drawing_view_feature("１２０") == "dimensions"
    assert fc.classify_drawing_view_feature("２２．７±０．０２") == "geometric_tolerances"
    assert fc.classify_drawing_view_feature("⌀１２０") == "hole_properties"


def test_bare_section_label_is_an_additional_view():
    """REVERSES an earlier decision in this same file, deliberately.

    This previously asserted `Ａ－Ａ` must stay `other`, on the reasoning that a section-marker
    label is not an engineering callout and NFKC folding must not make it start claiming a
    feature. The anti-folding half of that still holds and is tested above; the conclusion did
    not. `other` is "Other / Unclassified" — the bucket for findings the system could not
    identify — so filing a section designation there states something false about it, and in
    review it reads as unexplained noise next to the real findings.

    `additional_views` ("Additional Views") is the taxonomy item for exactly this, and a
    section callout added between revisions is a genuine change worth reporting under a name.
    `断面Ａ－Ａ` (with the explicit keyword) has always classified this way; the bare
    designation this corpus actually writes now agrees with it.
    """
    assert fc.classify_drawing_view_feature("Ａ－Ａ") == "additional_views"
    assert fc.classify_drawing_view_feature("断面Ａ－Ａ") == "additional_views"


def test_classify_drawing_view_feature_welding_symbol():
    assert fc.classify_drawing_view_feature("△ fillet weld") == "welding_symbol"


def test_classify_drawing_view_feature_machining_symbol():
    assert fc.classify_drawing_view_feature("∇ finish") == "machining_symbol"


def test_classify_drawing_view_feature_additional_views():
    assert fc.classify_drawing_view_feature("Section A-A") == "additional_views"
    assert fc.classify_drawing_view_feature("詳細図") == "additional_views"


def test_classify_drawing_view_feature_dimensions():
    assert fc.classify_drawing_view_feature("140.5") == "dimensions"


def test_classify_drawing_view_feature_unmatched_falls_to_other():
    assert fc.classify_drawing_view_feature("random annotation text") == taxonomy.OTHER_FEATURE_KEY


def test_classify_notes_feature_defaults_to_standard():
    assert fc.classify_notes_feature("Deburr all edges") == "standard_notes"


def test_classify_notes_feature_special():
    assert fc.classify_notes_feature("Heat treat to HRC 45") == "special_notes"


def test_classify_iso_feature_always_other():
    assert fc.classify_iso_feature("anything") == taxonomy.OTHER_FEATURE_KEY


def test_classify_title_ul_feature_machine_name():
    assert fc.classify_title_ul_feature("Unit No.") == "machine_name"


def test_classify_title_ul_feature_quantity():
    assert fc.classify_title_ul_feature("Q'ty") == "quantity"


def test_classify_title_ul_feature_unmatched():
    assert fc.classify_title_ul_feature("Random Header") == taxonomy.OTHER_FEATURE_KEY


# ─── marking_builder.py::inject_title_block_markings / inject_bom_markings ────

def test_inject_title_block_markings_sets_feature_from_field_map():
    clean_markings = []
    ref_fields = {"SCALE": {"value": "1:1", "coordinates": [10.0, 10.0]}}
    rev_fields = {"SCALE": {"value": "1:2", "coordinates": [10.0, 10.0]}}
    inject_title_block_markings(clean_markings, ref_fields, rev_fields, [], [])
    scale_marking = next(m for m in clean_markings if "SCALE" in m["details"])
    assert scale_marking["feature"] == "scale"


def test_inject_title_block_markings_unmapped_field_falls_to_other():
    clean_markings = []
    ref_fields = {"STD NO": {"value": "JIS-1", "coordinates": [10.0, 10.0]}}
    rev_fields = {"STD NO": {"value": "JIS-1", "coordinates": [10.0, 10.0]}}
    inject_title_block_markings(clean_markings, ref_fields, rev_fields, [], [])
    std_marking = next(m for m in clean_markings if "Std. No." in m["details"])
    assert std_marking["feature"] == taxonomy.OTHER_FEATURE_KEY


def test_inject_bom_markings_sets_feature_from_col_map():
    # is_blank_spacer_local() (non-assembly drawings) treats a row with no CODE/DIMENSION
    # value as a blank spacer and drops it entirely — CODE must be populated for the row
    # to survive filtering, even though this test is only exercising the QTY column.
    clean_markings = []
    ref_rows = [{
        "NO": {"value": "1", "coordinates": [0.0, 100.0]},
        "CODE": {"value": "ABC", "coordinates": [0.0, 100.0]},
        "QTY": {"value": "2", "coordinates": [0.0, 100.0]},
    }]
    rev_rows = [{
        "NO": {"value": "1", "coordinates": [0.0, 100.0]},
        "CODE": {"value": "ABC", "coordinates": [0.0, 100.0]},
        "QTY": {"value": "3", "coordinates": [0.0, 100.0]},
    }]
    inject_bom_markings(
        clean_markings, ref_rows, rev_rows, is_assembly_drawing=False,
        ref_bom_bbox=None, rev_bom_bbox=None, ref_entities=[], rev_entities=[],
        used_ref_entities=set(), used_rev_entities=set(),
    )
    qty_marking = next(m for m in clean_markings if "Q'ty" in m["details"])
    assert qty_marking["feature"] == "quantity"


# ─── marking_builder.py::inject_ballooning_markings ───────────────────────────

def test_inject_ballooning_markings_flags_new_orphan_balloon_in_revision():
    clean_markings = []
    rev_circle, rev_text = _circle_and_number(50.0, 50.0, 5.0, "3")
    inject_ballooning_markings(clean_markings, ref_bom_rows=[], rev_bom_rows=[], ref_entities=[], rev_entities=[rev_circle, rev_text])
    assert len(clean_markings) == 1
    assert clean_markings[0]["feature"] == "ballooning"
    assert clean_markings[0]["status"] == "ADDED"
    assert clean_markings[0]["category"] == "bill_of_materials"


def test_inject_ballooning_markings_skips_preexisting_issue_present_in_both():
    ref_circle, ref_text = _circle_and_number(50.0, 50.0, 5.0, "3")
    rev_circle, rev_text = _circle_and_number(50.0, 50.0, 5.0, "3")
    clean_markings = []
    inject_ballooning_markings(clean_markings, ref_bom_rows=[], rev_bom_rows=[], ref_entities=[ref_circle, ref_text], rev_entities=[rev_circle, rev_text])
    assert clean_markings == []


def test_inject_ballooning_markings_flags_new_unlinked_bom_row():
    clean_markings = []
    rev_bom_rows = [{"NO": {"value": "7", "coordinates": [0.0, 100.0]}}]
    inject_ballooning_markings(clean_markings, ref_bom_rows=[], rev_bom_rows=rev_bom_rows, ref_entities=[], rev_entities=[])
    assert len(clean_markings) == 1
    assert clean_markings[0]["feature"] == "ballooning"
    assert "7" in clean_markings[0]["text_content"]


# ─── title_block_extractor.py::extract_title_block — REVISION CODE ────────────

def test_extract_title_block_revision_code_present():
    entities = [_text_entity("AMD.", 100.0, 50.0), _text_entity("T1", 100.0, 40.0)]
    res = extract_title_block(entities, all_text_list=[e.properties["text"] for e in entities])
    assert res["REVISION CODE"]["value"] == "T1"
    assert res["REVISION CODE"]["coordinates"] is not None


def test_extract_title_block_revision_code_absent_returns_none_not_fabricated():
    entities = [_text_entity("SCALE", 100.0, 50.0), _text_entity("1:2", 100.0, 40.0)]
    res = extract_title_block(entities, all_text_list=[e.properties["text"] for e in entities])
    assert res["REVISION CODE"]["value"] == "NONE"
    assert res["REVISION CODE"]["coordinates"] is None


# ─── feature_classifier.py — section designations & their arrow labels ────────
#
# A section callout arrives as three findings: the `Ａ－Ａ` designation titling the section and
# a lone `Ａ` at each cut arrow. All three used to land in "Other / Unclassified" — the bucket
# meaning "the system could not tell what this is" — so an added section callout read as three
# unexplained entries even though `additional_views` already existed for exactly this.


def test_classify_bare_section_designation():
    # The keyword list only had the spelled-out `view a-a`; this corpus writes the designation
    # alone and fullwidth (`Ａ－Ａ` NFKC-folds to `A-A`).
    assert fc.classify_drawing_view_feature("A-A") == "additional_views"
    assert fc.classify_drawing_view_feature("Ａ－Ａ") == "additional_views"
    assert fc.classify_drawing_view_feature("B — B") == "additional_views"


def test_section_designation_requires_the_same_letter_twice():
    # `A-B` is a range or a part code, not a section. Guessing here would be the false
    # confidence the module docstring refuses.
    assert fc.classify_drawing_view_feature("A-B") == "other"


def test_lone_letter_is_refiled_only_when_its_section_exists_on_the_drawing():
    markings = [
        {"text_content": "Ａ－Ａ", "feature": "additional_views"},
        {"text_content": "Ａ", "feature": "other"},   # this section's arrow
        {"text_content": "Ｂ", "feature": "other"},   # unrelated — no B-B on this drawing
    ]
    fc.refine_view_labels(markings)
    assert [m["feature"] for m in markings] == [
        "additional_views", "additional_views", "other",
    ]


def test_lone_letter_untouched_when_the_drawing_has_no_section_designation():
    markings = [{"text_content": "Ａ", "feature": "other"}]
    fc.refine_view_labels(markings)
    assert markings[0]["feature"] == "other"


def test_refine_view_labels_does_not_overwrite_a_confident_classification():
    # A finding already filed as a real feature keeps it, even if its text is a lone letter.
    markings = [
        {"text_content": "A-A", "feature": "additional_views"},
        {"text_content": "Ａ", "feature": "dimensions"},
    ]
    fc.refine_view_labels(markings)
    assert markings[1]["feature"] == "dimensions"


def test_refine_view_labels_returns_the_callout_labels_for_suppression():
    # The return value is what orchestrator.DROP_SECTION_CALLOUT_LABELS drops. It must be the
    # designation plus its arrows and nothing else — narrower than "everything classified
    # additional_views", which also holds real content like `詳細Ｂ 尺度2:1`.
    designation = {"text_content": "Ａ－Ａ", "feature": "additional_views"}
    arrow = {"text_content": "Ａ", "feature": "other"}
    detail = {"text_content": "詳細Ｂ 尺度2:1", "feature": "additional_views"}
    unrelated = {"text_content": "Ｂ", "feature": "other"}

    labels = fc.refine_view_labels([designation, arrow, detail, unrelated])

    assert [m["text_content"] for m in labels] == ["Ａ－Ａ", "Ａ"]
    assert detail not in labels, "a detail view carrying a scale is real content, not a label"
    assert unrelated not in labels


def test_refine_view_labels_returns_empty_without_a_section_designation():
    assert fc.refine_view_labels([{"text_content": "Ａ", "feature": "other"}]) == []
