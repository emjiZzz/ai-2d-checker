---
title: Gotcha - drawing_views Was the Residual, Not the Views Box
type: gotcha
tags: [gotcha, comparison, zones, drawing-views, spatial-differ, cache]
status: resolved
date: 2026-08-03
---

# 🔥 Gotcha — `drawing_views` Compared the Whole Sheet, Not the `views` Box

## ⚠️ The Problem

Every other compared zone in the deterministic engine scopes to its own box — `notes`, `iso`
(via `extract_zone_entities`), `bom`, `title`, `title_upper_left` (structured extraction). But
`drawing_views` did **not**. It was the **residual**: `safe_filter` subtracted the *other* zones
and the margin from the whole sheet and compared **everything left over**. So content sitting
inside no zone box at all was still compared, and the pinned/detected `views` box was ignored for
scoping — it only fed coordinate placement and finding re-labeling. A user who pinned a `views`
box expecting it to bound the comparison found it disregarded.

The AI engine (`full_ai_orchestrator`) already scoped to `views_bbox` via `detect_subviews`, so
`rag`/`hybrid` were the outlier, not the design.

## 🛠️ The Fix

`drawing_views` now scopes strictly to the `views` box:
`scope_entities_to_views(entities, views_bbox, views_exclusions(regions))`
(in `bom/zone_detector.py`) keeps only entities whose centroid sits inside `views`, minus the
sibling zones. Its output feeds the existing `safe_filter` (same margin/layer/learned/structured
noise filters, now on the scoped set). A sheet with **no** views box yields an empty
`drawing_views` — **strict, no residual fallback**, by explicit decision.

## 🧨 The wrinkle: geometry has no `insert` point

Text entities carry `geometry["insert"]`, which `is_in_bbox` reads. Lines/arcs/ellipses do not —
their coordinates live under `start`/`end`/`center`/`points`/… A naive `insert`-only containment
test would have silently dropped **all drawable geometry** from the pool. Containment is therefore
computed from the entity **centroid via `_entity_points`**. If you ever add another zone-scoped
pool, use `_entity_points`, never `insert` alone.

> [!NOTE] The consumer this protected is gone.
> Drawable geometry was scoped this way for `geometry_differ.diff_geometry`, which was reverted on
> 2026-08-04 — see [[Gotcha - The Differ Compared Text Only]]. The `_entity_points` rule still
> holds for zone detection and any future geometry consumer; it just no longer feeds a differ.

## 💥 The load-bearing caveat (false negatives)

This flips the failure mode. The residual could never *miss* a real change — it compared
everything. Strict scoping can: **a small, mis-pinned, or missing `views` box now silently drops
content from comparison.** The views box is load-bearing. This was a deliberate, owner-approved
trade (predictable scope over catch-everything), but it means:

- A `views` box that doesn't cover the whole drawing area → changes outside it are not reported.
- No `views` box on a sheet → `drawing_views` is empty (a `logger.warning` fires; see orchestrator).
- **Total zone-detection failure** counts as "no views box." When sheet-bounds detection fails,
  every zone collapses to the `(0,0,1000,1000)` `percentage_fallback_no_sheet_bounds` placeholder
  (see [[Gotcha - Zone Detection Accuracy & Stability]]); the placeholder is not a real box, so
  `drawing_views` is empty. Real drawings with `render_bounds` + a pinned template `views` box
  never hit this — it's the degenerate/no-metadata path.
- The global default template's `views` box now does real work — see
  [[Gotcha - Global Default Zone Template & the Aspect Caveat]].

> [!WARNING]
> This change first looked like a *different* test regressing (`test_physical_comparison`) — but
> that test hit a stale on-disk **comparison cache** from before the cache bump, then recomputed
> the empty result on the next run. When a comparison-behavior change "breaks" a test, suspect a
> `storage/cache/gemini_comparison_*_vNN_*.json` cache masking the real output before chasing the
> code. The test drawing simply had no resolvable views box; giving it a real one fixed it.

## 🧊 Cache

`COMPARISON_CACHE_VERSION` bumped **v26 → v27** — comparison output changes on any pair where
content sat outside the views box. Cached pairs keep serving pre-change results until recomputed;
that's the usual [[Gotcha - Comparison Cache Invalidation]] rule (Re-test / force_refresh).

## 📌 Scope

Fixes `rag` and `hybrid`'s deterministic generator (both run `generate_deterministic_candidates`).
`ai_vision`/`full_ai` already scopes subviews to the views box; a deeper AI-path audit is a
separate follow-up, not part of this change.

## 🧪 Guards

`tests/test_views_scoping.py` — inside kept / outside dropped; sibling-excluded dropped; a **line**
(start/end, no `insert`) located by centroid; `views_bbox=None` → `[]`.

## 🔗 Related Notes
- See [[Gotcha - The Differ Compared Text Only]] — why `diff_geometry` was built alongside `diff_views`, and why it was reverted.
- See [[Gotcha - Zone Detection Accuracy & Stability]] — why a wrong box is now costlier.
- Return to [[00 - Map of Content (MOC)]]
