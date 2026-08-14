---
title: Gotcha - A Checklist Item With No Producer Reported Clean
type: gotcha
tags: [gotcha, checklist, taxonomy, line-attributes, false-negative, drawing-views, dxf]
status: fixed
date: 2026-08-14
---

# 🔥 Gotcha — a checklist item with no producer reported "No changes detected."

`Drawing Views → Line Attributes` has been on the checklist since the taxonomy was grouped.
Nothing has ever produced a finding for it. The card was therefore reachable only through its
empty state, and that empty state reads:

> No changes detected.

So for every comparison this system has ever run, a check that **never ran** reported a clean
result. Reported from a live review, where the card sat green beside a populated Dimensions
card on a real pair.

---

## 🎯 Why it had no producer

`feature_classifier.py` says so in its own module docstring, and has all along:

> `origin`, `alignment_of_views`, `line_attributes`, and `text_attributes` have no reliable
> text-level signal at all and are never assigned by these rules — **Generator B** (which
> reasons visually over the rendered image) is the intended source for those four.

[[ADR-006 Retiring the Hybrid Pipeline|ADR-006]] deleted Generator B. The four items were left
pointing at a generator that no longer exists, and nothing recorded that their designated
producer had gone.

Two of the four are also invisible to the deterministic differ by construction:
`COMPARABLE_ENTITY_TYPES` is `("text", "dimension")`, so a LINE is not in any comparison pool
at all — see [[Gotcha - The Differ Compared Text Only]].

---

## ✅ The honest treatment already existed, one item over

`taxonomy.DEFERRED_FEATURES` exists for exactly this, and `line_name` is in it. The frontend
renders a deferred item as *"Not yet supported for automatic checking."* instead of the normal
empty state, so it cannot read as checked-and-clean.

`line_attributes` was never added to that set. **Either treatment is defensible; the gap
between them is not.** An item with no producer must say so.

> [!IMPORTANT] The general rule.
> A checklist sub-item's empty state asserts *"checked, nothing found."* Adding a sub-item to
> `taxonomy.TAXONOMY` therefore makes a claim, and the claim is only true once something can
> assign that key. Add the item and its producer together, or add the item to
> `DEFERRED_FEATURES` in the same change.

**All four items are now resolved, by the two different routes the rule allows.**
`line_attributes` gained a producer (below). `origin`, `alignment_of_views` and
`text_attributes` were added to `DEFERRED_FEATURES` on the same day and now render *"Not yet
supported for automatic checking"* — none of the three had a false result to fix, only a false
*claim*, and deferring is the honest statement until someone builds their producer.

> [!WARNING] Membership in `DEFERRED_FEATURES` **hides rows**.
> `ChecklistPanel` tests `isDeferred` **before** `hasRows`, so a deferred key that ever carries
> a finding renders the "not yet supported" text and drops the finding on the floor. Before
> adding a key, prove nothing can assign it. Before building a producer for one, remove it from
> the set **in the same change**.
>
> That check was done for these three rather than assumed: the only backend occurrences of the
> three keys are the `TAXONOMY` declaration itself and two docstrings, `normalize_feature` has
> **no caller**, and `classify_drawing_view_feature` returns `OTHER_FEATURE_KEY` for anything it
> cannot confidently match. ⚠ Note `orchestrator.py`'s `m["origin"] = "deterministic"` is the
> CanvasMarking **provenance** field and has nothing to do with the `origin` feature key — a
> name collision that makes a grep for this look alarming.

---

## 🛠 What was built instead — `line_attribute_differ.py`

Line attributes are one of the four that did *not* need a visual generator, because the DXF
states them outright. `entity_mapper.common_properties` writes `linetype`, `lineweight`,
`color` and `ltscale` onto every graphic entity, and `dxf_parser` records the same on each
`layer` record so BYLAYER resolves. Nothing is inferred.

One row per `(linetype, lineweight)` either side draws with, over the strokes in the `views`
zone. Measured across all 42 drawings in `storage/uploads`: the whole corpus uses **four**
line types — CONTINUOUS (16200 strokes), CENTER (818), DASHED (684), HIDDEN (2).

### The key is measured, not chosen

| key                            | min | median | max |
| :----------------------------- | --: | -----: | --: |
| (linetype, lineweight)         |   4 |      5 |   7 |
| (linetype, lineweight, colour) |   8 |     11 |  15 |

Five rows is a card; eleven is a wall. Colour is also the wrong axis here: on this corpus it
is a house convention layered *on top of* the line type. The section cut plane and the part
centreline are both CENTER at 0.25mm and differ only by ACI index — `sectionCallouts.ts` finds
the cut plane by exactly that, and documents it as a client convention rather than something
the DXF states.

### ⛔ Presence decides status. A count difference never does.

This is the constraint that separates it from the reverted `geometry_differ`, whose lesson is
recorded as: **a finding must say what changed, not how many primitives differ.**

- MATCHED — both drawings use that line attribute
- ADDED / REMOVED — only one does
- **never CHANGED on a count**

