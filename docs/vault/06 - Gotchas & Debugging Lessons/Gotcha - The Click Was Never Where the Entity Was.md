---
tags: [gotcha, ground-truth, addressing, eval-corpus, removed]
status: fixed
cache-version: n/a — `address_resolver` is not on the comparison path
date: 2026-08-20
---

# Gotcha — The Click Was Never Where the Entity Was

> Found by trying to close a known gap rather than by a bug report. The handover said:
> *"REMOVED has never been carried end to end. Deletions may convert badly and nothing has
> measured it."* Measuring it found something worse than bad conversion.

## Symptom

None. That is the whole problem, and it is why this went unnoticed through the design,
implementation and review of both `address_resolver.py` and `manual_check_bridge.py`.

A REMOVED marking on reference-side geometry resolved to **a different entity than the one the
engineer clicked**, and reported it at **distance 0.0** — the strongest match the resolver can
express. The resulting label reads perfectly. Nothing downstream can tell.

## Root cause: two different quantities, compared as if they were one

`EntityAddress.point` is documented as *"Where the engineer clicked"*, and that is literally
what it is — `useEntityPicking` sends the pointer's world position verbatim:

```ts
coordinates: [world.x, world.y],
```

Tier 4 compared that against `_entity_point(entity)`, which returns the entity's **canonical
anchor**: the first of `insert`, `text_point`, `def_point`, `start`, `center`.

For TEXT and INSERT those nearly coincide, which is exactly why nothing surfaced it — measured
over 3611 real reference entities, **all 1541 TEXT entities resolved correctly**. The tests
were written against text. The corpus's labelled findings are text. The feature demo was text.

For a LINE they diverge without limit:

| | |
| :--- | :--- |
| Border line on `M745204N01` | `start` (600, 801) → `end` (1230, 801) |
| Engineer clicks its middle | (915, 801) |
| Distance to its own `start` | **415 units** |
| `COORDINATE_TOLERANCE` | **1.0** |

So the entity the engineer actually picked **was not even a candidate**. Meanwhile an unrelated
line whose `start` happened to sit at the click was returned instead, at distance 0.0.

This is the same defect the vault already records one layer over, in
[[Gotcha - Dimension Scoped by Its Span Midpoint]]: *collapsing an entity to one derived point
produces a phantom location where nothing is drawn.* There it dropped a dimension from the
comparison pool — a **missing** finding. Here it silently attributes a person's judgement to
the wrong entity — a **wrong** one. The second is worse, because the first is countable.

## A second defect, underneath it

`_nearest` ranked by `<` alone, so when several candidates sat at the same minimal distance it
returned **whichever came first in payload order**. That is a guess wearing the costume of a
measurement.

The coincidences are not floating-point noise; they are real CAD:

* two border lines meeting at a corner share an endpoint exactly,
* three concentric arcs of a corner round share a centre exactly.

Measured across the eight human pairs: **101 of 1737 coordinate-tier resolutions were
ambiguous, and order-breaking got 44 of them wrong.**

## Measured, before and after

Simulating a REMOVED stamp on every reference entity of the human pairs — clicking where a
person actually clicks (the middle of a line, a point on a curve), then asking whether the
address the bridge emits resolves back to the entity that was picked:

| | before | after |
| :--- | ---: | ---: |
| correct | 2142 (59.3%) | **3379 (93.6%)** |
| **silently wrong** | **33 (0.9%)** | **0** |
| unresolved (reported, safe) | 1436 (39.8%) | 232 (6.4%) |

By type, before → after: `line` 270 → **1322** correct with 33 → **0** wrong; `polyline`
36 → **197**; `arc` 32 → **56**; `text` 1541 → 1541 (unchanged, and the reason this hid).

End to end through `manual_check_bridge.build_labels`, every emitted address now resolves back
to the picked entity: **904 / 904, 0 wrong.**

31 of the 33 mis-resolutions were the anchor defect; 2 were the tie defect. Both are fixed.

## The fix

`_entity_distance(entity, target)` measures to the geometry the entity **draws** — point-to-
segment for `start`/`end`, every polyline run (`points`, `vertices`, `render_paths`, …), and
distance-to-circumference for `center` + `radius`. A click lands *on* what it selected; that is
what selecting something means. `_entity_points` is borrowed from `zone_detector` rather than
re-derived, because it already had to learn the exotic keys (ellipses, splines) the hard way.

`_nearest` now **refuses a tie** instead of breaking it. This costs the 57 that payload order
happened to get right — deliberately. It is the trade the module docstring already committed
to: *an unresolved marking is a known, countable gap; a mis-resolved one corrupts the dataset
in a way nothing downstream can detect.*

`COORDINATE_TOLERANCE` is **unchanged at 1.0**. Measuring to geometry widens what tier 4 can
reach, not how far it reaches, and a test pins that so the constant cannot drift into being a
hit radius around an entire 800-unit line.

⚠ An arc is measured to its **full circumference** — the payload carries `center` and `radius`
but no angular sweep, so a click on the empty side of an arc reads as on it. Over-permissive by
exactly the span the file does not record; the ambiguity refusal is what keeps that from
becoming a wrong answer.

## What remains unresolved, and why that is fine

`layer` pseudo-entities (138) carry no geometry and are not pickable. `line` (101) are genuine
coincidences the address cannot separate — refused on purpose. Both are **reported**, and
`from-manual-check` refuses to write a partial draft without `--allow-unresolved`.

## Rules

* **An address that stores where a human clicked must be resolved against what the entity
  draws, not against a point derived from it.** A canonical anchor answers a different
  question, and for anything longer than a character it answers it badly.
* **A tie is not a ranking.** If two candidates are indistinguishable to the data you stored,
  the honest output is nothing. Order is not a discriminator; it only looks like one.
* **Coverage that is 100% on one entity type is not coverage.** Text resolved perfectly
  throughout, which is precisely what kept this hidden — the tests, the corpus and the demo
  were all text. Ask which subpopulation your green tests actually cover.
* **A gap flagged as "never measured" is a defect report with the severity field left blank.**
  This one was on the handover as *"deletions may convert badly"*; measuring it found silent
  mis-attribution, not bad conversion.

## Pinned by

`tests/test_ground_truth_addressing.py` — three tests that each **fail against the previous
resolver** (verified by reverting it, not assumed):

* `test_a_click_on_a_line_resolves_to_that_line_not_to_a_stranger_near_its_anchor`
* `test_a_click_on_a_circle_measures_to_its_outline_not_its_centre`
* `test_coincident_geometry_is_refused_rather_than_broken_by_payload_order`

plus `test_a_click_beyond_tolerance_still_resolves_to_nothing`, which passes both ways by
design — it guards the tolerance against widening later.

Related: [[Gotcha - Two Ground-Truth Stores That Never Met]],
[[Gotcha - Manual Check Wrote Through And Still Lost Work]],
[[Gotcha - A Marking Cannot Store an Entity Id]],
[[Gotcha - Dimension Scoped by Its Span Midpoint]].
