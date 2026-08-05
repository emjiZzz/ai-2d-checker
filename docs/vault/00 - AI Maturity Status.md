---
title: AI Maturity Status
type: status-ledger
tags: [status, ledger, agent-guide, roadmap, ai-architecture]
status: active
current_rung: 0
rung_evidence: none
date: 2026-08-05
verified-against: cache v37, no eval corpus yet
---

# 📊 AI Maturity Status — the living ledger

> [!IMPORTANT]
> **AI AGENT DIRECTIVE — this file is mandatory, in both directions.**
>
> **Before** any work on the comparison engines, retrieval, the learned model, or the AI pipeline:
> read this file to learn which rung the system is actually on. Do not infer it from code, from
> other notes, or from a method named `rag`.
>
> **After** landing anything: append a Work Log entry, tick the Stage Board, and rewrite **What's
> Next**. If a rung boundary was crossed, update `current_rung` **and** `rung_evidence` together —
> in the frontmatter above.
>
> **A rung claim with no `rung_evidence` link is a defect, not a status.** This rule exists because
> this vault has already produced one phantom: `CLAUDE.md` advertised "the four V2 gaps" for months,
> and [[00 - AI Agent Navigation & System Gap Analysis]] had to record that the phrase *"has no
> source in this vault — no such list was ever written down."* Do not create a second one.

Related: [[AI Maturity Ladder — Staged Plan]] (the work) · [[ADR-003 AI Maturity Ladder]] (the
decisions) · [[00 - AI Agent Navigation & System Gap Analysis]] (the gap this addresses).

---

## 🚀 Kickoff prompt — paste this to start a new agent session

`CLAUDE.md` auto-loads in Claude Code, so there **one line** is enough:

```
Read docs/vault/00 - AI Maturity Status.md before starting. <your task>
```

Every other agent starts cold — Antigravity, Cursor, ChatGPT, Gemini, or any tool that does not
auto-load `CLAUDE.md`. For those, paste this whole block:

```
Read these before doing anything, in order:
1. docs/vault/00 - AI Maturity Status.md   ← the ledger: current rung, stage board, next action
2. docs/vault/00 - Map of Content (MOC).md ← index
3. CLAUDE.md                                ← 5 hard constraints

Do not infer system state from code or from names. The default comparison method is
keyed `rag` and contains no retrieval and no LLM. The ledger is the only authority
on which rung the system is on.

Before writing code, check `06 - Gotchas & Debugging Lessons/` and `07 - ADRs/` for the
area you are touching — those are bugs already paid for and decisions already settled.
Do not re-litigate them.

When you finish, this is part of the work, not paperwork:
- append a Work Log entry to the ledger (state the measured effect, or state explicitly
  that it is unmeasured — never omit it)
- tick the Stage Board and rewrite "What's Next"
- if you crossed a rung boundary, update `current_rung` AND `rung_evidence` together
- record negative results too
- run: services/backend/.venv/Scripts/python.exe -m pytest tests/ -q

Task: <what you want done>
```

> [!NOTE] Why the prompt lives here and not in a notes app
> This file is the first thing the prompt tells the agent to read, so the prompt and its target
> travel together and cannot drift apart. If you change the closing ritual, change it here — the
> next session picks it up automatically.

---

## 🎯 The goal

```
rung 0          rung 1           rung 2              rung 3               rung 4
pre-RAG   →   Basic RAG   →   Fine-Tuned RAG   →  End-to-End Trainable → Agentic & Adaptive
  ▲
  └── we are here
```

---

## 📍 Current rung: **0 — pre-RAG**

`rung_evidence:` **none** — and under the rule above, that is exactly why the rung cannot be claimed
higher. There is no evaluation report in this repository, so no rung above 0 is assertable.

The system is **not on rung 1**. This is a measured statement about the code, not a judgement:

