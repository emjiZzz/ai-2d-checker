---
title: Gotcha - The Leader Stopped Short of Its Own Label
type: gotcha
tags: [gotcha, rendering, leaders, extraction, entity-mapper, ezdxf, dxf-defaults]
status: resolved
date: 2026-08-14
cache-version: n/a for `COMPARISON_CACHE_VERSION` — LEADER is not in `COMPARABLE_ENTITY_TYPES`
  (`("text", "dimension")`), so nothing about the comparison changes.
  `EXTRACTION_SCHEMA_VERSION` 3 → **4**: this is an extraction-time field and stale rows draw a
  pointer that never arrives.
related: [Gotcha - The Dimension Text Was Anchored to the Line It Had to Avoid, Gotcha - A Blurry CAD Canvas and Its Four Causes, Gotcha - The Extraction Pipeline Had Never Been Run Twice]
---

# Gotcha — the leader stopped short of its own label

**Class:** the geometry is not all in the geometry · **Found:** 2026-08-14, reported as "the line
is too short"

---

## Symptom

The `6-9キリ` hole callout's pointer ran from the hole and **stopped in mid-air**, well short of
the text it belongs to. The label floated with a line ending near it but not reaching it.

## Cause

A DXF `LEADER` does not store its landing. It stores the vertex path plus two attributes:

```
handle=104  vertices = (-65.63,-3.23), (-78.78,-21.14), (-82.98,-21.14)
            has_hookline = 1
            text_width   = 22.620745
```

The **hookline** is the horizontal landing that runs under the annotation text, and the renderer
is expected to synthesise it by extending the final segment by `text_width`. We drew the three
stored vertices and nothing else.

Measured against ezdxf's own rendering of the same leader, in projected paper units:

| | xmin |
|---|---|
| ours | 125.0 |
| ezdxf | **107.9** |

**17.1 units short** — the entire landing. `text_width` is 22.62 model units, 16.16 projected, so
extending by it lands at 108.9: within **1.0** of ezdxf. That residual is the dimstyle gap ezdxf
also adds, and is left on the table deliberately — reading DIMGAP to chase one unit costs more
than it buys, and being 1 unit short of the text is not the defect; being 17 short is.

## The trap that bit on the way in

The first fix read the two attributes directly and **lengthened every plain leader by 1.0 unit**.

`ezdxf` returns the **DXF-spec default** for an unset optional attribute. On a LEADER that
declares neither, `has_hookline` reads back as `1` and `text_width` as `1` — both truthy, neither
written by the CAD. This file's two section-callout tails carry no hookline and were extended by
exactly one unit before the guard went in.

So `entity_mapper` now has two readers, and the distinction is the whole point:

- `_dxf_get(dxf, name, default)` — **what is the effective value.** Already existed, and its own
  docstring warned about this exact behaviour.
- `_dxf_is_set(dxf, name)` — **did the file actually say this.** New, and required by anything
  that branches on presence rather than value.

**Rule: an attribute you can read is not an attribute the file contains.** Same family as the
documented `map_text` MTEXT trap, where reading the TEXT-shaped attribute off an MTEXT yields a
wrong-but-plausible default instead of an error. A default that is *falsy* hides this class of bug
by accident; `has_hookline`'s default is truthy, so it applies itself.

## What was NOT wrong, and how that was established

`⌀125` was reported in the same breath and is **faithful**. Its dimension block contains a single
LINE, and our `render_paths` reproduce it exactly — bounding boxes agree at (148.1, 169.1) with
ezdxf's extra 1.4 on `xmax` accounted for entirely by text ink, which `render_paths` does not
contain by design.

Also checked and clean, before the leader was found: dimension path geometry matches ezdxf to
within 0.2 units across all four dimensions; the ⌀145 dimension line is one continuous segment
with no gap; every dimension and leader is `Continuous` with no dash pattern; and the renderer
does call `closePath()` on `is_closed` chains.

