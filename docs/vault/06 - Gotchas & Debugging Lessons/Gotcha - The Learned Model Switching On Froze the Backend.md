---
title: Gotcha - The Learned Model Switching On Froze the Backend
type: gotcha
tags: [gotcha, learning, event-loop, concurrency, performance, race-condition, hitl]
status: active
date: 2026-08-17
cache-version: n/a (no comparison cache involvement)
related: [Gotcha - Learned Corrections Model and Post-Cache Inference, ADR-012 Indexing Human Judgement as Retrieval Collections, Gotcha - The Cache Served Findings That Existed Nowhere]
---

# Gotcha — the learned model switching on froze the backend

**Class:** event-loop blocking, triggered by a data milestone rather than a code change ·
**Found:** 2026-08-17, reported from live use as *"Connection Lost / Reconnecting every time I add
a verdict or correction"*

---

## Symptom

Every supervisor verdict and every correction produced a **"Connection Lost"** banner in the
desktop app, followed by a reconnect. Reliably, on a **single** click — not only under rapid
clicking, which is what ruled out the concurrency explanation early.

**Nothing had changed in the verdict code path.** That is the whole shape of this bug.

## Cause

Three facts, each cheap to check and only meaningful together.

**1. The disconnect threshold is 3 seconds.** `connectionStore.checkHealth` polls `/health` every
5 s with a 3 s `AbortController` timeout. Any event-loop block longer than that *is* a disconnect,
whatever caused it.

**2. The retrain runs on the event loop.** `review_violation` queues `train_from_feedback` through
FastAPI's `BackgroundTasks`, which runs an **async** task on the loop — not in a thread. Everything
after its one `await` was synchronous: `build_bundle` (fit + cross-validate), `save_bundle`
(joblib + JSON), `_write_model_card`, `holder.reload()` (joblib read).

**3. `build_bundle` had recently become expensive.** Measured on the live corpus, three
consecutive calls in one process:

```
build_bundle call #1:   7.279s
build_bundle call #2:   7.269s
build_bundle call #3:   7.218s
```

Not import cost — **7.2 s every call.**

### Why it started without a code change

`_cv_accuracy` — a 3-fold `StratifiedKFold` that fits a model per fold and then calls
`predict_one` **per test row** — sits inside the branch that only runs once the verdict head
actually activates:

```python
if len(verdict_labels) >= config.MIN_TRAIN and len(set(verdict_labels)) >= 2:
    if minority_share >= config.MIN_MINORITY_SHARE:
        verdict_clf = FindingClassifier().fit(verdict_rows, verdict_labels)
        metrics["verdict_cv_accuracy"] = _cv_accuracy(verdict_rows, verdict_labels)
    else:
        ...abstain
```

Below the balance floor `build_bundle` abstains and returns in milliseconds. The corpus crossed it:
**112 verdict labels, 71 / 41, minority share 0.3661** against a 0.30 floor.

**So the cost arrived with the milestone.** The learned verdict head switching on is a goal this
project has tracked for weeks — [[00 - AI Maturity Status]] called it *"the cheapest unclaimed win
in the project"* — and the moment it was reached, every verdict began freezing the backend for 7
seconds. No commit correlates with the regression, because none caused it.

## Fix

**The retrain's whole synchronous half moved into a worker thread** (`asyncio.to_thread`), which
is the rule `infrastructure/retrieval/service.py` already states for indexing and had learned the
hard way: *"All CPU work is offloaded, because fitting a vocabulary over the corpus blocks the
event loop for its whole duration."* The retrieval layer knew this; the learning layer did not.

Measured after, with a 50 ms heartbeat coroutine watching the loop during a real retrain:

```
TRAIN_TOTAL=7.514s
WORST_EVENT_LOOP_STALL=0.058s
```

The work still takes 7.5 s. The loop no longer notices.

### Four smaller defects fixed alongside, all on the same path

- **Two retrains could overlap.** Both fit a model and write the same two files; now serialised
  behind `_TRAIN_LOCK`, so the last correction wins rather than whichever thread finished last.
- **The bundle and the index were written in place.** `review_violation` also rebuilds the
  `lessons` index on every verdict *through a worker thread*, so two verdicts genuinely ran
  `VectorStore.write` in parallel — able to pair one run's matrix with another run's records.
  `load()` already *detected* that (`matrix.shape[0] != len(records)` → `STALE`) but nothing
  prevented it, and a STALE index silently drops the audit path to substring matching. Both the
  model bundle and all three index files are now written to a temp path and `os.replace`d, and
  `lessons` rebuilds are serialised per collection.
- **`LearnedModelHolder.reload()` published a null window.** It set `_bundle = None` before
  re-reading, so a comparison running on the loop while a retrain reloaded from a worker thread
  could see the model as absent and silently skip the learned adjustment. It now reads into a
  local and publishes in one assignment.
- **67 log lines per verdict.** `_collapse_duplicate_texts` logged a WARNING *per dropped
  duplicate*, which is fine for a startup build and pathological for a collection rebuilt on
  every click. Now one aggregate line with a bounded sample of citations —
  `test_the_drop_is_reported_rather_than_swallowed` pins that the citations stay traceable, and
  it correctly failed when the first attempt moved them wholesale to DEBUG.

## Two things measured and found innocent

Recorded because both were plausible, and guessing at either would have cost hours:

- **The cp932 logging storm.** Every duplicate-drop warning contained an em-dash, which the
  Windows console cannot encode, so each raised inside `Handler.emit` and printed a traceback.
  Real, and **0.063 s for 67 warnings** — nowhere near the budget. Fixed anyway (the server's
  logger now reconfigures stdout with `errors="replace"`, a guard `tools/retrieval_eval.py` has
  carried for months), because the *log lines* were being lost, not because it was slow.
- **The in-request index rebuild.** `await rebuild_lessons_index()` runs before the response:
  **0.096 s.** Not the cause.

## Lessons

- **A performance cliff can be triggered by data, not by code.** `git log` cannot find this
  regression; nothing in it changed. The trigger was the corpus crossing a threshold that turns on
  an expensive branch. When a symptom appears with no correlating commit, ask what *data* crossed
  a line.
- **`BackgroundTasks` is not a thread.** An async background task runs on the event loop, so
  "backgrounded" bought nothing here. The name is the trap.
- **The gate that protects quality can also gate cost.** `MIN_MINORITY_SHARE` exists to stop a
  skewed head silently suppressing findings. It also, incidentally, was the only thing keeping
  `_cv_accuracy` from running — so the safety gate was hiding a performance cliff behind it, and
  both were released at once.
- **Measure the candidates you are about to fix.** Two of the three suspects here were real
  defects and neither was the cause. Timing them took minutes; fixing the wrong one confidently
  would have taken a day and left the symptom in place.
