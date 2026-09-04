---
title: Gotcha - The Sweep Never Got the Zone Template Seam
type: gotcha
tags: [gotcha, evaluation, sweep, zone-detection, measurement, calibration]
status: active
date: 2026-08-07
related: [Gotcha - Zone Templates Vanish in Offline Eval, Gotcha - Mutation Pairs Cannot Exercise a Spatial Constant]
---

# Gotcha — The sweep never got the zone template seam

**Found:** 2026-08-07, by running `tools/sweep.py` for the first time since 2026-08-05 and
noticing its baseline did not match the eval's.

---

## Symptom

```
tools/eval.py    baseline F1 0.92
tools/sweep.py   baseline F1 0.68
```

Same corpus, same 36 pairs, same engine, same commit. And in the sweep's log, once per pair:

```
[zone_template] Template lookup failed for 'aspect-1.414': signature
```

## Cause

[[Gotcha - Zone Templates Vanish in Offline Eval]] added a `zone_templates` parameter to
`generate_deterministic_candidates` on **2026-08-06** so an offline run scores against the
hand-aligned boxes users actually see, rather than raw detector output. That fix moved
**precision 0.78 → 1.00** and is one of the largest single results in this project's log.

`eval/runner.py` passes it:

```python
candidates, _, _ = await generate_deterministic_candidates(
    ref_drawing, rev_drawing, ref_entities, rev_entities,
    zone_templates=(pair.ref.zone_template, pair.rev.zone_template),
)
```

`eval/sweep.py` did not. It calls the same function with four arguments and no templates, so
the engine fell back to the Mongo lookup — which offline does not exist — and degraded to plain
detection on every pair.

**`sweep.py` (Stage 0.5b) landed 2026-08-05. The template seam landed 2026-08-06.** The sweep
predates the fix by one day and nobody re-ran it afterwards, so it kept the old regime. There is
no shared call site: two files call the same engine entry point with different arguments, and
nothing compares them.

## Why it matters more than a wrong number

The sweep's whole output is **spreads between runs**. A spread measured in the wrong zone regime
is not merely offset — the constants are being asked a different question, because zone boxes
decide which entities are in the pool at all. So:

> Stage 0.5b's headline finding — **"13 of 14 constants are flat across their entire declared
> range"**, recorded as a negative result and used to argue the sweep is blocked on corpus
> quality rather than on machinery — was measured against detector boxes while every other
> number in this project was measured against templates.

That claim needed re-measuring before it could be relied on, and it was, the same day.

### The correction, and why it is not the correction anyone expected

**The flat/not-flat partition did not change at all.** Corrected full pass, 580 s, baseline
F1 0.923:

| | wrong regime (2026-08-05) | corrected (2026-08-07) |
| :--- | :--- | :--- |
| constants swept | 14 (incl. the since-deleted `match_radius_mm`) | 14 (13 + `min_structured_value_length`) |
| flat across declared range | 13 | **12** |
| responds | `changed_similarity_floor` | `changed_similarity_floor`, `min_structured_value_length` |
| `changed_similarity_floor` spread | **0.139** | **0.305** |

Of the original constants, **every one that was flat is still flat, and the one that moved still
moves.** The count only changed because a new constant was added. That is the *right* outcome and
worth stating plainly: the spatial constants are flat because a mutation pair is a drawing and a
copy of it — 253 of 253 comparable entities at identical coordinates — and **that is a property
of the corpus, not of the zone boxes.** A wrong zone regime could not have changed it.

So the structural finding in [[Gotcha - Mutation Pairs Cannot Exercise a Spatial Constant]]
survives intact, and was never actually at risk. **Two things were still wrong:**

1. **The magnitude was understated 2.2×.** `changed_similarity_floor`'s spread was reported as
   0.139; it is **0.305**. Anyone reasoning about how fragile that constant is was working from
   a number less than half the real one.
2. **The default sits on the edge of a cliff, and the old run could not show it.** Per-value,
   corrected:

   | floor | 0.0 | 0.2 | **0.4** | 0.6 | 0.8 | 1.0 |
   | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
   | exactness | 0.958 | 0.958 | **0.958** | 0.917 | 0.796 | 0.653 |

   Flat from 0.0 to 0.4, then falls away. The default **0.4 is the last value before the
   degradation starts** — not the middle of a plateau. The sweep module's docstring names this
   as one of the three questions it exists to answer (*"is the current value even near the
   middle of its useful range?"*), and the answer here is no. That is a fragility signal about
   the one constant this corpus can actually exercise, and it was invisible before the fix.

Also confirmed: `changed_similarity_floor` moves **exactness, not F1** (F1 spread 0.0086, i.e.
flat). That is the [[00 - AI Maturity Status]] "sweeping on detection F1 alone" negative result
holding up under re-measurement — the scorer matches a finding to its label *before* comparing
status, so a constant that flips CHANGED into ADDED+REMOVED reshapes every verdict without
moving detection.

It would also have mattered *silently and later*. The sweep is Stage 0.5's whole instrument. The
moment human pairs land, it would have been pointed at them and would have produced calibrated
constants tuned to a zone regime the product does not use.

## The fix

One argument, plus the comment saying why. The symptom to recognise, recorded in the code:

- a sweep baseline far below the published eval baseline, and
- `[zone_template] Template lookup failed for '<signature>'` in the log.

## The general shape

**A seam added to one caller is not added to the system.** `generate_deterministic_candidates`
has two offline callers with the same responsibility — reproduce the engine as users run it —
and only one was updated. The parameter is optional and defaults to `None`, which is correct for
the app (it means "resolve from Mongo") and is exactly what makes the omission silent offline.

An optional parameter whose default is right for production and wrong for the harness will be
omitted by the next harness that gets written. If a second offline caller ever appears, the
honest fix is a shared `run_pair`-style helper that owns the template plumbing, rather than a
third copy of the argument list.

Compare [[Gotcha - Full-Width Grid Labels Bridged Zones]], where two copies of one predicate
drifted and only one normalised NFKC — same failure, different layer. This project has now paid
for the "two callers, one contract, no shared definition" mistake three times.

---

## Related

- [[Gotcha - Zone Templates Vanish in Offline Eval]] — the fix this one failed to inherit
- [[Gotcha - Mutation Pairs Cannot Exercise a Spatial Constant]] — the sweep's *other* limit,
  which is real and unaffected by this
- [[00 - AI Maturity Status]] — Stage 0.5b, and the corrected sweep figures
