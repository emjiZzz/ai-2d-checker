---
title: ADR-008 The Second Brain — Retrieval-Only Local Knowledge
type: adr
tags: [adr, architecture, rag, retrieval, knowledge, second-brain, privacy, ai-architecture]
status: accepted
date: 2026-08-07
amended: 2026-08-10 (R3 and R4 retired — the corpus is empty; see ADR-009)
supersedes: none
amends: none
amended-by: ADR-009 Retiring the Standards Knowledge Track
related: [ADR-005 Local-Only Processing with Cloud Licensing, ADR-007 Re-scoping the Maturity Ladder, ADR-009 Retiring the Standards Knowledge Track, RAG Reference Architecture — Gap Analysis]
---

# ADR-008 — The Second Brain: retrieval-only, local, governed

**Status:** accepted, **partially retired 2026-08-10** · **Date:** 2026-08-07

Work: [[Standards Knowledge — Staged Plan]] · Contract: [[Standards Knowledge — Rule Bundle Format]] ·
Findings that prompted it: [[RAG Reference Architecture — Gap Analysis]]

> [!WARNING] Amended 2026-08-10 — [[ADR-009 Retiring the Standards Knowledge Track]]
> **R0, R1 and R2 landed. R3 and R4 are retired, and the track stops here.** R2's census found the
> corpus empty — `standard_chunks` **0**, and all 1,322 audit violations unreviewed — so decisions
> **2** (two tiers) and **3** (hosting deferred) are retired unbuilt, and decision **4**'s payload
> lapses as a build item while surviving as a constraint. Decisions **1** (retrieval-only) and **5**
> (LAN server rejected) stand unchanged, as does everything below about custody and encryption,
> which is about [[ADR-005 Local-Only Processing with Cloud Licensing]] and outlives this track.
>
> **Two things below are now false and are corrected in ADR-009 rather than edited out here.** The
> consequence *"the standards-audit pipeline gets an owner"* is **reversed** — it has no owner
> again, though it is no longer running on fiction. And the R3 obligation *"two seams must exist
> before the fork arrives"* is **half met**: the bundle source abstraction was built early in R1 and
> survives; the minimized feedback record was R3's and does not exist. The
> `AutoDocEngine` cross-client defect R3 was to fix is **live** and re-homed to
> [[00 - AI Maturity Status]].
>
> **The subsystem this ADR designs was renamed on 2026-08-10: it is the "standards knowledge
> track", not "the Second Brain".** That name collided with the vault itself — the MOC is titled
> *"AI-2D-Checker System Second Brain"*, and `vault_sync.py` and `auto_doc.py` both say *"the
> Obsidian Second Brain"* — so *"the Second Brain is retired"* read as *"the vault is retired"*.
> **This ADR keeps its original title on purpose**: an ADR records what was decided *and under what
> name*, and retitling a ratified decision erases half of that. Every occurrence of "the Second
> Brain" in the decision text below means the standards knowledge subsystem. The working documents
> ([[Standards Knowledge — Staged Plan]], [[Standards Knowledge — Rule Bundle Format]]) carry the
> new name.
>
> The original decision text is left intact below. ADR-009 records the reopening condition.

---

## Context

The brief was to make RAG *the foundation* of the system. Investigating what we already had
produced a finding that reframed the question — [[RAG Reference Architecture — Gap Analysis]]:

**There are two pipelines, and [[00 - AI Maturity Status]] tracks only one.**

| | Drawing comparison | Standards audit |
| :--- | :--- | :--- |
| Entry | `audit/comparison/orchestrator.py` | `audit/audit_orchestrator.py` |
| Retrieval | none, deliberately | **yes — live** |
| LLM | none (title-block OCR aside) | yes, Gemini |
| Governed by | ADR-004/006/007 | **nothing** |

The standards-audit pipeline is already shaped like a textbook RAG diagram — real query, vector
search, prompt injection, generation — and it is live product surface, wired into `main.py` at
startup. **Every retrieval component in it is a placeholder:**

- Embeddings are `np.random.default_rng(sha256(text))` while the docstrings claim
  *"HuggingFace/SentenceTransformers"* and *"ONNX Runtime"*; `_load_model` assigns the **string**
  `"ONNX_Quantized_MiniLM"`.
- The "vector store" is `index_shards.json`. No such file exists on disk.
- Similarity search runs cosine over that noise and returns ranked, scored, plausible results.

That last property is the reason this ADR exists. **A stub raises; this returns answers.** Nothing
downstream — no test, no metric, no reviewer — could distinguish it from a working model, and it
survived in production unnoticed for months.

