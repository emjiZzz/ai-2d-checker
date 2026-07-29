"""Tests for pinned-zone growth and the `views` exclusion contract.

Two changes are pinned here:

1. **A pinned `bom` grows against detection.** Templates are aligned against whatever
   drawing the user happened to have open. A BOM aligned on a one-row sheet is a shallow
   band; a later drawing with three rows extends further down. The template application used
   to overwrite the detected box outright, so those extra rows fell outside the zone and were
   dropped from BOM extraction with no warning — the pinned box made the zone *worse* than
   detection on exactly the drawings that needed it.

2. **`views` is templatable, and keeps its exclusion.** `views` is defined by exclusion, but
   that is baked into `_derive_views_zone`. A pinned `views` is a plain rectangle over the
   drawing area with no exclusion in it, so the sibling zones have to be subtracted at the
   point of use or notes/title content inside the rectangle reads as drawing geometry.
"""
from types import SimpleNamespace

import pytest

from services.backend.infrastructure.audit.bom.table_extractor import (
    GROWABLE_PINNED_ZONES,
    _grow_pinned_zone,
)
from services.backend.infrastructure.audit.bom.zone_detector import (
    VIEWS_EXCLUDED_ZONES,
    ZONE_MAX_LIMITS,
    detect_subviews,
    point_in_any_bbox,
    views_exclusions,
)

RENDER_BOUNDS = [0.0, 0.0, 1000.0, 1000.0]


# ---------------------------------------------------------------------------
# 1 -- pinned BOM grows with its rows
# ---------------------------------------------------------------------------

def test_bom_is_the_growable_zone():
    assert "bom" in GROWABLE_PINNED_ZONES
    # Fixed printed furniture must NOT grow: a mis-detection could only corrupt a box the
    # user already aligned correctly.
    for fixed in ("title", "tolerance", "title_upper_left"):
        assert fixed not in GROWABLE_PINNED_ZONES
    # A pinned `views` is the drawing area by definition; growing it defeats the purpose.
    assert "views" not in GROWABLE_PINNED_ZONES


def test_pinned_bom_extends_downward_for_extra_rows():
    """The regression: a shallow pinned band must cover a taller detected table.

    CAD is Y-up, so more BOM rows extend to *lower* y. The union must pull the bottom edge
    down without moving the edges the user aligned.
    """
    pinned = (500.0, 900.0, 950.0, 960.0)      # one-row band
    detected = (500.0, 840.0, 950.0, 960.0)    # three rows, extends 60 units lower

    grown, was_grown = _grow_pinned_zone("bom", pinned, detected, RENDER_BOUNDS)

    assert was_grown is True
    assert grown[1] == pytest.approx(840.0), "bottom edge did not follow the extra rows"
    assert grown[3] == pytest.approx(960.0), "top edge moved — pinned edges must hold"
    assert grown[0] == pytest.approx(500.0)
    assert grown[2] == pytest.approx(950.0)


def test_growth_never_shrinks_the_pinned_box():
    """Detection finding *less* than the user pinned is not a reason to shrink. The human
    decision is the floor."""
    pinned = (500.0, 840.0, 950.0, 960.0)
    detected = (600.0, 900.0, 700.0, 920.0)   # entirely inside the pinned box

    grown, was_grown = _grow_pinned_zone("bom", pinned, detected, RENDER_BOUNDS)

    assert was_grown is False
    assert grown == pinned


def test_runaway_detection_is_refused_not_clamped():
    """A detection breaching ZONE_MAX_LIMITS is not believable.

    Returning the pinned box is deliberate: clamping the union back to the cap would trim it
    symmetrically and silently move the edges the user aligned by hand, which is a worse
    failure than declining to grow.
    """
    max_w_frac, max_h_frac = ZONE_MAX_LIMITS["bom"]
    pinned = (500.0, 900.0, 950.0, 960.0)
    detected = (10.0, 10.0, 990.0, 990.0)      # detector swallowed the sheet

    grown, was_grown = _grow_pinned_zone("bom", pinned, detected, RENDER_BOUNDS)

    assert was_grown is False
    assert grown == pinned
    assert (grown[2] - grown[0]) <= 1000.0 * max_w_frac
    assert (grown[3] - grown[1]) <= 1000.0 * max_h_frac


