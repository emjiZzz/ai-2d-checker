---
title: AI Maturity Ladder — Staged Plan
type: architecture
tags: [roadmap, ai-architecture, rag, evaluation, learning, agentic]
status: active
date: 2026-08-05
verified-against: cache v37, 4-drawing corpus, uncommitted working set
---

# 🪜 AI Maturity Ladder — Staged Plan

Live status, and the one thing to do next: [[00 - AI Maturity Status]].
Decisions and rejected alternatives: [[ADR-003 AI Maturity Ladder]].

---

## Why the stated order does not work

The goal is **Basic RAG → Fine-Tuned RAG → End-to-End Trainable → Agentic & Adaptive**. Two findings
reshape it:

**The system is not on rung one.** The default method `rag` contains no retrieval and no LLM; the
embeddings are SHA-256 noise; the vector store is a JSON file. See [[00 - AI Maturity Status]] for
the component-by-component reading.

**Every rung above zero is defined by optimising against a metric, and no metric exists.**
"Fine-tuned" needs a validation score, "trainable" needs a loss, "adaptive" needs a signal.
[[00 - AI Agent Navigation & System Gap Analysis]] states it directly:

> *"Nothing has ever measured whether the engine catches the changes a human checker would flag.
> There is no drawing pair with a known, deliberate change list to score against. For an inspection
> tool that is the number that matters, and we do not have it. Closing this gap needs ground truth,
> not more code."*

So the plan inserts **Stage 0 (measurement)** ahead of everything, and promotes threshold
calibration to **Stage 0.5** — ahead of all retrieval work. Calibrating 16 hand-guessed constants
against a real harness will move F1 more than any retrieval or model change, in a week, with zero
new dependencies.

### Two things verified during planning that drive the design

**The eval seam is free.** `generate_deterministic_candidates` (`orchestrator.py:290`) makes no
`.find()`, `.save()`, `insert_many` or Gemini call across its 960 lines — its only awaits are
progress callbacks and `extract_dynamic_regions_async`. All impurity lives in the thin
`perform_drawing_comparison` wrapper at `:1253`. **That pure function is the entire eval substrate:**
feed it serialized entities and stub drawing objects and the full pipeline runs offline, in-process,
in milliseconds, with no cache and no Mongo.

**Replay over the cache is dead on arrival.** `storage/cache/` holds 36 files; *every*
`gemini_comparison_*` is method `rag`, most are test placeholders
(`..._ref_dwg_id_rev_dwg_id_...`), only 2 are real v37 entries, and there are **zero**
`hybrid` / `rag_ai` / `ai_vision` entries. There is no LLM output in this repo to replay — a
record/replay cassette has to *create* that corpus. Recorded as a negative result in
[[00 - AI Maturity Status]].

---

## Stage 0 — Measurement substrate

*~2 weeks. Everything else is blocked on this. Adds no dependencies.*

> The status ledger is written **before** 0a, not after Stage 0 completes. A ledger written at the
> end of a stage is a changelog; written at the start it is what keeps the next session on track.

### 0a. Unblock and de-corrupt *(half a day, first)*

Land or revert the uncommitted working set first — **a baseline measured against uncommitted code is
not a baseline.** Then three bugs that actively poison measurement:

- `full_ai_orchestrator.py:75` — `getattr(request, "client_name", None)` in a function whose
  signature (`:41`) has no `request` parameter. NameError, and with zero `hybrid` cache entries to
  mask it, **`hybrid` is 100% broken today.** Thread `client_name` through from
  `hybrid_orchestrator.py:159`.
- `ai_engine.py:173` — hardcoded `gemini-2.0-flash`, retired 2026-06-01 per `config.py:60`. The
  standards AI pass silently returns `[]`.
- `CorrectionControls.tsx:89-91` — hardcodes three snapshot features to `null`. **Fix before
  collecting another label**; degraded labels cannot be retroactively repaired.

Delete `audits.py:372`'s `provider.embed_text(...)` rather than fixing it — the method does not
exist, the exception is swallowed, and it writes fake vectors into a fake store. Stage 1 replaces the
path.

### 0b. Fixture corpus

**Create** `services/backend/infrastructure/eval/{corpus,serialize}.py`. The differ only touches
`.entity_type`, `.layer`, `.handle`, `.properties`, `.geometry`, so duck-typed stubs suffice — no
Beanie needed.

