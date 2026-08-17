---
title: Gotcha - The Pinned Template Has No Shim Zone
type: gotcha
tags: [gotcha, zone-template, shim-table, safe-zone, eval-corpus]
status: open — found 2026-08-17 while labelling, not yet fixed
date: 2026-08-17
cache-version: n/a — nothing changed yet. Adding a zone to a template changes which entities are
  compared and must bump `COMPARISON_CACHE_VERSION`.
related: [Gotcha - Optional Zones and the Shim Table, Gotcha - A Zone Cap Smaller Than the Table It Caps, Gotcha - A Fixed OCR Misread Came Back Through the Title Zone, Gotcha - Global Default Zone Template & the Aspect Caveat]
---

# Gotcha — a safe zone that is absent from the template is not safe

**Class:** an omission that reads as a configuration · **Found:** 2026-08-17, while labelling
`M745227N01`

---

## Symptom

The worksheet for `M745227N01` attributes every row of the シム表 — its title, its column headers
(`No.` / `t` / `材質` / `一組分個数`), and all of its data rows — to zone **`views`**, on both
sides. Under [[Gotcha - Optional Zones and the Shim Table]] the shim table is a SAFE zone and must
**never be compared**. Attributed to `views`, it is compared.

## Cause

The pinned template for this pair's `zone_signature` has no `shim` key at all:

```
manifest.zone_templates['aspect-1.414'].keys()
  -> bom, iso, notes, title, title_upper_left, tolerance, views
```

Seven zones, and `shim` is not among them. There is no mis-sized box here and nothing to
re-align — the zone simply does not exist in the template, so nothing claims the table and it
falls through to the `views` pool.

## Why absence is worse than a bad box

**A pinned zone beats detection unconditionally.** That is the property the whole templating design
rests on, and it is stated in the ledger as the reason a mis-pinned zone is a *silent* miss. It
cuts the other way too: where a template exists, detection does not get a second opinion — so a
template that is missing a safe zone **disables that safe zone for every pair sharing the
signature**, no matter how well detection would have found it.

This is the difference from [[Gotcha - A Zone Cap Smaller Than the Table It Caps]], which is the
same table failing for the opposite reason: there, `ZONE_MAX_LIMITS["shim"]` was smaller than the
drawn table, so *detection* produced a box that truncated it. That note fixed detection
(0.35 → 0.45). **A fix to detection cannot reach a sheet whose template pins the zones**, and this
pair is one.

⚠ So the two notes together mean the shim table has now failed on this drawing family **twice, by
two independent routes**, and neither route's fix protects against the other.

## The rule

**A safe zone must be present to be safe.** Any zone whose job is *exclusion* is a claim that
something is being deliberately not compared, and an absent key makes that claim silently false —
where a wrong box at least produces a visibly wrong overlay. When auditing a template, check the
**key set** against the zones the sheet actually has, not just the geometry of the keys present.

Related shape, one level up: [[Gotcha - A Checklist Item With No Producer Reported Clean]] — an item
with no producer reports "no changes detected", and here a zone with no box reports nothing
excluded. **An empty configuration and a satisfied one look identical from the outside.**

## Blast radius

Every pair whose `zone_signature` is `aspect-1.414` **and** whose sheet carries a シム表. In the
eval corpus that is `M745227N01` alone, which is also the only corpus pair with a shim table at all
— so **no published baseline can see this**, exactly as the 2026-08-12 work-log entry predicted for
the cap fix. In production it is every A-series sheet with a shim table, which is a real fraction
of this client's drawings.

## Not fixed, and the decision is not purely technical

Adding a hand-aligned `shim` box to the `aspect-1.414` template is a few minutes' work in the zone
editor. Two reasons it is not done here:

1. **It is a ground-truth change disguised as a config change.** The labels for `M745227N01` were
   authored on 2026-08-17 treating the シム表 as a safe zone *by rule* — its two worksheet rows are
   in `not_findings` with that reasoning. Adding the zone changes which entities the engine
   compares and therefore which findings it can produce, so the pair should be re-scored and the
   label file's reasoning re-read at the same time.
2. **The aspect-keying limitation is the real defect**, and it now has three notes pointing at it
   (this one, [[Gotcha - A Fixed OCR Misread Came Back Through the Title Zone]], and the original
   [[Gotcha - Mislocated OCR Crop and Ungrounded Misreads]]). Patching one missing key on one
   signature is worth doing, but it should be recorded as a patch and not as the fix.

## Guarded by

Nothing. A cheap and worthwhile check: assert that every committed template whose pairs carry a
shim table declares a `shim` key — or, more generally, that a template's key set covers every SAFE
zone the guideline names. `tests/test_zone_template_residual.py` is the existing home for
template-integrity assertions of this shape.
