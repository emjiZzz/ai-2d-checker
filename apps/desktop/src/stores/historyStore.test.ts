/**
 * Tests for the unified undo/redo history.
 *
 * These assert on `applyHistoryEntry` directly rather than dispatching synthetic mouse events
 * at two canvases: the applier IS the semantics of undo, and reaching it through the DOM would
 * test jsdom's event plumbing more than the behaviour that matters.
 *
 * The cases here are the ones that produce plausible-looking wrong state rather than a crash —
 * a zone that comes back as an empty box instead of being removed, or a marker restored twice
 * because two affordances both think they own the deletion.
 */
import { beforeEach, describe, expect, it } from "vitest";

import {
  MAX_HISTORY,
  recordHistoryGroup,
  useHistoryStore,
  type HistoryEntry,
} from "./historyStore";
import { applyHistoryEntry, performRedo, performUndo } from "../hooks/useUndoRedo";
import { useReviewStore } from "./reviewStore";
import { useWorkspaceStore } from "./workspaceStore";
import type { ViolationItem } from "./workspace/types";

const DRAWING = "drawing-1";
/** The second pane. The editor's toolbar actions always touch both. */
const DRAWING_B = "drawing-2";

const BOX_A = { xMin: 0.1, xMax: 0.2, yMin: 0.1, yMax: 0.2 };
const BOX_B = { xMin: 0.5, xMax: 0.7, yMin: 0.5, yMax: 0.7 };

function violation(id: string): ViolationItem {
  return {
    id,
    description: `violation ${id}`,
    coordinates: [10, 20],
  } as ViolationItem;
}

beforeEach(() => {
  useHistoryStore.setState({ past: [], future: [] });
  useReviewStore.setState({
    customRegions: {},
    pinnedZoneKeys: {},
    userAlignedZoneKeys: {},
    hasSeededCustomRegions: false,
  });
  useWorkspaceStore.setState({ violations: [], deletedViolationsStack: [], selectedViolation: null });
  localStorage.clear();
});

describe("history stack", () => {
  it("records, undoes, and redoes in LIFO order", () => {
    const first: HistoryEntry = {
      kind: "zone/update", label: "a", drawingId: DRAWING, zoneKey: "title",
      before: BOX_A, after: BOX_B,
    };
    const second: HistoryEntry = {
      kind: "zone/update", label: "b", drawingId: DRAWING, zoneKey: "bom",
      before: BOX_A, after: BOX_B,
    };

    useHistoryStore.getState().record(first);
    useHistoryStore.getState().record(second);

    expect(useHistoryStore.getState().takeUndo()).toBe(second);
    expect(useHistoryStore.getState().takeUndo()).toBe(first);
    expect(useHistoryStore.getState().takeUndo()).toBeNull();

    // Both are now on the redo stack, and come back in the reverse order they were undone.
    expect(useHistoryStore.getState().takeRedo()).toBe(first);
    expect(useHistoryStore.getState().takeRedo()).toBe(second);
  });

  it("drops the redo branch once a new change is recorded", () => {
    const entry: HistoryEntry = {
      kind: "zone/update", label: "a", drawingId: DRAWING, zoneKey: "title",
      before: BOX_A, after: BOX_B,
    };
    useHistoryStore.getState().record(entry);
    useHistoryStore.getState().takeUndo();
    expect(useHistoryStore.getState().future).toHaveLength(1);

    useHistoryStore.getState().record({ ...entry, zoneKey: "notes" });

    // Redoing now would replay a change against state that has since moved on.
    expect(useHistoryStore.getState().future).toHaveLength(0);
  });

  it("bounds the stack, discarding the oldest entries", () => {
    for (let i = 0; i < MAX_HISTORY + 10; i += 1) {
      useHistoryStore.getState().record({
        kind: "zone/update", label: `edit ${i}`, drawingId: DRAWING, zoneKey: `zone-${i}`,
        before: BOX_A, after: BOX_B,
      });
    }
    const { past } = useHistoryStore.getState();
    expect(past).toHaveLength(MAX_HISTORY);
    // The survivors are the NEWEST ones — dropping from the wrong end would make Ctrl+Z
    // jump to an ancient edit.
    expect(past[past.length - 1].label).toBe(`edit ${MAX_HISTORY + 9}`);
    expect(past[0].label).toBe("edit 10");
  });
});

