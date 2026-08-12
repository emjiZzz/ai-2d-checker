---
title: Gotcha - One Unplaceable Finding Became a Checkmark on Every Matching Cell
type: gotcha
tags: [gotcha, frontend, markers, safe-zone, guard-fails-open]
status: resolved
date: 2026-08-12
---

# The guard was written for this exact bug, and it failed open

Reported three times in one afternoon, each time as **green MATCHED checkmarks inside the シム表**
— a SAFE zone that is never compared. The first report was a real zone-detection defect
([[Gotcha - A Zone Cap Smaller Than the Table It Caps]]) and fixing it removed one marking. The
checkmarks stayed. The owner then restarted the dev server, **deleted and re-uploaded the pair**
— which changes the drawing ids and therefore the whole cache key — and they were still there.

That ruled out cache and ruled out the backend, because the backend's own output was clean:
**no finding had coordinates inside the shim table.** The markers were being invented on the
client.

## What actually happened

`markerGenerator.ts` re-grounds markings by fuzzy text match against the drawing's entities.
For `title_block` and `bill_of_materials` it is not supposed to — those are extracted from
specific cells and carry authoritative coordinates — and the code said so, in a comment that
names this very failure:

> *"Re-grounding a short value like `4`/`1`/`0` by text match anchors it to a same-valued cell
> elsewhere on the sheet — e.g. a tolerance-grid cell."*

The guard was `!(isStructuredCategory && hasBackendCoord)`. **It only skipped grounding when the
backend had already supplied a coordinate** — so in the one case where grounding is genuinely
dangerous, the case with nothing to sanity-check the result against, it fell straight through.

On `M745227N01` the BOM's deferral row produces `Q'ty: 1 vs 1` with
`coordinates: null, resolution_method: "unresolved"`. Search term `"1"`. Being ≤6 characters it
takes the *exact match* path, which returns **every entity on the sheet reading `1`** — and the
loop below emits **one marker per match**:

```
maxInstances = Math.max(matches.length, refMatches.length, 1)
```

One finding, three markers, painted straight down the 一組分個数 column of the shim table. All
labelled `bill_of_materials / MATCHED`, all pointing at a table that is never compared.

The reproduction is exact: the regression test, run against the old condition, produces
**3 markers** for one unresolved `"1"` — the three the owner photographed.

## The fix

Skip text grounding for structured categories **unconditionally**. A BOM or title-block value
has no meaning outside the cell the backend read it from, so when the backend could not place
it, it gets **no marker**. The value is still reported in the BOM / title-block table; what is
dropped is a claim about *where* it is that nothing could support.

`RawViolation.coordinates` was also widened to `[number, number] | null`. It was typed
`[number, number] | undefined`, which is **not what the payload carries** — and that gap is part
of why the unresolved case went unhandled: a reader checking the type would conclude it could
not arise.

## The transferable rules

> **A guard conditioned on the evidence being present cannot fire when the evidence is missing —
> which is the case it exists for.** `hasBackendCoord` was doing double duty as "is this
> trustworthy" and "does this exist", and the two answers diverge exactly when it matters.

> **One finding must not become many markers.** A fan-out over text matches turns an unplaceable
> value into confident-looking marks on unrelated content. If the position is unknown, the
> honest render is nothing.

And the reason it took three reports: **the backend was measured clean each time and that was
true.** Three separate mechanisms produced the same symptom on the same table — a zone cap, then
the pool guards, then client-side re-grounding — so each fix looked like it had failed.

## Guarded by

`apps/desktop/src/utils/markerGenerator.test.ts` — *"does NOT scatter an UNRESOLVED bom value
across every same-valued cell on the sheet"*, sitting next to the pre-existing test for the
*resolved* case that this defect slipped past. Verified failing against the old condition
(3 markers) before the fix, so the failure path has been run — see
[[Gotcha - A Guard Test's Failure Path Had Never Run]].

No cache bump: display-only, nothing in the comparison changed.
