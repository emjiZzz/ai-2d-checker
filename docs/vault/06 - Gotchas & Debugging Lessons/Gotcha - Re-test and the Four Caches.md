---
title: Gotcha - Re-test and the Four Caches
type: gotcha
tags: [gotcha, cache, re-test, ocr, ingestion, comparison]
status: reference
date: 2026-07-30
---

# What "Re-test" actually refreshes — and the four caches behind a comparison

A physical comparison reads from **four** independent caches. "Re-test" refreshes only one of
them by default, which is the source of a recurring confusion (a stale OCR misread or an
un-re-ingested drawing surviving repeated Re-tests).

| Layer | Where | Keyed by | Refreshed by |
| :-- | :-- | :-- | :-- |
| **Comparison result** | `storage/cache/gemini_comparison_{version}_…json` | `COMPARISON_CACHE_VERSION` + drawing ids + file hashes | Re-test (`force_refresh`), **or** a cache-version bump |
| **Title-block OCR** | `storage/cache/title_block_ocr_v1_{id}_{hash}.json` | drawing id + file hash | **only** `refresh_ocr` (a paid Gemini call/drawing) |
| **Extracted entities** | MongoDB `extracted_entities` | drawing id | **only** re-uploading / re-ingesting the DXF |
| **Room's shown result** | `rooms.physical_comparison_results` | — | replaced by any run |

## Re-test = `force_refresh`, not "load previous"

The Re-test button (`TwoDLeftPanel.tsx`) does `resetComparison()` +
`runPhysicalComparisonAI(true)` → `force_refresh: true`. In `perform_drawing_comparison`:

```python
cached_payload = None if force_refresh else ComparisonCacheManager.get_cached_comparison(...)
```

So Re-test **bypasses the comparison cache and recomputes**. If the result looks identical, it
is because the inputs (entities) and the code did not change — it genuinely re-ran. The *normal*
path (opening a room, plain run) is what serves the cached result in ~0.14s.

Note `COMPARISON_CACHE_VERSION` embeds in the cache filename, so **bumping it auto-invalidates**
the comparison cache for a plain run too — the other way results refresh without Re-test. Bump it
on every logic change to spatial matching / zone extraction / title-block reading (see CLAUDE.md).

## The trap: Re-test does NOT re-run OCR or re-ingest

- **OCR** is read unconditionally by `get_cached_ocr` inside `generate_deterministic_candidates`.
  A Gemini misread (`ME17227N24` off a mislocated crop) therefore **survives every Re-test** —
  the crop is never re-sent. That is why the fix lived at the reasoning layer (reject ungrounded
  OCR; see [[Gotcha - Mislocated OCR Crop and Ungrounded Misreads]]), not in a Re-test.
- **Ingestion** is untouched: an ingestion-side fix (ellipse/Shift-JIS parsing) is invisible to
  Re-test because the `extracted_entities` in Mongo are unchanged. Those need the DXF re-uploaded.

## `refresh_ocr` — the deep Re-test

`PhysicalComparisonRequest.refresh_ocr` (the **ScanText** icon button next to Re-test) bypasses
the OCR cache: `ref_ocr = rev_ocr = None`, so the crop is re-sent to Gemini and the fresh reading
overwrites the stale one via `set_cached_ocr`. It **implies `force_refresh`** (a fresh OCR value
only reaches the output through a fresh comparison). Kept separate from Re-test on purpose — OCR
is a paid per-drawing call and must not fire on every recompute. Verified live: `refresh_ocr`
rewrites the OCR cache and logs a Gemini call; plain Re-test leaves it untouched (0 calls).

Still not covered by either button: **re-ingestion**. If you suspect the parsed entities are
stale, re-upload the DXF — there is no in-app "re-extract" path today.
