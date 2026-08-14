"""Tests for line_attribute_differ — the `line_attributes` checklist sub-item.

The defect these pin is not a wrong answer, it is a missing one: `line_attributes` had no
producer at all, so its card fell through to the "No changes detected." empty state on every
comparison. A check that never ran, reporting clean.

The behavioural cases below are the ones that decide whether this is useful or is the
reverted `geometry_differ` again — chiefly `test_a_stroke_count_difference_is_never_a_change`,
which is the whole reason presence and not counting drives the status.
"""
from types import SimpleNamespace

import pytest

from services.backend.infrastructure.audit.comparison import taxonomy
from services.backend.infrastructure.audit.comparison.line_attribute_differ import (
    CONTINUOUS,
    FEATURE_KEY,
    build_layer_linetypes,
    diff_line_attributes,
    profile_line_attributes,
    resolve_linetype,
    resolve_lineweight_mm,
)


def _stroke(
    entity_type: str = "line",
    linetype: str = "CONTINUOUS",
    lineweight: int = 25,
    layer: str = "0",
    color: int = 256,
) -> SimpleNamespace:
    """Duck-typed ExtractedEntity: the differ reads entity_type/layer/properties via getattr."""
    return SimpleNamespace(
        entity_type=entity_type,
        layer=layer,
        properties={"linetype": linetype, "lineweight": lineweight, "color": color},
        geometry={"start": [0.0, 0.0], "end": [1.0, 0.0]},
    )


def _layer(name: str, linetype: str = "Continuous", lineweight: int = 25, color: int = 7):
    return SimpleNamespace(
        entity_type="layer",
        layer=name,
        properties={"linetype": linetype, "lineweight": lineweight, "color": color},
        geometry={},
    )


def _rows_by_text(markings: list[dict]) -> dict[str, dict]:
    return {m["text_content"]: m for m in markings}


# --------------------------------------------------------------------------------------
# Attribute resolution
# --------------------------------------------------------------------------------------


def test_bylayer_linetype_resolves_through_the_layer_table():
    """The corpus draws centre lines by setting the LAYER's linetype, not the entity's."""
    layers = build_layer_linetypes([_layer("CENTRELINES", linetype="CENTER")])

    assert resolve_linetype(_stroke(linetype="BYLAYER", layer="CENTRELINES"), layers) == "CENTER"


@pytest.mark.parametrize("name", ["CONTINUOUS", "Continuous", "BYBLOCK", "SOLID", ""])
def test_every_name_meaning_no_pattern_collapses_to_one_row(name):
    """Three aliases for 'solid' would otherwise split one line attribute across three rows."""
    assert resolve_linetype(_stroke(linetype=name), {}) == CONTINUOUS


def test_an_unset_linetype_falls_back_to_the_layer_not_to_solid():
    """An entity with no linetype of its own is BYLAYER by DXF rule, not CONTINUOUS."""
    layers = build_layer_linetypes([_layer("HID", linetype="HIDDEN")])
    entity = SimpleNamespace(entity_type="line", layer="HID", properties={}, geometry={})

    assert resolve_linetype(entity, layers) == "HIDDEN"


def test_lineweight_sentinels_are_not_read_as_widths():
    """-1/-2/-3 are 'look elsewhere', not 0.01mm. See GeometrySerializer._resolve_lineweight."""
    layers = {"THICK": 100}

    assert resolve_lineweight_mm(_stroke(lineweight=-1, layer="THICK"), layers) == 1.0
    assert resolve_lineweight_mm(_stroke(lineweight=50), layers) == 0.5
    # DEFAULT, and a layer that is itself BYLAYER, both mean $LWDEFAULT.
    assert resolve_lineweight_mm(_stroke(lineweight=-3), layers) == 0.25


# --------------------------------------------------------------------------------------
# Profiling
# --------------------------------------------------------------------------------------


def test_only_stroke_geometry_is_profiled():
    """A dimension's stroke is chosen by its dimension style, not by the drafter, and its text
    is already compared by SpatialDiffer. Profiling it would report a drafting decision nobody
    made."""
    entities = [
        _stroke("line"),
        _stroke("circle"),
        _stroke("arc"),
        _stroke("polyline"),
        _stroke("dimension"),
        _stroke("leader"),
        _stroke("text"),
        _stroke("hatch"),
    ]

    profile = profile_line_attributes(entities, {}, {})

    assert sum(b["count"] for b in profile.values()) == 4


def test_colour_does_not_split_a_row():
    """The cut plane and the part centreline are both CENTER 0.25mm and differ only by ACI —
    a client convention, not a line attribute. Measured: keying on colour takes the median
    sheet from 5 rows to 11."""
    entities = [
        _stroke(linetype="CENTER", lineweight=25, color=4),
        _stroke(linetype="CENTER", lineweight=25, color=8),
    ]

    profile = profile_line_attributes(entities, {}, {})

    assert list(profile) == [("CENTER", 0.25)]
    assert profile[("CENTER", 0.25)]["count"] == 2


# --------------------------------------------------------------------------------------
# The diff
# --------------------------------------------------------------------------------------