**Confidentiality split.** Entity JSONL carries the customer's Japanese text — the same class as the
DXFs, which are already gitignored.

| | Location | Contents |
| :--- | :--- | :--- |
| Committed | `tests/fixtures/eval/` | `manifest.json` (pair ids, per-payload sha256, category counts) + hand-authored labels. Tiny, reviewable, diffable. |
| Gitignored | `storage/eval/pairs/` | The entity payloads. |

The runner asserts payload sha256 against the manifest and **fails loudly on drift**, making silent
fixture edits impossible.

Target **8–12 human-labelled real pairs**, with **3 held out permanently** and touched exactly once,
at the end of Stage 0.5.

**Write [[Eval Corpus Annotation Guideline]] first.** "Is this one finding or two?" is exactly what
`marking_reconciler.py` answers heuristically. A corpus labelled under a shifting definition is
worthless.

### 0c. Mutation generator

**Create** `eval/mutator.py` using `ezdxf` (already a dependency). Each operator emits a typed
`ExpectedFinding` carrying the handle it touched:

| Operator | Category |
| :--- | :--- |
| `retype_dimension_override` (`%%c120`→`%%c125`) | drawing_views |
| `edit_note_mtext` (truncate/extend a 注記 line) | notes_section |
| `delete_text` / `insert_text` | drawing_views, notes_section |
| `translate_block` (move a view) | drawing_views |
| `edit_bom_cell` / `add_bom_row` / `remove_bom_row` | bill_of_materials |
| `edit_title_attrib` (DWG No., JOB NO, 作成年月日) | title_block |
| `add_section_callout` (Ａ－Ａ + arrows) | other_engineering_references |
| **`null_mutation`** (re-save, no change) | **all — pure precision probe** |

`null_mutation` is the highest-value operator: ground truth is *zero findings*, so every finding
produced is a measured false positive. That alone yields a precision number in week one.

Build **both** levels — DXF-level (round-trips through `oda_converter`/`dxf_parser`, so it also
exercises extraction, where the Shift-JIS and DIMENSION bugs of cache v14/v36 lived) for ~30
realistic pairs, and entity-level for fast sweep iterations.

### 0d. Scorer

**Create** `eval/scorer.py`. The hard part is matching a *predicted* finding to an *expected* one.
**Do not write a third differ** — reuse `reconciler.py`'s spatial NN logic, but make `entity_handle`
the primary key with spatial+text as fallback (`entity_index.py` already namespaces `REF-`/`REV-`).
Handle-first matching is what keeps the scorer robust while Stage 0.5 moves coordinates around.

Emit per-category and micro/macro: **precision, recall, F1** (recall has never existed); a
**status-confusion matrix** (found-but-labelled-ADDED-instead-of-CHANGED is a downgrade, not a
miss); **category-attribution accuracy** (independent of detection — where zone regressions surface);
**duplicate rate** (the v13/v16 bug class); and **null-pair false-positive count**.

Print counts alongside every rate. At 8–12 pairs every conclusion carries wide error bars — say so
in the output, not in a comment.

### 0e. Runner + CLI

**Create** `eval/runner.py` and `tools/eval.py`. The runner calls
`generate_deterministic_candidates` **directly** — not `perform_drawing_comparison`, not the cache.

```bash
services/backend/.venv/Scripts/python.exe tools/eval.py --corpus storage/eval --method rag --json out.json
```

### 0f. Cassette + trace capture

**Wire both at exactly one place: `gemini_client.py`.** Decorators over `execute_gemini_cascade`
(`:71`) and `execute_title_block_ocr` (`:123`) — both sync, both called via `asyncio.to_thread`, a
clean single choke point. Do not scatter instrumentation across the four orchestrators.

- `eval/cassette.py` — key on `sha256(system_instruction + contents + model)`. Modes `record` /
  `replay` (**raise on miss; never silently fall through to a live call in CI**) / `passthrough`.
- `infrastructure/observability/trace.py` — fills the empty `storage/ai-artifacts/{prompts,responses}/`.
  One JSONL record per call: `trace_id`, `session_id`, `method`, `model`, prompt sha + text, response,
  `usage_metadata` token counts, latency, retry/fallback chain, estimated cost. Per-finding
  provenance keys off the `origin` field `ComparisonCandidate` already carries.

The 7 existing `title_block_ocr_v1` cache files keep the current corpus fully offline.

