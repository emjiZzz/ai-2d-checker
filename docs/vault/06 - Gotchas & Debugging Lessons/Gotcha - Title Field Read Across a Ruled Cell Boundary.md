---
title: Gotcha - Title Field Read Across a Ruled Cell Boundary
type: gotcha
tags: [gotcha, title-block, field-extraction, false-positive, corroboration, spatial-resolution]
status: resolved
date: 2026-08-04
---

# 🔥 Gotcha — A Title Field Read Across a Ruled Cell Boundary, Then Corroborated Itself

Marker **M019** on the `M7452A1N01` pair rendered as a green ✓ `MATCHED` with the value `1`,
positioned in the *tolerance table's Fabrication column* on the reference. Finding `[18]` in the
v31 cache:

```
status=MATCHED cat=title_block feature=previous_drawing_number text='1'
details=Title block Previous Dwg. No. checked: 1 vs NONE
coords=[408.667, 16.5]   ref_coordinates=[371.968, 77.322]
```

Both cached coordinates were reproduced exactly from the source entities using the two anchor
formulas below, so the chain is not a hypothesis.

## The chain — two independent defects compounding

**1. The proximity search stepped over a ruled cell boundary.**
`extract_proximity_value(["Previous Dwg. No.", "旧図面番号"], "below", prefer_highest_y=True)` anchors
on the `旧図面番号` label at `(382.1, 89.3)` and picked the tolerance table's Fabrication cell `1` at
`(364.9, 74.5)` — `dx=17.2`, `dy=14.8`, admitted because `coord_scale` inflates `dx_tol=8.0` past
17.2. The candidate anchor `[xmax + h*0.8, ymin + (ymax-ymin)/2]` = `[371.968, 77.322]`, the cached
`ref_coordinates`.

The search is a bare rectangle around the label's insert point. The **vertical rule at x=380.1**
(spanning y 25.0–128.2) is the tolerance-table / title-block divider and stands squarely between
label and candidate. The extractor had no notion of the grid it was reading.

**2. The corroboration guard validated it.** The revision reads NONE (its own Fabrication `1` is
dropped by `keep_for_title_extraction`), so status was `REMOVED`, which triggers the bilateral
guard: `find_drawing_text_coordinates(rev_entities, "1", region_bbox=rev_title_bbox,
match_level=2)`. Level 2's short-target pass used `(^|\D)1(\D|$)` — designed to stop `1` matching
inside `11`. It matched the `1` **inside `M7452A1N01`**, because there the neighbours are *letters*,
not digits. Anchor `[xmax + h*0.4, ymin + box_h/2]` = `[408.667, 16.5]`, the cached `coordinates`.
Status flipped `REMOVED → MATCHED`.

A mis-extraction was laundered into a green tick. **A guard that can confirm garbage is worse than
no guard**, because it converts a visible false finding into an invisible one.

## Ground truth: read the ruled lines, not the proximity of labels

The two sheets are the same title block at a 2.5× coordinate ratio (revision verticals
`141.5, 152.0, 158.0, 175.5, 181.5, 210.5, 244.5` map to reference
`353.9, 380.1, 394.4, 439.0, 453.3, 526.4, 619.3` — all within 0.3 after ÷2.5; see
[[Gotcha - Reference and Revision in Different Coordinate Spaces]]).

| cell | revision | reference | contents |
| :-- | :-- | :-- | :-- |
| Previous Dwg. No. **value** | `x[152.0, 196.0] y[28.0, 34.5]` | `x[380.1, 489.8] y[68.6, 85.9]` | **empty on both sheets** |
| Job No. (工事番号) **value** | `x[181.5, 210.5] y[10, 28]` | `x[453.3, 526.4] y[25, 68.6]` | `9324` / `2589` |

`9324`'s bbox is `x 185.8–206.2`; `2589`'s is `x 460.5–519.2`. Both squarely inside the **Job No.**
cell. So `2589 → 9324` is a real change that was being reported as `JOB NO: NONE vs NONE — MATCHED`,
while the field that *did* produce a marker had no value on either sheet.

Job No. failed because `工事番号` is set as **four separate single-character vertical TEXT
entities** — no entity's text ever equals the pattern — leaving the English `Job No.` as the only
anchor. It sits at the *bottom* of the label cell with its value up and to the **right**, so a
`direction='below'` search with `prefer_lowest_y=True` ran off the bottom of the sheet.

