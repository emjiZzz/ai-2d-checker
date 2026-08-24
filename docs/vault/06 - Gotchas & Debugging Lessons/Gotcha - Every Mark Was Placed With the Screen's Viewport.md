---
tags: [gotcha, frontend, canvas, coordinates, export, markings]
status: fixed
cache-version: n/a — rendering only, nothing is cached on this path
date: 2026-08-24
---

# Gotcha — Every Mark Was Placed With the Screen's Viewport

> The exported compliance report showed the drawing correctly and every checkmark, dot and
> annotation pin bunched into the top-left corner of the sheet, over nothing. Reported as "fix the
> checkmarks". The marks were not wrong about *which* entity they belonged to — they were drawn
> with a transform that had nothing to do with the page.

## Symptom

On screen: perfect, at every zoom, for as long as the feature has existed. In the PDF: the whole
set of marks occupying roughly the top-left 20% × 20% of the page, in a loose grid, a few of them
landing on the title block by coincidence because the title block is also top-left.

That 20% is the tell. The app's canvas panel is about 700 × 500 CSS pixels; the export capture is
3492 × 2448. `700 / 3492 ≈ 20%`. The marks were being drawn at the pixel positions they occupied
**in the app's panel**, painted onto a page-sized canvas.

## Root cause: two transforms, one used everywhere it shouldn't be

`coordinateTransform.ts` had one world→pixel conversion for this purpose:

```ts
worldToScreen(wx, wy, norm, viewport)   // derives its transform from the live pan and zoom
```

Every placement in the render path used it — `renderViolationReticles` (engine findings *and*
manual markings, which share that renderer), `renderAnnotationPins`, and the pending-pair ring in
`renderManualMarkings`.

Meanwhile `CanvasRenderer.renderContent` paints geometry through the frame's own transform, set on
the context:

```ts
ctx.translate(transX, transY);
ctx.scale(scale, scale);
```

**On screen the two are the same arithmetic.** `scale === viewport.scale * normScale` and
`transX === viewport.x - xmin * scale`, so `worldToScreen` reduces exactly to
`wx * scale + transX`. That identity is why this survived every review and every test.

**On export they are unrelated.** The export branch *replaces* `scale`/`transX`/`transY` with a
fit-to-page transform and leaves `viewport` untouched — it is the user's pan and zoom, and the
export has no business with it. Geometry followed the page; marks followed the panel.

## The fix

A second named conversion, `worldToCanvas(wx, wy, norm, { scale, transX, transY })`, and the rule
that **inside a render pass you use the frame's transform; `worldToScreen` is for the pointer.**

It is provably the same maths the geometry uses. `renderEntities` places a TEXT entity as:

```ts
const screenX = tx * scale + transX;
const screenY = flipY(tyRaw) * scale + transY;
```

which is `worldToCanvas` written out. A mark and the entity it marks can no longer disagree.

## Three more viewport reads on the same path, all wrong on export

Found by grepping for `viewport` in the render modules once the first one was understood. None of
them would have been noticed from the screenshot, and two are worse than mis-placement:

1. **`if (viewport.scale < 0.1) return;`** — a level-of-detail cull. On export it read the zoom the
   user happened to leave the app at, so a checker who had zoomed out past 0.1 exported a report
   with **no marks on it at all**. A clean-looking sheet, not a broken one. Now
   `currentViewportScale`, which is `scale / normScale` — the pass's *own* zoom, identical on
   screen and correct on export. Same for the `< 0.3` card cull.

2. **`markerPositionsRef.current[v.id] = { x, y }`** — the hit targets the pointer is tested
   against, written unconditionally. An export wrote page coordinates into them, so **exporting a
   report silently moved every clickable marker** until the next repaint. Now guarded on
   `!isExport`.

3. **`MARKER_DOT_PX * resolutionMultiplier * viewport.scale`** — two window-dependencies in one
   expression, and the second is the subject of the section below. The dot is now
   `MARKER_DOT_PX * currentViewportScale`: unchanged on screen, and a property of the page on
   export.

