---
title: ADR-006 Removing the Three AI Comparison Methods
type: adr
tags: [adr, architecture, ai-architecture, scope, comparison-engine, deletion]
status: accepted
date: 2026-08-07
supersedes: none
amends: ADR-004 Deterministic-Only Scope
related: [ADR-003 AI Maturity Ladder, ADR-004 Deterministic-Only Scope]
---

# ADR-006 — Delete `rag_ai`, `ai_vision` and `hybrid`

**Status:** accepted · **Date:** 2026-08-07 · **Amends:** [[ADR-004 Deterministic-Only Scope]]

Live status: [[00 - AI Maturity Status]] · Work: [[AI Maturity Ladder — Staged Plan]]

---

## Context

[[ADR-004 Deterministic-Only Scope]] shelved the three Gemini-backed comparison methods and
then listed, verbatim, **what it was not deciding**:

> - Whether to delete the three methods' code (12 backend files reference them). Leaving them
>   in place costs nothing while they are DEV-badged and unmeasured; deleting is reversible
>   only from git.
> - Whether the picker should still show them.

This ADR answers both. It is not a re-litigation of ADR-004 — it is the deferred half of it.

The user's decision, in their words: *"Since we only focus on RAG and its method, can we
remove other 3 methods completely both backend and frontend?"* — with the ladder's own
framing that agentic behaviour remains the eventual goal, but that the system is on rung 0 and
should be worked on there.

## Decision

**Delete them, in both tiers.** `comparison_method` narrows to `Literal["rag"]`; the
COMPARISON ENGINE picker is removed from the Create Room dialog entirely rather than reduced
to one button, because a chooser with one option is not a choice.

### Removed

| File | Lines | Served |
| :--- | ---: | :--- |
| `comparison/full_ai_orchestrator.py` | 303 | `rag_ai`, `ai_vision` |
| `comparison/live_dxf_orchestrator.py` | 382 | `ai_vision` |
| `comparison/hybrid_orchestrator.py` | 516 | `hybrid` |
| `comparison/crop_verifier.py` | 231 | `hybrid`'s adjudicator |
| `comparison/full_ai/` (4 files) | 657 | prompts, parsing, persistence |
| `comparison/reconciler.py` | 168 | `hybrid`'s cross-generator matcher |
| `comparison/few_shot_retriever.py` | — | fed only the Gemini system prompt |
| `tests/test_hybrid_pipeline.py`, `test_live_dxf_ai_pipeline.py`, `test_few_shot_retriever.py` | — | the above |

Plus: the `_dispatch_comparison` routing table, the `hybrid_candidates_*` cache lever
(`CANDIDATE_CACHE_VERSION` and its read/write pair), the four-button picker and three room
badges, and the per-method stage sequences and timeout budgets in `comparisonStages.ts`.

### Deliberately NOT removed

These are the traps. A grep-and-delete pass takes all four.

- **`gemini_client.py`.** The deterministic path calls `execute_title_block_ocr` from it, and
  so do `summarization_pipeline.py` and the ADR-002 zone-bbox endpoint. **"Remove the AI
  methods" is not "remove Gemini"** — `rag` has a live Gemini dependency for OCR, which is
  also why an eval run on a cache-cold pair is not network-free.
- **`image_cropper.py`.** Used directly by `orchestrator.py`, not only by the crop verifier.
- **`renderMode: 'hybrid' | 'vector' | 'raster'`** in `reviewStore.ts` / `renderEntities.ts`.
  An unrelated name collision — this is the canvas rendering mode. Deleting it breaks the 2D
  canvas and has nothing to do with the comparison method.
- **The `CONFLICT` / `unverified` statuses** in `candidate.py` and `renderEntities.ts`. Only
  `hybrid` ever produced them, so they are unreachable — but they are written into cached
  comparison payloads, and a reader that no longer knows the key renders an old audit wrong
  rather than not at all.

## The finding that outlived the removal

`match_radius_mm` was one of the 16 tuning constants in `ComparisonParams`, swept by Stage
0.5, and it lived in `reconciler.py` as the hybrid cross-generator radius. Deleting the
reconciler left it with exactly one reader: **the eval scorer's spatial fallback tier.**

That exposed something the shared import had been hiding. **The constant tunes the
measurement, not the engine.** It decides which prediction the scorer pairs with which
expected finding, so sweeping it moves F1 with no engine behaviour changing at all — the same
class of error the ledger already records under *"Sweeping on detection F1 alone — rejected,
measured wrong"*. It had been sitting in the sweep's range table the whole time, described as
"included so the sweep can *show* it is inert".

It now lives in `eval/scorer.py` as `SPATIAL_MATCH_RADIUS_MM`, at its original value so scores
are byte-identical, and is pinned out of `_BINDINGS` by
`test_the_scorer_radius_is_not_a_sweepable_engine_constant`. **The default sweep pass is
13 constants, not 14.**

The general shape, worth more than the specific fix: **a constant shared between the thing
being measured and the thing doing the measuring is a defect that only becomes visible when
one of them is deleted.**

## Consequences

**Positive**

- ~2,100 lines and 12 files of unmeasured, DEV-badged, never-defaulted code gone. `hybrid` in
  particular *could not complete a single run* until 2026-08-05 (a `NameError`), so its entire
  history is code that never worked being kept in case it was wanted.
- One method means no routing table, one cache lever instead of two, and one stage sequence.
- The Create Room dialog loses a DEV-badged control that offered users three engines the
  project had already decided not to develop or measure.

**Negative / accepted costs**

- `hybrid_orchestrator.py`'s dual-generator + `crop_verifier.py` adjudicator is recorded in
  the ledger as *"the right shape for rung 4 — it needs generalising, not replacing"*, and
  **rung 4 remains the stated end goal.** It is now recoverable only from git. Find it with:
  `git log --diff-filter=D -- services/backend/infrastructure/audit/comparison/hybrid_orchestrator.py`
- Stages 0f and 1b, already dropped by ADR-004, now return at *more* than their original cost
  if the scope reverses: the code they were to be built against is gone too.
- `few_shot_retriever.py` is gone, so ADR-004's "1b — real retrieval store" would start from
  nothing. 1a is unaffected: `vault_sync.get_learned_dismissals()` → `safe_filter` is a
  different mechanism and remains the only retrieval on the deterministic path.

## Data

No migration. Measured before deciding, against the live database rather than assumed:
**108 rooms, of which 8 are live and all 8 are `rag`.** All 48 rooms carrying `rag_ai` (18),
`ai_vision` (18) or `hybrid` (12) were already soft-deleted, and `list_rooms` filters
`is_deleted == False` **in the Mongo query**, so a tombstone is never fetched and never
validated against the narrowed `Literal`.

The 48 tombstones are left as they are, on the user's instruction — the deletion history is
worth more than a uniform field. One residual, recorded rather than fixed: `get_room` loads by
id and *then* checks `is_deleted`, so a direct GET on a tombstone's id now raises a validation
error instead of a clean 404. Reachable only by something still holding a deleted room's id.

**No cache bump.** Nothing on the deterministic path changed — no spatial matching, no zone
extraction, no scoring. `COMPARISON_CACHE_VERSION` stays at v42, leaving v43 free for Stage
0.5 as the ledger intends. Any `hybrid_candidates_*.json` still in `storage/cache/` is
orphaned; nothing reads it and nothing deletes it.

## See also

- [[ADR-004 Deterministic-Only Scope]] — the decision this completes
- [[00 - AI Maturity Status]] — the ledger; Stage 4's "shelved, not deleted" note is now false
  and has been corrected there
