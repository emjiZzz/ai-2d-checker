---
tags: [gotcha, frontend, canvas, coordinate-transform, y-flip, review-ui, viewports]
status: fixed
cache-version: n/a — desktop overlay only, no engine, zone-extraction or comparison behaviour
date: 2026-08-12
---

# Gotcha — A Missing Y Flip Is Invisible Near the Centreline

> [!WARNING] `renderViewOrigins` drew all three of `M745221N01_FSRS2`'s markers **mirrored
> about the sheet's horizontal centreline**, with their Y arms pointing down. Two of the three
> were 18 and 6 units out and looked right. Only the isometric view gave it away, at **152
> units** — nearly half the sheet.

## What happened

The overlay exists because neither exporter writes a UCS, so iCAD SX's on-screen ORIGIN marker was
never an entity that could be extracted — see
[[Gotcha - The Two Sides of a Comparison Come From Different Exporters]]. It is reconstructed on
the client from `viewport_transform`, one marker per viewport at its `view_target_point` anchor.

> [!NOTE] It shipped as `renderViewOrigins`, and **that reconstruction was itself wrong** — the
> anchor projects to the viewport's *window centre*, not to the view's origin. Same overlay, same
> session, separate defect: [[Gotcha - The View Origin Marker Marked the Middle of the Window]].
> This note is only about the mirror. Fixing the flip put the markers where the code intended;
> that note is about the intent being wrong.

`renderViewOrigins` drew each one at its raw paper Y, and said why:

```js
// Paper Y is CAD-up; the canvas transform already carries the flip, so the "up" arm is
// drawn toward +y here and lands upward on screen.
```

**The canvas transform does not carry the flip.** `CanvasRenderer` sets
`ctx.scale(scale, scale)` — no negative anywhere — and `renderEntities` mirrors *every entity's
own coordinates* at draw time instead, through `flipY(y) = ymax + ymin - y` against
`render_bounds`. World space on this canvas is therefore **Y-down**, and a marker placed at a raw
CAD Y is reflected about the sheet's centreline with its arm inverted. One omission, two visible
defects: wrong position, wrong direction.

## Why two of three looked correct

The error is not a constant. `|y − flipY(y)| = |2y − (ymax + ymin)|` — exactly **twice the
distance from the centreline**. So the defect's visibility is a function of *where on the sheet you
happen to look*:

`render_bounds` y −14.9 … 311.9, so `flipY(y) = 297.0 − y` and the centreline is **148.5**:

| viewport | view | paper Y | drawn at | belongs at | error |
|---|---|---|---|---|---|
| `299` | 正面図 (front) | 157.3 | 157.3 | 139.7 | **18** |
| `2D2` | sectA | 145.6 | 145.6 | 151.4 | **6** |
| `2D5` | isome1 | 224.8 | 224.8 | 72.2 | **152** |

The front and section views sit within a few units of the centreline because that is where a
title-block layout puts the main views. An 18-unit slip on a 327-unit sheet reads as a marker
sitting slightly off the anchor point — indistinguishable from an anchor that is genuinely a few
units off. The isometric view is high on the sheet at y 224.8, so it was drawn **at the bottom
right while the flange it marks is at the top right** — which is how it was reported.

**Rule: a mirror error is smallest exactly where a layout puts most of its content.** Two
plausible-looking instances plus one obvious one is the signature — the same asymmetry-as-a-
fingerprint reasoning as [[Gotcha - One Zone Template Cannot Fit Two Sides]], and the concrete form
of the *"mirrored overlay that looks plausible"* warning in
[[Gotcha - Zone Detection Accuracy & Stability]].

## Why the suite was green

`viewOrigins.test.ts` drove the renderer through a `Proxy` context that counted paint calls:

```js
if (k === 'stroke') return () => { calls.stroke++; };
if (k === 'fill') return () => { calls.fill++; };
if (k === 'strokeRect') return () => { calls.strokeRect++; };
```

Everything else — `moveTo`, `lineTo`, every coordinate — resolved to a noop. It asserted
`stroke: 3, fill: 6, strokeRect: 3`: three markers were painted, and **all three were in the wrong
place with their arms pointing the wrong way.** A counting context can only ever prove that
drawing happened.

Fixed by adding a `recordingCtx` that keeps the arguments, and tests that assert *where*: each
corner lands at `297.0 − paperY`, the isometric corner is in the top half of the sheet, the Y arm
end has a **smaller** y than its corner, and the corner square occupies the same quadrant as the
arms. `flipWorldY` also got direct tests, including that it is its own inverse and that a point
far from the centreline moves much further than a near one.

**Two process notes worth keeping:**

- The new tests were checked for non-vacuity by reverting the fix — 2 of the 3 failed as they
  should. **The third stayed green because the revert was partial**: the fixed `strokeRect` was
  still in place, so the quadrant assertion had nothing to catch. A revert used as a control has
  to be complete, or it silently reports the test as weak when it is fine.
- Ad-hoc verification queried Mongo directly. The collection is **`drawing_documents`**, not
  `drawings`; an empty result from the obvious name is not evidence that a drawing lacks a
  transform.

## The structural fix

`flipY` was hand-rolled inline in `renderEntities`, and the obvious repair was to hand-roll a
second copy — in a codebase whose hard constraints already include *"zone geometry spans two
coordinate spaces with opposite Y directions"*. The mirror now has one definition,
`flipWorldY(wy, norm)` in `apps/desktop/src/utils/coordinateTransform.ts`, alongside
`worldToScreen` (which bakes it in) and the two functions that deliberately skip it. With no
bounds it is a passthrough: nothing to mirror about, and a guessed centreline is worse than an
unmirrored point.

**Which renderers owe the mirror is decided by one observable thing: whether they reset the canvas
transform.** `renderViolationReticles`, `renderAnnotationPins` and `renderZoneEditor` all open with
`ctx.setTransform(dpr, 0, 0, dpr, 0, 0)` and position in screen pixels via `worldToScreen` /
`fractionsToScreenRect`, which flip internally — they were checked and are correct.
`renderViewOrigins` is the **only** overlay in the file that stays in world space, because dividing
its arm lengths by `scale` is how it stays screen-constant while tracking the geometry. It was
written in the world-space family while holding the screen-space family's assumption.

## Measured

- `npx vitest run` — **342 passed across 30 files** (was 333; 4 new placement tests on the markers,
  5 on `flipWorldY`).
- `npx tsc --noEmit` — 0 errors.
- No cache bump: the overlay reads a stored `viewport_transform` and changes nothing any engine
  consumes.

## See also

- [[Gotcha - The Two Sides of a Comparison Come From Different Exporters]] — why this overlay has to
  be reconstructed at all: no UCS on either side, so the marker was never an entity
- [[Gotcha - Zone Detection Accuracy & Stability]] — the two opposite-Y spaces, and the mirrored
  overlay that looks plausible; this is that failure arriving in a second place
- [[Gotcha - A Guard Test's Failure Path Had Never Run]] — same species of dead assurance: a test
  that passes under both the broken and the fixed implementation
- [[Gotcha - A Blurry CAD Canvas and Its Four Causes]] and
  [[Gotcha - A Crisp Hairline Is a Phase Problem, Not a Width Problem]] — measurements that were
  correct, and silent, because they did not model the thing that was wrong
- [[Gotcha - The Views Overlay Showed a Region That Is Not Compared]] — the other overlay defect
  that presented as an engine bug
