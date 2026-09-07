"""Regression: which zones title extraction is allowed to read, and which it must not blank.

Two exclusions, one guard.

1. The detected/pinned tolerance box is frequently over-wide (spanning the full bottom strip),
   so a naive "exclude everything in the tolerance box" also deletes the bottom-right title
   block — DRAWN/SCALE/DESIGNED/TITLE then all read NONE, producing false ADDED title findings.
2. The upper-left table has its own extractor. The title block's QTY field searches for
   ``T. Q'ty`` / ``総製作個数``, the upper-left table's own column header, so it read that
   table's cell and the one physical cell appeared twice in the title_block checklist.

The guard for both: only drop an entity that is in the excluded box AND NOT in the title box.

See docs/title-block-false-findings-implementation-plan.md (Phase 2) and
docs/vault/06 - Gotchas & Debugging Lessons/
  Gotcha - Title Block QTY Reads the Upper-Left Table.md
"""
from types import SimpleNamespace

from services.backend.infrastructure.audit.comparison.orchestrator import (
    keep_for_title_extraction,
)

# Over-wide tolerance box (full bottom strip) and a title box that overlaps its right half —
# the real geometry from the M7452A1N01 pair (tolerance x45..1042, title x294..924, y overlap).
TOL = (45.0, 76.0, 1042.0, 299.0)
TITLE = (294.0, 39.0, 924.0, 299.0)


def _ent(x, y):
    return SimpleNamespace(geometry={"insert": [x, y, 0.0]})


def test_title_value_inside_overwide_tolerance_box_is_kept():
    # SCALE value at (654, 90): inside BOTH boxes → must be kept (it's real title content).
    assert keep_for_title_extraction(_ent(654, 90), TOL, TITLE) is True
    # DRAWN value at (617, 90): same.
    assert keep_for_title_extraction(_ent(617, 90), TOL, TITLE) is True


def test_tolerance_table_cell_outside_title_is_dropped():
    # A tolerance grid cell bottom-left (200, 90): in the tolerance box, NOT in the title box.
    assert keep_for_title_extraction(_ent(200, 90), TOL, TITLE) is False


def test_entities_outside_tolerance_box_are_kept():
    # Anything not in the tolerance box is always kept.
    assert keep_for_title_extraction(_ent(654, 400), TOL, TITLE) is True


def test_missing_title_box_falls_back_to_plain_tolerance_exclusion():
    # No title box (None) → behaves like the old exclusion: drop what's in the tolerance box.
    assert keep_for_title_extraction(_ent(654, 90), TOL, None) is False
    assert keep_for_title_extraction(_ent(654, 400), TOL, None) is True


# Measured `title_upper_left` and `title` from the reference sheet of the M7452A0N01 eval pair.
# The two boxes are far apart — the UL table sits at y≈700, the title block at y≈40..299.
UL = (65.7, 680.0, 241.1, 714.8)


def test_upper_left_table_cell_is_dropped_from_title_extraction():
    # The `T. Q'ty` label at its measured insert (172.9, 702.4). It is the upper-left table's
    # column header, and the title block's QTY field searches for exactly this string — so
    # leaving it in makes one cell surface as both `QTY (QUANTITY)` and `T. Q'TY / 総製作個数`.
    assert keep_for_title_extraction(_ent(172.9, 702.4), TOL, TITLE, UL) is False
    # Its value cell, one row below the header, goes with it.
    assert keep_for_title_extraction(_ent(172.9, 695.0), TOL, TITLE, UL) is False


def test_upper_left_exclusion_never_blanks_the_title_block():
    # Same protection the tolerance box gets: a mis-detected over-wide UL box must not delete
    # real title content, and a sheet whose bottom title block carries its own quantity cell
    # keeps it. Entity at (654, 90) is inside the title box and inside this over-wide UL box.
    overwide_ul = (45.0, 39.0, 1042.0, 714.8)
    assert keep_for_title_extraction(_ent(654, 90), TOL, TITLE, overwide_ul) is True


def test_title_block_entities_survive_the_upper_left_exclusion():
    # The real UL box does not reach the title block, so nothing there is affected.
    assert keep_for_title_extraction(_ent(654, 90), TOL, TITLE, UL) is True
    assert keep_for_title_extraction(_ent(617, 90), TOL, TITLE, UL) is True


def test_upper_left_bbox_defaults_to_no_exclusion():
    # Sheets without a detected upper-left table pass None and behave exactly as before.
    assert keep_for_title_extraction(_ent(172.9, 702.4), TOL, TITLE, None) is True
    assert keep_for_title_extraction(_ent(172.9, 702.4), TOL, TITLE) is True