### 0g. Fix `services/backend/tests/`

Three files there have **never executed** — they sit outside `pyproject.toml`'s `testpaths` and fail
collection with `ModuleNotFoundError`. This is why Pillars 2 and 4 are unverified.

**Do not add the directory to `testpaths`.** Import styles are incompatible: root tests use
`services.backend.infrastructure...`, these use `infrastructure...`. Making both resolve creates
**two distinct module objects per backend module**, so `LearnedModelHolder` singletons and
`config.MIN_TRAIN` monkeypatches would apply to only one copy — silent, maddening cross-talk.

Instead rewrite the 3 files to `services.backend.*` imports and move them into root `tests/`.
~20 lines of churn. Expect failures; they have never run.

Related: `vault_sync.py` reads a gitignored, machine-local directory at runtime, which makes those
tests environment-dependent. Give `VaultSyncManager` an injectable path pointed at
`tests/fixtures/vault/`.

### 0h. Move the model artifact out of the vault

`finding_classifier.joblib` lives in `09 - Learned Models/`, which `.gitignore:77` excludes. **A
model that cannot be committed, diffed, or shipped is not trainable infrastructure** — this blocks
rung 3 outright.

New resolution order in `learning/config.py` + `model_holder.py`: `LEARNED_MODEL_DIR` env →
`services/backend/storage/models/` (gitignored payload, committed `.meta.json`) → vault path as a
deprecated fallback. `Model Card.md` keeps writing to the vault — that is the human surface. The
`.joblib` is a build artifact.

Then un-ignore the vault's documentation folders, keeping `08 - Client Domain & CAD Rules/` ignored:
it holds customer-specific Japanese anchors and is the only runtime input.

### Exit criterion

> `tools/eval.py --method rag` prints per-category precision/recall/F1 over ≥8 human pairs and ≥30
> mutation pairs, in <60 s, with **zero network calls**, green in CI. A published v37 baseline exists
> for all 6 categories. `pytest tests/ -q` green including the 3 relocated backend tests.

### Risks

- **The scorer's matcher is itself a differ and can be wrong.** Hand-audit its decisions on 2 pairs
  before trusting any aggregate.
- **Labelling is harder than it looks** — mitigated by writing the guideline first.
- **8–12 pairs is a small sample.** Every downstream conclusion inherits that.

---

## Stage 0.5 — Calibration

*~1 week. This is where F1 actually moves. Adds no dependencies.*

Sixteen module-level constants, every one a hand-guess. The gap analysis is explicit: *"Every
heuristic constant is a judgement call… None are measured optima."* The marking reconciler's
fuzzy-pass guards were *"calibrated against one observed case."*

```
spatial_differ.py:32-40,66   STRICT/TWIN/FUZZY_RADIUS_NORM .005/.010/.150 (+3 _ABS twins),
                             CHANGED_SIMILARITY_FLOOR 0.40
reconciler.py:20             MATCH_RADIUS_MM 35.0
marking_reconciler.py:74-77  SIMILARITY_THRESHOLD .82, AMBIGUITY_MARGIN .08,
                             MIN_FUZZY_LENGTH 4, MAX_NORMALIZED_MOVE .25
bom/zone_detector.py:185-270 CLUSTER_RADIUS 200, MIN_ISO_ELLIPSES 3, ISO_BLOCK_DOMINANCE .6,
                             ISO_CLUSTER_RADIUS_FRACTION .15, BBOX_PADDING 30,
                             GRID_LABEL_MARGIN_FRACTION .09
coordinate_resolver.py:17    LABEL_PROXIMITY_TOLERANCE_MM 3.0
bom/anchors.py:27            _CHAR_WIDTH_RATIO 0.6
```

**Create** `comparison/params.py` — a frozen `ComparisonParams` with `DEFAULT_PARAMS` reproducing
today's values byte-for-byte. Thread it through `generate_deterministic_candidates`. **Assert
byte-identical corpus output before and after the refactor** — it must be provably behaviour-neutral
or the sweep measures the refactor, not the thresholds.

**Create** `eval/sweep.py` — **coordinate descent, not grid** (16 dims of grid is nonsense at this
corpus size). One parameter at a time over a declared range, leave-one-pair-out CV, accept only on a
held-out win with ΔF1 > 0.03.

### Two traps

