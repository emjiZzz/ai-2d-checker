import { create } from "zustand";
import * as idbKeyval from "idb-keyval";
import { WorkspaceState } from "./workspace/types";
import { createComparisonSlice } from "./workspace/slices/createComparisonSlice";
import { createUploadSlice } from "./workspace/slices/createUploadSlice";
import { createAuditSlice } from "./workspace/slices/createAuditSlice";
import { createClientSlice } from "./workspace/slices/createClientSlice";
import { createUndoSlice } from "./workspace/slices/createUndoSlice";
import { createNavSlice } from "./workspace/slices/createNavSlice";
import { createAnnotationsSlice } from "./workspace/slices/createAnnotationsSlice";
import { createManualCheckSlice } from "./workspace/slices/createManualCheckSlice";
import { useHistoryStore } from "./historyStore";

// Re-export types so we don't break existing imports
export type {
  DrawingItem,
  ViolationItem,
  UploadState,
  QueueEntry,
  ClientItem,
} from "./workspace/types";

// Custom storage engine for idb-keyval
const idbStorage = {
  getItem: async (name: string): Promise<string | null> => {
    return (await idbKeyval.get(name)) || null;
  },
  setItem: async (name: string, value: string): Promise<void> => {
    await idbKeyval.set(name, value);
  },
  removeItem: async (name: string): Promise<void> => {
    await idbKeyval.del(name);
  },
};

export const useWorkspaceStore = create<WorkspaceState>()(
  (set, get, store) => ({
    ...createComparisonSlice(set, get, store),
    ...createUploadSlice(set, get, store),
    ...createAuditSlice(set, get, store),
    ...createClientSlice(set, get, store),
    ...createUndoSlice(set, get, store),
    ...createNavSlice(set, get, store),
    ...createAnnotationsSlice(set, get, store),
    ...createManualCheckSlice(set, get, store),
  })
);

export const saveWorkspaceState = async (roomId: string): Promise<void> => {
  const state = useWorkspaceStore.getState();
  const partial = {
    oldDrawing: state.oldDrawing,
    newDrawing: state.newDrawing,
    violations: state.violations,
    complianceScore: state.complianceScore,
    panX: state.panX,
    panY: state.panY,
    zoom: state.zoom,
    activeLayers: state.activeLayers,
  };
  await idbStorage.setItem(`workspace-${roomId}`, JSON.stringify(partial));
};

export const loadWorkspaceState = async (roomId: string): Promise<void> => {
  // Undo history belongs to the room being left, not the one being opened. Its entries name
  // drawing ids and zone keys from that room, so replaying one here would write a box onto an
  // unrelated drawing. Cleared before the swap so it cannot outlive it on any path — the
  // success branch below does not go through resetWorkspace.
  useHistoryStore.getState().clear();

  const data = await idbStorage.getItem(`workspace-${roomId}`);

  if (data) {
    try {
      const partial = JSON.parse(data);
      useWorkspaceStore.setState({
        ...partial,
        annotations: [],
        manualSessionPair: null,
        manualSessionId: null,
        hasHydrated: true,
      });
      
      const state = useWorkspaceStore.getState();
      if (state.oldDrawing) {
        state.fetchLayers(state.oldDrawing.id, "old");
        state.fetchAnnotations(state.oldDrawing.id);
      }
      if (state.newDrawing) {
        state.fetchLayers(state.newDrawing.id, "new");
        state.fetchAnnotations(state.newDrawing.id);
      }
      state.recalculateCompatibility();
    } catch (err) {
      console.warn("Failed to parse workspace state for room", roomId, err);
      useWorkspaceStore.getState().resetWorkspace();
      useWorkspaceStore.setState({ hasHydrated: true });
    }
  } else {
    useWorkspaceStore.getState().resetWorkspace();
    useWorkspaceStore.setState({ hasHydrated: true });
  }
};
