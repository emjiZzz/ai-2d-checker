---
title: Gotcha - A Reshaped Zone Is Not Its Bounding Box
type: gotcha
tags: [gotcha, zones, polygon, coordinate-spaces, y-flip, false-negative-risk, zone-template]
status: resolved
date: 2026-08-05
---

# 🔥 Reshaping a zone: two ways to be silently wrong

A zone box can now be **reshaped**: hovering an edge in the alignment editor shows a `+` ghost,
clicking inserts a node, and the zone becomes a polygon you drag by its vertices. Requested
because a rectangle cannot follow a sheet whose drawing area is notched by a floating table.

The feature is small. The two ways to get it wrong are not, and neither raises.

## Failure 1 — a vertex conversion is NOT the box conversion

Template fractions are **Y-DOWN**; CAD is **Y-up**. The existing *box* conversion flips Y **and
swaps min with max**:

```python
cad_ymin = by1 - yMax * h        cad_ymax = by1 - yMin * h
```

That swap is an artifact of the **names**: "min" and "max" are claims about magnitude, and
reversing an axis reverses which edge earns which name. A **vertex** has no such pair. Its
conversion is the flip alone:

```python
cad_y = by1 - y * h
```

Copy the box rule onto points — or reach for `by0 + y * h` — and the outline comes back
**vertically mirrored**. It is still closed, still the right size, still inside the correct
bounding box, so nothing errors and the overlay looks entirely plausible. It just gates the
comparison on the opposite half of the zone.

This is the same trap [[Gotcha - Reference and Revision in Different Coordinate Spaces]] and
the zone-template work already paid for once, arriving through a new door. Pinned on both sides
by an orientation assertion rather than by inspection:
`zoneShapes.test.ts::puts a top-edge vertex ABOVE a bottom-edge vertex in CAD` and
`test_zone_polygons.py::test_outline_conversion_flips_y_without_swapping_min_and_max`.

## Failure 2 — excluding a reshaped sibling on its bounding box

`views` is the drawing area minus its sibling zones. If a sibling is reshaped and the exclusion
still uses its **bounding box**, then content sitting in the notch the user deliberately cut
out of that sibling is dropped from `views` too — and **no other category picks it up**. It is
reported by nothing.

That is the silent, false-negative direction, in a system whose largest known measurement gap
is that false negatives have never been measured. So `views_exclusions` returns
`(bbox, outline)` pairs and `safe_filter` passes each zone's outline through to `is_in_bbox`.
Pinned by `test_zone_polygons.py::test_a_reshaped_sibling_excludes_only_what_it_covers`.

The overlay has the mirror-image version of the same bug: punching a sibling's *bbox* out of
the views tint would draw content as excluded that the engine still compares — reintroducing
[[Gotcha - The Views Overlay Showed a Region That Is Not Compared]] through a different door.
Pinned by `zonePolygonRender.test.ts`, verified to fail against a bbox punch before being kept.

## Shape of the change

The outline is **additive**, and that is what kept the blast radius small:

| layer | rectangle | reshaped |
| :-- | :-- | :-- |
| `RegionFractions` / `ZoneFractions` | 4 scalars | 4 scalars **+ `points`** |
| the 4 scalars | the zone | the outline's **derived** bounding box |
| `regions[zone_key]` | 4-tuple | **still a 4-tuple** |
| the outline | — | `regions["_zone_polygons"][zone_key]`, absolute CAD |

So the ~29 sites that index `regions` as `(xmin, ymin, xmax, ymax)` — growth caps, overlap
logging, crop bounds, proximity windows — are untouched, and every one of them *wants* the
bounding box anyway. Only the places that gate **content** consult the outline:
`scope_entities_to_views`, `views_exclusions`, and the orchestrator's `is_in_bbox`.

`normalizeFractions` **derives** the scalars from the points on every write, so the bounding
box every non-shape-aware consumer reads can never drift from the outline. A stored template
written before this existed has no `points` and parses as the rectangle it always was — no
migration. The outline is smuggled under a reserved underscore key, the same pattern as
`safe_zones`, `_zone_confidence` and `_anchor_matches`.

### Two rules that are not obvious

**A grown zone loses its outline.** `bom` is a `GROWABLE_PINNED_ZONE`: a template box is a
*floor* that detection may extend, because a BOM aligned on a one-row sheet clips the rows off
a three-row one. If growth fires, the union no longer matches the shape the user drew, so
keeping the outline would gate content on the smaller original while every bbox consumer used
the larger union. The outline is dropped, with a warning, and the zone reverts to its grown
rectangle. Growth is a safety net against dropping content; the reshape is a statement about
one sheet. When they conflict the safety net wins, because dropping content is the worse
failure.

**Fewer than 3 vertices is not a shape.** Two points enclose nothing, so a zone carrying them
would contain no entity at all — a zone that silently compares nothing. Dropped to the
rectangle at the schema, in `normalizeFractions`, and in `removePointAt`, which refuses to
delete the third-to-last node.

### Handles

A rectangle keeps its four corner handles and its rectangular resize, unchanged. Once reshaped,
the handles **are** the vertices — there is no opposite edge to hold, so "resize the box" has
no meaning. Clicking an edge inserts a node *and immediately hands it the drag*, so adding and
placing are one gesture; alt-clicking a node removes it. The edge hit-test uses segment
distance, not distance to the infinite line, or the hint would light up far outside the zone
near a corner; it is checked after the vertex handles and with a tighter radius (8px vs 12px)
so grabbing an existing node always beats minting a new one.

## Measured

Reshaping the reference sheet's `views` zone to its left half, via a real template outline:

| side | pool as a rectangle | pool reshaped |
| :-- | --: | --: |
| reference | 85 | **41** |
| revision | 70 | **22** |

The reshaped pool is asserted to be a **subset** — a reshape can only ever remove.

Eval over 36 pairs: **every metric byte-identical to the v38 baseline**. The feature is inert
until someone reshapes a zone, and nothing reshapes one automatically.

Cache **v41 → v42**: a sheet whose template carries a reshaped zone has a different
`drawing_views` pool than its v41 entry.

## Guarded by

- `tests/test_zone_polygons.py` (14) — geometry, the Y flip, schema degradation, and the
  reshaped-sibling exclusion.
- `apps/desktop/src/utils/zoneShapes.test.ts` (25) — the mirrored-outline assertion, node
  insert/remove/move, derived bounds, and containment.
- `apps/desktop/src/components/review/zonePolygonRender.test.ts` (9) — polygon stroke/fill,
  per-vertex handles, the edge ghost, and the outline-not-bbox tint cut.
