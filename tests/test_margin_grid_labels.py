"""Sheet-frame grid labels and amendment-table headers must stay out of `drawing_views`.

Background: a live comparison of the KEMCO pair bc17b56d / 63adc691 (2026-07-30) produced
32 findings, 22 of them filed under `comparison_drawing_views`. Most of those 22 were not
drawing content at all -- they were the sheet's frame furniture and the column headers of
the amendment/revision-history table.

Two independent defects put them there:

1. `is_margin_grid_text` compared the raw text against ASCII "A".."H" and "1".."12". This
   drawing standard draws its frame labels full-width (U+FF21 'Ａ', U+FF11 '１'), which
   compare unequal, so the predicate returned False for every grid label on every drawing
   in the corpus and the filter at its one call site was inert. `orchestrator.is_in_margin`
   was a near-duplicate that *did* normalise -- the two copies had drifted, which is how
   this survived. Its 6% band was also below the 6.27-8.52% at which the labels actually
   sit, so it would have missed them even with normalisation.

2. The amendment table is title-block furniture but is not reliably inside the detected
   `title` box. On the revision it sits at x 338-402, inside `title`; on the reference the
   same table sits bottom-left at x 28-129 while `title` starts at x 152. It is therefore
   excluded by text rather than by position.

Coordinates below are the measured positions from that pair.
"""
from types import SimpleNamespace

import pytest

from services.backend.infrastructure.audit.bom.zone_detector import (
    GRID_LABEL_MARGIN_FRACTION,
    is_margin_grid_text,
)
from services.backend.infrastructure.audit.comparison.orchestrator import (
    REVISION_TABLE_HEADERS,
    amendment_table_bboxes,
)

# Reference sheet render_bounds from the measured pair.
BOUNDS = (-21.0, -15.428820875335504, 441.0, 324.00524552200557)


def _text(value, x, y):
    return SimpleNamespace(
        properties={"text": value},
        geometry={"insert": [x, y, 0.0]},
        layer="RAHM2",
        entity_type="text",
    )


def _norm(t):
    import unicodedata
    return unicodedata.normalize("NFKC", str(t or "")).strip().lower()


class TestFullWidthGridLabels:
    """The NFKC regression: full-width labels are what this standard actually draws."""

    @pytest.mark.parametrize("label", ["Ａ", "Ｂ", "Ｃ", "Ｄ", "Ｅ", "Ｆ"])
    def test_full_width_letters_on_the_frame_are_excluded(self, label):
        # x=18.4 and x=411.4 are the left/right frame rails on the measured sheet.
        assert is_margin_grid_text(_text(label, 18.4, 221.7), BOUNDS)
        assert is_margin_grid_text(_text(label, 411.4, 221.7), BOUNDS)

    @pytest.mark.parametrize("label", ["１", "２", "３", "７", "８"])
    def test_full_width_digits_on_the_frame_are_excluded(self, label):
        # y=5.9 is the bottom frame rail.
        assert is_margin_grid_text(_text(label, 140.6, 5.9), BOUNDS)

    def test_ascii_equivalents_still_excluded(self):
        assert is_margin_grid_text(_text("B", 18.4, 221.7), BOUNDS)
        assert is_margin_grid_text(_text("8", 390.6, 5.9), BOUNDS)


class TestMarginThreshold:
    """The band has to reach the labels without reaching real content."""

    def test_outer_ring_at_8_5_percent_is_covered(self):
        # Measured outermost grid ring: 8.52% of the sheet dimension. The previous 6%
        # cutoff sat below it and excluded nothing.
        assert GRID_LABEL_MARGIN_FRACTION > 0.0852
        assert is_margin_grid_text(_text("Ｃ", 18.4, 171.7), BOUNDS)

    def test_band_does_not_reach_the_drawing_interior(self):
        # Anything at 15% in from an edge is drawing area, not frame.
        assert GRID_LABEL_MARGIN_FRACTION < 0.15
        assert not is_margin_grid_text(_text("Ｃ", 90.0, 160.0), BOUNDS)

    def test_multi_character_text_in_the_band_is_kept(self):
        """`is_grid_char` is what makes the wider band safe -- it must stay tight.

        These sit at 8.28% and 8.95%, inside the band, and are real title-block content.
        """
        assert not is_margin_grid_text(_text("M745203N01", 30.0, 12.0), BOUNDS)
        assert not is_margin_grid_text(_text("DWG.No.", 30.0, 14.0), BOUNDS)
        assert not is_margin_grid_text(_text("2491FSRS", 129.4, 25.2), BOUNDS)

    def test_single_cjk_character_in_the_band_is_kept(self):
        # '行', '号', '発' were measured at 7.7-8.8%; none are grid characters.
        for ch in ("行", "号", "発"):
            assert not is_margin_grid_text(_text(ch, 30.0, 13.0), BOUNDS)

    def test_amendment_row_letters_are_not_frame_furniture(self):
        """The reference's amendment table has an A/B/C/D row-letter column at x=29.2.

        Spaced 7 units apart beside 旧工事番号 / 2491FSRS, ~10.9% in -- these are table
        content, and the frame filter must not swallow them just because they are single
        letters. They are the residual part of this bug: still mis-attributed to
        drawing_views, but that needs an amendment-table zone, not a wider margin.
        """
        for label, y in (("Ａ", 17.2), ("Ｂ", 24.2), ("Ｃ", 31.2), ("Ｄ", 38.2)):
            assert not is_margin_grid_text(_text(label, 29.2, y), BOUNDS)