**Tier the sweep.** Matching constants are safe. **Zone constants are not** — they feed
`safe_filter`, zone templates and `views_exclusions()`, and users have hand-pinned templates. Moving
`BBOX_PADDING`/`CLUSTER_RADIUS` can silently invalidate them. Separate pass, with an explicit
"pinned templates still resolve" assertion. See [[Gotcha - Global Default Zone Template & the Aspect Caveat]].

**Overfitting is the default outcome, not a risk.** Coarse-sweep on mutation pairs, validate on human
pairs, touch the 3 permanently-held-out pairs exactly once, at the end.

### Ship discipline

New constants change spatial matching → **bump `COMPARISON_CACHE_VERSION` to v38** with a `# v38:`
note, per the existing 37-bump convention. See [[Gotcha - Comparison Cache Invalidation]].

**Rename `rag` → `deterministic` here**, at the cache bump, where everything is invalidated anyway.
The key lives in the DB (`Room.comparison_method`), cache filenames, the API and the UI, and
`drawings.py` substring-matches those filenames — this is the one safe moment. Keep a compat alias in
the dispatcher for one release.

### Exit criterion

> Measured-optimal values for ≥10 of 16 constants, each with a recorded held-out ΔF1 and stated
> confidence. Aggregate F1 ≥0.05 over the v37 baseline on held-out human pairs — **or a documented
> finding that the defaults were already near-optimal**, which is a legitimate and valuable result.

---

## Stage 1 — Real retrieval → rung 1

*~1.5 weeks. Zero new dependencies under the lexical-first decision.*

### 1a. Fix the retrieval that actually gates output today

`vault_sync.get_learned_dismissals()` → `safe_filter` (`orchestrator.py:783-808`) is the **only**
retrieval on the default path. It matches exactly, never as substring, and learned patterns include
`"1"` and `"2A0"`. Exact-matching `"1"` is simultaneously useless (misses `"1."`, `"１"`) and
dangerous.

Make patterns structured — `{pattern, match_mode: exact|normalized|prefix, min_length,
category_scope}` — with `auto_doc.py` emitting `normalized` (NFKC + `SpatialDiffer._normalize_text`)
for patterns ≥3 chars and `exact` below. This is a suppression rule, so it trades recall for
precision: **measure it on the Stage 0 harness.**

### 1b. Replace the fake stack

**Delete** `ai/embeddings/local_embedding_model.py` and `ai/vectorstore/lancedb_manager.py`. Audit
`ai/reasoning/drawing_similarity_engine.py` and `ai/knowledge_graph/graph_builder.py` — if they
consume the fake embeddings they are also measuring noise. Read `tests/test_phase8_vector_memory.py`
first; it probably asserts the fake behaviour.

**Create** `infrastructure/retrieval/`:
- `store.py` — numpy brute-force over `.npy` + JSONL sidecar. `lancedb_manager.py` had the right
  algorithm and the wrong name; keep the algorithm, fix the name and the persistence format.
- `lexical.py` — `TfidfVectorizer(analyzer="char_wb", ngram_range=(2,4))` + BM25. sklearn is already
  a dependency, and this mirrors `FindingClassifier`'s `HashingVectorizer(char_wb,2-4)` — the one
  component in the system that demonstrably works.
- `encoder.py` — pluggable interface; lexical is the default, dense sits behind it for later.
- `index_builder.py` — two collections: `feedback_exemplars` (from `AuditFeedbackDocument`) and
  `domain_rules` (from `08 - Client Domain & CAD Rules/*.md`, chunked by heading).

**Rewrite** `few_shot_retriever.py`: client becomes a **filter**, similarity becomes the **ranking**,
and the query is the current finding's text. Keep `format_exemplars_for_system_instruction`'s output
contract so `prompt_builder.py:136-143` needs no change.

**Also:** call `apply_learned_adjustments` from `hybrid_orchestrator.py`. It never does, so every
human correction is invisible on the method we are steering toward.

### Impact honesty

Retrieval feeds only the Gemini system prompt → `rag_ai` and `hybrid`'s generator B. **The default
method never sees it.** A perfect retriever changes nothing users observe until `hybrid` becomes the
default. 1a ships value now; 1b ships value when `hybrid` does.

### Exit criterion

> Retrieval recall@5 ≥ 0.7 on held-out (finding → correct exemplar) pairs, against a measured
> baseline for today's last-5-by-recency. End-to-end F1 for `rag_ai`/`hybrid` with retrieval on vs.
> off shows a **non-negative** delta.

