---
title: Gotcha - Reference and Revision in Different Coordinate Spaces
type: gotcha
tags: [gotcha, spatial-differ, rag, coordinate-space, viewport, measurement]
status: resolved
date: 2026-07-29
---

# 🔥 Gotcha — the two sides of a comparison are not in the same coordinate space

`SpatialDiffer` matched reference against revision in **raw CAD units**, on the unstated
assumption that both drawings use the same ones. They frequently do not.

`dxf_parser` projects model-space geometry into paper space **only when the drawing has a
paper-space viewport**. A DXF without one keeps its model units. So a reference authored in
AutoCAD (no viewport) and a revision regenerated from 3D (viewport) end up stored at
different scales — and are then compared coordinate-to-coordinate.

---

## 📏 Measured — the M7452A0N01 pair

| | reference | revision |
| :--- | :--- | :--- |
| `metadata.coordinate_space` | `model` | `paper` |
| text-entity span | 982.7 x 709.0 | 393.1 x 283.6 |
| `render_bounds` | 1155.00 x 816.75 | 462.00 x 326.70 |

**Exactly 2.500x apart.** Confirmed on text that is identical in both drawings:

| text | reference | revision | ratio |
| :--- | :--- | :--- | ---: |
| `FSRS2` | 623.6, 40.5 | 245.5, 16.5 | 2.54 |
| `M7452A0N01` | 792.0, 40.5 | 311.5, 16.5 | 2.54 |
| `津田` | 581.1, 90.2 | 232.3, 36.0 | 2.50 |
| `2A0` | 136.9, 685.0 | 54.7, 273.0 | 2.50 |
| `45` | 87.5, 685.0 | 35.0, 273.0 | 2.50 |

---

## ⚠️ Why the pre-alignment could not save it

`calculate_global_offset` estimated a **translation** — a median `(dx, dy)` over exact text
matches — and nothing else. A scale difference is not a translation: the offset each entity
demands grows with its distance from the origin. Across that sheet the required `dx` ranged
from **-52.5** (`45`, near the left edge) to **-480.5** (`M7452A0N01`, far right). No single
median satisfies a 428-unit spread.

Compounding it, the match thresholds were absolute CAD units (5 / 10 / 150, widened to 750).
150 units is 13% of the reference sheet but 32% of the revision's — the same constant meant
two different things on the two sides of the same comparison.

**Result:** unchanged text away from the alignment centroid could never pair. It was emitted
as `REMOVED` on the reference side and `ADDED` on the revision side — one unchanged label
producing two false findings.

---

## ✅ Fix — match in a normalized frame

Each drawing's coordinates are divided by **its own `render_bounds`** into a unit square
before matching. The scale term disappears, and thresholds become fractions of the sheet, so
they mean the same thing on both sides.

`45` went from unmatchable to a separation of **0.003**.

Measured over the pair's real 249 / 254 text entities:

| | before | after |
| :--- | ---: | ---: |
| MATCHED | 200 | **234** |
| CHANGED | 22 | **6** |
| ADDED | 32 | **14** |
| REMOVED | 27 | **9** |
| ADDED+REMOVED as share of findings | 21.0% | **8.7%** |

> [!IMPORTANT]
> The `CHANGED` collapse from 22 to 6 matters as much as the ADDED/REMOVED drop. Those were
> **false pairings**, not real edits: with the alignment broken, the nearest candidate for a
> string was often unrelated. It produced findings like `"1/2.5"` reported as changed from
> `"2010/09/13"` — the title block's *scale* diffed against its *date*. That looked like a
> title-block field-mapping bug and was very nearly fixed as one. It was this.

> [!WARNING] Correction (2026-07-30) — there were TWO scale-vs-date bugs, not one.
> The claim above ("it was this, not a field-mapping defect") was **incomplete**. It is true
> for the *SpatialDiffer* variant — loose text pooled across a broken alignment, where a
> scale string paired with an unrelated date. But the first live end-to-end run also produced
> a *structured* title-block finding, `[CHANGED] Title block SCALE checked: '04/12/22\n20' vs
> '1/1'` (the `marking_builder` "… checked:" format, a different code path). That one **was**
> a field-mapping defect: `title_block_extractor` resolved SCALE with `direction='right'`,
> which skipped the value directly beneath the label and grabbed the adjacent Y/M/D date
> column. Fixed by switching SCALE to `direction='below'` with a tight `dx_tol`. See
> [[Gotcha - SCALE Field Read the Date Column]]. Lesson: "scale vs date" is a *symptom* with
> at least two independent causes — check which code path emitted the finding (`checked:` =
> structured extractor; a bare paired string = SpatialDiffer) before attributing it.

Two invariants worth keeping:

1. **Normalize both sides or neither.** Normalizing one alone puts the drawings in frames
   ~1000x apart and matches nothing. Guarded by `test_one_sided_bounds_fall_back_rather_than_normalizing_one_side`.
2. **Normalization is for matching only.** `raw_x`/`raw_y` stay in CAD units and are what
   every marking reports, because coordinate resolution, canvas pins and redline writeback
   all need real drawing coordinates. Guarded by `test_matched_output_coordinates_stay_in_cad_units`.

Rounding is also space-dependent: the old `round(dx, 1)` is harmless in CAD units and
catastrophic in a frame where the whole sheet is 1.0 wide.

---

## 🧩 What this did NOT fix

Twelve findings newly appear as ADDED+REMOVED pairs, and they are **honest**: the notes block
genuinely relocated by more than the widened same-text threshold (0.150 of sheet). The old
code matched them only by accident, via an offset that was wrong in a compensating direction.

They are correctly *detected* but wrongly *presented* — a relocated line should be one
`MOVED` finding, not a `REMOVED` plus an `ADDED`. That reconciliation is still open, and it
is the same mechanism as the zone-split double counting: when the same text lands in
different buckets on the two sides, it is reported twice. See
[[Gotcha - Zone Detection Accuracy & Stability]].

---

## 🔎 How to spot this class of bug

Compare `metadata.coordinate_space` on the two drawings. If one says `model` and the other
`paper`, anything comparing their raw coordinates is suspect. The zone pipeline is safe —
zone boxes are computed per drawing in that drawing's own space, and templates are stored as
`render_bounds` fractions — but the differ was not.

---

## 🔗 Related Notes
- See [[Gotcha - Zone Detection Accuracy & Stability]] — zone-split double counting, the remaining half of the noise
- See [[Gotcha - Dropped ELLIPSE & SPLINE Geometry]]
- See [[Gotcha - Comparison Cache Invalidation]] — why this went to `v12`
- See [[RAG Engine (Deterministic)]]
- Return to [[00 - Map of Content (MOC)]]
