---
title: Gotcha - Dropped ELLIPSE & SPLINE Geometry
type: gotcha
tags: [gotcha, ingestion, entity-mapper, zone-detector, iso, isometric, measurement]
status: resolved
date: 2026-07-29
---

# 🔥 Gotcha — ELLIPSE and SPLINE were dropped at ingestion

`EntityMapper.map_any` routed DXF types to mappers with an `if/elif` chain and had **no
branch for `ELLIPSE` or `SPLINE`**, so it returned `None` for both and
`dxf_parser.process_entity` silently discarded them. Not a rendering gap and not a
comparison gap — the entities never reached the database at all.

This is the root cause of the long-standing "[[Gotcha - Zone Detection Accuracy & Stability|`iso` has never been detected]]" symptom, and it went unnoticed for the reasons in *Why it hid* below.

---

## 📏 Measured impact

Across the 6-drawing corpus, **111 `ELLIPSE` + 46 `SPLINE` were dropped**. The losses are
not spread evenly — they land entirely on the three drawings that carry an isometric view:

| Drawing | ELLIPSE | SPLINE | Dropped | Iso view |
| :--- | ---: | ---: | :--- | :--- |
| `2efb5c4c` | 0 | 0 | 0 / 508 | — |
| `c43f1d10` | 0 | 0 | 0 / 548 | — |
| `ef043223` | 0 | 0 | 0 / 509 | — |
| `31d15527` | 38 | 0 | **38 / 135 (28.1%)** | block `JZB_0014` |
| `4cbfc679` | 63 | 14 | **77 / 369 (20.9%)** | block `JZB_0015` |
| `daabcba6` | 10 | 32 | **42 / 271 (15.5%)** | block `JZB_0010` |

Measured at the level of the isometric view itself, the loss is near-total:

| Iso block | Entities | Dropped | Share |
| :--- | ---: | ---: | ---: |
| `JZB_0014` | 42 | 38 | **90.5%** |
| `JZB_0015` | 120 | 70 | 58.3% |
| `JZB_0010` | 54 | 28 | 51.9% |

> [!WARNING]
> No downstream fix could ever have worked. A text detector, a geometric detector and an
> AI-vision pass over stored entities would all have been reading a hollowed-out remnant
> of the view they were being asked to find.

---

## 🕵️ Why it hid

1. **The mapper fails open.** `map_any` ends with a bare `return None`, and the caller
   treats `None` as "not of interest" rather than "unhandled type". An unknown type is
   indistinguishable from a deliberately-skipped one.
2. **Nothing counted what was skipped.** `dxf_parser`'s `counts` dict was seeded with the
   handled types only, and unhandled types were never added, so "this drawing has no
   ellipses" and "ellipses were never counted" produced identical output. `counts` now
   seeds `ellipse` and `spline` at 0 so the distinction is visible.
3. **The affected drawings looked fine.** The three sheets with no ellipses are the
   *reference* drawings; nothing was missing from them, so any spot-check of a reference
   passed.
4. **`iso`'s metric looked healthy.** It reported 0.0pp positional spread, the best in the
   system. That was six identical percentage-grid guesses — see Trap 1 of
   [[Gotcha - Zone Detection Accuracy & Stability]].

---

## ✅ Ellipse density is the isometric-view signal

A circle viewed at an angle projects to an ellipse. Orthographic views keep their circles
as `CIRCLE`/`ARC`; an axonometric view converts them to `ELLIPSE`. Corpus separation is
total — **38 / 63 / 10 against 0 / 0 / 0** — so `MIN_ISO_ELLIPSES` needs no tuning and only
guards against a stray true ellipse (an obliquely-cut cylinder, a slot).

`zone_detector._detect_iso_zone` uses this in two stages:

1. **Block dominance.** An isometric view is normally placed as a single `INSERT`, so when
   ≥60% of the ellipses share one `parent_handle`, that block's extent *is* the zone —
   exact, with no clustering heuristic and no percentage grid.
2. **Clustering fallback.** Nested `INSERT`s lose the parent handle during explosion and
   loose model-space geometry never had one, so single-linkage clustering of ellipse
   centres backs it up.

It returns `None` when there is no isometric view, which matters as much as returning a
box: half the corpus genuinely has none, and the old behaviour asserted a grid guess on
every drawing.

---

## ❌ Negative result — the 30°/150° line-angle test is worse

The obvious geometric approach is that isometric axes sit at 30° and 150°. Measured, it is
materially weaker than ellipse density and should not be revisited without new evidence:

