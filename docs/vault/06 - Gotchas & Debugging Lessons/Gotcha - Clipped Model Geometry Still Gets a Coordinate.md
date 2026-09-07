---
tags: [gotcha, cad, viewport, rendering, coordinates]
date: 2026-08-11
---

# Gotcha — Clipped Model Geometry Still Gets a Coordinate

## Symptom

A phantom section label (`Ａ`) floated on the sheet in vector mode — present in our canvas,
absent from both iCAD SX and the backend's own ezdxf raster of the same file. Reported as
"a ghost that the original drawing doesn't have visually".

## Root cause

`ViewportTransform.project` has a documented fallback:

```python
# Geometry outside every viewport window still has to land somewhere
# deterministic -- fall back to the first viewport rather than dropping it.
vp = self.viewports[0]
```

That is the right call — Phase 1 exists to make the projection **invertible**, and dropping
coordinates would break it. But it means the projected coordinate **cannot tell you whether
the entity is visible**. A paper-space viewport shows only its own model window; anything
outside is clipped by the CAD application and by ezdxf, no matter how reasonable the fallback
coordinate looks.

On M745221N01 the drawing has three viewports covering three disjoint model regions. One
section label sits at model `y = 110.6` while its viewport window ends at `y = 91.9` — just
outside. Projected through viewport 0 it lands in the middle of the sheet, so it looks like
legitimate annotation and renders on top of real geometry.

## Fix

`ViewportTransform.covers_model_point(x, y)` answers the question `project` cannot, and
`project_mapped_entity` records `properties.outside_viewport = True` when the entity's anchor
resolved through the fallback. `renderEntities.ts` skips those.

**Flagged, not dropped.** The coordinate is still the honest answer to "where would this be",
the entity stays in the comparison set, and only the renderer opts out. Deleting it at
ingestion would silently shrink what gets diffed.

## The trap next door

Setting the flag did nothing at first:

```python
properties = mapped.get("properties") or {}   # BUG
```

An **empty properties dict is falsy**, so `or {}` returns a *detached* dict and every write is
silently discarded. This had been latent: real entities always carry properties from
`common_properties`, so it only bites entities built without them — which is exactly what the
new test did. `PROJECTED_PROPERTY_POINT_LISTS` writes had the same exposure.

`x = d.get(k) or {}` is only safe when the empty value is genuinely uninteresting. When you
intend to *mutate* it, it has to be `setdefault`-shaped.

## What does NOT work: filtering by layout

The obvious first idea — "model-space annotation is leaking onto the sheet, so render only the
layout the raster renders" — is wrong, and measurably so. On a paper-space drawing the **part**
lives in model space; the paper layout holds only the sheet border, title block and tables.
Filtering M745221N01 to `ICADSX Layout` removes 86 entities including **all 33 ellipses (the
entire isometric view) and all 4 dimensions**.

Model geometry reaches the raster because ezdxf renders the paper layout's VIEWPORT, which
pulls model space through it — clipped. The unit of visibility is the viewport window, not the
layout.

## Lessons

1. **A deterministic fallback is not a visibility answer.** If a function is documented to
   place things "somewhere reasonable" when it cannot resolve them, downstream code needs a
   separate predicate to ask whether it resolved at all.
2. **The unit of CAD visibility is the viewport window**, not the layout. Layout membership
   tells you almost nothing about whether something is drawn.
3. **Compare against the ezdxf raster when a rendering disagrees with the CAD app.** Cropping
   the backend's own PNG at the disputed coordinate settled in one image that the label is
   genuinely not drawn there, which is what pointed at clipping.

## Related

- [[Gotcha - Wrapped Elliptical Arcs Were Tessellated Backwards]] — the other correctness defect
  found while making the vector renderer trustworthy.
- [[Gotcha - A Blurry CAD Canvas and Its Four Causes]] — why the vector path was being brought
  up at all.
- [[Gotcha - Reference and Revision in Different Coordinate Spaces]] — the other place a
  plausible-looking coordinate came from the wrong space.
