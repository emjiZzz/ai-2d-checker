---
title: Gotcha - Title Read the Drawing Number and Was Never Compared
type: gotcha
tags: [gotcha, title-block, field-extraction, silent-no-op, taxonomy, key-mismatch]
status: resolved
date: 2026-08-04
---

# 🔥 Gotcha — TITLE read the drawing number, and was never compared anyway

Three defects stacked on one field. Each alone produces silence rather than a wrong answer,
which is why none of them surfaced until the title block was inspected field by field.

## 1. The value read was the drawing number

`resolve_field("TITLE", ["TITLE", "名称", "品名"], "below", dx_tol=50, dy_tol=35,
prefer_lowest_y=True, multiline=True)` returned **`M7452A1N01`** — the DWG No. — on *both*
sheets, so it compared equal and looked like a clean MATCHED.

The 名称 value does not sit below its label. It sits in the cell **beside** it:

| | label 名称 | title value | dx | dy |
| :-- | :-- | :-- | :-- | :-- |
| reference (coord_scale 1.80) | (752.7, 93.3) | `Roll Cassette 12" Mill` (897.8, 99.2) | +145.1 | **+5.9** |
| | | `基準スペーサー：3` (897.2, 79.2) | +144.5 | −14.1 |
| revision (coord_scale 1.00) | (297.3, 37.1) | `ロールカセット 12"ミル` (358.1, 40.5) | +60.8 | **+3.4** |
| | | `基準スペーサー：3` (358.1, 32.5) | +60.8 | −4.6 |

Note the sign: one row is **above** the label. A `below` search cannot reach it at any
tolerance, and widening `dy_tol` to try only walks further down into the drawing-number cell —
which is exactly what `M7452A1N01` at dy=52.8 was.

## 2. The 名称 cell is two ruled rows, and merging them hides a change

The grid confirms it. In revision coordinates the title value cell is `x[305.5, 410.0]`
`y[28.0, 44.0]`, and a horizontal rule at **y=37.0** (spanning `x[310.5, 405.0]`) splits it in
two. Reference equivalent: cell `x[772.9, 1025.0]` `y[68.6, 110.7]`, divider at **y=90.9**.

On the measured pair the upper row changed and the lower row is byte-identical:

```
CHANGED   machine_name   TITLE checked: Roll Cassette 12" Mill vs ロールカセット 12"ミル
MATCHED   machine_name   TITLE (2nd line) checked: 基準スペーサー：3 vs 基準スペーサー：3
```

The old `multiline=True` grouping concatenated rows into one string, so this would have read as
a single wholesale rewrite — losing the fact that only the product name's *language* changed
while the part designation held. `extract_stacked_values` returns one value per row, top first,
each with its own coordinates so the two findings pin separate markers.

## 3. …and none of it was ever compared

`marking_builder.field_labels_map` keyed the field **`"NAME"`**. `extract_title_block` returns
**`"TITLE"`**. The lookup is
`ref_title_fields.get(field_key, {"value": "NONE", ...})` — a miss returns the NONE default, and
the marking is only appended `if kmti_val != "NONE" or orig_val != "NONE"`. So the title
produced **no marking on any drawing, ever**, and the panel showed nothing rather than showing
something wrong.

> [!WARNING] This class of bug is invisible by construction.
> Two dicts keyed by hand, in different modules, with a `.get(..., default)` between them. No
> exception, no log line, no empty-state — the field simply is not in the output. When adding a
> title-block field, check that the key in `field_labels_map` matches the key
> `extract_title_block` actually returns. `DWG NO` currently reads NONE on this corpus for the
> *first* reason above (its value is also beside the label, not below) — it is wired up
> correctly but extracts nothing, which presents identically.

## ➕ DATE (作成年月日 / Y/M/D) — new field

Not previously extracted at all. It does sit directly below its label:
reference `Y/M/D (702.0, 112.2) -> '2010/09/13' (709.1, 85.3)` dx=7.1 dy=26.9;
revision `Y/M/D (278.2, 44.6) -> '2026/07/03' (282.0, 36.0)` dx=3.8 dy=8.6.
Extracted with `dx_tol=10, dy_tol=22, prefer_lowest_y=True`, under a new `creation_date`
taxonomy feature.

> [!IMPORTANT] `prefer_lowest_y` is load-bearing here, not cosmetic.
> **`Y/M/D` appears twice on the sheet** — once as the amendment/revision table's date-column
> header (reference y=129.9, revision y=51.5) and once as the title block's own label
> (y=112.2 / 44.6). The title-block one is always the lower. Anchoring on the amendment header
> instead would read a revision-history row as the drawing's creation date, and the value would
> look entirely plausible.

## Deliberate choices

- **Both 名称 rows use the `machine_name` feature.** They are two rows of one field. The
  taxonomy's other name key, `line_name`, is in `DEFERRED_FEATURES` — the frontend renders those
  with a "not yet supported" treatment, so claiming it for the second row would misreport it.
- **TITLE is not routed through `resolve_field`/OCR.** The OCR mapping carries a single `TITLE`
  string; grounding it would collapse the two rows back into one value, defeating the split.
  The spatial read is cell-bounded and correct on both sheets, so it no longer needs OCR cover.
- **`creation_date` was added to `taxonomy.py` AND `apps/desktop/src/utils/comparisonTaxonomy.ts`.**
  That mirror is hand-maintained; `tests/test_taxonomy_consistency.py` fails if they drift.

## Guarded by

- `tests/test_extraction_logic.py::test_title_is_read_from_the_cell_beside_its_label_not_below`
  — includes the drawing number below the label, so it fails the moment the search walks back down.
- `tests/test_extraction_logic.py::test_title_rows_are_reported_separately_and_in_order`
  — also asserts the two rows get *different* coordinates.
- `tests/test_extraction_logic.py::test_date_anchors_on_the_title_block_ymd_not_the_amendment_table_header`
  — includes both `Y/M/D` labels and a decoy amendment-row date.

## Traps

- Cache is **v34**. Every cached result predates all three findings.
- `dy_tol=10` for the title band admits the company-name row on the revision
  (`日下部電機株式会社` / `Kusakabe …` at dy=8.7) and relies on `TITLE_BLOCK_LABEL_KEYWORDS` to
  reject it — `日下部電機` and `kusakabe` are both in that list. Tightening to 8.5 would exclude it
  geometrically but leaves only 1.2 units of margin on the reference's lower row. If a sheet ever
  puts a non-keyword value in that row, the keyword filter will not save it.
- Related: [[Gotcha - Title Field Read Across a Ruled Cell Boundary]] — same title block, same
  root shape (a proximity rectangle that ignores the ruled grid), found in the same session.
