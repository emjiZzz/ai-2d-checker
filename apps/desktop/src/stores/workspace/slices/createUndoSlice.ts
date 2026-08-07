import { StateCreator } from "zustand";
import { WorkspaceState, UndoSlice } from "../types";
import { useHistoryStore } from "../../historyStore";

/**
 * The "Undo Delete" context-menu affordance: a stack of deleted markers, newest first.
 *
 * This is NOT the general undo stack any more. Ctrl+Z / Ctrl+Y run off `historyStore`, which
 * covers zone alignment as well as markers and supports redo. What survives here is the one
 * thing that history does not express: a menu item that restores the last deleted marker
 * specifically, independent of whatever else the user has done since.
 *
 * The two are kept consistent at their two points of contact — `applyHistoryEntry` filters a
 * restored marker out of this stack, and `popAndRestoreViolation` below drops the matching
 * history entry — so a deletion can be walked back by either route without the marker coming
 * back twice.
 */
export const createUndoSlice: StateCreator<WorkspaceState, [], [], UndoSlice> = (set, get) => ({
  deletedViolationsStack: [],

  pushDeletedViolation: (v) => set((state) => ({
    deletedViolationsStack: [...state.deletedViolationsStack, v],
  })),

  popAndRestoreViolation: () => {
    const stack = get().deletedViolationsStack;
    if (stack.length === 0) return;
    const last = stack[stack.length - 1];
    set({
      deletedViolationsStack: stack.slice(0, -1),
      violations: [...get().violations, last],
    });
    // Drop this deletion from the keyboard history too. Leaving it would let a later Ctrl+Z
    // "undo" a delete that the menu has already undone, adding a second copy of the marker.
    useHistoryStore.setState((s) => ({
      past: s.past.filter(
        (entry) => !(entry.kind === "violation/delete" && entry.violationId === last.id),
      ),
      future: s.future.filter(
        (entry) => !(entry.kind === "violation/delete" && entry.violationId === last.id),
      ),
    }));
  },
});
