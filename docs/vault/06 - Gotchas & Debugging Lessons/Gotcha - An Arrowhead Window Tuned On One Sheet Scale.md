---
title: Gotcha - An Arrowhead Window Tuned On One Sheet Scale
type: gotcha
tags: [gotcha, extraction, dimensions, arrowheads, dxf, entity-mapper, dry]
date: 2026-09-03
related: [Gotcha - A Blurry CAD Canvas and Its Four Causes, ADR-011 Vector as the Only Render Path, CanvasRenderer & Entity Drawing]
---

# An arrowhead window tuned on one sheet scale

Every arrowhead in `storage/uploads` is an `_OPEN30` block: **317 of them across the 12 sheets
sampled, and zero SOLID/TRACE fills.** The block draws a hollow head and records no triangle, so
the vector canvas painted every dimension arrow as two bare barbs where iCAD SX and the printed
sheet both show it solid. Reconstructing the triangle at extraction is the fix.

The interesting part is the heuristic that does it, and the two ways the first attempt was wrong.

## An `_OPEN30` block holds three lines, not two

All three meet at the tip — two barbs and the shaft — so each head offers **three** candidate
pairs, of which one is the head. Measured included angles over the sample: **min 15, median 15,
max 30**. The two barb-shaft pairs sit at exactly half the head's angle, and they outnumber it
2:1. The angle window is therefore the entire discriminator and has to be tight enough to reject
15 while accepting 30 — `cos` in `[0.80, 0.92]`, i.e. 23°–37°. A looser window does not degrade
gracefully; it fills a wedge along the shaft instead of the head.

The same window is why `_OPEN90` — a genuinely open tick — is left alone despite matching the
`OPEN` name gate. **The name selects candidates; the geometry decides.**

## ⛔ An absolute length bound cannot work, and looked like it did

The first version required each barb to measure between **1.0 and 10.0** drawing units. On the
sheet it was written against, it worked. Across the sample it reconstructed **127 of 317 heads and
silently dropped 190** — barbs run **2.5 to 12.4 units** depending on sheet scale, and the sheet
with 111 dimensions produced 10 fills.

There was no error and nothing to see downstream: a dropped head just renders the way it always
had. The only symptom was arrows that were solid on some sheets and hollow on others, which reads
as a drawing difference rather than a bug.

Length is now compared **barb against barb only** (within 25%), which is scale-free, plus a
`1e-9` degeneracy guard so a zero-length segment has a direction to measure. Coverage: **320 of
320, zero misses.** The general form: *a threshold in drawing units is a threshold in sheet
scale.* `arrow_size`/DIMASZ exists precisely because the CAD does not assume one either.

## ⛔ The canvas must not hold a second opinion about this

The same reconstruction was also implemented in `renderEntities.ts`, running per frame, `O(n²)`
over each dimension's `render_paths`, with its own copy of the tolerances — one of which had
already drifted (`0.20` against the backend's `0.25`). It existed because the stored drawings were
**five schema versions stale**, so it was compensating in the renderer for extraction that had
never been re-run.

Deleted. `render_fills` already carries the triangle, the canvas already paints it, and
`EXTRACTION_SCHEMA_VERSION` is the mechanism for "this drawing predates the fix" — see
`tools/reextract_stale_drawings.py`. Bumped **7 → 8**.

Three downstream compensations went with it, each justified in its comment by the same thin
arrowheads and each applying to everything else on the sheet as a side effect: a hairline floor
raised to `max(1.0, 1.25/dpr)` (which doubles every stroke on a high-DPR display — see
[[Gotcha - A Crisp Hairline Is a Phase Problem, Not a Width Problem]]), `lineCap`/`lineJoin` set
to `round` on every stroke batch, and a boundary stroke painted over every fill batch, hatches
included. **When a fix needs three global compensations to look right, the fix is in the wrong
layer.**

## Guarded by

`tests/test_dimension_arrowhead_fills.py` — verifies open arrowheads stay in `render_paths` as wireframe strokes and produce 0 fills.

## Superseded in v9: The Arrowhead is NOT Solid in CAD

Direct comparison with original CAD drawings (e.g. iCAD SX / Part 221) confirmed that the arrowheads on engineering drawings are authored and printed as **open wireframe barbs** (`_OPEN30`), NOT solid fills. The v8 synthetic triangle reconstruction in `entity_mapper.py` and the solid fill in `renderEntities.ts` were retired in `EXTRACTION_SCHEMA_VERSION` **8 → 9**; open arrowheads now render faithfully as stroked wireframe lines matching the CAD drawing.