describe("zone/update", () => {
  it("restores the previous geometry on undo and re-applies it on redo", () => {
    useReviewStore.getState().updateCustomRegion(DRAWING, "title", BOX_B);

    const entry: HistoryEntry = {
      kind: "zone/update", label: "Edit zone box", drawingId: DRAWING, zoneKey: "title",
      before: BOX_A, after: BOX_B,
    };

    applyHistoryEntry(entry, "undo");
    expect(useReviewStore.getState().getRegionsFor(DRAWING).title).toMatchObject(BOX_A);

    applyHistoryEntry(entry, "redo");
    expect(useReviewStore.getState().getRegionsFor(DRAWING).title).toMatchObject(BOX_B);
  });

  it("REMOVES a zone whose `before` is null rather than writing an empty box", () => {
    // The zone picker seeds a box for a zone that had none; undoing that must leave the key
    // absent. A zero-size box left behind would read as "already placed" and never re-seed.
    useReviewStore.getState().updateCustomRegion(DRAWING, "shim", BOX_A);
    expect(useReviewStore.getState().getRegionsFor(DRAWING).shim).toBeDefined();

    applyHistoryEntry({
      kind: "zone/update", label: "Add zone box", drawingId: DRAWING, zoneKey: "shim",
      before: null, after: BOX_A,
    }, "undo");

    expect(useReviewStore.getState().getRegionsFor(DRAWING).shim).toBeUndefined();
    expect(JSON.parse(localStorage.getItem(`custom_regions_${DRAWING}`)!).shim).toBeUndefined();
  });

  it("drops the alignment record when the undo removes the box", () => {
    // Seeding from the chip marks the zone hand-aligned, which is what makes it immune to the
    // template stamp on the next editor open. Undo takes the box away, so the mark has to go
    // too — otherwise the zone ends up with no box AND no template to fill it, which is the
    // one state neither the chip nor the template can get it out of.
    useReviewStore.getState().updateCustomRegion(DRAWING, "shim", BOX_A);
    expect(useReviewStore.getState().userAlignedZoneKeys[DRAWING]).toContain("shim");

    applyHistoryEntry({
      kind: "zone/update", label: "Add zone box", drawingId: DRAWING, zoneKey: "shim",
      before: null, after: BOX_A,
    }, "undo");

    expect(useReviewStore.getState().userAlignedZoneKeys[DRAWING] ?? []).not.toContain("shim");
  });

  it("keeps the alignment record when the undo restores an earlier box", () => {
    // The other half of the rule: walking a reshape back to a previous shape is still the
    // user's own geometry, and it must stay immune to the template.
    useReviewStore.getState().updateCustomRegion(DRAWING, "notes", BOX_B);

    applyHistoryEntry({
      kind: "zone/update", label: "Edit zone box", drawingId: DRAWING, zoneKey: "notes",
      before: BOX_A, after: BOX_B,
    }, "undo");

    expect(useReviewStore.getState().userAlignedZoneKeys[DRAWING]).toContain("notes");
  });

  it("preserves a polygon outline through undo", () => {
    // A reshaped zone's `points` are the truth and the four scalars are derived. Restoring
    // only the bounding box would silently turn the polygon back into a rectangle.
    const polygon = {
      xMin: 0.1, xMax: 0.4, yMin: 0.1, yMax: 0.4,
      points: [
        { x: 0.1, y: 0.1 }, { x: 0.4, y: 0.1 }, { x: 0.4, y: 0.4 },
        { x: 0.25, y: 0.3 }, { x: 0.1, y: 0.4 },
      ],
    };
    useReviewStore.getState().updateCustomRegion(DRAWING, "notes", BOX_B);

    applyHistoryEntry({
      kind: "zone/update", label: "Edit zone box", drawingId: DRAWING, zoneKey: "notes",
      before: polygon, after: BOX_B,
    }, "undo");

    expect(useReviewStore.getState().getRegionsFor(DRAWING).notes.points).toHaveLength(5);
  });
});

describe("zone/bulk", () => {
  it("brings a whole alignment back after Reset", () => {
    const regions = { title: BOX_A, bom: BOX_B };
    useReviewStore.setState({
      customRegions: { [DRAWING]: regions },
      pinnedZoneKeys: { [DRAWING]: ["title"] },
    });

    const entry: HistoryEntry = {
      kind: "zone/bulk", label: "Reset zone alignment", drawingId: DRAWING,
      before: regions, after: null, pinnedBefore: ["title"], pinnedAfter: null,
    };

    useReviewStore.getState().resetCustomRegions(DRAWING);
    expect(useReviewStore.getState().customRegions[DRAWING]).toBeUndefined();

    applyHistoryEntry(entry, "undo");
    expect(useReviewStore.getState().customRegions[DRAWING]).toMatchObject(regions);
    // The pinned list travels with the boxes: without it, hand-aligned zones would come back
    // drawn as detector guesses.
    expect(useReviewStore.getState().pinnedZoneKeys[DRAWING]).toEqual(["title"]);
    expect(localStorage.getItem(`custom_regions_${DRAWING}`)).not.toBeNull();
  });

  it("redoing a Reset clears the localStorage key, not writes an empty object", () => {
    const regions = { title: BOX_A };
    useReviewStore.setState({ customRegions: { [DRAWING]: regions } });

    applyHistoryEntry({
      kind: "zone/bulk", label: "Reset zone alignment", drawingId: DRAWING,
      before: regions, after: null, pinnedBefore: null, pinnedAfter: null,
    }, "redo");

    expect(useReviewStore.getState().customRegions[DRAWING]).toBeUndefined();
    expect(localStorage.getItem(`custom_regions_${DRAWING}`)).toBeNull();
  });
});

