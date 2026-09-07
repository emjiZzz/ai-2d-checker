---
title: Gotcha - A Room Restored From Its Findings Lost Every Checkmark
type: gotcha
tags: [gotcha, frontend, state-restore, zustand, rooms, physical-comparison, review]
status: resolved
date: 2026-08-14
cache-version: n/a — frontend restore path only. Spatial matching, zone extraction and the shape
  of the cached payload are all untouched, and the fix reads a field the backend has always
  written, so hard constraint 2 does not apply. Nothing about `COMPARISON_CACHE_VERSION` changes.
related: [Gotcha - The Cache Served Findings That Existed Nowhere, Gotcha - A Tested Endpoint That Nothing Ever Called, Gotcha - One Unplaceable Finding Became a Checkmark on Every Matching Cell]
---

# Gotcha — a room restored from its findings lost every checkmark

**Class:** lossy restore from a strict subset · **Found:** 2026-08-14, from a user report that
re-entering a room "loses the checkmarks"

---

## Symptom

Run a physical comparison in a room, leave, come back. The coloured findings return. **Every green
checkmark is gone.**

Nothing errors. The canvas renders, the checklist populates, the compliance score is right. The
result simply has fewer rows than it did a minute earlier, and the rows it dropped are exactly the
ones that were *fine* — which is the half a reader is least likely to be counting.

## Cause

A comparison produces a marking for **every** compared row. It persists a document for only the
rows that **failed**.

```python
# orchestrator.py:1933 — all of them, onto the Room
canvas_markings=[CanvasMarking(**item) for item in clean_markings],

# orchestrator.py:1939 — and then only the failures
non_matched = [m for m in clean_markings if m.get("status") != "MATCHED"]
...
for marking_dict in non_matched:            # :1966
    ...
await AuditViolation.insert_many(violations_to_save)   # :1994
```

That asymmetry is correct and deliberate: an `AuditViolation` is a *finding*, and there is nothing
to review about a row that matched. The consequence is that **the persisted violations are a
strict subset of the markings**, and the MATCHED rows — the checkmarks — exist in exactly one
place: `physical_comparison_results.canvas_markings` on the Room document.

`roomStore.openRoom` restored from the wrong one of those two:

```ts
if (roomData.active_audit_session_id && newDoc) {
  // fetch the session + its violations, hand them to loadSessionIntoWorkspace
} else {
  // ...and here, unreachable, sat the canvas_markings restore
}
```

`loadSessionIntoWorkspace` sets `violations` to precisely what it was handed
(`createAuditSlice.ts`). So the session branch rebuilt the room from the non-MATCHED subset and
every checkmark was dropped — **not by a bug in the restore, but by restoring from a source that
never contained them.**

## Why it survived

**The correct code existed, was correct, and had never run for a room anyone cared about.**

The `canvas_markings` restore was sitting in the `else` — the branch taken only when a room has
**no** `active_audit_session_id`, which is to say a room no comparison has ever been run in. The
one state where the checkmarks matter is the one state that branch could not reach.

*Correct code in an unreachable branch reads as coverage.* Grepping for `canvas_markings` in the
store finds a restore, with a comment explaining it, doing the right thing. Nothing about it looks
dead, because it is not dead in general — only for every room that has been compared. This is the
same shape as [[Gotcha - A Tested Endpoint That Nothing Ever Called]], one level in: not a path
nothing called, but a path only the uninteresting case could call.

The symptom hid the rest. "Some rows are missing" invites you to look at filtering, at
`hiddenViolationIds`, at the checklist's own rendering — all downstream of a `violations` array
that was already short before any of them saw it.

## The rule

**When one representation is written in full and another is persisted as a filtered subset of it,
restoring from the subset is lossy by construction — it is not a bug you can find by reading the
restore.** Ask which field is the complete record *before* asking whether the code that reads it
is correct.

Corollary, and the reason the fix is a join rather than a swap: the subset was still needed.
Markings are the **render** source and carry no id; persisted violations are the **identity**
source and carry nothing else the canvas needs. Neither alone reconstitutes the room.

## Resolution

`openRoom`'s session branch now prefers the room's markings when it has them, reconciled against
the very violations it had already fetched (`roomStore.ts`):

```ts
const sessionMarkings = roomData.physical_comparison_results?.canvas_markings;
if (Array.isArray(sessionMarkings) && sessionMarkings.length > 0) {
  useWorkspaceStore.setState({
    violations: reconcilePersistedIds(mapCanvasMarkingsToMarkers(sessionMarkings), violationsData),
  });
}
```

Three things about that shape are load-bearing:

1. **It can only add rows, never remove them.** When a room stored no markings — an audit that was
   not a physical comparison — the guard falls through and the session violations stand.
2. **`reconcilePersistedIds` is what keeps the findings reviewable.** Restored markers carry
   synthetic `phys_chk_restored_*` ids, so without the join a supervisor's verdict would PATCH a
   document that does not exist — see [[Gotcha - The Cache Served Findings That Existed Nowhere]]
   for what that costs. MATCHED rows never match a persisted document and stay unreviewable, which
   is correct rather than a gap.
3. **Overwriting `violations` after `loadSessionIntoWorkspace` is safe** because that action
   derives nothing from the array it sets — it resets `hiddenViolationIds` to `{}` and sets no
   other violation-keyed state. If that ever stops being true, this becomes a desync.

The mapping was extracted out of the `else` branch into
`apps/desktop/src/utils/restoreCanvasMarkings.ts`, so the two restore paths cannot drift — they
had already drifted once, when the live path kept `entity_handle`/`status` and the restore path
silently dropped them.

Pinned by **`apps/desktop/src/stores/__tests__/roomStore.openRoom.test.ts`** (4 tests), confirmed
to fail against the pre-fix store with `expected [] to have a length of 2` — the reported symptom
exactly — rather than merely to pass after. It covers the fallback and the no-session path too,
so "delete the new branch" does not also pass.

### Footnote: an interface cannot satisfy `MarkerLike`

`reconcilePersistedIds<T extends MarkerLike>` constrains on a type carrying
`[key: string]: unknown`. TypeScript grants an **implicit** index signature to object type
literals but **never to an interface**, so `interface RestoredMarker extends ViolationItem {...}`
fails the constraint no matter how correct its fields are. The signature is declared explicitly on
`RestoredMarker` for that reason. Cheap to fix, expensive to diagnose from the error text, which
talks about a missing property rather than a missing index signature.
