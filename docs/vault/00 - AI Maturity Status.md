---
title: AI Maturity Status
type: status-ledger
tags: [status, ledger, agent-guide, roadmap, ai-architecture]
status: active
current_rung: 0
rung_evidence: none
date: 2026-08-05
verified-against: cache v38, no eval corpus yet
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
| Learned model | **Real and wired**, but **inert**: 21 verdict labels against `MIN_TRAIN = 40`, `metrics: {}`. Only exact-match overrides fire today. The 21 labels are **sound**, not degraded — see the 2026-08-05 Stage 0a work-log entry. See [[Gotcha - Learned Corrections Model and Post-Cache Inference]]. |
| Evaluation | **Substrate exists as of 2026-08-05; ground truth does not.** `tools/eval.py` prints per-category precision/recall/F1 over 36 mutation pairs in ~16 s, offline, with a published v38 baseline. But **0 human-labelled pairs**, and after the 2026-08-05 rebuild the corpus covers **one drawing family**, so per-category figures are a property of that sheet rather than of the client. Nothing yet measures what a checker would flag. |
| Observability | **None.** `storage/ai-artifacts/{prompts,responses,embeddings}/` all exist and are all empty. |

Corrected 2026-08-05, from running the pipeline offline for the first time: the eval **seam** is
real and now demonstrated — 3 pairs, 0.77 s, zero non-local sockets — but two of the plan's
assumptions about it were wrong. `generate_deterministic_candidates` reads a **sixth** entity
attribute (`.id`, via `detect_balloons`), and it is **not** network-free: title-block OCR calls
Gemini on a cache miss. Both are guarded in `infrastructure/eval/`; neither changes the rung.

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

> [!IMPORTANT] Scope changed 2026-08-05 — [[ADR-004 Deterministic-Only Scope]]
> All work now targets the **deterministic method only**. `RAG + AI`, `AI Vision` and `HYBRID`
> are neither developed nor measured. Stages **0f, 1b and 4 are dropped**; **0.5 is promoted**
> to the highest-value work in the plan. Rung 1 ("Basic RAG") is **unreachable** under this
> scope — retrieval feeds only the Gemini system prompt, which the default method never sees.
> The rung metric therefore needs re-scoping or retiring; that is **not yet decided**.

**Stage 0b's labels. Nothing else is the bottleneck any more.**

Stages 0a–0e, 0g and 0h are done and the harness works: `tools/eval.py` prints per-category
precision/recall/F1 over 36 mutation pairs in ~16 s with zero network calls, and there is a
published v38 baseline. What that harness cannot do is judge itself. **Every number in the
baseline is mutation-only, and since the 2026-08-05 rebuild they all come from one drawing
family** — so a per-category figure describes that sheet, not this client. Mutation pairs have
three further stated blind spots:

- they are drawn from the engine's own comparison pool, so they **cannot reveal a scoping
  bug** — and that is a live bug class here ([[Gotcha - A Naive Mutator Manufactures Recall Misses]]);
- their category attribution is **not independent** of `zone_detector`, so the 0.90 attribution
  accuracy is partly circular;
- they cannot gate Stage 3's learned matcher, which is trained on that distribution.

So `recall 0.65` is a real number about synthetic edits on one sheet, and **not yet the number
the gap analysis asked for** — "whether the engine catches the changes a human checker would
flag". Closing that is annotation, not engineering.

**Two things are needed, in this order:**

1. **Five more drawing pairs.** Only three exist on this machine — M745200N01, M7452A0N01,
   M7452A1N01, all `reference` ↔ `FSRS2_kmti`, all already exported and integrity-checked.
   Add more with:

   ```
   tools/eval_corpus.py export --pair-id <ID> --ref <file_name|_id> --rev <file_name|_id>
   ```

   > **None of the existing three can be a held-out pair.** Engine output on all three has
   > already been inspected — they have cache entries. The guideline requires held-out pairs be
   > chosen *before* anyone looks at engine output on them, so **all 3 held-out pairs must come
   > from the new ones, and must be designated at export time**, with `--held-out`, before the
   > engine is ever run on them.