| Component | State |
| :--- | :--- |
| Default method `rag` | Contains **zero retrieval and zero LLM**. It is a pure deterministic spatial/text differ (`orchestrator.py:290`). The name is a misnomer baked into the DB (`Room.comparison_method`), cache filenames, the API and the UI. |
| Embeddings | **Fake.** `infrastructure/ai/embeddings/local_embedding_model.py` returns `SHA-256(text)`-seeded Gaussian noise, plus `+100.0` bumps on dims 0/100/200 for the English keywords `tolerance/hole`, `cable/rubber`, `column/wind` — words that do not occur in this Japanese CAD domain. The docstring claims SentenceTransformers/ONNX; `_load_model` assigns the *string* `"ONNX_Quantized_MiniLM"`. |
| Vector store | **Fake.** `lancedb_manager.py` is not LanceDB — one `index_shards.json` + a numpy loop. The store is empty. |
| Retrieval | `few_shot_retriever.py` = `find(client_name).sort("-created_at").limit(5)`. A recency filter with no query and no similarity. It feeds only the Gemini system prompt — which the default method never invokes. |
| Learned model | **Real and wired**, but **inert**: 21 verdict labels against `MIN_TRAIN = 40`, `metrics: {}`. Only exact-match overrides fire today. See [[Gotcha - Learned Corrections Model and Post-Cache Inference]]. |
| Evaluation | **None.** No corpus, no fixtures in-repo, no precision/recall/F1 anywhere. |
| Observability | **None.** `storage/ai-artifacts/{prompts,responses,embeddings}/` all exist and are all empty. |

### Why rung 0 is the honest reading

Rungs 1–4 are each defined by optimising against a metric. "Fine-tuned" needs a validation score,
"trainable" needs a loss, "adaptive" needs a signal. **None exist.** The gap analysis states it
plainly:

> *"Nothing has ever measured whether the engine catches the changes a human checker would flag…
> For an inspection tool that is the number that matters, and we do not have it."*

So the ladder cannot be climbed in the order it was stated. Stage 0 builds the measurement
substrate, and Stage 0.5 spends it on calibration before any retrieval work. See
[[AI Maturity Ladder — Staged Plan]].

### What is genuinely strong today

Not everything is a gap, and the plan is built on these:

- **Feedback capture.** `AuditFeedbackDocument` + the fixed-shape `FindingSnapshot`, seven
  correction verbs, flowing from `CorrectionControls.tsx`. Purpose-built for training.
- **A clean eval seam.** `generate_deterministic_candidates` (`orchestrator.py:290`) makes no DB
  call, no LLM call, across 960 lines. All impurity sits in the `:1253` wrapper. The whole pipeline
  can be run offline, in-process, at zero cost.
- **A proto-agentic pattern.** `hybrid_orchestrator.py`'s dual-generator + `crop_verifier.py`
  adjudicator is the right shape for rung 4 — it needs generalising, not replacing.
- **37 cache versions of hard-won fixes**, each documented. See the gotchas index in the MOC.

---

## 🧭 What's next

> **One action. Not a backlog.**

**Stage 0a — unblock and de-corrupt.** Three bugs actively poison measurement, so they land before
the harness that would measure them.

1. `full_ai_orchestrator.py:75` — `client_name = getattr(request, ...)` inside
   `generate_ai_vision_candidates`, whose signature at `:41` has **no `request` parameter**.
   NameError. With zero `hybrid` cache entries to mask it, **`hybrid` is 100% broken today.**
   Thread `client_name: str | None = None` through from `hybrid_orchestrator.py:159`.
2. `ai_engine.py:173` — hardcoded `model="gemini-2.0-flash"`, retired 2026-06-01 per `config.py:60`.
   Read `settings.GEMINI_MODEL_*`. Until fixed, the standards AI pass silently returns `[]`.
3. `CorrectionControls.tsx:89-91` — hardcodes `text_similarity`, `match_distance` and
   `is_numericish` to `null`. **Fix before collecting another label** — degraded labels cannot be
   retroactively repaired.

Prerequisite: land or revert the uncommitted working set first (`orchestrator.py`,
`cache_manager.py`, `full_ai_orchestrator.py`, `hybrid_orchestrator.py`, `feature_classifier.py`,
`audits.py`, plus 7 frontend files). **A baseline measured against uncommitted code is not a
baseline.**

---

## 📋 Stage board

Exit criteria are reproduced verbatim from [[AI Maturity Ladder — Staged Plan]] so "done" is never
a judgement call. Tick a box only when its criterion is *measured*, not when the code merely exists.

