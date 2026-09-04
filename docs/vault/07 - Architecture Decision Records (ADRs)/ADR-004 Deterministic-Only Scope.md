---
title: ADR-004 Deterministic-Only Scope
type: adr
tags: [adr, architecture, ai-architecture, scope, rag, comparison-engine]
status: accepted
date: 2026-08-05
supersedes: none
amends: ADR-003 AI Maturity Ladder
related: [ADR-003 AI Maturity Ladder]
---

# ADR-004 — Focus solely on the deterministic comparison method

**Status:** accepted · **Date:** 2026-08-05 · **Amends:** [[ADR-003 AI Maturity Ladder]]

Work: [[AI Maturity Ladder — Staged Plan]] · Live status: [[00 - AI Maturity Status]]

---

## Context

The app exposes four comparison engines behind a **DEV** badge: `RAG` (SpatialDiffer + BOM),
`RAG + AI` (Gemini, PNG+JSON), `AI Vision` (real DXF AI), and `HYBRID` (two generators +
verify). Only the first is the default and the only one users actually run.

The user's decision: **ignore the three AI methods and focus entirely on the deterministic
one.** Recorded here because ADR-003 sequenced work that assumed the opposite, and because
"don't re-litigate settled decisions" only works if the decision is written down.

## Decision

All AI-ladder work targets the deterministic method only. The three Gemini-backed methods are
neither developed nor measured until this decision is revisited.

## The consequence that matters

**The ladder stops being a RAG ladder.** ADR-003's rungs are named after capabilities that live
in the paths now out of scope. The staged plan says so directly:

> *"Retrieval feeds only the Gemini system prompt → `rag_ai` and `hybrid`'s generator B. **The
> default method never sees it.** A perfect retriever changes nothing users observe until
> `hybrid` becomes the default."*

So rung 1 — "Basic RAG" — is **not reachable** under this scope, because the only consumers of
retrieval are excluded. That is not a reason to reverse the decision; it is a reason to stop
describing the work with rung names that no longer fit.

| Stage | Fate under this ADR | Why |
| :--- | :--- | :--- |
| **0.5 — calibration** | **Promoted to the highest-value work in the plan** | All 16 tuning constants are on the deterministic path: `spatial_differ.py` (6), `reconciler.py` (1), `marking_reconciler.py` (4), `bom/zone_detector.py` (6), `coordinate_resolver.py` (1), `bom/anchors.py` (1). Every one is an unmeasured guess. |
| 0f — cassette + trace | **Dropped** | Exists solely to make the Gemini paths replayable and measurable. With no Gemini paths in scope it buys nothing. `tools/eval.py` already refuses non-deterministic methods. |
| 1a — structured dismissal patterns | **Kept** | `vault_sync.get_learned_dismissals()` → `safe_filter` is the **only** retrieval on the default path, and it gates real output today. |
| 1b — real retrieval store | **Dropped** | Feeds only the Gemini system prompt. |
| 2 — learned overlay | **Kept** | Runs post-cache on the deterministic path. Still gated on label count, not engineering. |
| 3 — learned matcher | **Kept, and becomes the end-goal** | It replaces the threshold cascade *inside* the differ — the most deterministic-path-relevant stage in the whole plan. |
| 4 — agent loop | **Dropped** | Adjudicates disputed `hybrid` findings. |

## Two follow-on consequences

**The `rag` misnomer gets worse, not better.** The one method now receiving all attention is
named after a technique it does not contain — no retrieval, no LLM. Stage 0.5 already planned
`rag` → `deterministic` at its cache bump (the one safe moment, since the key lives in the DB,
cache filenames, the API and the UI, and `drawings.py` substring-matches those filenames). Under
this ADR that rename goes from tidy-up to **necessary**.

> [!NOTE] **Done 2026-08-07, and two of the premises above were wrong.**
> The rename landed *without* the cache bump. `clear_cache_for_drawing` matches on **drawing
> id**, not on the method token, so the purge path was never method-sensitive — the
> `drawings.py` hazard named here does not exist. And the cache held **one real v42 entry**, so
> "the one safe moment" was protecting a single re-run. v43 is still unspent.
> See the ledger's 2026-08-07 work-log rows.

**`current_rung` becomes unanswerable as posed.** The ladder's rungs measure retrieval and
agency. Left as-is the ledger will keep reporting rung 0 forever, which is technically true and
practically useless. Needs either a re-scoped ladder or an explicit note that the rung metric is
retired. **Not decided here** — flagged for the next session.

## What is *not* decided

> [!NOTE] **Both resolved 2026-08-07 by [[ADR-006 Removing the Three AI Comparison Methods]]:
> delete, and no, the picker is gone.** Left below as written — this section is why ADR-006
> is a completion of this decision rather than a reversal of it.

- Whether to delete the three methods' code (12 backend files reference them). Leaving them
  in place costs nothing while they are DEV-badged and unmeasured; deleting is reversible only
  from git.
- Whether the picker should still show them.

## Consequences

**Positive**

- Removes an entire class of blocked work: no cassette, no Gemini key, no per-call cost, no
  non-reproducible measurement. Everything in scope runs offline.
- Concentrates effort on the path users actually run, where the plan already predicted the
  largest near-term F1 movement.
- Stage 0.5 was already the highest-expected-value week in the plan; this makes it unambiguous.

**Negative / accepted costs**

- The rung ladder and much of ADR-003's framing no longer describe the work.
- `hybrid`'s dual-generator + adjudicator pattern — recorded in the ledger as "the right shape
  for rung 4" — is shelved with it. *(Deleted outright as of
  [[ADR-006 Removing the Three AI Comparison Methods]]; recoverable from git only.)*
- If the decision reverses, Stage 0f and 1b return with their full original cost. *(Under
  ADR-006, at more than that — the code they were to be built against is gone too.)*
