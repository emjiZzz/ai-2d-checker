import { StateCreator } from "zustand";
import { WorkspaceState, NavSlice } from "../types";
import { useReviewStore } from "../../reviewStore";
import { useHistoryStore } from "../../historyStore";

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
    // Entries reference drawings and zones that no longer exist here. Replaying one after a
    // reset would write a stale box back onto whatever drawing next takes that id.
    useHistoryStore.getState().clear();
    set({
      oldDrawing: null,
      newDrawing: null,
      isComparing: false,
      auditStatus: "idle",
      complianceScore: null,
      violations: [],
      deletedViolationsStack: [],
      selectedViolation: null,
      auditError: null,
    });
  },
});
