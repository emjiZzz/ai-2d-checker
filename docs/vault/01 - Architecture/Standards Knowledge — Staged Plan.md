---
title: Standards Knowledge — Staged Plan
type: architecture
tags: [roadmap, architecture, rag, retrieval, knowledge, second-brain, evaluation]
status: closed — R0–R2 landed, R3–R4 retired 2026-08-10
date: 2026-08-07
closed: 2026-08-10 (ADR-009; the corpus is empty and the track stops at R2)
verified-against: cache v43, baseline-v43.json, working tree at 2026-08-10
related: [ADR-008 The Second Brain — Retrieval-Only Local Knowledge, ADR-009 Retiring the Standards Knowledge Track, Standards Knowledge — Rule Bundle Format, RAG Reference Architecture — Gap Analysis]
---

# 🧠 Standards Knowledge — Staged Plan

Decisions: [[ADR-008 The Second Brain — Retrieval-Only Local Knowledge]] ·
Closed by: [[ADR-009 Retiring the Standards Knowledge Track]] ·
Contract: [[Standards Knowledge — Rule Bundle Format]] ·
Why: [[RAG Reference Architecture — Gap Analysis]]

> [!WARNING] **This plan is closed. Do not start R3.** — 2026-08-10, [[ADR-009 Retiring the Standards Knowledge Track]]
> R0, R1 and R2 landed on 2026-08-07. R2's census found the corpus **empty** — `standard_chunks`
> **0**, no standard ever uploaded, and all 1,322 audit violations unreviewed — so R3 and R4 would
> be distribution machinery for a payload that does not exist. **The owner's decision, taken
> 2026-08-10, is that the standards-audit pipeline is not the product.** R3 and R4 are **retired,
> not deferred**: nothing is waiting for a trigger.
>
> R0–R2 stay landed and their code stays in the tree — see ADR-009 on why deleting
> `infrastructure/retrieval/` would destroy the evidence for the negative result. **R3's one live
> defect fix (`AutoDocEngine`'s missing `client_name` filter) is re-homed** to
> [[00 - AI Maturity Status]]; it is a comparison-engine defect and does not retire with this plan.
>
> The reopening condition is stated concretely in ADR-009: `standard_chunks > 0` **and** ≥30
> human-labelled queries clearing the four gates.

> [!IMPORTANT] This plan governs the **standards-audit** pipeline, not the drawing comparison.
> [[00 - AI Maturity Status]] governs the comparison engine and is untouched by this work.
> The two are **parallel tracks**: labelling remains the comparison engine's critical path.
> **Cross-cutting invariant:** the eval corpus must score **P 0.98 / R 0.87 / F1 0.92** against
> `baseline-v43.json` at every stage. Movement means something leaked across the boundary.

---

## 🎯 The shape

```
R0 Delete the fakes  →  R1 Lexical retrieval  →  R2 The metric  ┃  R3 Two-tier bundles
        ✅                      ✅                  ⚠️ census    ┃        ⛔ RETIRED
                                                     only       ┃            │
                                                                ┃  ┌─────────┘
                                            the track stops ────┫  ▼
                                                       here     ┃  R4 Knowledge sync ⛔ RETIRED
```

**R0–R3 ship value with no server, no cloud, and no network.** R4 is the only stage where the
hosting question matters, and it is production work. That ordering is deliberate: if R4 is never
built, R0–R3 still leave the product better than it is today.

> **That ordering paid off, in the direction nobody plans for.** R4 was never built and now never
> will be, and R0–R2 still left the product better: nine fake modules gone, a real retrieval
> component in their place, and a census that answered the question the whole track was asking.
> Sequencing the cheap honest stages first is what made stopping cost nothing.

---

## Why this plan starts by deleting things

The standards-audit pipeline is already shaped like a RAG diagram and already runs in production.
What it lacks is not structure — it is **anything real underneath the structure**:

| Component | State |
| :--- | :--- |
| Embeddings | `np.random.default_rng(sha256(text))`. Docstrings claim *"HuggingFace/SentenceTransformers"*, *"ONNX Runtime"*; `_load_model` assigns the **string** `"ONNX_Quantized_MiniLM"`. |
| Vector store | `index_shards.json` + a numpy loop. **No such file exists on disk.** |
| SimSearch | Cosine over the above. Runs. Returns ranked, scored results. |
| Re-rank | Absent. |
| Retrieval metric | Absent. |

**The danger is not that it is broken — it is that it answers.** A stub raises. This returns
plausible vectors, and nothing downstream can tell. That is why R0 is deletion, not repair.

---

## Stage R0 — Delete the fakes ✅ **COMPLETE 2026-08-07**

*Half a day. No new dependencies.* — **Actual: half a day, no new dependencies.**

> [!SUCCESS] Landed. **Nine modules deleted, not two.** Eval byte-identical (P 0.98 / R 0.87 /
> F1 0.92), `pytest` 759 passed / 3 skipped, the 2 known `test_vision_ocr_grounding` failures
> unchanged. Guard: `tests/test_no_fake_ai_capability.py` (12 tests).
> Work log: [[00 - AI Maturity Status]], 2026-08-07 R0 entry.
> Defect note: [[Gotcha - A Swallowed AttributeError Made a Write Path a Permanent No-Op]].
>
> **What the plan got right.** The named risk was the real one: `lancedb_manager` had two live
> importers and both were rewired before deletion, so the standards upload flow never broke.
>
> **What the plan under-counted.** The audit list named three suspects; the disease was in
> **nine** modules. The whole `vectorstore/` package went (`embedding_provider`,
> `retrieval_engine`, `standards_indexer`, `vector_persistence` alongside `lancedb_manager`), plus
> both `geometry/` modules. Four `ai/` subpackages are now empty and removed.
>
> **What was kept, and why the criterion is "does it lie" not "is it used".**
> `knowledge_graph/graph_builder.py` — named in the plan as a suspect — is a **real** in-memory
> graph that consumes no embeddings. It has zero callers, and it stays: dead code is a separate
> cleanup from fake code. The four `explainability/` modules stay for the same reason.
> `rendering/comparison_engine.py` also stays — its comment *"in a real implementation we would do
> deep geometric equivalence"* is an honest self-limitation, and its docstring accurately says
> "simplistic coordinate hashing".
>
> **Worst offender, unlisted:** `reasoning/drawing_similarity_engine.py`.
> `calculate_drawing_distance` returned a hardcoded `0.85` and `find_systemic_drafting_errors`
> fabricated a finding with an invented `0.88` frequency. Its test asserted `dist == 0.85` — a
> test certifying a constant. Two other tests certified the same way (`onnx_available is True`).
>
> **A tenth fake, outside `infrastructure/ai/`, found by the guard test rather than by reading:**
> `ops/backup_manager.py`. `create_secure_backup` made an empty directory, logged *"System state
> successfully archived"* and returned a path to a `.zip` it never wrote; compression and
> AES-256-GCM encryption were a comment beginning `# In production:`. Zero production callers —
> its only test monkeypatched **both** methods and asserted on its own lambdas. Now raises
> `NotImplementedError`. A backup routine is the worst possible place for a stub that returns
> cleanly, because the failure is silent until a restore is attempted.
>
> **Carried into R1:** `tests/test_standards_loader_async.py` guarded `asyncio.to_thread`
> offloading of the vector indexer — i.e. it was protecting the event loop from a random number
> generator. Rewritten to guard the surviving CPU-bound offloads (`StandardsParser.parse_file`,
> `calculate_file_hash`), and **verified to fail** when `to_thread` is stubbed to run inline.
> **R1 must add a case for real indexing**, where the property finally matters.

**Delete outright:**

- `infrastructure/ai/embeddings/local_embedding_model.py` — the hash-as-embedding module above.
- `infrastructure/ai/vectorstore/lancedb_manager.py` — keep the **algorithm** (brute-force numpy
  cosine is exact and ~1 ms at this scale; adding LanceDB/FAISS is a recorded negative result),
  lose the misleading name and the JSON persistence.

**Audit for the same disease** — all three have **zero live callers**, so if they consume the fake
embeddings they have been measuring noise: `ai/reasoning/drawing_similarity_engine.py`,
`ai/knowledge_graph/graph_builder.py`, `ai/geometry/vector_geometry_index.py`.

**Fix the confirmed bug.** `api/routers/audits.py:377` calls `provider.embed_text(...)`
(**singular**) against a provider defining only `embed_texts` (**plural**). It is an
`AttributeError` inside a `try` whose `except Exception` logs a warning and continues — so the
`lessons_learned` collection has **never been written**, since the code was authored. Note the
read path (`retrieval_engine.py:23`, `standards_indexer.py:37`, `standards.py:231`) uses the
plural form correctly: **retrieval queries an index one of its two writers can never populate.**

> **Exit:** no module in `infrastructure/ai/` claims a capability it does not have. A guard test
> asserts no embedding provider returns hash-derived vectors — the specific defect that survived
> in production for months.
>
> ✅ **Met.** `tests/test_no_fake_ai_capability.py`, four checks: no random stream seeded from a
> hash anywhere in the backend; no docstring naming an uninstalled dependency (none of
> `sentence_transformers`, `onnxruntime`, `lancedb`, `faiss`, `transformers` is installed — every
> such claim was fiction); the nine deleted paths stay deleted; and the surviving contents of
> `infrastructure/ai/` are pinned to an explicit reviewed list.

**A note on how that guard is written, because the obvious version does not work.** The first
attempt scanned source text for `default_rng` near `sha256` and failed immediately — on the
**tombstone comments left at each deletion site**, which quote the defect precisely so future
readers know what was removed. A guard that punishes documenting a defect is worse than no guard.
The working version is an AST pass: it discards comments and inspects executable code plus
docstrings only. That is the right line anyway — **a docstring is a module's claim about itself; a
comment recording why something was removed is history.**

### Risk

Deleting a module with zero callers is safe; deleting one with *two* callers
(`lancedb_manager`) is not. `audits.py` and `standards.py` both import it. Replace before delete,
or the standards upload flow breaks.

*Outcome: this was the correct risk to name.* Both callers were rewired first — the
`lessons_learned` write in `audits.py` and the zero-caller `POST /admin/standards/reindex` in
`standards.py` — along with two more the plan had not listed: the vector query in
`audit_orchestrator.py` (its pre-existing MongoDB regex fallback is now the only path, which is
why retrieval output did not change) and the indexing call in `standards_loader.py` (chunks still
persist to Mongo, so R1 has its corpus). Standards upload was verified working by test.

---

## Stage R1 — Lexical retrieval that works ✅ **COMPLETE 2026-08-07**

*~1 week. **Zero new dependencies** — sklearn 1.9.0, numpy 2.4.6, scipy 1.18.0 are all present.*
— **Actual: one session. Zero new dependencies, as predicted; all three versions confirmed present.**

> [!SUCCESS] Landed. `infrastructure/retrieval/` — `encoder.py`, `lexical.py`, `store.py`,
> `index_builder.py`, `service.py`, `__init__.py`. Eval byte-identical to `baseline-v43`
> (P 0.98 / R 0.87 / F1 0.92). `pytest` **793 passed / 3 skipped**, the 2 known
> `test_vision_ocr_grounding` failures unchanged. 34 new tests across
> `test_retrieval_lexical.py` (27) and `test_lessons_index_write_path.py` (7).
>
> **Exit criterion met and tested as written.** `retrieval.query()` returns ranked chunks with
> scores and citations, offline, in **6–9 ms** against the 100 ms budget, under `no_network()` —
> the same socket guard `infrastructure/eval/runner.py` uses, reused rather than reimplemented
> so "offline" has one definition in this repo.
>
> **Char n-grams justified themselves immediately.** `ユニット No` (spaced) retrieves the indexed
> `ユニットNo.` (unspaced, trailing period) at 0.351 and ranks it first. A word tokeniser scores
> that pair at zero. Pinned by test.
>
> **Deviation, recorded not quiet: sparse `.npz`, where this plan said `.npy`.** Char n-gram
> TF-IDF is inherently sparse — at 2**16 features a dense float32 row costs 256 KB *per chunk*
> and is ~99.9% zeros. Same exact brute-force cosine, same results, correct container. The
> "numpy brute force" intent is unchanged; only the serialisation format differs.
>
> **`domain_rules` sources markdown, not the bundle**, because the bundle is an R3 deliverable
> and does not exist yet. Rather than block, the source is a *function returning records*
> (`RecordSource`) instead of a path — which is the "bundle source abstraction rather than a
> path" seam R3 was going to build anyway. R3 swaps the source and touches nothing else.
>
> **Three collections are built; one is consumed. Deliberate.** The audit path queries
> `standards`. `domain_rules` and `lessons` are built, queryable and tested, but not yet blended
> into the audit context window — **how to merge three ranked lists into one prompt is a ranking
> question, and answering it without R2's metric would be exactly the untested tuning this plan
> sequences R2 ahead of.** Same reasoning as shipping `rrf` implemented-but-not-default.
>
> **Two defects found by building this, both recorded as gotchas:**
> [[Gotcha - A Guard Test's Failure Path Had Never Run]] — R0's capability guard crashed with
> `AttributeError` instead of reporting, the first time it caught anything, because
> `ast.Module` has no `lineno`. And
> [[Gotcha - Our Own Punctuation Broke on the cp932 Console]] — the citation separator was `·`,
> which cp932 cannot encode, so any log line carrying a citation would raise on a Japanese
> Windows install.
>
> **A third thing the guard caught, which is the guard working as designed:** the first draft put
> rejected-alternatives prose ("we did not use LanceDB/FAISS because…") in *docstrings*. R0's
> rule is that a docstring is a claim and a comment is history, so the guard flagged it. The
> prose moved to comments rather than the guard being weakened.

**Create `infrastructure/retrieval/`:**

| Module | Job | As built |
| :--- | :--- | :--- |
| `lexical.py` | `TfidfVectorizer(analyzer="char_wb", ngram_range=(2,4))` + BM25 | ✅ both, plus `reciprocal_rank_fusion`. **`tfidf` is the default and no blend ships** — fusing is an R2 question |
| `store.py` | numpy brute force over `.npy` + JSONL sidecar | ✅ exact brute-force cosine + JSONL sidecar + `manifest.json`. **Sparse `.npz`**, see above |
| `index_builder.py` | two collections — `standards` (from `StandardChunk`), `domain_rules` (from the bundle, chunked by heading) | ✅ **three** — `standards`, `domain_rules` (from vault markdown until R3), `lessons` (from confirmed violations) |
| `encoder.py` | pluggable interface; **lexical is the default** | ✅ `Encoder` protocol; `TfidfEncoder` the only implementation, and it **raises rather than returning a placeholder vector** |
| — | *(not in the original table)* | `service.py` — the async Mongo/vault edge, so `index_builder` stays synchronous and testable without a database |

**Why char n-grams and not words.** This is a Japanese CAD domain and Japanese does not
word-segment on whitespace, so a word-level tokenizer is close to useless on `素材調質施工` or
`ユニットNo.`. It also mirrors `learning/finding_classifier.py:28`'s
`HashingVectorizer(analyzer="char_wb", ngram_range=(2,4))` — **the one learned component in this
system that demonstrably works.** Reusing its shape means one definition of "similar text" across
retrieval and classification.

**Dense stays behind the interface** and must win on a measurement before it ships. If it ever
does, the path is ONNX Runtime (~80 MB, no torch); `sentence-transformers` is already rejected for
pulling ~2.5 GB into a Tauri sidecar.

**Retrieval returns cited chunks to a human.** No generation — therefore no hallucination surface,
no prompt to tune, no token cost, and no LLM dependency to justify in a security review.

### Inherited from R0 — do these here

- [x] **Re-offload indexing, and extend the guard.** *(2026-08-07)* `ingest_standard` rebuilds the
      `standards` index through `asyncio.to_thread`, and `tests/test_standards_loader_async.py`
      now records the OS thread for **three** steps — `calculate_file_hash`, `parse_file` and
      `build_index`. **Verified non-vacuous**: stubbing `asyncio.to_thread` to run inline makes it
      fail naming all three. Note the rebuild is whole-corpus, not incremental, because idf is a
      corpus-level property — appending would rank new and old chunks under different weights.
- [x] **Pin the write by reading it back.** *(2026-08-07)*
      `tests/test_lessons_index_write_path.py` (7 tests). Every one performs the write and then
      **queries the index for the record**; none assert "no exception was raised". Also pinned:
      rejected findings are not indexed (a false positive fed back teaches the opposite), and the
      index survives deletion because it is derived from the violations rather than written
      beside them.
- [x] **Narrow the exception guard.** *(2026-08-07)* `review_violation` catches
      `(OSError, ValueError, EncoderError)`. Enforced by an AST test that fails if the handler
      ever names `Exception` or `BaseException` — the property is about *which* types are caught,
      and there is no runtime behaviour to observe when the correct answer is "it propagates".
- [x] **Restore a reindex path deliberately.** *(2026-08-07)* Indexing triggers from the ingest
      path and from startup (`bootstrap_retrieval_indexes`, which builds only what is missing).
      **No admin endpoint was added** — the deleted one had zero callers, and adding an
      unreachable route back would repeat the mistake rather than fix it.

> **Exit:** `retrieval.query(text)` returns ranked chunks with scores and citations, offline, in
> <100 ms, with **zero sockets** — enforced by patching `socket.connect`, on the pattern already
> proven in `infrastructure/eval/runner.py`'s `no_network`.
>
> ✅ **Met, clause by clause.** Ranked chunks with `score` and `rank`
> (`test_query_returns_ranked_chunks_with_scores_and_citations`); citations via
> `Record.citation()` → `JIS B 0405 > TOLERANCES > p.12`; **6–9 ms** measured against the 100 ms
> budget (`test_query_is_under_the_hundred_millisecond_budget`); and offline under the reused
> `no_network()` guard (`test_query_is_offline`). `SLOW_QUERY_MS` logs a warning above the budget
> rather than failing, so corpus growth reports itself instead of silently degrading.

### Risk

**The index can be empty and the system will not say so.** `reindex_standards` exists but nothing
calls it automatically, and there is no staleness signal. An empty index returns zero results,
which is indistinguishable from "nothing relevant". Emit an explicit warning when a collection is
empty, rather than returning `[]` silently.

> ✅ **Addressed structurally, not just with a warning.** `query()` returns a `SearchOutcome`
> carrying an `IndexStatus`, so `MISSING` / `EMPTY` / `STALE` are **different values** from `OK`
> with no hits — a caller cannot conflate them by accident, and `outcome.answered` is the
> one-line check. Each non-OK status also logs a warning naming the collection and the reason.
>
> Three further consequences worth recording:
> - **`build_index` declines to write an empty index.** "Nothing to index" leaves the collection
>   `MISSING`, which is the honest label; writing an empty one would assert that a build ran and
>   found nothing, a stronger claim than the truth.
> - **Staleness is detected, not just emptiness.** The manifest records the encoder name and
>   schema version, and an index built by a different encoder is refused as `STALE` rather than
>   searched with incompatible vectors.
> - **The audit path falls back rather than going quiet.** If the index cannot answer,
>   `audit_orchestrator` drops to the old MongoDB substring match and says so in the log.
>   Retrieval gets worse; it does not silently vanish.

---

## Stage R2 — The retrieval metric, before any tuning ⚠️ **HARNESS COMPLETE, BLOCKED ON DATA — 2026-08-07**

*~3 days. No new dependencies.* — **Actual: one session, no new dependencies. The harness is
done. The measurement is not, and cannot be, for a reason that is the stage's real output.**

> [!WARNING] **The finding: there is nothing to retrieve.**
>
> The corpus census, run against the live database for the first time:
>
> | Collection | Records | Why |
> | :--- | ---: | :--- |
> | `standards` | **0** | `standard_documents` = 0, `standard_chunks` = 0. **No standard has ever been uploaded to this system.** |
> | `lessons` | **0** | 1,322 audit violations exist and **every one is unreviewed** — 0 approved, 0 rejected. |
> | `domain_rules` | 6 | The two client rule notes in the gitignored vault folder. Client-local. |
>
> This is a live, working database — 1,322 violations, 8,055 extracted entities, 108 rooms, 58
> audit sessions. The standards subsystem has simply never been used.
>
> **The plan predicted this and said what to do about it.** The Risk section below reads *"the
> likely result is that retrieval is not the bottleneck… record it as a negative result and stop,
> rather than reaching for dense embeddings to rescue the number."* That is what happened, and the
> answer is stronger than predicted: it is not that retrieval is a weak lever, it is that **the
> lever is not connected to anything.**
>
> **A corollary that sharpens the R0 finding.**
> [[Gotcha - A Swallowed AttributeError Made a Write Path a Permanent No-Op]]
> records that `lessons_learned` was never written because of a swallowed
> `AttributeError`. True — and the census adds that **the review endpoint has never been called at
> all.** 1,322 violations, zero reviewed. Even a correct write path would have written nothing.
> The bug was real and was also, independently, moot.

> [!SUCCESS] **What did land.** `metrics.py`, `labels.py`, `evaluate.py`,
> `tools/retrieval_eval.py`, [[Retrieval Annotation Guideline]], and a committed census baseline
> at `tests/fixtures/retrieval/retrieval-baseline.json` recording `status: "no-measurement"` and
> exactly why. 21 tests. The harness is proven end-to-end against the 6-record `domain_rules`
> corpus — and **correctly refuses to report that run as evidence.**
>
> **The most important behaviour in the stage, demonstrated:** the smoke run scores
> `recall@5 = 1.00 (6/6)` — a perfect score — and prints
> `VERDICT: NOT INFORMATIVE`, naming three failed gates: labels are synthetic, 6 queries < 30,
> and a corpus of 6 at k=5 where a shuffling ranker already scores **0.83**.
>
> **Two design defects were found by running the harness rather than by reading it**, both now
> pinned by test:
> - The first run printed `VERDICT: the measurement distinguishes this encoder from chance`
>   directly above a caveat saying the labels were synthetic. `informative` did not consider
>   provenance. A verdict line contradicting the caveat beneath it is precisely how a meaningless
>   number gets quoted on its own.
> - The corpus-size gate was `corpus_size > k`, which a 6-document corpus passes at k=5. Replaced
>   with a **chance-floor** gate (`chance_recall@k ≤ 0.25`, roughly `N ≥ 4k`), because retrieving
>   five documents out of six is not retrieval however good the number looks.
>
> **Not done, and not doable here: the ~30 hand-labelled pairs.** Labelling which clause is
> relevant to which query is human judgement over a corpus that does not yet exist. Generating
> them would have produced a confident `recall@5` measuring whether TF-IDF can find text copied
> out of the corpus — the retrieval-shaped version of the mutation-pair limit ADR-007 already
> ruled inadmissible. `provenance` is a required field precisely so that this cannot happen by
> accident, and the tool **refuses** to write a baseline from a run containing synthetic labels.

**Deliberately sequenced ahead of everything downstream**, and this is the stage most likely to be
skipped under pressure. It should not be. [[ADR-007 Re-scoping the Maturity Ladder]] made
measurement rung 1 for exactly this reason, and the standards pipeline is the proof of what
happens without it: **SHA-256 embeddings survived in production because no number would have
moved if they were replaced by a real model.**

- [ ] **~30 hand-labelled `(query → relevant chunk)` pairs.** Small, and every conclusion inherits
  that — say so in the output, not in a comment.
  → **Blocked, and blocked upstream of labelling: the `standards` corpus is empty.** The format,
  loader, drift guard and worksheet generator all exist ([[Retrieval Annotation Guideline]]);
  there is nothing to label against. *Say so in the output* is implemented literally — the sample
  size caveat prints in every report, and below 30 the tool renders no verdict at all.
- [x] **`recall@5` and `MRR`**, with **counts printed beside every rate**, on the pattern of
  `infrastructure/eval/scorer.py`. *(2026-08-07 — `metrics.py`, plus `precision@k`. Counts beside
  every rate as specified, and **a chance floor beside every rate** as an addition: `recall@5`
  is bounded below by what a shuffler gets, and without that floor printed, `1.00` over six
  documents reads as success.)*
- [x] **A committed baseline** (`tests/fixtures/retrieval/retrieval-baseline.json`), so
  lexical-vs-dense becomes a measured question rather than a matter of taste. *(2026-08-07 — a
  **census baseline**, `status: "no-measurement"`, recording per-collection record counts and the
  reason no metric exists. `domain_rules` is marked `client_local` and deliberately **not** pinned:
  it comes from the gitignored client rules folder, so a committed count would match one machine
  and read as a regression on every other install. Regenerate with
  `python tools/retrieval_eval.py census --baseline`.)*

> **Exit:** `recall@5` exists as a number against a committed baseline. **Nothing tunes retrieval
> before this lands** — including the tempting one-line changes to `ngram_range` and `top_k`.
>
> ⚠️ **Not met, and correctly so.** `recall@5` exists as *machinery* and refuses to produce a
> number, because the corpus it would measure is empty. The committed baseline records that
> refusal rather than a placeholder figure.
>
> **The freeze on tuning therefore stands, and is now enforced rather than promised.** Nothing in
> R1 or R2 tuned `ngram_range`, `top_k`, `min_score`, or the ranker choice; `tfidf` remains the
> default over BM25 and RRF on argument alone. There is no number to tune against, and the tool
> will not manufacture one — `informative` is False unless all four gates pass, and a baseline
> written from synthetic labels is refused outright.

### Risk

**The likely result is that retrieval is not the bottleneck.** The corpus is thin: **2** learned
dismissal patterns live, 21 verdict labels, an unknown number of uploaded standards. If R2 reports
that lexical retrieval over a handful of documents changes nothing a user notices, **that is a
real answer** — and it is far cheaper to learn here than after building sync. Record it as a
negative result and stop, rather than reaching for dense embeddings to rescue the number.

> ✅ **This risk landed, and the "unknown number of uploaded standards" is now known: it is zero.**
> Recorded as a negative result in [[00 - AI Maturity Status]]. No dense embeddings were reached
> for, no encoder was changed, and no parameter was tuned — there is no number any of that could
> have improved.
>
> **What R3 and R4 inherit.** R3 (two-tier bundles) and R4 (knowledge sync) are both machinery for
> *moving rules between machines*. On the evidence here, the binding constraint is one level
> below that: **the vendor baseline tier has no content and the standards corpus has no
> documents.** Building distribution for an empty payload is the same error as building retrieval
> over an empty index, one stage later and considerably more expensive. Before R3, either upload
> real standards and label ~30 queries, or take the decision that the standards-audit pipeline is
> not the product and stop the track here. That is a scoping call, not an engineering one.
>
> ✅ **Answered 2026-08-10: stop the track** — [[ADR-009 Retiring the Standards Knowledge Track]]. The
> owner's decision, on product grounds; the census establishes only that the corpus is empty, not
> whether filling it is worth doing. Two other options were weighed and are recorded in ADR-009:
> narrowing R3/R4 to `domain_rules` (6 records do not need a distribution format) and building both
> stages anyway (the error the track existed to correct, one layer up). **The reopening condition is
> concrete**, so this is a stop rather than an abandonment.

---

## Stage R3 — Two-tier bundles, and the seams that keep hosting open ⛔ **RETIRED 2026-08-10**

*~1 week. No new dependencies.* — **Never started.**

> [!CAUTION] Retired unbuilt — [[ADR-009 Retiring the Standards Knowledge Track]]
> **Distribution machinery for a payload that does not exist.** The vendor baseline tier has no
> content and the standards corpus has no documents (R2's census: `standard_chunks` = 0). Building
> this would be the same error as building retrieval over an empty index, one stage later and
> considerably more expensive.
>
> **One of the two seams was already built, and survives.** R1 made `domain_rules` source records
> through a *function* (`RecordSource`) rather than a path — which is exactly seam 1 below — because
> the bundle did not exist yet. So the cheap half of R3's forward-compatibility obligation is in the
> tree regardless. Seam 2, the minimized feedback record as a first-class type, is **not built** and
> lapses with R4.
>
> **The defect below is live and does NOT retire with this stage.** It is re-homed to
> [[00 - AI Maturity Status]]'s unblocked-engineering list, because it belongs to the comparison
> engine, not to this track.

Full schema in [[Standards Knowledge — Rule Bundle Format]].

- **Global baseline** — vendor-authored, installer-shipped, version-pinned per release.
- **Per-client overlay** — client-scoped; **never merges upward automatically.**
- `VaultSyncManager` loads *baseline then overlay*. **Markdown stays the authoring format; the
  bundle is the distribution format.** The loading seam already exists —
  `VaultSyncManager.__init__` takes an injectable `vault_path` and is tested.

### The two seams — build them now; they are expensive to retrofit

1. **A bundle *source* abstraction, not a path.** A local directory today; a remote source drops
   in later without touching a single consumer. A path parameter would force a rewrite at every
   call site the day hosting is decided.
2. **The minimized feedback record as a first-class type** — `(pattern, category, count,
   client_id)` — emitted at the edge **even though nothing transmits it.** This fixes the privacy
   boundary while it is free. Retrofitting minimization onto a shipped full-payload API means
   breaking a contract someone already depends on.

### A defect to fix in the same change → **re-homed 2026-08-10, still live**

> [!DANGER] This is the one item that outlives the stage, and with the overlay tier retired
> **nothing else prevents it.** Tracked from [[00 - AI Maturity Status]] now. A second defect in the
> same six lines was found while confirming this one on 2026-08-10: the count is wrapped in
> `except Exception: dismiss_count = getattr(feedback, "_mock_dismiss_count", 3)`, so **any database
> error defaults the count to exactly the promotion threshold** and one dismissal writes a permanent
> rule. Test scaffolding (`_mock_…`) reachable from the production path, in the write path to the
> only vault folder the engine actually reads.

`AutoDocEngine.process_feedback_event` counts dismissals with **no `client_name` filter**:

```python
dismiss_count = await AuditFeedbackDocument.find(
    AuditFeedbackDocument.entity_text == target_text,
    AuditFeedbackDocument.human_corrected_status == "dismissed"
).count()
```

So a pattern dismissed **once at each of three different clients** reaches N≥3 and is then filed
under whichever client happened to trip it — `Learned_Rules_{client_label}.md`. That is
cross-client contamination in the precise mechanism the overlay tier exists to prevent, and it
must be fixed before overlays are generated from it.

> **Exit:** an edge with no network resolves rules from the installer baseline alone,
> deterministically, pinned by version. A test asserts a pattern dismissed at **3 different
> clients does not promote**.

### Risk

`VaultSyncManager` is a **runtime input to the comparison engine** — `get_learned_dismissal_rules`
feeds `safe_filter` and the zone pools. Changing how it loads can silently change what the
comparison engine excludes. `tests/test_vault_sync_scope.py` and
`tests/test_learned_dismissal_scope.py` must stay green, **and** the eval corpus must remain
byte-identical.

---

## Stage R4 — Knowledge sync ⛔ **RETIRED 2026-08-10** (was ⏸ deferred)

*Do not start until production. Recorded so it does not become a phantom.* — **Never started, and
now retired rather than deferred. The distinction is the point: a deferred stage waits for a
trigger; this one waits for nothing.**

> [!CAUTION] Retired — [[ADR-009 Retiring the Standards Knowledge Track]]
> The hosting fork below never has to be resolved, because there is no knowledge to host. **The
> payload decision survives as a constraint**, not as a plan: if sync is ever revisited, it is still
> `(pattern, category, count, client_id)` and the minimization argument in
> [[ADR-008 The Second Brain — Retrieval-Only Local Knowledge]] still holds. The LAN-server
> rejection also stands, on its own cost argument, independently of this.

**The hosting decision is deliberately open**: vendor cloud (per-client isolated) or
installer-bundles-only. It gets its own ADR when production arrives, informed by a working index
and a real retrieval metric — neither of which exists today.

What was **already fixed**, so that R3's seams could be built against it — retained as constraints:

- **Payload:** `(pattern, category, count, client_id)`. Never drawings, geometry, coordinates,
  filenames, session ids, `finding_snapshot`, or free-text `human_comment`.
- **`AutoDocEngine` runs centrally**, not at the edge: N≥3 thresholding **scoped per client**,
  plus a lead-auditor approval gate before a candidate becomes a rule.
- **Edges consume overlays read-only.** Server unreachable is **normal operation**, not an error.

Rejected during planning and recorded in [[ADR-008 The Second Brain — Retrieval-Only Local Knowledge]]: the **customer LAN server** (install/upgrade/support burden at every site) and
**encryption as a substitute for minimization** (custody, not interception, is the objection).

---

## Dependency budget

| Stage | New dependencies |
| :--- | :--- |
| R0 | none |
| R1 | **none** — sklearn, numpy, scipy present |
| R2 | none |
| R3 | none |
| R4 (deferred) | none in this repo; a service that does not exist yet |
| dense encoder (optional, **only on a measured win**) | `onnxruntime` + `tokenizers` (~80 MB) |

**The entire local foundation ships without adding a byte to the bundle.** For a Tauri app
carrying a Python sidecar, that is worth protecting.

---

## Definition of Done — every stage

- [ ] Code landed, tests pass
- [ ] Measured effect recorded — **or explicitly recorded as unmeasured; never omitted**
- [ ] Eval corpus still **P 0.98 / R 0.87 / F1 0.92** against `baseline-v43.json`
- [ ] Any new gotcha written under `06 - Gotchas & Debugging Lessons/` and linked from the MOC,
      **including negative results**
- [ ] `pytest tests/ -q` green bar the 2 known `test_vision_ocr_grounding` failures;
      `npx tsc --noEmit` clean; `npx vitest run` green
