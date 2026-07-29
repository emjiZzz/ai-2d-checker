"""Tests that the spatial differ matches across a scale difference between drawings.

Background, measured on the M7452A0N01 reference/revision pair:

The two sides of a comparison are not necessarily stored in the same coordinate space. A DXF
with no paper-space viewport is kept in model units; one with a viewport is projected to
paper units by `dxf_parser`. That pair came out at `coordinate_space: model` spanning 982.7
units versus `coordinate_space: paper` spanning 393.1 — exactly 2.500x apart:

    text          reference          revision          ratio
    FSRS2         623.6, 40.5        245.5, 16.5       2.54
    M7452A0N01    792.0, 40.5        311.5, 16.5       2.54
    津田           581.1, 90.2        232.3, 36.0       2.50
    2A0           136.9, 685.0       54.7, 273.0       2.50
    45            87.5, 685.0        35.0, 273.0       2.50

`calculate_global_offset` only ever estimated a *translation*, and the match thresholds were
absolute CAD units. A single offset cannot align a scale difference — the shift needed across
that sheet ranged from -52 to -480 — so unchanged title-block text was emitted as REMOVED on
the reference side and ADDED on the revision side, one unchanged label producing two false
findings.
"""
from types import SimpleNamespace

import pytest

from services.backend.infrastructure.audit.comparison.spatial_differ import (
    STRICT_RADIUS_ABS,
    STRICT_RADIUS_NORM,
    SpatialDiffer,
    _usable_bounds,
)

# The real render_bounds of the two drawings.
REF_BOUNDS = [-52.5, -37.125, 1102.5, 779.625]      # 1155.00 x 816.75, model space
REV_BOUNDS = [-21.0, -14.85, 441.0, 311.85]         # 462.00 x 326.70, paper space

# Measured positions of text that is IDENTICAL on both drawings.
SAME_TEXT = [
    ("FSRS2",      (623.6, 40.5),   (245.5, 16.5)),
    ("M7452A0N01", (792.0, 40.5),   (311.5, 16.5)),
    ("津田",        (581.1, 90.2),   (232.3, 36.0)),
    ("2A0",        (136.9, 685.0),  (54.7, 273.0)),
    ("45",         (87.5, 685.0),   (35.0, 273.0)),
]


def _text(x: float, y: float, txt: str, handle: str):
    return SimpleNamespace(
        entity_type="text", layer="0",
        properties={"text": txt, "handle": handle},
        geometry={"insert": [x, y]},
    )


def _corpus_entities():
    ref = [_text(x, y, t, f"R{i}") for i, (t, (x, y), _) in enumerate(SAME_TEXT)]
    rev = [_text(x, y, t, f"V{i}") for i, (t, _, (x, y)) in enumerate(SAME_TEXT)]
    return ref, rev


def _by_status(markings):
    out = {}
    for m in markings:
        out.setdefault(m["status"], []).append(m["text_content"])
    return out


def test_unchanged_text_across_a_scale_difference_matches():
    """The regression. Every string here is identical on both drawings."""
    ref, rev = _corpus_entities()

    markings = SpatialDiffer.diff_views(
        ref, rev, category="title_block",
        ref_bounds=REF_BOUNDS, rev_bounds=REV_BOUNDS,
    )

    by_status = _by_status(markings)
    assert by_status.get("ADDED", []) == [], f"false ADDED: {by_status.get('ADDED')}"
    assert by_status.get("REMOVED", []) == [], f"false REMOVED: {by_status.get('REMOVED')}"
    assert len(by_status.get("MATCHED", [])) == len(SAME_TEXT)


def test_scale_difference_appears_as_a_huge_translation_without_bounds():
    """States the defect itself, rather than one of its downstream symptoms.

    A scale difference cannot be modelled as a translation: each entity demands a different
    offset, growing with distance from the origin. Here the required shift ranges from -52.5
    (`45`, near the left edge) to -480.5 (`M7452A0N01`, far right) — a 428-unit spread that
    no single median can satisfy. Whether any *particular* label then survives via the
    widened same-text pass depends on how many entities are in the pool and where they sit,
    which is why this asserts the cause and not a specific ADDED/REMOVED count.
    """
    ref, rev = _corpus_entities()

    abs_dx, abs_dy, _ = SpatialDiffer.calculate_global_offset(ref, rev)
    norm_dx, norm_dy, _ = SpatialDiffer.calculate_global_offset(
        ref, rev, ref_bounds=REF_BOUNDS, rev_bounds=REV_BOUNDS
    )

    assert abs(abs_dx) > 100.0, (
        "without bounds the estimated offset should absorb the scale difference"
    )
    # Normalized, the same two drawings need essentially no translation at all.
    assert abs(norm_dx) < 0.02
    assert abs(norm_dy) < 0.02