### Risk

**Retrieval can hurt.** Injecting five near-miss exemplars as authoritative prose ("Do NOT report X
as a discrepancy") into a system prompt is a recall attack — the exact failure mode the gap analysis
names. The Stage 0 harness is the gate. Without it you would ship a precision gain and a silent
recall loss.

---

## Stage 2 — Learned components → rung 2

*~2 weeks. Gated on label count, not on engineering. Zero new dependencies.*

The model is inert at 21/40 labels. Every model here is starved. **The binding deliverable is
labels, not architecture.**

- **2a — label throughput, first.** `LabelingQueue.tsx`: keyboard-driven batch labelling (j/k
  navigate, d dismiss, c confirm, 1-6 recategorise). Today labelling means opening a session and
  clicking through a popover per finding. Add a batch feedback endpoint — `POST /audits/feedback`
  currently kicks a full retrain over the whole table **per call**. Plus **active learning**: rank
  unlabelled findings by `|p_true − 0.5|` and surface the most uncertain first (~30 lines on top of
  `inference.py`'s existing `proba` call). Target **300+ verdict, 150+ category** labels.
- **2b — learned feature classifier.** `feature_classifier.py` is pure regex; its own docstring
  admits four feature types "have no signal at all", and `classify_iso_feature` always returns
  `other`. **Watch the feedback loop:** `feature` is an *input* to the verdict model, so a learned
  head feeding a verdict head trained on rule-labelled data compounds errors. Train and evaluate it
  independently; keep rules as prior/fallback; accept per-feature-type on measured accuracy.
- **2c — reranker, not a fine-tuned encoder.** Retrieve top-20 lexically, rerank with a
  `FindingClassifier` over `(query ⊕ candidate)` features, using dismissed-vs-confirmed as the label.
  Zero new dependencies. If it doesn't beat lexical-only, that is a real answer: retrieval isn't the
  bottleneck.

### Exit criterion

> ≥300 verdict labels. `verdict_cv_accuracy` present in `metrics` (currently `{}`) and ≥0.80, **and**
> the learned overlay produces a measured F1 gain on the held-out corpus — not just fit quality.

### Risks

- **The 21-label wall is a human-time problem; no engineering removes it.** If labels do not
  materialise, say so early rather than building models that cannot train.
- **`_cv_accuracy` is fit quality, not audit quality.** Never let the metric that already exists
  become the acceptance metric.
- Learning is global by explicit design ([[Gotcha - Learned Corrections Model and Post-Cache Inference]]:
  *"Revisit per-client scoping if it bites"*). At 300 labels across clients it will bite. Add
  `client_name` as a **feature** first — cheap, no policy change — before splitting the models.

---

## Stage 3 — Learned matcher → rung 3

*~3 weeks. Only start if Stage 0.5 showed the cascade near its ceiling.*

Stage 0.5 already delivered measured optima for the constants. What remains is replacing the cascade
itself.

**Create** `comparison/learned_matcher.py`. Reframe ref↔rev matching as **pairwise scoring**: for
each candidate pair within a generous radius, score `P(same entity)`, then solve the assignment
(Hungarian via `scipy.optimize.linear_sum_assignment`, already present via sklearn). Features are all
already computed — text similarity, spatial distance, type/layer/zone match, numeric delta, char
n-grams.

**Training labels are free.** The Stage 0 mutator knows the true correspondence *by construction*:
every non-mutated entity is a positive pair, every other combination a negative. This is the one rung
with effectively unlimited supervision, and the reason it is feasible at all.

**Broaden the learned overlay from 3 to 6 categories.** The restriction exists because `title_block`
and `bill_of_materials` are table-derived with a different feature shape, and
`inference.py:_recompute_spatial_categories` (79-105) only regenerates marking tables — it needs a
table-aware branch. Gate each category on its own measured F1.

**Ship behind a flag**: `ComparisonParams.matcher: "threshold" | "learned"`, defaulting to
`threshold`. Flipping the default is another cache bump.

### Exit criterion

> Learned matcher beats the calibrated cascade by ≥0.05 F1 on held-out **human** pairs — mutation
> pairs do not count, the matcher was trained on that distribution. Learned overlay active on ≥5 of 6
> categories, each at or above its deterministic baseline.

### Risks

- **Mutation-distribution overfit.** Synthetic mutations are cleaner than real revisions — no
  re-layout, no re-lettering, no drafter drift. The human held-out set is the only honest gate.
- **Latency.** Pairwise scoring is O(n·m) within a radius; blocking by zone (already computed) is the
  mitigation.
- `hallucination_guardrails.py` and `apply_deterministic_overrides` assume threshold semantics —
  audit both before swapping.

---

## Stage 4 — Agentic & adaptive → rung 4

*~3 weeks. Hard-blocked on Catmull roadmap Phases 1–2. This is the convergence point.*

`entity_index.py` exists and its `query()` surface is the right shape, but `entity_handle()` still
falls back to `properties["handle"]` — Phase 1's handle promotion is only partly landed. **The
Catmull roadmap's Phase 4 is Stage 4's prerequisite, not a parallel track.**

Generalize `hybrid_orchestrator.py`'s dual-generator + `crop_verifier.py` adjudicator — **do not
replace the generators.** They are cheap, parallel and deterministic-ish. The agent loop replaces
only the adjudication of *disputed* findings, where the LLM already runs and per-call cost is already
accepted.

**Create** `infrastructure/audit/agent/`:
- `tools.py` — `query_entities` (over `EntityIndex.query`), `crop_region` (reuse `crop_verifier.py`'s
  tiling), `read_zone` (reuse `zone_detector.py`), `lookup_standard` (Stage 1's store),
  `compare_values`.
- `loop.py` — bounded: max 6 tool calls, max 2 rounds, hard wall-clock timeout, mandatory terminal
  "state your verdict" turn.
- `budget.py` — per-audit token/cost ceiling read from the Stage 0 trace layer.

### Two constraints to design around

**Hard constraint 1 extends to tool declarations.** Gemini's function-declaration parameter schemas
reject open-ended objects the same way `response_schema` does. Every tool parameter must be a flat
typed field — no `filters: dict`. Extend
`tests/test_zone_overlay_endpoint.py::test_llm_response_schema_has_no_open_ended_objects` to walk
tool declarations too. See [[ADR-002 Decoupled Zone Bounding Box Endpoint]].

**Latency.** N sequential round-trips per disputed finding, against a product where cached audits
return in 0.14 s. Opt-in per session, streamed via the existing `progress_callback` plumbing,
hard-capped.

### Adaptive

`ClientPolicy` (thresholds, suppression rules, learned-model scope) resolved by `client_name`,
defaulting to global. `learning/config.py` becomes the global default rather than the only config.
Active learning already shipped in 2a.

### Exit criterion

> Agent loop resolves disputed `hybrid` findings with measured F1 above `crop_verifier.py`'s
> single-shot adjudication, at ≤2× token cost, within a stated p95 latency. Tool-schema guard green.
> Per-client policy demonstrated on ≥2 clients with divergent measured thresholds.

### Risks

- **Tool loops are where cost explodes silently.** The Stage 0 trace layer is the only reason this is
  safe to attempt.
- **Non-determinism breaks the cache model.** An agent loop cannot be keyed by `(ref, rev, method)`.
  Either cache the *trace* and replay it, or accept agentic runs are always cold — **decide
  explicitly and record it.**
- **Debuggability regression.** Today a wrong finding traces to a line of Python; after Stage 4 it
  traces to a tool-call sequence. The trace layer is what prevents this being a net loss.

---

## Dependency budget

| Stage | New dependencies |
| :--- | :--- |
| 0 | none — `ezdxf`, `sklearn`, `numpy` all present |
| 0.5 | none |
| 1 | none (lexical). `onnxruntime` + `tokenizers` (~80 MB) only on a measured win |
| 2 | none |
| 3 | `scipy` — already present via sklearn |
| 4 | none |

**Rung 3 is reachable without adding a single dependency**, which for a Tauri app shipping a Python
sidecar is worth protecting.

---

## Definition of Done — every stage, not just Stage 0

No exit criterion is met until the ledger entry is written:

- [ ] Code landed, tests pass
- [ ] Measured effect recorded — **or explicitly recorded as unmeasured; never omitted**
- [ ] Work-log entry appended to [[00 - AI Maturity Status]]
- [ ] Stage board reflects reality
- [ ] `current_rung` + `rung_evidence` updated **together** if a boundary was crossed
- [ ] Any new gotcha written under `06 - Gotchas & Debugging Lessons/` and linked from the MOC,
      **including negative results**
