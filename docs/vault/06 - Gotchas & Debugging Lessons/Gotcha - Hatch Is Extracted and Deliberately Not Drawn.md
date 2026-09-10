---
tags: [gotcha, rendering, canvas, hatch, icad, scope, negative-result]
related: [ADR-011 Vector as the Only Render Path, Gotcha - iCAD .icd Converts Silently Empty,
  Gotcha - Dropped ELLIPSE & SPLINE Geometry, Gotcha - The Engine Ignored the Section Callout but
  the Canvas Still Drew It]
date: 2026-09-10
---

# Gotcha - Hatch Is Extracted and Deliberately Not Drawn

HATCH is extracted, is addressable, has boundary loops, and the canvas does not draw it. That is
a decision, not a gap. Read this before "fixing" it, because it was found and fixed twice in one
afternoon and both fixes were thrown away.

## What happened

`renderEntities` branches on text, line, circle, arc, dimension, polyline, ellipse, spline,
leader and multileader. There was no hatch branch, so `render_audit` reported hatch under
`no-branch` -- the bucket that means "the renderer forgot".

It looked forgotten because it had never been exercised. The DXF corpus carries no hatch at all,
which is why the census on `0029fc8cdf974f5e92fa7148a679255d.dxf` never needed a hatch bucket.
The first real iCAD drawing brought 106 on one sheet, and section fills that iCAD SX draws as
45-degree ruling rendered as empty outlines.

## Two fixes, both wrong

**A tinted fill.** Non-solid hatch filled at 22% alpha, even-odd so islands stayed holes. Built
on the belief that the pattern definition was unavailable, so real ruling could not be derived
without inventing the spacing. Rejected on sight against iCAD: a flat wash reads as a filled
area, and over an aluminium extrusion profile it buries the internal detail a checker is reading.

**Real ANSI31 ruling.** The premise behind the tint was simply wrong. The DXF carries the
resolved pattern definition per hatch -- angle, base point and offset per line family, 20
distinct definitions across those 106 -- and `ezdxf.render.hatching.hatch_entity()` walks it
against the boundary loops, islands included. Extracted into `geometry.pattern_lines` at
`EXTRACTION_SCHEMA_VERSION` 11 and stroked thin: 1273 segments at 45 and 135 degrees, clipped
correctly, faithful to the sheet.

It worked, and it was still thrown away.

## Why neither shipped

Owner's call, 2026-09-10: *"those hatch are not necessary in our system because our only need was
the data location and the data pairs."*

`COMPARABLE_ENTITY_TYPES` is `("text", "dimension")`. A hatch can never produce a finding. Drawing
it adds ink on top of the geometry the checker reads through, in service of nothing the checker
does. The same reasoning already governs section callouts, which the engine drops and the canvas
therefore refuses to paint:
[[Gotcha - The Engine Ignored the Section Callout but the Canvas Still Drew It]].

Everything was reverted: the renderer branch, the picking change that made hatches selectable,
the `pattern_lines` extraction, and the version bump back to 10. The 106 rows already written
with `pattern_lines` were re-extracted away, because dead payload that nothing reads is how the
next person concludes the feature exists.

## What is guarded

`render_audit.py` reports hatch under `excluded-by-design`, not `no-branch`, via
`DELIBERATELY_UNDRAWN_TYPES`. That distinction is the whole point of this note: `no-branch` means
the renderer forgot and someone should fix it; `excluded-by-design` means someone already
decided. Measured on `17131ML-A4031-0`: `hatch excluded-by-design=106`, and
`0029fc8cdf974f5e92fa7148a679255d.dxf` still reads **490/518** because it carries no hatch.

Nothing enforces the absence itself. A hatch branch added to `renderEntities` would pass every
test in the suite; only the census would move, and only if someone ran it.

## Traps for the next person

- **A missing render branch is not automatically a bug.** Ask what the canvas is *for* before
  asking how to draw the thing correctly. Two working implementations were built before that
  question got asked, which is the actual lesson here.
- **The pattern definition IS in the DXF.** If hatch is ever wanted, do not approximate it and do
  not hardcode ANSI31 -- `ezdxf.render.hatching` resolves the real thing, and the work is
  recoverable from this note's description rather than from scratch.
- **Reverting an `EXTRACTION_SCHEMA_VERSION` bump leaves rows stamped ahead of the code.** Any
  drawing extracted at the higher version reads as current forever, because staleness is
  `stored < current`. Re-extract those drawings as part of the revert; the payload they carry is
  otherwise invisible and permanent.

## Still unmeasured

Whether a checker ever *wants* the ruling. The decision was made on the argument that hatch
produces no findings, not on watching anyone check a sectioned drawing without it. If a section
view turns out to be unreadable when the fill is absent, that is the evidence that would reopen
this, and none was collected either way.

Return to [[00 - Map of Content (MOC)]].
