---
title: Gotcha - The Extraction Pipeline Had Never Been Run Twice
type: gotcha
tags: [gotcha, extraction, ingestion, idempotence, api, re-extraction, cache]
status: resolved
date: 2026-08-14
cache-version: n/a for `COMPARISON_CACHE_VERSION` — no comparison logic changed. But re-extraction
  **clears that drawing's cached comparisons** before queueing, which is not optional: a hit
  returns in ~0.14s and would serve findings computed against entities the run is about to
  replace.
related: [ADR-011 Vector as the Only Render Path, Gotcha - A Blurry CAD Canvas and Its Four Causes, Gotcha - The Cache Served Findings That Existed Nowhere, Gotcha - The Dimension Text Was Anchored to the Line It Had to Avoid]
---

# Gotcha — the extraction pipeline had never been run twice

**Class:** a function that was only ever correct once · **Found:** 2026-08-14, while adding the
re-extract route

---

## Why the route exists

`render_paths`, `render_text_point`, MTEXT rotation and the elliptical-arc fix are all computed at
**extraction** time. A drawing ingested before any of them renders wrong for as long as it lives,
and the only cure was **delete and re-upload** — which discards the drawing's id, and with it the
room slot, the audit history and every finding that referenced it.

This had been recorded as a standing prerequisite since ADR-011 ("re-ingestion is a prerequisite,
not a nicety") and it blocked **two separate fixes in a single session**. That is what made it
worth building rather than noting again.

## The defect the route exposed

`ExtractionPipeline.run` inserts a drawing's entities and **never deleted the previous ones**,
because it had only ever been reached once per drawing — immediately after upload, when there are
none.

```python
if bulk_entities:
    await ExtractedEntity.insert_many(bulk_entities)   # append, unconditionally
```

Run it a second time and every entity **doubles**. And a doubled payload is not an error: it
renders as a drawing (each line drawn twice, pixel-identical) and compares as a drawing (each
string matched against its own duplicate), so nothing anywhere reports a problem. The same family
as every other defect in this vault whose output is *plausible* rather than wrong.

This was already reachable before the route — a requeued or retried job would have done it — so
the route did not introduce the bug, it made it certain.

## Two orderings, both load-bearing

**The delete goes immediately before the insert, not at the top of `run`.** Everything above it can
fail: conversion, parsing, rendering. If the delete ran first, a corrupt file would leave the
drawing with *no* entities at all — a blank canvas, silently, from a failure the user never sees.
By the time the insert is reached the new entities are already built and only the write remains.

**The cache purge goes before the job is enqueued, not after it completes.** Cached comparisons
were computed against the entities about to be replaced; leaving them lets a hit bypass the entire
re-extraction in ~0.14s. Clearing first means there is no window in which a stale hit can be served
against new entities. See [[Gotcha - The Cache Served Findings That Existed Nowhere]] for what that
costs when it happens.

## `render_bounds` is the thing that could quietly break

Every zone template stores its geometry as **fractions of `render_bounds`**, and `zone_signature()`
derives a template's identity from it. Re-rendering the same file is deterministic, so a
re-extraction normally reproduces it exactly — but if the *renderer* changed between the original
extraction and the re-run, the bounds move and every stored fraction silently maps to the wrong
region. A mirrored-overlay class of defect: it looks plausible.

Nothing would have caught that, so the pipeline now compares the incoming `render_bounds` against
the stored one and, when they differ, logs a warning and records
`job.diagnostics["render_bounds_changed"]` with both values. It should never fire; it fires in
exactly the case nobody would think to check.

## The route

`POST /api/v1/drawings/{id}/reextract` → the queued `ExtractionJob`, polled on `GET /jobs/{id}`
like an upload.

- **404** unknown drawing.
- **409** an extraction is already `queued` or `processing` — two concurrent runs would race on
  one entity set.
- **422** the source file is missing from storage, so there is nothing to re-read. Failing here
  beats enqueueing a job that dies in the worker with a path error nobody reads, leaving the
  drawing at `queued` forever.

Logic lives in `DrawingIngestionService.reextract_drawing`, beside `purge_drawing`, so deletion and
re-extraction stay one source of truth each. It **reuses the upload pipeline verbatim** — a second
extraction path would drift, and the failure mode of drift here is a drawing that renders
differently depending on how it was ingested.

## Deliberately not done

- **The revision-chain block still runs on a re-extract**, exactly as on upload. `detect_revision`
  returns `None` on 14 of 14 corpus sides so it is dead in practice, but if it ever fires, a
  re-extraction would recompute `previous_revision_id` and could demote a different drawing's
  `is_latest_revision`. Special-casing it here would be an unreviewed behaviour change to a
  feature nobody has seen run — the same reasoning
  [[Gotcha - Nothing Checked That the Two Drawings Were the Same Drawing]] used to leave
  `part_number` dead rather than repair it as a side effect. Flagged, not fixed.
- **No UI.** The route is callable but nothing in the desktop app calls it, so bringing a stale
  drawing current is still a deliberate act by someone who knows to do it. The natural home is a
  badge driven by `extraction_schema_version`, which **nothing currently reads** — that field is
  written on every `DrawingDocument` and consulted by no one, so "which drawings are stale" is
  recorded but not surfaced.
