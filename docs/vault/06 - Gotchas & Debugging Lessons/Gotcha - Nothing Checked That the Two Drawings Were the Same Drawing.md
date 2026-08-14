---
title: Gotcha - Nothing Checked That the Two Drawings Were the Same Drawing
type: gotcha
tags: [gotcha, ingestion, rooms, validation, revision-detection, comparison]
status: resolved
date: 2026-08-12
cache-version: n/a — no comparison behaviour changed. The guard runs at ingestion and
  rejects the pair before an audit exists; spatial matching and zone extraction are untouched,
  so hard constraint 2 does not apply.
related: [Gotcha - Room-Owned Drawing Deletion, Gotcha - A Swallowed AttributeError Made a Write Path a Permanent No-Op]
---

# Gotcha — nothing checked that the two drawings were the same drawing

**Class:** missing precondition · **Found:** 2026-08-12, reported by the owner from a live room

---

## Symptom

Room 228 held `M745228N01R1A_REFERENCE.DXF` on the left and `M745219N01_FSRS2_KMTI.DXF` on the
right — **two unrelated parts**. The system ingested both, aligned zones, ran the comparison and
produced a full result. Nothing anywhere said the premise was wrong.

The output of comparing two unrelated drawings is not an error. It is a complete, confident
report in which nearly every value differs — the shape of a real answer, carrying no information.
This is the failure mode [[Gotcha - A Swallowed AttributeError Made a Write Path a Permanent No-Op]]
names: **a component whose healthy output and whose broken output are the same value.**

## Cause

There was no precondition. `createUploadSlice` checked file extension, size, MZ header, and
format agreement between the slots — everything about the *file*, nothing about the *drawing*.

## The part that cost the time: the obvious fix does not work

`DrawingDocument.part_number` exists for exactly this, populated by `detect_revision` at the end
of extraction. It is **dead on real drawings** — measured, not assumed: `detect_revision` returns
`None` on **14 of 14 corpus sides**. Two gates fail independently, and neither is a tuning problem:

1. It only reads text on layers matching `am_bor|border|title|title_block`. The measured layers
   carrying the number are `RAHM2`, `WAKU` and `NoLayerName_001`.
2. It requires the label and value in **one** text entity (`DWG NO: M745203N01`). This title
   block rules them into separate cells, so they are separate entities — which is precisely why
   `bom/title_block_extractor.py` has to run a spatial proximity search to pair them.

So Phase 7.2's revision chain has **never fired on this client's drawings**, and neither has the
`previous_revision_id` auto-link that consumes it (`audits.py:101`). Recorded here rather than
fixed, because repairing `part_number` would switch that dormant auto-link on as a side effect of
adding a validation guard. **Waking a feature nobody has ever seen run is not a free by-product;
it is an unreviewed behaviour change.** The guard therefore uses its own field.

## The design: do not identify the number, ask whether they share one

`infrastructure/cad/drawing_identity.py` collects every text token *shaped* like a drawing number
and stores the set on the drawing. The guard asks only whether the two sheets **share** one.

That is deliberately weaker than "extract the drawing number", and stronger in practice — it
tolerates noise. `M745227N01`'s reference genuinely carries a stray `C2801P` alongside its real
number; an extractor that had to pick one would need to be right about which, and this does not.

Measured over the eval corpus, the only ground truth available:

| | result |
| :--- | :--- |
| 7 real reference/revision pairs | **7/7 share a token** — none would be rejected |
| 42 cross-pairings (`ref[A] × rev[B]`) | **42/42 share none** — all rejected |

## The rule

**Absent evidence is not a mismatch, and the asymmetry is the reason.**

A false reject deletes a drawing the user just uploaded. A false accept only runs the comparison
they already asked for. So a sheet whose numbering does not match the expected shape, or a
drawing ingested before this field existed, yields no tokens — and **passes**. Both the Python
and TypeScript halves encode this, and it is the property most worth keeping pinned.

⚠ `_DRAWING_NUMBER_SHAPE` is tuned to KMTI's `M745203N01` / `M7452A0N01` form. Another client's
numbering will most likely yield nothing and fail open, which is the correct default but means
**the guard silently does nothing there.** It is a net over one client's drawings, not a
general-purpose identity check.

## Where the deletion lives, and why that is not negotiable

[[Gotcha - Room-Owned Drawing Deletion]] is explicit: deletion belongs only where user intent is
unambiguous — a completed replacement upload, or an explicit room delete — because the room PATCH
and the reset primitive both fire transiently with a mismatched (room, drawings) pair.

The rejection satisfies that test: it is the drawing the user *just* uploaded, into a slot they
just targeted, in the room currently open. So the delete lives in `applyCompletedDrawing`, the
single gate both completion paths now go through (the immediate one in `uploadDrawingFile` and
the polled one in `useUploadJobPolling` — previously two independent code paths that installed a
drawing, which is how a guard on one of them would have been half a guard).

**It deletes the rejected upload, never the drawing already in the room**, and that is pinned by
its own test rather than left to the reading.

## Known interaction, not fixed here

Replace-delete purges the displaced drawing *as soon as the upload persists*, before extraction
and therefore before this guard runs. So uploading a mismatched drawing **over an occupied slot**
loses the drawing that was there and then rejects the new one, leaving the slot empty. The user
re-uploads; nothing irreplaceable is lost (the source file is theirs). Fixing it properly means
holding the whole displaced `DrawingItem` in the store and restoring it on rejection — the UI has
already dropped it by then, so an id is not enough — which is a larger change with its own
cross-room risks. Flagged deliberately rather than half-done.

## Guards

- `tests/test_drawing_identity.py` (13) — extraction off the real layer names, prose/dimension
  rejection, the `C2801P` noise case, case normalisation, and the corpus discrimination matrix
  above. The corpus test **skips** when the gitignored payloads are absent rather than passing
  vacuously.
- `apps/desktop/src/utils/__tests__/drawingIdentity.test.ts` (8) — the TypeScript twin, same cases.
- `apps/desktop/src/stores/__tests__/createUploadSlice.test.ts` (+5) — rejection deletes the new
  drawing and not the old one, the slot is left empty, the message names both numbers, and both
  fail-open paths install normally.

One defect was caught by these while writing them: `is_pair_mismatch` compared raw strings while
its TypeScript twin normalised case, so `m745203n01` and `M745203N01` would have read as two
different drawings. Two implementations of one rule need the same tests pointed at both.
