---
tags: [gotcha, frontend, undo, zones, react]
status: fixed
cache-version: n/a — desktop UI state only, no engine or zone-extraction behaviour
date: 2026-08-07
---

# Gotcha — One Click on Two Panes Recorded Two Undo Steps

> [!WARNING] Ctrl+Z appeared broken inside the zone editor. It was not: **Reset**, **Save to
> template**, and the zone picker's chips each write one history entry *per drawing*, and the
> 2D workspace has two. One press undid the reference pane and left the revision as it was.

## What happened

The editor's toolbar actions all loop over both drawings:

```ts
for (const d of [oldDrawingForZones, newDrawingForZones]) {
  recordHistory({ kind: 'zone/bulk', label: 'Reset zone alignment', drawingId: d.id, ... });
  resetCustomRegions(d.id);
}
```

Two entries. The user clicked once. `performUndo` pops one entry, so the first Ctrl+Z restored
one pane's boxes and the second pane stayed empty — and the two panes sit side by side, so the
result is visibly *wrong* rather than visibly *half-done*.

## Why it read as "undo is broken" rather than "undo needs two presses"

The state after one press is a state the user never created and cannot create: the reference
aligned, the revision reset. There is no mental model in which that is a step backwards through
their own history, so the natural reading is that the feature is faulty. A second press would
have fixed it, but nobody presses again after watching the first press produce nonsense — they
reach for Reset, or they file a bug.

This also survives every obvious diagnosis. The listener is installed exactly once
([[Gotcha - A Window Listener in a Per-Pane Hook Fires Once Per Pane]]), nothing clears the
stack when the editor opens, and `applyHistoryEntry` is correct for every entry kind and is
covered by tests. Each *entry* does exactly what it should. The defect is that **an entry is
not the unit the user acts in.**

Single-pane edits — dragging a handle, inserting or removing a node — were never affected, so
the bug only appeared for the toolbar, and only when both drawings were loaded.

## The rule

**One user action is one undo step, no matter how many stores or documents it touches.** Where
a handler loops over the panes, collect the entries and record them with `recordHistoryGroup`
rather than calling `recordHistory` inside the loop.

`recordHistoryGroup` stamps a shared `groupId` across the entries; `performUndo`/`performRedo`
drain the whole group. A single entry is recorded ungrouped, so the common case carries no
marker at all and the stack stays flat.

Two details worth keeping:

- **The group boundary must not leak.** The drain loop stops as soon as the next entry's
  `groupId` differs, so an ordinary edit made before the click survives it.
- **`MAX_HISTORY` can tear a group.** Dropping the oldest entry of a pair leaves the other to
  undo one pane on its own, reproducing the original bug 100 gestures later. `record` discards
  the rest of a torn group along with it.

## The fourth site had no history at all

`SavedTemplatesModal` is the other place a template is saved and stamped over both panes, and
it called `applyZoneTemplate` on each drawing while recording **nothing**. Applying a saved
template from that modal wipes both panes' alignment — the same destructive reach as Reset —
and Ctrl+Z did not touch it, while the identical operation from the toolbar was undoable.

Worth noting how that asymmetry hid: the modal is where you go to *manage* templates, so it
reads as a settings surface rather than an editing one, and settings surfaces are not expected
to be undoable. The reach is what makes it an edit, not the affordance it lives behind.

## A second defect found alongside it

`restoreCustomRegion` marked a zone as hand-aligned on *every* restore, including one that
removes the box (`bounds === null`, i.e. undoing the chip that created it). The mark is what
makes a zone immune to the template stamp on the next editor open, so undoing a chip left the
zone in the one state nothing can fix: no box, and no template allowed to supply one. It now
drops the mark when the box goes, matching `restoreDrawingRegions`' `regions === null` branch.

## The transferable lesson

Undo bugs are rarely in the applier. The applier is data-in/data-out and easy to test — this
one had a full suite and every case passed. The bugs are in **where the boundaries were drawn**
when the entries were recorded, which is at the interaction layer, in a loop, where nothing
looks like undo code at all.

## See also

- [[Gotcha - A Window Listener in a Per-Pane Hook Fires Once Per Pane]] — the other undo defect
  caused by pane count, from the opposite direction: one press, two handlers
- [[Gotcha - A Reshaped Zone Was Flattened by the Template Round Trip]] — the template stamp
  that the alignment record exists to hold off
- [[Gotcha - A Reshaped Zone Is Not Its Bounding Box]] — the geometry undo has to restore intact
