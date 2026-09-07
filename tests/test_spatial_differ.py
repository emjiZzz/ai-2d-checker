"""
Tests for SpatialDiffer (services/backend/infrastructure/audit/comparison/spatial_differ.py).

This module had zero pytest coverage despite two targeted fixes landing in it during the
2026-07-20 security-remediation pass (docs/security-remediation-implementation-plan.md,
Phase D, finding #4): (1) calculate_global_offset picking the nearest ref coordinate
candidate instead of the first one in list order when a normalized text string has
multiple ref entities (e.g. repeated dimension labels), and (2) the widened second
spatial-matching pass being restricted to same-text-only pairs, so a long-range match
between genuinely different text is never silently accepted as a "structural edit".
That plan's own completion log flagged this as verified only at the isolated-logic-script
level, never through a real pytest case — these tests close that gap.
"""
from types import SimpleNamespace

import pytest

from services.backend.infrastructure.audit.comparison.spatial_differ import SpatialDiffer


def _text_entity(text: str, x: float, y: float, handle: str = "") -> SimpleNamespace:
    """
    Duck-typed stand-in for ExtractedEntity: SpatialDiffer only ever reads
    entity_type/properties/geometry via getattr(), so a real Beanie Document isn't
    needed (and would require init_beanie()/a live Mongo connection just to
    construct, since Document.__init__ resolves its collection eagerly).
    """
    return SimpleNamespace(
        entity_type="text",
        properties={"text": text, "handle": handle or text},
        geometry={"insert": [x, y]},
    )


def test_calculate_global_offset_uses_nearest_candidate_not_first_in_list_order():
    """
    Two ref entities share the same normalized text ("PART5"), at very different
    locations. The rev entity is close to the *second* one in list order. The offset
    must be computed from the nearest candidate — if it picked the first instead, the
    returned offset would be wildly wrong (~995 units off instead of ~5).
    """
    ref_entities = [
        _text_entity("PART5", 1000.0, 1000.0, handle="far"),   # listed first, far from rev
        _text_entity("PART5", 0.0, 0.0, handle="near"),        # listed second, near rev
    ]
    rev_entities = [_text_entity("PART5", 5.0, 5.0)]

    offset_x, offset_y, is_mismatch = SpatialDiffer.calculate_global_offset(ref_entities, rev_entities)

    assert offset_x == pytest.approx(5.0, abs=0.1)
    assert offset_y == pytest.approx(5.0, abs=0.1)
    assert is_mismatch is False


def test_diff_views_widened_pass_never_pairs_different_text():
    """
    A rev entity ("C5") has no same-text match anywhere, but an unrelated ref entity
    with different text ("R2") sits within the widened second-pass search radius.
    Cross-text pairing in the widened pass would falsely report this as a CHANGED
    dimension ("R2" -> "C5") instead of correctly reporting an independent ADDED +
    REMOVED pair.
    """
    # Four exact-match pairs (dist 0) to push the strict-mode match rate to
    # >= 0.80, so is_digital_twin=True and the widened threshold is a known 150.0
    # (max(150.0, 10.0 * 5.0)) rather than depending on fuzzy-mode's wider auto value.
    matched_pairs_ref = [_text_entity(f"OK{i}", i * 10.0, i * 10.0, handle=f"ok{i}-ref") for i in range(1, 5)]
    matched_pairs_rev = [_text_entity(f"OK{i}", i * 10.0, i * 10.0, handle=f"ok{i}-rev") for i in range(1, 5)]

    ref_entities = matched_pairs_ref + [_text_entity("R2", 520.0, 510.0, handle="r2-ref")]
    rev_entities = matched_pairs_rev + [_text_entity("C5", 500.0, 500.0, handle="c5-rev")]
    # distance(R2, C5) ~= 22.4 -> outside pass-1 threshold (10.0 in digital-twin mode),
    # inside the widened pass-2 threshold (150.0) -> exactly the false-pair scenario.

    markings = SpatialDiffer.diff_views(ref_entities, rev_entities)

    c5_marking = next(m for m in markings if m["text_content"] == "C5")
    r2_marking = next(m for m in markings if m["text_content"] == "R2")

    assert c5_marking["status"] == "ADDED"
    assert r2_marking["status"] == "REMOVED"
    # Neither marking may claim the other's text as its paired original/changed value.
    assert "R2" not in str(c5_marking.get("original_value", ""))
    assert c5_marking["status"] != "CHANGED"


