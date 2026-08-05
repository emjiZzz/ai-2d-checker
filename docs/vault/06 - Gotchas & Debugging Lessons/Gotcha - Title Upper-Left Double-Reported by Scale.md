---
title: Gotcha - Title Upper-Left Double-Reported by Scale
type: gotcha
tags: [gotcha, title-block, upper-left, matching, coordinate-scale]
status: resolved
date: 2026-07-30
---

# Every upper-left value reported as REMOVED *and* ADDED at once

The title-upper-left metadata table (`Unit No. | Part No. | T. Q'ty | Stock Q'ty`) is
**identical** on the KEMCO pair — `45 / 227 / 16組 / 0` on both drawings. Yet the comparison
reported all four values as REMOVED (ref → NONE) **and** ADDED (NONE → rev): eight spurious
findings for zero real change.

## Root cause: a fixed band threshold + exact-key matching

`extract_title_ul_kv` groups the table into horizontal y-**bands** with a hardcoded 4.0-unit
threshold, treats the last band as values and the earlier bands as headers, and joins all
header parts into the field's key. The two stacked header rows (English `Unit No.` over
Japanese `ユニットNo.`) sit ~1 text-height apart — which is **8-9 units on the large-coordinate
reference** (two bands → key `Unit No. / ユニットNo.`) but **3.3 units on the small-coordinate
revision** (one merged band → key `Unit No.`). The old matcher keyed an exact-string lookup on
the combined key, so the same field carried different keys on the two drawings and never
paired → REMOVED + ADDED.

## Fix 1 — match on a shared header token

`match_title_ul_pairs` (module-level, in `orchestrator.py`) pairs ref↔rev fields if their keys
share **any** normalized header token (split on `' / '`). The reference's `Unit No. /
ユニットNo.` always contains the revision's `Unit No.` (or, for Stock Q'ty, the revision kept
the Japanese `在庫棚入庫`, which the reference's key also contains). Unrelated fields share no
token, so they never cross-match; a field on only one side stays one-sided (a real ADDED).

## Fix 2 — a scale-relative grid-label guard

That left one residual: Stock Q'ty read `NONE vs 0` because `is_grid_label` dropped the
reference's `0` value. Its guard was `vx < 25.0 or vy > 285.0` — absolute constants that only
hold in the small coordinate space; on the large reference the `0` sits at y≈822 > 285 and was
discarded as a top-margin frame label. Now measured **relative to the UL zone bbox**
(`vy > bbox_top - 0.08*height`, `vx < bbox_left + 0.08*width`), so a value inside the table is
never mistaken for a frame reference at any scale.

Result (verified live): all four UL fields read MATCHED; `title_block` dropped from 12 findings
(8 of them spurious UL double-reports) to 9 — 5 MATCHED, 3 CHANGED (the real designer/drawn/
scale edits), 1 REMOVED (the revision-side `DWG. No.` still reads NONE — a separate
spatial-extraction gap, not this).

## Guarded by / cache

`tests/test_title_ul_matching.py` (token split, same-field pairing incl. the Japanese-label
Stock case, genuine ADDED stays one-sided, no cross-match). Cache **v23→v24**. This is the
same hardcoded-threshold-vs-coordinate-scale family as [[Gotcha - SCALE Field Read the Date
Column]] and [[Gotcha - Mislocated OCR Crop and Ungrounded Misreads]].
