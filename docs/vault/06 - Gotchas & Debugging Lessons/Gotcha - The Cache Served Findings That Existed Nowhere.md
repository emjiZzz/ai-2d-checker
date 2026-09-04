---
tags: [gotcha, backend, cache, comparison, review-ui, persistence]
status: fixed
cache-version: no bump — matching and zone extraction are unchanged; the guard heals stale entries on read
date: 2026-08-10
---

# Gotcha — The Cache Served Findings That Existed Nowhere

> [!WARNING] The supervisor verdict block was fixed, tested, shipped — and still did not appear.
> The frontend was right. The findings on screen had **no `AuditViolation` behind them at all**,
> because a cache hit returns before the code that creates them.

## What happened

Immediately after [[Gotcha - A Guard Clause Named an Exception the Library Stopped Raising]] landed
the client-side join, the checklist rendered ADDED/REMOVED rows with **no Approve/Reject and no eye
toggle**. Both controls are gated on a real persisted id, so both vanishing at once said the same
thing: not one marker had joined to a document.

The join itself was fine. Its input was empty. `perform_drawing_comparison` looks like this:

```python
    if cached_payload:
        cached_response = PhysicalComparisonResponse(...)
        return apply_learned_adjustments(...)      # <-- returns here

    candidates, parsed, ... = await generate_deterministic_candidates(...)
    ...
    await comparison_session.save()                # AuditSession
    await AuditViolation.insert_many(...)          # the documents the UI reviews
    comparison_response.diagnostics.audit_session_id = str(comparison_session.id)
```

**Every write that gives a finding a reviewable identity sits on the cache-MISS path.** A hit
returns markings with no session id, so the client has nothing to fetch and nothing to join. Proven
against the entry actually on screen — its `canvas_markings` are the same three Japanese notes in the
screenshot, and its `diagnostics` has no `audit_session_id` key at all:

```
diagnostics keys: model_used, zone_detection_warnings, generator_a_candidates, ...
has audit_session_id: False
```

It was written at 09:39; the field was added to `ComparisonDiagnostics` at 11:53 the same day.

## Why "Re-test" could never fix it

This is the part that costs an afternoon. The obvious user response — press **Re-test**, reload the
room, restart the backend — **hits the same cache entry and reproduces the bug exactly**. The
backend was running new code. The frontend was running new code. The *data* was old, and nothing
on either side said so. Compare [[Gotcha - Comparison Cache Invalidation]]: same cache, same class
of silence, a different consequence.

## The rule

**A cache that stores a computation's output but not its side effects is not a cache — it is a
branch that skips them.** `set_cached_comparison` was handed the response body, which is genuinely
all a *rendering* needs. Persistence, id assignment and the session row were side effects of
producing it, and replay silently omits every one.

So: when a function both returns a value and writes something durable, **ask what the cached branch
does not do.** If the answer includes anything a later request depends on, the cache is lying by
omission — and it will lie fastest on exactly the pairs that get used most.

## The fix

Treat a cached entry with no `audit_session_id` as a miss and fall through to a full run, which
persists the findings, stamps the id and rewrites the entry. One slow run per stale entry, once —
self-healing, and no `COMPARISON_CACHE_VERSION` bump, which would have discarded every *valid* entry
to repair a missing field on some of them.

The guard is deliberately on the id's presence rather than on a version number, so it also catches
the case a bump cannot: a run whose persistence block threw and was swallowed by its own
`except Exception ... (non-fatal)`. If persistence is broken, that pair stops caching until it is
fixed. That is the intended trade: a finding nobody can sign off on is worse than a slow one.

## Verified

`tests/test_comparison_architecture.py` pins both directions — a payload without the id must reach
the generator, one with it must not. The second test is the load-bearing one: without it, "disable
the cache entirely" also passes.

## See also

- [[Gotcha - A Guard Clause Named an Exception the Library Stopped Raising]] — the join this
  starved, and the review path it belongs to
- [[Gotcha - Comparison Cache Invalidation]] — the first time this cache silently served the wrong
  past
- [[Gotcha - A Swallowed AttributeError Made a Write Path a Permanent No-Op]] — the `except` arm
  that turns a broken write into silence, which this guard also has to survive
