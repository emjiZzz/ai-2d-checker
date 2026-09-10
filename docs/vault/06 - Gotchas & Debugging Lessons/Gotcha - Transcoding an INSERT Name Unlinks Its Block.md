---
tags: [gotcha, rendering, encoding, dxf, render-bounds, comparison]
related: [Gotcha - The Two Sides of a Comparison Come From Different Exporters, Gotcha - A Blurry CAD Canvas and Its Four Causes, Gotcha - iCAD .icd Converts Silently Empty, Gotcha - Comparison Cache Invalidation]
date: 2026-09-10
---

# Gotcha - Transcoding an INSERT Name Unlinks Its Block

## What happened

Reported as two symptoms in one screenshot: comparing a `.dwg` against a `.icd` of the same
part, the two panes did not line up, and the data pairing was 0%.

One cause. `load_and_transcode` reads a DXF as latin-1 to preserve raw bytes, then re-decodes
each string as cp932 to recover Shift-JIS. It applied that recovery to `INSERT.dxf.name` as
well:

```python
elif dxftype == "INSERT":
    entity.dxf.name = transcode_str(entity.dxf.name)
```

`dxf.name` is a pointer into the block table, not text. The reference was rewritten to the
decoded name and the BLOCK record was not renamed, so any block whose name carried CJK bytes
lost its referent. On `M745228N01R1A.dwg` one block of 102 did: `1A1ﾌﾞﾋﾝ`, one of six distinct
INSERT names in the layouts. `Frontend.draw_layout` raised
`DXFStructureError: Required block definition for "1A1ﾌﾞﾋﾝ" does not exist` and the whole
render died on it.

## Why it produced a wrong number instead of an error

`render_dxf_background` catches that exception and computes fallback bounds from the extracted
entities. The fallback read one geometry key:

```python
if "geometry" in e and "points" in e["geometry"]:
```

On this drawing 59 entities have `geometry["points"]`, all polylines, out of 1,231. The other
1,172 -- every text, line, circle and insert -- were invisible to it. The stored `render_bounds`
was therefore the bounding box of 59 polylines, and nothing downstream could tell:

| | `render_bounds` | size | aspect |
| :--- | :--- | :--- | :--- |
| DWG, fallback | `[-260.2, -5.2, 292.5, 155.9]` | 552.7 x 161.1 | 3.430 |
| DWG, rendered | `[-28.5, -21.7, 313.6, 220.0]` | 342.2 x 241.7 | 1.416 |
| ICD, rendered | `[-42.1, -29.7, 883.0, 623.7]` | 925.1 x 653.4 | 1.416 |

Both sides of the pair are sheets of the same aspect. The fallback claimed one of them was
three and a half times wider than tall.

`SpatialDiffer._to_match_space` normalises each side against its own `render_bounds` before
pairing, so a wrong frame on one side moves every entity on that side. Over the 62 strings the
two files share verbatim, measured as separation on the unit square:

| DWG bounds | median separation | within 0.02 | within 0.05 |
| :--- | :--- | :--- | :--- |
| fallback | 0.1501 | 0 / 62 | 0 / 62 |
| rendered | 0.0025 | 53 / 62 | 56 / 62 |

The canvas normalises to the same bounds, so the misalignment the owner saw and the 0% pairing
are the same defect seen twice.

## The fix

`INSERT` is no longer transcoded. Every consumer of `load_and_transcode` renders -- the
background renderer, the vector PDF exporter, `tools/render_audit.py`, `tools/text_layer_audit.py`
-- and none displays a block name, so recovering it bought nothing and could only unlink.
Renaming the BLOCK record to match was the alternative and was rejected: `rename_block` does not
update references, nested INSERTs inside blocks were never renamed by this loop anyway, and the
whole exercise is invisible in the output.

The fallback now reads every key a coordinate can arrive under. It is still not the same
measurement as the success path -- that one is matplotlib's autoscale over a paper-space layout,
where viewport-projected model geometry lands in paper coordinates, while this is the raw extent
of entities in their own spaces. A drawing carrying `render_aspect` is one to re-extract, not one
that is merely 10% loose.

## How to spot it

`render_aspect` is written only by the fallback branch; the success path never sets it. Three of
43 stored drawings had it, all DWG.

Guarded by `tests/test_render_transcoding.py`, which pins that every INSERT still resolves to a
block definition and that the layout actually draws. The fixture has to set `doc.encoding =
"cp932"`: with ezdxf's default cp1252 the recovery pass decodes these bytes successfully into
garbage and never reaches UTF-8, so a fixture that leaves the codepage alone exercises a
different path and passes against the bug.

## The reasoning error worth keeping

The first hypothesis was that `render_bounds` was distorted by `set_aspect('equal', 'box')` on an
axes pinned to a fixed 24x18 figure -- plausible, consistent with an aspect that was too wide, and
wrong. What settled it was noticing that the fallback writes a field the success path does not,
which turned "which of these two code paths ran" into a database query rather than an argument.
Prefer the fingerprint over the mechanism.
