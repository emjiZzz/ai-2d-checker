import { StateCreator } from "zustand";
import { WorkspaceState, NavSlice } from "../types";
import { useReviewStore } from "../../reviewStore";

export const createNavSlice: StateCreator<WorkspaceState, [], [], NavSlice> = (set, get) => ({
  currentNav: "workspace",
  hasHydrated: false,
  setCurrentNav: (nav) => set({ currentNav: nav }),
  setHasHydrated: (state) => set({ hasHydrated: state }),

  resetWorkspace: () => {
    // Clear uploads
    get().clearUpload("old");
    get().clearUpload("new");
    useReviewStore.getState().resetCustomRegions();
    set({
      oldDrawing: null,
      newDrawing: null,
      isComparing: false,
      auditStatus: "idle",
      complianceScore: null,
      violations: [],
      deletedViolationsStack: [],
      undoStack: [],
      selectedViolation: null,
      auditError: null,
    });
  },
});