## Fix

`title_block_extractor.py`
- `_collect_vertical_rules(entities)` harvests the grid from LINE/POLYLINE geometry. These entities
  already reach the extractor: `keep_for_title_extraction` filters on `geometry["insert"]`, which
  line geometry lacks, so the bbox test is a no-op for them (188 lines survive on the reference,
  189 on the revision).
- `_separated_by_rule()` rejects a candidate when a vertical rule lies between it and the label
  **and** that rule's y-span covers both points. The span condition matters: a stub that merely
  overlaps the band may be a divider one row up, not one standing between these two texts.
- Applied in the `direction == 'below'` branch **and** the multi-line grouping loop, which reuses
  the same rectangle and could otherwise stitch a neighbouring column onto a correctly-read value.
- `JOB NO` → `direction='right', dx_tol=22.0`.

`spatial_utils.py` — the short-target guard is now `(?<![0-9A-Za-z])…(?![0-9A-Za-z])`. Alphanumeric
boundaries, not merely non-digit ones, are what "whole token" actually means.

`marking_builder.py` — corroboration of a title value of ≤3 characters requires `match_level=1`
(exact whole-string equality). A few characters occurring *somewhere* in the title block is not
evidence. This errs toward showing a finding rather than hiding one.

Cache **v31 → v32**.

## ⚠️ The guard is below-only. Do not generalise it.

Crossing a vertical rule while searching **downward** always means landing in the wrong column.
Crossing one while searching **rightward** is the normal label-cell → value-cell move — Job No.
reads `9324` across the rule at x=181.5 and *depends* on not being blocked. Applying
`_separated_by_rule` to `'right'` re-breaks Job No. immediately. This was measured, not assumed.

## Negative result — what was rejected

**Tightening `dx_tol` for Previous Dwg. No. alone**, mirroring the `dx_tol=5` fix in
[[Gotcha - SCALE Field Read the Date Column]]. It works on this pair (reference dx=17.2 and
revision dx=7.1 both fall outside a tightened window) and is a one-line change. Rejected: it is a
magic number carrying no information about *why* the candidate is wrong, and that gotcha's own
closing note already warns the constant is calibrated on n≈1 and "could still miss" on another
standard. The ruled lines are in the file, exact, and mean precisely "different cell" — the geometry
was there to be read all along.

Also rejected: extending `is_garbage_value` to reject bare single alphanumerics. It needs a
per-field opt-in, since `QTY = 4` and `REVISION CODE = 1` are legitimately single characters, and
the rule guard already removes the candidate.

## Guarded by

- `tests/test_extraction_logic.py::test_below_search_does_not_read_across_a_ruled_vertical` —
  measured revision geometry; asserts the candidate IS picked without the rule, so the fixture
  provably exercises the guard rather than passing for an unrelated reason.
- `tests/test_extraction_logic.py::test_below_search_still_reads_a_value_in_its_own_cell` — rules
  flanking both points must not block.
- `tests/test_extraction_logic.py::test_job_no_reads_value_to_the_right_of_its_label` — includes the
  label/value divider the guard must ignore.
- `tests/test_title_block_corroboration.py::test_single_char_value_is_not_corroborated_inside_a_longer_token`

## Traps

- `dx_tol=22.0` for Job No. was measured across **all six DXFs in the corpus** and the true value is
  the closest candidate on every one (reference dx=38.6 at coord_scale 1.80; revision dx=15.1 at
  1.00). The runner-up inside the window is the sheet-margin label `４`, which loses on the right
  branch's 4×-dy-weighted distance — the ordering is safe, not lucky. Still re-measure on a new
  customer's standard.
- `coord_scale` (median text height ÷ 2.5, clamped 1.0–3.0) **under-estimates** the real ratio here:
  it reads 1.80 on the reference where the measured coordinate ratio is 2.50. That under-shoot is
  why tolerance-only fixes are fragile, and it is unchanged by this work.
- The Previous Dwg. No. label pair is `旧図面番号` + `Previous Dwg. No,` — with a **comma**, not a
  period. The English pattern `"Previous Dwg. No."` therefore never matches, on either the exact or
  the substring pass. Only the Japanese label anchors this field.
