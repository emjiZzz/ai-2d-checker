---
title: Gotcha - One Zone Template Cannot Fit Two Sides
type: gotcha
tags: [gotcha, zones, zone-template, eval, corpus, measurement, stage-0b]
date: 2026-08-12
cache-version: v45 — the template that exposed this is a v45 template
related: [Gotcha - A Zone Template Gap Hid Half of a Real Change, Gotcha - Zone Detection Accuracy & Stability, Gotcha - Reference and Revision in Different Coordinate Spaces, Gotcha - Global Default Zone Template & the Aspect Caveat, 00 - AI Maturity Status]
---

# One zone template cannot fit two sides

Found on 2026-08-12 by the owner, hand-aligning zones in the editor:

> *"Whenever I adjust the zone box from reference drawing, it will adjust slightly downward
> because of template mismatch. Reference drawing is off a little bit from revised template,
> that's why our zone box adjusts upward to match with revised and includes the numbers 1-8."*

That is exactly right, and it is measurable.

## The measurement

For every text present on **both** sides of a pair with the same normalised value — frame grid
labels `1`–`8` / `A`–`F`, BOM column headers — compare its position as a **fraction of that
side's own `render_bounds`**. If one fractional template fits both sides, those fractions agree.

| pair | landmarks | dy (rev − ref) mean | range |
| :--- | ---: | ---: | :--- |
| M745203N01 | 14 | −0.0164 | −0.0330 … +0.0043 |
| M745227N01 | 13 | +0.0040 | −0.0000 … **+0.0458** |
| M745230A01 | 14 | +0.0014 | −0.0000 … +0.0125 |
| M7452A0N01 | 40 | +0.0002 | −0.0072 … +0.0066 |
| M7452A1N01 | 40 | +0.0002 | −0.0072 … +0.0066 |
| M7452A2N01 | 40 | +0.0002 | −0.0072 … +0.0066 |

Up to **4.6% of sheet height** — about 15 CAD units on a 326.8-unit sheet, comfortably more than
a text row is tall.

**The offset is not uniform.** M745203N01 spans −0.033 to +0.004 *within one pair*. That is the
part that matters: a uniform offset is a shifted sheet and could be corrected once, per side, with
a single number. A non-uniform one means the two sides are **genuinely different layouts** —
different row heights, different table extents — that happen to share an aspect ratio.

## Why the template collides them

`zone_signature()` (`domain/models/zone_template.py`) buckets on the rounded aspect ratio alone,
and its own docstring already says so:

> *"every A-series sheet is 1.414, so two genuinely different layouts printed on A-series paper
> collide into one template… do not treat matching aspect ratio as proof of matching layout."*

This note is that warning arriving. The resolution path is per-side and correct — each side
computes its own signature from its own `render_bounds` and resolves independently — so the
architecture already supports two templates. The defect is that the *key* cannot tell the two
sides apart, so both fetch the same document.

The editor then compounds it: regions are merged `{...reference, ...revision}`, so **the revision
pane's boxes win** (`TwoDWorkspace.tsx`). Aligning to what you can see on the revision silently
overwrites the reference's version of the same zone.

## What it cost, in findings

The 2026-08-12 hand-alignment closed the unzoned gap that
[[Gotcha - A Zone Template Gap Hid Half of a Real Change]] recorded — stranded rows **9 → 1** —
but two boxes had to be stretched to cover both sides at once, and each stretch was paid for:

| box | change | consequence | cost |
| :--- | :--- | :--- | :--- |
| `bom.yMax` | 0.1421 → 0.2620 (~2.8× taller) | swallowed drawing content on the reference | **3 findings lost**: `追加3-m8`, `タップ、キリ穴は面取り仕上げのこと` ×2 — they moved `views` → `bom` and stopped being compared |
| `notes.yMax` | 0.3290 → 0.2884 (shorter) | 12 rows fell out of `notes` into `views`, incl. `指示なき角部は糸面取りのこと`, `完成時、バリ、キリ粉はなきこと` | **attribution 1.00 → 0.89** (`notes_section→drawing_views` ×5) |

It also pulled 3 extra frame grid labels into a scored zone — **on the reference side only**
(11 → 14 on M745203N01; every revision side unchanged). That asymmetry is the fingerprint: a box
aligned on one side and applied to the other.

Measured over the 36-pair mutation corpus:

| | v43 | as saved | + both edges pulled back |
| :--- | ---: | ---: | ---: |
| precision | 0.9796 | 0.9783 | **0.9796** |
| recall | 0.8727 | 0.8182 | **0.8727** |
| F1 | 0.9231 | 0.8911 | **0.9231** |
| attribution | 1.0000 | 0.8889 | **1.0000** |
| rows in no zone | 9 | 1 | **1** |

So the compromise was not necessary *for the gap* — the reshaped `views` outline closes that on its
own. It was necessary only to make one box serve two layouts, and pulling both edges back recovers
v43 exactly while keeping the gap closed.

## The transferable rule

> **A template keyed on geometry that does not determine layout is a template that will be
> stretched until it fits, and the stretching is silent.** Every box becomes a compromise between
> the sheets colliding on that key, and the cost lands as lost findings rather than as an error.

The check that catches the *first* kind of defect does not catch this one, and that is worth
stating plainly: `tests/test_zone_template_residual.py` asserts no row falls outside **every**
zone. A row swallowed by the wrong zone is still inside a zone. **A residual check cannot see a
mis-attribution** — only the category-attribution metric can, and only on labelled pairs.

## Not yet decided

Whether to discriminate `zone_signature()` further (content anchors? explicit per-side templates?
a user-chosen template per drawing?) is **open**. Recorded here rather than fixed, because the
corpus's critical path is labelling and the edge corrections above buy back the whole regression.
See [[00 - AI Maturity Status]]'s "What's next" for the ordering.

Related: [[Gotcha - Reference and Revision in Different Coordinate Spaces]] is the *other* reason
the two sides differ — one stored in model units, the other in paper units. That one is handled;
this one is not, and they are independent.
