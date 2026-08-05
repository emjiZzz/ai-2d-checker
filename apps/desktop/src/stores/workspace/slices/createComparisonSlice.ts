import { StateCreator } from "zustand";
import { WorkspaceState, ComparisonSlice } from "../types";
import { useReviewStore } from "../../reviewStore";
import { buildHeaders, baseUrl, parseOrThrow } from "../../../services/fetchUtils";
import { fetchDrawingZones } from "../../../services/drawingsApi";

export const createComparisonSlice: StateCreator<WorkspaceState, [], [], ComparisonSlice> = (set, get) => ({
  oldDrawing: null,
  newDrawing: null,
  oldLayers: {},
  newLayers: {},
  isComparing: false,
  panX: 0,
  panY: 0,
  zoom: 1,
  syncViewport: true,
  activeLayers: { "0": true, "Format": true, "Text": true, "Dimensions": true },
  
  aiScanProgress: "idle",
  aiScanProgressPct: 0,
  aiChecklistResults: {},
  aiScanError: null,

  setAiScanProgress: (progress) => set({ aiScanProgress: progress }),
  setAiScanProgressPct: (pct) => set({ aiScanProgressPct: pct }),
  setAiChecklistResults: (results) => set({ aiChecklistResults: results }),
  setAiScanError: (error) => set({ aiScanError: error }),

  zoneRegions: {},
  zoneErrors: {},

  fetchZoneRegions: async (drawingId) => {
    // Cached per drawing id and never refetched within a session — zone detection is a
    // pure function of the drawing's entities, which don't change without a re-parse
    // (and a re-parse means a new drawing id).
    if (get().zoneRegions[drawingId]) return;
    try {
      const zones = await fetchDrawingZones(drawingId);
      set((s) => ({
        zoneRegions: { ...s.zoneRegions, [drawingId]: zones },
        zoneErrors: Object.fromEntries(
          Object.entries(s.zoneErrors).filter(([id]) => id !== drawingId),
        ),
      }));
    } catch (err) {
      // Surfaced as a canvas notice rather than swallowed. The backend's message is the
      // useful part (e.g. entities not yet extracted); a generic string would defeat the
      // purpose of a debugging overlay.
      set((s) => ({
        zoneErrors: {
          ...s.zoneErrors,
          [drawingId]: err instanceof Error ? err.message : String(err),
        },
      }));
    }
  },

  setOldDrawing: (drawing) => {
    // Clear stale geometry synchronously in the same set() as the metadata swap
    // so React batches them into one render — otherwise the canvas briefly
    // shows the PREVIOUS old-side drawing's CAD entities under the new
    // drawing's file name until the async fetchLayers() below resolves.
    set({ oldDrawing: drawing, oldLayers: {} });
    get().recalculateCompatibility();
    if (drawing) {
      // Zone boxes are per drawing, so both sides load their own saved alignment — same
      // reasoning as annotations below. This was previously guarded by `if (!newDrawing)`,
      // which was harmless while customRegions was a single shared set but silently dropped
      // the reference pane's alignment once each drawing kept its own.
      useReviewStore.getState().loadCustomRegions(drawing.id);
      // Annotations are per-drawing and each pane renders its own, so both
      // sides are fetched regardless of which is "primary".
      get().fetchAnnotations(drawing.id);
      get().fetchLayers(drawing.id, "old");
    }
  },

  setNewDrawing: (drawing) => {
    set({ newDrawing: drawing, newLayers: {} });
    get().recalculateCompatibility();
    if (drawing) {
      useReviewStore.getState().loadCustomRegions(drawing.id);
      get().fetchAnnotations(drawing.id);
      get().fetchLayers(drawing.id, "new");
    } else {
      useReviewStore.getState().loadCustomRegions(null);
    }
  },

  fetchLayers: async (drawingId, side) => {
    // Was a hand-rolled fetch() that only sent Authorization, never
    // X-Session-Token — silently 401'd against the session-authenticated
    // layers endpoint, leaving oldLayers/newLayers stuck at {} with no error
    // surfaced anywhere (drawing metadata + violation markers still render,
    // since those come from persisted state / other endpoints, but the
    // actual CAD geometry never loads). Migrated to fetchUtils.
    try {
      const res = await fetch(`${baseUrl()}/api/v1/drawings/${drawingId}/layers`, { headers: buildHeaders() });
      const data = await parseOrThrow<{ layers: Record<string, any[]> }>(res);
      if (data?.layers) {
        if (side === "old") {
          set({ oldLayers: data.layers });
        } else {
          set({ newLayers: data.layers });
        }
      }
    } catch (err: any) {
      console.error(`Failed to fetch layers for ${side} drawing (${drawingId}):`, err.message);
    }
  },

  setViewport: (panX, panY, zoom) => {
    if (get().syncViewport) {
      set({ panX, panY, zoom });
    }
  },

  setSyncViewport: (sync) => set({ syncViewport: sync }),

  toggleLayer: (layerName) => {
    set((state) => ({
      activeLayers: {
        ...state.activeLayers,
        [layerName]: !state.activeLayers[layerName],
      },
    }));
  },
});