describe("violation entries", () => {
  it("restores a deleted marker and clears it from the deleted stack", () => {
    const v = violation("v1");
    useWorkspaceStore.setState({ violations: [], deletedViolationsStack: [v] });

    applyHistoryEntry({
      kind: "violation/delete", label: "Delete marker", violationId: "v1", violation: v,
    }, "undo");

    expect(useWorkspaceStore.getState().violations.map((x) => x.id)).toEqual(["v1"]);
    // Left on the deleted stack, the context menu's "Undo Delete" would restore a second copy.
    expect(useWorkspaceStore.getState().deletedViolationsStack).toHaveLength(0);
  });

  it("does not duplicate a marker the context menu already restored", () => {
    const v = violation("v1");
    useWorkspaceStore.setState({ violations: [v], deletedViolationsStack: [] });

    applyHistoryEntry({
      kind: "violation/delete", label: "Delete marker", violationId: "v1", violation: v,
    }, "undo");

    expect(useWorkspaceStore.getState().violations).toHaveLength(1);
  });

  it("redoing a delete removes the marker and puts it back on the deleted stack", () => {
    const v = violation("v1");
    useWorkspaceStore.setState({ violations: [v], deletedViolationsStack: [] });

    applyHistoryEntry({
      kind: "violation/delete", label: "Delete marker", violationId: "v1", violation: v,
    }, "redo");

    expect(useWorkspaceStore.getState().violations).toHaveLength(0);
    expect(useWorkspaceStore.getState().deletedViolationsStack.map((x) => x.id)).toEqual(["v1"]);
  });

  it("moves a marker back to its original coordinates", () => {
    useWorkspaceStore.setState({
      violations: [{ ...violation("v1"), coordinates: [99, 99] } as ViolationItem],
    });

    applyHistoryEntry({
      kind: "violation/move", label: "Move marker", violationId: "v1",
      before: { coordinates: [10, 20] }, after: { coordinates: [99, 99] },
    }, "undo");

    expect(useWorkspaceStore.getState().violations[0].coordinates).toEqual([10, 20]);
  });
});

describe("popAndRestoreViolation coupling", () => {
  it("drops the matching history entry so Ctrl+Z cannot restore the marker twice", () => {
    const v = violation("v1");
    useWorkspaceStore.setState({ violations: [], deletedViolationsStack: [v] });
    useHistoryStore.getState().record({
      kind: "violation/delete", label: "Delete marker", violationId: "v1", violation: v,
    });

    useWorkspaceStore.getState().popAndRestoreViolation();
    expect(useWorkspaceStore.getState().violations).toHaveLength(1);

    // The deletion is no longer in history, so undo finds nothing to do.
    expect(useHistoryStore.getState().past).toHaveLength(0);
    expect(performUndo()).toBeNull();
    expect(useWorkspaceStore.getState().violations).toHaveLength(1);
  });
});

