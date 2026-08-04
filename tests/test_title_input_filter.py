"""Regression: the tolerance exclusion for title extraction must not blank the title block.

The detected/pinned tolerance box is frequently over-wide (spanning the full bottom strip), so
a naive "exclude everything in the tolerance box" also deletes the bottom-right title block —
DRAWN/SCALE/DESIGNED/TITLE then all read NONE, producing false ADDED title findings. The guard
keeps any entity that is also inside the title box.

See docs/title-block-false-findings-implementation-plan.md (Phase 2).
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
