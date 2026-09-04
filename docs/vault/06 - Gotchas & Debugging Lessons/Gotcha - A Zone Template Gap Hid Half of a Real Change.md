---
title: Gotcha - A Zone Template Gap Hid Half of a Real Change
type: gotcha
tags: [gotcha, zones, eval, corpus, annotation, ground-truth, stage-0b]
date: 2026-08-11
related: [Eval Corpus Annotation Guideline, 00 - AI Maturity Status, Gotcha - Zone Detection Accuracy & Stability, Gotcha - drawing_views Was the Residual, Not the Views Box, Gotcha - Reference and Revision in Different Coordinate Spaces]
---

# A zone template gap hid half of a real change

Found on 2026-08-11 by the first thing that ever asked *"which zone is each annotation row in?"* —
the worksheet triage added to `tools/eval_corpus.py`. It was not looking for this.

## The finding

On pair `M745203N01`, a genuine dimensional change is split across two zone states:

| side | address | text | position | zone |
| :--- | :--- | :--- | :--- | :--- |
| reference | `REF#321` | `4.5x40x48` | @(241.1, 268.3) | **none** |
| revision | `REV#405` | `4.5×40×52` | @(238.5, 269.5) | `bom` |

Same BOM row, ~2 units apart, `48` → `52`. On the revision side it sits inside the `bom` box. On
the reference side it sits in a **~7.8-unit unzoned sliver**: that template's `views` box ends at
y=268.0 and its `bom` box begins at y=275.8.

```
   y=275.8  ┌──────────── bom ────────────┐
                                              ← REF#321 @ 268.3 falls here, in neither
   y=268.0  └─────────── views ───────────┘
```

## The bigger one, found by sweeping the same check across every pair

The BOM sliver above is a single-pair accident. Running the no-zone check over all six loadable
pairs found something systematic, and it is the reason this note matters more than one stranded
row.

**Every `aspect-1.414` revision template has the same `notes` box — y 204.4 to 261.4 — and it is
roughly 13 units too short.** The same two strings fall above its top edge in all three large pairs:

| pair | rows | y | above the top by |
| :--- | :--- | ---: | ---: |
| M745203N01 | `REV-2DB`, `REV-2DC` | 271.2, 262.3 | 9.8, 0.9 |
| M745227N01 | `REV-2E2`, `REV-2E3` | 273.8, 265.5 | 12.4, 4.1 |
| M745230A01 | `REV-447`, `REV-446` | 274.4, 266.4 | 13.0, 5.0 |

The strings are `４ロール：１２（２×６台）` and `２ロール：　４（２×２台）` every time — roll
counts. On M745203N01's **reference** side the equivalents (`REF-228`, `REF-227`) sit *inside*
`notes`, at y 247.5 and 255.6.

So the reference zones this content and the revision drops it, systematically, on every large pair
in the corpus. A roll-count change is exactly what a checker is employed to catch, and it is
currently unlabellable on one side.

**Why it reads as an accident until you sweep:** each individual row is 1–13 units outside a box,
which looks like a rounding artefact rather than a defect. It is only when the same two semantic
strings turn up stranded in three separate pairs that it resolves into "the box is wrong", not
"these rows are unlucky". One instance is noise; three identical instances are a measurement.

## Why this is worse than a missing box

The guideline is explicit that out-of-zone content is out of scope:

> *"Anything outside the `views` box that belongs to no zone… is genuinely out of scope. If you
> believe a real change sits there, that is a **zone-detection bug**: record it in `notes` and
> file it, do not label it as a comparison finding."*

So an annotator following the rules correctly does **not** label `REF#321`. The rule is right; the
box is wrong. The result is a REMOVED-side anchor that no label can reference, and the pair's
ground truth quietly loses one side of a real CHANGED.

**This is the failure mode ground truth cannot self-detect.** A wrong label is visible when the
engine disagrees with it. A change excluded by a template gap produces agreement — the engine does
not report it, the labels do not contain it, and precision and recall both look fine. It inflates
the score in the direction the whole corpus exists to measure.

## Why the boxes differ per side at all — and why that is *not* the bug