def test_growth_is_skipped_without_a_detection():
    grown, was_grown = _grow_pinned_zone("bom", (1.0, 2.0, 3.0, 4.0), None, RENDER_BOUNDS)
    assert (grown, was_grown) == ((1.0, 2.0, 3.0, 4.0), False)


# ---------------------------------------------------------------------------
# 2 -- pinned `views` keeps its exclusion
# ---------------------------------------------------------------------------

def test_views_exclusions_returns_the_sibling_zones():
    regions = {
        "views": (0.0, 0.0, 1000.0, 1000.0),
        "title": (700.0, 0.0, 1000.0, 150.0),
        "bom": (700.0, 850.0, 1000.0, 1000.0),
        "notes": (50.0, 600.0, 300.0, 800.0),
        "iso": None,                    # absent zones must not become empty exclusions
        "_zone_confidence": {"views": "user_pinned_template"},
    }

    exclusions = views_exclusions(regions)

    assert len(exclusions) == 3
    assert (0.0, 0.0, 1000.0, 1000.0) not in exclusions, "views must not exclude itself"
    assert None not in exclusions


def test_views_is_not_in_its_own_exclusion_list():
    assert "views" not in VIEWS_EXCLUDED_ZONES


def test_point_in_any_bbox_tolerates_empty_and_none():
    assert point_in_any_bbox(5.0, 5.0, None) is False
    assert point_in_any_bbox(5.0, 5.0, []) is False
    assert point_in_any_bbox(5.0, 5.0, [(0.0, 0.0, 10.0, 10.0)]) is True
    assert point_in_any_bbox(50.0, 5.0, [(0.0, 0.0, 10.0, 10.0)]) is False


def _label(x: float, y: float, text: str):
    return SimpleNamespace(
        entity_type="text", layer="0",
        properties={"text": text}, geometry={"insert": [x, y]},
    )


def test_subview_anchor_inside_an_excluded_zone_is_ignored():
    """The concrete failure a pinned `views` would cause.

    "SECTION A-A" printed as a title-block field, or a view label quoted in the notes,
    sits inside the pinned views rectangle. Without the exclusion it seeds a sub-view.
    """
    entities = [
        _label(200.0, 500.0, "SECTION A-A"),      # genuine, in the drawing area
        _label(850.0, 100.0, "SECTION B-B"),      # inside the title block
    ]
    views_bbox = (0.0, 0.0, 1000.0, 1000.0)
    title_bbox = (700.0, 0.0, 1000.0, 200.0)

    without = detect_subviews(entities, views_bbox=views_bbox)
    with_exclusion = detect_subviews(
        entities, views_bbox=views_bbox, exclude_bboxes=[title_bbox]
    )

    assert len(without) == 2, "precondition: both labels seed sub-views when nothing is excluded"
    assert len(with_exclusion) == 1
    assert with_exclusion[0]["label"] == "SECTION A-A"


def test_excluded_zone_entities_do_not_join_a_subview_cluster():
    """Beyond seeding, excluded content must not be swept into a legitimate sub-view's box."""
    entities = [
        _label(200.0, 500.0, "SECTION A-A"),
        _label(210.0, 510.0, "12.5"),
        _label(880.0, 120.0, "M7452A0N01"),   # title-block text, far right
    ]
    views_bbox = (0.0, 0.0, 1000.0, 1000.0)
    title_bbox = (700.0, 0.0, 1000.0, 200.0)

    subviews = detect_subviews(
        entities, views_bbox=views_bbox, exclude_bboxes=[title_bbox]
    )

    assert len(subviews) == 1
    bbox = subviews[0]["bbox"]
    assert bbox[2] < 700.0, "title-block text was pulled into the sub-view bounding box"