## Decision

Build the Second Brain as **local, retrieval-only, governed knowledge**, on a two-tier bundle
model, with the hosting question deliberately deferred.

### 1. Retrieval-only — RAG without the G

> [!WARNING] **Narrowed 2026-08-10 — [[ADR-010 Grounded LLM Summarization of Comparison Results]]**
> *"No LLM in the loop"* now means: **no LLM in the retrieval loop, and no LLM deciding findings.**
> Generation **is** permitted strictly downstream of a complete deterministic finding list, behind a
> mechanical verification gate. The reasoning below is untouched for *clause retrieval* — a checker
> wants cited clauses, not a paragraph they must re-verify — because ADR-010 summarises the system's
> own structured output rather than a retrieved document.

No LLM in the loop. Retrieval surfaces **cited standard clauses and prior decisions to a human
checker**; it never generates prose.

For an inspection tool this is not a compromise, it is the better product. *"Here are the three
clauses that apply, with citations"* is more actionable to a checker than a generated paragraph
they must then verify — and it has **no hallucination surface at all**. Generation can be added
later behind the same retrieval interface if it ever earns its place.

### 2. Two tiers: vendor baseline + per-client overlay

- **Global baseline** — vendor-authored from domain knowledge, ships in the installer,
  version-pinned per release.
- **Per-client overlay** — client-scoped, **never merges upward automatically**.

The tiering exists for a specific hazard, not for tidiness. Learned dismissal patterns are
**verbatim customer drawing text** — the live example, `ユニットNo.`, is a title-block field lifted
from a real sheet. A single shared knowledge pool would ship one customer's drawing content to
every other customer as a "rule". The overlay tier makes that impossible by construction.

### 3. Hosting deferred until production

Dev builds local only. No cloud, no LAN server, no sync.

This is not indecision. **Stages R0–R3 are byte-identical under every hosting option** — an
honest index, a retrieval metric and a versioned bundle format are required whether the Second
Brain later lives in a vendor cloud, on a customer's LAN, or nowhere at all. The fork only
matters once feedback moves *between machines*, and that is production work.

The obligation this creates is real and is discharged in R3: **two seams must exist before the
fork arrives** — a bundle *source* abstraction (not a path), and the minimized feedback record as
a first-class type. Both are cheap now and expensive to retrofit.

### 4. When sync arrives, the payload is already fixed

`(pattern, category, count, client_id)`. Never drawings, geometry, coordinates, filenames,
session ids, or free-text comments.

Fixed **now**, while nothing transmits it, because retrofitting minimization onto a shipped
full-payload API means breaking a contract someone already depends on.

### 5. The LAN server is rejected

It was the only option preserving a strict local-only claim *and* an automatic flywheel, and it
was rejected on cost: install, upgrade and support burden at every customer site, for a
capability that is not needed in development. [[ADR-005 Local-Only Processing with Cloud Licensing]] already records that three of four planned systems do not exist; this would have been
a fifth.

---

## The reasoning worth preserving: encryption does not save a local-only claim

This came up directly and the answer is not obvious, so it is recorded rather than left to be
re-derived.

**ADR-005's argument is about custody, not interception.** In its own words: *"our drawings are
uploaded to a vendor's cloud for analysis is frequently a procurement blocker rather than a
preference to be negotiated"*, and *"a claim of local-only that a determined auditor could
disprove is worth very little."*

Against that argument:

| Measure | Why it does not resolve it |
| :--- | :--- |
| TLS in transit | Table stakes for any API. Says nothing about the data now sitting on a vendor server. |
| Encrypted at rest, vendor holds keys | The vendor decrypts to process. That is *"we promise not to look"*, not *"we cannot look."* |
| **Zero-knowledge** (vendor never decrypts) | **Mutually exclusive with this design.** The entire purpose of a central Second Brain is to *process* feedback — N≥3 thresholding, curation, approval. **You cannot threshold what you cannot read.** |

So encryption is necessary but not sufficient, and it changes the promise from *"your drawings
never leave your network"* to *"they leave encrypted and we decrypt to process."* That is ordinary
SaaS and sellable to many customers — but it is a **different product promise**, and ADR-005
argues it is precisely the one that fails Japanese manufacturing procurement.

**The effective lever is minimization, not encryption: reduce what exists to leak rather than
protecting what does.** Hence decision 4. The residual is stated honestly rather than hidden —
pattern text is still drawing-derived, so a part number can travel. Minimization shrinks the
exposure by an order of magnitude; it does not eliminate it.