Each side resolves its fractional template against **its own** `render_bounds`, and the two sides
of a pair are routinely in different coordinate spaces — `M745227N01`'s reference is
1323×935 against a 441×312 revision, a 3× difference. See
[[Gotcha - Reference and Revision in Different Coordinate Spaces]]. Per-side resolution is correct
and the runner depends on it. `M745203N01` goes further: its sides carry *different signatures*
(`aspect-1.361` vs `aspect-1.414`), so they are genuinely two different hand-drawn templates.

The defect is not that the two sides differ. It is that **one of them has a gap between adjacent
boxes**, and nothing checks adjacency.

## What was deliberately not done — *superseded 2026-08-12, see below*

The template was **not** re-drawn. A hand-aligned box is what the runner scores against, so
silently widening `bom` would change measured precision and recall on a pair whose numbers are
already published in `baseline-v43.json` — a scoring change disguised as a fix. It is reported to
the annotator, who owns the boxes.

## Repaired 2026-08-12 — and the diagnosis above was wrong in two places

The owner re-drew the template. Rows in no zone: **9 → 1**. Both original diagnoses needed
correcting, and the corrections are the useful part of this note.

**1. The reference sliver was `bom`, not `views`.** This note said `views` ends at y=268.0 and
`bom` begins at 275.8, and read that as `views` being short. It is `bom` whose **bottom edge cuts
through its own header row**: lowering it files `No.`, `Code`, `Dimension/Model No.`, `Q'ty`,
`Material Weight(kg)`, `Finished Weight(kg)` and the first data row (`1`, `SS400`, `4.5x40x48`,
`0.07`) inside `bom`, where they belong. Raising `views` instead would have filed BOM cells as
drawing content.

**Ten of those rows had never appeared on any worksheet**, because the worksheet lists only
*unmatched* rows and they match on both sides. The nine rows this note counted were the visible
part of a larger set — worth remembering when a count comes from a tool that filters first.

**2. The revision rows are in a *column* gap, not a vertical one.** `REV-2DB`/`REV-2DC` and their
twins sit at x 116.6–121.7, between `title_upper_left` (ends x=103.9) and `bom` (starts x=199.7),
above `notes`. No vertical adjustment reaches them; measured, closing the vertical band rescued 15
rows but only **2 of the 9**. They were reached by reshaping `views` into a 12-vertex outline with
a riser up that column.

**3. Re-drawing was not free, and the cost was a second defect.** Stretching one template over two
differently-laid-out sides cost 3 findings and 5 category attributions until two edges were pulled
back. That is its own note: [[Gotcha - One Zone Template Cannot Fit Two Sides]].

**A residual check does not catch the successor defect.** `tests/test_zone_template_residual.py`
now asserts no unmatched row falls outside every zone — which is this note's rule made executable —
but a row swallowed by the **wrong** zone is still inside a zone. Only category attribution sees
that, and only on labelled pairs.

`REF-192` (`CS SW M6x16 2x2コ`, 6.6 units above `bom`'s top, nothing else in that band, no
counterpart on the revision) is **accepted as genuinely out of zone** rather than enclosed, and is
a named exemption in that test with a staleness check attached.

## The transferable rule

> **Zones are an allowlist, and an allowlist needs a residual check.** Any hand-drawn zone set
> should be tested for gaps between adjacent boxes, not only for whether each box is in the right
> place.

Related and not the same: [[Gotcha - drawing_views Was the Residual, Not the Views Box]] is the
opposite error — `drawing_views` used to *be* the residual and swept in everything unzoned.
Scoping it strictly to the views box was right, and it is what turned "unzoned" from a catch-all
into a silent drop. This note is the cost of that correction, and does not argue against it.

## Where it surfaces now

`tools/eval_corpus.py worksheet` prints a **Rows in no zone — out of scope** section, carrying the
guideline's own instruction to file a zone-detection bug rather than label it. That section is
where this was found, and its existence is the reason the triage never merges "no zone" into the
safe-zone pile: the safe-zone pile is *confirm and move on*, and this one is *look*.

Pinned by `tests/test_worksheet_triage.py`, whose fixture boxes are modelled on this pair's real
reference template — gap included — so the case stays exercised.