### Stage 0 — Measurement substrate → unlocks rung 1
- [ ] 0a — three poisoning bugs fixed; working set clean
- [ ] 0b — fixture corpus: ≥8 human-labelled pairs, 3 held out permanently
- [ ] 0c — mutation generator incl. `null_mutation` (the pure precision probe)
- [ ] 0d — scorer emitting per-category precision / **recall** / F1, handle-first matching
- [ ] 0e — `tools/eval.py` runner + CLI
- [ ] 0f — cassette + trace capture, wired only at `gemini_client.py`
- [ ] 0g — the 3 never-collected `services/backend/tests/` files relocated and passing
- [ ] 0h — `finding_classifier.joblib` moved out of the vault; vault docs git-tracked

> **Exit:** `tools/eval.py --method rag` prints per-category precision/recall/F1 over ≥8 human pairs
> and ≥30 mutation pairs, in <60 s, with **zero network calls**, green in CI. A published v37
> baseline exists for all 6 categories. `pytest tests/ -q` green including the 3 relocated tests.

### Stage 0.5 — Calibration
- [ ] `ComparisonParams` extracted; refactor proven **byte-identical** on the corpus
- [ ] Matching constants swept (coordinate descent, leave-one-pair-out CV)
- [ ] Zone constants swept separately, with "pinned templates still resolve" asserted
- [ ] `COMPARISON_CACHE_VERSION` bumped to v38; `rag` renamed `deterministic` with a compat alias

> **Exit:** measured-optimal values for ≥10 of 16 constants, each with a recorded held-out ΔF1 and
> stated confidence. Aggregate F1 ≥0.05 over the v37 baseline on held-out human pairs — **or a
> documented finding that the defaults were already near-optimal**, which is a legitimate result.

### Stage 1 — Real retrieval → **rung 1: Basic RAG**
- [ ] 1a — learned-dismissal patterns made structured (`exact` / `normalized` / `prefix`)
- [ ] 1b — `local_embedding_model.py` and `lancedb_manager.py` **deleted**
- [ ] 1b — `infrastructure/retrieval/` built, lexical-first (char n-gram TF-IDF + BM25)
- [ ] 1b — `few_shot_retriever` retrieves by **similarity to the current finding**
- [ ] `apply_learned_adjustments` called from `hybrid_orchestrator.py`

> **Exit:** retrieval recall@5 ≥ 0.7 on held-out (finding → correct exemplar) pairs, against a
> measured baseline for today's last-5-by-recency. End-to-end F1 for `rag_ai`/`hybrid` with
> retrieval on vs. off shows a **non-negative** delta.

### Stage 2 — Learned components → **rung 2: Fine-Tuned RAG**
- [ ] 2a — `LabelingQueue.tsx`, batch feedback endpoint, active learning by uncertainty
- [ ] 2a — **≥300 verdict labels, ≥150 category labels** (the binding constraint)
- [ ] 2b — learned feature classifier, evaluated independently of the verdict head
- [ ] 2c — reranker over lexical top-20

> **Exit:** ≥300 verdict labels. `verdict_cv_accuracy` present in `metrics` (currently `{}`) and
> ≥0.80, **and** the learned overlay produces a measured F1 gain on the held-out corpus — not just
> fit quality. Learned feature classifier beats rules on ≥4 feature types, or is documented as
> not-yet-worth-it.

### Stage 3 — Learned matcher → **rung 3: End-to-End Trainable**
- [ ] `learned_matcher.py` — pairwise scoring + assignment, trained on free mutation labels
- [ ] Learned overlay broadened from 3 to 6 categories
- [ ] Shipped behind `ComparisonParams.matcher`, defaulting to `threshold`

> **Exit:** learned matcher beats the Stage-0.5-calibrated cascade by ≥0.05 F1 on held-out **human**
> pairs (mutation pairs do not count — the matcher was trained on that distribution). Learned
> overlay active on ≥5 of 6 categories, each at or above its deterministic baseline.

### Stage 4 — Agent loop → **rung 4: Agentic & Adaptive**
- [ ] ⛔ **Blocked** on Catmull roadmap Phases 1–2 (entity model + `CadPoint` contract)
- [ ] `audit/agent/{tools,loop,budget}.py` — bounded loop over `EntityIndex`
- [ ] Tool-declaration schema guard (hard constraint 1 extends to function declarations)
- [ ] `ClientPolicy` — per-client thresholds and learned-model scope
- [ ] Explicit decision recorded: cache the agent trace, or accept always-cold runs