---

## Alternatives rejected

| Alternative | Why not |
| :--- | :--- |
| **Implement the reference RAG diagram on the comparison engine** | It is a *question-answering* shape and the comparison engine is a **differ** — it takes two drawings and reports what changed. There is no natural-language query, no information need, and nothing for the `Query` node to bind to. Building it would also reverse [[ADR-006 Removing the Three AI Comparison Methods]] two days after it landed. [[ADR-007 Re-scoping the Maturity Ladder]] already settled what retrieval means there: retrieving *prior human decisions*. |
| **Repair the existing embedding stack rather than delete it** | The module does not merely fail to work — its docstrings assert capabilities it does not have, and it returns plausible output. Repairing in place preserves the naming and the assumption that it was ever real. Delete and rebuild honestly. |
| **Dense embeddings first (ONNX / sentence-transformers)** | `sentence-transformers` pulls ~2.5 GB of torch into a Tauri sidecar to embed ~2k short strings — already a recorded negative result. Lexical char n-grams need **zero** new dependencies, mirror the one learned component in this system that demonstrably works (`FindingClassifier`'s `HashingVectorizer(char_wb, 2-4)`), and suit Japanese, which does not word-segment on whitespace. Dense must **win on a measurement** before it ships; the path is ONNX Runtime (~80 MB, no torch). |
| **Add LanceDB / FAISS / Chroma / Qdrant** | Already rejected: at ≤100k short strings brute-force numpy cosine is ~1 ms and **exact**. An ANN index buys nothing and costs a dependency, a build step and an accuracy approximation. `lancedb_manager.py` had the right algorithm and the wrong name. |
| **Vendor cloud with full feedback payload** | Ships `entity_text` + `client_name` + `coordinates` + unbounded free-text `human_comment` off the customer's network. The free-text field is the sharpest edge: an engineer can type anything into it. |
| **Reject ADR-005 and go conventional SaaS** | Discards a genuine commercial differentiator to solve a problem we do not yet have. Deferring keeps the option open at no cost. |
| **Build the flywheel now** | The corpus cannot support it: **2** learned dismissal patterns live, 21 verdict labels. A learning loop over that is machinery with nothing to learn from. |

---

## Consequences

**The standards-audit pipeline gets an owner.** It has been running in production, unmeasured and
governed by no ADR, on noise. This ADR brings it into the same discipline as the comparison
engine.

**Measurement comes before tuning, again.** R2 (the retrieval metric) is deliberately sequenced
ahead of everything downstream. This is [[ADR-007 Re-scoping the Maturity Ladder]]'s lesson
applied literally: optimising against an absent metric is *exactly* how SHA-256 embeddings
survived in production. A retrieval system with no recall@k is the same defect wearing a
different hat.

**A likely outcome is "retrieval is not the bottleneck", and that is a real answer.** The corpus
is thin. R2 may report that lexical retrieval over a handful of standards changes nothing users
notice — far cheaper to learn there than after building sync.

**Retrieval can still hurt.** Surfacing near-miss rules as authoritative is a recall attack, and
in an inspection tool a silent recall loss is the worst possible failure. Retrieval-only mitigates
it — a human reads the citation — but does not remove it.

**The comparison engine is untouched.** Labelling remains its critical path; ADR-004/006/007 stand
unchanged. The eval corpus must score identically (**P 0.98 / R 0.87 / F1 0.92** against
`baseline-v43.json`) throughout this work; **any movement means something leaked across the
boundary.**

**One decision is deliberately left open**, and is recorded here so it does not become a phantom:
**where the Second Brain lives in production.** Vendor cloud (per-client isolated) or
installer-bundles-only. It gets its own ADR when production arrives, informed by a working index
and a real retrieval metric.

---

## Related

- [[ADR-009 Retiring the Standards Knowledge Track]] — **amends this**: R3 and R4 retired, the reopening
  condition, and where the orphaned `AutoDocEngine` defect went
- [[RAG Reference Architecture — Gap Analysis]] — the component-by-component audit behind this
- [[Standards Knowledge — Staged Plan]] — the work, R0→R4 (R0–R2 landed; R3–R4 retired)
- [[Standards Knowledge — Rule Bundle Format]] — the vendor/edge/cloud contract
- [[ADR-005 Local-Only Processing with Cloud Licensing]] — amended by this work; see its
  amendment section
- [[ADR-007 Re-scoping the Maturity Ladder]] — why the comparison engine's "retrieval" is
  something else entirely
