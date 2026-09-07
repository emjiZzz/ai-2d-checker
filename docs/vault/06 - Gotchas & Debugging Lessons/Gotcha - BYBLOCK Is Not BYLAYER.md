---
title: Gotcha - BYBLOCK Is Not BYLAYER
type: gotcha
tags: [gotcha, rendering, color, dxf, byblock, bylayer, blocks, serializer]
date: 2026-08-11
related: [ADR-011 Vector as the Only Render Path, Gotcha - Exploded Block Children Have No Handle, Gotcha - A Blurry CAD Canvas and Its Four Causes]
---

# BYBLOCK is not BYLAYER, and the surface-finish symbol is where that bites

Reported by the user: *"the welding/machining symbol isn't colour red — that thing must be red."*

They were right, and the drawing said so all along.

## The two sentinels are not interchangeable

ACI 256 (**BYLAYER**) and ACI 0 (**BYBLOCK**) are both instructions to look somewhere else, but
they point at *different places*:

| sentinel | resolves against |
| :-- | :-- |
| BYLAYER (256) | the entity's **layer** |
| BYBLOCK (0) | the **INSERT** that placed the entity |

BYBLOCK exists precisely so that one block definition can be drawn in a different colour at each
insertion point. Collapsing it onto the layer throws away the only thing it encodes.

`GeometrySerializer._resolve_index` did exactly that:

```python
if index in (ACI_BYLAYER, ACI_BYBLOCK):
    index = layer_colors.get(layer, 7)
```

and the docstring above it recorded the reasoning as deliberate: *"the parent is recoverable
(`parent_handle`), but exploded children already carry the layer they landed on, so deferring to
the layer is both cheaper and right in the common case where a block's contents are BYLAYER
anyway."*

The common case was right. The uncommon case was the surface-finish symbol.

## The measurement

On `M745221N01_FSRS2_KMTI` there is **exactly one** BYBLOCK entity in the whole drawing:

```
type=polyline  layer=0  parent=2AF  parent_type=block  parent_color=1  layer_color=7
```

ACI 1 is red. So the correct chain is BYBLOCK → INSERT `2AF` → ACI 1 → **red**, and what actually
happened was BYBLOCK → `layer_colors['0']` → ACI 7 → **white**. One entity, one sentinel, and it
was the one the sheet uses to mark machining.

The reference sheet has **zero** BYBLOCK entities, so the symbol appears only on the revision —
which is why this presented as "the revised drawing looks wrong" rather than as a renderer bug.

Not a one-drawing curiosity: `M7452A0N01_FSRS2_kmti` carries **8** BYBLOCK polylines across four
different parent INSERTs, all of which were rendering white.

## Why nothing caught it

Same shape as [[Gotcha - A Crisp Hairline Is a Phase Problem, Not a Width Problem]] — every
instrument was measuring something real and none of them measured this:

- the **census** counts entities, and the polyline was present and drawn
- the **placement oracle** measures text, and this is geometry
- the **colour tests** in `test_phase5_visual_workspace.py` covered BYLAYER, true_color, ACI 250
  near-black lifting, and a BYBLOCK entity **with no layer record** — the orphan fallback, which
  is the one BYBLOCK case the old code got right

A test existed for BYBLOCK. It asserted the fallback and never the inheritance.

## The fix

`_resolve_index` now splits the two sentinels, and BYBLOCK walks `parent_handle` upward through
`_inherited_from_insert`:

- the parent's explicit ACI wins
- a parent that is itself **BYLAYER** resolves against the **parent's** layer, not the child's
- nested BYBLOCK keeps climbing, depth-capped at 8 rather than cycle-tracked, so a malformed file
  cannot hang a render
- no recoverable parent falls back to the layer — the old behaviour, which was correct there

This depends on the parent being findable, and it is:
[[Gotcha - Exploded Block Children Have No Handle]] measured `handle` and `parent_handle` to be
**perfectly mutually exclusive across all 3615 entities** in six drawings, so an exploded child
always carries a parent pointer and the `block` record always carries the handle it points to.
The routes already pass block records to the serializer unfiltered, which is also why
`_build_layer_colors` works.

> [!NOTE] Runtime fix — no re-upload, no cache bump
> `GeometrySerializer` runs per request on `GET /drawings/{id}/layers`, not at extraction. Nothing
> stored changes, and `serialize_entities` is not on the comparison path (only the two routes and
> tests call it), so `COMPARISON_CACHE_VERSION` does not move.

**Verified end-to-end against the live API and stored Mongo data**, not just re-parsed DXF:
`M745221N01_FSRS2_kmti` serves `stroke=#FF0000` for its one BYBLOCK polyline, `M745221N01_reference`
has none and is unchanged, and a sweep asserted **zero** non-BYBLOCK entities changed colour.

## Lessons

1. **A sentinel that "usually" resolves the same way as another sentinel is still a different
   sentinel.** The shortcut was documented, reasoned, and wrong exactly where the two diverge —
   which is the only place the distinction exists at all.
2. **A test for the fallback is not a test for the feature.** The existing BYBLOCK test asserted
   the no-parent path, so it passed under both the broken and the fixed implementation.
3. **A defect on one entity out of 518 is invisible to every aggregate.** Counts, medians and
   percentages all stayed healthy. It took a human looking at the drawing and knowing what colour
   the symbol should be — which is an argument for keeping domain review in the loop, not for
   building a better average.