> **Exit:** agent loop resolves disputed `hybrid` findings with measured F1 above
> `crop_verifier.py`'s single-shot adjudication, at ≤2× token cost, within a stated p95 latency.
> Tool-schema guard test green. Per-client policy demonstrated on ≥2 clients with divergent
> measured thresholds.

---

## 📓 Work log

Append-only. Newest last. One entry per landed change. State the measured effect, or state
explicitly that it is unmeasured — **never omit it.**

| Date | What shipped | Stage | Measured effect | Cache |
| :--- | :--- | :--- | :--- | :--- |
| 2026-08-05 | Ladder planned; this ledger, [[AI Maturity Ladder — Staged Plan]], [[ADR-003 AI Maturity Ladder]] and [[Eval Corpus Annotation Guideline]] created. Rung recorded as 0 with no evidence, per the evidence rule. | — | n/a — documentation only | — |

---

## ⛔ Negative results

Ideas measured and rejected, so they are not re-implemented. Per `CLAUDE.md` constraint 4, a
rejected idea is worth as much as one that worked. Expected to fill up quickly — the Stage 0.5 sweep
will reject most candidate constants, and "the defaults were already near-optimal" is a legitimate
and valuable outcome.

| Idea | Verdict | Why |
| :--- | :--- | :--- |
| Replay evaluation over `storage/cache/` | **Rejected before implementation** (2026-08-05) | Of 36 cache files, every `gemini_comparison_*` is method `rag`, most are test placeholders, only 2 are real v37 entries, and there are **zero** `hybrid` / `rag_ai` / `ai_vision` entries. There is no LLM output in the repo to replay. Superseded by: call the pure `generate_deterministic_candidates` directly, and build a record/replay cassette for the LLM paths. |
| Contrastive fine-tuning of an embedding model on feedback | **Rejected for now** (2026-08-05) | Infeasible at 21 labels. The binding constraint at every rung is label count, not model class. Superseded by a reranker over the existing `FindingClassifier` machinery. Revisit above ~2000 labels. |
| Gemini supervised tuning | **Rejected for now** (2026-08-05) | Breaks offline capability, cannot ship in the Tauri bundle, needs Vertex-side infrastructure, and tunes to noise at ~300 examples. Decisively: **the default method contains no LLM at all.** Revisit only if `hybrid` becomes default *and* labels exceed ~2000. |
| Adding LanceDB / FAISS / Chroma / Qdrant | **Rejected** (2026-08-05) | At ≤100k short strings, brute-force numpy cosine is ~1 ms and *exact*. An ANN index buys nothing and costs a dependency, a build step and an accuracy approximation. `lancedb_manager.py` already had the right algorithm and the wrong name. |
| `sentence-transformers` for embeddings | **Rejected** (2026-08-05) | Pulls `torch` — ~2.5 GB into a Python sidecar shipped inside a Tauri bundle, to retrieve over ~2k short strings. If dense is ever needed, ONNX Runtime (~80 MB, no torch) is the path, and only on a measured win over lexical. |

---

## 🔒 Rules that constrain every stage

Restated here because this is the file agents are directed to read first.

1. **Never add open-ended shapes to `PhysicalComparisonResponse`** — it is Gemini's `response_schema`.
   At Stage 4 this **extends to tool/function declarations**, which reject open-ended objects the
   same way. See [[ADR-002 Decoupled Zone Bounding Box Endpoint]].
2. **Bump `COMPARISON_CACHE_VERSION`** when spatial matching or zone extraction changes. Stage 0.5
   and Stage 3 both trip this. See [[Gotcha - Comparison Cache Invalidation]].
3. **Only `08 - Client Domain & CAD Rules/` is a runtime input.** This ledger, the staged plan and
   the ADR are documentation and must never steer the engine.
4. **Record negative results**, in the table above.
5. **The learned model runs post-cache and is never cached** — retrains take effect immediately with
   no version bump. Do not "optimise" this away. See
   [[Gotcha - Learned Corrections Model and Post-Cache Inference]].