# --- Standard (pass 1) similarity gate: an in-place CHANGED requires the two strings to be
#     a plausible edit of each other, not merely co-located. See CHANGED_SIMILARITY_FLOOR.

def _twin_fillers():
    """Four exact-match pairs so the strict match rate is >= 0.80 (digital-twin mode, pass-1
    threshold 10.0), placed far from the (500, 500) test region."""
    ref = [_text_entity(f"OK{i}", i * 10.0, i * 10.0, handle=f"ok{i}-ref") for i in range(1, 5)]
    rev = [_text_entity(f"OK{i}", i * 10.0, i * 10.0, handle=f"ok{i}-rev") for i in range(1, 5)]
    return ref, rev


def test_diff_views_does_not_pair_unrelated_text_as_changed():
    """Two DIFFERENT, co-located strings that are not a plausible edit of each other must
    surface as REMOVED + ADDED, never a single CHANGED. This is the notes false-pairing fix:
    '2 ロール：4' was reported as CHANGED into an unrelated fabrication note purely because the
    two sat close together on the sheet."""
    ref, rev = _twin_fillers()
    ref.append(_text_entity("APPLE ORCHARD", 500.0, 500.0, handle="a-ref"))
    rev.append(_text_entity("ZEBRA CROSSING", 501.0, 501.0, handle="z-rev"))  # dist ~1.4, in pass-1 range

    markings = SpatialDiffer.diff_views(ref, rev)
    removed = next(m for m in markings if m["text_content"] == "APPLE ORCHARD")
    added = next(m for m in markings if m["text_content"] == "ZEBRA CROSSING")

    assert removed["status"] == "REMOVED"
    assert added["status"] == "ADDED"
    assert not any(m["status"] == "CHANGED" for m in markings)


def test_diff_views_keeps_a_plausible_in_place_edit_as_changed():
    """The gate must not over-suppress genuine edits: a co-located pair with high character
    overlap ('TORQUE 45NM' -> 'TORQUE 50NM') stays a single CHANGED."""
    ref, rev = _twin_fillers()
    ref.append(_text_entity("TORQUE 45NM", 500.0, 500.0, handle="t-ref"))
    rev.append(_text_entity("TORQUE 50NM", 501.0, 501.0, handle="t-rev"))

    markings = SpatialDiffer.diff_views(ref, rev)
    changed = next(m for m in markings if m["text_content"] == "TORQUE 50NM")

    assert changed["status"] == "CHANGED"
    assert changed["original_value"] == "TORQUE 45NM"


def test_diff_views_keeps_numeric_value_change_as_changed():
    """Two dimension values ('130' -> '125') share few characters but are a real edit, so the
    numeric-both bypass keeps them a CHANGED rather than splitting into REMOVED + ADDED."""
    ref, rev = _twin_fillers()
    ref.append(_text_entity("130", 500.0, 500.0, handle="d-ref"))
    rev.append(_text_entity("125", 501.0, 501.0, handle="d-rev"))

    markings = SpatialDiffer.diff_views(ref, rev)
    changed = next(m for m in markings if m["text_content"] == "125")

    assert changed["status"] == "CHANGED"
    assert changed["original_value"] == "130"


def _dimension_entity(text: str, x: float, y: float, measurement: float,
                      dim_type: int = 160, handle: str = "") -> SimpleNamespace:
    """A DXF DIMENSION: value in `properties.measurement`, position under `text_point`.

    Note there is deliberately NO `insert` key — dimension geometry does not have one, which
    is exactly why _get_entity_coords used to resolve every dimension to (0.0, 0.0).
    """
    return SimpleNamespace(
        entity_type="dimension",
        properties={"text": text, "measurement": measurement,
                    "dim_type": dim_type, "handle": handle or text},
        geometry={"text_point": [x, y], "def_point": [x, y - 5.0]},
    )


