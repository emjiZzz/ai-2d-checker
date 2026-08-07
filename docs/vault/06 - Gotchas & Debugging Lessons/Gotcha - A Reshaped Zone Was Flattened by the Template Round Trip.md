---
tags: [gotcha, zones, zone-template, frontend, reshape, silent-data-loss]
status: FIXED 2026-08-06 — confirmed by the reporter
cache-version: n/a — client-side only; no engine behaviour changed
date: 2026-08-06
verified-against: reported live, both regression tests verified to fail against the old code
---

# Gotcha — A Reshaped Zone Was Flattened by the Template Round Trip

> [!IMPORTANT] Reported as *"I edit the zone boxes and realign → clicked DONE → shows edit zone
> boxes again → didn't apply what I change"*, and correctly diagnosed by the reporter as
> **"this bug occurs after the implementation of adding nodes to zone boxes."** That sentence
> is what located it: a zone stopped being four scalars when reshaping landed, and two places
> still described the old shape.

## The two defects

**1. The client's template type and payload builder were blind to `points`.**

`saveZonesAsTemplate` rebuilt every zone as a four-field object literal:

```ts
zones[key] = {
  xMin: clamp01(frac.xMin), xMax: clamp01(frac.xMax),
  yMin: clamp01(frac.yMin), yMax: clamp01(frac.yMax),
};   // ← points dropped
```

…and `ZoneTemplateFractions` in `drawingsApi.ts` declared only those same four fields, so
TypeScript agreed with the omission rather than catching it. The **backend was never the
problem**: `ZoneFractions.points` and `ZonePoint` have always existed and the API has always
accepted them. Only the client could not express an outline.

Worse than a lost save: `saveZonesAsTemplate` then calls `applyZoneTemplate(d.id, zones, …)`,
which writes the flattened payload straight back over the live regions — so the reshape
disappeared *on screen*, at the moment of saving it.

**2. The template was stamped over local regions on every editor open.**

`seedCustomRegionsFromDetected` guarded the detector path carefully —

```ts
// The DETECTOR only seeds a drawing that has no alignment yet. Re-seeding over an
// existing one would silently discard the user's own work
if (!state.customRegions[drawingId]) { … }
```

— and then applied the template **unconditionally**. So re-entering the editor replaced every
pinned zone with its template rectangle, discarding any unsaved reshape.

That unconditional stamp was itself a deliberate fix: a stale `localStorage` seed used to mask
a pinned zone and make it look reverted. The rule is right for a value restored from disk and
wrong for one the user just dragged, **and `customRegions` alone cannot tell those apart.**

## Why it was silent

**A zone outline is additive by design** — `regions[zone_key]` stays a 4-tuple and the outline
rides alongside, so old templates parse as the rectangles they were with no migration. See
[[Gotcha - A Reshaped Zone Is Not Its Bounding Box]]. The same property means a *dropped*
`points` is not an error: it degrades to a perfectly valid rectangle. Nothing threw, nothing
logged, and the zone still looked like a zone.

It was invisible before reshaping existed because the four scalars *were* the whole zone: the
literal was complete, and stamping a rectangle over a rectangle changed nothing you could see.

## The fix

- `ZoneTemplateFractions` gains `points`, and the payload builder moved out of the component
  into a pure `zonesToTemplatePayload` in `zoneFractions.ts` — the same reason `zoneGate.ts` is
  pure: the bug lived in a component that cannot be mounted without flexlayout, a canvas and a
  ResizeObserver. It **spreads** `frac` rather than re-listing fields, so the next field added
  to `RegionFractions` cannot be dropped the same way.
- `userAlignedZoneKeys` records which zones a **human** placed — `updateCustomRegion` and the
  two undo/redo restores are the user's write paths, since seeding writes through `set`
  directly — and the template stamp skips them. `Reset` and `applyZoneTemplate` clear the
  record, because both are explicit "use the template/detector" decisions.

  **Persisted, and it was session-scoped first — that was wrong.** The reasoning was that
  "Save to template" is how an edit outlives a session. It survived one round of testing and
  then failed the obvious way: *"server restarts and the zones back to default."* A
  per-drawing alignment is legitimate work a user expects to survive a restart, and a template
  is a per-*layout* default, so the more specific value has to win — the same precedence the
  backend already uses when a signature-specific template beats the global default. The record
  now lives in `custom_regions_aligned_<id>`, a sibling of the regions entry, so an install
  that predates it reads back "nothing was hand-aligned" and behaves exactly as before.