def test_the_card_is_filled_when_both_drawings_are_identical():
    """The regression this whole module exists for. Two identical sheets previously produced
    zero line_attributes findings, so the card rendered 'No changes detected.' — a clean
    result from a check that never ran."""
    entities = [_stroke(linetype="CENTER"), _stroke(), _stroke()]

    markings = diff_line_attributes(entities, list(entities), entities, list(entities))

    assert len(markings) == 2
    assert {m["status"] for m in markings} == {"MATCHED"}
    assert {m["feature"] for m in markings} == {FEATURE_KEY}
    assert {m["category"] for m in markings} == {"drawing_views"}


def test_a_stroke_count_difference_is_never_a_change():
    """A revision is a re-trace, not a copy, so stroke counts differ on nearly every real pair.
    geometry_differ was reverted for exactly this class of finding: a count carries no
    engineering meaning, and firing CHANGED on every comparison trains a checker to skim past
    the panel."""
    ref = [_stroke(linetype="CENTER")] * 9
    rev = [_stroke(linetype="CENTER")] * 12

    markings = diff_line_attributes(ref, rev, ref, rev)

    assert [m["status"] for m in markings] == ["MATCHED"]
    # The counts are still reported — hidden is not the same as not-a-status.
    assert "x9" in markings[0]["original_value"]
    assert "x12" in markings[0]["text_content"]


def test_a_line_type_only_the_revision_uses_is_reported_added():
    ref = [_stroke()]
    rev = [_stroke(), _stroke(linetype="HIDDEN", lineweight=35)]

    markings = diff_line_attributes(ref, rev, ref, rev)
    rows = _rows_by_text(markings)

    added = [m for m in markings if m["status"] == "ADDED"]
    assert len(added) == 1
    assert "HIDDEN" in added[0]["text_content"]
    assert added[0]["original_value"] is None
    assert rows["CONTINUOUS 0.25mm x1"]["status"] == "MATCHED"


def test_a_line_type_only_the_reference_uses_is_reported_removed():
    """The finding that motivates the whole item: HIDDEN appears twice in the entire corpus,
    so a hidden line silently becoming solid is precisely what a checker cannot spot by eye."""
    ref = [_stroke(), _stroke(linetype="HIDDEN", lineweight=35)]
    rev = [_stroke()]

    markings = diff_line_attributes(ref, rev, ref, rev)

    removed = [m for m in markings if m["status"] == "REMOVED"]
    assert len(removed) == 1
    assert "HIDDEN" in removed[0]["text_content"]
    # build_marking_table reads original_value for the ORIGINAL cell of a REMOVED row; leaving
    # it None would blank the only side that has a value.
    assert removed[0]["original_value"] == removed[0]["text_content"]


def test_the_same_line_type_at_two_thicknesses_is_two_rows():
    """0.25mm and 0.5mm CONTINUOUS are the thin/thick line pair of every drafting standard;
    collapsing them would hide an outline drawn at construction-line weight."""
    ref = [_stroke(lineweight=25), _stroke(lineweight=50)]
    rev = [_stroke(lineweight=25)]

    markings = diff_line_attributes(ref, rev, ref, rev)

    assert len(markings) == 2
    assert [m["status"] for m in markings] == ["REMOVED", "MATCHED"]


def test_layer_records_are_read_from_the_full_entity_list_not_the_zone_pool():
    """A `layer` record has no geometry, so `entity_anchor` returns None and
    `scope_entities_to_views` drops it. Resolving BYLAYER against the scoped pool would find
    an empty table and file every centre line under CONTINUOUS."""
    strokes = [_stroke(linetype="BYLAYER", layer="CL")]
    all_entities = strokes + [_layer("CL", linetype="CENTER", lineweight=25)]

    markings = diff_line_attributes(strokes, list(strokes), all_entities, list(all_entities))

    assert markings[0]["text_content"].startswith("CENTER")


def test_markings_carry_no_coordinates():
    """A profile row describes every stroke of one kind across the whole view, so there is no
    single point a canvas pin could honestly sit at."""
    entities = [_stroke()]

    markings = diff_line_attributes(entities, list(entities), entities, list(entities))

    assert "coordinates" not in markings[0]
    assert "ref_coordinates" not in markings[0]


def test_rows_are_ordered_heaviest_first_and_are_stable():
    ref = [
        _stroke(lineweight=25),
        _stroke(lineweight=100),
        _stroke(linetype="CENTER", lineweight=25),
    ]

    first = diff_line_attributes(ref, list(ref), ref, list(ref))
    second = diff_line_attributes(ref, list(ref), ref, list(ref))

    assert [m["text_content"] for m in first] == [m["text_content"] for m in second]
    assert first[0]["text_content"].startswith("CONTINUOUS 1mm")


def test_neither_side_having_strokes_produces_no_rows():
    """A sheet with no `views` box contributes nothing — strict scoping, no invented rows."""
    assert diff_line_attributes([], [], [], []) == []


def test_the_feature_key_is_a_real_taxonomy_item():
    """Guards the hand-mirrored taxonomy: a typo here would file every row under
    'Other / Unclassified' and leave the Line Attributes card empty exactly as before."""
    keys = {item.key for item in taxonomy.TAXONOMY["drawing_views"]}

    assert FEATURE_KEY in keys
    assert FEATURE_KEY not in taxonomy.DEFERRED_FEATURES
