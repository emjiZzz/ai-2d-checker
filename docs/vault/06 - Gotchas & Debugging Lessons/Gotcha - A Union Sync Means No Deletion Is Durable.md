---
tags: [gotcha, database, sync, extraction, data-integrity]
date: 2026-08-18
status: open
---

# Gotcha — A Union Sync Means No Deletion Is Durable

Re-extracting a drawing does not replace its entities. It **adds a complete second copy**. Doing it
twice adds a third. `M745204N01` was measured at 402 → 804 → 1206 rows over two re-extractions,
and its revision at 594 → 1188 → 1782.

## Cause

`infrastructure/database/sync_manager.py` runs a bidirectional auto-sync, started at app startup
(`main.py:122`), enabled by default (`ENABLE_DB_AUTO_SYNC`), every `DB_AUTO_SYNC_INTERVAL_SEC`
(60). `SYNC_COLLECTIONS` includes **`extracted_entities`**, plus `drawing_documents`, `rooms`,
`annotations`, `audit_violations` and eight more.

Its merge is a union by `_id`:

> local docs not in cloud → push · cloud docs not in local → pull

**The file contains zero occurrences of the string `delete`.** There are no tombstones and no
deletion log. A document deleted on one store is indistinguishable from a document the other store
has and this one has not yet received — so the next sync **re-creates it**.

`ExtractionPipeline.run` does delete correctly, exactly as its own comment claims. The sequence:

| step | store A | after the next sync |
| :--- | ---: | ---: |
| upload, job `a1` | 402 | 402 |
| re-extract — deletes 402, inserts 402 (`f3f`) | 402 | **804** — `a1` pulled back from B |
| re-extract — deletes 804, inserts 402 (`b208`) | 402 | **1206** — `a1` + `f3f` pulled back |
| manual delete on the cloud store | 402 | **1206** — all three pulled back from local |

## The blast radius is not re-extraction

Any deletion, anywhere, in any of the 13 synced collections, is reverted while both stores are
reachable. That includes `DrawingIngestionService.purge_drawing`, which hard-deletes a drawing and
"every artifact it owns". A user deleting a drawing sees it vanish and reappear within a minute,
or worse, sees the drawing document deleted while its entities return — a half-deleted record no
code expects.

⚠ **The doubling does not announce itself.** A drawing with two copies of every entity renders
identically (each entity painted twice, in place) and compares plausibly. The visible symptom in
the manual-check overlay was a value match reporting `x3` — three identical boxes stacked at the
same coordinates, which reads as a matching bug rather than a data one.

## How it was found, and the reasoning error worth keeping

Two readings during a cleanup disagreed: 402 immediately after a re-extraction, then 804 later. I
recorded that as a racing read and moved on. **It was not a race — 804 was the true intermediate
state**, and it is exactly what a union sync predicts. The inconsistent measurement was the whole
signal, and explaining it away as measurement error cost two further re-extractions before the
cause was found.

The same instinct produced a second wrong conclusion: that the pipeline's `Replace, never append`
delete "evidently did not run". It ran every time. Nothing about the pipeline was ever broken.

**When two measurements of the same quantity disagree, that disagreement is the finding.**

## Cleaning up safely

Deleting on one store is pointless. The sync must not be running:

1. Stop the backend (or restart with `ENABLE_DB_AUTO_SYNC=false`).
2. Delete on **both** stores — `MONGO_URI` and `MONGO_FALLBACK_URI` — keeping the newest `job_id`
   per `drawing_id`. `extracted_entities` rows carry the `job_id` that wrote them, which is what
   makes the copies separable at all.
3. Restart, then verify the counts survive a full sync interval. They hold once both stores agree,
   because a union of two identical sets is stable.

## Not fixed

This note is `status: open`. Making deletion durable needs a real decision — soft-delete with
tombstones, a deletion log the sync replays, one-way sync, or dropping `extracted_entities` from
`SYNC_COLLECTIONS` (it is derived data, reproducible by re-extraction, and by far the largest
collection being copied). Until then:

- **Do not re-extract a drawing without checking its entity count afterwards.**
- `EXTRACTION_SCHEMA_VERSION` migrations across the corpus will multiply it, not migrate it.
- Nothing detects the condition. A `drawing_id` with more than one `job_id` in
  `extracted_entities` is the check, and no code performs it.

Related: [[Gotcha - An Angular Dimension Stored Its Measurement in Radians]],
[[Gotcha - A Cross-Sheet Hint That Cancelled Itself Out]]
