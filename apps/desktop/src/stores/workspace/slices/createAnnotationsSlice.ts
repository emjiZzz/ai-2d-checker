import { StateCreator } from "zustand";
import { WorkspaceState, AnnotationsSlice, SEVERITY_PEN_MAP, PenStroke } from "../types";
import { useRoomStore } from "../../roomStore";
import { useReviewStore } from "../../reviewStore";
import { recordHistory } from "../../historyStore";
import {
  fetchAnnotations as fetchAnnotationsApi,
  createAnnotation as createAnnotationApi,
  updateAnnotation as updateAnnotationApi,
  deleteAnnotation as deleteAnnotationApi,
} from "../../../services/annotationsApi";
import { reopenSession } from "../../../services/groundTruthApi";

export const createAnnotationsSlice: StateCreator<WorkspaceState, [], [], AnnotationsSlice> = (set, get) => ({
  annotations: [],
  selectedAnnotationId: null,
  isPlacingAnnotation: false,
  pendingAnnotationText: "",
  pendingAnnotationSeverity: "info",

  // Freehand Pen Tool
  penStrokes: [],
  isPenActive: false,
  penColor: "#ff2850", // High-contrast red default
  penWidth: 2.5,

  addPenStroke: (stroke) => {
    const id = `stroke_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
    const newStroke: PenStroke = {
      ...stroke,
      id,
      createdAt: new Date().toISOString(),
    };
    set((state) => ({
      penStrokes: [...state.penStrokes, newStroke],
    }));
    recordHistory({
      kind: 'pen/stroke',
      label: 'Draw pen stroke',
      drawingId: stroke.drawingId,
      stroke: newStroke,
    });
  },

  removePenStroke: (id) => {
    set((state) => ({
      penStrokes: state.penStrokes.filter((s) => s.id !== id),
    }));
  },

  undoLastPenStroke: (drawingId) => {
    set((state) => {
      if (!state.penStrokes.length) return state;
      if (drawingId) {
        const matching = state.penStrokes.filter((s) => s.drawingId === drawingId);
        if (!matching.length) return state;
        const lastId = matching[matching.length - 1].id;
        return { penStrokes: state.penStrokes.filter((s) => s.id !== lastId) };
      }
      return { penStrokes: state.penStrokes.slice(0, -1) };
    });
  },

  clearPenStrokes: (drawingId) => {
    const current = get().penStrokes;
    const strokesToClear = drawingId
      ? current.filter((s) => s.drawingId === drawingId)
      : current;
    if (strokesToClear.length > 0) {
      recordHistory({
        kind: 'pen/clear',
        label: 'Clear pen markings',
        drawingId: drawingId || '',
        strokes: strokesToClear,
      });
    }
    set((state) => ({
      penStrokes: drawingId
        ? state.penStrokes.filter((s) => s.drawingId !== drawingId)
        : [],
    }));
  },

  setIsPenActive: (active) => set({ isPenActive: active }),
  setPenColor: (color) => set({ penColor: color }),
  setPenWidth: (width) => set({ penWidth: width }),

  // Both panes hold annotations in this one array, so a fetch for one drawing
  // must replace only that drawing's entries — otherwise loading the second
  // pane would wipe the first pane's pins.
  fetchAnnotations: async (drawingId) => {
    try {
      const items = await fetchAnnotationsApi(drawingId);
      set((state) => ({
        annotations: [...state.annotations.filter((a) => a.drawing_id !== drawingId), ...items],
      }));
    } catch (err: any) {
      console.error(`Failed to fetch annotations for drawing ${drawingId}:`, err.message);
    }
  },

  // drawingId is the canvas that was actually clicked. A pin's coordinates are
  // only meaningful in its own drawing's CAD space, so it must be attached to
  // that drawing.
  createAnnotationAt: async (coordinates, content, drawingId, severityOverride, violationIdOverride) => {
    if (!drawingId) return;

    const reviewSessionId = useRoomStore.getState().activeRoom?.id || drawingId;
    const severity = severityOverride || get().pendingAnnotationSeverity || "info";
    const penType = SEVERITY_PEN_MAP[severity] || "checker_blue";
    const violationId = violationIdOverride !== undefined ? violationIdOverride : (useReviewStore.getState().selectedViolationId || null);

    const { manualSessionId, manualSessionStatus } = get();
    const isCurrentlySubmitted = manualSessionStatus === 'completed' || manualSessionStatus === 'submitted';

    try {
      const created = await createAnnotationApi({
        review_session_id: reviewSessionId,
        drawing_id: drawingId,
        content,
        coordinates,
        severity,
        pen_type: penType,
        violation_id: violationId,
      });
      set((state) => ({
        annotations: [created, ...state.annotations],
        isPlacingAnnotation: false,
        pendingAnnotationText: "",
        selectedAnnotationId: created.id,
        manualSessionStatus: 'in_progress',
      }));
      if (isCurrentlySubmitted && manualSessionId) {
        reopenSession(manualSessionId).catch((err) => console.warn('[annotations] Reopen on annotation create warning:', err));
      }
    } catch (err: any) {
      console.error("Failed to create annotation:", err.message);
      set({ isPlacingAnnotation: false });
    }
  },

  deleteAnnotationById: async (id) => {
    const { manualSessionId, manualSessionStatus } = get();
    const isCurrentlySubmitted = manualSessionStatus === 'completed' || manualSessionStatus === 'submitted';
    try {
      await deleteAnnotationApi(id);
    } catch (err: any) {
      console.error(`Failed to delete annotation ${id}:`, err.message);
    } finally {
      set((state) => ({
        annotations: state.annotations.filter((a) => a.id !== id),
        selectedAnnotationId: state.selectedAnnotationId === id ? null : state.selectedAnnotationId,
        manualSessionStatus: 'in_progress',
      }));
      if (isCurrentlySubmitted && manualSessionId) {
        reopenSession(manualSessionId).catch((err) => console.warn('[annotations] Reopen on annotation delete warning:', err));
      }
    }
  },

  updateAnnotationDetails: async (id, updates) => {
    try {
      const updated = await updateAnnotationApi(id, updates);
      set((state) => ({
        annotations: state.annotations.map((a) => (a.id === id ? updated : a)),
      }));
    } catch (err: any) {
      console.error(`Failed to update annotation ${id}:`, err.message);
    }
  },

  updateAnnotationStatus: async (id, status) => {
    return get().updateAnnotationDetails(id, { status });
  },

  // Drag-in-progress only — mutates the pin's position in local state so
  // rendering tracks the cursor without a PATCH per mousemove frame. The
  // caller (useCanvasInteraction) persists via updateAnnotationDetails once
  // the drag ends.
  moveAnnotationLocal: (id, coordinates) => set((state) => ({
    annotations: state.annotations.map((a) => (a.id === id ? { ...a, coordinates } : a)),
  })),

  selectAnnotation: (id) => set({ selectedAnnotationId: id }),
  setIsPlacingAnnotation: (v) => set({ isPlacingAnnotation: v }),
  setPendingAnnotationText: (text) => set({ pendingAnnotationText: text }),
  setPendingAnnotationSeverity: (severity) => set({ pendingAnnotationSeverity: severity }),
});
