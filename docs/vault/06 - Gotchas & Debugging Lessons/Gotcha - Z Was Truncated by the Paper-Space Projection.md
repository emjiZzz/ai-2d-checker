---
tags: [gotcha, cad, ingestion, coordinates, 3d, dxf]
status: fixed
cache-version: none — proven Z-only, see "Why no cache bump" below
date: 2026-08-06
---

# Gotcha — Z Was Truncated by the Paper-Space Projection

> [!WARNING] Every Z coordinate was destroyed at ingestion on any drawing with a paper-space
> layout — 6 of the 11 files in the local corpus. Drawings *without* a layout kept theirs, so
> the loss was invisible: stored geometry had two different shapes and nothing read the third
> component anyway.

## What happened

`project_mapped_entity` projects model-space coordinates into paper space through the
viewport transform. Its inner helper ended:

```python
def project_point(point: Any) -> list[float]:
    result = transform.project(float(point[0]), float(point[1]), state["index"])
    ...
    return [result.x, result.y]        # ← the third component, gone
```

The mappers feed it 3-component points — `map_line` has always stored
`[start[0], start[1], start[2]]`, and `_as_xyz` has existed for a long time — so the Z was
present right up until this line and then silently dropped.

`ViewportTransform` is genuinely two-dimensional, and correctly so: a paper-space viewport is
a *window onto the model's XY plane*. It has no Z axis to map into and no scale that means
anything for one. The mistake was expressing "this transform does not touch Z" as "this
transform deletes Z".

## Why it stayed invisible

Three things hid it, and each one is the interesting part:

1. **The identity early-return.** A drawing with no paper-space viewports returns from
   `project_mapped_entity` before `project_point` is ever called, and keeps its Z. So the
   corpus contained *both* shapes at once. There was no single observation that looked wrong.
2. **Nothing downstream reads `[2]`.** The comparison engine, zone detection, the canvas
   renderer and the bbox maths all slice `[0]` and `[1]`. Deleting a field that no consumer
   reads produces no error, no warning, and no visible defect — until the first consumer that
   needs it arrives, at which point the data is already gone from every stored document.
3. **The corpus is flat.** All 11 local DXFs are entirely 2D: 4,035 coordinates scanned,
   zero non-zero Z, zero 3D entity types, zero tilted extrusion vectors. A fixture that would
   have caught this does not exist on this machine and had to be written synthetically.

The general shape: **a lossy step in the middle of a pipeline is invisible while every
consumer happens to want the lossy version.** It becomes expensive at exactly the moment
someone needs the original — and by then the loss is baked into everything already ingested.

## The fix

Carry the third component through unchanged, and preserve arity rather than normalising to 3:

```python
if len(point) > 2:
    return [result.x, result.y, float(point[2])]
return [result.x, result.y]
```

**Arity preservation is not incidental.** `bbox`, the hatch boundary loops, and the
ellipse/spline tessellations are genuinely 2D values built by `_as_xy`. Padding them with a
fabricated `z=0` would invent an elevation the source file never stated — the same class of
error as the fabricated volume/surface-area figures removed from `three_d_pipeline.py`.

Fixed alongside it: `map_polyline` hardcoded `0.0` for LWPOLYLINE. An LWPOLYLINE is planar,
but its plane is not necessarily `z=0` — the entity stores its height once, in
`dxf.elevation`, instead of repeating it per vertex.

## Why no cache bump

CLAUDE.md constraint 2 requires bumping `COMPARISON_CACHE_VERSION` when spatial matching or
zone extraction changes. Neither did, and that was **measured rather than assumed**:

- All 11 corpus DXFs were re-parsed under both the old and new code, and the full parser
  output — entities, properties, layers, counts, metadata, viewport indices and scales — was
  serialised with every coordinate truncated to `[x, y]`. The two dumps are **byte-identical**
  (4.9 MB, sha256 `1399e0c8…`). The run exercises the projection on all 6 viewport drawings.
- `tools/eval.py --method rag --provenance mutation` produced identical results either way.
  Note this run does **not** exercise the projection at all — the eval corpus reads frozen
  `entities.jsonl` payloads rather than re-parsing DXFs — so it validates the comparison
  engine, not the fix. The byte-identical parser dump is the evidence that matters here.

Anything that changes what a *2D* consumer sees still needs the bump. This did not.

## The transferable lesson

When a transform legitimately ignores a dimension, make it **pass through**, not disappear.
"We don't use Z here" and "Z does not survive here" look identical at the call site and are
completely different facts about the data. The first is a property of one function; the second
is permanent data loss applied to every document the system has ever ingested.

## See also

- [[Gotcha - Dropped ELLIPSE & SPLINE Geometry]] — the same silent-loss pattern one stage
  earlier, in `map_any` rather than in the projection. Note that **`map_any` still drops every
  true-3D entity type** (`3DFACE`, `MESH`, `3DSOLID`, polyface/polymesh `POLYLINE`); the
  `three_d.unmapped_types` metadata field now counts them so the loss is reported instead of
  silent.
- [[Gotcha - Reference and Revision in Different Coordinate Spaces]] — the other way this
  transform bites
- [[Gotcha - Comparison Cache Invalidation]] — the bump rule this change was measured against