## `resolutionMultiplier` was the window, and it set every line weight on the page

The same defect one level up, and it reached further than the marks.

```ts
const resolutionMultiplier = renderWidth / width;   // `width` = the canvas pane's CSS width
```

It converts the renderer's design-pixel sizes into pass pixels. On screen `renderWidth` defaults to
`width`, so it is 1 and everything is a CSS pixel — correct. On export it is `3492 / <pane width>`,
so **the printed weight of every stroke, checkmark, card and pin was a function of how wide
flexlayout happened to make the pane**. The same audit exported from a maximised window and a
narrow one came out with different line weights.

It is not a marker-only concern: `ctx.lineWidth = (max(hairlinePx, widthPx) / scale) *
resolutionMultiplier` is how every entity on the sheet is stroked, and `$LWDISPLAY` is 0 on these
drawings — so `widthPx` is 0 and **every line is the hairline**, i.e. this constant alone sets the
weight of the whole drawing.

Now `resolutionMultiplierFor(isExport, renderWidth, cssWidth)`, whose export denominator is the
constant `EXPORT_REFERENCE_WIDTH_PX = 700` — the width this layout typically gives a canvas pane on
a 1920-wide display, chosen so an ordinary export is unchanged and an unusual one now matches it.
The value that actually matters is downstream and is asserted in millimetres: at the report's A4
capture it puts a hairline at **~0.42 mm** on paper.

⚠ The display's `devicePixelRatio` does **not** leak in alongside it. `hairlinePx` is a literal
`1.0` on export rather than `1 / dpr`, and `deviceWidthFor` — which does multiply by `dpr` — feeds
only the pixel-snapping phase, and snapping is disabled on export. Worth stating because the
absence is load-bearing and invisible.

## The test fixture was asserting the bug

`renderManualMarkings.test.ts` built its frame with `scale: 0.8, transX: 12, transY: 7` — three
arbitrary numbers next to a `VIEWPORT` they had nothing to do with — and then asserted every
coordinate against `worldToScreen(..., VIEWPORT)`. The fixture was quietly pinning that the
renderer **ignored the frame it was handed**. It did, and that was the defect.

The main fixture now *derives* its transform from its viewport exactly as `CanvasRenderer` does, so
those tests pin the equivalence the fix depends on. The cross-sheet-match fixtures keep an
arbitrary transform deliberately — those tests are about zone-confined matching, and a transform
the viewport cannot reproduce is what proves the code reads the frame.

`markerPlacement.test.ts` is new and written in pairs: a screen frame pinning the equivalence, and
an export frame pinning the divergence, with an explicit
`expect(drawn.x).not.toBeCloseTo(viaViewport.x)` so the test cannot pass against the bug it exists
to catch.

## Lessons

1. **Two conversions that agree in the common case are one bug waiting for an uncommon one.** The
   identity held for every pixel on screen, at every zoom, for the life of the feature. It broke
   the first time something rendered at a size that was not the screen's.
2. **Grep the whole path once you understand the first instance.** Placement was the reported
   symptom; the LOD cull (silently empty reports), the hit-target write (silently broken clicks)
   and a line weight set by the window size were all on the same three lines of reasoning, and
   none of them was visible in the screenshot that started this.
3. **An arbitrary constant in a fixture is an assertion.** `scale: 0.8` next to an unrelated
   viewport said "the frame does not matter here", which was exactly the claim under test.

## Related

- [[Gotcha - The Report's Drawing Pages Were Blank Because the PDF Was 112 MB]] — the rest of this
  report's story, including why `render_bounds` is not the drawing's extent.
- [[Gotcha - The Click Was Never Where the Entity Was]] — the same class one layer down: a
  coordinate that resolved confidently to the wrong thing, with no error anywhere.
- [[Gotcha - A Missing Y Flip Is Invisible Near the Centreline]] — why an error proportional to
  distance from the centre is the hardest kind to see.
