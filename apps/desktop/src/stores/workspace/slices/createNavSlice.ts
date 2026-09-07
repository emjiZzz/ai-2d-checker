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

      // Manual check. Absent here until 2026-08-20, and the omission was not cosmetic: this runs
      // from `roomStore.leaveRoom`, so room A's session id and markings survived into room B.
      // Until B's own session resolved, B's canvas rendered A's badges, and `findMarkingForEntity`
      // — which matches on handle and side, not on drawing — refused to let the engineer mark any
      // entity of B's whose handle collided with one of A's, with no explanation on screen.
      //
      // `markings` is safe to drop because it is a mirror, never the record: every marking was
      // written through to the server before it was added here, and `startManualSession` reloads
      // the list from `listMarkings` on the way in.
      manualSessionId: null,
      manualSessionStatus: null,
      manualSessionPair: null,
      manualSessionError: null,
      markingError: null,
      markings: [],
      pendingPairRef: null,
      pendingPairTool: "changed",
      selectedEntities: [],
      selectionLocator: null,
      selectionMenu: null,
      selectionCounterpart: null,
      hoverLocator: null,
      hoveredEntityId: null,
    });
  },
});
