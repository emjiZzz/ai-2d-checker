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