*The useful part of that list is that it is a list of negatives.* Four hypotheses were measured
and rejected before the real one surfaced, and the reject that mattered was "the dimension line is
being drawn dashed" — plausible, cheap to believe, and disproved in one query.

## Second pass — `text_width` is not the text's width

The first fix extended by the leader's own `text_width` and **was still visibly short**, which is
how the next layer surfaced: on the revision the leader declares `text_width = 22.62` while the
MTEXT it points from is **28.56** wide. 5.94 units, enough that the landing ends *inside* its own
label rather than spanning it.

The leader also carries **`annotation_handle`** — a hard reference to that very MTEXT — so the
real width is one `entitydb` lookup away. `text_width` is now only the fallback for a leader that
names no annotation.

**This deliberately overshoots ezdxf**, which uses `text_width` and lands 4.2 units short. The
evidence for the longer landing is the *reference sheet of the same pair*: it has no hookline at
all and instead authors its landing as an explicit `LINE`, **27.9 units against a 29.0-wide
text** — so the CAD's own landing spans its annotation, and matching ezdxf here would mean
matching a renderer rather than the drawing. After the change the revision reads 125.0 → **104.6**
against a text spanning 103.6 → 124.0, the same relationship the reference has natively.

*The generalisable part: when two sources disagree about a value, the one that names the thing
(`annotation_handle`) beats the one that describes it (`text_width`).* And when a fix is measured
against a renderer rather than the source, "matches ezdxf" can be the wrong success criterion —
here the second sheet of the same pair was the better oracle.

## Third pass — the arrowhead was never drawn at all

With the landing right, the callout **still looked wrong**, and this is the one that should have
been found first. Comparing ezdxf's recorded primitives per handle instead of its bounding box:

```
handle 1A5, ezdxf records 3 primitives:
  (221.13,224.40)-(231.00,242.19)   the leader path      <- the only one we drew
  (228.33,238.44)-(231.00,242.19)   arrowhead
  (230.51,241.32)-(231.00,242.19)   arrowhead
```

**A LEADER carries no arrowhead geometry.** The size lives on the DIMSTYLE it names, as `DIMASZ`,
and nothing in the pipeline had ever read it — so every leader on every sheet ended in a bare line
at the feature it points to.

*The bounding box hid this for two rounds.* An arrowhead sits at the tip, inside the path's own
extent, so `ours == ezdxf` on the box while we drew a third of the ink. **Comparing extents
answers "is anything far away missing", never "is anything missing".**

`arrow_size` is harvested from the dimstyle and joins `SCALED_PROPERTY_KEYS`, so it scales with
the viewport like every other length — 2.5 on the reference's paper-space leader, 1.786 on the
revision's inside a 0.7143 viewport. The canvas draws a filled head at **vertex 0**, because DXF
orders leader vertices *from* the arrow; reading the chain as text-to-feature is the natural
reading and puts the arrow in the middle of the label.

⚠ ezdxf draws this ~1.5× DIMASZ (its recorded tip box solves to a triangle 3.75 long against
DIMASZ 2.5). That multiplier is undocumented, so DIMASZ is used raw rather than fitted to one
renderer: a slightly small arrow is a size difference, no arrow is a missing feature.

## Resolution

`EntityMapper.map_leader` appends the landing vertex when **both** attributes are present,
continuing the final segment's direction — not assuming horizontal, since the last segment can run
at any angle. `has_hookline` and `text_width` are also recorded on the entity so a consumer can
tell a synthesised landing from an authored vertex.

Four tests in `tests/test_render_fidelity.py`, including the spec-default trap as its own case and
a diagonal final segment, because "extend horizontally" passes the real drawing and is wrong.

⚠ Extraction-time, so it does not reach drawings already ingested —
`POST /drawings/{id}/reextract` is the cure, and `EXTRACTION_SCHEMA_VERSION` 4 marks which
drawings need it.
