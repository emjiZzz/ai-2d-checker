---
tags: [gotcha, comparison, zones, dimensions]
status: fixed
cache-version: v37
date: 2026-08-04
---

# Gotcha — A Dimension Was Scoped by Its Span Midpoint

## Symptom

On the `M7452A1N01` pair, the reference drawing and the revision **both** carry a ⌀260
diameter dimension, unchanged. The audit reported it as a lone **ADDED** finding
(`M004`, `drawing_views`, feature `dimensions`) — with **no REMOVED counterpart**, and with
⌀120 and ⌀140 correctly MATCHED right next to it.

The missing REMOVED is the tell. A real add/remove asymmetry produces one of each; a lone
ADDED means the reference entity never entered the comparison pool at all.

## Root cause

`scope_entities_to_views` located every entity at the **centroid of `_entity_points`** — the
average of every coordinate the entity contributes. For text and geometry that is the right
answer. For a DIMENSION it is not:

| | ref ⌀260 (handle `28B`) | rev ⌀260 (handle `2DF`) |
|---|---|---|
| `text_point` (where the value is drawn) | (446.5, **358.5**) | (170.6, **142.2**) |
| `def_point` (the measured feature) | (446.5, 228.5) | (170.6, 194.2) |
| centroid used for scoping | (446.5, **293.5**) | (170.6, 168.2) |
| detected `tolerance` safe zone | (45.0, 76.6, 1042.5, **299.4**) | (−1.7, −2.9, 397.3, 86.2) |
| result | midpoint inside `tolerance` → **dropped** | clear → **kept** |

The centroid of a dimension is the midpoint between the feature and its value — **a phantom
point where nothing is drawn**. The reference ⌀260 spans y = 228.5 → 358.5, so its midpoint
landed inside the tolerance table's safe zone (a `views` sibling, always excluded), and the
dimension was dropped from the reference pool. The revision's ⌀260 has a shorter span in a
smaller coordinate space, so its midpoint cleared the zone and it stayed in. One side in, one
side out → phantom ADDED.

⌀120 survived on both sides only because its span is shorter — its midpoint (y = 328.5) misses
the tolerance box by 29 units. **Whether a dimension was compared at all depended on how far
its extension lines happened to reach.**

This also meant zone scoping and marker placement could disagree about the same dimension:
`SpatialDiffer._get_entity_coords` already anchors dimensions at `text_point`, so a dimension
could be scoped by one point and pinned at another, in a different zone.

## Fix (cache v37)

New `zone_detector.entity_anchor(entity)` — the one point that decides zone membership:

- **dimension** → `text_point`, falling back to `def_point` / `insert` / `location`.
- **everything else** → centroid of `_entity_points`, exactly as before, so lines/arcs/
  ellipses are still located correctly (see
  [[Gotcha - drawing_views Was the Residual, Not the Views Box]] for why that matters).

`scope_entities_to_views` now uses it. Scoping and marking agree on where a dimension is.

Verified on the live pair: the reference views pool goes 50 → 51 entities, the ⌀260 enters
both pools, and the finding comes back **MATCHED** (⌀120 and ⌀140 unaffected).

## The second defect underneath it — the tolerance zone was eating the drawing

Fixing the anchor exposed a second, independent bug hiding behind it. `22.7±0.02` was still
dropped — on **both** sheets, so it produced no false finding, just silence. Its `text_point`
genuinely fell inside the detected `tolerance` box, and that box was wrong:

| | ref | rev |
|---|---|---|
| detected `tolerance` box | (45.0, 76.6, 1042.5, 299.4) | (−1.7, −2.9, 397.3, 86.2) |
| as a fraction of the sheet | **0.95w × 0.30h** | **0.95w × 0.30h** |
| `ZONE_MAX_LIMITS["tolerance"]` | **(0.95, 0.30)** | **(0.95, 0.30)** |

Pinned at *both* caps on *both* drawings. A box that lands exactly on its cap in both axes is
not a detection — it is a flood-fill that ran away and got clamped. `tolerance` grew on the
isotropic `CLUSTER_RADIUS` (200) **with line geometry included**, so `_expand_bbox` hopped
along the sheet frame and the table's own column rules, across the full width and ~150 units up
into the drawing area. The reference box swallowed the `22.7±0.02` dimension (y = 179.7), the
`6-6.6キリ11ザグリ深6.5` hole callout (y = 205.4) and both section marks.

Because `tolerance` is a **safe zone that `views` subtracts**, everything it swallowed was
silently dropped from the drawing_views comparison. No finding, no warning — the content simply
was not checked, on every drawing in the corpus.

**Fix:** `tolerance` now grows on a decoupled wide-X/tight-Y radius
(`max(50, w*0.15), max(12, h*0.03)` — same shape as `bom`, which is the same shape of object)
and joins `title_upper_left`/`bom`/`notes` in `exclude_lines`. Measured after:

| | before | after |
|---|---|---|
| ref box height | 30.0% of sheet (capped) | **14.7%** |
| rev box height | 30.0% of sheet (capped) | **16.4%** |
| tolerance-table rows still covered | all | **all** |
| ref drawing_views pool | 51 entities | **89** |
| rev drawing_views pool | 76 entities | **92** |

