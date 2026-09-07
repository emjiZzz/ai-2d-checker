---
title: Gotcha - Full-Width Grid Labels Bridged Zone Clusters
type: gotcha
tags: [gotcha, zone-detector, nfkc, shift-jis, category-attribution, drawing-views]
status: resolved
date: 2026-07-30
---

# 🔥 Gotcha — Full-Width Grid Labels Bridged Zone Clusters

The first live end-to-end comparison of the KEMCO pair `bc17b56d` / `63adc691`
(2026-07-30, cache v18→v19) produced 32 findings, **22 filed under
`comparison_drawing_views`**. Most of those 22 were not drawing content — they were the
sheet's frame furniture and the amendment/revision-history table headers. This is the
category-attribution half of what [[Gotcha - Zone Detection Accuracy & Stability]]
predicted would surface once `views` became the whole sheet.

Corpus for every figure here: the two drawings named above, one customer, one drawing
standard. n is effectively 1 pair. Do not generalise the constants without re-measuring.

---

## The two defects

### 1. `is_margin_grid_text` never matched (the NFKC bug)

`zone_detector.is_margin_grid_text` is the filter that keeps sheet-frame reference labels
(`A`–`H` down the sides, `1`–`12` across) out of the entity pool that seeds zone
detection. It compared the **raw** text against ASCII `"A".."H"` / `"1".."12"`.

This standard draws its frame labels **full-width** — `Ａ` (U+FF21), `１` (U+FF11) — which
compare unequal to the ASCII forms. So the predicate returned `False` for every grid label
on every drawing in the corpus, and the filter at its one call site
(`detect_zones_by_content`, line ~641) was **inert**.

Consequence: the labels stayed in the detection pool, where single-linkage clustering
bridged them from one sheet edge to the other. The reference `tolerance` box came out
spanning x `8.4 → 411.6` — **21.4% of the sheet** — because it bridged via the grid letters
at x=18.4 and x=411.4. A zone box that wide then mis-claims or mis-excludes whatever falls
under it, and everything it fails to claim falls through to `drawing_views`.

The trap that hid it: `orchestrator.is_in_margin` was a near-duplicate of the same logic
that **did** call `unicodedata.normalize("NFKC", …)`. Two copies, drifted apart, and only
the inert one ran during zone detection. **Fix:** normalise NFKC in `is_margin_grid_text`,
and make `is_in_margin` delegate to it so there is one definition and one threshold.

### 2. The 6% band was below where the labels sit

Even normalised, the old 6.0% margin would have missed them. Measured, the grid labels
occupy two rings at **6.27–6.46%** and **7.43–8.52%** of the sheet dimension. The cutoff is
now **9%** (`GRID_LABEL_MARGIN_FRACTION`), clearing the outer ring by 0.5pp.

Widening a margin usually risks eating content. It is safe here **only** because
`is_grid_char` is a tight predicate — a bare letter `A`–`H`, a bare digit `1`–`12`, or a
circled numeral. The nearest non-grid text in the same band is multi-character
(`M745203N01` at 8.28%, `DWG.No.` at 8.95%) or a single CJK glyph (`行`, `号`, `発`) that no
branch matches. Audited collateral on both sheets: everything newly dropped is the frame
ruling itself (letters at x=18.4/411.4 spaced 50 apart, digits at y=5.9/287.6 spaced 50
apart). The one interior pair caught — tolerance-grade cells `4`/`6` at x=145.9 on the
revision — already sat inside the `tolerance` box and was excluded anyway.

### 3. Amendment-table headers are excluded by text, not position

The revision-history table (`Amd.`, `Y/M/D`, `Design Chg No.`, `Name`,
`Previous Dwg. No,`, `旧図面番号`, `旧工事番号`, …) is title-block furniture, but it is **not
reliably inside the detected `title` box**. On the revision it sits at x 338–402, inside
`title`; on the reference the same table sits **bottom-left** at x 28–129 while `title`
starts at x 152. `title`'s bottom-right quadrant filter excludes bottom-left anchors by
design, and widening `title` to reach across would breach its 0.60 width cap and swallow
the bottom strip.

So the headers are excluded by an exact NFKC-lowercase text match against
`REVISION_TABLE_HEADERS` (`orchestrator.py`), which is position-independent. **Headers
only** — the table's *values* (`2491FSRS`, `M745203N01`, dates, amendment codes) are real
content that a genuine revision changes, and they stay in the comparison. Match is exact,
never substring: `name` is short enough that substring matching would suppress unrelated
text (`Nameplate`).

---

## What is fixed

**Grid + headers:** all 17 amendment-header instances across the pair are dropped from the
drawing_views pool; both drawing-number values are kept; 12 of 15 stray grid letters are
dropped by the margin filter (the other 3 are the amendment row-letter column, handled
below).

**Amendment-table content → title_block (reclassification):** the reference amendment table
has an `A/B/C/D` **row-letter column** at x=29.2 and value cells (`2491FSRS`) that survive
header/grid filtering and, because the table sits bottom-left *outside* the detected `title`
box, land in `drawing_views`. This is category attribution, not detection — the finding is
real, just under the wrong heading.

`amendment_table_bboxes` (orchestrator, module-level) locates the table by **clustering its
own header anchors** (position-independent: bottom-left on the reference, inside `title` on
the revision), then any `drawing_views` marking whose CAD-unit position falls in a cluster
box is **relabelled** `title_block`. Relabel only, never dropped — a loose or wrong cluster
mislabels at worst and can never cause a false negative, which is why its pad/join constants
can be approximate. Guards: ≥2 headers per cluster, box capped at 20% of the sheet.

Measured on the pair: the x=29.2 row letters and `2491FSRS` reclassify to title_block; sheet
centre is untouched; the frame letters at x=18.4/411.4 never reach this stage (the grid
filter drops them upstream) and `M745203N01` was already title_block via the structured
DWG.No. path. Pinned in `tests/test_margin_grid_labels.py::TestAmendmentTableReclassification`.

---

## Guarded by

- `tests/test_margin_grid_labels.py` — 31 cases: full-width letters/digits excluded, ASCII
  still excluded, the 8.52% ring covered, multi-char and single-CJK content in the band
  kept, headers matched exactly, values kept, the residual row-letter column documented.

## Traps for the next person

- **Two coordinate/normalisation copies drift.** This bug lived because
  `is_margin_grid_text` and `is_in_margin` were duplicates and only one normalised. They now
  share one definition — keep it that way.
- **Zones here come from a template, not detection.** The revision (aspect 1.4141) matched
  template `aspect-1.414` and its 9 boxes were pinned; the reference (aspect 1.3611) did
  not and used content detection + percentage fallback. A zone-box change you expect to see
  may be masked by a pinned template. See [[Persistent Sheet Zone Templates]] if present.
- **`views` is the sheet.** Anything no other zone claims lands in `drawing_views`. Reducing
  drawing_views noise is mostly about making the *other* zones claim correctly, not about
  touching `views`. See [[Gotcha - Zone Detection Accuracy & Stability]].
- Cache bumped **v18 → v19**; note in `cache_manager.py`. Zone boxes move on every drawing,
  so this invalidates category attribution and coordinate resolution for all zones.

## Still unmeasured

False-negative rate. Everything here reduced misfiled noise; nothing established that real
changes are caught. There is still no drawing pair with a known change list to score
against. See [[00 - AI Agent Navigation & System Gap Analysis]].
