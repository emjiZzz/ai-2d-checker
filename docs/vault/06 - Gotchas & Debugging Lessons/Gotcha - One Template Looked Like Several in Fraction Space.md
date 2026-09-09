---
title: Gotcha - One Template Looked Like Several in Fraction Space
type: gotcha
tags: [gotcha, zone-templates, coordinate-spaces, ground-truth, title-block, bom, measurement]
status: resolved
date: 2026-09-08
---

# 🔥 Gotcha — normalising by `render_bounds` turned one drawing template into several

## 🧭 Context

The prototype build's first real harvest landed on 2026-09-07: **239 `ground_truth_markings`** across
8 sessions, 229 of them carrying **both** `ref_address` and `rev_address`. That is the first
positive, entity-addressed statement of *which two entities correspond* that this project has ever
held — [[Gotcha - A Marking Cannot Store an Entity Id]] explains why the address, not an id, is what
makes it durable.

The obvious first question was whether the title block and BOM sit in stable places, because a
stable place turns matching into a lookup. Positions were normalised the way every zone template in
this system stores them: as **fractions of `render_bounds`**.

## ⚠️ The wrong answer, and why it was persuasive

In fraction space the numbers said:

| category | fx sd | fy sd |
| :--- | ---: | ---: |
| `title_block` | 0.255 | **0.357** |
| `bill_of_materials` | 0.136 | 0.012 |

That reads as *the title block is the least stable thing on the sheet*, and the BOM columns looked
like **two different table layouts** — five sheets agreeing on one set of column fractions and
`M745200N01` on another. A note was drafted saying the corpus held two BOM templates and that
template identity would have to be induced automatically.

Both readings were wrong, and neither looked wrong. **The owner corrected it from domain knowledge**
before it was written down: there is one BOM template, the extra columns are optional, and assembly
drawings simply use bigger paper.

## 📏 The right answer — measure from a sheet corner

`render_bounds` is **the ISO sheet inflated by 1.1**, so the margin between the bounds edge and the
real sheet edge scales with paper size:

| paper | `render_bounds` | sheet | margin x | margin y |
| :--- | :--- | :--- | ---: | ---: |
| A3 | 462.0 x 326.7 | 420 x 297 | 21.00 | 14.85 |
| A2 | 653.4 x 462.0 | 594 x 420 | 29.70 | 21.00 |

Dividing by a denominator that differs by 8.70 units in x and 6.15 in y is what manufactured the
spread. Measured from a corner instead, the six A3 sheets are **identical to 0.00 units**:

```
unit_number   (from sheet left / top)      machine_name  (from sheet right / bottom)
  A3  x= 56.00  y= 38.85   x5 sheets         A3  x= 82.88  y= 55.35   x5 sheets
  A2  x= 64.70  y= 50.00                     A2  x= 96.58  y= 66.50
  A3-only sd:  x 0.00  y 0.00                A3-only sd:  x 0.00  y 0.00
```

Strip the bounds margin and the A2 difference is not a scale factor — it is a **constant 5.00-unit
frame inset** on the right, top and bottom, and **flush on the left**:

| field | anchor | A3 | A2 | delta |
| :--- | :--- | ---: | ---: | ---: |
| `unit_number` | sheet left | 35.00 | 35.00 | **0.00** |
| `unit_number` | sheet top | 24.00 | 29.00 | **+5.00** |
| `machine_name` | sheet right | 61.88 | 66.88 | **+5.00** |
| `previous_drawing_number` | sheet bottom | 16.50 | 21.50 | **+5.00** |

One template, two paper sizes, one inset constant. Exactly what the owner said.

## 🧩 The category was bimodal, which is the other half of the mistake

`title_block` sd 0.357 was **not** noise — it was two physically separate blocks pooled into one
number. They anchor to different corners:

- **Upper-left block** (`unit_number`, `part_number`, `stock_quantity`, `quantity`) → **left / top**
- **Bottom block** (`machine_name`, `line_name`, `previous_drawing_number`, `machine_unit_code`,
  `drawn`, `designed`, `scale`, `job_number`, `creation_date`) → **right / bottom**
- **BOM** → **right / top**, rows on a ladder of pitch **7.00 units**

See [[Gotcha - Title Block QTY Reads the Upper-Left Table]] for the earlier bug caused by the same
two-blocks-one-name confusion. **The unit of stationarity is the field, never the category.**

## ✅ Negative results worth keeping

Recorded per hard constraint #4, because each one cost a measurement and would otherwise be redone.

- **`material_specification` is not an unstable field.** Its apparent fx sd of 0.15 came from a
  single marking at fx 0.164 that the annotator had already **retracted**. Filtering `retracted_at`
  removes it. The same is true of the `job_number` outlier at x 173.42 against five sheets at
  245.00. **Retracted markings must be excluded before any position is measured** — they are
  corrections, and reading them as observations reintroduces the error the annotator fixed.
