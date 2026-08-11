---
title: AI Maturity Status
type: status-ledger
tags: [status, ledger, agent-guide, roadmap, ai-architecture]
status: active
current_rung: 0
rung_evidence: none
rung_scale: ADR-007 (re-scoped 2026-08-07; rungs are no longer the ADR-003 LLM ladder)
date: 2026-08-07
verified-against: cache v43, baseline-v43.json (36 mutation pairs, 0 human labels)
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

> [!WARNING] Scope boundary — this ledger covers the **drawing comparison** only
> Established 2026-08-07 while answering "can our system do RAG?":
> [[RAG Reference Architecture — Gap Analysis]]. There is a **second, live pipeline** — the
> standards audit (`audit/audit_orchestrator.py`, wired into `main.py` at startup) — which
> **does** have a retrieval stage, a real query, prompt injection and a Gemini call. It is
> tracked by no ledger and governed by no ADR, and its embeddings are SHA-256 noise.
>
> So "the default method contains no retrieval and no LLM" is true of the comparison engine and
> **says nothing about the rest of the product.** Do not read this ledger as a statement about
> the whole system; every rung, stage and measurement below is about the comparison path.
>
> **That second pipeline had an owner for three days and no longer does.**
> [[ADR-008 The Second Brain — Retrieval-Only Local Knowledge]] and [[Standards Knowledge — Staged Plan]]
> took it on 2026-08-07; [[ADR-009 Retiring the Standards Knowledge Track]] retired the track on
> 2026-08-10 after R2's census found the corpus empty. **What changed permanently, and is why this
> is not a return to the starting position:** its fake retrieval stack is deleted, its replacement
> reports `MISSING`/`EMPTY`/`STALE` instead of inventing answers, and
> `tests/test_no_fake_ai_capability.py` prevents the regression. An unowned pipeline that says it
> has nothing is a different risk from one that fabricates. It remains a **parallel track**:
> labelling remains this ledger's critical path and nothing in the standards knowledge plan touches the
> comparison engine. The invariant that keeps them separate is testable — the eval corpus must
> score **P 0.98 / R 0.87 / F1 0.92** against `baseline-v43.json` throughout that work, and any
> movement means something leaked across the boundary.

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

Do not infer system state from code or from names. There is exactly ONE comparison
method, keyed `deterministic`, and it contains no retrieval and no LLM. It was keyed
`rag` until 2026-08-07, which is why older notes say so — `rag` is still accepted as
a permanent input alias. The ledger is the only authority on which rung the system
is on.

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

> [!IMPORTANT] The rungs were re-scoped on 2026-08-07 — [[ADR-007 Re-scoping the Maturity Ladder]]
> The ADR-003 ladder (`Basic RAG → Fine-Tuned RAG → End-to-End Trainable → Agentic & Adaptive`)
> defined every rung by an **LLM** capability, and [[ADR-006 Removing the Three AI Comparison Methods]] deleted every LLM path. Rung 1 as written was unreachable, so the metric could only
> ever read 0 — which looks like a number and is not one. The rungs below are defined by what
> the deterministic engine can be **measured** on. This did **not** claim a rung: see below.

```
rung 0          rung 1        rung 2         rung 3              rung 4
pre-measure → Measured  →  Calibrated  →  Retrieval-augmented → Learned matching
  ▲            (≥8 human     (Stage 0.5     (stored human        (Stage 3 beats the
  │             pairs         optima on      decisions move       cascade on held-out
  │             labelled)     human pairs)   output, measured)    human pairs)
  └── we are here
```

**Rung 3's "retrieval" means retrieving prior human decisions** — the learned-dismissal flywheel
and the learned overlay — not retrieving context for a language model. That is the only
retrieval on the deterministic path, and unlike the old rung 1 it gates output users see today.

Every rung above 0 is now gated on the **same** resource: human labels. That is deliberate; see
ADR-007's consequences.

---

## 📍 Current rung: **0 — pre-measurement**

`rung_evidence:` **none** — and under the rule above, that is exactly why the rung cannot be claimed
higher. Rung 1 now means *per-category precision/recall/F1 over **human-labelled** pairs*, and the
corpus is **0 / 8 labelled**. A baseline exists (`baseline-v43.json`) but every number in it comes
from mutation pairs, which ADR-007 explicitly excludes as rung-1 evidence.

**Re-scoping the ladder did not move the rung, and was not meant to.** It made rung 1 reachable;
reaching it is annotation work. Claiming it on the mutation baseline would be the phantom the
evidence rule exists to prevent.

Component-by-component, as of cache **v43**. Read this as the state of the machinery, not as a
rung argument — under [[ADR-007 Re-scoping the Maturity Ladder]] the rung turns on **evidence**,
and the only missing evidence is labels:

| Component | State |
| :--- | :--- |
| The method, now `deterministic` | Contains **zero retrieval and zero LLM**. It is a pure deterministic spatial/text differ (`orchestrator.py:290`). **Renamed from `rag` on 2026-08-07** — the misnomer is gone from the DB, cache filenames, the API and the UI; `rag` survives only as a permanent input alias for rooms written before the rename. The name no longer claims a capability the code does not have, which was the point. |
| Embeddings | **None — deleted 2026-08-07** by R0 of the [[Standards Knowledge — Staged Plan]] ([[ADR-008 The Second Brain — Retrieval-Only Local Knowledge]]). `local_embedding_model.py` returned `SHA-256(text)`-seeded Gaussian noise with `+100.0` bumps on dims 0/100/200 for English keywords absent from this Japanese CAD domain, behind a docstring claiming SentenceTransformers/ONNX while `_load_model` assigned the *string* `"ONNX_Quantized_MiniLM"`. Deleted rather than repaired. Real embeddings are **not** the R1 plan either — R1 is lexical. |
| Vector store | **Real as of 2026-08-07 — but on the *other* track.** `infrastructure/retrieval/store.py` (R1) is an exact brute-force cosine over a scipy CSR matrix plus a JSONL sidecar and a manifest, holding three collections. It serves the **standards-audit** pipeline, not this one; the comparison engine still has no vector store and does not want one. The predecessor `lancedb_manager.py` was never LanceDB — an `index_shards.json` plus a numpy loop over a file that never existed. Its *algorithm* was right at this scale and survives; its name and JSON persistence did not. |
| Retrieval | **On this track: unchanged.** `few_shot_retriever.py` is **deleted** ([[ADR-006 Removing the Three AI Comparison Methods]]) — it fed only the Gemini system prompt, which no longer exists. The retrieval that remains on the comparison path is `vault_sync.get_learned_dismissal_rules()` → the zone pools: stored human decisions, **structured and category-scoped as of 2026-08-07**, gating real output. This is rung 3's substrate. It holds **2 patterns**, one of them the bare digit `8`. **On the standards-audit track: real as of 2026-08-07** — `infrastructure/retrieval/`, char n-gram TF-IDF, 6–9 ms, offline. Lexical, **not semantic**, and it says so. The two do not touch, and R1 moved no rung here. |
| Learned model | **Real and wired**, still **inert** — but much closer than this row said. **Corrected 2026-08-10 from the live bundle** (`services/backend/storage/models/finding_classifier.meta.json`, trained 2026-08-09): `n_total` **70**, `n_verdict` **36 / 40**, `n_category` **6 / 40**, `metrics: {}`. This row read "21 verdict labels" and was stale by 15. **The verdict head is four corrections from switching itself on** (`MIN_TRAIN = 40`, plus both classes present — `trainer.py:136`), which makes it the cheapest unclaimed win in the project. The category head is not close. Only exact-match overrides fire today. Labels are **sound**, not degraded — see the 2026-08-05 Stage 0a work-log entry. See [[Gotcha - Learned Corrections Model and Post-Cache Inference]]. **Read the meta file, not this row** — it is the only figure here that moves without a commit. Better, run `tools/label_status.py`, which reports the corpus the way `build_bundle` counts it (retracted rows excluded, verbs bucketed, skew flagged) rather than the way a row like this one goes stale.<br><br>**⚠️ The count is not the constraint; the class balance is.** Live corpus 2026-08-10: **27 class-0 against 9 class-1**, 75% negative. Four more `dismissed` (already the most-used verdict verb, and the easiest click) trains the head at **31:9** — and `inference._decide` flips a `CHANGED/ADDED/REMOVED` to **MATCHED** whenever `p_true < LOW_THRESH (0.20)`. A head whose prior is 75% negative crosses that gate routinely, so hitting 40 the cheap way ships **silent suppression** — the false-negative direction, in the system whose headline gap is that false negatives have never been measured. Blast radius is bounded but not small: `SPATIAL_CATEGORIES` only (`drawing_views`, `notes_section`, `isometric_view`), never title_block or BOM. **The next verdict labels should be class-1** (`confirmed_valid`, `verdict_changed`) and honestly earned, not farmed.<br><br>**The loudest signal in the corpus trains nothing.** `mispaired_missing_counterpart` is the **single most-used verb at 22** — more than `dismissed` (21). The human has said "you paired the wrong two entities" more often than anything else, and every one of those rows is parked for a Stage 3 matcher that does not exist (`trainer.MATCHER_FEEDBACK`). **Stage 3 has more training data waiting (22) than the verdict head is short (4).** That is the strongest evidence yet on where the real defect is, and it is not the verdict head. Also: **1,374 of 1,377 violations carry no supervisor verdict.** |
| Evaluation | **Substrate exists as of 2026-08-05; ground truth does not.** `tools/eval.py` prints per-category precision/recall/F1 over 36 mutation pairs in ~13 s, offline, against a published **v43** baseline — **P 0.98 (48/49) / R 0.87 (48/55) / F1 0.92, macro 0.88** — applying the same hand-aligned zone boxes users see. But **0 human-labelled pairs**, and since the 2026-08-05 rebuild the corpus covers **one drawing family**, so per-category figures are a property of that sheet rather than of the client. Nothing yet measures what a checker would flag. |
| Observability | **None.** `storage/ai-artifacts/{prompts,responses,embeddings}/` all exist and are all empty. |

Corrected 2026-08-05, from running the pipeline offline for the first time: the eval **seam** is
real and now demonstrated — 3 pairs, 0.77 s, zero non-local sockets — but two of the plan's
assumptions about it were wrong. `generate_deterministic_candidates` reads a **sixth** entity
attribute (`.id`, via `detect_balloons`), and it is **not** network-free: title-block OCR calls
Gemini on a cache miss. Both are guarded in `infrastructure/eval/`; neither changes the rung.

### Why rung 0 is the honest reading

Under ADR-007 every rung above 0 is defined by a **measurement over human-labelled pairs**, and
there are none. Under the old ADR-003 ladder the reason was different but the answer was the
same: "fine-tuned" needs a validation score, "trainable" needs a loss, "adaptive" needs a signal,
and none existed. The gap analysis states it plainly:

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
- ~~**A proto-agentic pattern.** `hybrid_orchestrator.py`'s dual-generator + `crop_verifier.py`
  adjudicator is the right shape for rung 4 — it needs generalising, not replacing.~~
  **Deleted 2026-08-07, [[ADR-006 Removing the Three AI Comparison Methods]].** Rung 4 remains
  the stated end goal, so this is a real cost and is recorded as one: the pattern is now
  recoverable only from git
  (`git log --diff-filter=D -- services/backend/infrastructure/audit/comparison/hybrid_orchestrator.py`).
  Worth remembering that `hybrid` **could not complete a single run** until the Stage 0a
  `NameError` fix, so what is preserved is a shape, never a working system.
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
>
> **Made permanent 2026-08-07 — [[ADR-006 Removing the Three AI Comparison Methods]].** The
> three methods are **deleted**, backend and frontend: ~2,100 lines, 12 files, the routing
> table, the second cache lever, and the Create Room picker. `comparison_method` is
> `Literal["rag"]`. ADR-004 explicitly left "whether to delete" undecided; this closes it.
> There is now **one comparison method in this system**, and the `rag` misnomer is the only
> name it has.
>
> **Closed 2026-08-07 — [[ADR-007 Re-scoping the Maturity Ladder]].** The "re-scoping or
> retiring — not yet decided" clause above is now decided: **re-scoped**. The rungs are defined
> by what the deterministic engine can be measured on, rung 3 is the learned-decision flywheel,
> and the old rung 1's retrieval-recall@5 exit criterion is retired for good. No rung was
> claimed — the corpus is still 0/8 labelled, which is the whole point.

**Stage 0b's labels. Nothing else is the bottleneck any more.**

> [!IMPORTANT] Updated 2026-08-10 — **the cheapest source of human judgment is now wired, and it is
> not the worksheets.**
> The supervisor review endpoint had **no caller in the app** until today
> ([[Gotcha - A Tested Endpoint That Nothing Ever Called]]), so all 1,322 violations sat unreviewed.
> `ReviewControls` now exists, which means **a supervisor working through the review queue produces
> human judgments about engine output as a side effect of normal use** — the resource every rung
> above 0 is gated on.
>
> **Amended later the same day: that was true only for pairs with no cache entry — which is to say,
> not the pairs anyone reviews.** A cache hit returns before the code that persists an
> `AuditViolation` and stamps its session id, so every already-compared drawing rendered findings
> with no reviewable identity and the control silently did not appear. Fixed
> ([[Gotcha - The Cache Served Findings That Existed Nowhere]]); the first Re-test of a stale pair
> runs long, which is the guard working. **The count this was meant to start accumulating was 0
> until 2026-08-10 and is still 0** — the queue is now genuinely open, and nobody has worked it yet.
>
> **This does not replace Stage 0b, and the difference must not be blurred.** A review verdict is
> `(finding → correct/incorrect)`. A rung-1 label is a structured `(pair → findings with categories,
> addresses and statuses)` under [[Eval Corpus Annotation Guideline]], including **findings the
> engine missed entirely** — which a review queue can never surface, because it only shows what the
> engine already reported. **Reviews cannot measure recall. That is the whole gap.** They can
> measure precision, they build the `lessons` corpus, and they are far cheaper to collect. Treat
> them as complementary, and do not let a growing pile of approvals be mistaken for rung-1 evidence.

