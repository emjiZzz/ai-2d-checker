---
title: Gotcha - A Patch on a Method Nobody Calls Fails Silently
type: gotcha
tags: [gotcha, testing, mocking, beanie, ground-truth, manual-check, corpus, database]
status: fixed 2026-08-25. 12 of 13 failures resolved; the 13th is a named `xfail(strict=True)`
  awaiting a live OCR capture (owner's call). Suite runtime 11 min -> ~2 min as a side effect.
cache-version: n/a — no extraction, comparison or `render_bounds` change.
related: [Gotcha - Three Quoted Figures That No Command Could Reproduce, Gotcha - A Verdict Mapping That Contradicted Its Own Comment, Gotcha - Making the Text Layer Visible Showed What Being Invisible Had Hidden]
date: 2026-08-25
---

# Gotcha — A Patch on a Method Nobody Calls Fails Silently

> `pytest` reported **13 failed**. CLAUDE.md said *"None. Both suites are green — treat any
> failure you see as yours."*
>
> They were not mine. `git log -L` put all thirteen in **one commit, `f89cf0d`**, nine days old.
> That is the second time this file's "pre-existing" claim has been wrong in the same direction,
> and the first is already recorded in
> [[Gotcha - A Verdict Mapping That Contradicted Its Own Comment]].

---

## Establish ownership before you fix anything

Two independent checks, both cheap, neither relying on reading the diff:

1. **Break the only module this session touched** — append garbage to it so it cannot import — and
   re-run. The same 11 failed. A module that cannot be imported cannot be causing them.
2. **Run at clean `HEAD` in a throwaway worktree** (`git worktree add --detach`), with none of the
   working tree present. The same 11 failed.

⚠ The count differs between an isolated run (11) and a full-suite run (13) — two of them are
**order-dependent**, which is its own finding. Don't reconcile the numbers by assuming; capture the
`FAILED` lines from the full run.

---

## The root cause: a mock aimed at a method the code stopped calling

`create_session._resume` used to be `ManualCheckSession.find_one({...})`. `3b90d1e` moved it to
`find(query).sort(...).to_list()`. **The tests kept patching `find_one`.**

A stale patch does not announce itself. `monkeypatch.setattr(Model, "find_one", ...)` succeeds — the
attribute exists — and then the real `find` runs, reaches an uninitialised beanie, and raises
`CollectionWasNotInitialized`. The error names a database problem, so it reads as environmental.

🔴 **The cost is not the red test, it is the window before anyone looked.** For that window the
resume path had no working guard at all, and `f89cf0d` changed its behaviour through the gap:

| | before `f89cf0d` | after |
| :--- | :--- | :--- |
| `_require_open` on a submitted session | `409`, refuse the marking | silently reopen and append |
| resume query | scoped by `status: "in_progress"` | status dropped |

Neither change is wrong in itself — an engineer who spots a miss after submitting should not have
to start over. **But `submit` is the moment a pass becomes what `tools/eval_corpus.py
from-manual-check` converts into corpus labels**, so a silent reopen leaves a label whose source
changed after the derivation, with nothing anywhere recording it.

✅ **Resolved by keeping the reopen and making it visible**, not by reverting it (owner's call
2026-08-25): `reopened_at` and `reopen_count` on `ManualCheckSession` *and* on `SessionResponse` —
a stamp that stops at the collection is a stamp nobody sees. `reopen_count` rather than the
timestamp alone, because repeated amendments otherwise remember only the last.

---

## ⚠ The branch that could not be tested was the branch that broke

`_require_open` queried with Beanie **class-attribute expressions**:

```python
ManualCheckSession.room_id == session.room_id      # AttributeError: room_id
```

Those resolve through descriptors that only exist after `init_beanie`, so a fully-mocked router
test **cannot construct them**. That branch therefore had no coverage — and it is exactly where the
unrecorded reopen shipped.

The file used to say so. `3b90d1e` deleted this comment along with the protection it described:

> *"A raw query mapping rather than Beanie's class-attribute expressions. Those resolve through
> descriptors that only exist after `init_beanie`, so they cannot be exercised by this router's
> fully-mocked tests — and an untested resume is how the bug above came back for free."*

✅ `_pair_query` is now the single definition of "which session is this pair's", used by both
`_resume` and `_require_open`, as a raw mapping. Two spellings of one rule is how they drift, and
here the drift is silent: a reopen matching one way and a resume looking another leaves a marking
on a session the next open cannot find. Pinned by
`test_the_reopen_looks_for_the_same_session_the_resume_does`.

---

## 🔴 The suite was writing to the production database

`test_database_sync_manager_status_and_execution` called the real `sync_manager.sync_all()` — a
live cross-database upsert — **on every `pytest` run**. Nobody opted into that as a test cost.

It was failing for a real reason that is not in the code: the live collections hold more than one
`in_progress` session for the same `(room, ref, rev, annotator)`, which the partial unique index
`one_in_progress_session_per_pair_per_annotator` refuses with `E11000`.
`tools/merge_duplicate_check_sessions.py` is the cure, and has to be run against **every**
environment including Atlas — these collections are not in `sync_manager.SYNC_COLLECTIONS`, so
they exist only there.

✅ Split: the diagnostics contract still runs everywhere, the live sync sits behind
`RUN_LIVE_DB_SYNC=1`.

⚠ **It was also 80% of the suite's runtime.** `pytest` went from **11 minutes to ~2**.

---

## Two smaller ones, both environment-dependent

- **`test_database_retry_handling`** pointed `MONGO_URI` at a dead port and asserted the connection
  failed — but `connect()` falls back to `MONGO_FALLBACK_URI`, default `mongodb://127.0.0.1:27017`,
  the local MongoDB most developers here run. It therefore passed or failed according to whether
  `mongod` was up. Both URIs are now dead ports, on **different** ports so the fallback is not
  de-duplicated away, and the counters are asserted as `max_retries × candidates` — they accumulate
  across candidates rather than resetting.
- **`test_committed_corpus_has_every_ocr_reading_captured`** is the one still open.
  `M745204N01` has no captured title-block reading and none is recoverable from `storage/cache/`
  by drawing id or by file hash. Capturing it means *making* one, which is a live Gemini call per
  side — an owner's decision, not something a test run should do. Owner's call: leave it.

⚠ **An `xfail` on a test that checks every pair excuses every pair**, so the marker is
`strict=True` (the suite fails the day it starts passing) and
`test_no_pair_beyond_the_known_one_is_missing_its_ocr_reading` keeps the rest guarded against a
sixth pair being exported the same way.

---

## The lesson worth keeping

**A mock is a claim about what the code calls, and it goes stale in silence.** Nothing in
`monkeypatch.setattr` checks that anything reads the attribute. When a test's subject moves, the
patch keeps succeeding and the assertions keep passing — right up until the untouched real path
raises something that reads like an environment problem.

If a test's whole point is that a query is observable, **assert on the observation**, not just on
the outcome: `_find_stub` exposes `.queries` so the mapping itself is checked, which is the only
reason the missing `status` clause was visible at all.
