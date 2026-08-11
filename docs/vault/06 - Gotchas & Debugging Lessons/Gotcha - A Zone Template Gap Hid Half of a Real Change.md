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

## What was deliberately not done

The template was **not** re-drawn. A hand-aligned box is what the runner scores against, so
silently widening `bom` would change measured precision and recall on a pair whose numbers are
already published in `baseline-v43.json` — a scoring change disguised as a fix. It is reported to
the annotator, who owns the boxes.

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
