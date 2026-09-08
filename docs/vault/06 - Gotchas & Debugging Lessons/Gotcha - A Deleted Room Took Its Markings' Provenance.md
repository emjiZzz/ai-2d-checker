---
tags: [gotcha, ground-truth, retrieval, data-loss]
date: 2026-09-08
---

# Gotcha - A Deleted Room Took Its Markings' Provenance

## What deleting a room actually does

`delete_room` soft-deletes the Room and **hard**-deletes everything the pair owned:

| Data | Fate |
| :--- | :--- |
| `Room` | Kept, `is_deleted: True` |
| `ground_truth_markings` | **Untouched — all survive** |
| `manual_check_sessions` | Untouched |
| Both `DrawingDocument` rows | Hard-deleted |
| `ExtractedEntity`, `ExtractionJob` | Hard-deleted |
| Source DXF, PNG, GLTF, comparison and OCR caches | Deleted from disk |

That split is deliberate and correct: the human judgement is the asset, and it outlives the
drawing. The defect was that it outlived its provenance too.

## The defect

`rebuild_ground_truth_index` built its sheet-name lookup from `DrawingDocument.find_all()` and
`ground_truth_record` resolved the name at index time. So a marking whose drawing had been purged
resolved to `sheet = ""`, and lost the sheet from **both** the indexed text and the citation.

Losing it from the text is the expensive half. `_collapse_duplicate_texts` keys on text alone, and
the sheet name is what distinguishes sibling sheets cut from one template — so sheet-less markings
collapse into each other and are dropped from the corpus.

The failure compounds: the markings most likely to lose their sheet are the ones whose room was
deleted, which is exactly the set no longer recoverable from anywhere else.

## Measured

On Atlas, 2026-09-08: 210 markings, 201 live, 2 soft-deleted rooms, and **9 markings pointing at
drawings that no longer existed** — 8 of them live, sitting in the index with no citable source.

Rebuilding the whole corpus with the drawing lookup emptied, which is what a full room cleanup
would produce:

| With all drawings deleted | Records | Distinct | Collapsed away | Uncitable |
| :--- | ---: | ---: | ---: | ---: |
| Resolving at index time | 201 | 119 | **82** | **201** |
| Reading the stored name | 201 | 177 | 24 | **0** |

41% of the corpus, and every citation.

## The rule

A corpus that is the source of truth must not depend on a row it does not own. Ground truth is
the durable artifact here; `DrawingDocument` is not, by design — deleting a room is a supported
action, not an accident.

Denormalising is usually the wrong instinct and is right here for one reason: the value is a
statement about **what the engineer saw at the time**, which a later lookup cannot reconstruct and
should not override. Same reasoning as `EntityAddress.source_file_hash`.

## What was changed

- `ManualCheckSession.ref_sheet` / `rev_sheet`, captured once when the pair is opened, and
  backfilled on resume for sessions that predate the field.
- `GroundTruthMarking.ref_sheet` / `rev_sheet`, copied from the already-loaded session, so a
  marking costs no extra read — the same pattern as `room_id`.
- `GroundTruthMarking.addressed_sheet()` returns the address and its sheet **together**, so the
  sheet cannot drift from the side the record indexes.
- `ground_truth_record` prefers the stored name and keeps the lookup as a fallback for old rows.
- `tools/backfill_marking_sheets.py`, report-only without `--apply`. A purged drawing's name is
  unrecoverable, so those rows get `deleted drawing <id>` rather than `""` — blank is the state
  that collapses, and the id at least keeps two deleted sheets distinct and says what happened.
  Run 2026-09-08: 201 filled from live drawings, 9 marked as deleted.
- `tests/test_ground_truth_sheet_provenance.py` (6), including the negative case that states what
  a blank sheet costs, so the field cannot be quietly removed.

## Related

- [[Gotcha - The Ground Truth Store the RAG Could Not Read]] — why this pool is separate
- [[ADR-014 The Ground Truth Verification Pass]]
- [[Gotcha - A Union Sync Means No Deletion Is Durable]] — the other half of deletion in this repo
