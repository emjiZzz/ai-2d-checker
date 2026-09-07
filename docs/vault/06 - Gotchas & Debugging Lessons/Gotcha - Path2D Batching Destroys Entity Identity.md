---
title: Gotcha - Path2D Batching Destroys Entity Identity
type: gotcha
tags: [gotcha, canvas, rendering, picking, ground-truth, coordinate-space]
status: active
date: 2026-08-18
cache-version: n/a (render path only; gated behind manual-check mode, no comparison involvement)
related: [Gotcha - A Missing Y Flip Is Invisible Near the Centreline, Gotcha - Zone Detection Accuracy & Stability, Gotcha - A Marking Cannot Store an Entity Id, ADR-011 Vector as the Only Render Path]
---

# Gotcha — `Path2D` batching destroys entity identity, so picking cannot be added afterwards

**Class:** an architectural property that looks like a missing feature · **Found:** 2026-08-18,
while planning canvas entity selection

---

## Symptom

"Which CAD entity is under the cursor" appears to be a small addition to a canvas that already
hit-tests violation markers, annotation pins and zone handles. It is not, and the reason is not
effort — it is that **the answer is destroyed before the frame is finished**.

## Cause

`renderEntities.ts` batches geometry by style. Every entity that shares a stroke colour, width,
dash pattern and dash unit-space is appended into **one shared `Path2D`**:

```
const batchKey = `${strokeColor}_${strokeWidth}_${dash}_${dashUnits}`;   // :592
pathBatches[batchKey].path                                               // :654-657
```

flushed with a single `ctx.stroke(batch.path)` at `:926`. Hundreds of entities go into one path
object, and after the loop nothing maps a pixel back to an `ent.id`. `ctx.isPointInStroke` would
answer *"is this pixel inside the cyan-0.25mm-solid batch"*, which is not a question anyone
asked. Text is the exception — drawn individually at `:594-651` — but it records no id either.

This is not a defect. Batching is why a 500-entity sheet renders at interactive speed, and
`renderEntities` returns only `{totalEntities, drawnEntities}` because that is all a renderer
owes anyone.

## Why a separate pass is the wrong fix

The tempting alternative is to compute bounding boxes in a standalone module from the same
`layers` prop, touching no existing file. It fails for the entities that matter most: the
renderer applies MTEXT rotation, attachment-point alignment, width factors, column widths and
section-callout culling, so an independent pass computes hit boxes for where text *would* be
rather than where it *was drawn*. The boxes would be plausible and slightly wrong — and in a
labelling tool a slightly wrong hit box does not look like a bug, it produces a dataset where
some fraction of judgements are filed against the wrong entity.

## Fix

Populate the index **inside the existing loop**, where identity is still in scope — one line,
generalising the pattern already used for violation markers (`markerPositionsRef.current[v.id] =
{x, y}` at `:1024`) for exactly the same reason. It is gated on an optional `frame.entityHitIndex`
that is `undefined` for every existing caller, so with manual-check mode off the loop does one
`if` per entity and the render path is unchanged. Measured: the mutation invariant is
byte-identical before and after.

`entityPicking.ts` owns the index. Bounds are stored in **flipped-world** units so a pan or zoom
does not require a rebuild, and `hitTest` returns the **smallest** box under the cursor — a
dimension's text sits inside its view's polyline, which sits inside the sheet border, so
first-hit or z-order picking hands back the border every time.

## Two traps inside the fix

⚠ **The Y flip is not optional.** Entity geometry is CAD Y-up; the canvas is Y-down.
`entityPicking` takes the renderer's own `flipY` rather than reimplementing it, and the hit test
uses `screenToWorld` — the **flipped** variant. `screenToWorldUnflipped` is for zone fractions
measured against `render_bounds` and using it here mirrors every hit box about the sheet's
centreline: plausible near the middle, 152 units out at the top. See
[[Gotcha - A Missing Y Flip Is Invisible Near the Centreline]], which is the same mistake in the
same coordinate space.

⚠ **A DIMENSION anchors on `def_point`, not `insert`.** `entityWorldBounds` prefers
`render_text_point`, then `text_point`, then `def_point`. Reading `insert` is exactly the open
defect that stops `tools/eval_corpus.py worksheet` placing a dimension at all — and an added
dimension is one of the corpus's four recorded false-negative classes, so a picker that
inherited the assumption would be unable to record the very thing it exists for.

## The lesson

**Before adding interaction to a render path, check whether the render path still knows what it
drew.** An optimisation that is invisible in the output can be load-bearing against a feature
nobody had planned when it was written — and the cost of finding out late is a hit test that is
subtly, silently wrong rather than obviously broken.
