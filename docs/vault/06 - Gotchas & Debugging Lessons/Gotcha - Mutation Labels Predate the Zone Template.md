---
tags: [gotcha, evaluation, mutation, zones, zone-template, ground-truth, measurement, negative-result]
status: FIXED 2026-08-06 — and the fix proved the metric was never measuring the engine
cache-version: n/a — the disagreement is between the labels and the engine
date: 2026-08-06
verified-against: 36 pairs regenerated at mutation schema v2; attribution 0.74 -> 1.00
---

> [!IMPORTANT] Read the resolution before citing any attribution number.
> The fix worked — recall 0.78 → 0.85, F1 0.88 → 0.91, attribution 0.74 → **1.00**. But
> 1.00 here is a **tautology, not an achievement**: the mutator and the engine now scope with
> identical zone boxes, so category agreement is true by construction. Attribution on mutation
> pairs measures nothing about the engine and never did. See "The metric was the problem".

# Gotcha — Mutation Labels Predate the Zone Template

> [!IMPORTANT] Applying hand-aligned zone templates offline improved every detection metric
> and made **category attribution worse** — 0.81 → 0.74. The engine did not regress. The
> **labels** did, because they were generated under different zone boxes than the engine now
> uses. Attribution on the mutation corpus currently measures *template-vs-detector
> disagreement*, not engine quality.

## What happened

[[Gotcha - Zone Templates Vanish in Offline Eval]] was fixed: the eval now applies this
machine's seven hand-aligned zones instead of degrading to plain detection. Detection moved
in one direction, hard — precision 0.78 → 1.00, recall 0.65 → 0.78, F1 0.71 → 0.88,
`notes_section` from F1 0.50 to 1.00.

Category attribution went the other way, and a new confusion appeared from nothing:

```
CATEGORY ATTRIBUTION
  accuracy   0.74 (32/43)          was 0.81 (29/36)
    notes_section -> drawing_views: 7        <- new
    isometric_view -> bill_of_materials: 4
```

## Why

`mutator.py:148` builds its zone map with **`extract_dynamic_regions`** — the synchronous,
detection-only function. It has no template awareness and never did:

```python
self.regions = extract_dynamic_regions(base_entities)
```

Those regions do two jobs. They pick **where mutations land**, and they assign each
`ExpectedFinding` its **category**. So every expected category in the corpus was decided
under detection-only zones, while the engine under test now scopes with the user's pinned
boxes. Where the template's `notes` box is tighter than the detector's, content the mutator
filed as `notes_section` legitimately arrives as `drawing_views`.

**The engine is right and the label is stale.** Seven times.

Note the absolute count of *correct* attributions went **up**, 29 → 32; the ratio fell only
because 43 findings are now matched instead of 36. A metric can degrade while everything it
measures improves, when its denominator grows faster than its numerator.

## Why this was predictable, and was in fact predicted

[[00 - AI Maturity Status]] already recorded that mutation-pair attribution *"is **not
independent** of `zone_detector`, so the 0.90 attribution accuracy is partly circular"*. This
is that circularity cashing out. The corpus grades the engine using the engine's own zone
pass, so changing the zone pass changes the exam and the answer key by different amounts.

The same root shape as [[Gotcha - A Naive Mutator Manufactures Recall Misses]]: **ground
truth is code, and code has bugs.** There the mutator's targets were wrong; here its
categories are merely *out of date*. Both times the corpus made the engine look worse than it
is, and both times the number was believable.

## The fix

`Mutator.__init__` takes a `zone_template` and builds its regions with
`extract_dynamic_regions_with_template`, the **synchronous twin** of the async path. Both
share `apply_zone_overrides`, so the override policy — safe-zone anchoring, BOM growth, the
grown-zone outline drop — has exactly one implementation. A mutator applying *nearly* the
engine's rules would be this same defect one layer down.

`MUTATION_SCHEMA_VERSION` 1 → **2**, because both halves of a v1 label are affected: v1 pairs
were targeted *and* categorised against detector boxes. They must be **regenerated, not
re-scored**, which is what a schema version exists to make identifiable.

All 36 pairs regenerated from the same seeds and operators. Same shape — 36 pairs, 11
zero-finding, 55 expected findings — so the comparison is like for like.

