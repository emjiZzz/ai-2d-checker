import { StateCreator } from "zustand";
import { WorkspaceState, UndoSlice, UndoAction } from "../types";

export const createUndoSlice: StateCreator<WorkspaceState, [], [], UndoSlice> = (set, get) => ({
  deletedViolationsStack: [],
  undoStack: [],

  pushDeletedViolation: (v) => set((state) => {
    const action: UndoAction = {
      type: "delete",
      violationId: v.id,
      violation: v
    };
    return {
      deletedViolationsStack: [...state.deletedViolationsStack, v],
      undoStack: [...state.undoStack, action]
    };
  }),

  popAndRestoreViolation: () => {
    const stack = get().deletedViolationsStack;
    if (stack.length === 0) return;
    const last = stack[stack.length - 1];
    set({
      deletedViolationsStack: stack.slice(0, -1),
      violations: [...get().violations, last],
      undoStack: get().undoStack.filter(act => !(act.type === "delete" && act.violationId === last.id))
    });
  },

  pushUndoAction: (action) => set((state) => ({
    undoStack: [...state.undoStack, action]
  })),

  undoLastAction: () => {
    const stack = get().undoStack;
    if (stack.length === 0) return;
    const last = stack[stack.length - 1];
    const newStack = stack.slice(0, -1);
    
    if (last.type === "delete" && last.violation) {
      set({
        undoStack: newStack,
        violations: [...get().violations, last.violation],
        deletedViolationsStack: get().deletedViolationsStack.filter(v => v.id !== last.violationId)
      });
    } else if (last.type === "move") {
      set({
        undoStack: newStack,
        violations: get().violations.map(v => {
          if (v.id === last.violationId) {
            const updated = { ...v };
            if (last.oldCoords) updated.coordinates = last.oldCoords;
            if (last.oldRefCoords) updated.ref_coordinates = last.oldRefCoords;
            return updated;
          }
          return v;
        })
      });
    }
  },
});
