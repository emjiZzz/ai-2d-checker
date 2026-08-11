---
title: RAG Reference Architecture — Gap Analysis
type: architecture
tags: [architecture, rag, retrieval, embeddings, vectorstore, gap-analysis, ai-architecture]
status: active — body is a 2026-08-07 snapshot; see the re-verification block for what changed
date: 2026-08-07
updated: 2026-08-10
verified-against: cache v43, baseline-v43.json, working tree at 2026-08-07; re-verified against the working tree and live Mongo on 2026-08-10
related: [ADR-007 Re-scoping the Maturity Ladder, ADR-004 Deterministic-Only Scope, ADR-006 Removing the Three AI Comparison Methods]
---

# RAG Reference Architecture — what we have, what we lack

Prompted by a canonical RAG diagram (Gemini-authored, 2026-08-07) and the question: *can our
system compare to this, and if not what are we lacking?*

The reference pipeline, in two phases:

```
Ingestion:      Parsing -> Chunking -> Embed(I) -> VectorStore
Query/Runtime:  Query -> Embed(Q) -> SimSearch <- Context -> Re-rank -> Prompting -> LLM Output
```

Every claim below was checked against the working tree on 2026-08-07, not taken from other
notes. Where a claim contradicts [[00 - AI Maturity Status]], the contradiction is stated.

> [!IMPORTANT] Re-verified 2026-08-10 — **five rows below were true for three days and are now
> wrong in the same direction.** The body is kept as written, because the diagnosis is what
> justified the fixes; read it as of 2026-08-07 and this block as of today.
>
> | Node | This doc says (08-07) | Live today (08-10) |
> | :--- | :--- | :--- |
> | Embed(I) / Embed(Q) | ⚠️ SHA-256 noise | ✅ **real.** `local_embedding_model.py` **deleted**; `retrieval/lexical.py` is char n-gram TF-IDF — lexical, and it says so |
> | VectorStore | ⚠️ a JSON file misnamed LanceDB | ✅ **real.** `lancedb_manager.py` **deleted**; `retrieval/store.py` is exact brute-force cosine over a scipy CSR matrix + JSONL sidecar + manifest |
> | SimSearch | ⚠️ cosine over noise | ✅ **real**, 6–9 ms, offline |
> | The `embed_text` singular bug | ❌ live; `lessons_learned` never written | ✅ **fixed** — no singular call site remains in our code |
> | Retrieval evaluation — *"the real gap"* | ❌ absent | ✅ **built** (R2), and it answered: there is nothing to measure |
>
> **The bottom line has inverted, and that is the finding.** On 08-07 this was *"the skeleton of
> the diagram with a placeholder where the semantics should be."* Today the semantics are real and
> the **corpus is empty**: `standard_chunks` **0**, `standard_documents` **0**, `standards` **0**,
> and no `lessons_learned` collection exists at all. We traded a retriever that worked on noise for
> a working retriever with nothing to retrieve — which is strictly better, because the second
> failure is visible and the first was not.
>
> **Why the corpus is empty is itself a correction.** Not disinterest — the desktop upload posted
> to a GET-only route and returned **405** on every attempt, so no standard could be ingested at
> all. Fixed 2026-08-10; see [[Gotcha - A Standard That Ingested Nothing Reported Success]]. Read
> `standard_chunks = 0` as a statement about the code, not about demand.
>
> This doc's own closing question — *"is the standards pipeline a product we are building or a
> prototype we are carrying?"* — was answered on 2026-08-10 by
> [[ADR-009 Retiring the Standards Knowledge Track]]: **carrying, and now retired** (that ADR is
> itself amended, on this same premise). R0–R2 stay in
> the tree; R3 and R4 are retired, not deferred, and the reopening condition is about data, not
> engineering. **Do not restart retrieval work from this document.**
>
> Unchanged and still the load-bearing point: **the comparison engine has no query.** See "the
> deeper mismatch" below — nothing since has altered it, and ADR-007 remains the answer.

---

## The headline: there are TWO pipelines, and the ledger only tracks one

This is the finding that reframes the question, and it is not recorded anywhere else in the
vault.

| | **Drawing comparison** | **Standards audit** |
| :--- | :--- | :--- |
| Entry point | `audit/comparison/orchestrator.py` | `audit/audit_orchestrator.py` |
| What it does | diffs two drawings, reports changes | audits one drawing against standards |
| Retrieval? | **none** | **yes — a live RAG stage** |
| LLM? | **none** (except title-block OCR) | **yes, Gemini** |
| Tracked by the ledger | yes, exclusively | **no, not at all** |
| Governed by ADR-004/006/007 | yes | **no** |

The whole maturity-ladder programme — ADR-003 through ADR-007, the eval harness, the corpus,
the sweep, everything in [[00 - AI Maturity Status]] — is about the **left** column. When that
ledger says *"the default method contains no retrieval and no LLM"*, it is telling the truth
about the comparison engine and saying nothing at all about the right column.

