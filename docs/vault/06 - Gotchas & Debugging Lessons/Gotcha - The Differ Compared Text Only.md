---
title: Gotcha - The Differ Compared Text Only
type: gotcha
tags: [gotcha, spatial-differ, rag, geometry, iso, measurement, negative-result, reverted]
status: reverted
date: 2026-07-29
updated: 2026-08-04
---

# 🔥 Gotcha — the deterministic differ compared TEXT only

> [!WARNING] The fix described here was REVERTED on 2026-08-04 (cache v33).
> `geometry_differ.py` and its tests are **deleted**; the differ does not compare bare shapes,
> on purpose. Read [[#❌ Why it was removed]] before re-implementing it.

> [!IMPORTANT] The defect had TWO halves. Only the shape half was reverted.
> "Text only" excluded both **bare geometry** (lines, circles, ellipses) *and* **DIMENSION
> entities**. `geometry_differ` addressed the first and was reverted as unactionable. The
> second — dimensions, which are the actual engineering content of a drawing view — was never
> addressed at all until 2026-08-04 (cache v36) and is now fixed in `spatial_differ` itself.
> See [[#✅ The dimension half, fixed in the differ]].

`SpatialDiffer.diff_views` builds both of its pools from `entity_type == 'text'`:

```python
for e in ref_entities:
    if getattr(e, 'entity_type', '') == 'text':
        ...
```

Lines, circles, arcs, polylines, ellipses and splines were therefore **never compared**. A
feature that carries no text did not exist as far as the audit was concerned. Nothing in the
output said so — the report simply had no row for it.

---

## 🎯 The case that exposed it

The M7452A0N01 revision carries an **isometric view the reference does not have** — 38
ellipses plus surrounding line work. The comparison reported **nothing at all** about it.

Two compounding causes:

1. **Geometry was never in the pool.** The iso view is ellipses and lines; no text to key on.
2. **`diff_views` returns `[]` when either pool is empty.** With the reference having no iso
   zone, `ref_iso_entities` is `[]`, so the function bailed before doing anything. A zone
   present on only one drawing was *guaranteed* zero findings — precisely the case where the
   finding matters most.

This also explains why ingesting ELLIPSE/SPLINE (see
[[Gotcha - Dropped ELLIPSE & SPLINE Geometry]]) made the iso view detectable and renderable
but still produced no audit finding: two separate defects on the same path.

---

## ✅ The dimension half, fixed in the differ (2026-08-04, cache v36)

A DXF DIMENSION is `entity_type == 'dimension'`, not `'text'`, so **every dimension on every
drawing this system has ever audited was dropped before comparison started** and could never
receive a checkmark. On the M7452A1N01 pair that is all four of ⌀120, ⌀260, ⌀140 and 22.7±0.02 —
they reach the `views` zone pool correctly and are then discarded by the pool filter.

Three things had to land together:

**1. Admit dimensions to the pools.** `COMPARABLE_ENTITY_TYPES = ("text", "dimension")`.
`leader`/`multileader` are deliberately excluded — their text duplicates the feature they point
at.

**2. Read dimension geometry.** Dimension geometry has **no `insert` key** — its coordinates are
`text_point`, `def_point`, `ext1_point`, `ext2_point`. `_get_entity_coords` read only `insert`
and returned `(0.0, 0.0)` otherwise, so admitting dimensions without this would have stacked
every one of them on the sheet origin. It now reads `insert → location → text_point → def_point`
and returns **None** rather than `(0,0)` when there is nothing usable — a silent origin is
indistinguishable from a real coordinate at the origin.

**3. Compare `measurement`, not display text.** This is the one that decides between four
correct checkmarks and four false CHANGED:

| reference `text` | revision `text` | `measurement` (both) |
| :-- | :-- | :-- |
| `%%c120` | `120` | 120.0 |
| `%%c260` | `260` | 260.0 |
| `%%c140` | `140` | 140.0 |
| `22.7±0.02` | `22.7` | 22.7 |

The same unchanged dimension is authored as a **text override** on the reference and left to the
**dimension style** on the revision. Both render `⌀120`; their `text` properties do not match.
The comparison key is therefore `dim:<kind>:<measurement>`, with `measurement` rounded to 6
decimals (observed float noise is ~1e-13: `140.0000000000002` vs `140.0000000000005`) and
`dim_type` masked to its low 3 bits so a linear 120 never matches a diameter 120 while a flipped
"user-defined text location" flag does not read as an engineering change.

A `kind` gate keeps dimensions and text in separate match spaces — their keys are measurements,
not strings, so a stray `120` label would otherwise pair with a 120mm dimension.

> [!NOTE] Dimension display text skips `safe_decode` on purpose.
> `strip_mtext` alone resolves `%%c` → ⌀ and leaves `±` intact. `safe_decode` would additionally
> run its mojibake repair, which **corrupts a literal `±` into halfwidth katakana ｱ**
> (`22.7±0.02` → `22.7ｱ0.02`, visible in the rendered reference). Dimension text is symbols and
> digits, never CJK, so it does not need that pass. **That `safe_decode` bug is still open** and
> affects every other decoded string in the system — it was deliberately split out rather than
> fixed here, because it is called on every text entity of every drawing.

---

## ⛔ The shape half — tried and reverted — `geometry_differ.diff_geometry`

Runs on the same zone-scoped pools as the text differ, in the same normalized frame (see
[[Gotcha - Reference and Revision in Different Coordinate Spaces]]), and **does not bail on
an empty side**.

Measured on the real pair after re-ingest:

```
ADDED   Geometry: 38 ellipse, 4 line    at [365.4, 222.6]   <- the isometric view
ADDED   Geometry: 13 line, 6 polyline
ADDED   Geometry: 3 line, 3 circle
REMOVED Geometry: 18 line
REMOVED Geometry: 3 circle, 2 line
...
```

Nine findings for the whole sheet, the largest being the iso view. Previously: zero.

---

## ❌ Why it was removed

Reverted 2026-08-04 after review of live output. **The findings were unactionable.** A row reading

```
[M011]  Geometry: 10 line     Cat: drawing views     Stat: MISMATCHED
```

names a *count* and a *primitive type* and nothing else. A checker cannot do anything with it:
it does not say which feature changed, or how, or whether it matters. Meanwhile every one of
these rows occupies a slot in the checklist and a marker on the canvas, competing with the text
findings that carry actual engineering content.

The measured nine-findings-per-sheet result above reads as a success only if you assume every
finding is worth a checker's attention. In practice one of the nine (the iso view) was, and the
rest were `N line` / `N circle` noise from tessellation differences, redrawn detail and
insignificant edits that the position/size tolerances could not separate from real changes.

**The known, accepted cost.** Both original causes are back in force: geometry is not in the
pool, and `diff_views` still returns `[]` when either side is empty. So **a zone present on only
one sheet and carrying no text reports nothing at all** — the motivating isometric-view case is
once again invisible. This was weighed explicitly and accepted: silence beats unactionable noise,
because noise trains a checker to skim past the panel and that costs more than the one missed
class of finding.

> [!IMPORTANT] If you re-implement this, do not re-implement *this*.
> The lesson is not "geometry diffing is wrong" — it is that **a finding must say what changed,
> not how many primitives differ**. A viable version would need to identify the *feature*
> (a hole, a slot, a view) and state the change in engineering terms. Clustering unmatched
> primitives by centroid cannot do that, and no amount of tolerance tuning gets it there.
>
> The deleted implementation and its tests are in git at commit `882250f`:
> `git checkout 882250f -- services/backend/infrastructure/audit/comparison/geometry_differ.py tests/test_geometry_differ.py`

---

## 🧭 Three deliberate omissions (of the reverted implementation)

These are choices, not oversights. Changing any of them is a decision, not a bug fix.

**Clusters, not entities.** Unmatched geometry is grouped spatially and each cluster is ONE
finding. A finding per entity would have produced hundreds of rows on a 528-entity drawing and
buried the text findings that are the checklist's actual content. `MIN_CLUSTER_ENTITIES = 4`
drops stray hatch ticks and lone centre-line fragments; `MAX_CLUSTERS_PER_SIDE = 5` stops a
wholesale redraw flooding the panel.

**No MATCHED findings.** Silence means matched, as a human checker would treat it. One row per
matched line is pure noise.

**No CHANGED findings.** A circle whose radius moved is a real engineering change — but on a
dimensioned drawing the text differ already reports it as a dimension change
(`%%c120` → `%%c130`), so a geometric CHANGED would double-report the common case. Picking a
radius tolerance that separates a real size change from tessellation and rounding noise is a
tuning exercise with **no measured basis yet**. Left out deliberately rather than guessed at.
Take a measurement before adding it.

> [!NOTE]
> `dimension`, `leader` and `multileader` are excluded from `GEOMETRY_TYPES`. Their meaning is
> their text, which the text differ already compares, and their geometry moves whenever the
> feature they point at moves — including them would report every annotation twice.

---

## ⚠️ What is still not compared

`hatch` is excluded. A hatch is a fill whose boundary tracks the shape it fills, so it would
restate whatever the boundary geometry already reports. If section-fill changes ever need
auditing on their own, that is a separate decision with its own tolerance question.

Matching keys on kind + normalized centroid + normalized extent. Two different features of the
same kind at the same place and size are indistinguishable to it — acceptable, because the
consequence is a missed finding rather than a wrong one.

---

## Guarded by

`tests/test_spatial_differ.py` — seven cases pinning the dimension half:
`test_dimensions_are_compared_at_all`,
`test_unchanged_dimension_matches_despite_different_display_text`,
`test_changed_dimension_measurement_is_reported`,
`test_dimension_coordinates_come_from_text_point_not_the_origin`,
`test_a_dimension_never_pairs_with_a_text_of_the_same_number`,
`test_diameter_and_linear_dimensions_of_equal_size_are_not_silently_matched`,
`test_dimension_display_text_resolves_the_diameter_escape`.

## 🔗 Related Notes
- See [[Gotcha - Dropped ELLIPSE & SPLINE Geometry]] — why the iso view's geometry was not even in the database
- See [[Gotcha - Reference and Revision in Different Coordinate Spaces]] — the normalized frame this reuses
- See [[Gotcha - Zone Detection Accuracy & Stability]]
- See [[RAG Engine (Deterministic)]]
- Return to [[00 - Map of Content (MOC)]]
