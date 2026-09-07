---
title: Gotcha - The Dimension Text Was Anchored to the Line It Had to Avoid
type: gotcha
tags: [gotcha, rendering, dimensions, extraction, entity-mapper, canvas]
status: resolved
date: 2026-08-14
cache-version: n/a — **no `COMPARISON_CACHE_VERSION` bump.** `text_point` is untouched, so entity
  pooling and spatial scoping are byte-identical; the new anchor is a second field the renderer
  reads and the comparison never does. `EXTRACTION_SCHEMA_VERSION` 2 → **3**, because this *is* an
  extraction-time field and stale rows need to be identifiable.
related: [ADR-011 Vector as the Only Render Path, Gotcha - A Blurry CAD Canvas and Its Four Causes]
---

# Gotcha — the dimension text was anchored to the line it had to avoid

**Class:** right point, wrong point · **Found:** 2026-08-14, by holding the canvas beside iCAD SX

---

## Symptom

Every measurement was drawn straight through its own dimension line. `⌀145` and `⌀100` sat on
their vertical dimension lines instead of beside them, so each line looked **broken** where the
glyphs crossed it — reported, reasonably, as "the dimension lines are being cut".

Nothing was cut. The line is one continuous path; the text was on top of it.

## Cause

A DIMENSION carries two different points that both sound like the text position:

- **`text_midpoint`**, an attribute of the DIMENSION entity. It is the midpoint of the *dimension
  line*. `map_dimension` read this into `geometry.text_point`.
- **the `insert` of the MTEXT inside the dimension's anonymous geometry block** — where the CAD
  actually placed the string, offset perpendicular to the line by roughly
  `text_height/2 + DIMGAP` so the value reads beside it.

`_dimension_render_geometry` already walked that block and harvested the MTEXT's **height,
rotation, colour, width factor, tracking and text** — everything except *where it goes*.

Measured on M745221N01's revision, model units:

| dimension | dimension line | block MTEXT insert | offset |
|---|---|---|---|
| `⌀145` | x = −105.70 | x = **−110.02** | 4.32 |
| `⌀100` | x = −93.80 | x = **−98.06** | 4.26 |
| `6` | y = −439.05 | y = **−434.79** | 4.26 |
| `⌀125` | angled leader | perpendicular | 4.25 |

Uniformly ~4.3, always perpendicular to the text direction — which is exactly the offset that
anchoring on `text_midpoint` throws away.

## Why it survived

**Because the two points coincide on every dimension this project can generate.** ezdxf's renderer
*writes* `text_midpoint` to wherever it placed the text, so on a document ezdxf authored the
attribute and the block MTEXT are the same point. Only a CAD that offsets them — iCAD SX — makes
the difference observable, and no fixture in the suite came from iCAD.

That is also why the regression test moves the block's MTEXT by hand instead of trusting a
generated dimension to reproduce the offset: *a fixture built with the same library that renders
it cannot expose a disagreement between two of its own fields.*

The symptom pointed the wrong way too. "The line is broken" reads as a path defect —
`render_paths`, arrowhead gaps, dash patterns — and `render_paths` was in fact perfect: one
continuous segment from arrow base to arrow base. The break was ink drawn over it.

## The rule

**When an entity records a position *and* embeds a rendering of itself, they are two different
sources and the embedded one is what the CAD drew.** The DIMENSION's own attributes are anchors
for *reasoning* about the dimension; its geometry block is the *drawing*. This project had already
learned the same lesson twice on the same entity — the `⌀` prefix and the `\W`/`\T` scaling both
live only in the block — and still read the position from the attribute.

## Resolution

`_dimension_render_geometry` now harvests the MTEXT `insert` as `render_text_point`;
`map_dimension` moves it into **geometry** (not properties) and it joins the dimension schema's
`points` tuple, so the model→paper projection reaches it for free. In projected paper units the
anchor moves 3.04–3.09 — for `⌀145`, from 229.20 (the line) to 226.11 — leaving a ~1.1-unit gap
between the glyph band and the line.

`renderEntities` prefers `geo.render_text_point`, falling back to `text_point`.

**Two things deliberately left alone**, both for the same reason the `render_text` split exists:

1. **`text_point` still reads `text_midpoint`.** The comparison scopes entities by their points,
   so repointing it would shift dimensions between zones and stale every cached audit. Adding a
   field for the renderer costs nothing; moving the existing one costs a
   `COMPARISON_CACHE_VERSION` bump and a re-audit of the corpus.
2. **The offset is harvested, not recomputed.** `text_height/2 + DIMGAP` reproduces it to about a
   tenth of a unit (4.32 / 4.26 / 4.25 on one sheet, so DIMGAP is not quite constant), the side
   depends on the text direction, and a radial dimension with a leader places its text by a
   different rule again. The authored point is exact and already in the file.

⚠ **This is an extraction-time field, so it does not reach drawings already ingested** — they keep
the old anchor via the fallback and still draw through the line until re-extracted.
`EXTRACTION_SCHEMA_VERSION` goes 2 → 3 so those rows are identifiable.

That gap is now closable: `POST /drawings/{id}/reextract` landed the same day, precisely because
this was the second fix in one session blocked on it. See
[[Gotcha - The Extraction Pipeline Had Never Been Run Twice]].
