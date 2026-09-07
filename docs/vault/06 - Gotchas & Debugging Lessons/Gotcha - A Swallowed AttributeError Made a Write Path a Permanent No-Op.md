---
title: Gotcha - A Swallowed AttributeError Made a Write Path a Permanent No-Op
type: gotcha
tags: [gotcha, standards-audit, retrieval, error-handling, silent-failure, second-brain]
status: active
date: 2026-08-07
cache-version: n/a (standards-audit pipeline; no comparison cache involvement)
related: [ADR-008 The Second Brain — Retrieval-Only Local Knowledge, RAG Reference Architecture — Gap Analysis, Standards Knowledge — Staged Plan]
---

# Gotcha — a swallowed AttributeError made a write path a permanent no-op

**Class:** silent failure · **Found:** 2026-08-07, reading the code during R0 rather than from any
symptom — **there was no symptom, and there could not have been one**

---

## Symptom

None. That is the entire problem.

The `lessons_learned` collection — the mechanism by which a supervisor's verdict on a violation was
supposed to inform future audits — had **never been written a single record**, from the day the
code was authored until the day it was deleted. No error surfaced, no log line complained beyond a
single warning nobody read, and every audit ran normally.

## Cause

`api/routers/audits.py`, in the supervisor-review endpoint:

```python
try:
    provider = EmbeddingProvider()
    vector = provider.embed_text(text_to_embed)   # singular
    ...
except Exception as e:
    logger.warning(f"Failed to index lesson: {e}")
```

`EmbeddingProvider` only ever defined `embed_texts` — **plural**. So `provider.embed_text(...)`
raised `AttributeError` on the *first* line of the `try` block, every single time. The bare
`except Exception` caught it, logged a warning, and let the request continue to its success
response.

The read path had the name right. `retrieval_engine.py`, `standards_indexer.py` and
`standards.py` all called `embed_texts` correctly.

**So retrieval was querying an index that one of its two writers could never populate.**

## Why nothing caught it

This is the part worth keeping, because the individual typo is trivial and the failure mode is
not:

1. **The `except Exception` converted a typo into a no-op.** An `AttributeError` is a programming
   error — the one class of exception that should never be swallowed by an integration guard
   written for network and disk failures. The handler could not distinguish "the vector store is
   temporarily unreachable" from "this method does not exist".
2. **The read path made the write path's failure unobservable.** A retrieval query against an
   empty index returns no results. "No relevant lessons for this drawing" is a *completely
   normal* answer — it is what you would expect on a new drawing, an unusual layer set, or a
   first-of-its-kind audit. The empty state is indistinguishable from the working state.
3. **Nothing asserted the write.** No test called the endpoint and then checked that a record
   existed. The endpoint's own test asserted a 200 response, which it always returned.

Points 1 and 2 compound: a swallowed write error is survivable if *something* later notices the
data is missing. Here the only consumer's healthy behaviour was to return nothing.

## The rule

**Assert that a write wrote. Do not assert that it did not throw.**

An integration write guarded by `except Exception` and verified only by "the request succeeded" is
untested by construction. If the write is worth doing, one test must read the record back.

Two narrower rules follow:

- **Never catch `AttributeError`, `TypeError` or `NameError` in an integration guard.** Catch the
  errors the integration can actually produce (`ConnectionError`, `OSError`, the client library's
  own exception type). A guard broad enough to hide a misspelled method name will hide one.
- **Be suspicious of a component whose healthy output and whose broken output are the same
  value.** Retrieval returning `[]`, a cache reporting a miss, a filter matching nothing — each
  needs an independent liveness check, because the failure is invisible in the output.

## Resolution

Not repaired — **deleted**, with the rest of the fake retrieval stack, by R0 of
[[Standards Knowledge — Staged Plan]]. Repairing it would have meant correcting the method name so the
endpoint began writing `np.random.default_rng(sha256(text))` — hash-seeded noise — into a JSON
file, alongside `remarks`, the supervisor's free text. See
[[ADR-008 The Second Brain — Retrieval-Only Local Knowledge]] for why the whole stack went rather
than the one line.

R1 rebuilds the feedback path over real lexical retrieval. When it does, the write must be pinned
by a test that reads the record back.

## Related

The same audit found a second instance of "reports success, does nothing":
`BackupManager.create_secure_backup` created an empty directory, logged *"System state
successfully archived"*, and returned a path to a `.zip` it never wrote — with the compression and
AES-256-GCM encryption present only as a comment beginning `# In production:`. Its test
monkeypatched **both** methods and asserted on the return values of its own lambdas, so it passed
without executing a line of the class. Now raises `NotImplementedError`; a backup that reports
success without writing bytes is worse than no backup, because it is trusted.

Both are guarded by `tests/test_no_fake_ai_capability.py`.