class TestRevisionTableHeaders:
    """Headers are furniture; the values beside them are real content."""

    @pytest.mark.parametrize("header", [
        "Amd.", "Y/M/D", "Design Chg No.", "Name",
        "Previous Dwg. No,", "旧図面番号", "旧工事番号", "訂正符号",
    ])
    def test_headers_are_excluded(self, header):
        assert _norm(header) in REVISION_TABLE_HEADERS

    @pytest.mark.parametrize("value", [
        "2491FSRS",      # old job number
        "M745203N01",    # old drawing number
        "04/12/22",      # an amendment date
        "橋本",           # a name *value* in the DESIGNED cell
    ])
    def test_values_are_kept(self, value):
        assert _norm(value) not in REVISION_TABLE_HEADERS

    def test_matching_is_exact_not_substring(self):
        """'name' is short; substring matching would suppress unrelated text."""
        assert _norm("Name") in REVISION_TABLE_HEADERS
        assert _norm("Machine Name Plate") not in REVISION_TABLE_HEADERS
        assert _norm("Nameplate") not in REVISION_TABLE_HEADERS

    def test_full_width_headers_normalise_onto_the_set(self):
        # NFKC folds full-width ASCII, so a full-width 'Ａｍｄ.' still matches.
        assert _norm("Ａｍｄ.") in REVISION_TABLE_HEADERS


# Reference sheet global bounds (from compute_drawing_bounds on the measured pair) --
# tighter than render_bounds, which is what amendment_table_bboxes receives at runtime.
REF_GLOBAL = (0.0, 0.0, 420.0, 297.0)


def _header(value, x, y):
    return SimpleNamespace(
        properties={"text": value},
        geometry={"insert": [x, y, 0.0]},
        layer="RAHM2",
        entity_type="text",
    )


class TestAmendmentTableReclassification:
    """The residual from the grid/header fix: the amendment table's own content is
    title-block furniture but lands in drawing_views when the table sits outside the
    detected `title` box. It is relocated by clustering the header anchors.
    """

    def _ref_table(self):
        # The reference amendment table, measured: a bottom-left header cluster with the
        # A/B/C/D row-letter column sitting just above it at x=29.2.
        return [
            _header("Amd.", 28.2, 10.9),
            _header("Y/M/D", 40.5, 10.7),
            _header("Design Chg No.", 58.3, 10.7),
            _header("Name", 89.5, 10.7),
            _header("旧工事番号", 105.9, 25.2),
            _header("旧図面番号", 116.7, 19.7),
        ]

    def test_headers_form_a_small_capped_box(self):
        boxes = amendment_table_bboxes(self._ref_table(), REF_GLOBAL)
        assert boxes, "the header cluster should produce a bbox"
        # Every box stays well under the 20% runaway cap.
        sheet = 420.0 * 297.0
        for b in boxes:
            frac = (b[2] - b[0]) * (b[3] - b[1]) / sheet
            assert frac <= 0.20

    def test_row_letter_column_falls_inside(self):
        boxes = amendment_table_bboxes(self._ref_table(), REF_GLOBAL)
        # The A/B/C/D column at x=29.2, y 24-38 -- above the header row.
        for y in (24.2, 31.2, 38.2):
            assert any(b[0] <= 29.2 <= b[2] and b[1] <= y <= b[3] for b in boxes), \
                f"row-letter at y={y} should be inside an amendment box"

    def test_value_cell_falls_inside(self):
        boxes = amendment_table_bboxes(self._ref_table(), REF_GLOBAL)
        # '2491FSRS' old-job-number value at (129.4, 25.2).
        assert any(b[0] <= 129.4 <= b[2] and b[1] <= 25.2 <= b[3] for b in boxes)

    def test_drawing_interior_is_not_covered(self):
        boxes = amendment_table_bboxes(self._ref_table(), REF_GLOBAL)
        # Centre of the sheet is drawing area and must never be relabelled.
        assert not any(b[0] <= 210 <= b[2] and b[1] <= 150 <= b[3] for b in boxes)

    def test_lone_header_is_not_a_table(self):
        # A single 'Name' with no sibling header (e.g. a stray label in a note) must not
        # seed a reclassification box.
        assert amendment_table_bboxes([_header("Name", 200.0, 150.0)], REF_GLOBAL) == []

    def test_no_headers_no_boxes(self):
        plain = [_header("SECTION A-A", 200.0, 150.0),
                 _header("DETAIL B", 210.0, 160.0)]
        assert amendment_table_bboxes(plain, REF_GLOBAL) == []