**The right column is where a RAG pipeline already exists**, and it is live product surface:
`audit_pipeline.audit_queue` is imported by `main.py` at app startup and by the `audits.py`
router. `audit_orchestrator.py:229` constructs a `RetrievalEngine` and queries it on every
audit; `:103` logs *"RAG retrieval complete in {duration}s"*.

So the answer to *"can our system compare to this diagram"* is: **one half of the product is
shaped almost exactly like it, and every retrieval-specific component in that shape is
non-functional.**

---

## Node-by-node

Legend: ✅ real · ⚠️ runs but meaningless · ❌ absent · 🚫 deliberately out of scope

| Diagram node | Drawing comparison | Standards audit |
| :--- | :--- | :--- |
| **Parsing** | ✅ **Genuinely strong.** DXF → entities via ODA converter + `entity_mapper`, Shift-JIS/CP932 handling, MTEXT markup stripping, zone detection. Years of gotchas paid for. But it parses *geometry*, not prose. | ✅ `StandardChunk` documents in Mongo |
| **Chunking** | ⚠️ The nearest analogue is **zone detection** — `notes` / `bom` / `title` / `views` / `iso`. That is spatial chunking of a sheet, and it is real, but it is not text chunking for embedding. | ✅ chunked at ingest |
| **Embed(I)** | 🚫 n/a | ⚠️ **SHA-256 noise.** `local_embedding_model.py:34-40` seeds `np.random.default_rng` from `sha256(text)` and returns 384 Gaussian dims. |
| **VectorStore** | 🚫 n/a | ⚠️ **A JSON file.** `lancedb_manager.py` is not LanceDB — `index_shards.json` plus a numpy loop. No such file exists on disk; `storage/ai-artifacts/embeddings/` is empty. |
| **Query** | ❌ **There is no query, and there cannot be one.** See "the deeper mismatch" below. | ✅ drawing file name + layer names + entity types, `audit_orchestrator.py:188-205` |
| **Embed(Q)** | 🚫 n/a | ⚠️ same noise model |
| **SimSearch** | ❌ `few_shot_retriever.py` **deleted** by [[ADR-006 Removing the Three AI Comparison Methods]]. It was `find(client).sort("-created_at").limit(5)` — recency, not similarity. | ⚠️ **cosine over noise.** Mathematically valid, semantically empty. Runs, returns results, logs a count. |
| **Re-rank** | ❌ absent (was Stage 2c) | ❌ absent |
| **Prompting** | ❌ consumers deleted by ADR-006 | ✅ injects retrieved chunks as *"Lessons Learned"* |
| **LLM Output** | 🚫 **deleted.** `gemini_client.py` survives **only** for `execute_title_block_ocr` — OCR, not generation. | ✅ real Gemini call |

### The one outright bug found while checking

`audits.py:377` calls `provider.embed_text(text_to_embed)` — **singular**. `EmbeddingProvider`
only defines `embed_texts` (plural). It is an `AttributeError`, inside a `try` whose `except
Exception` logs a warning and continues.

**Consequence:** the `lessons_learned` collection is **never written**. Every supervisor
review that was supposed to be indexed as a lesson has silently failed since the code was
written. The staged plan flagged this at Stage 0a and it is still live — it was never actioned
because Stage 0a's scope was the comparison path.

Note `standards.py:231`, `retrieval_engine.py:23` and `standards_indexer.py:37` all call the
**plural** method correctly. So the *read* path works and the *write* path for lessons does
not — which means retrieval queries an index that one of its two writers can never populate.

---

## What "we lack" actually means, in order

### 1. A real embedding model — the one genuine dependency

Everything else is code we could write today. This is the only item needing a new artifact.

**Decided already, do not re-litigate** ([[00 - AI Maturity Status]] negative results):
`sentence-transformers` is rejected — it pulls `torch`, ~2.5 GB into a Python sidecar shipped
inside a Tauri bundle, to embed ~2k short strings. The path, if dense is ever justified, is
**ONNX Runtime (~80 MB, no torch)**.

**But lexical first.** `TfidfVectorizer(analyzer="char_wb", ngram_range=(2,4))` + BM25 needs
**zero** new dependencies (sklearn is present) and mirrors `FindingClassifier`'s
`HashingVectorizer(char_wb, 2-4)` — the one learned component in this system that
demonstrably works. Character n-grams are also the right call for Japanese, which does not
word-segment on spaces. Dense should have to beat lexical on a measurement, not on vibes.

### 2. Deleting the fake stack, not fixing it

`local_embedding_model.py` should be **deleted, not repaired**. Its docstrings claim
*"HuggingFace/SentenceTransformers"*, *"ONNX Runtime and Quantized inference"*, and
*"robust offline semantic matching"*, while `_load_model` assigns the **string**
`"ONNX_Quantized_MiniLM"` to `self._model` and never loads anything.

That is worse than an empty stub. A stub raises; this returns plausible 384-dim normalized
vectors that flow through cosine similarity and produce ranked results with scores. **Nothing
downstream can tell the difference between this and a working model** — which is precisely the
failure mode this project's whole Stage 0 exists to make impossible.