A revision is a re-trace, not a copy, so stroke counts differ on nearly every real pair.
Measured on two corpus sheets: `CONTINUOUS 0.5mm x114 → x116`, `CENTER 0.25mm x9 → x5`. A
count-driven CHANGED would fire on almost every comparison and mean nothing — which is exactly
how the reverted implementation trained a checker to skim past the panel. Counts are still
shown in the ORIGINAL/REVISION cells; they are simply not a verdict.

Presence is the half that carries engineering meaning. HIDDEN appears **twice in the entire
corpus**, so a hidden line that silently becomes solid between revisions is precisely the
change no one spots by eye.

---

## ⚠️ Three things that will bite the next person

**1. `layer` records are not in the zone pool.** A layer record has no geometry, so
`zone_detector.entity_anchor` returns `None` and `scope_entities_to_views` drops it. The layer
table must be built from the drawing's **full** entity list even though the profile is counted
over the scoped pool. Resolve BYLAYER against the scoped pool and every centre line silently
files under CONTINUOUS. Pinned by
`test_layer_records_are_read_from_the_full_entity_list_not_the_zone_pool`.

**2. The pool is `ref_views_pool`, not `filtered_ref_entities`.** `safe_filter`'s remaining
passes (structured-value de-dup, learned dismissals) are keyed on TEXT. A stroke has none, so
running them would filter nothing while implying it had.

**3. BYBLOCK linetype resolves to solid, deliberately.** The colour path walks the INSERT chain
(`GeometrySerializer._inherited_from_insert`); the linetype path does not, because
`resolve_dash_pattern` puts BYBLOCK in `SOLID_LINETYPE_NAMES` and **the checklist must describe
the same strokes the canvas paints**. Three entities in the whole corpus carry a BYBLOCK
linetype. Fix both paths together or neither.

Markings carry **no coordinates**. A profile row describes every stroke of one kind across the
whole view, so there is no point a canvas pin could honestly sit at. Coordinate-free markings
were already an established shape — `inject_title_block_markings` emits them.

---

## 🔍 Corpus fact worth keeping: these DXFs carry no application attributes

Asked whether a line could carry a semantic attribute type directly, so the colour heuristic in
`sectionCallouts.ts` could be replaced with something the file states. Swept all 42 drawings:

```
APPIDs registered, all 42 files:
  ACAD, ACAD_DSTYLE_DIM_LINETYPE, ACAD_DSTYLE_DIM_EXT1_LINETYPE,
  ACAD_DSTYLE_DIM_EXT2_LINETYPE, ACAD_MLEADERVER, ACAD_DSTYLE_DIMRADIAL_EXTENSION

Non-Autodesk XDATA on any entity:  NONE
Extension dictionaries:            DIMENSION (817), VIEWPORT (162) — Autodesk internals
```

Every XDATA tag in the corpus belongs to an `ACAD*` appid and is formatting internals. **No
entity in this corpus carries client semantics.** So colour/linetype/lineweight is not a
shortcut around a better field — it is the only channel present, which is what makes the
`(linetype, lineweight)` profile the honest ceiling for this check.

Two genuine semantic carriers did turn up and are worth their own look:
- **`SX_FinishSymbol_1`** — a named block in 15 files. A far stronger anchor for the finish
  symbol than matching the string `仕上げ`, which is on record as a false detection anchor.
- **Layer names split the corpus in half**: 21 files use `NoLayerName_001..003`, the other 21
  use named layers (`RAHM2`, `2`–`8`, `7A`, `VIEWPORTS`). `sectionCallouts.ts` says this corpus
  puts everything on `NoLayerName_001`; that is true of the iCAD SX half only.

Also measured while there: every one of the **14** sheets carrying an `X-X` designation has its
cut plane as a strict minority colour among its CENTER lines, so `findCutPlaneLines` holds
across the grown corpus. Its docstring says 9, measured when `storage/uploads` was smaller.

---

## Guarded by

`tests/test_taxonomy_consistency.py::test_deferred_features_match` — the backend set and the
frontend `DEFERRED_FEATURE_KEYS` mirror are parsed and compared, so the two cannot drift.

`tests/test_line_attribute_differ.py` — 20 cases. The load-bearing ones:
`test_the_card_is_filled_when_both_drawings_are_identical`,
`test_a_stroke_count_difference_is_never_a_change`,
`test_a_line_type_only_the_reference_uses_is_reported_removed`,
`test_layer_records_are_read_from_the_full_entity_list_not_the_zone_pool`,
`test_colour_does_not_split_a_row`,
`test_the_feature_key_is_a_real_taxonomy_item`.

Cache invalidated at **v49**.

## 🔗 Related Notes
- See [[Gotcha - The Differ Compared Text Only]] — why bare geometry is not compared, and the count-vs-content lesson this obeys
- See [[Gotcha - The Engine Ignored the Section Callout but the Canvas Still Drew It]] — the colour convention this reuses and does not depend on
- See [[Gotcha - Comparison Cache Invalidation]]
- Return to [[00 - Map of Content (MOC)]]