> [!NOTE] A second track existed from 2026-08-07 and was **retired 2026-08-10**. It never changed
> the action above, and its closure does not either.
> **Closed by [[ADR-009 Retiring the Standards Knowledge Track]]: R3 and R4 are retired, not deferred, and
> the standards-audit pipeline is not the product.** R0–R2 stay landed and their code stays in the
> tree. Two things carry forward into *this* ledger and nothing else does: the negative result below
> ("do not optimise retrieval"), and the **`AutoDocEngine` defects re-homed into the unblocked-engineering
> list above** — R3 owned that fix, and it is a comparison-engine defect. Do not restart R3; the
> reopening condition is in ADR-009 and it is about data, not engineering. The detail of what landed
> follows, unchanged:
> [[Standards Knowledge — Staged Plan]] governs the **standards-audit** pipeline (`audit_orchestrator`'s
> clause retrieval), which [[RAG Reference Architecture — Gap Analysis]] found running in
> production on SHA-256 noise, tracked by no ledger. **R0, R1 and R2 all landed 2026-08-07** —
> nine fake modules deleted, `infrastructure/retrieval/` built to replace them with char n-gram
> TF-IDF (6–9 ms, offline, lexical not semantic), then the metric built to measure it. Eval
> byte-identical throughout.
>
> **R2's answer is that the track is blocked on data, not engineering:** `standard_chunks` = **0**
> (no standard has ever been uploaded) and all 1,322 audit violations are unreviewed, so two of
> three retrieval collections are empty.
>
> > [!WARNING] **Corrected 2026-08-10: "blocked on data, not engineering" was half wrong.**
> > `standard_chunks` = 0 because **the upload could not succeed** — the desktop app posted to
> > `POST /api/v1/standards`, which is GET-only, and got a 405 every time. Nobody chose not to
> > upload a standard; nobody could. Fixed, along with a zero-chunk parse that reported success
> > and an `.xls` path that no parser could read. See
> > [[Gotcha - A Standard That Ingested Nothing Reported Success]] and the amendment on
> > [[ADR-009 Retiring the Standards Knowledge Track]]. **The retirement stands** — R3/R4 remain
> > premature while the corpus is empty *today* — but its reopening condition is now live and
> > cheap to test, where before it was a question the code prevented anyone from answering.
> > **Unchanged: labelling is still this ledger's critical path**, and the comparison engine is
> > untouched by any of it. Improving the encoder would move a number that does not
> exist. **Do not optimise retrieval — that is the wasted next instinct, and it is recorded as a
> negative result below.** This ledger still governs the **comparison engine**, and
> **labelling is still its critical path.** The two tracks share a corpus invariant (P 0.98 /
> R 0.87 / F1 0.92 against `baseline-v43.json`) and nothing else; movement in that number during
> standards knowledge work means something leaked across the boundary. Do not read R0 as progress up
> *this* ladder — deleting a false claim moved no rung, and was not meant to.

Under [[ADR-007 Re-scoping the Maturity Ladder]] this is no longer scaffolding ahead of the real
work — **labelling *is* rung 1.** The six worksheets were regenerated at guideline `2026-08-06`
on 2026-08-07 (they had been stamped `2026-08-05`, which `tools/eval.py` would have refused), and
`tools/eval_corpus.py validate` now checks a draft in place. Nothing else blocks an annotator.

Stages 0a–0e, 0g and 0h are done and the harness works: `tools/eval.py` prints per-category
precision/recall/F1 over 36 mutation pairs in ~13 s with zero network calls, against a
published `baseline-v43.json` that applies the same hand-aligned zone boxes users see.
What that harness cannot do is judge itself. **Every number in the baseline is mutation-only,
and since the 2026-08-05 rebuild they all come from one drawing family** — so a per-category
figure describes that sheet, not this client. Mutation pairs have three further stated blind
spots:

- they are drawn from the engine's own comparison pool, so they **cannot reveal a scoping
  bug** — and that is a live bug class here ([[Gotcha - A Naive Mutator Manufactures Recall Misses]]);
- their category attribution is **not independent** of `zone_detector` — no longer a suspicion
  but a demonstrated fact, since changing the zone boxes moved attribution 0.81 → 0.74 without
  the engine regressing at all ([[Gotcha - Mutation Labels Predate the Zone Template]]);
- they cannot gate Stage 3's learned matcher, which is trained on that distribution.

So `recall 0.87` is a real number about synthetic edits on one sheet, and **not yet the number
the gap analysis asked for** — "whether the engine catches the changes a human checker would
flag". Closing that is annotation, not engineering.

**Step 1 is done as of 2026-08-06 — the corpus is 7 / 8 human pairs.** All seven ingested
`reference` ↔ `FSRS2_kmti` pairs are exported, integrity-checked, zone-captured and (bar the
held-out one) offline-ready: M745203N01, M745206N01, M745227N01, M745230A01, M7452A0N01,
M7452A1N01, M7452A2N01. Payload digests confirm all seven are distinct, though A0/A1/A2 are
one drawing family, so the corpus samples roughly **five** layouts rather than seven.

**The binding constraint is now held-out pairs, at 1 / 3, and it needs drawings that do not
exist yet.** The guideline requires a held-out pair be designated *before* anyone looks at
engine output on it. Measured against `storage/cache/`: **six of the seven already carry a
comparison cache entry**, so only **M745206N01** was eligible, and it was exported
`--held-out` first, before anything else touched it. The other two must come from pairs
ingested and exported **without ever running a comparison on them**:

```
tools/eval_corpus.py export --pair-id <ID> --ref <file> --rev <file> --held-out
```

> [!WARNING] The held-out pair is not offline-ready, and the reason is circular.
> `M745206N01` has no title-block OCR cache — precisely *because* no comparison has ever run
> on it, and OCR is populated on a comparison's cache miss. So the thing that makes a pair
> offline-ready is the thing that burns its held-out eligibility. The way out is the
> **ScanText / deep Re-test** path, which re-reads the crop without running a comparison
> ([[Gotcha - Re-test and the Four Caches]]). Until then an eval run *including* held-out
> pairs would hit the no-network guard rather than silently differ — the guard working.