- **Dimension and leader arrowheads are drawn near 30°** and are scattered sheet-wide.
- **`SX_FinishSymbol_*` blocks** (surface-finish marks) are also ~30° triangles, and appear
  on drawings with *and* without isometric views.
- Result: on `31d15527` the 30/150° segments spanned `x = 0.13…0.99`, `y = 0.00…0.85` of
  the sheet — essentially the whole drawing. Filtering by segment length helped but did not
  separate the classes.

Angle is a property of *lines*, which every view has. Ellipse-vs-circle is a property of
the *projection*, which is the thing actually being detected.

---

## 🧭 Trap — `major_axis` is a vector, not a coordinate

DXF stores an ellipse as centre + major-axis **offset vector** + minor/major `ratio`.
Running that vector through the viewport projection as if it were a point re-anchors it to
the viewport origin and reshapes the ellipse — while still producing a closed, plausible
curve.

`GEOMETRY_SCHEMA` therefore gained a **`vectors`** category alongside `points`,
`point_lists` and `lengths`: vectors take the viewport *scale* but not the *translation*.
Pinned by `test_major_axis_is_scaled_but_not_translated`.

The same reasoning applies to the tessellation: the minor axis is the major axis rotated
90° and scaled by `ratio`, so deriving it wrongly shears the ellipse in a way that still
looks round. `test_tessellation_handles_a_rotated_major_axis` asserts a `ratio=1.0`
ellipse with a rotated major axis stays a true circle.

---

## ⚠️ Confound — iso presence correlates with toolchain, not only revision status

Both confirmed pairs run reference-without-iso → revision-with-iso:

| Pair | Reference | Revision |
| :--- | :--- | :--- |
| 1 | `ef043223` — no iso | `daabcba6` — `JZB_0010` |
| 2 | `2efb5c4c` — no iso | `31d15527` — `JZB_0014` |

But the iso-bearing sheets also use `NoLayerName_001…004`, `SX_DraftLine`, `VIEWPORTS` and
`Defpoints` layers with `JZB_*`/`SX_*` blocks, while the non-iso sheets use numeric AutoCAD
layers (`0`, `1`, `2`, `2A`, …). Combined with `sw_converter.py` in the repo, that reads as
*the revisions were regenerated from SolidWorks 3D*, which is why they carry an isometric
view at all.

> [!IMPORTANT]
> This is a toolchain artifact, not a drafting convention. Do **not** encode "revisions have
> isometric views" as a rule — it would not hold for a customer who revises in AutoCAD. n=2
> pairs.

---

## 🚨 Already-ingested drawings need re-extraction

The fix is at **ingestion** time. `COMPARISON_CACHE_VERSION` → `v10` invalidates cached
*comparisons*, but it does not touch the `DrawingDocument` entity lists already stored in
MongoDB — those were written by the old mapper and still have no ellipses or splines.

> [!WARNING]
> A drawing ingested before this change will still show no isometric view, and no amount of
> re-running the comparison will fix it. **Re-upload or re-extract the drawing.** The cache
> bump makes the comparison honest about the entities it is given; it cannot add entities
> that were never stored.

---

## 🧩 Still open

- **Splines flatten via `ezdxf.flattening`, which needs a live document.** Detached or
  virtual entities fall back to control points, which is coarser. Not currently a problem
  because ingestion parses whole files, but it is why the fallback exists.
- **`_get_xy` still does not read `center`.** `detect_subviews` admits `arc` and `circle` in
  its entity filter, but those resolve to `None` and are skipped. Teaching `_get_xy` about
  centres would change sub-view boxes as a side effect, so `_ellipse_center` was added
  separately instead. Worth measuring on its own.
- **Comparison output will move.** The engine now sees geometry it was blind to, so those
  features become reportable as ADDED/REMOVED/CHANGED for the first time. This has not been
  measured against a corpus — see the note below.
- **The corpus DXFs were deleted from `storage/uploads` during this work** (only
  `storage/temp/fresh_test_drawing.dxf` remains). The figures above were measured before
  that; re-measuring needs the files re-ingested. `tests/test_iso_zone_detection.py`
  therefore builds its geometry explicitly rather than reading fixtures.

---

## 🔗 Related Notes
- See [[Gotcha - Zone Detection Accuracy & Stability]] — the `iso` symptom this explains
- See [[Gotcha - Comparison Cache Invalidation]] — why `COMPARISON_CACHE_VERSION` went to `v10`
- See [[Zone Detector & Bounding Boxes]]
- See [[ezdxf Entity Extraction]]
- Return to [[00 - Map of Content (MOC)]]
