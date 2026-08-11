---
tags: [gotcha, cad, ingestion, geometry, zones]
date: 2026-08-11
---

# Gotcha — Wrapped Elliptical Arcs Were Tessellated Backwards

## Symptom

The isometric flange on M745221N01 rendered as a **broken crescent**: two ring arcs covering
roughly half their sweep and six bolt holes drawn as open fragments. ezdxf's own raster of the
*same entities* drew two closed rings and six closed bolt holes.

All 33 ellipses were present in Mongo, all 33 were drawn, and the extracted points were
byte-identical to what `map_ellipse` produced from the source file. Nothing was lost in
storage, projection or rendering — the geometry was wrong at the moment it was computed.

## Root cause

A DXF ellipse **always sweeps counter-clockwise from `start_param` to `end_param`**, so
`end < start` means the arc wraps through 2π. It does not mean the arc runs backwards.

`_tessellate_ellipse` took the raw difference:

```python
sweep = end_param - start_param     # 0 - 180deg = -180deg
```

and swept the short way round, drawing the arc on the **opposite side of its own ellipse** —
landing on top of arcs already there and leaving the half it should have covered empty.

On this drawing 9 of 33 arcs wrap:

```
 2 start=180.0 end=  0.0 span=-180.0
19 start=225.0 end=  0.0 span=-225.0
```

### Why reading the source file made it look fine

**The wrap only appears after block explosion.** The block *definitions* store `(180, 360)` —
a clean positive sweep. The INSERT transform is what rewrites it to `(180, 0)`. So inspecting
`doc.blocks` shows a healthy span histogram (`{135: 9, 45: 9, 180: 8, ...}`, all positive) and
the defect is invisible; it only exists in the exploded geometry that actually gets rendered.
Diagnosing this from the block definitions costs an hour and concludes "the params are fine".

## Fix

```python
sweep = end_param - start_param
if sweep <= 1e-12:
    sweep += math.tau
```

which also handles the full-ellipse-as-`(0, 0)` case correctly (0 → τ). `is_closed` was
normalised the same way (`(end - start) % tau`), since a wrapped full ellipse was previously
reported as an open arc.

## This is not only a rendering bug

`zone_detector._detect_iso_zone` locates the isometric view **by ellipse density**, and sizes
it via `_largest_ellipse_cluster`, whose extent is computed from exactly these tessellated
points. A half-covered ring yields a smaller, offset `iso` box than a complete one — so every
cached audit of a drawing with an isometric view was scoped against a wrong zone.

`COMPARISON_CACHE_VERSION` bumped **v43 → v44** accordingly. This is precisely the case
constraint 2 in `CLAUDE.md` exists for: the fix is in ingestion, but the blast radius reaches
zone extraction and therefore the cache.

## Lessons

1. **`end < start` on a DXF arc means wrap, not reverse.** Same for ARC `start_angle` /
   `end_angle`. Normalise the sweep, never take the raw difference.
2. **Inspect the geometry that renders, not the geometry on disk.** Block definitions and
   exploded virtual entities carry *different* parameters; the transform rewrites them. Any
   ingestion bug involving blocks has to be reproduced post-explosion.
3. **Compare against ezdxf's own raster.** It reads the same file and is the cheapest available
   ground truth. Rendering the extracted vectors beside a crop of the backend's PNG turned
   "something looks off" into a specific, provable defect in one image — but only once both
   panels showed the *same entity types*. An earlier comparison plotted ellipses-only against a
   raster crop containing everything, which made faithful extraction look like data loss.

## Related

- [[Gotcha - Dropped ELLIPSE & SPLINE Geometry]] — ellipses were previously dropped entirely at
  ingestion. They now arrive, but arrived *wrong*; the same isometric view was the casualty
  both times, and the same `iso` zone depends on them.
- [[Gotcha - A Blurry CAD Canvas and Its Four Causes]] — this was found while making the vector
  renderer viable, and is one of the two defects that had to be fixed for it to be trustworthy.
- [[Gotcha - Comparison Cache Invalidation]] — why the v44 bump is mandatory here.