describe("grouped actions (one click across two panes)", () => {
  /** What the Reset button records: one entry per pane, both halves of one click. */
  function resetEntries(): HistoryEntry[] {
    return [DRAWING, DRAWING_B].map((id) => ({
      kind: "zone/bulk",
      label: "Reset zone alignment",
      drawingId: id,
      before: { title: BOX_A },
      after: null,
      pinnedBefore: null,
      pinnedAfter: null,
    }));
  }

  it("stamps one shared group id across the entries", () => {
    recordHistoryGroup(resetEntries());
    const { past } = useHistoryStore.getState();

    expect(past).toHaveLength(2);
    expect(past[0].groupId).toBeDefined();
    expect(past[0].groupId).toBe(past[1].groupId);
  });

  it("leaves a lone entry ungrouped", () => {
    // A drag gesture affects one pane. Nothing to group, and no marker to carry.
    recordHistoryGroup([resetEntries()[0]]);
    expect(useHistoryStore.getState().past[0].groupId).toBeUndefined();
  });

  it("does not collide group ids between two separate clicks", () => {
    recordHistoryGroup(resetEntries());
    recordHistoryGroup(resetEntries());
    const { past } = useHistoryStore.getState();
    // Four entries, two actions. A shared id across the pair would make one Ctrl+Z undo both
    // clicks — the opposite failure to the one being fixed.
    expect(past[0].groupId).toBe(past[1].groupId);
    expect(past[2].groupId).toBe(past[3].groupId);
    expect(past[0].groupId).not.toBe(past[2].groupId);
  });

  it("undoes BOTH panes on a single Ctrl+Z, and redoes both", () => {
    // The bug this exists for: Reset cleared both panes, the first undo restored only the
    // reference, and the revision stayed empty. That reads as undo being broken.
    useReviewStore.setState({
      customRegions: { [DRAWING]: { title: BOX_A }, [DRAWING_B]: { title: BOX_A } },
    });
    recordHistoryGroup(resetEntries());
    useReviewStore.getState().resetCustomRegions(DRAWING);
    useReviewStore.getState().resetCustomRegions(DRAWING_B);

    performUndo();

    expect(useReviewStore.getState().customRegions[DRAWING]).toMatchObject({ title: BOX_A });
    expect(useReviewStore.getState().customRegions[DRAWING_B]).toMatchObject({ title: BOX_A });
    expect(useHistoryStore.getState().past).toHaveLength(0);

    performRedo();

    expect(useReviewStore.getState().customRegions[DRAWING]).toBeUndefined();
    expect(useReviewStore.getState().customRegions[DRAWING_B]).toBeUndefined();
    expect(useHistoryStore.getState().future).toHaveLength(0);
  });

  it("stops at the group boundary instead of swallowing the edit before it", () => {
    useReviewStore.getState().updateCustomRegion(DRAWING, "bom", BOX_B);
    useHistoryStore.getState().record({
      kind: "zone/update", label: "Edit zone box", drawingId: DRAWING, zoneKey: "bom",
      before: BOX_A, after: BOX_B,
    });
    recordHistoryGroup(resetEntries());

    performUndo();

    // The ungrouped edit that preceded the click is still there — draining a group must not
    // run past its own members. (Its geometry is gone, but only because restoring a whole
    // drawing's alignment legitimately replaces every zone on it; the ENTRY is what matters.)
    expect(useHistoryStore.getState().past).toHaveLength(1);
    expect(useHistoryStore.getState().past[0].label).toBe("Edit zone box");

    // Still reachable by a second press, which is the point of not swallowing it.
    performUndo();
    expect(useReviewStore.getState().getRegionsFor(DRAWING).bom).toMatchObject(BOX_A);
  });

  it("discards the rest of a group torn in half by the size cap", () => {
    // The group goes in first, then enough later edits to push its oldest member off the end.
    // Dropping only that member would leave the other to undo one pane on its own — a state
    // the user never saw, reachable only by holding Ctrl+Z long enough.
    recordHistoryGroup(resetEntries());
    for (let i = 0; i < MAX_HISTORY - 1; i += 1) {
      useHistoryStore.getState().record({
        kind: "zone/update", label: `edit ${i}`, drawingId: DRAWING, zoneKey: `zone-${i}`,
        before: BOX_A, after: BOX_B,
      });
    }

    const { past } = useHistoryStore.getState();
    expect(past.some((e) => e.groupId)).toBe(false);
    expect(past).toHaveLength(MAX_HISTORY - 1);
  });
});

describe("performUndo / performRedo round trip", () => {
  it("walks a zone edit back and forward through the stack", () => {
    useReviewStore.getState().updateCustomRegion(DRAWING, "title", BOX_A);
    useReviewStore.getState().updateCustomRegion(DRAWING, "title", BOX_B);
    useHistoryStore.getState().record({
      kind: "zone/update", label: "Edit zone box", drawingId: DRAWING, zoneKey: "title",
      before: BOX_A, after: BOX_B,
    });

    performUndo();
    expect(useReviewStore.getState().getRegionsFor(DRAWING).title).toMatchObject(BOX_A);

    performRedo();
    expect(useReviewStore.getState().getRegionsFor(DRAWING).title).toMatchObject(BOX_B);

    // Redo stack is drained; a second redo is a no-op rather than a repeat.
    expect(performRedo()).toBeNull();
    expect(useReviewStore.getState().getRegionsFor(DRAWING).title).toMatchObject(BOX_B);
  });
});