`zoneFractions.test.ts` (+5) and `zoneTemplateSeeding.test.ts` (+4). The one that matters was
**verified to fail against the unconditional stamp**, and the three guarding the preserved
behaviour still pass — a regression test that passes either way proves nothing.

**A test caught a bug in the fix**, which is worth recording: spreading `frac` to future-proof
the field list also let a *degenerate* outline (fewer than `MIN_ZONE_POINTS`) ride through,
because the spread had already copied `points` before the conditional could decline to add it.
Setting a field conditionally is not the same as removing it; the helper now deletes it
explicitly.

## The root confusion, stated plainly

`customRegions` — and its `localStorage` entry — holds **two different kinds of value under
one key**: boxes the detector seeded, and boxes the user dragged. Once written they are
indistinguishable, and that single ambiguity produced a bug in each direction:

| Trusting… | Produces |
| :--- | :--- |
| the local entry | a stale **detector** seed masks a pinned template zone → a saved alignment looks reverted |
| the template | a **user's** own alignment is destroyed on every editor open and every restart |

Neither policy is right, because the question "should the template override this box?" cannot
be answered from the box. **Recording who placed it is what makes both answerable** — and the
record has to have the same lifetime as the thing it describes, which is why session-scoping
failed as soon as the app was restarted.

## Rules

- **When a value gains a field, grep for every place it is rebuilt from a literal.** A spread
  survives the change; an enumerated object silently truncates. The type will agree with the
  truncation if the type was written against the old shape too.
- **An additive design converts schema drift into silent data loss.** It is the right design —
  it is what made reshaping migration-free — but it removes the error you would otherwise get,
  so the field list becomes something only a test can hold.
- **"It broke after feature X" from a reporter is a bisect you did not have to run.** Here it
  pointed straight at the one construction site that predated the feature.
- **When one key stores values from two different authors, no override policy can be correct.**
  Record the author, not a better guess — and give that record the same lifetime as the value,
  or it degrades to a guess again at the first restart.
- **Check the persisted artifact before theorising about persistence.** The stored template was
  dated two days before the session being debugged, which said immediately that the edits had
  never reached the server and the question was entirely client-side.

## Postscript — it survived the fix, in a second file (2026-08-07)

The rule above says grep every place the value is rebuilt from a literal. **That grep was not
run, or not run widely enough.** `SavedTemplatesModal.handleSaveTemplate` is the *other* place a
template is saved and stamped over both panes, and it still carried the enumerated
`{xMin, xMax, yMin, yMax}` literal — so "Save Current Alignment to Template" in the modal
flattened every reshaped zone exactly as the toolbar button used to, four days after the toolbar
button was fixed.

Nothing pointed at it. The two paths produce identical UI feedback, the modal's own comment
(about filtering non-zone keys) reads as though the payload construction had been considered,
and `tsc` agreed with the truncation for the same reason it did the first time.

Both call sites now go through `zonesToTemplatePayload`, and the modal has a DOM-level test —
`SavedTemplatesModal.test.tsx` — that clicks Save and asserts `points` survives. **The test had
to be driven through the DOM**: the defect was in the call site, so a test that invoked
`zonesToTemplatePayload` directly would have passed against the broken code, which is precisely
why the helper's existing unit tests did not catch this.

The strengthened rule: **when a bug is a construction site, fixing one site is not the fix — the
fix is a test at every site that constructs.** "Grep for the others" is an instruction to a
human who may not run it; a test is the version that runs itself.

## See also

- [[Gotcha - One Click on Two Panes Recorded Two Undo Steps]] — found in the same file, in the
  same pass: this modal also recorded no undo history for either write path
- [[Gotcha - A Reshaped Zone Is Not Its Bounding Box]] — the reshape feature and its additive design
- [[Gotcha - Zod Strips Unknown Room Fields]] — the same class one layer out: a field the
  client's schema does not know about vanishes without an error
- [[Gotcha - Zone Template Pollution (Non-Zone Keys)]] — the opposite direction, extra keys
  rather than missing ones
