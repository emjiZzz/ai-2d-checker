---
title: Gotcha - SCALE Field Read the Date Column
type: gotcha
tags: [gotcha, title-block, field-extraction, false-changed, spatial-resolution]
status: resolved
date: 2026-07-30
---

# 🔥 Gotcha — SCALE Read the Date Column, Not the Scale

The first live end-to-end run (KEMCO pair `bc17b56d` / `63adc691`, 2026-07-30) reported:

```
[CHANGED] Title block SCALE checked: '04/12/22\n20' vs '1/1'
```

The reference "scale" is a date. The real scales are `1:1` (reference) and `1/1` (revision).

## Not the coordinate-space bug — a second, independent cause

A prior session attributed all "scale vs date" findings to the two-coordinate-space false
pairing (see [[Gotcha - Reference and Revision in Different Coordinate Spaces]]) and recorded
that it was *not* a field-mapping defect. That holds for the **SpatialDiffer** variant. This
finding is different: the `… checked:` format is emitted by `marking_builder`
(`inject_title_block_markings`), fed by the **structured** `title_block_extractor`. Two
different code paths produce the same symptom. Always check which one emitted the finding:

- `Title block <FIELD> checked: A vs B` → structured extractor (`title_block_extractor.py`)
- a bare paired string reported CHANGED → `SpatialDiffer.diff_views`

## Root cause

The KEMCO title block is a **stacked grid**: a header row of labels
(`DESIGNED | DRAWN | SCALE | Y/M/D`) at y≈46, with each field's value **directly below** it
at y≈36. Measured on the reference:

| label | at | value | at |
| :-- | :-- | :-- | :-- |
| `SCALE` | (261.7, 45.9) | `1:1` | (261.8, **35.9**) — same column, 10 below |

`resolve_field` mapped SCALE with `direction='right'` (the only stacked field that did — DRAWN,
DESIGNED, DWG_NO, TITLE, QTY all use `'below'`). The right-search has a `dy_min` floor on
horizontal distance, so the value *directly* below (dx≈0) was excluded, and the nearest
qualifying text to the right was the neighbouring **Y/M/D date column** (`04/12/22`, `20`).
Same mechanism on the revision → `2026/07/03`.

## Fix

`title_block_extractor.py`: SCALE → `direction='below'`, `dx_tol=5.0`, `dy_tol=14.0`.

- `'below'` matches the actual layout.
- `dy_tol=14` reaches the value ~10 below without touching the row beneath (~23 down).
- `dx_tol=5` is the load-bearing constant. The SCALE value sits at dx≈0 under its label; the
  Y/M/D date fragment is only ~8 to the right. `dx_tol=8` separated them by **0.1 units** on
  the measured pair — and the multi-line grouping step (which reuses `dx_tol`) would then
  merge the date fragment onto the value as `1:1\n20`. `dx_tol=5` keeps a 3-unit margin from
  the date column while still clearing DRAWN on the left (dx≈-15).

After: reference `1:1`, revision `1/1`.

## What this does NOT change (deliberate, do not "fix")

`1:1` vs `1/1` is still reported `CHANGED`. `utils/text.py::compare_values` has an explicit
guard *above* its `:`↔`/` normaliser — `if (":" in o and "/" in k) ...: return "CHANGED"` with
the comment "e.g. 1:2 vs 1/2 must be CHANGED" — and `marking_builder` annotates it
"(Standardized based on Standard context provided)". Scale **notation** is treated as
significant by this drawing standard. That is a decided behaviour; this fix only ensures the
values being compared are the actual scales, not a date. The finding is now legitimate
(notation differs) instead of garbage (date vs scale).

## Guarded by

`tests/test_extraction_logic.py::test_scale_reads_value_below_not_date_to_the_right` — a
stacked layout with a date fragment at dx=8; asserts SCALE reads `1:1`, never the date. It
fails at `dx_tol=8` (produces `1:1\n20`), so it pins the tightness, not just the direction.

## Traps

- Cache is **v19** (bumped this session for the zone/category work); this extractor change
  rides along under it. No live cache exists under v19 yet.
- n≈1 pair. `dx_tol=5` cleanly separates the observed columns; a title block with a
  wider-offset SCALE value could still miss. Re-measure `_anchor`/column spacing before
  trusting it on a new customer's standard.
