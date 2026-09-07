---
title: ADR-003 AI Maturity Ladder
type: adr
tags: [adr, architecture, ai-architecture, rag, evaluation, learning, agentic]
status: accepted
date: 2026-08-05
supersedes: none
related: [ADR-002 Decoupled Zone Bounding Box Endpoint]
---

# ADR-003 — AI Maturity Ladder: sequencing and four locked decisions

**Status:** accepted · **Date:** 2026-08-05

Work: [[AI Maturity Ladder — Staged Plan]] · Live status: [[00 - AI Maturity Status]]

---

## Context

The stated goal is to evolve the AI architecture along four rungs: **Basic RAG → Fine-Tuned RAG →
End-to-End Trainable → Agentic & Adaptive**. Investigation of the codebase and this vault established
two facts that make the stated order unworkable.

**The system is on rung 0, not rung 1.** The default comparison method is keyed `rag` but contains
no retrieval and no LLM — it is a pure deterministic spatial/text differ. The embedding model returns
`SHA-256(text)`-seeded Gaussian noise with hardcoded bumps for English keywords (`tolerance/hole`,
`cable/rubber`, `column/wind`) that do not occur in this Japanese CAD domain, behind a docstring
claiming SentenceTransformers and ONNX. The "LanceDB" manager is a JSON file plus a numpy loop, and
its store is empty. The only retrieval that exists is `find(client_name).limit(5)` ordered by
recency — a filter, not a query.

**Every rung above zero is defined by optimising against a metric, and no metric exists.**
[[00 - AI Agent Navigation & System Gap Analysis]] records this as the system's largest gap:

> *"Nothing has ever measured whether the engine catches the changes a human checker would flag.
> There is no drawing pair with a known, deliberate change list to score against. For an inspection
> tool that is the number that matters, and we do not have it. Closing this gap needs ground truth,
> not more code."*

"Fine-tuned" needs a validation score. "Trainable" needs a loss. "Adaptive" needs a signal. Without a
scoring function, each rung would be a claim rather than a measurement — and this vault has already
recorded what that produces: `CLAUDE.md` advertised "the four V2 gaps" for months, a phrase the gap
analysis had to document as having *"no source in this vault."*

Two further findings shaped the sequencing:

- `generate_deterministic_candidates` (`orchestrator.py:290`) makes no database call and no LLM call
  across its 960 lines; all impurity sits in the `perform_drawing_comparison` wrapper at `:1253`.
  The full pipeline is therefore runnable offline, in-process, at zero cost.
- `storage/cache/` contains no replayable LLM output at all: every `gemini_comparison_*` entry is
  method `rag`, most are test placeholders, and there are zero `hybrid` / `rag_ai` / `ai_vision`
  entries.

---

## Decision

**Insert a measurement substrate as Stage 0, ahead of all rung work, and promote threshold
calibration to Stage 0.5, ahead of all retrieval work.** Then climb the ladder in order.

Four sub-decisions are locked.

### 1. Ground truth: mutation-first, then human

An `ezdxf`-based mutator injects known changes into real DXFs — retype a dimension, delete a note,
add a BOM row, edit a title attribute, plus `null_mutation` where the truth is *zero findings* and
every result is a measured false positive. Recall is known **by construction**, pairs are unlimited,
and it lands in days. Then 8–12 hand-labelled real pairs serve as the honest held-out gate, with 3
held out permanently.

*Rejected — human-labelled only:* takes weeks against ~6 available pairs, and every subsequent
threshold sweep would overfit a corpus that small.
*Rejected — mutation only:* synthetic changes are cleaner than real revisions (no re-layout, no
re-lettering, no drafter drift), so a recall number against them alone would not describe reality.
*Rejected — mining the 22 existing corrections as weak labels:* structurally incapable of measuring
false negatives, because it only labels findings the engine already produced — which is the entire
gap.

### 2. Retrieval: lexical first; dense must earn its way in

Character n-gram TF-IDF + BM25 via sklearn, already a dependency. This corpus is not prose: it is
short, symbol-dense, mixed-script CAD callouts where the discriminating signal is often a single
digit (`22.7±0.02` vs `22.7±0.05`) — precisely where dense semantic smoothing hurts and character
n-grams excel. `FindingClassifier` already uses `HashingVectorizer(char_wb, 2-4)` and is the one
learned component in the system that demonstrably works.

