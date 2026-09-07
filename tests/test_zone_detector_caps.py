"""
Tests for zone bounding-box size caps in zone_detector._expand_bbox.

Background: `_expand_bbox` refuses any flood-fill expansion that would breach max_w/max_h,
but it used to add BBOX_PADDING to all four sides *after* the growth loop returned. The
declared ZONE_MAX_LIMITS were therefore not limits — every content-aware box came out up to
2*padding oversized in each axis. Measured on M7452A0N01_reference.dxf, the `title` zone grew
to 259 units (inside its 286-unit cap) and was returned at 319 units: 39.1% of sheet height
against a declared 35% ceiling.

This mattered beyond cosmetics. The same boxes drive BOM row extraction, category assignment
in result_parser, safe-zone exclusion, and crop-verifier tiles. Fixing it changed zone
geometry on every drawing in the corpus and the entire backend suite still passed, which is
why these tests exist: nothing asserted on box size at all.
"""
from types import SimpleNamespace

import pytest

from services.backend.infrastructure.audit.bom.zone_detector import (
    BBOX_PADDING,
    _expand_bbox,
)


def _text(x: float, y: float, t: str = "X"):
    """Duck-typed entity; zone_detector reads via getattr, and the real beanie Document
    cannot be constructed without a live Mongo connection."""
    return SimpleNamespace(
        entity_type="text", layer="0", properties={"text": t}, geometry={"insert": [x, y]}
    )


def _row_of_text(count: int, spacing: float, y: float = 0.0):
    """A horizontal run of text the flood-fill will try to sweep into one box."""
    return [_text(i * spacing, y) for i in range(count)]


def test_padding_does_not_push_the_box_past_max_w():
    # 40 points 10 apart spans 390 units; the flood-fill will pull in as many as the cap
    # allows, then padding is applied. With a 100-unit cap the result must still be <= 100.
    entities = _row_of_text(40, 10.0)
    bbox = _expand_bbox(entities, [(0.0, 0.0)], radius=50.0, max_w=100.0, max_h=100.0)

    assert bbox is not None
    width = bbox[2] - bbox[0]
    assert width <= 100.0 + 1e-9, (
        f"width {width} exceeds max_w=100 — padding is being applied after the cap check"
    )


def test_padding_does_not_push_the_box_past_max_h():
    entities = [_text(0.0, i * 10.0) for i in range(40)]
    bbox = _expand_bbox(entities, [(0.0, 0.0)], radius=50.0, max_w=100.0, max_h=100.0)

    assert bbox is not None
    height = bbox[3] - bbox[1]
    assert height <= 100.0 + 1e-9


@pytest.mark.parametrize("cap", [20.0, 55.0, 100.0, 250.0])
def test_cap_is_respected_across_magnitudes(cap):
    """A cap smaller than 2*BBOX_PADDING is the sharpest case: padding alone would exceed it."""
    entities = _row_of_text(60, 10.0)
    bbox = _expand_bbox(entities, [(0.0, 0.0)], radius=80.0, max_w=cap, max_h=cap)

    assert bbox is not None
    assert (bbox[2] - bbox[0]) <= cap + 1e-9
    assert (bbox[3] - bbox[1]) <= cap + 1e-9


def test_clamping_trims_symmetrically():
    """Shrinking to the cap must not bias the box toward one edge.

    An asymmetric clamp would slide zones off their content — worse than an oversized box,
    because the error is directional and would systematically favour one side of the sheet.

    Note the growth loop *refuses* expansions that would breach the cap rather than growing
    past it and being trimmed, so the box never spans a cluster wider than max_w. The case
    that actually exercises the clamp is a cluster that fits the cap but whose *padded*
    extent does not: here 0..80 fits a 100 cap, but padding to -30..110 (140 wide) does not.
    """
    entities = _row_of_text(9, 10.0)  # spans x = 0..80, inside the 100 cap
    bbox = _expand_bbox(entities, [(0.0, 0.0)], radius=50.0, max_w=100.0, max_h=100.0)

    assert bbox is not None
    assert (bbox[2] - bbox[0]) == pytest.approx(100.0), "should be clamped to exactly max_w"
    # Centre of the grown cluster (0..80) is 40; symmetric trimming must preserve it.
    assert ((bbox[0] + bbox[2]) / 2.0) == pytest.approx(40.0, abs=1e-6)


def test_small_cluster_well_inside_the_cap_still_gets_its_padding():
    """The clamp must only engage when the cap is actually breached.

    Padding exists so a box fully contains the glyphs whose baseline-left insert points were
    collected; clamping unconditionally would silently remove it everywhere.
    """
    entities = [_text(0.0, 0.0), _text(10.0, 0.0)]
    bbox = _expand_bbox(entities, [(0.0, 0.0)], radius=50.0, max_w=10_000.0, max_h=10_000.0)

    assert bbox is not None
    assert bbox[0] == pytest.approx(-BBOX_PADDING)
    assert bbox[2] == pytest.approx(10.0 + BBOX_PADDING)


def test_exclude_lines_uses_the_tighter_padding():
    """Text-only zones (title_upper_left, bom, notes) pad by 5.0, not BBOX_PADDING."""
    entities = [_text(0.0, 0.0)]
    bbox = _expand_bbox(
        entities, [(0.0, 0.0)], radius=10.0, max_w=10_000.0, max_h=10_000.0, exclude_lines=True
    )

    assert bbox is not None
    assert bbox[0] == pytest.approx(-5.0)


def test_no_seeds_returns_none():
    assert _expand_bbox([_text(0.0, 0.0)], [], radius=10.0) is None
