---
title: Gotcha - The Views Overlay Showed a Region That Is Not Compared
type: gotcha
tags: [gotcha, zones, drawing-views, overlay, canvas, false-alarm, ui-truthfulness]
status: resolved
date: 2026-08-05
---

# 🔥 Gotcha — the `views` overlay drew a region the engine had already excluded

Reported from a live review session (2026-08-05): *"the drawing views zone box in the revised
drawing occupies spaces and includes some other views — the system must be smart enough to
exclude other data if it belongs to other zone boxes."*

On screen the cyan `DRAWING VIEWS` rectangle plainly swallowed the `NOTES`, `ISO VIEW`,
`BOM TABLE` and `TITLE (UL)` boxes. The reasonable inference — that notes text was being
compared as drawing geometry — was **wrong**, and the engine was already correct.

## The engine was right; the overlay was not

`scope_entities_to_views` drops any entity whose anchor falls inside a sibling zone
(`VIEWS_EXCLUDED_ZONES` = title, title_upper_left, bom, tolerance, notes, iso, shim). Measured
on the `M7452A0N01` pair — and the exclusion is not a detail, it is most of the work:

| side | anchors inside the `views` rectangle | inside a sibling zone (dropped) | final `drawing_views` pool |
| :-- | --: | --: | --: |
| reference | 508 | **423 (83%)** | 85 |
| revision | 562 | **492 (88%)** | 70 |

Confirmed end to end on the reporter's own cached audit: the three note lines
(`タップ、キリ穴は面取り仕上げのこと`, `指示なき角部は糸面取りのこと`, `完成時、バリ、キリ粉はなきこと`) are
`notes_section` cards, and every `drawing_views` card is a dimension or `２－７キリ`. Nothing
leaked.

## Why the rectangle looks like that

`views` is defined by exclusion — the drawing area, meaning everything that is not sheet
furniture or a floating annotation block. When it is *detected*, that subtraction is baked into
`_derive_views_zone`. When it is **pinned from a template** — the session header read *"Loaded 7
pinned zone(s) from template"* — it is a plain rectangle over the whole drawing area, and the
subtraction is re-applied at the point of use instead. That comment already existed above
`VIEWS_EXCLUDED_ZONES`. The renderer never got the message: it filled the raw rectangle.

So the overlay asserted that notes/BOM/iso were being diffed as geometry. They were not. **A
correct engine plus a misleading overlay is indistinguishable from a scoping bug**, and cost a
review cycle to tell apart.

## Fix

`renderEntities.ts::renderZoneEditor` subtracts the sibling boxes from the `views` **tint**.
The stroke stays the full rectangle — the editor manipulates the real box, and a clipped
outline would make it un-grabbable.

Subtraction is a **chained even-odd clip per sibling**, not one even-odd fill over all of them:

```ts
ctx.beginPath(); ctx.rect(left, top, w, h); ctx.clip();   // to the views rect
for (const s of siblings) {
  const hole = new Path2D();
  hole.rect(0, 0, renderWidth, renderHeight);             // outer
  hole.rect(s.left, s.top, sw, sh);                       // hole
  ctx.clip(hole, 'evenodd');
}
```

Chained clips **intersect**, so two overlapping siblings still cut one hole. A single even-odd
path over all of them would re-fill their intersection — and sibling overlap is real here: the
orchestrator logs `Spatial region overlap detected!` for BOM vs title.

`VIEWS_EXCLUDED_ZONES` is mirrored into `drawingsApi.ts` beside `ZONE_KEYS`, which already
mirrors the backend list, so the two stay adjacent and diverge visibly.

**No cache bump.** No engine behaviour changed — this is a tint. The eval is untouched by it.

## Guarded by

`zoneOverlay.test.ts`, five new tests. The suite had never rendered the `views` zone at all,
which is why the branch was reachable and unpinned:
- `cuts a hole for each sibling that has a box` and `cuts no holes when views is the only zone`
  — **verified to fail against the old renderer** before being kept.
- `leaves the full outline so the box stays draggable and resizable`,
  `does not clip any zone other than views`, `ignores a sibling whose box collapses to zero
  area` — invariants that hold before and after, guarding the new code rather than detecting
  the change.

jsdom ships no canvas, so the test file stubs `Path2D` with a recorder and the mock context
captures each `clip()`'s path geometry.

## Rule

**When a zone's meaning is "this rectangle minus those rectangles", the UI has to draw the
subtraction.** A shape drawn as a plain rectangle is a claim about what is being compared, and
when that claim is false it gets reported as an engine bug. Both halves of a zone — the box the
user drags and the region the engine uses — must be visible, or the reviewer audits the wrong
one.

## Traps

- This changes the tint only. If a genuine scoping bug ever does appear, the overlay will now
  show it correctly rather than hiding it in a uniformly filled rectangle — which is the point,
  but it means the overlay is no longer a constant and can itself be wrong.
- The measurement above comes from the offline eval, where zone templates do not resolve (see
  [[Gotcha - Zone Templates Vanish in Offline Eval]]), so those `views` boxes are the detection
  fallback covering the whole sheet — `(0, 0, 1050, 742.5)` and `(0, 0, 420, 297)`. That makes
  the exclusion percentages an upper bound, not the pinned-template figure. The end-to-end
  card-level check on the live pair is the evidence that stands without that caveat.
