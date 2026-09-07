import { StateCreator } from "zustand";
import { WorkspaceState, ComparisonSlice } from "../types";
import { useReviewStore } from "../../reviewStore";
import { buildHeaders, baseUrl, parseOrThrow } from "../../../services/fetchUtils";
import { fetchDrawingZones } from "../../../services/drawingsApi";

/**
 * In-flight layer requests, keyed by drawing id.
 *
 * Module scope rather than store state: it is read and written inside one synchronous stretch of
 * `fetchLayers`, and a store field would not be visible to a second caller until React had
 * flushed — which is precisely the window the duplicate request arrives in.
 *
 * Entries are removed on settle, so this is a de-duplicator and never a cache. Layers do change
 * — `/reextract` rewrites them — and a cache here would serve stale geometry with no way to
 * invalidate it from the one place that knows.
 */
const layerRequests = new Map<string, Promise<Record<string, any[]> | null>>();

async function runLayerFetch(
  drawingId: string,
  side: string,
  set: (partial: any) => void,
): Promise<void> {
  const request = (async (): Promise<Record<string, any[]> | null> => {
    try {
      const res = await fetch(`${baseUrl()}/api/v1/drawings/${drawingId}/layers`, {
        headers: buildHeaders(),
      });
      const data = await parseOrThrow<{ layers: Record<string, any[]> }>(res);
      return data?.layers ?? null;
    } catch (err: any) {
      console.error(`Failed to fetch layers for ${side} drawing (${drawingId}):`, err.message);
      return null;
    } finally {
      // Cleared on BOTH paths. A failed request left in the map would make every later attempt
      // await a promise that already rejected, so one flaky fetch would permanently blank the
      // canvas for that drawing.
      layerRequests.delete(drawingId);
    }
  })();

  layerRequests.set(drawingId, request);
  const layers = await request;
  if (layers) set(side === "old" ? { oldLayers: layers } : { newLayers: layers });
}

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
    // ── one request per drawing, however many callers ask ────────────────────────────
    // Opening a room asks TWICE for each drawing: `loadWorkspaceState` restores the pair from
    // IndexedDB and fetches their layers, then `setDrawing` fetches them again as the server's
    // room payload lands. Measured in the backend log — the same drawing id served twice,
    // 6.59s and 5.64s, concurrently, competing for the same Mongo round trip.
    //
    // Nothing about that is wrong per caller; both genuinely need the layers. So the fix is
    // here rather than at either call site: a second ask for a drawing already in flight waits
    // on the first request instead of starting another.
    //
    // Keyed by drawing id, NOT by side. The same drawing can occupy both panes, and the payload
    // is a property of the drawing — deduplicating by side would miss exactly that case.
    const inFlight = layerRequests.get(drawingId);
    if (inFlight) {
      const layers = await inFlight;
      // The awaited request resolved into the OTHER side's slot, so this caller still has to
      // place it in its own.
      if (layers) set(side === "old" ? { oldLayers: layers } : { newLayers: layers });
      return;
    }
    return runLayerFetch(drawingId, side, set);
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
