---
title: Gotcha - A Zone Cap Smaller Than the Table It Caps
type: gotcha
tags: [gotcha, zone-detection, shim-table, safe-zone, caps]
status: resolved
date: 2026-08-12
---

# The cap was smaller than the table, so a row of a SAFE zone got compared

Reported from a live review with a screenshot: **`総厚サ 6mm` marked `Cat: drawing views`** on the
シム表 of `M745227N01` — a table that is identical on both sides and, by
[[Gotcha - Optional Zones and the Shim Table]], **must never be compared at all**.

`shim` is a SAFE zone exactly like `tolerance`: assembly-thickness reference data, detected so
that `views` can subtract it, never diffed as its own category. So a row the box fails to reach
does not land in the wrong zone — it falls through to the `drawing_views` pool and **becomes a
finding**, on a table whose entire point is that it produces none.

## The number that explains it

| | value |
| :--- | :--- |
| drawn シム表, reference | 337.5 units tall (x 746.7–986.7, y 292.4–629.9) |
| its anchor cluster incl. the title | 345.9 units |
| the sheet | 891.0 units tall |
| the table as a fraction of the sheet | **37.9%**, cluster **38.8%** |
| `ZONE_MAX_LIMITS["shim"]` height | **0.35** |
| the box that came out | y 346.9–658.8 — **311.85 tall, its cap to the unit** |
| `総厚サ 6mm` | y=311.1, **35.8 units below the bottom edge of its own zone** |

> **The cap was smaller than the thing it was capping.** No amount of correct growth could
> cover that table while 0.35 stood.

`_expand_bbox` refuses any point that would push the cluster past the cap, so a cap below the
table's own size does not produce a *smaller box around the right content* — it **excludes real
rows from the zone that owns them**, in the direction that manufactures findings.

## The fix

`ZONE_MAX_LIMITS["shim"]` height **0.35 → 0.45**. Measured after: **0 rows uncovered on either
side**, and the only thing inside the box but outside the drawn table is the table's own title
(`シム表`), drawn above its top rule and part of it. The box now stops on its own content rather
than on the limit. Cache **v47 → v48**.

Checked in the other direction too, because over-growth on a SAFE zone is the expensive
failure — anything the box swallows is dropped from `drawing_views` with **no finding to show
it happened**. A dimension 120 units clear of the table is not pulled in, and the end-to-end run
reports **0 findings inside either drawn shim table** while the two roll-count lines still pair
with their own counterparts.

## ⚠ No published number moves when this breaks

`M745227N01` is the **only** corpus pair carrying a shim table and it is one of the six the
runner skips for having no labels. Both baselines are byte-identical across this change —
`baseline-v48.json` and `baseline-v48-detection.json` differ from the v47 pair only in the
version stamp. The same blind spot as
[[Gotcha - Every Published Baseline Measures a Configuration Users Do Not Get]], arriving from
the other side: there the number measured a configuration users do not get, here there is no
number at all. `tests/test_shim_safe_zone.py` is the only guard, and its fixture is the real
measured geometry — under the old cap it reproduces the live box to the unit
(716.7, **346.875**, 1016.7, **658.725** against the drawing's 716.7, **346.9**, 1016.7,
**658.8**), and three of its four tests fail. That failure path was run, not assumed —
see [[Gotcha - A Guard Test's Failure Path Had Never Run]].

## The net, added because the invariant had three keepers

Fixing the cap fixed *this* leak. It did not make the class impossible, and the owner reported
the same symptom twice in one day, so the invariant is now enforced once at the end rather than
assumed at three separate points:

| keeper | what it covers |
| :--- | :--- |
| `safe_filter` | the `drawing_views` pool only |
| `inject_bom_markings` / `inject_title_block_markings` | consult **no** zone at all |
| `resolve_marking_coordinates` | can *move* a marking after both of the above decided |

The **safe-zone net** in `orchestrator`, immediately after coordinate resolution, drops any
marking whose owning zone is `shim` or `tolerance`.

> **Keyed on ownership, never on a bare box test — a box is not a claim.** The revision's
> `tolerance` box over-reaches into the title block on this pair and **7 real `title_block`
> findings sit inside it**. `owner_of` walks ZONE_PRECEDENCE, `title` outranks `tolerance`, and
> all seven survive. A naive "is it inside the tolerance box?" test would have deleted every
> one — silently, in the direction this system cannot detect.

Measured: it drops **0** findings on the reported pair and leaves both baselines byte-identical.
That is the point — **it is a net, not a fix.** Anything it ever drops is a bug upstream of it,
so each drop is logged with the zone that claimed it.

## ⚠ This was not the whole of the reported symptom

The checkmarks the owner photographed survived this fix *and* the net, a dev-server restart, and
a delete-and-re-upload of the pair. The remaining ones were invented on the client:
`markerGenerator.ts` re-grounded an **unplaceable** BOM value by text match and emitted one
marker per match, painting the shim table's quantity column. See
[[Gotcha - One Unplaceable Finding Became a Checkmark on Every Matching Cell]].

Worth recording as a debugging lesson in its own right: **three independent mechanisms produced
the same symptom on the same table**, so each correct fix looked like it had failed, and the
backend measured clean throughout — which was true and was not the answer.

## ⛔ Not fixed by reading the drawn table

Reading the box off the table's own ruled border was implemented on 2026-08-12 and **reverted
the same day on the owner's call**. This is the minimal alternative and it touches no pairing
code — one constant, and the caps table was already the single place both zone-producing paths
consult.

## The transferable rule

> **A cap must be able to contain the thing it caps, or it is not a limit — it is a silent
> truncation.** Every entry in `ZONE_MAX_LIMITS` is a claim about how large that zone can
> legitimately be; check it against the largest real instance, not against intuition. `shim`'s
> comment said *"a compact parts table, never large"*, which was true of the table and false of
> the sheet it was measured against.

And the older rule it re-proves, from the other direction:

> **Only take content out of the shared pool if you will compare it** — and conversely, if a
> zone will not compare its content, it had better cover all of it.

## Guarded by / cache

`tests/test_shim_safe_zone.py` (4). Cache **v48**.
