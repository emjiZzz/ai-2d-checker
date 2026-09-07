"""
Tests for applying hand-aligned zone templates to the comparison pipeline.

Lives in `tests/` because that is the only directory `pyproject.toml`'s `testpaths` collects.
The original version of this file sat in `services/backend/tests/`, was never collected, and
errored on collection when run directly — which is how the two defects below shipped green.

Both defects are silent in different ways, so both are pinned here:

  - The module could not be imported at all (relative import one level too shallow), and the
    caller wrapped the import in `try/except`, so the entire feature was a no-op that logged
    a warning among normal comparison chatter.

  - The fraction->CAD conversion omitted the Y flip, which mirrors every pinned zone. A
    title block pinned at 79.5-92.3% down from the top resolved to 14.1% down — onto the BOM
    table. Because `title`/`tolerance` are safe zones excluded from comparison, that excludes
    the wrong regions and feeds the real title block into the diff as drawing geometry.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.backend.domain.models.zone_template import ZoneTemplateDocument
from services.backend.infrastructure.audit.bom.zone_template_resolver import (
    fractions_to_absolute_bbox,
    resolve_zone_overrides,
)

# Real bounds of M7452A0N01_reference.dxf. Deliberately not a tidy 0..N box: the negative,
# non-zero origin is what exposes an offset error that a 0-origin sheet would hide.
BOUNDS = [-52.5, -37.125, 1102.5, 779.625]
BX0, BY0, BX1, BY1 = BOUNDS
W = BX1 - BX0   # 1155.0
H = BY1 - BY0   # 816.75


def _pct_down_from_top(ymin: float, ymax: float) -> float:
    """Where a CAD-space box sits vertically, as % down from the top of the sheet."""
    return (BY1 - (ymin + ymax) / 2) / H * 100


def test_module_imports():
    """Guards the defect that made the whole feature a silent no-op.

    The caller catches import errors so a template problem degrades to detection instead of
    failing the audit. That safety net also hid a broken module completely, so the import
    itself needs asserting.
    """
    assert callable(fractions_to_absolute_bbox)
    assert callable(resolve_zone_overrides)


class TestYFlip:
    """The conversion must flip Y and swap min/max. See the module docstring."""

    def test_title_block_pinned_near_bottom_stays_near_bottom(self):
        # As the desktop editor saves it: Y-DOWN, 0.795 = 79.5% down from the top.
        title = {"xMin": 0.375, "xMax": 0.932, "yMin": 0.795, "yMax": 0.923}
        bbox = fractions_to_absolute_bbox(title, BOUNDS)

        assert bbox is not None
        pct = _pct_down_from_top(bbox[1], bbox[3])
        assert pct == pytest.approx(85.9, abs=0.5), (
            f"title block resolved to {pct:.1f}% down from the top; expected ~86%. "
            "Landing near the top means the Y flip was dropped."
        )

    def test_top_of_sheet_fraction_resolves_to_high_cad_y(self):
        # title_upper_left: near the top in Y-DOWN terms.
        bbox = fractions_to_absolute_bbox(
            {"xMin": 0.10, "xMax": 0.27, "yMin": 0.075, "yMax": 0.140}, BOUNDS
        )
        assert bbox is not None
        # Near the top of the sheet == near BY1 in CAD, which is Y-up.
        assert bbox[3] > BY0 + 0.8 * H

    def test_a_zone_higher_on_screen_gets_a_larger_cad_y(self):
        upper = fractions_to_absolute_bbox(
            {"xMin": 0, "xMax": 1, "yMin": 0.05, "yMax": 0.15}, BOUNDS
        )
        lower = fractions_to_absolute_bbox(
            {"xMin": 0, "xMax": 1, "yMin": 0.80, "yMax": 0.95}, BOUNDS
        )
        assert upper[1] > lower[3]

    def test_x_is_a_plain_ratio_with_no_inversion(self):
        bbox = fractions_to_absolute_bbox(
            {"xMin": 0.0, "xMax": 1.0, "yMin": 0.4, "yMax": 0.6}, BOUNDS
        )
        assert bbox[0] == pytest.approx(BX0)
        assert bbox[2] == pytest.approx(BX1)

    def test_full_sheet_fraction_maps_to_full_sheet(self):
        bbox = fractions_to_absolute_bbox(
            {"xMin": 0.0, "xMax": 1.0, "yMin": 0.0, "yMax": 1.0}, BOUNDS
        )
        assert bbox == pytest.approx((BX0, BY0, BX1, BY1))

    def test_output_is_always_min_then_max(self):
        bbox = fractions_to_absolute_bbox(
            {"xMin": 0.2, "xMax": 0.8, "yMin": 0.1, "yMax": 0.9}, BOUNDS
        )
        assert bbox[0] < bbox[2]
        assert bbox[1] < bbox[3]


class TestConversionRectangle:
    """Fractions are relative to `render_bounds`, not to the detected geometry frame."""

    def test_conversion_uses_the_bounds_it_is_given(self):
        frac = {"xMin": 0.5, "xMax": 1.0, "yMin": 0.0, "yMax": 0.5}
        # render_bounds is ~4.5% larger than compute_drawing_bounds() on this corpus
        # (matplotlib autoscale margin), so using the wrong rectangle shifts every box.
        frame = [0.0, 0.0, 1050.0, 742.5]
        assert fractions_to_absolute_bbox(frac, BOUNDS) != fractions_to_absolute_bbox(frac, frame)

    def test_same_fractions_scale_across_sheet_sizes(self):
        """The property the per-template approach rests on: the corpus has 1155x817 and
        462x327 sheets at the same 1.4141 aspect."""
        frac = {"xMin": 0.375, "xMax": 0.932, "yMin": 0.795, "yMax": 0.923}
        small = [-21.0, -14.85, 441.0, 311.85]
        big_pct = _pct_down_from_top(*fractions_to_absolute_bbox(frac, BOUNDS)[1::2])

        b = fractions_to_absolute_bbox(frac, small)
        sh = small[3] - small[1]
        small_pct = (small[3] - (b[1] + b[3]) / 2) / sh * 100
        assert small_pct == pytest.approx(big_pct, abs=0.01)


class TestDegenerateInput:
    @pytest.mark.parametrize(
        "bounds",
        [None, [], [1, 2, 3], [0, 0, 0, 0], [0, 0, -5, -5]],
    )
    def test_bad_bounds_return_none(self, bounds):
        frac = {"xMin": 0.1, "xMax": 0.9, "yMin": 0.1, "yMax": 0.9}
        assert fractions_to_absolute_bbox(frac, bounds) is None

    @pytest.mark.parametrize(
        "frac",
        [None, {}, {"xMin": 0.1}, {"xMin": "a", "xMax": "b", "yMin": "c", "yMax": "d"}, 42],
    )
    def test_bad_fractions_return_none(self, frac):
        assert fractions_to_absolute_bbox(frac, BOUNDS) is None

    def test_pydantic_style_model_is_accepted(self):
        class Frac:
            def model_dump(self):
                return {"xMin": 0.0, "xMax": 1.0, "yMin": 0.0, "yMax": 1.0}

        assert fractions_to_absolute_bbox(Frac(), BOUNDS) == pytest.approx((BX0, BY0, BX1, BY1))


class TestResolveGuards:
    """Paths that must not need a database."""

    @pytest.mark.parametrize("bounds", [None, [], [1, 2, 3]])
    async def test_missing_render_bounds_returns_empty_not_error(self, bounds):
        # No bounds means the fractions cannot be placed at all. Degrading to detection is
        # correct; raising would fail the whole audit over an optional feature.
        assert await resolve_zone_overrides(bounds) == {}


def _tpl(signature: str, is_default: bool = False) -> ZoneTemplateDocument:
    """An unsaved template with one title zone pinned ~86% down (the Y-flip fixture value)."""
    return ZoneTemplateDocument(
        signature=signature,
        name=signature,
        zones={"title": {"xMin": 0.375, "xMax": 0.932, "yMin": 0.795, "yMax": 0.923}},
        is_default=is_default,
    )


class _MockField:
    """Makes `ZoneTemplateDocument.field == x` evaluable without init_beanie — same pattern as
    test_rooms.py. The comparison result is only ever passed to a mocked find_one, so its exact
    value is irrelevant; it just must not raise."""

    def __init__(self, name):
        self.name = name

    def __eq__(self, other):
        return ("cmp", self.name, other)


@pytest.fixture
def mock_zone_fields(monkeypatch):
    monkeypatch.setattr(
        ZoneTemplateDocument, "get_pymongo_collection", classmethod(lambda cls: MagicMock())
    )
    monkeypatch.setattr(ZoneTemplateDocument, "signature", _MockField("signature"), raising=False)
    monkeypatch.setattr(ZoneTemplateDocument, "is_default", _MockField("is_default"), raising=False)


class TestDefaultFallback:
    """A sheet with no signature-specific template inherits the designated default; a sheet
    that has its own template is unaffected. Mirrors resolve_zone_overrides exactly."""

    async def test_falls_back_to_default_when_no_signature_match(self, monkeypatch, mock_zone_fields):
        # find_one: first call (by signature) misses, second call (by is_default) hits.
        default_tpl = _tpl("aspect-9.999", is_default=True)
        monkeypatch.setattr(
            ZoneTemplateDocument, "find_one", AsyncMock(side_effect=[None, default_tpl])
        )

        overrides = await resolve_zone_overrides(BOUNDS)

        assert "title" in overrides  # the default's zone was applied to THIS sheet's bounds
        pct = _pct_down_from_top(overrides["title"][1], overrides["title"][3])
        assert pct == pytest.approx(85.9, abs=0.5)  # scaled to BOUNDS, not the default's own sheet

    async def test_signature_specific_template_wins_over_default(self, monkeypatch, mock_zone_fields):
        specific = _tpl("aspect-1.414")
        find_one = AsyncMock(side_effect=[specific])
        monkeypatch.setattr(ZoneTemplateDocument, "find_one", find_one)

        overrides = await resolve_zone_overrides(BOUNDS)

        assert "title" in overrides
        assert find_one.await_count == 1  # the default lookup must never happen when specific hits

    async def test_no_match_and_no_default_returns_empty(self, monkeypatch, mock_zone_fields):
        monkeypatch.setattr(
            ZoneTemplateDocument, "find_one", AsyncMock(side_effect=[None, None])
        )

        assert await resolve_zone_overrides(BOUNDS) == {}
