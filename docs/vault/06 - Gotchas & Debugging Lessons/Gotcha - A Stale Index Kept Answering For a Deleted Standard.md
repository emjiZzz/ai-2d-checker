---
tags: [gotcha, backend, retrieval, standards, index, metrics, startup, adr-008, adr-009]
status: fixed
cache-version: n/a — retrieval index; no comparison engine or zone-extraction behaviour
index-schema-version: bumped 1 → 2 (`store.INDEX_SCHEMA_VERSION`)
date: 2026-08-14
---

# Gotcha — A Stale Index Kept Answering For a Deleted Standard

> [!WARNING] The corpus census said 32 records. Sixteen of them belonged to a document that had
> been deleted, and the number was being quoted as evidence that retrieval was finally measurable.

## What was actually on disk

`tools/retrieval_eval.py census` reported `standards = 32 record(s)`. Mongo held **one**
`StandardDocument` (`KEMCO AND JIS STANDARDS`, ingested 2026-08-10) and **16** `StandardChunk`
rows. The other 16 records cited a `standard_id` with no document and no chunks behind it —
byte-identical texts, because both ingests were the same workbook.

So the index was serving the full text of a deleted standard: retrievable, scored, and **cited
back to a checker** as though it were current. In an inspection tool that is the failure ADR-008's
consequences section names — *"surfacing near-miss rules as authoritative is a recall attack"* —
except worse, because the rule was not near-miss, it was withdrawn.

## The first line of defence existed. The second did not.

This exact defect was found and fixed once already, at the delete endpoint:
[[Gotcha - A Tested Endpoint That Nothing Ever Called]]'s sibling,
`tests/test_standards_delete_reindex.py`, pins that `delete_standard` calls
`rebuild_standards_index`. That test still passes. It was never the gap.

The gap is what happens when that rebuild **doesn't take**. It is deliberately non-fatal —
Mongo is the source of truth, so a failed reindex must not fail the delete — and it logs and moves
on, on the stated assumption that *"startup or the next ingest"* repairs the index. Startup did
not:

```python
for collection, rebuild in builders.items():
    if store_for(collection, root).exists():        # <-- manifest.json and records.jsonl present
        continue                                    #     ...which is true of a stale index
```

`exists()` is a file-presence check. A stale index satisfies it perfectly. So
`INDEX_SCHEMA_VERSION` — the guard whose entire job is to stop an old index being misread — was
**inert**: `search()` dutifully returned `IndexStatus.STALE`, and no code path anywhere in the
system acted on that status. A version bump could detect a problem it could not fix.

**The rule: a status nothing acts on is a comment.** `MISSING` / `EMPTY` / `STALE` were introduced
by R0 precisely so an unusable index would be distinguishable from one that searched and found
nothing — and then the one caller that could have repaired it asked a different question.
`bootstrap_retrieval_indexes` now rebuilds anything not reporting `OK`.

## Why nobody noticed for four days

Because retrieval kept working. Every query returned ranked, plausible, well-cited hits — and half
the corpus was a ghost. Same family as the SHA-256 embeddings this whole track exists to correct:
**a stub raises; this returns answers.**

## The measurement consequence, which is the expensive half

`metrics.py` takes `corpus_size` from `manifest.n_records`, and the chance floor every verdict is
gated on is `k/N` over that count. Duplicated records inflate N without adding a single
distinguishable answer:

| | `chance recall@5` | vs `MAX_CHANCE_FLOOR = 0.25` |
| :--- | :--- | :--- |
| 32 records (16 texts, each twice) | 0.16 | **passes** |
| 16 distinct texts | 0.31 | **fails** |

A corpus too small to support a measurement was reporting itself as large enough to support one,
and the page being drafted to request annotation had already quoted the passing number. It fails
by a second route too: every relevant chunk had a twin, so an honest annotator ticks both,
`mean_relevant` goes to 2, and `chance_recall_at_k`'s `n_relevant` term lifts the floor to 0.29
even on the inflated count. Both arithmetics land on `NOT INFORMATIVE`.

`build_index` now collapses byte-identical texts and logs each drop with both citations. ⚠ **That
net would not have caught this** — `build_index` never received 32 records; the duplication
accumulated in a file nobody rebuilt. It is there for the case that genuinely reaches it, which is
`lessons`: two approved violations on different drawings routinely carry identical text and are
one answer to a query. Recorded explicitly because a net credited with catching a bug it cannot
catch is how the next person stops looking for the real cause.

## What this does not change

The corpus is still one workbook, and
[[Gotcha - A Standard That Ingested Nothing Reported Success]] already established the binding
constraint: **14 of its 18 sheets contain no text at all** — the standards are screenshots of
tables. Deduplication took `standards` from a false 32 to an honest 16. Reaching the 20 distinct
chunks the chance floor needs at k=5 is not "upload another standard"; it is either a standard
whose content is actually text, or the OCR decision that note flagged and left open.

## Verified

Census re-run against the live index: `standards` 32 → **16**, one `standard_id`, 16 distinct
texts, and a top-5 that returns 5 distinct texts where it previously returned 3 wearing 5 badges.
All three collections migrated v1 → v2 on the running backend's own startup, which is the
migration path working end to end rather than a claim about it.
`tests/test_retrieval_corpus_integrity.py` (8) pins both halves — the dedupe and, more importantly,
that a stale index is *rebuilt* rather than merely detected. Backend selection: 80 passed.

## See also

- [[Gotcha - A Standard That Ingested Nothing Reported Success]] — the same corpus, the constraint
  that outlives this fix
- [[Gotcha - A Count You Could Not Take Is Not Evidence]] — a census is evidence about the system
  before it is evidence about anything else; here the count was inflated rather than zero
- [[Gotcha - A Swallowed AttributeError Made a Write Path a Permanent No-Op]] — a guard that
  reported correctly into a void
- [[ADR-009 Retiring the Standards Knowledge Track]] — its reopening condition is what made anyone
  look at the census again
- [[Retrieval Annotation Guideline]] — the gates this count feeds