The corroborating detail: after the fix the tolerance box top (ref 141.6, rev 59.2) lands just
under the independently pinned `views` box bottom (ref 148.7, rev 59.5) on both sheets. Two
values derived from completely different sources agreeing to within a few units is what a
correct box looks like.

`22.7±0.02`, both section marks and the hole callout are now compared. The callout comes back
CHANGED — the revision reads `ザグリ深サ` where the reference reads `ザグリ深`, a genuine text
edit — which is the system working, not a false positive.

## Follow-on: the section callout that looked like noise

Widening the pool surfaced three new findings — `Ａ` ×2 and `Ａ－Ａ`, all ADDED — which read as
junk. Checked before acting, and they are **genuine**: the reference carries only two `Ａ`
texts, both on layer `WAKU` (枠, frame) at the sheet edges, which `is_margin_grid_text`
correctly excludes as grid labels. It has no section arrows and no `Ａ－Ａ` title anywhere, and
no block ATTRIBs hiding one (every block on both sheets has `attributes == {}`). The revision
genuinely adds a section designation. ADDED is the right answer.

What was wrong was the *label*: all three landed in `other` — "Other / Unclassified", the
bucket meaning *the system could not identify this* — so a real, nameable change read as three
unexplained rows. `additional_views` ("Additional Views") already existed for exactly this.

Two reasons it missed:
- `_ADDITIONAL_VIEW_KEYWORDS` only had the spelled-out `view a-a`. This corpus writes the bare
  designation, fullwidth: `Ａ－Ａ`, which NFKC-folds to `A-A`. Now matched by
  `_SECTION_DESIGNATION_RE`, which requires **the same letter twice** — `A-B` is a range or a
  part code, not a section.
- The two cut arrows are each a lone `Ａ`, which carries no signal on its own; it is equally a
  balloon, a zone reference or a part label. `refine_view_labels` resolves it from drawing
  context instead of guessing: a lone `X` is a section arrow **only if** that drawing also
  carries an `X-X` designation.

This reversed `test_bare_section_label_stays_unclassified`, which had asserted `Ａ－Ａ` must stay
`other`. That test's anti-folding reasoning still holds and is still tested; its conclusion did
not survive contact with the review panel. The reversal is recorded in the test's own docstring.

**Note the distinction this turns on:** a finding being unwanted in review and a finding being
wrong are different problems with different fixes. This one was correct and misfiled, so the
first fix was the label, not the comparison.

Classification alone was not the whole answer, though. The reviewer's position — and they are
the domain expert — is that the section IDENTIFIER is draughting furniture: *which letter names
a cut* says nothing about the part, and it re-letters freely between revisions. So
`orchestrator.DROP_SECTION_CALLOUT_LABELS` (default True) now drops these three findings.

The classification work is still what makes the suppression safe. `refine_view_labels` returns
exactly the designation and its context-resolved arrows — **not** everything classified
`additional_views`, which also holds real content like `詳細Ｂ 尺度2:1` where the scale is an
engineering change. Suppressing by feature key would have taken that with it.

What is given up, recorded so it is not rediscovered as a bug: a revision that adds or removes
a section view now reports the change in that view's **contents** but not the callout itself.
The geometry inside the named view is compared exactly as before. Set the flag False to
restore it.

## Rules to carry forward

1. **An entity's "position" is where a human reads it, not the average of its coordinates.**
   Any entity type whose geometry spans a distance — dimensions, leaders, anything with a
   pointer and a payload — needs an explicit anchor. Averaging puts it somewhere nothing is
   drawn, and zone containment then answers a question about empty space.

2. **A zone box sitting exactly on its cap is a bug report, not a measurement.** `ZONE_MAX_LIMITS`
   is a safety net; a box that hits it has told you the flood-fill did not converge. Worth
   logging as a warning rather than leaving to be noticed by eye.

3. **Never flood-fill a ruled table along its own rules.** Table rules are collinear with the
   sheet border and with every other table's rules, so line-following bridges any box to any
   other furniture and then to the drawing. Every ruled zone here is dense with text; seed from
   the text (`exclude_lines=True`) and the box still covers the table.

4. **An over-grown SAFE zone fails silently and is therefore the expensive kind.** A compared
   zone that is too big produces visible noise. A safe zone that is too big produces *nothing* —
   the content it covers is subtracted from `views` and never checked, and the audit looks
   clean. Suspect the safe zones when a finding is missing rather than wrong.

## Related

- [[Gotcha - The Differ Compared Text Only]] — dimensions only started being compared in v36;
  this defect was invisible until then.
- [[Gotcha - drawing_views Was the Residual, Not the Views Box]] — strict `views` scoping is
  what makes a wrong anchor drop a finding instead of merely misfiling it.
- [[Gotcha - Zone Detection Accuracy & Stability]] — zone box sizes are what a bad anchor
  collides with.
- [[Gotcha - Comparison Cache Invalidation]] — v36 → v37; cached results carry the wrong
  status for any dimension whose span crosses a zone boundary.

Pinned by `tests/test_views_scoping.py::test_dimension_located_by_text_point_not_the_span_midpoint`
and its converse, `test_dimension_whose_value_sits_in_a_sibling_zone_is_still_excluded`; the
tolerance half by `tests/test_tolerance_zone_growth.py` (which covers both directions: the box
must still cover its own table, and must not reach content above it).