def test_dimensions_are_compared_at_all():
    """Regression: the pools filtered `entity_type == 'text'`, so every DIMENSION on every
    drawing was dropped before comparison and could never receive a checkmark."""
    ref = [_dimension_entity("%%c120", 100.0, 100.0, 120.0)] + _twin_fillers()[0]
    rev = [_dimension_entity("120", 100.0, 100.0, 120.0)] + _twin_fillers()[1]
    dims = [m for m in SpatialDiffer.diff_views(ref, rev) if "120" in m["text_content"]]
    assert len(dims) == 1, dims
    assert dims[0]["status"] == "MATCHED"


def test_unchanged_dimension_matches_despite_different_display_text():
    """The same unchanged dimension is authored as a `%%c120` text override on one sheet and
    left to the dimension style on the other — both render ⌀120. Comparing display text gives
    a false CHANGED; the numeric `measurement` is what actually decides."""
    ref = [_dimension_entity("%%c120", 100.0, 100.0, 120.0)] + _twin_fillers()[0]
    # Float noise of the magnitude really present in the corpus (140.0000000000002 vs ...5).
    rev = [_dimension_entity("120", 100.0, 100.0, 120.0000000000002)] + _twin_fillers()[1]
    m = next(m for m in SpatialDiffer.diff_views(ref, rev) if "120" in m["text_content"])
    assert m["status"] == "MATCHED", m


def test_changed_dimension_measurement_is_reported():
    """The other side of the same guard: a real size change must still surface."""
    ref = [_dimension_entity("120", 100.0, 100.0, 120.0)] + _twin_fillers()[0]
    rev = [_dimension_entity("125", 100.0, 100.0, 125.0)] + _twin_fillers()[1]
    m = next(m for m in SpatialDiffer.diff_views(ref, rev) if "12" in m["text_content"])
    assert m["status"] == "CHANGED", m
    assert m["original_value"] == "120"


def test_dimension_coordinates_come_from_text_point_not_the_origin():
    """Dimension geometry has no `insert`. Reading only that key resolved every dimension to
    (0, 0), which would stack the whole set on the sheet origin instead of on its feature."""
    ref = [_dimension_entity("%%c120", 640.0, 480.0, 120.0)] + _twin_fillers()[0]
    rev = [_dimension_entity("120", 640.0, 480.0, 120.0)] + _twin_fillers()[1]
    m = next(m for m in SpatialDiffer.diff_views(ref, rev) if "120" in m["text_content"])
    assert m["coordinates"] == [640.0, 480.0]
    assert m["ref_coordinates"] == [640.0, 480.0]


def test_a_dimension_never_pairs_with_a_text_of_the_same_number():
    """Dimension keys are measurements, not strings, so without a kind gate a stray '120'
    label sitting on top of a 120mm dimension would pair with it."""
    ref = [_text_entity("120", 100.0, 100.0)] + _twin_fillers()[0]
    rev = [_dimension_entity("120", 100.0, 100.0, 120.0)] + _twin_fillers()[1]
    statuses = {m["status"] for m in SpatialDiffer.diff_views(ref, rev) if m["text_content"] == "120"}
    assert statuses == {"ADDED", "REMOVED"}, statuses


def test_diameter_and_linear_dimensions_of_equal_size_are_not_silently_matched():
    """dim_type's low bits carry the dimension KIND: a linear 120 is not a diameter 120."""
    ref = [_dimension_entity("120", 100.0, 100.0, 120.0, dim_type=160)] + _twin_fillers()[0]   # linear
    rev = [_dimension_entity("%%c120", 100.0, 100.0, 120.0, dim_type=163)] + _twin_fillers()[1]  # diameter
    m = next(m for m in SpatialDiffer.diff_views(ref, rev) if "120" in m["text_content"])
    assert m["status"] == "CHANGED", m


