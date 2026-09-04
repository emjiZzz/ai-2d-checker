---
title: Gotcha - Learned Corrections Model and Post-Cache Inference
type: gotcha
tags: [gotcha, debugging, learning, hitl, orchestrator, cache]
status: resolved
date: 2026-07-31
---

# 🧠 Gotcha — The Learned-Corrections Model Runs POST-Cache (and Never Gets Cached)

## Context
The `rag` comparison is deterministic and noisy — near-identical drawings scored ~31%
matched. We added a **human-in-the-loop learned-correction layer**: every engineer correction
(dismiss, flip verdict CHANGED↔MATCHED, confirm a change, reclassify, correct a value) becomes
a labeled example on `AuditFeedbackDocument`; a small scikit-learn `LogisticRegression`
(`infrastructure/learning/`) trains on them and adjusts findings at comparison time. No LLM.

## ⚠️ The three things that will bite you

### 1. The model is applied AFTER the cache, and its output is NEVER cached.
`perform_drawing_comparison` still caches the **pre-model** deterministic
`PhysicalComparisonResponse` under `COMPARISON_CACHE_VERSION`. `apply_learned_adjustments`
runs on the way out, on **both** the cache-hit and fresh-compute paths
(`orchestrator.py`). Consequences you must preserve:
- A **retrain takes effect immediately** for every drawing pair, including already-cached
  ones, with **no `COMPARISON_CACHE_VERSION` bump**. Do not "optimize" by caching the adjusted
  result — that would freeze one model version into the cache and silently defeat learning.
- Because we did not touch matching/zone logic, the existing cache stays valid. If you *do*
  change the deterministic differ, bump the version as usual (see
  [[Gotcha - Comparison Cache Invalidation]]).

### 2. Learning is deliberately scoped to the three SPATIAL categories in v1.
Only `drawing_views` / `notes_section` / `isometric_view` are model-adjusted, because their
checklist content is a marking table we regenerate with `build_marking_table` so the rows AND
the Completion Parity stay consistent with the canvas badges. `title_block` / `bill_of_materials`
verdicts are table-derived with a different feature shape and are left to the deterministic
logic — their corrections are still *captured* for training, just not applied yet. If you widen
this, you must also regenerate those categories' content, not only their status.

### 3. Precedence: exact human override > model > abstain.
A finding the human corrected *exactly* (same normalized text + category) is forced
deterministically (confidence 1.0) — one correction takes effect immediately on that exact
item. The model only **generalizes** to unseen findings, and only once
`n_verdict ≥ LEARNING_MIN_TRAIN` (default 40) with both classes present; below that it
**abstains** and the deterministic verdict stands. This is the honest cold-start behavior:
**expect no visible change until a few dozen corrections exist** (the Settings → Active Learning
panel shows "warming up N/40"). Promotion (MATCHED→CHANGED) sits behind a high threshold; it is
riskier than suppression.

## Storage — everything lives in the vault
The model (`finding_classifier.joblib`), its meta, and the human-readable `Model Card.md` live
under `docs/vault/09 - Learned Models/`, resolved via `VaultSyncManager.get_instance().vault_path`
(the same path `AutoDocEngine` uses for `08 - Client Domain & CAD Rules`). Note the whole
`docs/vault/` tree is **gitignored**, so the binary never enters git — the earlier worry about
"binary churn in git history" was moot. The `.joblib` is a compiled index; the corrections in
MongoDB are the source of truth and can rebuild it anytime via `POST /audits/learning/retrain`.

## Scope decision recorded (negative-result discipline)
Learning is **global** by explicit user choice — a correction generalizes across all clients.
One client's convention can therefore silence another's; confidence gating + exact-match
precedence mitigate but don't eliminate this. Revisit per-client scoping if it bites.

## Related
- [[Gotcha - Comparison Cache Invalidation]] — the four caches and when to bump versions.
- [[Gotcha - Reference and Revision in Different Coordinate Spaces]] — the deterministic noise this layer learns to suppress.