def test_matched_output_coordinates_stay_in_cad_units():
    """Normalization is for matching only. Every consumer downstream — coordinate
    resolution, canvas pins, redline writeback — needs real drawing coordinates."""
    ref, rev = _corpus_entities()

    markings = SpatialDiffer.diff_views(
        ref, rev, category="title_block",
        ref_bounds=REF_BOUNDS, rev_bounds=REV_BOUNDS,
    )

    matched = [m for m in markings if m["status"] == "MATCHED"]
    assert matched
    for m in matched:
        cx, cy = m["coordinates"]
        rx, ry = m["ref_coordinates"]
        # Normalized values would all be within 0..1; real CAD coords here are >> 1.
        assert max(abs(cx), abs(cy)) > 1.5, f"revision coords look normalized: {m['coordinates']}"
        assert max(abs(rx), abs(ry)) > 1.5, f"reference coords look normalized: {m['ref_coordinates']}"

    # And they must be the actual measured positions, not merely un-normalized.
    coords = {m["text_content"]: (m["coordinates"], m["ref_coordinates"]) for m in matched}
    rev_c, ref_c = coords["45"]
    assert rev_c == pytest.approx([35.0, 273.0])
    assert ref_c == pytest.approx([87.5, 685.0])


def test_genuine_changes_are_still_detected_across_scales():
    """The fix must not collapse everything into MATCHED."""
    ref, rev = _corpus_entities()
    # A value that really did change, at the same relative sheet position.
    ref = ref + [_text(700.0, 300.0, "8.7", "R99")]
    rev = rev + [_text(280.0, 120.0, "8.65", "V99")]

    markings = SpatialDiffer.diff_views(
        ref, rev, category="bill_of_materials",
        ref_bounds=REF_BOUNDS, rev_bounds=REV_BOUNDS,
    )

    changed = [m for m in markings if m["status"] == "CHANGED"]
    assert len(changed) == 1
    assert changed[0]["text_content"] == "8.65"
    assert changed[0]["original_value"] == "8.7"


def test_genuinely_removed_text_is_still_reported():
    ref, rev = _corpus_entities()
    ref = ref + [_text(700.0, 300.0, "DELETED NOTE", "R99")]

    markings = SpatialDiffer.diff_views(
        ref, rev, category="notes_section",
        ref_bounds=REF_BOUNDS, rev_bounds=REV_BOUNDS,
    )

    assert _by_status(markings).get("REMOVED") == ["DELETED NOTE"]


def test_one_sided_bounds_fall_back_rather_than_normalizing_one_side():
    """Normalizing only one drawing would put the two in frames ~1000x apart."""
    ref, rev = _corpus_entities()

    only_ref = SpatialDiffer.diff_views(ref, rev, category="t", ref_bounds=REF_BOUNDS)
    only_rev = SpatialDiffer.diff_views(ref, rev, category="t", rev_bounds=REV_BOUNDS)
    neither = SpatialDiffer.diff_views(ref, rev, category="t")

    assert _by_status(only_ref) == _by_status(neither)
    assert _by_status(only_rev) == _by_status(neither)


def test_offset_is_computed_in_the_normalized_frame():
    """A pure scale difference must not masquerade as a large translation."""
    ref, rev = _corpus_entities()

    dx, dy, _ = SpatialDiffer.calculate_global_offset(
        ref, rev, ref_bounds=REF_BOUNDS, rev_bounds=REV_BOUNDS
    )

    # Same sheet layout at a different scale -> near-zero residual translation.
    assert abs(dx) < 0.02, f"normalized offset_x should be ~0, got {dx}"
    assert abs(dy) < 0.02, f"normalized offset_y should be ~0, got {dy}"


@pytest.mark.parametrize("bad", [None, [], [1, 2, 3], [0, 0, 0, 0], [10, 10, 5, 5]])
def test_unusable_bounds_are_rejected(bad):
    assert _usable_bounds(bad) is False


def test_thresholds_are_scale_relative_not_absolute():
    """Guards the constants themselves: the normalized radius must be a sheet fraction."""
    assert 0 < STRICT_RADIUS_NORM < 1.0
    assert STRICT_RADIUS_ABS >= 1.0
