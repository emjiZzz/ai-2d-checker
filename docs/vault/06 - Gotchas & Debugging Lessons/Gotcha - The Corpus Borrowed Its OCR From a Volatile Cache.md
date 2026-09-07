---
tags: [gotcha, evaluation, corpus, ocr, reproducibility, measurement]
status: fixed
cache-version: n/a — corpus infrastructure, not engine behaviour
date: 2026-08-05
verified-against: every OCR cache entry deleted; score byte-identical after the fix
---

# Gotcha — The Corpus Borrowed Its OCR From a Volatile Cache

> [!WARNING] Deleting old comparisons in the app changed what an eval score *meant*, without
> changing a single byte of the corpus and without any error.

## What happened

Stage 0b pinned the entity payloads with sha256 precisely so a fixture could not drift
underneath a measurement. It did not pin the **title-block OCR reading**, which lived only in
`storage/cache/title_block_ocr_v1_{drawing_id}_{file_hash}.json` — outside the corpus, keyed
on an ingestion that a user can delete.

A routine cleanup (delete old comparisons, re-ingest a drawing) removed all six readings the
corpus depended on. Nothing failed:

- payload sha256 all still verified — the corpus data was intact;
- `tools/eval.py` still printed precision 0.85 / recall 0.68 / F1 0.76, **identical to the
  published baseline**;
- the no-network guard never fired.

All three of those are misleading. What actually happened: the renderings for the deleted
drawing ids were gone too, so `crop_title_block_image` returned `None`, so no Gemini call was
attempted — which is why the guard stayed quiet. The **reference** side therefore fell back to
spatial title extraction while the **revision** side still had a derived OCR entry. The two
sides were being compared under different title-extraction regimes. The numbers matched by
coincidence, because the spatial reading happened to agree on those fields.

## Why this is the dangerous shape

A measurement that breaks loudly is a nuisance. This one:

1. produced the *same* number, so nothing prompted a second look;
2. depended on state the corpus did not declare, so `verify` reported everything fine;
3. degraded **asymmetrically** — one side of a comparison, which is the worst case, because a
   differ's whole job is comparing two sides under identical rules.

## The fix: the corpus owns the reading

Each side's reading is now captured into the pair payload as `{side}.ocr.json` and hashed into
the manifest as `ocr_sha256`. `CorpusPair.restore_ocr_cache()` writes any missing entry back
into the cache before a run, and `runner.run_corpus` calls it for every pair before the
no-network guard goes up.

Restoring rather than injecting because `generate_deterministic_candidates` reads the cache
internally and offers no seam to pass a reading through. Idempotent, and it only ever writes
back exactly what the corpus captured.

**Verified the way it should be:** every OCR cache entry was deleted — the same action that
caused the problem — and the score came back byte-identical. Before the fix that action
silently changed the comparison regime; after it, it changes nothing.

`missing_ocr_cache()` now asks *"would this run differently?"* rather than *"is the cache
warm?"*, and `uncaptured_ocr_sides()` reports any pair still borrowing from the cache.
`test_committed_corpus_has_every_ocr_reading_captured` guards the real corpus, not a fixture.

## The recovery rule worth remembering

**The OCR reading is a function of the drawing file, not of the ingestion.** Re-uploading the
same DXF mints a new `drawing_id` and therefore a new cache key, so an exact-key lookup misses
a reading that is provably for the same bytes. `_find_ocr_reading` falls back to matching on
`file_hash` alone, which is what made one of the three lost pairs recoverable after its
re-ingest. The other two were unrecoverable — their source DXFs were gone from
`storage/uploads/` as well — and the corpus was rebuilt around the survivor.

## The transferable lesson

**Pin everything a measurement depends on, not just the part that looks like data.** The
entity payloads were obviously the fixture, so they got hashed. The OCR reading looked like a
cache — an optimisation, something regenerable — so it did not. It was neither: it was an
input, and a paid, non-reproducible one. Ask of every cache a measurement touches: *if this
were empty, would the number change?* If yes, it is not a cache, it is corpus.

## See also

- [[Gotcha - Zone Templates Vanish in Offline Eval]] — the same shape, still open: hand-aligned
  zone boxes an offline run cannot resolve
- [[Gotcha - The Scorer Is a Differ Too]] — measurement code needs the same scepticism as the
  code it measures
- [[Gotcha - Re-test and the Four Caches]] — the wider cache landscape this sits in
- [[00 - AI Maturity Status]] — the baseline these numbers go into
