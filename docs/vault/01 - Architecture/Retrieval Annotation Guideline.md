---
title: Retrieval Annotation Guideline
type: architecture
tags: [evaluation, ground-truth, annotation, retrieval, second-brain, rag]
status: dormant — the track was retired 2026-08-10; this defines the condition for reopening it
guideline_version: 2026-08-07
date: 2026-08-07
verified-against: schema enforced by `infrastructure/retrieval/labels.py`; 0 human labels, corpus census 2026-08-14 standards=16 / domain_rules=6 / lessons=3 (standards read 32 until the stale-index repair — see [[Gotcha - A Stale Index Kept Answering For a Deleted Standard]])
related: [ADR-009 Retiring the Standards Knowledge Track, Standards Knowledge — Staged Plan, Eval Corpus Annotation Guideline]
---

# 🔎 Retrieval Annotation Guideline

Part of Stage R2 in [[Standards Knowledge — Staged Plan]]. Decisions:
[[ADR-008 The Second Brain — Retrieval-Only Local Knowledge]].
Sibling: [[Eval Corpus Annotation Guideline]], which governs the *comparison* corpus.

> [!NOTE] **Dormant, and deliberately not retired** — [[ADR-009 Retiring the Standards Knowledge Track]], 2026-08-10
> The standards knowledge track stopped at R2 because the corpus was empty. This guideline is kept
> because it *is* half the reopening condition: the track reopens when `standard_chunks > 0`
> **and** ≥30 labels at `provenance: human` clear the four gates defined below. **Do not weaken a
> gate to make the track restartable** — the gates are what stop a meaningless number being
> produced, and producing one is the failure the whole track existed to correct. The schema in
> `infrastructure/retrieval/labels.py` and the tooling in `tools/retrieval_eval.py` both stay in
> the tree and stay tested.
>
> > [!TIP] **Amended 2026-08-14 — the first clause is now satisfied, so read the second carefully.**
> > `standard_chunks` = 16. The blanket *"no labelling is scheduled and none should be started
> > today"* that stood here is withdrawn, because it was reasoning from a corpus of zero.
> >
> > What replaces it is narrower and is **not** permission to start labelling:
> > - **Collecting real queries is unblocked and useful now.** Queries are the input no tooling can
> >   synthesise, they take the longest to gather, and nothing about them expires.
> > - **Transcribing relevance labels is not yet worth doing**, for a mechanical reason rather than
> >   a scheduling one: labels record the index's `source_digest` and `assert_matches_index` refuses
> >   to score across a mismatch. Any upload that grows the corpus past the chance floor **rebuilds
> >   the index and invalidates every label already written**. Queries survive that; judgements do
> >   not. Label after the corpus settles, not before.
> >
> > This is the sequencing the ledger's critical path assumes too: the comparison corpus
> > (`M7452A0N01`, 0 of 8) is what moves a rung. This track is parallel and does not.

> [!WARNING] **Read the census before labelling anything — and read it as a count of *distinct*
> answers.**
> ```bash
> python tools/retrieval_eval.py census
> ```
> **2026-08-14: `standards` = 16**, from one workbook. It is no longer zero, which is what changed;
> it is also not yet enough. At k=5 the chance floor gate (`≤ 0.25`) needs **20 distinct chunks**,
> so `standard_chunks > 0` is necessary and not sufficient — see *How many* and *the chance floor*
> below.
>
> ⚠ This line read **32** for four days. Half the index was a *deleted* standard's chunks, and the
> duplication halved the reported chance floor from a failing 0.31 to a passing 0.16 — a corpus
> reporting itself as measurable because it was double-counting a document that no longer existed.
> [[Gotcha - A Stale Index Kept Answering For a Deleted Standard]]. **A census figure is a claim
> about the index, not about the source, until the two have been reconciled.**
>
> The 16 that remain are the four text-bearing sheets of an 18-sheet workbook; the other 14 are
> pasted images and contribute nothing
> ([[Gotcha - A Standard That Ingested Nothing Reported Success]]). Labelling against this corpus
> today would produce mostly `unanswerable` entries — which is a real coverage finding and worth
> having, but is not a retrieval measurement. See the R2 finding in [[00 - AI Maturity Status]].

---

## What a label is

One `(query → relevant chunk ids)` pair, judged by a person.

```json
{
  "query_id": "q07",
  "query": "板厚 12 の溶接記号は指定が要るか",
  "relevant_ids": ["a1b2c3d4e5f6a7b8"],
  "provenance": "human",
  "note": "checker asked this during the M7452 review"
}
```

## The relevance test

> **Would a checker auditing a drawing that raised this query want this clause put in front of
> them?**

