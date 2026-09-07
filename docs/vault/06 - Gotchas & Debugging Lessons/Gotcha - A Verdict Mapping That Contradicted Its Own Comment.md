---
title: Gotcha - A Verdict Mapping That Contradicted Its Own Comment
type: gotcha
tags: [gotcha, learning, trainer, false-negative, silent-failure, error-handling, regression]
status: active
date: 2026-08-17
cache-version: n/a (learned layer; no comparison cache involvement — the head abstained throughout)
related: [Gotcha - Learned Corrections Model and Post-Cache Inference, Gotcha - A Swallowed AttributeError Made a Write Path a Permanent No-Op, Gotcha - A Tested Endpoint That Nothing Ever Called, ADR-007 Re-scoping the Maturity Ladder]
---

# Gotcha — a verdict mapping that contradicted its own comment

**Class:** silent mislabelling, contained by one gate · **Found:** 2026-08-17, by running
`pytest` — which is the only reason it was found at all

---

## Symptom

Five test failures across `test_label_status`, `test_matcher_feedback` and
`test_lessons_index_write_path`, carried in `CLAUDE.md` as *"pre-existing"* and therefore
approximately invisible. They were not pre-existing. All five arrived in commit `9336601`,
and the test that catches the second defect predates it by two commits.

**There was no product symptom, and there could not have been one** — see Containment.

## Cause 1 — the mapping argued with the comment 16 lines below it

`infrastructure/learning/trainer.py` grew two verbs:

```python
# Label 1 == "this IS a true discrepancy", label 0 == "not a real
# discrepancy / false alarm / actually matched / badly paired".
VERDICT_ZERO = {"dismissed", "verdict_matched", "mispaired_missing_counterpart", "mispaired_wrong_match"}
```

Sixteen lines below, untouched, stood the block that forbids exactly this:

> Pairing feedback … **Captured, never mapped to a verdict label**, and the restraint is the
> point — both available mappings would teach the verdict head something false … label 0
> ("not a real discrepancy") would suppress a finding that may well be genuine.

So did `schemas.py:256`, `CorrectionControls.tsx:35` and `auditsApi.ts:22`. **Four statements
of the rule, one contradiction of it, and the contradiction won** because it was the one place
that executes.

The instructive detail is the comment *above* the constant: it was edited to fit
(`/ badly paired` appended) while the block *below* was left standing. The file was made
locally consistent and globally false. A reviewer reading the diff hunk saw a comment and its
code agreeing.

`mispaired_missing_counterpart` is the corpus's **single most-used verb**. The rule that got
broken was the one guarding the most data.

## Cause 2 — a new guard re-swallowed what a test had already pinned

The same commit added a feedback bridge to `audits.review_violation` containing
`except Exception: pass` and a second `except Exception`. That is precisely the shape
[[Gotcha - A Swallowed AttributeError Made a Write Path a Permanent No-Op]] cost this project
a permanently-empty collection to learn, and
`test_the_review_endpoint_does_not_swallow_programming_errors` was written to pin it — by
parsing the source for handler types, because *"there is no runtime behaviour to observe when
the correct answer is 'the error propagates'"*.

The test asserts over **every** handler in the function, so new code inside it inherits the
contract automatically. That breadth is what caught this; a test scoped to the original
rebuild guard would have passed.

## Containment — and why "it was inert" is not "it was safe"

The mislabelling reached the training corpus and stopped one gate short of inference.

| | `n_verdict` | class 0 / 1 | minority share |
| :--- | :--- | :--- | :--- |
| under the defect (committed bundle) | 92 | 80 / 12 | **0.1304** |
| corrected | 60 | 48 / 12 | **0.200** |

The 32-row delta is exactly the matcher-feedback corpus (30 `mispaired_missing_counterpart`
+ 2 `mispaired_wrong_match`). `config.MIN_MINORITY_SHARE` (0.30) abstained on **both** sides,
so the head never trained and no finding was ever suppressed.

That gate landed 2026-08-11 for this exact failure mode — a skewed prior crossing
`LOW_THRESH` and flipping `CHANGED/ADDED/REMOVED` to `MATCHED`. It did its job. But note what
the arithmetic says: the defect **improved the case for activation** by adding 32 rows toward
`MIN_TRAIN`, while making the balance worse. On a corpus with a healthier class-1 count, those
32 rows would have activated a head taught that *"the engine paired the wrong two entities"*
means *"not a real discrepancy"* — a false negative, in `SPATIAL_CATEGORIES`, in the system
whose headline gap is that false negatives have never been measured.

**One gate deep is not the same as defended.**

## Fix

1. `VERDICT_ZERO` reverted to `{"dismissed", "verdict_matched"}`, with the constraint restated
   **at the point of edit**. The 16-line distance between the rule and the line it governs is
   the mechanism, so the fix shortens the distance rather than restating the rule elsewhere.
2. Both handlers narrowed to `(OSError, ValueError, PyMongoError)` and
   `(ImportError, OSError, ValueError, PyMongoError)` — the precedent already in
   `standards.py:227` for the same guard. `ValueError` covers pydantic's `ValidationError`
   (it subclasses `ValueError` in v2, verified rather than assumed); `OSError` covers
   `AutoDocEngine` writing its rule file. The silent `pass` now logs.

`pytest tests/`: **1180 passed, 3 skipped, 0 failed**, from 5 failed.

⚠ The committed `finding_classifier.meta.json` still records a run trained under the defect
(`n_verdict 92`). It self-corrects on the next correction that triggers a retrain; until then
it is stale evidence, not a current reading.

## Lessons

- **A comment 16 lines from the code it governs is not a guard.** Put the constraint where the
  edit happens. Both `MATCHER_FEEDBACK`'s block and the three other restatements were correct,
  well-written, and did not prevent the change.
- **Local consistency is what a bad diff looks like.** The comment was updated to match the
  code. Nothing in the hunk looked wrong.
- **A standing "known pre-existing failures" allowlist is where new breakage hides.** `CLAUDE.md`
  says this in its own words — *"a standing allowlist is a place for new breakage to hide,
  which is exactly what happened below"* — and it happened again, to the same section, in the
  form of a header note asserting the failures were pre-existing. They were one commit old.
  Verify that claim before inheriting it; `git log -L` answers it in seconds.
- **Prefer assertions over the widest scope that is still true.** The source-parsing test earned
  its keep by covering every handler in the function rather than the one it was written for.
