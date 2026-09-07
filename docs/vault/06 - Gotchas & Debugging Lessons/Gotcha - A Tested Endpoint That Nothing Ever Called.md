---
title: Gotcha - A Tested Endpoint That Nothing Ever Called
type: gotcha
tags: [gotcha, debugging, api, reachability, testing, feedback-loop, retrieval]
status: resolved
date: 2026-08-10
related: [ADR-009 Retiring the Standards Knowledge Track, Gotcha - A Swallowed AttributeError Made a Write Path a Permanent No-Op, 00 - AI Maturity Status]
---

# Gotcha — a tested endpoint that nothing ever called

**Symptom:** the `lessons` retrieval collection was empty. 1,322 audit violations existed and
**every single one was unreviewed** — 0 approved, 0 rejected — on a live database with 8,055
extracted entities, 108 rooms and 58 audit sessions.

**Cause:** `PATCH /audits/violations/{id}/review` had **no caller anywhere in the desktop app.**
Not a broken caller. Not a caller behind a feature flag. Zero. `grep -rn "violations/.*review"
apps/desktop/src` returns nothing.

---

## Why nothing caught it

The endpoint was not neglected code. It was **well written and well tested**: it validates, it
persists a verdict, it re-derives the lessons index, and its exception guard is deliberately narrow
so an `AttributeError` crashes loudly rather than being swallowed — that narrowing was itself the
fix for [[Gotcha - A Swallowed AttributeError Made a Write Path a Permanent No-Op]]. There is a test
that performs a review and reads the record back out of the index rather than asserting a 200.

Every one of those tests calls the endpoint **directly**. None of them, and nothing else, asserts
that any *user-reachable surface* calls it. So the system had:

| Layer | State |
| :--- | :--- |
| Endpoint | correct, tested |
| Index rebuild | correct, tested |
| Read path (`audit_orchestrator` queries `lessons`) | correct, tested |
| **A button** | **does not exist** |

and the observable behaviour — retrieval returns nothing — is *exactly* what a healthy system
returns for a drawing with no relevant prior lessons. Same signature as the swallowed
`AttributeError` before it: **a hole that returns the same value as the healthy case.**

> **The lesson: a test proves a path *works*. Nothing there proved it was *reachable*.** Those are
> different properties and this repo had only ever checked the first.

---

## The compounding effect

This is why [[ADR-009 Retiring the Standards Knowledge Track]]'s census read the way it did. Two of
three retrieval collections were empty, and the two emptinesses had completely different causes:

- `standards` = 0 → **nobody ever uploaded a standard.** A data problem needing a data-entry
  project.
- `lessons` = 0 → **there was no button.** An engineering problem needing one screen.

Read together as "the corpus is empty" they look like one finding. They are not, and the second one
is far cheaper to fix. Splitting them is what turned "retrieval is not the lever" into "one of these
two is a week of work".

---

## The second defect, found while building the fix

`AuditViolation` carries both `is_resolved: bool` and `resolution_type: str | None`. The API
response shipped **only the boolean**.

```
is_resolved = False   ← "nobody has reviewed this"
is_resolved = False   ← "a supervisor reviewed this and REJECTED it"
```

A client cannot tell those apart. A review queue filtered on what the API actually returns would
show every rejected finding **forever**: the reviewer works through the list, and the list does not
shrink. `resolution_type` is now on `AuditViolationResponse` and populated at both construction
sites.

**The nasty part is how it fails.** `resolution_type` has a default of `None` on the response
model, so a construction site that simply forgets to pass it raises nothing, fails no type check,
and returns a **well-formed response asserting the violation is unreviewed.** Wrong data, valid
shape, no error — the same class as everything else in this file. Pinned by
`tests/test_violation_review_response.py`, whose three behavioural assertions were **verified to
fail** with the field removed from the call sites (`{'v-no': None} != {'v-no': 'REJECTED'}`).

---

## What to check next time

1. **For any write endpoint, grep the client for its path.** If nothing calls it, the feature does
   not exist regardless of its test coverage.
2. **Be suspicious of a boolean that answers a three-state question.** `is_resolved` was never
   wrong; it was never sufficient. "Not yet" and "no" are different answers, and collapsing them
   silently produces a queue that cannot be emptied.
3. **When a corpus is empty, ask which kind of empty.** "No data was ever entered" and "no code path
   can write data" look identical from the read side and cost wildly different amounts to fix.

## Related

- [[Gotcha - A Swallowed AttributeError Made a Write Path a Permanent No-Op]] — the *other* reason
  `lessons` was empty, and the reason this one stayed hidden: with the write path already known to
  be broken, the empty collection had a sufficient explanation, so nobody asked whether anything
  called it. **Two independent faults on one path, and the first one found was cover for the
  second.**
- [[Gotcha - A Child Cannot Claim Its Own Line in a Nowrap Flex Row]] — the defect introduced *by*
  this fix. The UI written here to give the endpoint a caller was appended to a flex row that could
  not hold it, so **Approve** shipped rendering as `Ap`. Giving a dead endpoint a button is not
  finished until the button is legible in the panel it lives in.
- [[ADR-009 Retiring the Standards Knowledge Track]] — the census this sharpened
- [[00 - AI Maturity Status]] — the work-log entry for the review UI