Judge each `(query, chunk)` pair **on its own**. Not "is this the best chunk" — several may be
relevant, and `relevant_ids` takes a list. Not "is this chunk about the same topic" — a clause
about welding is not relevant to a welding query if it answers a different question.

Mark relevant when the chunk **would change or support what the checker does next**. Mark it not
relevant when reading it would be a waste of the checker's attention, even if the words overlap.

## Where queries come from

**From real audit situations. Never from the corpus text.**

This is the rule most likely to be broken by accident, and breaking it invalidates the whole
measurement. A query written while looking at a chunk is a paraphrase of that chunk, and
retrieving it proves only that TF-IDF can find text it was given a copy of. The resulting
`recall@5` will be near 1.00 and will mean nothing.

Good sources:
- Questions a checker actually asked during a review.
- The layer names, entity types and file-name fragments the audit pipeline itself builds queries
  from (`audit_orchestrator._retrieve_lessons_learned`) — these are the *real* production queries.
- A finding that was raised, phrased as the question it should have been checked against.

Write the query **first**, then look at what comes back.

## Provenance is mandatory

`human` or `synthetic`. Enforced by `labels.py`; there is no default.

`synthetic` labels are generated from the corpus (typically a chunk's own heading as the query).
They are a **smoke test** — they catch a totally broken index — and are excluded from scoring
unless `--include-synthetic` is passed. A run including them can never be reported as
informative and **may not be written as a baseline**; the tool refuses.

This mirrors [[ADR-007 Re-scoping the Maturity Ladder]]'s exclusion of mutation pairs from
rung-1 evidence on the comparison track, for the same reason: a label derived from the thing
being measured is circular.

## Unanswerable queries are a result, not a gap

If nothing in the corpus answers a query, record it under `unanswerable` rather than inventing a
best-effort match or leaving a label with an empty `relevant_ids` (the loader rejects those).

A long `unanswerable` list is a **coverage finding**: the corpus does not contain what checkers
need. No recall number will ever surface that, because recall is only computed over queries that
have an answer. This is the most likely real outcome on this system today.

## How many, and why the number is a gate

**~30 human labels per collection.** Below `MIN_QUERIES_FOR_VERDICT = 30`, the tooling renders
**no verdict at all** — not a low score, no verdict. With 6 labels, one query moves `recall@5` by
0.17, which is larger than the 0.15 lift margin the verdict tests against; the metric would be
noisier than the effect it is measuring.

## Read the chance floor, always

Every report prints `chance` beside every rate. A shuffling ranker scores roughly `k/N`.

| Corpus | `chance recall@5` | What `recall@5 = 1.00` means |
| :--- | :--- | :--- |
| 6 docs | 0.83 | almost nothing — you retrieved 5 of 6 documents |
| **16 docs** | **0.31** | **`standards` today — still above the gate, so still no verdict** |
| 20 docs | 0.25 | the floor the tooling requires before it will render a verdict |
| 500 docs | 0.01 | a real result |

⚠ **Count distinct texts, not records.** The floor is computed from `manifest.n_records`, and an
index holding the same text twice inflates that count without adding an answer — which *lowers*
the reported floor and can carry a corpus through this gate that should not pass it. `build_index`
now collapses byte-identical texts for exactly this reason. See
[[Gotcha - A Stale Index Kept Answering For a Deleted Standard]].

A verdict is only rendered when the chance floor is **≤ 0.25**, the sample is **≥ 30**, the lift
over chance is **≥ 0.15**, and no synthetic labels were scored. All four, or the report says
`NOT INFORMATIVE` and names the gates that failed.

## Drift

Labels record the `source_digest` of the index they were authored against. Rebuild the index from
changed sources and chunk ids can move — at which point every label points at the wrong text and
scores as a miss, which presents as *"the encoder got worse"*. The loader refuses to score on a
digest mismatch. Re-label, or rebuild from the original sources.

Labels also record `guideline_version`. If this document's definition of relevance changes, bump
the frontmatter **and** `labels.GUIDELINE_VERSION`, then re-label or discard. Do not mix.

## Workflow

```bash
python tools/retrieval_eval.py census
python tools/retrieval_eval.py worksheet --collection standards --queries "first real query; second"
# fill in the markdown, then transcribe to tests/fixtures/retrieval/labels-standards.json
python tools/retrieval_eval.py score --collection standards
python tools/retrieval_eval.py score --collection standards --baseline
```

The worksheet retrieves candidates and leaves every relevance box **unticked**. It deliberately
does not guess: a label the tool wrote is not evidence about whether retrieval helps a person.
