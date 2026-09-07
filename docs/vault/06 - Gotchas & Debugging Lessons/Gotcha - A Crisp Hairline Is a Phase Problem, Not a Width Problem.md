---
title: Gotcha - A Crisp Hairline Is a Phase Problem, Not a Width Problem
type: gotcha
tags: [gotcha, rendering, canvas, vector, hairline, antialiasing, dpr, frontend]
date: 2026-08-11
related: [ADR-011 Vector as the Only Render Path, Gotcha - A Blurry CAD Canvas and Its Four Causes, CanvasRenderer & Entity Drawing]
---

# A crisp hairline is a phase problem, not a width problem

Reported as: *"our canvas has thicker lines of just 0.5px than iCAD SX."*

The report was accurate and the diagnosis it implies is wrong. The lines were **not thicker**. The
width was already exactly right and had been all along.

## The measurement that settles it

`lineWidth` is set to `(1/dpr) / scale`, and the context carries `dpr × scale`, so the painted
width multiplies out to **exactly 1.0000 device pixels**. Confirmed in Chrome, sweeping the
sub-pixel phase of a single hairline and reading the alpha profile back with `getImageData`:

| translate phase | lit columns | alpha profile | total ink |
|---|---|---|---|
| +0.0 | **2** | 0.498 / 0.502 | 1.000 |
| +0.125 | 2 | 0.373 / 0.627 | 1.000 |
| +0.25 | 2 | 0.247 / 0.753 | 1.000 |
| +0.375 | 2 | 0.122 / 0.878 | 1.000 |
| **+0.5** | **1** | **1.000** | 1.000 |
| +0.625 | 2 | 0.875 / 0.125 | 1.000 |
| +0.75 | 2 | 0.749 / 0.251 | 1.000 |

**Total ink is conserved at exactly 1.0 at every phase.** The stroke is not gaining width — it is
being *spread*. A stroke of width `w` fills whole pixels only when its centreline sits at a
half-integer device coordinate for odd `w`, or an integer for even `w`. Everywhere else the
browser splits it across two columns.

Against a viewer that snaps its hairlines — iCAD SX does — a 50/50 split reads as a two-pixel grey
smear next to a one-pixel hard line. *That* is the reported half pixel, and it is half a pixel per
side, which is why the number felt oddly precise.

Nothing in the chain was snapping: `transX = viewport.x - normXMin * effectiveScale` is an
arbitrary pan float, so every axis-aligned rule on the sheet landed at a random phase.

## Why the count-and-width instruments were all silent

This is the same failure mode as the `textBaseline` blind spot in
[[Gotcha - A Blurry CAD Canvas and Its Four Causes]], one level further down:

- the **census** (`497/518`) was correct — nothing was missing
- the **placement oracle** (`|dx|` max 1.27) was correct — every entity was in the right place
- the **width** was correct — exactly 1.0 device px, provably

Every instrument measured a real property, every one passed, and the screen was still visibly
wrong, because **none of them modelled what the rasteriser does with a correct coordinate and a
correct width.** An instrument that stops at the renderer's input reports zero error for the whole
class of defects that live in the rasterisation.

## The fix, and its two edge cases

Snap the constant axis of axis-aligned geometry to the device grid, inverting the transform:

```ts
const device  = dpr * (translate + viewScale * world);
const snapped = Math.round(device - phase) + phase;   // phase 0.5 for odd widths, 0 for even
return ((snapped / dpr) - translate) / viewScale;
```

On this corpus that covers **194 of 249 straight segments (78%)** on `M745221N01_FSRS2_KMTI` and
**140 of 184 (76%)** on the reference sheet — the frame, title block, tolerance table and grid
rules, which is precisely where long thin parallel runs make a soft edge obvious.

Two things that will bite anyone extending it:

1. **A mixed polyline must be left alone entirely.** Snapping one segment of a chain that also
   contains a diagonal detaches it from its neighbour and opens a visible kink. Only chains where
   *every* segment is axis-aligned qualify — and for those, snapping both axes of every vertex
   keeps the chain closed, so rectangles stay rectangles.
2. **Phase depends on width parity.** Odd widths want half-integers, even widths want integers.
   `$LWDISPLAY` is 0 across this corpus so everything is the 1px hairline, but the lineweight
   display widths (0.94 / 1.89 / 3.78 px) round to 1 / 2 / 4 and take different phases.

Diagonals and curves are deliberately untouched — no phase makes a diagonal crisp. Export is
skipped too: it renders at 7016px with its own transform and no dpr, where half a pixel is
meaningless.

> [!NOTE] Verified end-to-end, not just in unit tests
> A horizontal hairline drawn through the real `renderEntities` in a browser lit **exactly 1 row
> at alpha 1.000 at all 8 phases tested** (0 → 0.9), while a diagonal control stayed at 2 rows /
> 0.373 / 0.627. `render_audit.py` is unchanged at 497/518 with `|dx|` max 1.4017 — as expected,
> since it measures payload placement and never touches the canvas rasteriser.

## Lessons

1. **"Thicker" and "spread over more pixels" look identical and have opposite fixes.** Increasing
   or decreasing `lineWidth` here would have made it worse in both directions. Measure the alpha
   profile before touching the width — conserved total ink is the tell that width is not the
   problem.
2. **Geometry, width and *phase* are three independent properties, and this project had
   instruments for only the first two.** The census answers "is it there", the oracle answers "is
   it in the right place", and neither answers "does it land on the pixel grid".
3. **A user reporting a suspiciously precise number is usually reporting a real quantity.** "About
   0.5px thicker" was not a vague impression; it was half the ink sitting in the neighbouring
   column, and taking the number literally led straight to the cause.

## Related

- [[ADR-011 Vector as the Only Render Path]] — the decision that made this visible at all; with
  the raster gone, the vectors are what you are looking at.
- [[Gotcha - A Blurry CAD Canvas and Its Four Causes]] — the four earlier causes, including the
  `1/dpr`-not-1.5-CSS-px floor this builds directly on, and the `textBaseline` blind spot this
  note rhymes with.
- [[CanvasRenderer & Entity Drawing]] — the renderer this lives in.
