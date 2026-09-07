---
title: Gotcha - Optional Zones and the Shim Table
type: gotcha
tags: [gotcha, zone-detection, shim-table, optional-zone, safe-zone]
status: resolved
date: 2026-07-30
---

# Shim Table (シム表) — an optional SAFE zone, and the optional-zone pattern

The shim table (`No. | t | 材質 | 一組分個数`, plus 設計組厚サ / 総厚サ) is a small
assembly-thickness table that sits **inside the drawing area on some sheets and not others**.
Its rows used to fall into `drawing_views` and be reported as if they were drawing dimensions.

**Domain rule (confirmed with the customer):** the shim table is *reference data*, like the
tolerance block — it does **not** change meaningfully between revisions, so it must be
**excluded from comparison, never diffed.** The full-AI path already encoded this
(`result_parser._is_shim_table_item` drops シム表 items "as out of scope"); the rag path now
matches it by zone.

So `shim` is a **safe zone, exactly like `tolerance`**: detected, alignable in the editor,
and subtracted from the `drawing_views` pool — but it has no comparison category, no findings,
and no results section.

> An earlier iteration (cache v20–v24) made shim a *compared* category (`shim_table` with its
> own diff, findings, taxonomy, response field, and UI section). That was wrong — reverted in
> **v25**. If you find a stray `shim_table` reference, it is a leftover from that iteration.

## The load-bearing pattern: optional means NO percentage fallback

This part is the reusable lesson and is unchanged. `table_extractor.default_pct` seeds a
percentage-grid box for every zone it lists, and content detection only *overrides* it. A zone
in `default_pct` therefore gets a **phantom box on every sheet**, present or not — which is why
`iso` (in `default_pct`) carves out a box even where there is no isometric view.

`shim` is deliberately **left out of `default_pct`**. It is detected only by its own text
anchor (`シム表`), so a sheet without one simply has `regions.get("shim") is None`, which flows
through as "no shim zone" everywhere.

**To add another sometimes-present zone, follow shim, not iso: anchor it in `ZONE_ANCHORS`, cap
it in `ZONE_MAX_LIMITS`, add it to `VIEWS_EXCLUDED_ZONES` and `safe_zones`, and do NOT add it to
`default_pct`.** For a SAFE zone (like shim/tolerance) stop there — do not give it a comparison
category or a diff pool.

## Anchor matches on an NFKC substring

`_find_anchor_positions` compares `_norm(anchor) in _norm(text)` (NFKC + lowercase +
whitespace-collapse), so the single anchor `シム表` also catches the revision's decorated
`Ｌ　シム表　ｌ`. No need to enumerate the decorated forms.

## What is wired (safe-zone, not compared)

- `zone_detector.py` — `ZONE_ANCHORS`/`ZONE_MAX_LIMITS`/cluster radius, `VIEWS_EXCLUDED_ZONES`,
  and `safe_zones` (now `("tolerance", "shim")`).
- `orchestrator.safe_filter` — `shim_bbox` excludes shim rows from `drawing_views`. No shim
  diff, no `shim_table` markings/summary/response.
- Editor keeps shim: `ZONE_KEYS`, colours, labels, the zones endpoint field, and the
  click-to-place default box (`selectZone`) — so a user can align it and save it to the
  template even though it is never compared.

Verified live (v25): `shim_table` findings = 0, response has no `shim_table`, shim zone still
detected, and no shim materials (`SPCC`/`C2801P`/シム) leak into `drawing_views`.

## Guarded by

`tests/test_zone_overlay_endpoint.py` (shim zone maps when present; optional otherwise) and
`tests/test_taxonomy_consistency.py` (backend/frontend taxonomies stay in step — both now
without `shim_table`). Cache **v24→v25**.