| | v42 (stale labels) | v42 regenerated |
| :--- | :--- | :--- |
| precision | 1.00 (43/43) | 0.98 (47/48) |
| recall | 0.78 (43/55) | **0.85 (47/55)** |
| F1 | 0.88 | **0.91** |
| macro F1 | 0.86 | 0.87 |
| handle-tier matches | 15 | **22** |
| attribution | 0.74 (32/43) | 1.00 (47/47) ⚠ |
| categories with coverage | 5 / 6 | **4 / 6** ⚠ |

Recall and F1 rose, and the *trustworthy* match tier grew from 15 to 22 — more findings are
now matched by entity handle rather than by text. One new false positive appeared in
`bill_of_materials`, which is reported rather than smoothed over.

## The metric was the problem

**Attribution reached 1.00 with an empty confusion matrix, and that is the tell.** The
mutator now derives each expected category from the same zone boxes the engine scopes with,
so for any entity in exactly one zone the two agree *by construction*. The number cannot
be anything else.

Its whole history is a history of measuring something other than the engine:

| Corpus state | Attribution | What it actually reflected |
| :--- | :--- | :--- |
| 6 drawing families | 0.90 | detector-vs-detector, three sheet layouts |
| rebuilt on one family | 0.81 | detector-vs-detector, one layout |
| templates applied to the engine only | 0.74 | template-vs-detector **disagreement** |
| templates applied to both | 1.00 | nothing — a tautology |

None of those four is a statement about whether the engine files a finding under the right
category. **Only human-labelled pairs can measure attribution**, because only a human assigns
a category without consulting `zone_detector`. Do not cite `1.00`, and do not read a future
drop in it as an engine regression.

## `isometric_view` lost all coverage, and that is the correct outcome

Expected `isometric_view` findings went **5 → 0**, and this is not a sampling accident: the
hand-aligned `iso` box contains **zero** comparable entities on either side — measured, both
sides, text and dimensions. `COMPARABLE_ENTITY_TYPES` is text plus dimension, and an
isometric view is geometry; the user's box draws it correctly and there is no text in it.

So the old corpus's five `isometric_view` findings were landing on text that the *detector's*
looser box swept in and the user's box excludes. **The previously reported `isometric_view`
F1 of 0.89 was measured on content that is not in the isometric view.**

The corpus now honestly covers **4 of 6 categories**. Both gaps are structural, not lazy:

- `isometric_view` — no comparable entity exists inside the correct box, so no mutation
  operator can produce one.
- `other_engineering_references` — section callouts are deliberately suppressed
  (`DROP_SECTION_CALLOUT_LABELS`), so such a pair is a recall miss *by design*.

Losing a category's coverage while learning that its old number was meaningless is a gain in
what is known, and a loss in what is claimed. Recorded as both.

## What stays true

- **Detection metrics (precision / recall / F1) are sound**, before and after. The scorer
  matches on handle then text with category only a *preference*, so a stale category never
  created or destroyed a match. See [[Gotcha - The Scorer Is a Differ Too]].
- **Mutation pairs still cannot reveal a scoping bug** — targeting the engine's own pool is
  what makes labels satisfiable, and what makes this class invisible
  ([[Gotcha - A Naive Mutator Manufactures Recall Misses]]). Making the pool *more* accurate
  does not change that; if anything it tightens the circle.

**Rule: when ground truth is generated by the same code being graded, changing that code
changes the answer key too — and the two do not move together. Check which of the engine and
the labels a metric actually moved, before believing either.**

**Second rule, from the resolution: making a circular metric agree with itself does not make
it a measurement.** Attribution went 0.90 → 0.81 → 0.74 → 1.00 across four corpus states
without once describing the engine. A metric that reaches a perfect score by construction has
told you it was never independent — treat that as a finding about the metric, not a result.

## See also

- [[Gotcha - Zone Templates Vanish in Offline Eval]] — the fix that surfaced this
- [[Gotcha - A Naive Mutator Manufactures Recall Misses]] — the same root shape, one layer down
- [[Gotcha - Mutation Pairs Cannot Exercise a Spatial Constant]] — the other structural limit
  of a self-labelling corpus
- [[00 - AI Maturity Status]] — the ledger, where this is the recorded next action