`lancedb_manager.py` keeps its **algorithm** and loses its **name**: brute-force numpy cosine
over ≤100k short strings is ~1 ms and *exact*, and an ANN index buys nothing at this scale
(also already recorded as a rejected idea). What it needs is honest naming and a real
persistence format (`.npy` + JSONL sidecar), not LanceDB.

### 3. Populating the index at all

`reindex_standards` (`standards.py:208`) exists and runs. It currently writes noise. Fixing
(1) makes this endpoint immediately useful — but nothing calls it automatically, so index
freshness is a manual operation with no staleness signal.

### 4. Re-ranking

Absent from both pipelines. The plan's shape — retrieve top-20 lexically, rerank with a
`FindingClassifier` over `(query ⊕ candidate)` features using dismissed-vs-confirmed as the
label — needs no new dependencies. **And if it does not beat lexical-only, that is a real
answer**, not a failure: it would say retrieval is not the bottleneck.

### 5. A way to know whether any of it works

This is the one that matters most and is easiest to skip. There is **no retrieval metric** for
the standards pipeline, no golden query set, and no offline harness — the eval machinery built
across Stage 0 covers only the comparison path.

Building retrieval without this repeats the exact mistake the ladder was rewritten to avoid:
[[ADR-007 Re-scoping the Maturity Ladder]] made *measurement* rung 1 precisely because
optimising against an absent metric is how a system ends up with SHA-256 embeddings that
nobody notices for months.

**Retrieval can also actively hurt.** Injecting five near-miss exemplars into a prompt as
authoritative prose is a recall attack — it teaches the model to *not* report things. In an
inspection tool, a silent recall loss is the worst possible failure, and it is the one this
system already knows it cannot detect.

---

## The deeper mismatch: our comparison engine has no query

Worth stating plainly, because it is why this diagram cannot simply be adopted wholesale.

The reference architecture is a **question-answering** shape. It assumes a user arrives with a
query, and the system finds context to answer it.

**The drawing comparison has no query.** It takes two drawings and reports what changed. There
is no natural-language question, no information need to satisfy, and no answer to ground. The
`Query` node has nothing to bind to. Retrofitting one — embedding a finding and retrieving
"similar findings" — is a real idea, but it is a *reranking / adjudication* aid, not the
diagram's `Query` node, and it does not make the pipeline RAG.

This is exactly what [[ADR-007 Re-scoping the Maturity Ladder]] settled on 2026-08-07: rung 3
is **"Retrieval-augmented"** meaning *retrieving prior human decisions* — the learned-dismissal
flywheel and the learned overlay — because that is the only retrieval the deterministic path
can consume. It gates real output today, which the diagram's version never did.

So:

- **For the comparison engine:** this diagram is **the wrong target**, and building it would
  reverse ADR-004 and ADR-006 two days after they landed. What retrieval means there is
  narrower and already planned.
- **For the standards audit:** this diagram is **exactly right**, it is already the shape of
  the code, and every retrieval component in it is a placeholder.

---

## Honest scorecard

| | Reference | Ours |
| :--- | :--- | :--- |
| Ingestion parsing | generic documents | ✅ better than generic — real CAD extraction |
| Chunking | text splitter | ✅ standards chunked; ⚠️ drawings chunked spatially, not for retrieval |
| Embeddings | trained model | ❌ **SHA-256 noise** |
| Vector store | ANN index | ⚠️ JSON file, empty (algorithm right, everything else wrong) |
| Similarity search | cosine/ANN | ⚠️ runs over noise |
| Re-ranking | cross-encoder | ❌ absent |
| Prompting | grounded context | ✅ on the standards path only |
| Generation | LLM | ✅ standards path · 🚫 comparison path, deliberately |
| **Retrieval evaluation** | recall@k | ❌ **absent — and this is the real gap** |

**Bottom line.** We are not "close to RAG with a few pieces missing." On the standards path we
have the *skeleton* of the diagram with **a placeholder where the semantics should be**, plus a
silent write-path bug. On the comparison path we deliberately have none of it, and per ADR-007
that is a decision, not a deficiency.

The single most valuable thing is not an embedding model. It is deciding whether the standards
pipeline is a product we are building or a prototype we are carrying — because it is currently
neither measured nor governed by any ADR, while running in production on noise.

---

## Related

- [[ADR-007 Re-scoping the Maturity Ladder]] — why rung 3's "retrieval" is not this diagram's
- [[ADR-004 Deterministic-Only Scope]] · [[ADR-006 Removing the Three AI Comparison Methods]] —
  why the comparison path has no LLM
- [[00 - AI Maturity Status]] — the ledger (comparison path only)
- [[AI Maturity Ladder — Staged Plan]] — Stage 1b (dropped) and Stage 2c (reranker)
- [[00 - AI Agent Navigation & System Gap Analysis]] — *"nothing has ever measured whether the
  engine catches the changes a human checker would flag"*