2. **Label all 8.** For each pair: `tools/eval_corpus.py worksheet --pair-id <ID>` writes a
   neutral annotation aid (a naive high-recall text inventory — deliberately *not* engine
   output, so the engine's own misses stay visible) plus an empty label draft. Fill the draft in
   against [[Eval Corpus Annotation Guideline]], then
   `tools/eval_corpus.py label --pair-id <ID> --from <draft>`. The loader rejects invented
   categories, bad statuses, malformed addresses and stale guideline versions, so a filled draft
   that installs is a well-formed one.

**Three decisions are waiting on the first two annotated pairs** — the guideline's own open
questions (title-block rows, revision-table rows, amendment markers, and what counts as "bulk").
It is `status: draft` until they are resolved, and resolving them later means re-labelling.

**One decision is waiting on nothing**, and the baseline is already affected by it:
[[Gotcha - Zone Templates Vanish in Offline Eval]] — either thread resolved zone overrides into
`extract_dynamic_regions_async`, or declare templates out of scope and assert it. The v38
baseline was measured **without** this machine's seven hand-aligned zones, which is not what
users see. Not choosing produces a number everyone trusts and nobody can reproduce.

### Unblocked engineering, under the deterministic-only scope

**0.5a and 0.5b are both done — and 0.5b measured why the rest of Stage 0.5 cannot proceed.**
`ComparisonParams` is extracted and proven byte-identical; `tools/sweep.py` works. The sweep
then found that **13 of 14 constants are not merely unmeasured on this corpus but unmeasurable
on it**: mutation pairs put both sides at identical coordinates (253/253 entities), so every
spatial and relocation constant is trivially satisfied and never reaches a decision. The one
human pair shares **0 of 11** coordinates, because a real revision here is a re-trace.

That upgrades the case for human pairs from methodological to mechanical. It is no longer "a
mutation-only sweep would overfit"; it is "a mutation-only sweep has nothing to measure." See
[[Gotcha - Mutation Pairs Cannot Exercise a Spatial Constant]].

Then, in rough order of what the baseline says is worth attacking:

- **`notes_section` is the weakest category — P 0.47 / R 0.54** on the rebuilt corpus.
- **A single-character deletion goes unreported** (confirmed by the scorer hand-audit: `G`
  removed from the notes zone produced no finding). Prime suspect:
  `marking_reconciler.MIN_FUZZY_LENGTH = 4` — and it is one of the 16 constants, so 0.5 may
  resolve it for free.
- **BOM row granularity.** The engine reports one edited row as five cell-level findings,
  against a guideline that says one row is one finding — four false positives per edited row,
  by construction. Not a threshold; a semantics fix.
- **`other_engineering_references` has no coverage** — no mutation operator targets it, because
  section callouts are deliberately suppressed (`DROP_SECTION_CALLOUT_LABELS`, cache v38), so
  such a pair would be a guaranteed recall miss *by design*. Now measurable, once someone
  decides which way that trade should go.
- **Rename `rag` → `deterministic`.** [[ADR-004 Deterministic-Only Scope]] makes this necessary
  rather than tidy: the sole method under development is named after a technique it does not
  contain. Do it at Stage 0.5's cache bump, the one moment everything is invalidated anyway.

None of that changes the headline: **the sweep itself must not run on a mutation-only corpus.**
Coordinate descent over 16 constants, validated against pairs drawn from the engine's own
comparison pool, would fit the constants to the mutator — and since the 2026-08-05 rebuild the
corpus is one drawing family, which makes that worse, not better.

---

## 📋 Stage board

Exit criteria are reproduced verbatim from [[AI Maturity Ladder — Staged Plan]] so "done" is never
a judgement call. Tick a box only when its criterion is *measured*, not when the code merely exists.

### Stage 0 — Measurement substrate → unlocks rung 1
- [x] 0a — poisoning bugs fixed; working set clean *(2026-08-05 — 2 of the 3 were real; the third
      was not a defect. See the work log.)*
- [ ] 0b — fixture corpus: ≥8 human-labelled pairs, 3 held out permanently
      *(2026-08-05 — **infrastructure done, corpus not**. Format, loader, drift detection,
      held-out lock and CLI landed and tested; the offline seam is demonstrated end to end.
      **1 / 8 pairs registered, 0 / 8 labelled, 0 / 3 held out** — down from 3 after the
      2026-08-05 rebuild, which lost two pairs whose source DXFs and OCR readings were both
      deleted. Run `tools/eval_corpus.py status` for the live count — it reads the manifest,
      so it cannot go stale the way this line can.)*
- [x] 0c — mutation generator incl. `null_mutation` (the pure precision probe)
      *(2026-08-05 — 8 operators, 36 pairs from 2 bases, 11 of them zero-finding. Measured:
      **0 false positives across all 11 zero-finding pairs.** `tools/eval_corpus.py status`
      for the live count.)*
- [x] 0d — scorer emitting per-category precision / **recall** / F1, handle-first matching
      *(2026-08-05 — hand-audited on 2 pairs per the plan's risk note; the audit found and
      fixed two scorer bugs before any aggregate was believed. Handle-first applies to 18 of
      52 matches; the rest fall back to text, which the report states rather than hides.)*
- [x] 0e — `tools/eval.py` runner + CLI
      *(2026-08-05 — 54 pairs in 19 s, zero non-local sockets **enforced** by patching
      `socket.connect`. Baseline published at `tests/fixtures/eval/baseline-v38.json`.)*
- [x] ~~0f — cassette + trace capture, wired only at `gemini_client.py`~~ **DROPPED**
      *(2026-08-05 — [[ADR-004 Deterministic-Only Scope]]. It exists solely to make the Gemini
      paths replayable; with none in scope it buys nothing. `tools/eval.py` already refuses
      non-deterministic methods rather than making a paid call. Returns at full cost if the
      scope decision reverses.)*
- [x] 0g — the 3 never-collected `services/backend/tests/` files relocated and passing
      *(2026-08-05 — rewritten to `services.backend.*` imports and moved into root `tests/`;
      the old directory is gone, so the two import styles can never coexist. **They all
      passed on first execution**, against the plan's expectation of failures — recorded as
      a negative result below. Two of the three originals asserted against the **real**
      gitignored vault; rewritten against an injected path.)*
- [x] 0h — `finding_classifier.joblib` moved out of the vault; ~~vault docs git-tracked~~
      *(2026-08-05 — reads resolve `LEARNED_MODEL_DIR` → `services/backend/storage/models/`
      → vault (deprecated); writes never touch the vault, so an existing install keeps
      working and migrates itself on its next retrain. `.joblib` gitignored, `.meta.json`
      **committed**. `Model Card.md` stays in the vault — it is documentation, not a build
      artifact.)*

> **Exit:** `tools/eval.py --method rag` prints per-category precision/recall/F1 over ≥8 human pairs
> and ≥30 mutation pairs, in <60 s, with **zero network calls**, green in CI. A published v38
> baseline exists for all 6 categories. `pytest tests/ -q` green including the 3 relocated tests.

### Stage 0.5 — Calibration
- [x] `ComparisonParams` extracted; refactor proven **byte-identical** on the corpus
      *(2026-08-05 — `comparison/params.py`, 20 constants across 6 modules, each module now
      deriving from `DEFAULT_PARAMS`. Proven: engine output identical to the committed v38
      baseline. `sweep_override()` is the override mechanism — module-global rebinding,
      **single-threaded offline use only**, restored in a `finally`. Threading a params
      object through the call tree was deliberately deferred; the reason is in the module
      docstring.)*
- [ ] Matching constants swept (coordinate descent, leave-one-pair-out CV)
      *(⛔ **blocked, and harder than "needs a better corpus"** — 2026-08-05: measured, **13 of
      14 constants cannot be exercised at all** by mutation pairs, because both sides share one
      coordinate system exactly. The sweep machinery exists and works (`tools/sweep.py`); it has
      nothing to measure until human pairs land. See
      [[Gotcha - Mutation Pairs Cannot Exercise a Spatial Constant]].)*
- [ ] Zone constants swept separately, with "pinned templates still resolve" asserted
      *(machinery ready behind `--include-zone`; the pinned-template assertion is not written)*
- [ ] `COMPARISON_CACHE_VERSION` bumped (**v42** — v38 through v41 were all spent on
      2026-08-05); `rag` renamed
      `deterministic` with a compat alias

> **Exit:** measured-optimal values for ≥10 of 16 constants, each with a recorded held-out ΔF1 and
> stated confidence. Aggregate F1 ≥0.05 over the v38 baseline on held-out human pairs — **or a
> documented finding that the defaults were already near-optimal**, which is a legitimate result.

### Stage 1 — ~~Real retrieval → rung 1: Basic RAG~~ **mostly dropped**

*[[ADR-004 Deterministic-Only Scope]]: rung 1 is unreachable under this scope. Retrieval feeds
only the Gemini system prompt, which the default method never sees, so 1b changes nothing users
observe. Only 1a survives — it is the sole retrieval on the deterministic path and gates real
output today.*

- [ ] 1a — learned-dismissal patterns made structured (`exact` / `normalized` / `prefix`)
- [x] ~~1b — `local_embedding_model.py` and `lancedb_manager.py` deleted~~ **DROPPED**
- [x] ~~1b — `infrastructure/retrieval/` built, lexical-first~~ **DROPPED**
- [x] ~~1b — `few_shot_retriever` retrieves by similarity~~ **DROPPED**
- [x] ~~`apply_learned_adjustments` called from `hybrid_orchestrator.py`~~ **DROPPED** *(hybrid
      is out of scope; the learned overlay already runs on the deterministic path)*

> **Exit (1a only):** the suppression rule trades recall for precision, so its effect is
> measured on the Stage 0 harness rather than assumed. The original retrieval-recall@5 exit
> criterion is retired with 1b.

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

### Stage 4 — ~~Agent loop → rung 4: Agentic & Adaptive~~ **DROPPED**

*[[ADR-004 Deterministic-Only Scope]]: the loop exists to adjudicate disputed `hybrid` findings,
and `hybrid` is out of scope. `hybrid_orchestrator.py`'s dual-generator + `crop_verifier.py`
adjudicator — recorded above as "the right shape for rung 4" — is shelved with it, not deleted.*

- [x] ~~`audit/agent/{tools,loop,budget}.py`, tool-schema guard, `ClientPolicy`, trace-caching
      decision~~ **DROPPED** *(returns at full cost if the scope decision reverses; it was also
      hard-blocked on Catmull roadmap Phases 1–2 regardless)*

> **Exit:** retired with the stage. `ClientPolicy` is the one piece with standalone value on the
> deterministic path (per-client thresholds), and can be reclaimed into Stage 0.5 if wanted.

---

## 📓 Work log

Append-only. Newest last. One entry per landed change. State the measured effect, or state
explicitly that it is unmeasured — **never omit it.**

| Date | What shipped | Stage | Measured effect | Cache |
| :--- | :--- | :--- | :--- | :--- |
| 2026-08-05 | Ladder planned; this ledger, [[AI Maturity Ladder — Staged Plan]], [[ADR-003 AI Maturity Ladder]] and [[Eval Corpus Annotation Guideline]] created. Rung recorded as 0 with no evidence, per the evidence rule. | — | n/a — documentation only | — |
| 2026-08-05 | **Working set landed** (`ce9fd5c`), clearing the Stage 0a prerequisite. SSE progress streaming for all four comparison methods; section designations (`Ａ－Ａ`) and their cut-arrow labels classified as `additional_views` and then suppressed from the checklist behind `DROP_SECTION_CALLOUT_LABELS`; `docs/vault/` git-tracked for the first time (46 notes previously existed on one machine), with client-domain rules and the model bundle carved out. Four defects in the working set were fixed before landing: three docstrings demoted to dead string literals by callback insertions, deleted Phase-7 cache rationale restored, an SSE task with no strong reference (GC could hang the stream), and an error-boundary keyed on connection status that remounted every child on any blip. | 0a (prereq) | **Unmeasured** — no corpus exists yet, which is the point of Stage 0b. The section-callout change removes 3 findings from the M7452A1N01 pair by construction; whether that is a precision gain or a recall loss is exactly what cannot be stated today. | **v37 → v38**, candidates v2 → v3 |
| 2026-08-05 | **Stage 0a complete.** (1) `generate_ai_vision_candidates` took `client_name` as a parameter instead of reading it off a `request` that was never in scope — that NameError made `hybrid` 100% non-functional, unmasked by any cache. (2) The standards pass in `ai_engine.py` reads `settings.GEMINI_MODEL_PRO` with a fallback instead of the retired `gemini-2.0-flash`, and now names the failing model in the log rather than swallowing the error into an empty violations list. (3) **Item 3 was not a defect** — see the correction below. Pinned by `tests/test_stage_0a_measurement_unblocking.py` (7 tests). | 0a | **Unmeasured for (1) and (2)** — both paths need a live Gemini key, and no `hybrid`/`rag_ai` fixture exists. What *is* established: `hybrid` could not previously complete a single run, so any measurement of it before today would have been a measurement of a NameError. (3) is measured in the sense that the equality it rests on is asserted by test. | — |
| 2026-08-05 | **Stage 0b — corpus infrastructure landed; the pairs and the labels are not.** `infrastructure/eval/{serialize,corpus}.py` + `tools/eval_corpus.py` + `tests/test_eval_corpus.py` (30 tests). Committed `tests/fixtures/eval/manifest.json`, gitignored payloads under `storage/eval/pairs/`. Three enforcements that the guideline previously left to discipline are now code: payload sha256 checked on every load and **refusing to run** on drift; held-out pairs excluded by default, unlockable only with a written reason that is appended to an access log; label files carrying the guideline version they were authored under, rejected on mismatch. **The eval seam is demonstrated, not asserted** — see the measured column. Three defects/divergences found by running it, all recorded: the plan's "the differ touches five entity attributes" was off by one (`detect_balloons` reads `.id`); [[Gotcha - Exploded Block Children Have No Handle]]; [[Gotcha - Zone Templates Vanish in Offline Eval]]. | 0b (partial) | **Measured, and it is the first number this project has:** `generate_deterministic_candidates` runs over 3 real pairs in **0.77 s total**, in-process, with **zero non-local sockets** (asserted by patching `socket.connect`), producing 50 / 29 / 29 candidates. That is throughput and offline-ness, **not accuracy** — there are still no labels, so no precision, recall or F1 exists and rung 0 stands. Also measured: handle coverage on the reference sheets is 0.8–13%, over 3615 entities. | — (no engine behaviour changed) |
| 2026-08-05 | **Stage 0c complete — 54 mutation pairs, and the first precision number.** `infrastructure/eval/mutator.py` + `tools/eval_corpus.py mutate` + `tests/test_eval_mutator.py` (18 tests). Eight operators, three of which are designed to emit **no** finding: `null_mutation` (re-save), `restyle_dimension_text` (`%%c120` → `120`, measurement untouched — a transcoding, not a change) and `translate_entities` (relocation with identical text). Generated labels are deterministic from a seed, so the manifest commits the *recipe* rather than 54 files of customer drawing text. Two mutator defects found and fixed before any number was trusted — see [[Gotcha - A Naive Mutator Manufactures Recall Misses]]. | 0c | **Measured. 23 zero-finding pairs → 0 findings reported. Precision on the pure precision probe is 1.00** (n=23, wide error bars, one client's sheets). Separately: across the 31 pairs carrying injected changes, **76 findings expected, 61 reported** — 17 of 31 pairs report fewer than were injected. That is a *count* comparison, **not recall**: nothing has matched a reported finding to an expected one yet, so a pair could report two wrong findings while missing two real ones. Quantifying it is exactly Stage 0d. | — |
| 2026-08-05 | **Stage 0d + 0e complete — precision, recall and F1 exist.** `infrastructure/eval/{scorer,runner}.py` + `tools/eval.py` + `tests/test_eval_scorer.py` (10 tests). Handle-first matching with text then spatial fallback, category a *preference* rather than a filter; status-confusion matrix, category attribution scored independently, duplicate rate, null-pair false positives, and **counts printed beside every rate**. The runner calls `generate_deterministic_candidates` directly — never the cache — and patches `socket.connect` to raise on any non-local address, so "zero network calls" is enforced rather than claimed. Published baseline: `tests/fixtures/eval/baseline-v38.json`. **The scorer was hand-audited on 2 pairs before any aggregate was believed, as the plan requires, and that audit found two scorer bugs** — see the measured column. | 0d, 0e | **Measured. First precision/recall/F1 in this project's history**, over 54 mutation pairs, 76 expected findings, in **19 s with zero non-local sockets**: **precision 0.85 (52/61), recall 0.68 (52/76), F1 0.76, macro F1 0.78**; **0 false positives across 23 zero-finding pairs**; category attribution 0.90 (47/52). Weakest category `bill_of_materials` (P 0.56 / R 0.50), strongest `title_block` (P 1.00 / R 0.92). **Mutation-only** — no human pairs are labelled, so this cannot settle scoping or category attribution, and 33 of 52 matches came from the text tier rather than handles. Two scorer bugs caught by the hand-audit and fixed first: a cross-category text collision (`Ａ` NFKC-folds to `a`) that got precision *and* recall wrong in opposite directions on one pair, and a proximity-based duplicate rule that forgave over-reporting whenever a candidate happened to carry coordinates. | — |
| 2026-08-05 | **Stage 0g + 0h complete.** 0g: the 3 files in `services/backend/tests/` that had never executed are rewritten to `services.backend.*` imports and moved into root `tests/`; the old directory is deleted, so the two incompatible import styles can never coexist and produce two module objects per backend module. 0h: the learned bundle resolves `LEARNED_MODEL_DIR` → `services/backend/storage/models/` → vault (deprecated, read-only). Writes never touch the vault, so an install that trained earlier keeps working and migrates itself on its next retrain — no script, no window where the model is missing. `.joblib` gitignored, `.meta.json` committed. | 0g, 0h | **Measured, and it contradicts the plan: all 10 relocated tests passed on first execution.** The plan said "expect failures; they have never run." Recorded as a negative result. Two of the three originals were *environment-dependent* rather than broken — they asserted Japanese keywords against the real, gitignored vault, so they would have failed in CI for a reason unrelated to the code; both now use an injected path. 0h is measured in that `test_learned_model_location.py` (9 tests) pins the resolution order, and the live holder still loads the existing bundle through the deprecated fallback. **One defect introduced and fixed in the same session** — see the note below the table. | — |
| 2026-08-05 | **Corpus rebuilt on one drawing family, and the corpus now owns its OCR reading.** A routine cleanup in the app (delete old comparisons, re-ingest a drawing) removed 7 of 9 drawings and **all six title-block OCR readings the corpus depended on**. The payloads survived — they are independent copies — but the readings lived only in `storage/cache/`, outside the sha256-pinned corpus. Fixed: each reading is captured into the pair as `{side}.ocr.json`, hashed as `ocr_sha256`, and restored into the cache before every run. Recovery rule recorded: the reading is a function of the **file**, not the ingestion, so a `file_hash` lookup recovers it across a re-upload. Two of the three human pairs were unrecoverable (source DXFs also gone); the corpus was rebuilt around M7452A0N01 on the user's instruction. See [[Gotcha - The Corpus Borrowed Its OCR From a Volatile Cache]]. | 0b, 0c | **Measured, and the fix is verified the hard way: every OCR cache entry was deleted and the score came back byte-identical.** Before the fix that same action silently changed the title-extraction regime on one side only. **The baseline moved because the corpus shrank, not because the engine changed**: 36 pairs from 2 bases (was 54 from 6), 55 expected findings (was 76) — precision **0.78** (36/46), recall **0.65** (36/55), F1 **0.71**, macro F1 0.75, 0 false positives across 11 zero-finding pairs. `notes_section` fell hardest (F1 0.81 → 0.50) and `bill_of_materials` rose (0.53 → 0.71); with one sheet layout instead of three, per-category figures are now a property of this drawing, not of the client. | — |
| 2026-08-05 | **Scope narrowed to the deterministic method only** — [[ADR-004 Deterministic-Only Scope]]. `RAG + AI`, `AI Vision` and `HYBRID` are neither developed nor measured until the decision is revisited. Stages **0f, 1b and 4 dropped**; **0.5 promoted** to the highest-value work; 1a, 2 and 3 survive with the learned matcher becoming the end-goal. Recorded as an ADR because ADR-003 sequenced work assuming the opposite. | scope | **n/a — no code changed.** The consequence is structural, not measured: **rung 1 ("Basic RAG") is unreachable under this scope**, because the plan states that retrieval feeds only the Gemini system prompt and "the default method never sees it". The rung metric therefore needs re-scoping or retiring — flagged, not decided. Two follow-ons: the `rag` misnomer goes from tidy-up to necessary (the sole method under development is named after a technique it does not contain), and 12 backend files still reference the shelved methods — left in place, since they are DEV-badged and cost nothing while unmeasured. | — |
| 2026-08-05 | **Stage 0.5a — `ComparisonParams` extracted.** `comparison/params.py` collects all 20 tuning constants from `spatial_differ`, `reconciler`, `marking_reconciler`, `zone_detector`, `coordinate_resolver` and `bom/anchors` into one frozen object; each module now derives its constant from `DEFAULT_PARAMS` instead of declaring a literal. `sweep_override()` rebinds them for a scoped block — **single-threaded offline use only**, documented as such, restored in a `finally`. Zone constants are separated into `ZONE_PARAMS` because they feed `safe_filter` and hand-pinned templates and need their own pass. `tests/test_comparison_params.py` (23 tests). | 0.5a | **Measured: engine output is identical to the committed v38 baseline** — precision 0.78, recall 0.65, F1 0.71, per-category and match-tier breakdowns all unchanged. That equality is the point of the stage: the sweep that follows compares runs against each other, so a refactor that moved anything would be measured as a threshold effect. Also verified end-to-end that an override *reaches* the engine — the first attempt at that test passed vacuously on a zero-finding probe pair, which would have meant a sweep reporting every parameter as irrelevant. | — (values unchanged, so no bump) |
| 2026-08-05 | **Stage 0.5b — sensitivity sweep built and run.** `infrastructure/eval/sweep.py` + `tools/sweep.py` + `tests/test_eval_sweep.py` (9 tests). Coordinate descent, one constant at a time, over declared per-parameter ranges. Framed as **sensitivity, not calibration** — the report says so in its own output and `apply_best()` deliberately does not exist, pinned by a test, because one click applying 'optimal' values found on synthetic edits to a single sheet would undo what Stage 0 exists to establish. | 0.5b | **Measured, and the headline result is a limit on the corpus rather than on the engine: only 1 of 14 constants moves anything.** Baseline F1 0.713 / exactness 0.722 over 36 pairs, 865 s. `changed_similarity_floor` spread 0.139 — **entirely in exactness, 0.000 in F1**. The other 13 are flat, and the reason is mechanical and now verified: mutation pairs are a drawing and a copy of it, so **253 of 253 comparable entities sit at identical coordinates** (the human pair: 0 of 11). Distance is exactly zero, every radius matches on the first tier, and `reconcile_relocated_markings` never engages. See [[Gotcha - Mutation Pairs Cannot Exercise a Spatial Constant]]. **The first run measured F1 only and reported 14 of 14 flat** — a clean, confident falsehood, caught because a passing test proved the same override did change engine output. | — |
| 2026-08-05 | **Correction UI reworded, and a new class of feedback added.** The menu asked the same question two ways depending on the engine's own verdict (`isMatched ? "Actually a change" : "Confirm real change"`), so a reviewer had to decode that verdict before describing what they saw. Buttons now state an observation about the drawings; the wire verb is chosen underneath, so **no schema migration and the 21 existing labels are untouched**. Added `mispaired_missing_counterpart` / `mispaired_wrong_match` — the first feedback that judges the **matcher** rather than a finding's verdict, prompted by a real 'NONE → 260' card where the engine had failed to pair an entity that does have a counterpart. Captured, deliberately **not** mapped to a verdict label (`trainer.MATCHER_FEEDBACK`): label 0 would suppress a finding that may be genuine, label 1 would affirm a pairing the human just rejected. `tests/test_matcher_feedback.py` (6 tests) + `CorrectionControls.test.tsx` (6). | 2a (partial) | **Unmeasured, and it cannot be measured yet** — the learned model is inert at 21 of 40 labels, and these new verbs train nothing until the Stage 3 matcher exists. What is established by test: the verbs reach the corpus, produce no verdict label, and do not disturb the existing ones. Also fixed a documentation defect found in passing — `schemas.py` called `confirmed_valid` label 0 while `trainer.py` puts it in `VERDICT_ONE`; the prose agreed with the trainer, so the parenthetical was wrong. | — |
| 2026-08-05 | **Two UI bugs reported live, both fixed.** (1) A title-upper-left column produced **two cards for one unchanged value** — `コードNO. 230→NONE` and `PART NO. NONE→230`, both MATCHED. A recurrence of [[Gotcha - Title Upper-Left Double-Reported by Scale]]: its shared-token fix cannot pair fields when the two drawings keep **different halves** of a bilingual header. Added `_TITLE_UL_SYNONYMS`, tried only after the literal match fails. (2) Clicking a checklist card selected a different finding's marker: row→violation resolution was a per-row `violations.find(...)` with **no record of what had already been claimed**, so several rows resolved to the same marker, first-match-wins, and substring matching let a loose match on an early row steal the marker an exact match later needed. Now two passes — exact before substring — with each violation claimed once. | — (product defects) | **Measured: the eval corpus scores identically to the v38 baseline**, so the title fix is inert on pairs that do not exhibit the split — what a surgical fix should look like. The two frontend regression tests were **verified to fail against the old logic** before being kept; a regression test that passes either way proves nothing. `tests/test_title_ul_bilingual_pairing.py` (11) + `ChecklistPanel.test.tsx` (+2). **Both rows read MATCHED, not REMOVED/ADDED** — the bilateral corroboration guard masking the pairing failure rather than fixing it, which is the signature to watch for next time. | **v38 → v39** |
| 2026-08-05 | **A correction can be taken back.** The teach-the-model menu was one-way: by the time the card showed "Taught: …" the correction was persisted and had already kicked a retrain. `POST /audits/feedback/{id}/retract` sets `retracted_at` rather than deleting — the collection is the training corpus **and** the record of who taught the model what — and `build_bundle` skips retracted rows entirely. Idempotent, so a retry after a dropped response is not a 404. Deliberately does **not** rewrite a learned dismissal rule `AutoDocEngine` may already have written into the vault; those are human-editable notes. | 2a (partial) | **Unmeasured** — the verdict head is still inert. What is established by test: a retracted correction contributes **nothing**, not even to `n_total`. The obvious cheaper design was rejected on a measured basis rather than taste: a compensating `confirmed_valid` record does win the exact-match override (docs are sorted by `created_at`), but classifier rows are appended per document, so an undone correction would leave **two rows with identical features and opposite labels** — 2 verdict rows vs 0. At 33 of 40 labels that is expensive noise. Pinned by `test_a_compensating_record_was_not_the_chosen_design`. | — |
| 2026-08-05 | **A third duplicate card, from a different mechanism — and the eval cannot see any of them.** One physical cell (`16組`) produced **two MATCHED cards against one canvas marker**: `QTY (QUANTITY)` and `T. Q'TY / 総製作個数`. Unlike the v39 defect this one is **cross-extractor**: the bottom title block's QTY field searches for `T. Q'ty` / `総製作個数`, which *are* the upper-left table's own column header, and `keep_for_title_extraction` excluded only the tolerance box — so the proximity search reached from the title block (ends y≈299) up to the UL label at y≈702 and read the other table's cell. Fixed by excluding `title_upper_left` from title extraction exactly as `tolerance` already was, keeping the "unless also in the title box" guard so an over-wide box cannot blank the title block. See [[Gotcha - Title Block QTY Reads the Upper-Left Table]]. `tests/test_title_input_filter.py` (+4). | — (product defect) | **Measured, and the split between what was and was not measured is the point.** The eval scores **byte-identical to the v38 baseline** over 36 pairs (P 0.78 / R 0.65 / F1 0.713, macro 0.750, attribution 0.806) — real evidence of **no regression**, and **no evidence at all** about the duplicate. `runner.py` drops every `status == "MATCHED"` candidate before scoring, and both duplicate cards were MATCHED, so the scorer's `duplicates: 0` read zero *while the bug was live*. **All three duplicate-row defects to date (v13/v16, v39, v40) were invisible to it by construction** — do not cite that counter as coverage. The fix was verified at candidate level instead: 28 → 27 candidates, the removed one an exact twin of the survivor at the *same coordinates* `[75.25, 273.0]`. Field-level: QTY only, `'4'` → `'NONE'`, both sides; the other 15 title fields byte-identical. | **v39 → v40** |
| 2026-08-05 | **Four checklist items collapsed to one drawing number.** The bottom title block's DWG No. cell is ruled into sub-cells that spell out the number — `M745203N01` is `M745` (Machine Type) + `203` (Unit Code) + `N01` (Part No.) — and each had its own checklist row, all three reading `NONE` on the live pair while the DWG No. carried the value. Suppressed via `COMPONENT_OF_DWG_NO_FIELDS` + `is_component_of_dwg_no` in `utils/text.py`, imported by `marking_builder` rather than restated so the cards and the table cannot disagree; the DWG No. card label drops its five-name sub-header list. See [[Gotcha - Drawing Number Segments Reported as Separate Fields]]. `tests/test_dwg_no_component_rows.py` (18). | — (product defect) | **Measured: eval byte-identical to the v38 baseline again** (P 0.78 / R 0.65 / F1 0.713), which as with v40 is evidence of no regression and — these rows being `MATCHED` — *no* evidence about the noise reduction. Checklist verified directly: **11 rows → 8**, upper-left rows untouched. **Two deliberate non-simplifications, both of which would have been silent losses.** (1) Corroboration is *checked*: the live revision reads `DWG NO: NONE`, so unconditional suppression would leave a changed segment reported by nothing. (2) Matching is *positional*: the first implementation used `value in dwg_no` and **its own test caught that `45` sits inside `M745`203N01 without being a segment** — the same failure that once shipped a green tick in [[Gotcha - Title Field Read Across a Ruled Cell Boundary]]. Also pinned the name collision that makes this class dangerous: the **upper-left** table's `Unit No.`/`Part No.` are standalone fields, and its `Part No.` genuinely reads `203`, so aiming this rule at that table would delete a real field. | **v40 → v41** |
| 2026-08-05 | **A reported scoping bug that was not one — the overlay was lying, the engine was right.** The `DRAWING VIEWS` box visibly swallowed the NOTES / ISO / BOM / TITLE UL boxes on the revision. `views` means "this rectangle minus the sibling zones", and when pinned from a template it is a plain rectangle with the subtraction re-applied at use time by `scope_entities_to_views`; the renderer filled the raw rectangle and so claimed those regions were being diffed as drawing geometry. Fixed in `renderEntities.ts` by subtracting the siblings from the *tint* only — stroke stays whole so the box is still draggable — using a chained even-odd clip per sibling, because chained clips intersect and a single even-odd path would re-fill two overlapping siblings' intersection (BOM vs title overlap is logged on real sheets). See [[Gotcha - The Views Overlay Showed a Region That Is Not Compared]]. | — (UI truthfulness) | **Measured, and the measurement is the finding: the exclusion is doing 83–88% of the work, not a detail.** On `M7452A0N01`, **423 of 508** anchors inside the reference's views rectangle sit in a sibling zone and **492 of 562** on the revision, leaving pools of 85 and 70. On the reporter's own cached audit every note line came back as a `notes_section` card and every `drawing_views` card was a dimension or `２－７キリ` — nothing leaked. **No cache bump and no eval delta: no engine behaviour changed.** `zoneOverlay.test.ts` +5, of which the two that assert the subtraction were **verified to fail against the old renderer**; the suite had never rendered the `views` zone at all, which is why the branch was unpinned. | — (tint only) |

---

## ⛔ Negative results

Ideas measured and rejected, so they are not re-implemented. Per `CLAUDE.md` constraint 4, a
rejected idea is worth as much as one that worked. Expected to fill up quickly — the Stage 0.5 sweep
will reject most candidate constants, and "the defaults were already near-optimal" is a legitimate
and valuable outcome.

| Idea | Verdict | Why |
| :--- | :--- | :--- |
| Sweeping the 16 tuning constants against the mutation corpus (Stage 0.5's coordinate descent, as planned) | **Rejected — impossible, not merely unreliable** (2026-08-05) | Measured: **13 of 14 constants are flat across their entire declared range**, and the cause is structural. A mutation pair is a drawing and a copy of it, so both sides share one coordinate system exactly — 253 of 253 comparable entities at identical coordinates, versus 0 of 11 on the human pair, which is a re-trace. Distance is zero, so every matching radius succeeds on the first tier and the twin/fuzzy tiers are unreachable; `reconcile_relocated_markings` never engages because nothing is relocated. The plan's concern was that a mutation-only sweep would *fit* the constants to the mutator. The real risk is worse: it reports them **inert**, which invites deleting them. Only `changed_similarity_floor` responds, because it gates text and text is what mutations edit. See [[Gotcha - Mutation Pairs Cannot Exercise a Spatial Constant]]. |
| Treating the eval's `duplicates` counter as coverage for duplicate checklist rows | **Rejected — the metric cannot see the defect class** (2026-08-05) | Assumed while diagnosing the v40 QTY duplicate, and false. `runner.py` builds predictions from candidates with `status != "MATCHED"` — correct for precision/recall, since scoring MATCHED checklist rows would put precision near zero on a clean run. But **every duplicate-row defect this project has found surfaced as a *MATCHED* pair** (cache v13/v16; v39's bilingual UL split, flipped to MATCHED by the bilateral corroboration guard; v40's cross-extractor QTY). All three sat in the population the scorer discards, and `duplicates: 0` was reported throughout — including on runs where the bug was live and visible in the UI. The counter is real, but it only covers duplicates among *reported findings*. Measuring the MATCHED kind needs a distinct check — two rows in one zone with the same normalized value and the same coordinates — which does not exist. See [[Gotcha - Title Block QTY Reads the Upper-Left Table]]. |
| Sweeping on detection F1 alone | **Rejected — measured wrong** (2026-08-05) | The first sweep run reported **14 of 14** constants flat, i.e. "nothing in this engine is connected to anything" — contradicted by a passing test proving the same override changed real engine output. Both were right: the scorer matches a finding to its label *before* comparing status, so a constant that flips CHANGED into ADDED+REMOVED reshapes every verdict without moving detection by a thousandth. `Measurement` now carries **exactness** alongside F1, and `distance()` takes the max rather than the mean so a large move in one metric cannot hide behind a flat other. |
| "Expect failures" from the 3 never-collected `services/backend/tests/` files (Stage 0g) | **Wrong prediction** (2026-08-05) | All 10 relocated tests passed on first execution. The plan assumed code that had never been run must have rotted; what had actually rotted was the *collection path*, not the assertions. One genuine problem was found, but a different one: two of the three files asserted Japanese tolerance keywords against the **real** `08 - Client Domain & CAD Rules/`, which is gitignored — so they tested one developer's filesystem and would have failed in CI for a reason unrelated to the code. Both now inject a vault path, which `VaultSyncManager.__init__` already supported. Lesson: "never executed" predicts nothing about whether the assertions hold; run it before planning around the answer. |
| Copying the existing `finding_classifier.joblib` into its new home during Stage 0h | **Rejected** (2026-08-05) | Two copies on disk with nothing recording which is authoritative, and the choice re-made on every read. A read-order fallback (new location → vault) plus writes that only ever target the new location does the same job: the next retrain migrates the artifact by itself, there is no window where the model is missing, and no install needs a script run against it. The deprecated read logs a warning naming both paths, so the situation is visible rather than inferred. |
| Populate `text_similarity` / `match_distance` / `is_numericish` client-side in `CorrectionControls.tsx` — recorded above as Stage 0a item 3, "degraded labels that cannot be retroactively repaired" | **Rejected — the premise was wrong** (2026-08-05) | The nulls are not a defect and the 21 existing labels are not degraded. `feature_extractor.build_feature_row` derives all three from the raw texts and coordinates whenever they arrive as `None`, and the **inference** path (`features_from_marking`) never supplies them either — so `null` from the client is precisely what keeps training and inference on one definition. Computing them in TypeScript would introduce train/serve skew: there is no `SequenceMatcher` and no `SpatialDiffer._normalize_text` in JS, so the training-side number would systematically differ from the inference-side one. `ChecklistPanel.tsx:101-104` already said so; `CorrectionControls.tsx` was simply missing the comment, which is what made it look like an oversight. Action taken: the comment was added and the equality pinned by `test_training_and_inference_agree_on_the_derived_features`. |
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