2. **Label all 8 — this is now the whole of the critical path, and it is annotation work.**
   Worksheets and empty drafts are already generated for the six labellable pairs, under
   `storage/eval/worksheets/`. Nothing else in Stage 0 is waiting on engineering.

   > **Annotator note for `M745203N01` — CONFIRMED 2026-08-10, and the pair is parked.** Its two
   > sides have *different sheet shapes* — ref is `aspect-1.361`, rev is `aspect-1.414` — and no
   > template is pinned for 1.361, so that side takes the global default scaled onto a
   > differently-shaped sheet. Per [[Gotcha - Global Default Zone Template & the Aspect Caveat]]
   > its zone boxes may be misplaced, and the reference side is where REMOVED findings anchor.
   >
   > **The manifest disguises this as coverage.** `zone_templates` lists **both** signatures, seven
   > zones each, which reads as both shapes being handled — but the two blocks are **byte-identical**,
   > so 1.361 is carrying 1.414's boxes. `capture-zones` mirrors the app's lookup (specific, then
   > global default) and files the result under the key it asked for, so presence in that map cannot
   > be distinguished from alignment. Check equality whenever a new signature joins the corpus.
   >
   > **Decision (2026-08-10, user's call): label the other five first and park this pair** until a
   > 1.361 template is hand-aligned. Rationale: five pairs already yield the first recall number this
   > project has ever had, and labels authored over misplaced reference-side boxes would have to be
   > redone. Parking it means Stage 0b reads **5 / 8 labelled** at best until either the template is
   > pinned or the pair is labelled anyway with the caveat attached. Do not re-litigate this ordering;
   > revisit only when someone aligns 1.361.

   For each pair: `tools/eval_corpus.py worksheet --pair-id <ID>` writes a
   neutral annotation aid (a naive high-recall text inventory — deliberately *not* engine
   output, so the engine's own misses stay visible) plus an empty label draft. Fill the draft in
   against [[Eval Corpus Annotation Guideline]], then
   `tools/eval_corpus.py label --pair-id <ID> --from <draft>`. The loader rejects invented
   categories, bad statuses, malformed addresses and stale guideline versions, so a filled draft
   that installs is a well-formed one.

~~**Three decisions are waiting on the first two annotated pairs**~~ — **resolved 2026-08-06.**
[[Eval Corpus Annotation Guideline]] is `status: active` at `guideline_version: 2026-08-06`,
with all four open questions folded into the rules. Settled *before* the first label rather
than after two, reversing the original plan deliberately: at 7 registered pairs and 0 labelled
it cost nothing, while labelling under a draft would have meant re-labelling everything.

Three of the four had a **de facto answer already in the code**, which is why they were
settleable without labelling experience — ruled rows (the engine already emits `TITLE` and
`TITLE SUB` separately, and already suppresses DWG No. segments) and the amendment/balloon
categories. The one free choice, the bulk threshold, is marked as a convention rather than
dressed up as a finding.

**One resolution deliberately buys a false positive.** A newly added revision row is *not* a
finding, but the engine reports it today — `amendment_table_bboxes` reclassifies rather than
excludes. Every human pair will therefore show a title_block false positive by construction.
That is the point: it converts an invisible product behaviour into a measured one, and the
follow-on decision (should the engine suppress new revision rows?) now has evidence waiting
for it instead of taste.

~~**One decision is waiting on nothing**~~ — **resolved 2026-08-06.**
[[Gotcha - Zone Templates Vanish in Offline Eval]] is fixed: the corpus now carries its own zone
fractions and the engine applies them offline. **Precision 0.78 → 1.00, recall 0.65 → 0.78,
F1 0.71 → 0.88** — all ten false positives in the v38 baseline were artifacts of the
measurement, not defects in the engine. New baseline `baseline-v42.json`.

~~**It left one piece of debt**~~ — **paid 2026-08-06.**
[[Gotcha - Mutation Labels Predate the Zone Template]]: the mutator now scopes with the
engine's zones and all 36 pairs were regenerated at mutation schema **v2**. **Recall 0.78 →
0.85, F1 0.88 → 0.91, handle-tier matches 15 → 22.** It also settled two things that outlive
it — attribution on mutation pairs is a **tautology** and cannot measure the engine, and
`isometric_view` has no coverage because the correct `iso` box holds zero comparable entities.
Both are in the negative-results table.

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

- ~~**`AutoDocEngine` can write one client's drawing text into another client's rule file, and a
  database hiccup can write a rule from a single dismissal.**~~ **FIXED 2026-08-10** —
  [[Gotcha - A Count You Could Not Take Is Not Evidence]]. Both defects below are closed, and a
  **third of the same family** was found while fixing them: the count included **retracted**
  dismissals, which `trainer.py` already skips, so three taken-back clicks could write a permanent
  rule. The filter is now a plain dict (`build_dismissal_filter`) precisely so it can be asserted on
  — the suite has no MongoDB, and a filter built from Beanie expressions cannot be inspected offline,
  which is how the missing clause survived. Also: **the one existing test passed *because of* the
  defect** and had to be rewritten. Original text follows. — *(Re-homed here 2026-08-10 from the
  retired R3 — [[ADR-009 Retiring the Standards Knowledge Track]].)* Two defects in six lines of
  `infrastructure/knowledge/auto_doc.py`:
  1. `process_feedback_event` counts dismissals with **no `client_name` filter** (`:43`), then files
     the rule under `feedback.client_name` (`:52`). A pattern dismissed **once at each of three
     different clients** reaches N≥3 and lands in `Learned_Rules_{whoever_tripped_it}.md`.
  2. That count sits inside `except Exception: dismiss_count = getattr(feedback, "_mock_dismiss_count", 3)`
     (`:47-49`), so **any** DB error defaults it to exactly the promotion threshold — one dismissal
     writes a permanent rule — via test scaffolding reachable from the production path.

  **This is the highest-severity item on this list and it is not a metric item.** It writes into
  `08 - Client Domain & CAD Rules/`, the only directory in this vault that is a runtime input
  (rule 3 below): `get_learned_dismissal_rules()` → `safe_filter` and the zone pools. A wrong rule
  there **suppresses real findings** — the false-negative direction, in the system whose headline
  gap is that false negatives have never been measured. It was going to be fixed as part of R3's
  overlay tier; that tier is retired, so **nothing else prevents it.**
- ~~**`notes_section` is the weakest category — P 0.47 / R 0.54**~~ — **fixed for free,
  2026-08-06.** It was never an engine weakness: applying the hand-aligned zones took it to
  **P 1.00 / R 0.92 / F1 0.96**. The weakest category is now **`bill_of_materials`
  (P 0.86 / R 0.60 / F1 0.71)** — it carries the corpus's only false positive *and* half its
  recall loss, so it is the one category worth attacking on engine grounds.
- **Two categories have no coverage at all, both structurally** — `isometric_view` (the
  correct `iso` box holds zero comparable entities) and `other_engineering_references`
  (callouts deliberately suppressed). Neither is fixable by adding mutation operators; both
  need human pairs. See the negative-results table.
- ~~**A single-character deletion goes unreported.** Prime suspect: `MIN_FUZZY_LENGTH = 4`.~~
  **RESOLVED 2026-08-07, and both halves of that item were wrong** —
  [[Gotcha - A Short Structured Value Suppresses Its Own Zone]]. `MIN_FUZZY_LENGTH` gates
  *merging* a REMOVED+ADDED pair, so failing it produces **more** findings, never zero; it could
  not have caused a zero-finding symptom. And the cited example (`G`) reports correctly today
  and had gone stale. The real miss was a `１` suppressed because the BOM row was numbered `1`
  and the structured-value net matches text sheet-wide. **Recall 0.85 → 0.87, `notes_section`
  recall → 1.00, no new false positives.**
- ~~**BOM row granularity.**~~ **DONE 2026-08-07.** One edited row is now one finding;
  MATCHED cells keep their per-column verification rows. **Measured effect on the corpus:
  zero** — every BOM mutation operator edits a single cell, so no mutation pair has ever had a
  multi-column row edit for the collapse to act on. Pinned by `tests/test_bom_row_granularity.py`
  (7 tests, 3 verified to fail against the per-cell builder), because the eval structurally
  cannot reach it. The value is alignment: human BOM labels will be row-level.
- **`other_engineering_references` has no coverage** — no mutation operator targets it, because
  section callouts are deliberately suppressed (`DROP_SECTION_CALLOUT_LABELS`, cache v38), so
  such a pair would be a guaranteed recall miss *by design*. Now measurable, once someone
  decides which way that trade should go.
- ~~**Rename `rag` → `deterministic`.**~~ **DONE 2026-08-07.** The method is `deterministic`
  everywhere — DB, cache filenames, API, CLI and UI — with `rag` accepted as a **permanent**
  input alias, normalised on the way in by `domain/models/comparison_method.py`. No migration:
  rooms written before the rename still say `rag` on disk and load through the alias, so the
  day someone "cleans up" that alias is the day those rooms stop loading. Pinned by
  `tests/test_comparison_method_rename.py` (11 tests), which states that in each test's docstring.
  **The plan's stated reason for deferring it to Stage 0.5 did not survive measurement.** It was
  to be done "at Stage 0.5's cache bump, the one moment everything is invalidated anyway",
  because the method is a segment of the cache filename. Counted before doing it: `storage/cache/`
  held **one real v42 comparison entry** (the other v42 file is a `ref_dwg_id` placeholder), so
  the invalidation cost was one re-run, not a corpus. **No cache bump was taken** — v42 stands
  and v43 is still free for Stage 0.5, which is what the coupling was protecting in the first place.

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
      *(2026-08-07 — **7 / 8 registered, 0 / 8 labelled, 1 / 3 held out** (live, via
      `tools/eval_corpus.py status`). **Annotation is unblocked**: the six drafts were stamped
      `guideline: 2026-08-05` against an active `2026-08-06` and would have produced labels
      `tools/eval.py` refuses — regenerated 2026-08-07. `validate` now checks a draft in place
      and `status` prints a per-pair queue. Under [[ADR-007 Re-scoping the Maturity Ladder]]
      this box is no longer scaffolding: **it is rung 1.**)*
      *(2026-08-06 — **7 / 8 registered, 0 / 8 labelled, 1 / 3 held out.** All seven ingested
      pairs exported, zone-captured, distinct by payload digest; worksheets generated for the
      six labellable ones. Held-out is the blocker and needs **new** drawings: six of seven
      already carry a comparison cache entry, so only M745206N01 was eligible under the
      "designate before looking at engine output" rule. Labelling is the whole remaining
      critical path and no engineering is waiting on it.)*
      *(2026-08-05 — **infrastructure done, corpus not**. Format, loader, drift detection,
      held-out lock and CLI landed and tested; the offline seam is demonstrated end to end.
      Run `tools/eval_corpus.py status` for the live count — it reads the manifest, so it
      cannot go stale the way this line can.)*
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
      `socket.connect`. Baseline published at `tests/fixtures/eval/baseline-v38.json`.
      **2026-08-06 — 0e's open decision closed**: hand-aligned zone templates are now applied
      offline via the `zone_template` seam, so the run scores against the boxes users
      actually see. Baseline superseded by `baseline-v42.json` — P 1.00 / R 0.78 / F1 0.88,
      36 pairs in ~13 s. See [[Gotcha - Zone Templates Vanish in Offline Eval]].)*
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

> **Exit:** `tools/eval.py` prints per-category precision/recall/F1 over ≥8 human pairs
> and ≥30 mutation pairs, in <60 s, with **zero network calls**, green in CI. A published
> baseline exists for all 6 categories (now `baseline-v43.json`). `pytest tests/ -q` green
> including the 3 relocated tests. **Only the ≥8 human pairs are outstanding** — every other
> clause is met.
>
> *(`--method rag` in the original wording: the flag still accepts it as a permanent alias, but
> the method is `deterministic` and `--method` can be omitted entirely. There is no `--corpus`
> flag — the staged plan's example command invents one.)*

### Stage 0.5 — Calibration
- [x] `ComparisonParams` extracted; refactor proven **byte-identical** on the corpus
      *(2026-08-05 — `comparison/params.py`, 20 constants across 6 modules, each module now
      deriving from `DEFAULT_PARAMS`. Proven: engine output identical to the committed v38
      baseline. `sweep_override()` is the override mechanism — module-global rebinding,
      **single-threaded offline use only**, restored in a `finally`. Threading a params
      object through the call tree was deliberately deferred; the reason is in the module
      docstring.)*
> [!WARNING] Every Stage 0.5b number below predates 2026-08-07 and was measured in the **wrong
> zone regime.** `tools/sweep.py` called `generate_deterministic_candidates` **without**
> `zone_templates`, so it degraded to plain detection while `tools/eval.py` applied the
> hand-aligned boxes — sweep baseline **F1 0.68** against the eval's **0.92**, on the same
> corpus and the same commit. The sweep landed one day before the template seam and was never
> re-run. Fixed 2026-08-07; see [[Gotcha - The Sweep Never Got the Zone Template Seam]].
>
> **Re-measured after the fix, and the verdict holds: the flat/not-flat partition is
> identical.** 12 of 14 flat — 12 of the original 13, plus a new constant that responds. The
> spatial constants are flat because both sides of a mutation pair sit at identical
> coordinates, which zone boxes cannot change. What *was* wrong:
> `changed_similarity_floor`'s spread, understated **2.2×** at 0.139 against a true **0.305**,
> and its default **0.4 sitting at the edge of a cliff** (exactness 0.958 flat to 0.4, then
> 0.917 / 0.796 / 0.653) rather than mid-plateau. Corrected baseline **F1 0.923**, matching
> the eval. Full figures in the work log.

- [ ] Matching constants swept (coordinate descent, leave-one-pair-out CV)
      *(**2026-08-07: the default pass is now 13 constants, not 14.** `match_radius_mm` was
      removed with `reconciler.py` — and the removal exposed that it was tuning the eval
      **scorer**, not the engine, so a sweep of it would have moved F1 with nothing in the
      engine changing. See [[ADR-006 Removing the Three AI Comparison Methods]].)*
      *(⛔ **blocked, and harder than "needs a better corpus"** — 2026-08-05: measured, **13 of
      14 constants cannot be exercised at all** by mutation pairs, because both sides share one
      coordinate system exactly. The sweep machinery exists and works (`tools/sweep.py`); it has
      nothing to measure until human pairs land. See
      [[Gotcha - Mutation Pairs Cannot Exercise a Spatial Constant]].)*
- [ ] Zone constants swept separately, with "pinned templates still resolve" asserted
      *(machinery ready behind `--include-zone`; the pinned-template assertion is not written)*
- [ ] `COMPARISON_CACHE_VERSION` bumped (**now v44** — v38–v42 spent 2026-08-05,
      **v43 spent 2026-08-07**); ~~`rag` renamed `deterministic` with a compat alias~~
      *(**rename DONE 2026-08-07**, and deliberately decoupled from the bump: the cache held
      one real v42 entry, so the invalidation this checkbox was pairing it with cost a single
      re-run.)*
      *(**v43 was taken 2026-08-07** by two engine changes that could not wait for a sweep —
      BOM row-level findings and the structured-value length floor. The reservation was for
      convenience, not correctness, and it cost nothing: the sweep is blocked on human pairs
      regardless. **Stage 0.5's bump is v44.**)*

> **Exit:** measured-optimal values for ≥10 of 16 constants, each with a recorded held-out ΔF1 and
> stated confidence. Aggregate F1 ≥0.05 over the v38 baseline on held-out human pairs — **or a
> documented finding that the defaults were already near-optimal**, which is a legitimate result.

### Stage 1 — ~~Real retrieval → rung 1: Basic RAG~~ → **rung 3: Retrieval-augmented**

*[[ADR-004 Deterministic-Only Scope]]: rung 1 is unreachable under this scope. Retrieval feeds
only the Gemini system prompt, which the default method never sees, so 1b changes nothing users
observe. Only 1a survives — it is the sole retrieval on the deterministic path and gates real
output today.*

*Re-scoped 2026-08-07 by [[ADR-007 Re-scoping the Maturity Ladder]]: 1a is no longer the
leftover of a dropped stage, it is **rung 3's first increment**. "Retrieval" here means
retrieving prior human decisions, which is what this always was.*

- [x] 1a — learned-dismissal patterns made structured (`exact` / `normalized` / `prefix`)
      *(2026-08-07 — `LearnedDismissal{pattern, category, match_mode}` in `vault_sync`, with
      `normalized` at ≥3 chars and `exact` below, and each zone pool receiving **only its own
      category's** rules. Previously every category was flattened onto the drawing_views pool,
      so a `title_block` dismissal suppressed geometry and the notes/iso pools saw none at all.
      **Measured effect: zero** — 2 patterns live, one the bare digit `8`. Recorded as zero.
      `tests/test_learned_dismissal_scope.py` (10).)*
- [x] ~~1b — `local_embedding_model.py` and `lancedb_manager.py` deleted~~ **DROPPED** — *but
      the deletion itself happened anyway on 2026-08-07, under a different plan and for a
      different reason.* [[Standards Knowledge — Staged Plan]] R0 removed both files (and seven more)
      because they **claimed capabilities they did not have**, not because anything is building
      RAG here. **1b stays dropped:** it was a rung-1 *Basic RAG* stage, and
      [[ADR-004 Deterministic-Only Scope]]'s reasoning that retrieval would feed only a Gemini
      prompt the default method never sees is unchanged. Deleting a fake is not progress up this ladder —
      it is removal of a false claim, and it moved no rung. See the 2026-08-07 R0 work-log entry.
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
and `hybrid` is out of scope. ~~`hybrid_orchestrator.py`'s dual-generator + `crop_verifier.py`
adjudicator — recorded above as "the right shape for rung 4" — is shelved with it, not
deleted.~~ **Deleted 2026-08-07** ([[ADR-006 Removing the Three AI Comparison Methods]]); the
"not deleted" clause above is no longer true and is struck rather than edited, because the
change of mind is the fact worth keeping.*

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
| 2026-08-05 | **Zone boxes can be reshaped — hover an edge, click to insert a node, drag the vertices.** Full-stack, because a zone's shape is what the comparison runs on: `zone_geometry.py` (containment), `ZonePoint`/`ZoneFractions.points` (persistence), `fractions_to_absolute_polygon` (the Y flip), `scope_entities_to_views` / `views_exclusions` / `safe_filter` (the gates), plus outline rendering, the `+` edge ghost, per-vertex handles and alt-click delete. Kept small by making the outline **additive**: the four scalars become its *derived* bounding box, `regions[zone_key]` stays a 4-tuple for the ~29 sites that index it, and the outline rides under the reserved `_zone_polygons` key. Old templates have no `points` and parse as the rectangles they were — **no migration**. See [[Gotcha - A Reshaped Zone Is Not Its Bounding Box]]. | — (tooling) | **Measured. Reshaping the reference `views` zone to its left half via a real template outline cut the pool 85 → 41, and the revision 70 → 22, with the result asserted to be a SUBSET — a reshape can only ever remove.** Eval over 36 pairs is **byte-identical to the v38 baseline**: inert until someone reshapes something, and nothing reshapes automatically. **Two silent failure modes drove the design and are both pinned.** (1) A *vertex* conversion is not the *box* conversion — the box flips Y and swaps min/max, but that swap is an artifact of the names; a vertex is the flip alone. Get it wrong and the outline is vertically mirrored: closed, right size, right bounding box, gating the opposite half. (2) Excluding a reshaped sibling on its bounding box drops content from the notch cut out of it, which **no other category picks up** — the false-negative direction, in the system whose headline gap is that false negatives have never been measured. Also two non-obvious rules: a **grown** zone drops its outline (growth is the safety net against dropping content, the reshape is a claim about one sheet, and the safety net wins), and fewer than 3 vertices is not a shape. `test_zone_polygons.py` (14) + `zoneShapes.test.ts` (25) + `zonePolygonRender.test.ts` (9), the last verified to fail against a bbox punch. | **v41 → v42** |
| 2026-08-05 | **A third duplicate card, from a different mechanism — and the eval cannot see any of them.** One physical cell (`16組`) produced **two MATCHED cards against one canvas marker**: `QTY (QUANTITY)` and `T. Q'TY / 総製作個数`. Unlike the v39 defect this one is **cross-extractor**: the bottom title block's QTY field searches for `T. Q'ty` / `総製作個数`, which *are* the upper-left table's own column header, and `keep_for_title_extraction` excluded only the tolerance box — so the proximity search reached from the title block (ends y≈299) up to the UL label at y≈702 and read the other table's cell. Fixed by excluding `title_upper_left` from title extraction exactly as `tolerance` already was, keeping the "unless also in the title box" guard so an over-wide box cannot blank the title block. See [[Gotcha - Title Block QTY Reads the Upper-Left Table]]. `tests/test_title_input_filter.py` (+4). | — (product defect) | **Measured, and the split between what was and was not measured is the point.** The eval scores **byte-identical to the v38 baseline** over 36 pairs (P 0.78 / R 0.65 / F1 0.713, macro 0.750, attribution 0.806) — real evidence of **no regression**, and **no evidence at all** about the duplicate. `runner.py` drops every `status == "MATCHED"` candidate before scoring, and both duplicate cards were MATCHED, so the scorer's `duplicates: 0` read zero *while the bug was live*. **All three duplicate-row defects to date (v13/v16, v39, v40) were invisible to it by construction** — do not cite that counter as coverage. The fix was verified at candidate level instead: 28 → 27 candidates, the removed one an exact twin of the survivor at the *same coordinates* `[75.25, 273.0]`. Field-level: QTY only, `'4'` → `'NONE'`, both sides; the other 15 title fields byte-identical. | **v39 → v40** |
| 2026-08-05 | **Four checklist items collapsed to one drawing number.** The bottom title block's DWG No. cell is ruled into sub-cells that spell out the number — `M745203N01` is `M745` (Machine Type) + `203` (Unit Code) + `N01` (Part No.) — and each had its own checklist row, all three reading `NONE` on the live pair while the DWG No. carried the value. Suppressed via `COMPONENT_OF_DWG_NO_FIELDS` + `is_component_of_dwg_no` in `utils/text.py`, imported by `marking_builder` rather than restated so the cards and the table cannot disagree; the DWG No. card label drops its five-name sub-header list. See [[Gotcha - Drawing Number Segments Reported as Separate Fields]]. `tests/test_dwg_no_component_rows.py` (18). | — (product defect) | **Measured: eval byte-identical to the v38 baseline again** (P 0.78 / R 0.65 / F1 0.713), which as with v40 is evidence of no regression and — these rows being `MATCHED` — *no* evidence about the noise reduction. Checklist verified directly: **11 rows → 8**, upper-left rows untouched. **Two deliberate non-simplifications, both of which would have been silent losses.** (1) Corroboration is *checked*: the live revision reads `DWG NO: NONE`, so unconditional suppression would leave a changed segment reported by nothing. (2) Matching is *positional*: the first implementation used `value in dwg_no` and **its own test caught that `45` sits inside `M745`203N01 without being a segment** — the same failure that once shipped a green tick in [[Gotcha - Title Field Read Across a Ruled Cell Boundary]]. Also pinned the name collision that makes this class dangerous: the **upper-left** table's `Unit No.`/`Part No.` are standalone fields, and its `Part No.` genuinely reads `203`, so aiming this rule at that table would delete a real field. | **v40 → v41** |
| 2026-08-05 | **A reported scoping bug that was not one — the overlay was lying, the engine was right.** The `DRAWING VIEWS` box visibly swallowed the NOTES / ISO / BOM / TITLE UL boxes on the revision. `views` means "this rectangle minus the sibling zones", and when pinned from a template it is a plain rectangle with the subtraction re-applied at use time by `scope_entities_to_views`; the renderer filled the raw rectangle and so claimed those regions were being diffed as drawing geometry. Fixed in `renderEntities.ts` by subtracting the siblings from the *tint* only — stroke stays whole so the box is still draggable — using a chained even-odd clip per sibling, because chained clips intersect and a single even-odd path would re-fill two overlapping siblings' intersection (BOM vs title overlap is logged on real sheets). See [[Gotcha - The Views Overlay Showed a Region That Is Not Compared]]. | — (UI truthfulness) | **Measured, and the measurement is the finding: the exclusion is doing 83–88% of the work, not a detail.** On `M7452A0N01`, **423 of 508** anchors inside the reference's views rectangle sit in a sibling zone and **492 of 562** on the revision, leaving pools of 85 and 70. On the reporter's own cached audit every note line came back as a `notes_section` card and every `drawing_views` card was a dimension or `２－７キリ` — nothing leaked. **No cache bump and no eval delta: no engine behaviour changed.** `zoneOverlay.test.ts` +5, of which the two that assert the subtraction were **verified to fail against the old renderer**; the suite had never rendered the `views` zone at all, which is why the branch was unpinned. | — (tint only) |
| 2026-08-06 | **Undo/redo unified and moved to the one hook mounted once.** Ctrl+Z undid **two** actions per press: the handler was correct but installed twice, because `useCanvasInteraction` binds to `window` and `TwoDWorkspace` renders `DrawingCanvas` twice. Moved to `useGlobalShortcuts` (mounted once from `App.tsx`), with a single stack in `stores/historyStore.ts` now spanning zone alignment as well as marker moves. Two smaller defects in the same handler: the Delete/Backspace branch compared `e.key === 'delete'` against a key that reports `'Delete'` — dead code that never ran — and the keyboard delete path recorded no history, so fixing the casing alone would have introduced the workspace's only unrecoverable destructive action. See [[Gotcha - A Window Listener in a Per-Pane Hook Fires Once Per Pane]]. | — (product defect) | **Unmeasured by the eval, and it cannot be** — this is desktop interaction state, not engine behaviour, so no corpus number moves. What is established by test: `historyStore.test.ts` and the shortcut tests pin one-undo-per-press and the delete-records-history path. | — | 
| 2026-08-06 | **3D DXF ingestion and the in-pane 2D↔3D toggle removed, entirely.** Built the same day as backend ingestion (Z preserved through the paper-space projection, `3DFACE`/`MESH`/polyface mappers, a `metadata.three_d` summary) plus a per-pane toggle and F1 hotkey in `TwoDWorkspace`; reverted on instruction, including the committed backend work. The feature was gated on ingesting a genuine revised DXF and that gate was never met, so the button's enabled state, the toggle and camera framing on real extents all shipped unexercised. Cache **v43 → v42**, which re-frees v43 for Stage 0.5's own bump. Four ingestion defects are live again **by decision, not oversight** — recorded rather than left silent. See [[Gotcha - 3D DXF Ingestion Was Built and Removed]]. | — (scope) | **Measured: eval byte-identical to the v38 baseline** over 36 pairs (P 0.78 / R 0.65 / F1 0.713) — real evidence the removal caught nothing non-3D, since three files carried co-mingled undo/redo and zone-reshape work that had to survive. Full suite green bar the two known `test_vision_ocr_grounding` failures; `tsc` clean; vitest 205 passed (down from 222 with the 17 `dxfSceneGeometry` tests gone). Also recorded, and it outlives the feature: **`tools/eval.py` can never validate a parser change** — the corpus reads frozen `entities.jsonl` and never re-parses a DXF, so it never reaches `project_mapped_entity`. | **v43 → v42** |
| 2026-08-06 | **Stage 0e's open decision resolved — the eval now measures what users see.** `extract_dynamic_regions_async` gained a `zone_template` parameter with three states: `None` resolves from Mongo (the app, unchanged), `{}` asserts the sheet has no pinned zones, `{...}` applies exactly those with no database access. `overrides_from_template_zones` is the pure half split out of `resolve_zone_overrides`; `tools/eval_corpus.py capture-zones` freezes the fractions into the committed manifest, mirroring the app's lookup order (signature-specific, then global default). The seam takes **fractions, not resolved boxes**, so an offline run still exercises `fractions_to_absolute_bbox` — the conversion whose failure mode is a plausible mirrored zone. Stored **once per sheet signature**: the first cut stored it per side and grew the manifest by 3,330 lines (the same 7-zone block 74 times, since every pair here is one layout) against a fixture the staged plan requires stay "tiny, reviewable, diffable" — keyed by signature it is 47 lines, and presence in that map *is* the capture state, so there is no second flag to fall out of step. One layout captured, covering all 74 sides. `tests/test_offline_zone_templates.py` (7). See [[Gotcha - Zone Templates Vanish in Offline Eval]]. | 0e | **Measured, and it is the largest single move this project has recorded: precision 0.78 → 1.00 (43/43), recall 0.65 → 0.78, F1 0.71 → 0.88, macro 0.75 → 0.86.** All **ten** false positives in the v38 baseline were artifacts of the measurement, not defects in the engine — the eval had been scoring against detector boxes while users see hand-aligned ones. `notes_section`, the weakest category in the project (P 0.47 / R 0.54 / F1 0.50), is now **1.00 / 1.00 / 1.00**; `drawing_views` precision 0.89 → 1.00. Still 0 false positives across 11 zero-finding probes. New baseline `tests/fixtures/eval/baseline-v42.json`. **The refactor was proven inert first** — eval byte-identical to v38 before any template was captured, so the jump is attributable to the zones and not to the code move. **One number fell: category attribution 0.81 → 0.74**, which is the labels going stale, not the engine regressing — see the next row and [[Gotcha - Mutation Labels Predate the Zone Template]]. | — (no engine behaviour changed for the app; the app already applied templates) |
| 2026-08-06 | **A metric degraded while everything it measures improved.** Applying the templates surfaced a `notes_section -> drawing_views: 7` confusion from nothing and dropped attribution 0.81 → 0.74. Cause: `mutator.py:148` builds its zone map with the detection-only `extract_dynamic_regions`, and those regions both place the mutations **and** assign each `ExpectedFinding` its category — so every expected category was decided under different zone boxes than the engine now uses. The engine is right; the label is stale, seven times. Recorded, **not fixed in the same change**: making the mutator template-aware moves the mutation targets too, so every pair becomes a different pair and every detection number moves again, and landing both at once means neither is attributable. See [[Gotcha - Mutation Labels Predate the Zone Template]]. | 0c (debt) | **Measured, and the decomposition is the point: the *correct* count went UP, 29 → 32.** The ratio fell only because 43 findings are now matched instead of 36 — the denominator grew faster than the numerator. Detection metrics are unaffected because the scorer matches on handle then text with category as a *preference*, not a filter ([[Gotcha - The Scorer Is a Differ Too]]). This is the circularity this ledger already flagged — attribution "is not independent of `zone_detector`" — cashing out. **Attribution on mutation pairs is not currently a measure of the engine; do not cite 0.74 as quality and do not chase it.** | — |
| 2026-08-06 | **Human corpus taken from 1 to 7 pairs, and the held-out constraint measured rather than assumed.** All seven ingested `reference` ↔ `FSRS2_kmti` pairs exported, zone-captured and worksheet-generated. Held-out eligibility was checked against `storage/cache/` **before** exporting anything: six of the seven already carry a comparison cache entry and are therefore burned under the guideline's "designate before looking at engine output" rule, so **M745206N01 was exported `--held-out` first**, before any other command touched the corpus. A second sheet signature appeared — `aspect-1.361` on `M745203N01`'s reference side against `aspect-1.414` on its revision — with no template pinned for it, so that side takes the global default scaled onto a differently-shaped sheet ([[Gotcha - Global Default Zone Template & the Aspect Caveat]]); recorded as an annotator note rather than silently absorbed. | 0b | **Measured: 7 / 8 registered, 0 / 8 labelled, 1 / 3 held out.** Payload digests confirm all seven pairs are distinct, but A0/A1/A2 are one drawing family, so the corpus samples **~5 layouts, not 7** — stated because "7 pairs" overstates the diversity every downstream conclusion inherits. Eval unchanged (P 0.98 / R 0.85 / F1 0.91): unlabelled pairs are skipped for having no ground truth, which is the correct behaviour and was verified rather than assumed. **The held-out shortfall cannot be closed with drawings on this machine** — it needs pairs ingested and exported without ever running a comparison. Also found: the held-out pair has no OCR cache *because* nothing has run on it, so offline-readiness and held-out eligibility are in direct tension; the ScanText path is the way out. | — |
| 2026-08-06 | **The mutator scopes with the engine's zones, and the corpus was regenerated at schema v2.** `Mutator.__init__` takes a `zone_template` and builds its regions via `extract_dynamic_regions_with_template` — the **synchronous twin** of the async path, sharing `apply_zone_overrides` so the override policy (safe-zone anchoring, BOM growth, grown-zone outline drop) has exactly one implementation; a mutator applying *nearly* the engine's rules would be the same defect one layer down. `MUTATION_SCHEMA_VERSION` 1 → 2, because **both halves** of a v1 label are stale — v1 pairs were targeted *and* categorised against detector boxes, so they must be regenerated rather than re-scored. All 36 pairs regenerated from the same seeds and operators; same shape (36 pairs, 11 zero-finding, 55 expected findings), so the comparison is like for like. `tests/test_eval_mutator.py` (+4, two verified to fail when the template is dropped on the floor). | 0c | **Measured: recall 0.78 → 0.85 (47/55), F1 0.88 → 0.91, macro 0.86 → 0.87, and the trustworthy match tier grew 15 → 22** (more findings matched by entity handle than by text). One new false positive in `bill_of_materials` — precision 1.00 → 0.98 (47/48) — reported rather than smoothed. **Two findings matter more than the deltas.** (1) **Attribution hit 1.00 (47/47) with an empty confusion matrix, and that is a tautology, not an achievement**: the mutator and engine now scope with identical boxes, so category agreement is true by construction. Its whole history — 0.90 → 0.81 → 0.74 → 1.00 — measured detector-vs-detector, then template-vs-detector, then nothing. **Only human pairs can measure attribution.** (2) **`isometric_view` coverage went 5 → 0, correctly**: the hand-aligned `iso` box holds **zero** comparable entities on either side (measured), because `COMPARABLE_ENTITY_TYPES` is text+dimension and an isometric view is geometry — so the old `isometric_view` F1 of 0.89 was measured on text the detector's looser box swept in. The corpus honestly covers **4 of 6 categories** now. | — |
| 2026-08-06 | **Annotation guideline promoted to `active`; its four open questions resolved and `guideline_version` bumped to 2026-08-06.** Ruled rows: one finding per row when the rows carry independent facts (名称/TITLE), one for the whole value when they are segments of an identifier (DWG No.) — descriptive of two existing bug fixes that went in *opposite* directions. Revision rows: a new one is not a finding, a missing one is, an edited one is. Amendment content → `title_block`, balloon-vs-BOM → `bill_of_materials`, under a new general rule — *label by what the change is about, not where it is drawn*. Bulk: semantic rule plus `is_bulk` at ≥5 entities and a deterministic anchor order, explicitly marked a convention. **A second defect surfaced during the bump and was fixed: the version guard blocked its own remedy** — bumping made every existing label stale, and `mutate` could not load the corpus whose labels it was about to regenerate, nor `verify`/`status` report what needed regenerating. `tools/eval_corpus.py` now loads with `allow_stale_guideline=True` and *prints* which pairs are stale; `tools/eval.py` keeps the strict check, which is the only place a stale label could corrupt a number. `tests/test_eval_corpus.py` (+2). | 0b | **Measured: the eval is byte-identical after the bump** — P 0.98 (47/48), R 0.85 (47/55), F1 0.91, macro 0.87, attribution 1.00, 0 false positives across 11 zero-finding pairs. That equality is the evidence that the four resolutions changed **no mutation label's content, only its version stamp**: all 36 pairs were regenerated under the new version and scored the same. Timing was the deliberate part — settled at 0 labels, so nothing needed re-labelling; the guard's own rule is that a later change is a re-label, not an edit. **One resolution knowingly buys a systematic false positive** (new revision rows), which is how an invisible product behaviour becomes a measured one. | — |
| 2026-08-07 | **The three AI comparison methods removed, backend and frontend** — [[ADR-006 Removing the Three AI Comparison Methods]], closing the two questions [[ADR-004 Deterministic-Only Scope]] explicitly left open ("whether to delete the three methods' code" and "whether the picker should still show them": delete, and no). ~2,100 lines across 12 files: `full_ai_orchestrator`, `live_dxf_orchestrator`, `hybrid_orchestrator`, `crop_verifier`, the `full_ai/` package, `reconciler`, `few_shot_retriever` and three test modules, plus the `_dispatch_comparison` routing table, the `hybrid_candidates_*` cache lever, and the DEV-badged four-button picker in the Create Room dialog. `comparison_method` is now `Literal["rag"]` in `room.py` and all three `schemas.py` sites. **Four things were deliberately NOT removed and are the traps a grep-and-delete pass takes:** `gemini_client.py` (the deterministic path calls `execute_title_block_ocr` — *"remove the AI methods" is not "remove Gemini"*), `image_cropper.py` (used by `orchestrator.py` directly), the canvas `renderMode: 'hybrid' \| 'vector' \| 'raster'` (an unrelated name collision), and the `CONFLICT`/`unverified` statuses (unreachable, but present in cached payloads, and a reader that drops them renders an old audit wrong rather than not at all). | scope | **Measured against the live database before deciding, not assumed: 108 rooms, 8 live, all 8 `rag`.** All 48 rooms carrying a removed method were already soft-deleted, and `list_rooms` filters `is_deleted == False` *in the Mongo query*, so no tombstone is ever fetched or validated — hence no migration. **Eval and engine unaffected: no cache bump** (v42 stands, leaving v43 free for Stage 0.5), because nothing on the deterministic path changed. `pytest tests/ -q` green bar the two known `test_vision_ocr_grounding` failures; `tsc` clean; **vitest 232/232 — the first fully green frontend run in this log**, since rewriting `RoomsView.test.tsx` around the picker's absence also retired its stale `rgb(255,255,255)` assertion. **The finding that outlives the removal: `match_radius_mm` was being swept as an engine constant while tuning the *measurement*.** Deleting `reconciler.py` left the eval scorer as its only reader, which exposed that it decides how the scorer pairs a prediction with an expected finding — sweeping it moves F1 with the engine untouched, the same class as the rejected "sweeping on detection F1 alone". Moved to `eval/scorer.py` as `SPATIAL_MATCH_RADIUS_MM` at its original value (scores byte-identical), pinned out of `_BINDINGS` by test. **The default sweep pass is now 13 constants, not 14.** | — (v42 unchanged) |
| 2026-08-07 | **`rag` renamed `deterministic`, with a permanent compat alias.** The method name is written into the room document, the comparison request and response, the cache filename, the eval CLI and the UI; `"rag"` named a technique the engine does not contain (no retrieval, no LLM), which was tolerable as one default of four and became the system's **entire vocabulary** once [[ADR-006 Removing the Three AI Comparison Methods]] made it the only method. Canonicalised in a new `domain/models/comparison_method.py` — before this the string was simply repeated at each site, which is precisely what let the name outlive its accuracy: there was nothing to rename, only occurrences to find. `"rag"` is folded to `"deterministic"` by a `mode="before"` validator on every input model, so every consumer downstream sees one spelling. | 0.5 (partial) | **Measured, and it retires the reason this was being deferred.** The plan said to do it *at* Stage 0.5's cache bump, "the one moment everything is invalidated anyway", because the method is a path segment of the cache filename. Counted first: `storage/cache/` holds **one real v42 comparison entry** (the second v42 file is a `ref_dwg_id` placeholder), so the invalidation cost is **one re-run**, not a corpus — the coupling was never load-bearing. **No bump taken: v42 stands and v43 stays free for Stage 0.5 itself.** The alias is permanent, not a deprecation window, and the reason is data rather than politeness: **no migration was run, so all 55 `rag` rooms still say `rag` on disk** and removing the alias would make them unloadable. `tests/test_comparison_method_rename.py` (11) pins that, naming the artifact each test protects. Also verified the alias did not become an accept-anything — `hybrid`/`rag_ai`/`ai_vision` still raise. `pytest` green bar the two known `test_vision_ocr_grounding` failures; `tsc` clean; vitest 232/232. | — (v42 unchanged; the filename segment change orphans 1 entry by design) |
| 2026-08-07 | **The ladder re-scoped around the deterministic engine** — [[ADR-007 Re-scoping the Maturity Ladder]], closing the flag [[ADR-004 Deterministic-Only Scope]] raised and [[ADR-006 Removing the Three AI Comparison Methods]] made permanent: *"the rung metric needs re-scoping or retiring; that is not yet decided."* Decided: **re-scoped**. Rungs are no longer ADR-003's LLM ladder — 1 is **Measured** (per-category P/R/F1 over ≥8 **human** pairs; mutation-only explicitly excluded), 2 **Calibrated**, 3 **Retrieval-augmented** (stored human decisions measurably moving output — the learned-dismissal flywheel and the learned overlay, which is the only retrieval on this path), 4 **Learned matching**. The old rung 1's retrieval-recall@5 exit criterion is **retired for good** rather than deferred, and recorded as retired so nobody reconstructs it from ADR-003. Three alternatives were weighed and are in the ADR: retire the metric entirely, reinstate an LLM path, or leave it undecided. | scope | **n/a — no code changed, and deliberately no rung claimed.** The corpus is still **0 / 8 labelled**, so rung 1 has no evidence; `current_rung` stays **0** and `rung_evidence` stays **none**. Re-scoping makes the ladder reachable, not reached — claiming it on the mutation baseline would be exactly the phantom the evidence rule exists to prevent. The structural consequence worth recording: **every rung is now gated on the same resource, human labels**, where ADR-003's four rungs were gated on four different capabilities and so could be attempted out of order. | — |
| 2026-08-07 | **Annotation unblocked, and a validator added.** The six worksheets and label drafts were stamped `guideline: 2026-08-05` while the active guideline is **2026-08-06** — `corpus.py:363` raises on mismatch and `tools/eval.py` keeps the strict check, so **every hour of annotation would have produced labels the eval refuses.** Regenerated with `--force` (all six drafts verified empty first; the no-clobber guard and `--force` flag already existed at `eval_corpus.py:813`, which is why the first plain re-run updated the markdown and left the drafts stale). Added `tools/eval_corpus.py validate` — runs the installer's own `PairLabels.from_dict` plus address resolution against the frozen payload, reports **every** problem in one pass, and is read-only (`label` stays the only command that writes ground truth). `status` now prints a per-pair annotation queue, noting held-out pairs are excluded by the lock rather than missing. `tests/test_eval_corpus_validate.py` (5). | 0b | **Measured in the only terms that apply: 6 / 6 drafts now carry `2026-08-06`, and `status` reports no stale pair.** No engine behaviour changed and no eval number moved. The defect class is worth naming — a version guard that fails *late*, at install time, on work that is expensive to redo. The guideline bump on 2026-08-06 correctly refused to touch existing drafts, and the drafts were empty, so nothing warned. | — |
| 2026-08-07 | **One edited BOM row is one finding.** `marking_builder.inject_bom_markings` appended a marking per **cell** across 5 or 7 columns, against an annotation guideline that says *"A BOM row edited => 1 CHANGED per row, not per cell."* Non-MATCHED cells of a row now collapse into a single finding anchored on the first changed column in `bom_cols` order, with `details` naming every changed column. **MATCHED cells are deliberately NOT collapsed** — they are per-column verification rows a checker signs off on, and the guideline's rule is about findings; folding them away would be a product regression dressed as a metric win. Safeguards 1/2, the weight 2-decimal standardization and the `y < 60` stray-marker filter all stay at cell level, ahead of the collapse, because each is a per-cell judgement. A single-changed-cell row keeps today's exact wording, so the v42→v43 diff is auditable. | — (guideline alignment) | **Measured: eval byte-identical — P 0.98 / R 0.87 / F1 0.92, `bill_of_materials` unchanged at 0.86/0.60/0.71.** The reason is structural and is the finding: **every BOM mutation operator edits a single entity**, so no mutation pair has ever contained a multi-column row edit for the collapse to act on. The corpus cannot exercise this — the same class as [[Gotcha - Mutation Pairs Cannot Exercise a Spatial Constant]] — so it is pinned by `tests/test_bom_row_granularity.py` (7 tests) instead, **3 of which were verified to fail against the per-cell builder** (3 findings where 1 is expected, 4 where 2 are). The ledger's prior claim of "four false positives per edited row, by construction" was **not measured and is not supported**: the live corpus carries exactly one BOM false positive and it is unrelated. Real value is alignment — human BOM labels will be row-level, so the mismatch would have distorted every future human-pair number. | **v42 → v43** |
| 2026-08-07 | **A false negative found, and the ledger's stated suspect was wrong in mechanism and stale in example** — [[Gotcha - A Short Structured Value Suppresses Its Own Zone]]. The open item read *"a single-character deletion goes unreported… prime suspect `marking_reconciler.MIN_FUZZY_LENGTH = 4`"*. `MIN_FUZZY_LENGTH` gates **merging** a REMOVED+ADDED pair into one CHANGED, so failing it yields **more** findings, never zero — it cannot produce a zero-finding symptom, an observation available without running anything. The cited example (`G`) reports correctly today. The real miss: `_collect_structured_text_values` collects every title-block/BOM value into one flat set and excludes matching entities **sheet-wide, by text alone**, with no check that the entity is near the region the value came from. The BOM row was numbered `1`; a standalone full-width `１` in the notes zone NFKC-folds to `1` and was dropped from the notes pool **on both sides**, so its deletion changed a pool it was never in. Fixed with `ComparisonParams.min_structured_value_length = 3`, bound as `orchestrator.MIN_STRUCTURED_VALUE_LENGTH` and swept in both directions (raise it too far and a real `8.65` gets double-reported). `tests/test_structured_value_suppression.py` (3). | 0.5 (partial) | **Measured, and proven by isolating the collision rather than inferred: renumbering the BOM row `1` → `999` — changing nothing else — made the missing `1 REMOVED notes_section` appear.** Eval: **recall 0.85 → 0.87 (48/55), F1 0.91 → 0.92, macro 0.87 → 0.88, `notes_section` recall 0.92 → 1.00 (13/13)**, precision held at 0.98 (48/49) with **0 new false positives and 0 new duplicates** — the real risk, since the fix loosens a duplicate-suppression net in a project with three duplicate-row defects on record. Also produced the first hand-characterisation of *all eight* recall misses: 4 are unreported ADDED text, 2 are section designations suppressed **by design**, 1 was this bug, 1 is uninvestigated. Counting false negatives is not reading them. | **v43** (same bump) |
| 2026-08-07 | **The sweep was measuring a zone regime the product does not use** — [[Gotcha - The Sweep Never Got the Zone Template Seam]]. Found by running `tools/sweep.py` for the first time since 2026-08-05 to answer an open caveat, and noticing its baseline did not match the eval's: **F1 0.68 vs 0.92, same corpus, same commit**, with `[zone_template] Template lookup failed for 'aspect-1.414'` once per pair. `runner.py` passes `zone_templates=(pair.ref.zone_template, pair.rev.zone_template)` — the 2026-08-06 seam that moved precision 0.78 → 1.00 — and `sweep.py` called the same engine entry point with four positional arguments and none, falling back to a Mongo lookup that does not exist offline. **`sweep.py` landed one day before the seam and was never re-run.** No shared call site: two files reproduce the engine differently and nothing compared them. Guarded by `tests/test_eval_sweep.py::test_the_sweep_passes_zone_templates_like_the_runner`, asserted on source because the failure is an omitted keyword argument with no return value to check (verified non-vacuous — one `zone_templates=` occurrence in the file, and it is the call). | 0.5b | **Measured by re-running the full pass (580 s, 14 constants), and the correction is not the one to expect: the flat/not-flat partition is IDENTICAL.** Every previously-flat constant is still flat, the responsive one still responds; the count reads 12 of 14 only because a 14th was added. That is right — the spatial constants are flat because both sides of a mutation pair sit at identical coordinates, a property of the corpus that zone boxes cannot touch, so [[Gotcha - Mutation Pairs Cannot Exercise a Spatial Constant]] was never at risk. **Two things were genuinely wrong.** (1) `changed_similarity_floor`'s spread was understated **2.2×**: 0.139 → **0.305**. (2) The corrected per-value curve shows the default **0.4 sitting at the edge of a cliff** — exactness 0.958 flat across 0.0/0.2/0.4, then 0.917 → 0.796 → 0.653 — not mid-plateau. That is a fragility signal about the one constant this corpus can exercise, and it was invisible in the wrong regime. Confirms too that the constant moves **exactness, not F1** (F1 spread 0.0086), holding up the "sweeping on detection F1 alone" negative result. **Baseline F1 unaffected — the engine never changed, only the measurement.** | — |
| 2026-08-07 | **`min_structured_value_length` swept, converting a stated convention into evidence.** Landed the same day carrying an explicit caveat that 3 was *"a convention, not a measured optimum"*; swept rather than left as a caveat. | 0.5b | **Measured, and the shape is a step, not a curve: F1 1 → 0.913, then 2 / 3 / 4 / 6 → 0.923, identical.** The only transition is 1 → 2, which is the defect itself; above 2 this corpus cannot distinguish any value, so **3 is conservative and arbitrary within [2, ∞)** and this corpus cannot make it an optimum. **The stated risk did not reproduce, and that is itself informative:** at floor 6 the corpus's own structured values `8.65` and `5.31` (4 chars) leave the net entirely and F1 does not move — meaning the spatial `exclude_bboxes` are doing nearly all the work here and the value net is close to redundant above length 1. Recorded as **untested, not shown safe**: the case the net exists for is a title value sitting *outside* its zone box, and this corpus has none. It is the **second of 14 constants** the mutation corpus can exercise at all, and for the same reason as the first — it gates text, and text is what mutations edit. | — |
| 2026-08-07 | **Stage 1a — learned dismissals are structured and category-scoped.** `vault_sync` gained `LearnedDismissal{pattern, category, match_mode}` and `get_learned_dismissal_rules(category=...)`; `match_mode` is `normalized` at ≥3 characters and `exact` below, folded through one NFKC+casefold definition shared with the orchestrator's normaliser. The orchestrator previously flattened **every** category's patterns into one set and applied it to the **drawing_views** pool, so a `title_block` dismissal suppressed drawing geometry while a `drawing_views` dismissal never reached the notes or isometric pools — the flywheel closed for one of three generic zones. Each pool now receives only its own category's rules. `get_learned_dismissals() -> List[str]` is unchanged and not deprecated; several tests pin it. `tests/test_learned_dismissal_scope.py` (10). | 1a → rung 3 | **Measured: zero. Eval byte-identical — P 0.98 / R 0.87 / F1 0.92 — and that is reported rather than smoothed.** The live vault holds **2** patterns, `8` (drawing_views) and `ユニットNo.` (title_block); the latter matched nothing in the drawing_views pool, so scoping it out moved nothing. This is the Stage 0.5 limit again — not enough real data to measure a correct change — and it is why rung 3 is gated on label volume like every other rung. Justified by the hazard and by test, not by a metric move. Worth recording that `8` is **a single digit applied sheet-wide**: the same defect class as the structured value `1` above, sitting in the one filter driven entirely by stored human decisions. | — (no behaviour change on this corpus) |
| 2026-08-07 | **R0 — the fake retrieval stack deleted** ([[Standards Knowledge — Staged Plan]], [[ADR-008 The Second Brain — Retrieval-Only Local Knowledge]]). **This is the standards-audit pipeline, not the comparison engine** — the second live pipeline [[RAG Reference Architecture — Gap Analysis]] found running on SHA-256 noise, tracked by no ledger until now. **Nine modules removed**: `local_embedding_model`, the whole `vectorstore/` package (`lancedb_manager`, `embedding_provider`, `retrieval_engine`, `standards_indexer`, `vector_persistence`), `drawing_similarity_engine`, and `geometry/{vector_geometry_index,geometry_search_engine}`. Four callers rewired **before** deletion, since `lancedb_manager` had two live importers: the `lessons_learned` write in `audits.py`, the zero-caller `POST /admin/standards/reindex` in `standards.py`, the vector query in `audit_orchestrator.py` (the pre-existing Mongo regex fallback is now the only path), and the indexing call in `standards_loader.py` (chunks still persist to Mongo). **Kept deliberately:** `graph_builder.py` and `explainability/` — zero callers, but honest; dead code is a separate cleanup from fake code. Guarded by `tests/test_no_fake_ai_capability.py` (12), which is AST-based rather than a text scan **because the tombstone comments quote the defect they replace**, so a grep for `default_rng(sha256(...))` matches the very comments explaining it is gone. | R0 (Second Brain) | **Measured: zero behavioural change — and that is the finding, not a caveat.** Eval byte-identical: **P 0.98 (48/49) / R 0.87 (48/55) / F1 0.92, macro 0.88, 0 duplicates**, per-category unmoved, 36 pairs in 12.3 s with zero non-local sockets. It *must* be zero, and proving why is the point: the write path **never wrote a single record** — `audits.py` called `embed_text` (singular) against a provider defining only `embed_texts`, an AttributeError swallowed by `except Exception` into a warning since the code was authored — while the read path queried that permanently empty index and returned nothing, which is indistinguishable from "no relevant lessons". Deleting a writer that never wrote and a reader that always read empty is **observationally identical to keeping them**, which is precisely the argument for deletion over repair. See [[Gotcha - A Swallowed AttributeError Made a Write Path a Permanent No-Op]]. **The guard test then found a tenth fake outside the AI package**: `BackupManager.create_secure_backup` created an empty directory, logged *"System state successfully archived"* and returned a path to a .zip it never wrote — the compression and AES-256-GCM encryption were a comment beginning "In production:". Now raises. Its test had monkeypatched **both** methods and asserted on its own lambdas, so it passed without executing a line of the class. `pytest` **759 passed / 3 skipped**, the 2 known `test_vision_ocr_grounding` failures unchanged. | — (no bump: standards-audit path only; neither spatial matching nor zone extraction touched) |
| 2026-08-07 | **R1 — real lexical retrieval, on the standards-audit track.** `infrastructure/retrieval/`: `encoder.py` (pluggable seam, so dense must *win a measurement* before it ships), `lexical.py` (char n-gram TF-IDF + BM25 + RRF), `store.py` (exact brute-force cosine over a scipy CSR matrix + JSONL sidecar + manifest), `index_builder.py`, `service.py` (the async Mongo/vault edge, kept separate so the builder stays synchronous and testable without a database). Three collections: `standards` (StandardChunk), `domain_rules` (vault notes by heading — the bundle is R3, so the source is a *function* not a path, which is the seam R3 needed anyway), `lessons` (supervisor-confirmed violations). Wired into `audit_orchestrator` with the old substring match kept as an explicit fallback, into `ingest_standard` off-thread, and into startup. `char_wb`/(2,4) deliberately mirrors `finding_classifier.py` so there is **one definition of 'similar text'** in this system. **Deviation recorded: sparse `.npz` where the plan said `.npy`** — char n-gram TF-IDF is inherently sparse and a dense row would be 256 KB of 99.9% zeros. 34 new tests. | R1 (Second Brain) | **Measured against the exit criterion, clause by clause: ranked chunks with scores and citations, offline under the eval runner's own `no_network()` guard, in 6–9 ms against a 100 ms budget.** Eval byte-identical — P 0.98 (48/49) / R 0.87 (48/55) / F1 0.92, macro 0.88 — confirming nothing leaked across the track boundary. **What is *not* measured is retrieval quality, and that is R2's entire point**: there is no recall@5, so `tfidf` is the default over BM25 and RRF by argument rather than evidence, `min_score` is 0.0 rather than a tuned threshold, and `domain_rules`/`lessons` are built but **not blended into the audit prompt** — merging three ranked lists is a tuning decision and R2 is sequenced ahead of it deliberately. One qualitative result worth recording because it is why char n-grams were chosen: `ユニット No` retrieves the indexed `ユニットNo.` at 0.351 and ranks it first, where a word tokeniser scores it zero. Two defects found by building this: [[Gotcha - A Guard Test's Failure Path Had Never Run]] and [[Gotcha - Our Own Punctuation Broke on the cp932 Console]]. `pytest` **793 passed / 3 skipped**, same 2 known failures. | — (no bump: standards-audit path only) |
| 2026-08-07 | **R2 — the retrieval metric built, and it reports that there is nothing to measure.** `infrastructure/retrieval/{metrics,labels,evaluate}.py`, `tools/retrieval_eval.py`, [[Retrieval Annotation Guideline]], and a committed **census baseline** (`status: "no-measurement"`). `recall@k` / `MRR` / `precision@k` with counts beside every rate per the plan, **plus a chance floor beside every rate**, which is the stage's own addition and the thing that makes a number readable. Four gates must pass before any verdict is rendered: >=30 queries, chance floor <=0.25, lift >=0.15, and no synthetic labels. `provenance` is a required field on every label so a generated one can never be mistaken for a judged one, and the tool **refuses** to write a baseline from a run containing synthetic labels. 21 tests. | R2 (Second Brain) | **Measured, and the measurement is a census rather than a score: the corpus is empty.** `standard_documents` **0**, `standard_chunks` **0** — no standard has ever been uploaded. 1,322 audit violations exist and **every one is unreviewed** (0 approved, 0 rejected), so `lessons` is empty too; only `domain_rules` has anything, 6 client-local chunks. This is a live database — 8,055 entities, 108 rooms, 58 sessions — so the standards subsystem has simply never been used. **The plan predicted this risk and prescribed the response** (*'record it as a negative result and stop, rather than reaching for dense embeddings to rescue the number'*); the answer is stronger than predicted, in that the lever is not weak but unconnected. It also sharpens R0's finding: `lessons_learned` was never written because of a swallowed `AttributeError`, **and** because the review endpoint has never been called once. The harness proves itself on the 6-record corpus by **refusing that run**: `recall@5 = 1.00 (6/6)` prints `NOT INFORMATIVE`, naming all three failed gates — a shuffling ranker scores 0.83 there. Two design defects were caught by running it rather than reading it, both now pinned: `informative` ignored provenance (so a synthetic run printed a confident verdict directly above the caveat contradicting it), and the corpus gate was `N > k`, which a 6-document corpus passes at k=5 — replaced by the chance floor. **No parameter was tuned in R1 or R2**, as the exit condition requires. `pytest` **814 passed / 3 skipped**, same 2 known failures. | — (no bump: standards-audit path only) |
| 2026-08-10 | **The standards knowledge track retired at R2, and renamed on the way out** — [[ADR-009 Retiring the Standards Knowledge Track]], amending [[ADR-008 The Second Brain — Retrieval-Only Local Knowledge]]. R3 (two-tier bundles) and R4 (knowledge sync) are **retired, not deferred**; R4 had been `⏸ DEFERRED to prod` and the difference is the point — a deferred stage waits for a trigger, a retired one waits for nothing. The owner's decision on product grounds, taken after R2's census: **the standards-audit pipeline is not the product.** Three alternatives were weighed and are in the ADR (load real standards then label ~30 queries; narrow R3/R4 to the 6-record `domain_rules` tier; build both stages anyway). **Nothing was deleted.** `infrastructure/retrieval/` stays — removing it would drop the audit path back to substring matching *and* destroy the instrument that produced the negative result. ADR-008's decisions 1 (retrieval-only) and 5 (LAN server rejected) stand; 2 and 3 are retired unbuilt; 4's payload lapses as a build item and survives as a constraint. **A concrete reopening condition is recorded** (`standard_chunks > 0` **and** ≥30 human labels clearing the four gates) so "retired" does not decay into "forgotten". **Renamed in the same change:** the track was called *"the Second Brain"*, which collided with the vault — the MOC is titled *"AI-2D-Checker System Second Brain"* and `vault_sync.py`/`auto_doc.py` both say *"the Obsidian Second Brain"* — so *"the Second Brain is retired"* read as *"the vault is retired"*. **"Second Brain" now means the vault and only the vault**; the subsystem is the **standards knowledge track**. Notes renamed (`Standards Knowledge — Staged Plan`, `Standards Knowledge — Rule Bundle Format`); **ADR-008 keeps its title deliberately**, because an ADR records what was decided *and under what name*. Earlier rows in this log keep their original `(Second Brain)` stage tags — this table is append-only, and rewriting history to match a later rename is the opposite of what it is for. | R3/R4 (standards knowledge) — retired | **n/a — no code changed, and no number moved because none exists to move.** The measurement this rests on is R2's census (row above), not a new one. **What this entry exists to prevent losing: R3 carried a live comparison-engine defect, and retiring the stage would have orphaned it.** `AutoDocEngine.process_feedback_event` counts dismissals with **no `client_name` filter** and then files the rule under whichever client tripped it — cross-client contamination in the exact mechanism ADR-008's overlay tier was meant to prevent, and with that tier retired **nothing else prevents it.** Re-homed to the unblocked-engineering list above. **A second defect in the same six lines, found while confirming the first:** the count sits inside `except Exception: dismiss_count = getattr(feedback, "_mock_dismiss_count", 3)`, so **any** DB error defaults the count to exactly the N≥3 promotion threshold and a single dismissal writes a permanent rule — the [[Gotcha - A Swallowed AttributeError Made a Write Path a Permanent No-Op]] class pointed the other way, and it writes into `08 - Client Domain & CAD Rules/`, the only vault folder that is a runtime input. Both are unfixed as of this entry. **Also reversed and recorded as a cost:** ADR-008's headline consequence was *"the standards-audit pipeline gets an owner"* — it has none again. What makes that survivable is R0+R1: it now reports `MISSING`/`EMPTY`/`STALE` instead of inventing answers, and `tests/test_no_fake_ai_capability.py` keeps it that way. | — (no bump: nothing on the deterministic path changed; v43 stands) |
| 2026-08-10 | **Generation permitted, narrowly and for the first time since ADR-006** — [[ADR-010 Grounded LLM Summarization of Comparison Results]], amending [[ADR-008 The Second Brain — Retrieval-Only Local Knowledge]] decision 1 (*"RAG without the G"*). Decision only; **no code written.** The product shape the owner stated is *ingest → compare → summarize → learn*, and step 3 was forbidden by two ADRs. **The distinction that unlocks it without reversing [[ADR-006 Removing the Three AI Comparison Methods]]: that ADR's argument was that an LLM must not decide *what changed*, and it stands.** This puts a model strictly downstream of a complete deterministic finding list — it composes, it never detects. Six decisions: findings stay the product of record and the summary is derived/disposable; the model gets the structured finding list **only** (no images — an image lets it describe something not in the list, reintroducing the hallucination surface through a side door); **deterministic verification gates display** — cited ids must resolve, counts must match, and **every non-`MATCHED` finding must be mentioned or explicitly grouped**, else the summary is *withheld* and the existing template renders instead; absence is normal operation; **own endpoint, own fixed-field schema** per constraint 1 / [[ADR-002 Decoupled Zone Bounding Box Endpoint]]; cached by finding-list digest, **not** under `COMPARISON_CACHE_VERSION`. | — (decision) | **n/a — no code changed, and the ADR explicitly declines to invent a quality metric.** There is no summary-quality score and no corpus to build one from, so it ships behind a flag, **off by default**, with the deterministic template as a permanent fallback rather than a legacy path. **"Verification passes" means the summary is not lying about the finding list — not that it is good**, and the ADR says so in those words. What *is* mechanical is the grounding contract. **It also surfaced a live hole in [[ADR-005 Local-Only Processing with Cloud Licensing]]** that is now recorded there: `execute_title_block_ocr` **already sends image crops of the customer's drawing** to Gemini on a cache miss (`orchestrator.py:553`), with no flag — a larger disclosure than the finding text this ADR gates, and one ADR-005 has never covered, while its only egress amendment narrows the claim for knowledge sync, a feature retired before it shipped. | — (v43 stands) |
| 2026-08-10 | **The review UI — the finding that `lessons` was empty for two independent reasons, and the second one was a missing button.** `PATCH /audits/violations/{id}/review` had **zero callers in the desktop app**; the endpoint was correct and tested, but every test called it directly and nothing asserted a user-reachable surface did. Built: `ReviewControls.tsx` (Approve / Reject / remarks / change-verdict, wired into the `AuditConsole` violation cards with `stopPropagation` so a verdict click does not toggle canvas selection), `reviewViolation()` in `auditsApi.ts`, an `applyViolationReview` store action that folds in **the values the server stored rather than the ones the click implied**, and a review-status filter with an "N awaiting review" pill. Backend: `resolution_type` threaded onto `AuditViolationResponse` and both construction sites. See [[Gotcha - A Tested Endpoint That Nothing Ever Called]]. | 0b (labels) / R-flywheel | **Measured only in the sense that matters here — the loop is now closable, and the tests prove the contract rather than the absence of an exception.** No engine behaviour changed and no eval number moved: `pytest` same 2 known `test_vision_ocr_grounding` failures, `tsc` clean, **vitest 240/240 (was 232)**. **The second defect is the one worth carrying:** the API returned only `is_resolved: bool`, which reads `false` for *both* "never reviewed" and "reviewed and REJECTED" — a queue built on it could never be emptied. Nasty because `resolution_type` defaults to `None`, so a call site that forgets it returns a **well-formed response asserting the finding is unreviewed**: wrong data, valid shape, no error. `tests/test_violation_review_response.py` (4), **three verified to fail** with the field stripped from the call sites (`{'v-no': None} != {'v-no': 'REJECTED'}`); `ReviewControls.test.tsx` (8), including that a failed save surfaces an error and does **not** report success. **Not verified in a browser** — the console is behind login and needs a session with violations; component behaviour is covered by test instead, and that limit is stated rather than papered over. | — (no bump: no engine behaviour changed; v43 stands) |
| 2026-08-10 | **ADR-010 built — grounded summarization, with the gate that makes it safe.** `infrastructure/audit/summary/` (`models`, `verify`, `generate`, `service`), `GET /audits/sessions/{id}/summary`, `ComparisonSummaryResponse` (its own fixed-field schema, **not** nested into `PhysicalComparisonResponse` — constraint 1 / [[ADR-002 Decoupled Zone Bounding Box Endpoint]]), `SummaryPanel.tsx` rendering **below** the checklist, and `settings.ENABLE_LLM_SUMMARY` **off by default**. The model receives the structured finding list and nothing else — no images, asserted by test, because an image would let it describe something outside the list and the coverage check could not then distinguish that from a real omission by the differ. `SUMMARY_CACHE_VERSION` is a **separate lever** from `COMPARISON_CACHE_VERSION`, keyed by finding-list digest, pinned by a test that bumps the comparison version and asserts the summary cache survives. **Verification runs before the cache write**, and cached summaries are **re-verified on read** rather than trusted. | — (ADR-010) | **Measured on the invariant, and on the guard's own non-vacuity — not on summary quality, which has no metric and is not claimed to have one.** Eval **byte-identical: P 0.98 (48/49) / R 0.87 (48/55) / F1 0.92, macro 0.88** against `baseline-v43.json`, so nothing leaked onto the deterministic path. `pytest` **843 collected**, same 2 known `test_vision_ocr_grounding` failures; **vitest 246/246** (was 240); `tsc` clean; ruff clean on all new files. 20 backend + 6 frontend tests. **The load-bearing check was verified by breaking it:** disabling the coverage rule alone fails **four** tests including the whole-pipeline one, so `test_a_summary_that_omits_a_finding_is_withheld` is protecting something. **Two deviations from the ADR, both written back into it rather than absorbed:** check 2 is enforced on a *structured count echo* rather than by parsing prose — this domain's finding text is full of numbers that are not counts (`板厚 12 -> 14`, `2-7キリ`), and a false withholding costs the user the feature — and the opt-in is *global* rather than per-room, so the default-off property holds but the granularity does not exist. **What is emphatically not measured: whether the summaries are any good.** "Verification passes" means the summary is not lying about the finding list. | — (no bump: nothing on the deterministic path changed; v43 stands) |
| 2026-08-10 | **The highest-severity open item closed: one client's drawing text could be written into another client's rule file, and a database hiccup could write a rule from a single dismissal.** `AutoDocEngine.process_feedback_event` counted dismissals of a pattern **sheet-wide** while filing the resulting rule under `feedback.client_name`, so a pattern dismissed once at each of three clients reached N>=3 and landed in whichever client tripped it; and that count sat inside `except Exception: dismiss_count = getattr(feedback, "_mock_dismiss_count", 3)` — **defaulting to exactly the promotion threshold**, through test scaffolding reachable from production. A count that cannot be taken is now no information and returns `False`; the hook is deleted. **A third defect of the same family was found while fixing them:** the count included **retracted** dismissals, which `trainer.py` already skips, so three taken-back clicks could write a permanent rule — a vault rule being far more durable than a training row. The filter moved into `build_dismissal_filter`, a plain dict, because the suite has no MongoDB and a Beanie-expression filter cannot be inspected offline — which is exactly how the missing clause survived. See [[Gotcha - A Count You Could Not Take Is Not Evidence]]. | — (product defect; comparison-engine input) | **Unmeasured by the eval, and it structurally cannot be** — `tools/eval.py` calls `generate_deterministic_candidates` directly and never loads vault rules, so no corpus number moves in either direction. What is established instead is **mutation-tested**: each of the three defects was re-introduced into the fixed code and the suite caught all three (client clause dropped, retracted clause dropped, fallback restored). `tests/test_audit_feedback.py` 3 → 11. **The pre-existing write test passed *because of* the defect** — it had no database, so the `except` branch substituted the threshold and the write went through; it now stubs the count explicitly, which is the only way a test can tell "three dismissals" from "the database is down". Severity is stated rather than measured: this writes into `08 - Client Domain & CAD Rules/`, the only vault directory that is a runtime input (`get_learned_dismissal_rules()` → `safe_filter` → the zone pools), so a wrong rule here **suppresses real findings** — the false-negative direction, in the system whose headline gap is that false negatives have never been measured. | — (no comparison behaviour changed; vault rules are read at runtime, not cached) |
| 2026-08-10 | **The review queue was still inert on every cached pair, and the entry two rows above was premature.** [[Gotcha - The Cache Served Findings That Existed Nowhere]]. The verdict control shipped, was tested, and did not appear: `perform_drawing_comparison` returns on a cache hit **before** `AuditSession.save()`, `AuditViolation.insert_many()` and the line stamping `diagnostics.audit_session_id`, so **every write that gives a finding a reviewable identity sits on the cache-MISS path**. A hit returns markings the client cannot join to anything, and both the Approve control and the eye toggle disappear together — they gate on the same id. Confirmed against the entry actually on screen: same three Japanese notes, `has audit_session_id: False`, written 09:39 against a field added at 11:53 the same day. **Re-test could not fix it** — it hits the same entry, so backend and frontend both ran new code against old data with nothing on either side saying so. Fixed by treating a cached entry with no `audit_session_id` as a miss: one slow run per stale entry, self-healing. Guarding on the id's presence rather than a version number also catches a run whose persistence threw into its own non-fatal `except`. | — (rung-3 substrate: the `lessons` corpus) | **Unmeasured by the eval, and it cannot be** — `tools/eval.py` calls `generate_deterministic_candidates` directly and never touches the cache or the persistence block, so no corpus number can move; verified anyway, byte-identical. **What is corrected is a claim, not a number:** the 2026-08-10 review-UI row and the What's-next callout both said a supervisor now produces human judgments as a side effect of normal use. That was true only for pairs with no cache entry, i.e. **not the pairs anyone actually reviews** — every drawing already looked at is by definition cached. The judgment count that fix was supposed to start accumulating was **0 until today**, and remains 0 until a supervisor works the queue. No rung moves: verdicts measure precision, never recall ([[Eval Corpus Annotation Guideline]]), so rung 1 is still 0/8 labels. `tests/test_comparison_architecture.py` +2, both directions pinned. | — (**no bump**; the guard heals stale entries on read, so v43 stands) |
| 2026-08-11 | **The canvas finally draws vectors — and `renderMode` is deleted, not flipped.** [[ADR-011 Vector as the Only Render Path]]. The 2026-07-27 direction (full vector rendering, PNG display path dropped, hybrid explicitly declined) had not landed in two and a half weeks because **two default-flips were shipped and reverted** — the second on a correct diagnosis with clean types and a green suite, and it still deleted every DIMENSION from the sheet. Removed: the `drawImage` composite and mipmap selector in `renderEntities.ts`; the `/drawings/{id}/rendering` fetch, the halving mipmap chain and the chunked per-pixel light-theme recolour in `DrawingCanvas.tsx` (~175 lines); the "Ingesting CAD Geometry…" overlay that existed only to cover that download; the `PenTool` toggle; the `hybrid` mode; and the route itself, whose only client was the canvas. **The backend PNG generator stays** — `render_bounds` is matplotlib-autoscale output and every zone template is stored as fractions of it, so deleting the generator is a template-invalidation event, not a cleanup (⛔ recorded as a negative result in the ADR). | — (rendering; no rung) | **Measured before it shipped, which is the entire difference from the two failed attempts.** `tools/render_audit.py` on M745221N01: census **497/518** (the healthy ceiling — 18 non-drawable + 3 clipped), `|dx|` median **0.1148** / p90 0.7216 / max **1.4017**, `width_ratio` median **1.0222**, rotation lost **0**, off-axis **0**. `tsc` clean; **vitest 304/304**; `pytest` **922 passed, 2 failed** — the same two known `test_vision_ocr_grounding` failures, no new breakage. **No eval number moved and none should have:** this is display-only, it touches neither spatial matching nor zone extraction. **What is emphatically not measured is the in-app appearance** — the workspace is behind a login the agent will not authenticate through, so the visual A/B on both sheets and the PDF-export check are stated as outstanding rather than claimed. **The cost accepted and recorded: the escape hatch is gone.** Raster was kept selectable because the ezdxf PNG cannot be missing anything; a drawing the extractor mishandles now renders wrong with no in-app way to see it, and `render_audit.py` carries that load only if someone runs it. **Re-ingestion is a prerequisite** — `render_paths`, MTEXT rotation and the elliptical-arc fix are extraction-time, and there is no re-extract endpoint. | — (no bump: display-only; v44 stands) |

---

## ⛔ Negative results

Ideas measured and rejected, so they are not re-implemented. Per `CLAUDE.md` constraint 4, a
rejected idea is worth as much as one that worked. Expected to fill up quickly — the Stage 0.5 sweep
will reject most candidate constants, and "the defaults were already near-optimal" is a legitimate
and valuable outcome.

| Idea | Verdict | Why |
| :--- | :--- | :--- |
| `marking_reconciler.MIN_FUZZY_LENGTH` as the cause of an unreported single-character deletion | **Wrong hypothesis, and it could have been ruled out without running anything** (2026-08-07) | Carried in this ledger for two days as "prime suspect", and read afterwards as the explanation. It gates `_fuzzy_pairs`, which **merges** a REMOVED and an ADDED into one CHANGED — so a string too short to clear it is not suppressed, it surfaces as a separate REMOVED *and* a separate ADDED. Failing that gate produces **more** findings, never zero. Any zero-finding symptom is upstream of matching entirely: the entity never entered a pool. Two other length gates also look plausible and are also not it — `is_in_margin` (measured `False` on the failing entity) and `spatial_differ`'s `len(txt) > 2` (that only picks anchors for the global offset estimate). The real cause was the structured-value net; see [[Gotcha - A Short Structured Value Suppresses Its Own Zone]]. **Lesson: record why a suspect could produce the symptom, or the hedge is lost and the guess becomes a fact.** Second lesson: the example cited (`G`) reported correctly by the time anyone checked — re-derive the symptom before fixing it. |
| "BOM row granularity costs four false positives per edited row, by construction" | **Overstated — not measured** (2026-08-07) | Written into "unblocked engineering" as a quantified cost and repeated as motivation. The live corpus carries **one** `bill_of_materials` false positive and it is unrelated to row granularity; the multi-column case that would produce the extra findings **does not occur in the corpus at all**, because every BOM mutation operator edits a single entity. The fix was still right — it aligns the engine with the annotation guideline before human BOM labels land — but its justification is alignment, not a measured precision loss. Landing it moved **nothing**: eval byte-identical. |
| Sweeping the 16 tuning constants against the mutation corpus (Stage 0.5's coordinate descent, as planned) | **Rejected — impossible, not merely unreliable** (2026-08-05) · **re-measured 2026-08-07 and the verdict holds** | **The 2026-08-05 run was made in the wrong zone regime** — `sweep.py` never got the `zone_templates` seam ([[Gotcha - The Sweep Never Got the Zone Template Seam]]), so it scored against detector boxes at baseline F1 0.68 while the eval used templates at 0.92. Re-run after the fix: **the flat/not-flat partition is identical.** Every constant that was flat is still flat, the one that moved still moves; the count reads 12 of 14 only because a 14th constant was added. That is the correct outcome and worth stating — the spatial constants are flat because a mutation pair is a drawing and a copy of it, which is a property of the corpus and could not be changed by zone boxes. **Two things were genuinely wrong, though:** `changed_similarity_floor`'s spread was understated **2.2×** (0.139 → **0.305**), and the corrected per-value curve shows the default **0.4 sitting at the edge of a cliff** (exactness 0.958 flat to 0.4, then 0.917 / 0.796 / 0.653) rather than mid-plateau — a fragility signal about the one constant this corpus can exercise, invisible before the fix. Original reasoning below, unchanged: | Measured: **13 of 14 constants are flat across their entire declared range**, and the cause is structural. A mutation pair is a drawing and a copy of it, so both sides share one coordinate system exactly — 253 of 253 comparable entities at identical coordinates, versus 0 of 11 on the human pair, which is a re-trace. Distance is zero, so every matching radius succeeds on the first tier and the twin/fuzzy tiers are unreachable; `reconcile_relocated_markings` never engages because nothing is relocated. The plan's concern was that a mutation-only sweep would *fit* the constants to the mutator. The real risk is worse: it reports them **inert**, which invites deleting them. Only `changed_similarity_floor` responds, because it gates text and text is what mutations edit. See [[Gotcha - Mutation Pairs Cannot Exercise a Spatial Constant]]. |
| Category-attribution accuracy on mutation pairs, as a measure of the engine | **Rejected — it is structurally circular, and now provably so** (2026-08-06) | Ground truth for a mutation pair's category is `ZONE_CATEGORY[zone containing the target]`, computed by the mutator's own zone map. Once that map was made to match the engine's — the correct fix for [[Gotcha - Mutation Labels Predate the Zone Template]] — attribution went to **1.00 (47/47) with an empty confusion matrix**, because agreement is true by construction for any entity in exactly one zone. The full history is four numbers and none of them describe the engine: **0.90** (detector-vs-detector, three sheet layouts), **0.81** (one layout), **0.74** (template-vs-detector *disagreement*, after the engine moved and the labels had not), **1.00** (nothing). A metric that reaches a perfect score by construction has told you it was never independent. Only human-labelled pairs can measure attribution, because only a human assigns a category without consulting `zone_detector`. Do not cite 1.00, and do not read a future drop as an engine regression. |
| The corpus's `isometric_view` coverage | **Withdrawn — the old number was measured on the wrong content** (2026-08-06) | Making the mutator template-aware took expected `isometric_view` findings from 5 to **0**, which looked like lost coverage and is in fact a correction. Measured: the hand-aligned `iso` box contains **zero** comparable entities on either side. `COMPARABLE_ENTITY_TYPES` is text + dimension and an isometric view is geometry, so there is nothing in the correct box for any operator to target. The five findings the old corpus carried were landing on text the *detector's* looser box swept in and the user's box excludes — meaning the previously reported `isometric_view` **F1 of 0.89 was never about the isometric view.** The corpus now honestly covers 4 of 6 categories; both gaps (`isometric_view`, `other_engineering_references`) are structural rather than unfinished. |
| Treating the eval's `duplicates` counter as coverage for duplicate checklist rows | **Rejected — the metric cannot see the defect class** (2026-08-05) | Assumed while diagnosing the v40 QTY duplicate, and false. `runner.py` builds predictions from candidates with `status != "MATCHED"` — correct for precision/recall, since scoring MATCHED checklist rows would put precision near zero on a clean run. But **every duplicate-row defect this project has found surfaced as a *MATCHED* pair** (cache v13/v16; v39's bilingual UL split, flipped to MATCHED by the bilateral corroboration guard; v40's cross-extractor QTY). All three sat in the population the scorer discards, and `duplicates: 0` was reported throughout — including on runs where the bug was live and visible in the UI. The counter is real, but it only covers duplicates among *reported findings*. Measuring the MATCHED kind needs a distinct check — two rows in one zone with the same normalized value and the same coordinates — which does not exist. See [[Gotcha - Title Block QTY Reads the Upper-Left Table]]. |
| Sweeping on detection F1 alone | **Rejected — measured wrong** (2026-08-05) | The first sweep run reported **14 of 14** constants flat, i.e. "nothing in this engine is connected to anything" — contradicted by a passing test proving the same override changed real engine output. Both were right: the scorer matches a finding to its label *before* comparing status, so a constant that flips CHANGED into ADDED+REMOVED reshapes every verdict without moving detection by a thousandth. `Measurement` now carries **exactness** alongside F1, and `distance()` takes the max rather than the mean so a large move in one metric cannot hide behind a flat other. |
| "Expect failures" from the 3 never-collected `services/backend/tests/` files (Stage 0g) | **Wrong prediction** (2026-08-05) | All 10 relocated tests passed on first execution. The plan assumed code that had never been run must have rotted; what had actually rotted was the *collection path*, not the assertions. One genuine problem was found, but a different one: two of the three files asserted Japanese tolerance keywords against the **real** `08 - Client Domain & CAD Rules/`, which is gitignored — so they tested one developer's filesystem and would have failed in CI for a reason unrelated to the code. Both now inject a vault path, which `VaultSyncManager.__init__` already supported. Lesson: "never executed" predicts nothing about whether the assertions hold; run it before planning around the answer. |
| Copying the existing `finding_classifier.joblib` into its new home during Stage 0h | **Rejected** (2026-08-05) | Two copies on disk with nothing recording which is authoritative, and the choice re-made on every read. A read-order fallback (new location → vault) plus writes that only ever target the new location does the same job: the next retrain migrates the artifact by itself, there is no window where the model is missing, and no install needs a script run against it. The deprecated read logs a warning naming both paths, so the situation is visible rather than inferred. |
| Populate `text_similarity` / `match_distance` / `is_numericish` client-side in `CorrectionControls.tsx` — recorded above as Stage 0a item 3, "degraded labels that cannot be retroactively repaired" | **Rejected — the premise was wrong** (2026-08-05) | The nulls are not a defect and the 21 existing labels are not degraded. `feature_extractor.build_feature_row` derives all three from the raw texts and coordinates whenever they arrive as `None`, and the **inference** path (`features_from_marking`) never supplies them either — so `null` from the client is precisely what keeps training and inference on one definition. Computing them in TypeScript would introduce train/serve skew: there is no `SequenceMatcher` and no `SpatialDiffer._normalize_text` in JS, so the training-side number would systematically differ from the inference-side one. `ChecklistPanel.tsx:101-104` already said so; `CorrectionControls.tsx` was simply missing the comment, which is what made it look like an oversight. Action taken: the comment was added and the equality pinned by `test_training_and_inference_agree_on_the_derived_features`. |
| Replay evaluation over `storage/cache/` | **Rejected before implementation** (2026-08-05) | Of 36 cache files, every `gemini_comparison_*` is method `rag`, most are test placeholders, only 2 are real v37 entries, and there are **zero** `hybrid` / `rag_ai` / `ai_vision` entries. There is no LLM output in the repo to replay. Superseded by: call the pure `generate_deterministic_candidates` directly, and build a record/replay cassette for the LLM paths. |
| Contrastive fine-tuning of an embedding model on feedback | **Rejected for now** (2026-08-05) | Infeasible at 21 labels. The binding constraint at every rung is label count, not model class. Superseded by a reranker over the existing `FindingClassifier` machinery. Revisit above ~2000 labels. |
| Gemini supervised tuning | **Rejected for now** (2026-08-05) | Breaks offline capability, cannot ship in the Tauri bundle, needs Vertex-side infrastructure, and tunes to noise at ~300 examples. Decisively: **the default method contains no LLM at all.** Revisit only if `hybrid` becomes default *and* labels exceed ~2000. |
| Building R3/R4 — two-tier rule bundles and knowledge sync — over the existing corpus | **Rejected, and the track retired with it** (2026-08-10, [[ADR-009 Retiring the Standards Knowledge Track]]) | Both stages are machinery for *moving rules between machines*, and the census says there is nothing to move: the vendor baseline tier has no content and `standard_chunks` is **0**. Building distribution for an empty payload is the identical error to building retrieval over an empty index, one stage later and considerably more expensive to unwind. Two narrower variants were also rejected: scoping R3/R4 to `domain_rules` alone (**6 records do not need a distribution format, a two-tier resolver or a version-pinned bundle** — `VaultSyncManager` already reads them from markdown), and building both stages on the bet that content arrives later (the error the whole track existed to correct, one layer up). **The decision that made this a stop rather than a pause is a product one and is recorded as such** — the measurement establishes that the corpus is empty, not whether filling it is worth doing. Reopening condition in the ADR, stated concretely so "retired" cannot decay into "forgotten". |
| Improving retrieval quality on the standards-audit pipeline | **Not a lever — the corpus is empty** (2026-08-07, R2) | The census, run against the live database: `standard_documents` **0**, `standard_chunks` **0**, and 1,322 audit violations of which **0 have ever been reviewed**. Only `domain_rules` holds anything (6 client-local chunks). Every hour spent on encoders, `ngram_range`, rerankers or dense embeddings would move a number that does not exist. **The fix is data — upload standards, review findings — not engineering.** Recorded here so the next agent reads it before optimising retrieval, which is the natural and completely wasted next instinct. |
| Reporting `recall@5` without a chance floor beside it | **Rejected as a reporting format** (2026-08-07, R2) | The smoke run scores `recall@5 = 1.00 (6/6)`, which reads as a triumph. A ranker returning documents in *random order* scores **0.83** on that corpus, because it holds 6 documents and k is 5. Counts alone (`6/6`) do not reveal this; only the floor does. Every rate now prints its chance value and the lift, and no verdict is rendered when the floor exceeds 0.25. This is the same failure the whole track exists to correct — a plausible number that measures nothing — arriving through the *measurement* rather than the model. |
| Repairing the fake embedding stack instead of deleting it | **Rejected** (2026-08-07, R0) | The obvious move was to swap `local_embedding_model` for a real model and keep the surrounding `vectorstore/` structure — it was already shaped like a working retrieval pipeline. Rejected because **the shape was the liability, not the missing model.** A hash-seeded vector is finite, normalized and deterministic, so cosine over it returns ranked scored results and *nothing downstream can tell* — which is why it survived months in production while a stub would have been found in a day. Repairing would also have started writing supervisor free-text `remarks` into a fake index. The seam is kept in the *design* (brute-force numpy cosine is exact and ~1 ms at this scale, and returns as R1's `store.py`); the code is not. See [[ADR-008 The Second Brain — Retrieval-Only Local Knowledge]]. |
| Guarding "no fake capability" with a text/grep scan | **Rejected** (2026-08-07, R0) | The first attempt scanned source for `default_rng` near `sha256`. It failed immediately — on the **tombstone comments left at each deletion site**, which quote the defect precisely so future readers know what was removed. A guard that punishes documentation of a defect is worse than no guard. Replaced with an AST pass, which discards comments and leaves executable code plus docstrings: **a docstring is a module's claim about itself; a comment recording why something was removed is history.** |
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