*Rejected — ONNX dense now:* ~80 MB into a Tauri-bundled sidecar before any measurement justifies it.
Kept behind the `encoder.py` interface, admissible on a measured win.
*Rejected — Gemini embedding API:* puts a network call in the comparison loop, breaks offline-capable
desktop operation, costs per call, and sends customer CAD text to a third party.
*Rejected — `sentence-transformers`:* pulls `torch`, ~2.5 GB, to retrieve over ~2k short strings.
*Rejected — LanceDB / FAISS / Chroma / Qdrant:* at ≤100k short strings brute-force numpy cosine is
~1 ms and *exact*; an ANN index adds a dependency, a build step and an accuracy approximation to buy
nothing.

### 3. Sequencing: the AI ladder runs through Stage 3 first, then converges with the Catmull roadmap

Stages 0 through 3 need nothing from `docs/let-s-plan-about-the-structured-catmull.md` — they operate
on today's entity model and add no dependencies. Stage 4's agentic tool loop is **hard-blocked** on
that roadmap's Phases 1–2 (entity model + invertible `ViewportTransform`, `CadPoint` contract),
because the loop's entire value is entity-grounded queries and `entity_handle()` still falls back to
`properties["handle"]`. The roadmap's Phase 4 is Stage 4's prerequisite, not a parallel track.

*Rejected — Catmull Phases 1–2 first:* delays the recall number by months, and the recall number is
what makes every later decision measurable.
*Rejected — interleaving both tracks:* the roadmap itself warns that three concurrent workstreams is
already enough, and a moving entity model would invalidate eval baselines mid-flight.

### 4. Vault: move the model out, commit the docs, keep client rules ignored

`finding_classifier.joblib` lives in `docs/vault/09 - Learned Models/`, which `.gitignore:77`
excludes. **A model that cannot be committed, diffed, versioned or shipped is not trainable
infrastructure** — this blocks rung 3 outright. It moves to `services/backend/storage/models/`
(gitignored payload, committed `.meta.json`), with `Model Card.md` still written into the vault as
the human surface.

The vault's architecture, ADR and gotcha folders become git-tracked, so 46 notes of hard-won
knowledge stop existing on exactly one machine. `08 - Client Domain & CAD Rules/` **stays ignored**:
it holds customer-specific Japanese anchors and is the only folder that is a runtime input.

*Rejected — commit the entire vault:* would place customer CAD conventions and learned dismissal
patterns into git history.
*Rejected — leave both as-is:* leaves the learned model unshippable and the knowledge base a
single-machine liability.

---

## Consequences

**Positive**

- A recall number exists for the first time — the gap analysis's stated top priority.
- Rung 3 is reachable **without adding a single dependency**, which for a Tauri app shipping a Python
  sidecar is worth protecting.
- Stage 0.5 is expected to deliver most of the near-term F1 movement for one week of work, because
  all 16 tuning constants are currently unmeasured guesses and several were "calibrated against one
  observed case."
- Every later claim about retrieval or learning becomes falsifiable rather than assertable.

**Negative / accepted costs**

- ~3 weeks of work before any user-visible change. Stage 0 ships no feature.
- The eval corpus is small (8–12 human pairs); every conclusion drawn from it carries wide error
  bars, and the runner is required to print counts alongside every rate.
- The scorer's finding-matcher is itself a differ and can be wrong; it must be hand-audited on 2
  pairs before any aggregate is trusted.
- Stage 2 is gated on human labelling time, not engineering. At 21 of 40 required labels the model is
  inert, and no amount of code removes that wall.

**Neutral but load-bearing**

- Stage 1's retrieval improvements are invisible to users until `hybrid` becomes the default method,
  because retrieval feeds only the Gemini system prompt and the default method invokes no LLM. This
  is stated explicitly so the work is not mistaken for a shipped feature.
- Hard constraint 1 (no open-ended shapes in Gemini schemas) **extends to tool/function declarations**
  at Stage 4. The existing guard test must be widened to walk them.
- Stage 0.5 and Stage 3 both change spatial matching and therefore both require a
  `COMPARISON_CACHE_VERSION` bump. Stage 0.5 is also the one safe moment to rename the `rag` method
  key to `deterministic`, since that bump invalidates everything anyway.
- An agent loop cannot be cached by `(ref, rev, method)`. Stage 4 must explicitly decide between
  caching the trace and accepting always-cold runs.
