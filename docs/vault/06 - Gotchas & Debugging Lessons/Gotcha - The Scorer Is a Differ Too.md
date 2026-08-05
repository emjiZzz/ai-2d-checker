---
tags: [gotcha, evaluation, scorer, measurement, metrics]
status: fixed
cache-version: n/a — the scorer is offline infrastructure, not engine behaviour
date: 2026-08-05
verified-against: 54 mutation pairs, v38 baseline
---

# Gotcha — The Scorer Is a Differ Too

> [!IMPORTANT] Two bugs found by hand-auditing the scorer's output on **two pairs**, before
> any aggregate was believed. Both would have produced a plausible F1 that was wrong.

The staged plan lists this as Stage 0d's headline risk: *"The scorer's matcher is itself a
differ and can be wrong. Hand-audit its decisions on 2 pairs before trusting any aggregate."*
That instruction paid for itself immediately.

## Bug 1 — category was ignored, so short strings collided across the sheet

Matching deliberately did **not** require the predicted and expected categories to agree.
That part is right: a finding the engine located but filed under the wrong category is a
*category error*, not a miss, and requiring equality would count it as a false negative and
a false positive at once, making attribution unreadable.

But *ignoring* category is the opposite mistake. On `M745200N01-rev-mut002`:

| | |
| :--- | :--- |
| expected | `bill_of_materials` CHANGED, cell `a` → `aB` |
| matched to | `drawing_views` ADDED, text `Ａ` |
| meanwhile | the genuine `bill_of_materials` REMOVED `a` sat unmatched |

`Ａ` is fullwidth and NFKC-folds to `a`. One collision on a one-character string produced a
false match, a false positive that should have been a true positive, and a misattributed
category — **precision and recall wrong in opposite directions on the same pair**.

**Fix:** category is a *preference*, not a filter. Candidates rank same-category first, then
same-status, then nearest. Both extremes are now pinned by test.

## Bug 2 — "duplicate" was decided by proximity, and most findings have no coordinates

An unmatched prediction was called a duplicate rather than a false positive if it landed
within `MATCH_RADIUS_MM` of an already-matched finding. But `bill_of_materials` candidates
mostly carry **no coordinates at all** (they are table-derived), and `title_block` ones often
do not either. So whether an over-report was forgiven as a duplicate or charged as a false
positive depended on whether it happened to have a coordinate — noise, not a measurement.

The case that exposed it: the engine reports **one edited BOM row as five cell-level
findings** (`a`, `SS400 28×%%c185`, `1`, `5.91`, `4.36`), against an annotation guideline that
says one edited row is one finding. Four of those five are over-reporting. Two were being
absolved as duplicates purely by coordinate accident.

**Fix:** a duplicate now requires the same category *and* the same handle or the same text.
Proximity alone is not enough. This lowered measured precision from 0.90 to 0.85 — the
honest direction.

## What the audit also confirmed about the engine

Both audited pairs' remaining decisions were correct, and two of them are real engine
signals rather than scorer artefacts:

- **A 3-unit translation produced a false positive.** `translate_entities` nudged text by
  ≤3 units and the engine reported `Ａ` as ADDED with no REMOVED counterpart — the classic
  symptom of an entity crossing a zone boundary. Same shape as
  [[Gotcha - Dimension Scoped by Its Span Midpoint]].
- **A single-character deletion went unreported.** Deleting `G` from the notes zone produced
  no finding. Worth checking against `marking_reconciler.MIN_FUZZY_LENGTH = 4`.

## Design decisions worth not re-litigating

- **A prediction is a candidate whose `status != "MATCHED"`.**
  `generate_deterministic_candidates` returns every checklist row, including items checked
  and found unchanged — a null pair comes back with **50 candidates and 0 discrepancies**. A
  scorer counting candidates would report precision near zero on a perfect run.
- **Match tiers are reported, not hidden.** Only 18 of 52 matches came from handles; 33 came
  from text. A result resting on the weaker tier deserves less confidence, and a single F1
  would conceal that.
- **Every rate prints with its counts.** `0.86` invites a confidence that `0.86 (6/7)` does
  not.
- **An unresolvable label is a corpus defect, not a miss.** Counting it as a false negative
  would blame the engine for the corpus being wrong.

## The transferable lesson

**Measurement code needs the same scepticism as the code it measures — and gets less of it,
because its output looks like an answer.** A wrong engine produces a visible bug; a wrong
scorer produces a number, and a number ends the conversation. Audit by hand before the first
aggregate, not after the first surprising one.

## See also

- [[Gotcha - A Naive Mutator Manufactures Recall Misses]] — the same lesson one layer down
- [[Gotcha - Exploded Block Children Have No Handle]] — why handle-first matching is a
  minority path here
- [[Eval Corpus Annotation Guideline]] — the "one row is one finding" rule bug 2 rests on
- [[00 - AI Maturity Status]] — the v38 baseline these numbers went into
