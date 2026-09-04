---
tags: [gotcha, evaluation, mutation, calibration, measurement, negative-result]
status: measured — a hard limit, not a bug
cache-version: n/a — measurement infrastructure, no engine behaviour changed
date: 2026-08-05
verified-against: 36 mutation pairs, 14 constants, 72 engine runs, 865s
---

# Gotcha — Mutation Pairs Cannot Exercise a Spatial Constant

> [!IMPORTANT] The Stage 0.5 sweep reported **13 of 14 tuning constants as having no effect
> whatsoever**. That reading is available, clean, quantitative, and wrong. The constants are
> not dead — the corpus cannot ask the question.

## The measurement

`tools/sweep.py`, coordinate descent over the deterministic engine's tuning surface, 36
mutation pairs:

```
baseline F1 0.713, exactness 0.722, 46 findings

MOVES SOMETHING
  changed_similarity_floor   spread 0.139   ΔF1 0.000   Δexactness 0.139

MOVED NOTHING across its entire declared range
  strict_radius_norm · twin_threshold_norm · fuzzy_threshold_norm
  strict_radius_abs  · twin_threshold_abs  · fuzzy_threshold_abs
  match_radius_mm · similarity_threshold · ambiguity_margin
  min_fuzzy_length · max_normalized_move
  label_proximity_tolerance_mm · char_width_ratio
```

## Why

A mutation pair is a drawing and a **copy of that drawing** with a few text edits. Both sides
therefore share one coordinate system exactly:

| pair | comparable entities at identical coordinates |
| :--- | ---: |
| `M7452A0N01-ref-mut000` | **253 / 253** |
| `M7452A0N01-ref-mut002` | **253 / 253** |
| `M7452A0N01-ref-move000` | 252 / 253 — the single entity `translate_entities` moved |
| `M7452A0N01` *(the human pair)* | **0 / 11** |

Distance between a ref entity and its rev counterpart is **exactly zero**. Every matching
radius ≥ 0 therefore succeeds on the first tier, and the twin and fuzzy tiers below it are
never reached. The constants are read, evaluated, and never decide anything.

The same mechanism accounts for three more. `similarity_threshold`, `ambiguity_margin` and
`min_fuzzy_length` live in `reconcile_relocated_markings`, which exists to merge a REMOVED/ADDED
pair representing *the same content relocated*. With zero relocation there is no such pair to
merge, so the fuzzy pass never runs. `MAX_NORMALIZED_MOVE` is literally a move threshold
(`marking_reconciler.py:123`) against a move of zero.

And the human pair shows the opposite extreme — **0 of 11** shared coordinates — because a real
revision here is a *re-trace*: different coordinate space, different layer names, different
origin. That is exactly the regime the spatial constants were written for, and the only regime
that can test them.

## What this means for Stage 0.5

**Calibrating on a mutation corpus is not merely unreliable for these thirteen constants. It is
structurally impossible.** The plan already said the sweep must not run on a mutation-only
corpus, on the grounds that it would fit the constants to the mutator. The real situation is
sharper: it would not fit them at all, it would report them as inert and invite someone to
delete them.

The corpus can exercise roughly **1 of 14**. `changed_similarity_floor` moves because it gates
text similarity, and text is what mutations edit.

### Even the one live constant is only half-measured

The per-value curve, reproduced identically across two runs:

| `changed_similarity_floor` | 0.0 | 0.2 | **0.4** | 0.6 | 0.8 | 1.0 |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| F1 | .713 | .713 | **.713** | .713 | .713 | .713 |
| exactness | .722 | .722 | **.722** | .722 | .667 | .583 |

Detection is flat everywhere. Verdict accuracy is flat from 0.0 to 0.6 and then degrades —
tightening the gate turns genuine edits into REMOVED+ADDED pairs, which is a status downgrade.

**The upper half of that curve is trustworthy; the lower half is not.** The constant exists to
stop *unrelated* notes at nearby positions being paired as CHANGED — the code records unrelated
notes scoring 0.00–0.14 against a genuine edit at 0.75. That is a proximity phenomenon, and
this corpus cannot produce it: coordinates are identical and the mutator edits text in place, so
there are no near-miss neighbours to mispair. Reading "0.0 costs nothing" off this table would
be the same error as reading "the radii are dead" — the corpus simply never presents the case
the constant guards against.

So the default at 0.4 sits on a plateau whose right edge is measured and whose left edge is
unexamined. That is still worth knowing: it is *not* on a cliff, and raising it is measurably
harmful.

## The near-miss that produced the metric

The first sweep run reported `changed_similarity_floor` at spread **0.000** as well — i.e.
14 of 14 flat, "no constant in this engine is connected to anything". It was measuring
detection F1 only.

`test_an_override_changes_what_the_engine_reports` had independently proved that same override
changing real engine output, so the two disagreed and one had to be wrong. Both were right:
**the scorer matches a finding to its label before comparing status**, so a constant that flips
CHANGED into ADDED+REMOVED reshapes the status-confusion matrix while leaving detection
untouched. `Measurement` now carries **exactness** — the fraction of matched findings agreeing
on both status and category — and `distance()` takes the max of the two rates rather than the
mean, so a large move in one cannot hide behind a flat other.

Without that, this note would have recorded a 14/14 null result and the vault would now contain
a confident, thoroughly-measured falsehood.

## What is *not* concluded here

- **`min_fuzzy_length = 4` is not cleared** as the cause of the unreported single-character
  deletion found in the Stage 0d hand-audit. It reads flat from 1→10, but the pair that
  exhibited the miss was in the pre-rebuild corpus and no longer exists. The current corpus
  cannot ask that question either.
- **`char_width_ratio`** (BOM column geometry) is flat for a reason not yet attributed. The
  identical-coordinates explanation does not obviously cover it.
- **`match_radius_mm`** is flat because `reconciler.py` only runs on `hybrid`, which
  [[ADR-004 Deterministic-Only Scope]] puts out of scope. Confirmed rather than assumed —
  worth having, but not a finding about the constant.

## The transferable lesson

**A synthetic corpus tests the axes it varies, and silently reports every other axis as
irrelevant.** The mutator edits text, so text constants respond and spatial constants read as
dead. Nothing in the output says "not applicable" — flat and inert look identical, and flat is
the more actionable-looking of the two, which is what makes it dangerous.

Before believing a null result from a generated corpus, ask what the generator *varies* — and
check, mechanically, whether the thing you are measuring is even reachable.

## See also

- [[Gotcha - A Naive Mutator Manufactures Recall Misses]] — the same corpus, the opposite
  error: labels the engine was right to ignore
- [[Gotcha - The Scorer Is a Differ Too]] — where the match-before-status behaviour comes from
- [[ADR-004 Deterministic-Only Scope]] — why this tuning surface is now the whole surface
- [[00 - AI Maturity Status]] — Stage 0.5, and the human pairs this makes binding
