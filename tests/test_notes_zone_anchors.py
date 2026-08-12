"""A `notes` anchor must not match sheet furniture.

An anchor that also occurs outside the notes block does not merely add noise. The zone's box is
fitted to the matched cluster, so a match in the title or tolerance area drags the box across the
sheet and it ends up covering **neither** the furniture nor the real notes. That is the
false-negative direction: content in no zone is out of scope by the annotation guideline, and the
engine does not compare it either.

Measured on the corpus 2026-08-12, and both halves are pinned here:
  - removing `仕上げ` took notes rows inside the detected box from 16/45 to 27/45, and the three
    `M7452A*` reference sides from 0/3 to 3/3;
  - adding `ロール` appeared to reach 39/45 but landed the notes box **100% inside `tolerance`**
    on three sides, because the box inflated to span the roll counts and the drawing title.

See `docs/vault/06 - .../Gotcha - One Zone Template Cannot Fit Two Sides.md`.
"""
import pytest

from services.backend.infrastructure.audit.bom.zone_detector import ZONE_ANCHORS

# Terms that appear in this client's sheet furniture — title block, tolerance block, BOM header —
# and therefore cannot serve as a `notes` anchor however note-like they read.
FURNITURE_TERMS = {
    "仕上げ記号": "the finish-symbol label in the bottom-left tolerance block",
    "ロールカセット": "this drawing family's own title",
    "仕上重量": "a BOM column header",
    "材料寸法": "a BOM column header",
}


@pytest.mark.parametrize("term,where", sorted(FURNITURE_TERMS.items()))
def test_no_notes_anchor_matches_sheet_furniture(term, where):
    """No anchor may be a substring of a furniture term — that is how the match fires."""
    offenders = [a for a in ZONE_ANCHORS["notes"] if a and a in term]
    assert not offenders, (
        f"{offenders} would match {term!r} ({where}), dragging the `notes` box toward it. "
        "An anchor must appear ONLY in a note."
    )


def test_the_finish_symbol_anchor_stays_removed():
    """Named explicitly, because the general rule above would not survive someone re-adding it
    with a rationale — this records that it was measured and rejected, not overlooked."""
    assert "仕上げ" not in ZONE_ANCHORS["notes"]


def test_the_roll_anchor_was_measured_and_rejected():
    """`ロール` reaches the roll-count lines and is still wrong; see the module docstring."""
    assert "ロール" not in ZONE_ANCHORS["notes"]


def test_the_notes_anchors_that_carry_the_corpus_are_still_present():
    """The three standard note lines on every revision are found through these. Losing one is a
    silent regression: the zone falls back to the percentage grid and still returns *a* box."""
    for anchor in ("面取り", "なきこと", "角部は", "キリ粉"):
        assert anchor in ZONE_ANCHORS["notes"], f"{anchor!r} is load-bearing for this corpus"