- **`material_weight` is two columns wearing one feature name** (unit weight and total weight). Its
  14.00-unit within-sheet spread is the column gap, not jitter. The marking vocabulary has no column
  identity, so anything learning from it would fit a bimodal x. This is a schema gap, not a defect.
- **`drawing_views` does not do this and never will** — fx/fy sd 0.133/0.139, with no structure to
  decompose. Its content moves with the revision, which is the thing being compared. Location priors
  are for furniture; views need the matcher. See
  [[Gotcha - drawing_views Was the Residual, Not the Views Box]].
- **The CAD symbols are stored correctly.** `⌀265×20` read back as `'?265\xd7~20'` in the console;
  the stored codepoints are `0x2300` and `0xd7`. That was
  [[Gotcha - Our Own Punctuation Broke on the cp932 Console]] again, not a data defect. It was worth
  the one check, because a corrupted BOM value would have invalidated the text half of the corpus.

## 💥 Why this matters beyond the measurement

Every zone template stores fractions of `render_bounds`, and
[[Gotcha - Global Default Zone Template & the Aspect Caveat]] already records that a fallback
template's boxes scale proportionally onto whatever sheet inherits them. That note treats
proportional scaling as intrinsic and acceptable **for a zone box**, which it is — a box only has to
contain its table.

It is **not** acceptable for a field. A zone box tolerates a few percent of drift; a title-block cell
is a few millimetres tall, and 8.70 units of margin error is larger than the cell. So the two live at
different granularities and must not share a frame:

- **zone box** → fractions of `render_bounds`, as today
- **field anchor** → drawing units from the frame corner, per paper size

Anything that compares field positions across paper sizes in fraction space will produce a plausible
wrong cell, which is the failure mode this vault exists to catch.

The Y-direction conversion is untouched by this. Fields anchor in the same paper-space frame the
markings were captured in, so nothing here re-derives the Y-DOWN/Y-UP flip that
[[Gotcha - Reference and Revision in Different Coordinate Spaces]] and hard constraint #3 keep in
`zoneFractions.ts`.

## 🛠️ Where it lives

- `tools/title_block_anchors.py` — measures offsets from every sheet edge out of the live markings.
  Read-only. `--write-fixture` regenerates the committed observations.
- `tests/fixtures/title_block/anchor_observations.json` — **observations only**, 158 rows. The rules
  that turn them into anchors live in the test, so a rule change is a reviewable diff rather than a
  silent change inside a regenerated blob.

## 🧪 Guards

`tests/test_title_block_anchors.py`, all six mutation-checked (an inset of 0.00, a pitch of 8.00 and
a field moved to the wrong block each fail the expected tests):

- `test_render_bounds_is_the_iso_sheet_inflated_by_one_point_one` — the premise everything rests on.
- `test_title_block_fields_are_fixed_within_a_paper_size` — sd 0.00 against the field's own corner.
- `test_the_two_title_blocks_anchor_to_different_corners` — pins the bimodality, and fails if the
  corpus stops covering both blocks, since the test could not then detect the pooling mistake.
- `test_absolute_offsets_agree_where_fractions_do_not` — **the trap itself**. A fraction table would
  pass every other test in the file, so the comparison is pinned rather than only the result.
- `test_the_frame_inset_is_one_constant_per_paper_size` — an inset, not a scale, at 5.00.
- `test_bom_rows_are_evenly_pitched` — pitch 7.00, so a BOM with N items is one constant.

## ⚖️ What this does not establish

Six A3 sheets and one A2. That proves the template is stable and **not** that it is the only one in
the population, so anything built on it needs an unrecognised-frame path that degrades to today's
detection rather than to a confident wrong cell. The corpus is also 8–31% of text entities per sheet:
**an unmarked entity is not an unpaired one**, and mining negatives from unmarked entities would
teach a matcher that most correct pairs are wrong.

## 🔗 Related Notes
- [[Gotcha - Global Default Zone Template & the Aspect Caveat]] — the same fractions, at the
  granularity where they are correct.
- [[Gotcha - Title Block QTY Reads the Upper-Left Table]] — the earlier cost of pooling the two blocks.
- [[Gotcha - Reference and Revision in Different Coordinate Spaces]] — why the paper side is the
  stable frame at all.
- [[Gotcha - drawing_views Was the Residual, Not the Views Box]] — the category this does not cover.
- [[Gotcha - Our Own Punctuation Broke on the cp932 Console]] — the mojibake that was not a defect.
- [[00 - AI Maturity Status]] — the ledger; this is measurement, not a rung claim.
- Return to [[00 - Map of Content (MOC)]]
