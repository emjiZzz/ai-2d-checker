---
tags: [gotcha, evaluation, mutation, ground-truth, measurement, false-negative]
status: fixed
cache-version: n/a — no engine behaviour changed; this was a defect in the ground truth
date: 2026-08-05
verified-against: 54 mutation pairs generated from the 3 exported corpus pairs
---

# Gotcha — A Naive Mutator Manufactures Recall Misses

> [!WARNING] A bug in the generator does not surface as a failing test. It surfaces as a
> permanently wrong recall number that nobody can trace back to its cause.

## What happened

The first run of the Stage 0c mutation generator ([[00 - AI Maturity Status]]) picked its
targets by zone containment: any text entity inside the detected `notes` / `views` / `bom`
box, minus the safe zones. It then recorded each edit as an `ExpectedFinding`.

Comparing engine output against those labels showed pairs expecting 2 findings and getting
0. That looks like a recall failure. It was not. Here is what the generator had actually
chosen to delete:

| deleted text | zone | what it really is |
| :--- | :--- | :--- |
| `Dimension/Model No.` | bom | a **column header** |
| `材　　　　　料` | views | a **table header** ("material") |
| `G` | notes | a **margin grid label** |
| `８` | views | a single fullwidth digit — table furniture |

Every one of those is on the annotation guideline's own **"what is not a finding"** list.
The engine was right to report nothing. The recall miss belonged to the mutator.

## Why it is a trap specifically

A mutation corpus has no annotator, which is the entire appeal — and also means **nothing
looks at the labels**. A hand-labelled pair gets its bad label caught by the human writing
it. A generated one goes straight into an aggregate. The failure is silent by construction,
and it biases in the most dangerous direction: it makes the engine look *worse* at exactly
the thing this project has never measured, so the number would have been believed.

## The fix

Targets are now drawn from what the engine actually compares, using the orchestrator's own
importable scoping rather than a bbox test:

- `views` — `scope_entities_to_views(entities, views_bbox, views_exclusions(regions))`, the
  same call `orchestrator.py:872` makes
- `bom` — only text matching a cell value that `extract_bom_table` actually produced.
  Editing a column header is not a BOM row change
- `title` — only values present in the title-block OCR reading, so the field is real
- everywhere — restricted to `COMPARABLE_ENTITY_TYPES` (`text`, `dimension`), minus
  `is_margin_grid_text`, minus safe zones

After the fix: 23 zero-finding pairs report **zero** findings, and the remaining 31 pairs
expect 76 findings against 61 reported — a real signal instead of a manufactured one.

## The limitation this creates, stated rather than buried

Targeting the engine's own comparison pool means **a mutation can never land somewhere the
pool wrongly excludes.** Mutation pairs therefore cannot detect a *scoping* bug — and
scoping bugs are a live class here: [[Gotcha - Dimension Scoped by Its Span Midpoint]] is
precisely a case where an over-grown safe zone silently dropped real content from
comparison, and a mutation corpus built this way would have been blind to it.

**Only human pairs can catch a scoping bug.** That is a third reason human pairs cannot be
substituted for, alongside the two already recorded (they gate Stage 3's learned matcher,
and they are the only independent check on category attribution).

## A second, smaller trap in the same run

Two independent `rng` draws set a mutated dimension's display text and its `measurement`,
producing a dimension whose text read `%%c125` while its measurement said `119` — incoherent
as a drawing, and a label whose `rev_text` contradicted the value the differ actually
compares. Now derived: the text is rewritten *from* the new measurement, keeping the callout
shape (`%%c120` → `%%c122.5`).

## And a counting rule worth writing down

`generate_deterministic_candidates` returns **every checklist row**, including
`status="MATCHED"` — items checked and found unchanged. On a null pair it returns 50
candidates and 0 discrepancies. A scorer that counts candidates instead of filtering
`status != "MATCHED"` would report a precision near zero on a perfect run. The Stage 0d
scorer must filter.

## The transferable lesson

**Ground truth is code, and code has bugs.** A corpus that labels itself removes the
annotator, and the annotator was also the reviewer. Before trusting a generated label,
check what it would mean for the label to be *wrong* — and note which direction the bias
runs, because that is the direction you will believe.

## See also

- [[Eval Corpus Annotation Guideline]] — the "not a finding" list this violated
- [[Gotcha - Exploded Block Children Have No Handle]] — how these labels are addressed
- [[Gotcha - Zone Templates Vanish in Offline Eval]] — the other Stage 0 measurement hazard
- [[00 - AI Maturity Status]] — the ledger
