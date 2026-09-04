---
title: ADR-007 Re-scoping the Maturity Ladder
type: adr
tags: [adr, architecture, ai-architecture, scope, roadmap, evaluation, metrics]
status: accepted
date: 2026-08-07
supersedes: none
amends: ADR-003 AI Maturity Ladder
related: [ADR-003 AI Maturity Ladder, ADR-004 Deterministic-Only Scope, ADR-006 Removing the Three AI Comparison Methods]
---

# ADR-007 — Re-scope the rungs around the deterministic engine

**Status:** accepted · **Date:** 2026-08-07 · **Amends:** [[ADR-003 AI Maturity Ladder]]

Live status: [[00 - AI Maturity Status]] · Work: [[AI Maturity Ladder — Staged Plan]]

---

## Context

[[ADR-003 AI Maturity Ladder]] defined five rungs — pre-RAG → Basic RAG → Fine-Tuned RAG →
End-to-End Trainable → Agentic & Adaptive. Every rung above 0 was defined by an **LLM**
capability: retrieval feeding a model's context, then tuning that model, then an agent loop
around it.

Two later decisions removed the thing those rungs were about:

- [[ADR-004 Deterministic-Only Scope]] narrowed all work to the deterministic method, and
  recorded the consequence explicitly: *rung 1 is unreachable under this scope*, because
  retrieval feeds only the Gemini system prompt and the default method never sees it. It also
  said, in as many words, that **the rung metric therefore needs re-scoping or retiring — and
  that this was not yet decided.**
- [[ADR-006 Removing the Three AI Comparison Methods]] then **deleted** the three Gemini-backed
  methods, ~2,100 lines. There is now exactly one comparison method and it contains no LLM.

So the flag ADR-004 raised has been outstanding for two days across two ADRs, and the ledger has
been carrying `current_rung: 0` with `rung_evidence: none` while the ladder above it describes a
system that no longer exists. That is not a status; it is a measurement of a deleted design. A
rung metric that can only ever read 0 is worse than none, because it looks like a number.

## Decision

**Re-scope the rungs around what the deterministic engine can actually do and be measured on.**
Do not retire the metric, and do not reinstate an LLM path to make the old rungs reachable.

| Rung | Meaning | Evidence required to claim it |
| :--- | :--- | :--- |
| 0 | **Pre-measurement.** No metric exists. | — |
| 1 | **Measured.** Per-category precision/recall/F1 over **human-labelled** pairs. | A published baseline over ≥8 human pairs. Mutation-only does not count. |
| 2 | **Calibrated.** The tuning constants are measured optima, not hand-guesses. | Stage 0.5's exit criterion, on human pairs. |
| 3 | **Retrieval-augmented.** Stored human decisions measurably change engine output. | Learned-dismissal flywheel + learned overlay, measured on the Stage 0 harness. |
| 4 | **Learned matching.** A trained matcher beats the calibrated cascade. | Stage 3's exit criterion, on held-out human pairs. |

Rung 3 keeps the word **retrieval** and uses it honestly. Here it means retrieving **prior human
decisions** — `vault_sync.get_learned_dismissal_rules()` → the zone pools, and the learned
overlay — not retrieving context for a language model. That is a real retrieval-augmented system
by every definition except the one that assumes a transformer at the end of it, and unlike the
old rung 1 it gates output that users actually see today.

### What this explicitly does not do

- **It does not reinstate the deleted methods.** ADR-006 stands. Rung 4 no longer means "agent
  loop"; the dual-generator adjudicator pattern remains recoverable only from git, and that
  remains a recorded cost.
- **It does not claim a rung.** At the date of this ADR the corpus is 7/8 registered and
  **0/8 labelled**, so rung 1 has no evidence and is not claimed. Re-scoping makes the ladder
  *reachable*, not *reached*. Claiming otherwise would create exactly the phantom the ledger's
  evidence rule exists to prevent.

## Consequences

**The ordering inverts, and that is the point.** Under ADR-003 measurement was Stage 0 —
scaffolding before the real work. Under this ADR measurement *is* rung 1. The single thing
standing between this system and its first honest rung claim is annotation, which is
[[00 - AI Maturity Status]]'s "What's next" and has been for two days.

**One exit criterion is retired for good.** The old rung 1 required *retrieval recall@5 ≥ 0.7 on
held-out (finding → correct exemplar) pairs*. There are no exemplars and no consumer for them.
It is not deferred, it is gone; recorded here so nobody reconstructs it from ADR-003.

**Stage 1a survives and becomes rung 3's first increment**, which is what it always was in
substance — [[AI Maturity Ladder — Staged Plan]] already called it "the sole retrieval on the
deterministic path". Measured 2026-08-07: the live vault holds **two** learned patterns, one of
them the bare digit `8`, so the flywheel is real but nearly unexercised. Rung 3 is therefore
gated on **label volume**, the same binding constraint as rungs 1 and 2.

**The ladder is now monotone in one resource.** Rungs 1, 2, 3 and 4 are each gated on human
labels — 8 pairs, then calibration pairs, then dismissal volume, then held-out pairs. Under
ADR-003 the rungs were gated on four different things (retrieval, tuning, training, agency) and
so could be attempted out of order. They cannot be now, and the plan's stated worry about
climbing "in the order it was stated" dissolves.

## Alternatives rejected

| Alternative | Why not |
| :--- | :--- |
| **Retire the rung metric entirely** | Considered seriously, and it is the honest fallback if this re-scope drifts. Rejected because the ledger's one-line answer to "where are we" is load-bearing for exactly the cold-start agent sessions the kickoff prompt exists to serve. A stage board alone does not answer it. |
| **Reinstate an LLM comparison path so rung 1 becomes reachable as written** | Reverses ADR-006 two days after it landed, re-adds Gemini cost and non-determinism, and resurrects Stage 0f (cassettes) which was dropped for having nothing to record. It would also mean the roadmap dictating the product, rather than the reverse. |
| **Leave it undecided and keep doing engineering** | The status quo, and it has a measurable cost: the ledger reports rung 0 forever while claiming the ladder above it is the plan. The gap analysis already had to record one phantom in this vault; leaving a metric that cannot move is how the second one starts. |
| **Renumber so the current state is rung 1** | Rejected on the evidence rule. There is no baseline over human pairs, so there is nothing to point `rung_evidence` at, and a rung claim with no evidence link is defined in this vault as a defect. |

---

## Related

- [[ADR-003 AI Maturity Ladder]] — the rungs this amends
- [[ADR-004 Deterministic-Only Scope]] — raised the flag this closes
- [[ADR-006 Removing the Three AI Comparison Methods]] — made it permanent
- [[00 - AI Maturity Status]] — the ledger, where the rung is claimed
- [[Gotcha - A Short Structured Value Suppresses Its Own Zone]] — a false negative found while
  doing this work, and the class of defect rung 1 exists to make visible
