"""Which band of the upper-left table holds its VALUES.

`extract_title_ul_kv` used to take `bands[-1]`, the lowest row. That is a positional
assumption, and it holds only while the zone box stops at the bottom of the table.

The measured failure, reported from a live review of `M745227N01`:

    [CHANGED] Title Block (Upper-Left) T. Q'ty / 総製作個数: 4 ロール：12 (2x6台) vs 16組

The only stored zone template is `aspect-1.374` flagged `is_default`, and that sheet is 1.414,
so the fallback's fractions scaled onto a differently-shaped sheet and the reference's
`title_upper_left` box came out with its bottom edge at y=762.99 while the table's value row
sits at y=822. A NOTE at y=767.5 therefore became the lowest band, was read as the values row,
and the real values (`45 / 227 / 16組 / 0`) were demoted to a header band. The note inherited
the key `T. Q'ty / 総製作個数` because its x lands 2.4 units nearer that column than the next
one along, and was then compared against the revision's genuine `16組`.

Every coordinate below is measured off those two sheets.
"""

from services.backend.infrastructure.audit.comparison.orchestrator import (
    _ul_columns,
    ul_value_band_index,
)

# ---------------------------------------------------------------------------
# The real bands, both sides of M745227N01, with the default template applied.
# ---------------------------------------------------------------------------

#: Reference (DWG-exported, large coordinates). Box (75.22, 762.99, 313.71, 862.25).
REF_BANDS = [
    [(84.87, 851.8), (148.57, 851.8), (207.50, 851.8), (267.25, 851.8)],   # 0 ユニットNo. / コードNo. / 総製作個数 / 在庫棚入庫
    [(84.87, 841.9), (148.57, 841.9), (207.50, 841.9), (257.41, 841.9)],   # 1 Unit No. / Part No. / T. Q'ty / Stock Q'ty
    [(105.01, 822.0), (164.26, 822.0), (223.47, 822.0), (283.29, 822.0)],  # 2 45 / 227 / 16組 / 0   <- the values
    [(179.23, 767.5)],                                                     # 3 '4 ロール：12 (2x6台)' <- a note
]

#: Revision (iCAD-exported, ~3x smaller coordinates). Its box stops above the notes, so the
#: table bands correctly and the two stacked header labels merge into one band.
REV_BANDS = [
    [(27.29, 283.9), (28.29, 283.9), (48.52, 283.9), (49.52, 283.9),
     (68.16, 283.9), (69.16, 283.9), (87.69, 283.9), (88.08, 283.9)],      # 0 headers, both languages
    [(35.00, 273.0), (54.75, 273.0), (75.25, 273.0), (94.25, 273.0)],      # 1 45 / 227 / 16組 / 0
]


def test_the_reported_defect_the_note_is_not_the_values_row():
    assert ul_value_band_index(REF_BANDS) == 2, "the values row is 45 / 227 / 16組 / 0"


def test_the_side_that_was_already_right_is_untouched():
    assert ul_value_band_index(REV_BANDS) == 1


def test_two_bands_are_left_alone_there_is_nothing_to_compare_against():
    """A header row and a values row is the minimum readable table; with no third band there
    is no interior gap to call the last one an outlier against."""
    assert ul_value_band_index(REF_BANDS[:2]) == 1
    assert ul_value_band_index([REF_BANDS[0]]) == 0


def test_a_sparse_values_row_survives_because_it_fails_only_one_signal():
    """The case that makes requiring BOTH signals necessary rather than fussy.

    A values row with one cell filled and three empty covers 1 of 4 columns — the same
    coverage as the stray note — but it sits at the table's own row pitch. Dropping it would
    promote a header row to being the values row, which is worse than the defect being fixed.
    """
    sparse = REF_BANDS[:2] + [[(223.47, 822.0)]]
    assert ul_value_band_index(sparse) == 2


def test_a_note_far_below_is_dropped_even_when_it_lands_in_a_column():
    """Coverage alone would keep this: its x sits right under the 総製作個数 column. The row
    pitch is what rejects it — 54.5 against the table's own 9.9 and 19.9."""
    aligned_note = REF_BANDS[:3] + [[(223.47, 767.5)]]
    assert ul_value_band_index(aligned_note) == 2


def test_two_stray_bands_are_both_dropped():
    """The reference box on this sheet is one line short of swallowing the second roll-count
    note as well; a box slightly taller takes both."""
    two_strays = REF_BANDS + [[(179.23, 743.3)]]
    assert ul_value_band_index(two_strays) == 2


def test_it_never_leaves_fewer_than_two_bands():
    """A table with no header row above its values is not one this extractor can read, so the
    walk stops rather than consuming the whole table."""
    all_strays = [REF_BANDS[0], [(179.23, 700.0)], [(179.23, 600.0)], [(179.23, 500.0)]]
    assert ul_value_band_index(all_strays) >= 1


def test_a_band_at_the_tables_pitch_is_kept_however_odd_it_looks():
    """Deliberate limit, stated rather than discovered later: the guard is about content that
    drifted in from ELSEWHERE on the sheet, which is what an outlying gap means. A stray line
    inside the table's own row spacing is indistinguishable from a table row here, and is left
    to the column-coverage check at the pairing stage."""
    close_stray = REF_BANDS[:3] + [[(179.23, 812.0)]]
    assert ul_value_band_index(close_stray) == 3


# ---------------------------------------------------------------------------
# Column detection — the part that has to work across a 3x coordinate scale.
# ---------------------------------------------------------------------------

def test_columns_split_the_reference_headers_into_four():
    cols = _ul_columns([84.87, 148.57, 207.50, 267.25])
    assert len(cols) == 4


def test_columns_merge_the_stacked_bilingual_labels_of_one_cell():
    """The revision writes 総製作個数 and T. Q'ty one unit apart inside a single cell. A fixed
    tolerance cannot tell that from a real column boundary on the reference, where columns are
    ~60 apart; splitting on the shape of the gaps can."""
    cols = _ul_columns([27.29, 28.29, 48.52, 49.52, 68.16, 69.16, 87.69, 88.08])
    assert len(cols) == 4
    assert cols[0] == 27.79


def test_columns_handle_the_degenerate_inputs():
    assert _ul_columns([]) == []
    assert _ul_columns([42.0]) == [42.0]