def test_dimension_display_text_resolves_the_diameter_escape():
    """`%%c` must render as ⌀ in the checklist label, and a literal ± must survive intact —
    safe_decode's mojibake repair turns ± into halfwidth katakana ｱ, so dimensions skip it."""
    ref = [_dimension_entity("%%c120", 100.0, 100.0, 120.0),
           _dimension_entity("22.7±0.02", 200.0, 200.0, 22.7)] + _twin_fillers()[0]
    rev = [_dimension_entity("%%c125", 100.0, 100.0, 125.0),
           _dimension_entity("22.9±0.02", 200.0, 200.0, 22.9)] + _twin_fillers()[1]
    texts = {m["text_content"] for m in SpatialDiffer.diff_views(ref, rev)}
    assert "Ø125" in texts, texts
    assert "22.9±0.02" in texts, texts


def test_a_shifted_block_does_not_cross_pair_its_adjacent_lines():
    """Reported by the owner on M745227N01. Two production-count lines sit one row apart, and
    the whole block MOVED between revisions by more than half that row pitch. Ordering plausible
    cross-text pairs by proximity alone then makes each line's nearest neighbour its SIBLING, and
    the engine reported `4 ロール：12 (2x6台)` -> `２ロール：　４（２×２台）` — a false finding that
    reads as a 4-roll spec becoming a 2-roll spec. Each line is near-identical to its own
    counterpart and merely similar to its sibling, so similarity separates what distance cannot.

    Geometry mirrors the measured normalized positions: ref rows 24.6 apart, rev rows the same,
    with the whole rev block shifted UP 55 units — so ref-4roll is closer to rev-2roll (30.4)
    than to rev-4roll (55.0).
    """
    ref, rev = _twin_fillers()
    ref.append(_text_entity("4 ロール：12 (2x6台)", 500.0, 828.5, handle="r4-ref"))
    ref.append(_text_entity("2 ロール： 4 (2x2台)", 500.0, 803.9, handle="r2-ref"))
    rev.append(_text_entity("４ロール：１２（２×６台）", 500.0, 883.5, handle="r4-rev"))
    rev.append(_text_entity("２ロール：　４（２×２台）", 500.0, 858.9, handle="r2-rev"))

    markings = SpatialDiffer.diff_views(ref, rev)
    four = next(m for m in markings if m["text_content"] == "４ロール：１２（２×６台）")
    two = next(m for m in markings if m["text_content"] == "２ロール：　４（２×２台）")

    assert four["status"] in ("MATCHED", "CHANGED")
    assert two["status"] in ("MATCHED", "CHANGED")
    # The point of the test: each line pairs with ITS OWN counterpart, not its sibling.
    # When fully normalized (including Unicode multiplication symbol), they match cleanly.
    if four["status"] == "CHANGED":
        assert four["original_value"] == "4 ロール：12 (2x6台)"
    if two["status"] == "CHANGED":
        assert two["original_value"] == "2 ロール： 4 (2x2台)"


def test_similarity_can_never_let_a_cross_text_pair_beat_an_identical_one():
    """The similarity bonus is bounded far below the 1000 cross-text penalty. An identical-text
    pair further away must still win over a similar-text pair that is nearer, or the tie-break
    would have introduced a worse failure than the one it fixed."""
    ref, rev = _twin_fillers()
    ref.append(_text_entity("TORQUE 45NM", 500.0, 500.0, handle="same-ref"))
    rev.append(_text_entity("TORQUE 45NM", 508.0, 500.0, handle="same-rev"))
    rev.append(_text_entity("TORQUE 46NM", 501.0, 500.0, handle="near-rev"))

    markings = SpatialDiffer.diff_views(ref, rev)
    by_text = {m["text_content"]: m for m in markings if "TORQUE" in str(m["text_content"])}
    assert by_text["TORQUE 45NM"]["status"] == "MATCHED"
    assert by_text["TORQUE 46NM"]["status"] == "ADDED"
