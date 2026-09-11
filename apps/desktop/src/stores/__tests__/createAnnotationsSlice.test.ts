import { describe, it, expect, beforeEach, vi } from "vitest";
import { useWorkspaceStore } from "../workspaceStore";
import { useReviewStore } from "../reviewStore";
import * as annotationsApi from "../../services/annotationsApi";

vi.mock("../../services/annotationsApi", () => ({
  fetchAnnotations: vi.fn(),
  createAnnotation: vi.fn(),
  updateAnnotation: vi.fn(),
  deleteAnnotation: vi.fn(),
}));

describe("createAnnotationsSlice", () => {
  beforeEach(() => {
    useWorkspaceStore.setState({
      annotations: [],
      selectedAnnotationId: null,
      isPlacingAnnotation: false,
      pendingAnnotationText: "Check hole callout",
      pendingAnnotationSeverity: "high",
    });
    useReviewStore.setState({
      selectedViolationId: "v-100",
    });
    vi.clearAllMocks();
  });

  it("createAnnotationAt derives severity, pen_type and attaches active violation_id", async () => {
    const mockAnnotation = {
      id: "ann-1",
      review_session_id: "drawing-1",
      drawing_id: "drawing-1",
      author_id: "checker_user",
      annotation_type: "pin",
      content: "Check hole callout",
      severity: "high" as const,
      coordinates: [100, 200] as [number, number],
      target_entity_ids: [],
      violation_id: "v-100",
      status: "open",
      pen_type: "warning_orange" as const,
      created_at: "2026-07-24T00:00:00Z",
      updated_at: "2026-07-24T00:00:00Z",
    };

    vi.mocked(annotationsApi.createAnnotation).mockResolvedValue(mockAnnotation);

    await useWorkspaceStore.getState().createAnnotationAt([100, 200], "Check hole callout", "drawing-1");

    expect(annotationsApi.createAnnotation).toHaveBeenCalledWith({
      review_session_id: "drawing-1",
      drawing_id: "drawing-1",
      content: "Check hole callout",
      coordinates: [100, 200],
      severity: "high",
      pen_type: "warning_orange",
      violation_id: "v-100",
    });

    const state = useWorkspaceStore.getState();
    expect(state.annotations).toHaveLength(1);
    expect(state.annotations[0].id).toBe("ann-1");
    expect(state.selectedAnnotationId).toBe("ann-1");
  });

  it("createAnnotationAt optimistically places pin before server responds and swaps ID on success", async () => {
    let resolveCreate: (val: any) => void;
    const createPromise = new Promise((resolve) => {
      resolveCreate = resolve;
    });
    vi.mocked(annotationsApi.createAnnotation).mockReturnValue(createPromise as any);

    const promise = useWorkspaceStore.getState().createAnnotationAt([50, 60], "Optimistic pin", "drawing-1");

    // Immediately placed in state with 0ms UI delay
    const stateBefore = useWorkspaceStore.getState();
    expect(stateBefore.annotations).toHaveLength(1);
    expect(stateBefore.annotations[0].id).toMatch(/^optimistic_ann_/);
    expect(stateBefore.annotations[0].content).toBe("Optimistic pin");
    expect(stateBefore.selectedAnnotationId).toMatch(/^optimistic_ann_/);

    // Resolve server call
    resolveCreate!({
      id: "ann-server-123",
      review_session_id: "drawing-1",
      drawing_id: "drawing-1",
      content: "Optimistic pin",
      coordinates: [50, 60],
      severity: "high",
      pen_type: "warning_orange",
      violation_id: "v-100",
      status: "open",
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });
    await promise;

    const stateAfter = useWorkspaceStore.getState();
    expect(stateAfter.annotations[0].id).toBe("ann-server-123");
    expect(stateAfter.selectedAnnotationId).toBe("ann-server-123");
  });

  it("deleteAnnotationById optimistically removes pin immediately and rolls back on failure", async () => {
    const existing = {
      id: "ann-to-delete",
      review_session_id: "drawing-1",
      drawing_id: "drawing-1",
      author_id: "checker_user",
      annotation_type: "pin",
      content: "Do not lose me",
      severity: "info" as const,
      coordinates: [10, 20] as [number, number],
      target_entity_ids: [],
      violation_id: null,
      status: "open",
      pen_type: "checker_blue" as const,
      created_at: "2026-07-24T00:00:00Z",
      updated_at: "2026-07-24T00:00:00Z",
    };
    useWorkspaceStore.setState({ annotations: [existing] });

    let rejectDelete: (err: any) => void;
    const deletePromise = new Promise((_, reject) => {
      rejectDelete = reject;
    });
    vi.mocked(annotationsApi.deleteAnnotation).mockReturnValue(deletePromise as any);

    const promise = useWorkspaceStore.getState().deleteAnnotationById("ann-to-delete");

    // Removed immediately from UI
    expect(useWorkspaceStore.getState().annotations).toHaveLength(0);

    // Network fails
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    rejectDelete!(new Error("Network disconnect"));
    await promise;

    // Rollback restored the pin
    expect(useWorkspaceStore.getState().annotations).toHaveLength(1);
    expect(useWorkspaceStore.getState().annotations[0].id).toBe("ann-to-delete");
    consoleSpy.mockRestore();
  });

  it("updateAnnotationDetails updates store state and calls updateAnnotation API", async () => {
    const initialAnnotation = {
      id: "ann-1",
      review_session_id: "drawing-1",
      drawing_id: "drawing-1",
      author_id: "checker_user",
      annotation_type: "pin",
      content: "Original text",
      severity: "info" as const,
      coordinates: [10, 20] as [number, number],
      target_entity_ids: [],
      violation_id: null,
      status: "open",
      pen_type: "checker_blue" as const,
      created_at: "2026-07-24T00:00:00Z",
      updated_at: "2026-07-24T00:00:00Z",
    };

    useWorkspaceStore.setState({ annotations: [initialAnnotation] });

    const updatedAnnotation = {
      ...initialAnnotation,
      content: "Edited text",
      severity: "critical" as const,
      pen_type: "alert_red" as const,
    };

    vi.mocked(annotationsApi.updateAnnotation).mockResolvedValue(updatedAnnotation);

    await useWorkspaceStore.getState().updateAnnotationDetails("ann-1", {
      content: "Edited text",
      severity: "critical",
      pen_type: "alert_red",
    });

    expect(annotationsApi.updateAnnotation).toHaveBeenCalledWith("ann-1", {
      content: "Edited text",
      severity: "critical",
      pen_type: "alert_red",
    });

    const state = useWorkspaceStore.getState();
    expect(state.annotations[0].content).toBe("Edited text");
    expect(state.annotations[0].severity).toBe("critical");
  });

  it("updateAnnotationStatus delegates to updateAnnotationDetails", async () => {
    const initialAnnotation = {
      id: "ann-1",
      review_session_id: "drawing-1",
      drawing_id: "drawing-1",
      author_id: "checker_user",
      annotation_type: "pin",
      content: "Original text",
      severity: "info" as const,
      coordinates: [10, 20] as [number, number],
      target_entity_ids: [],
      violation_id: null,
      status: "open",
      pen_type: "checker_blue" as const,
      created_at: "2026-07-24T00:00:00Z",
      updated_at: "2026-07-24T00:00:00Z",
    };

    useWorkspaceStore.setState({ annotations: [initialAnnotation] });

    const resolvedAnnotation = { ...initialAnnotation, status: "resolved" };
    vi.mocked(annotationsApi.updateAnnotation).mockResolvedValue(resolvedAnnotation);

    await useWorkspaceStore.getState().updateAnnotationStatus("ann-1", "resolved");

    expect(annotationsApi.updateAnnotation).toHaveBeenCalledWith("ann-1", { status: "resolved" });
    expect(useWorkspaceStore.getState().annotations[0].status).toBe("resolved");
  });

  it("handles API failure gracefully during updateAnnotationDetails", async () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    vi.mocked(annotationsApi.updateAnnotation).mockRejectedValue(new Error("Network failure"));

    await useWorkspaceStore.getState().updateAnnotationDetails("ann-999", { status: "resolved" });

    expect(consoleSpy).toHaveBeenCalledWith(
      "Failed to update annotation ann-999:",
      "Network failure"
    );
    consoleSpy.mockRestore();
  });

  describe("Freehand Pen Tool", () => {
    it("adds pen strokes to store and allows undoing and clearing", () => {
      const store = useWorkspaceStore.getState();
      store.setIsPenActive(true);
      expect(useWorkspaceStore.getState().isPenActive).toBe(true);

      store.addPenStroke({
        drawingId: "dwg-1",
        points: [
          [10, 20],
          [15, 25],
          [20, 30],
        ],
        color: "#ff2850",
        width: 2.5,
      });

      store.addPenStroke({
        drawingId: "dwg-1",
        points: [
          [50, 60],
          [55, 65],
        ],
        color: "#00e5ff",
        width: 1.5,
      });

      store.addPenStroke({
        drawingId: "dwg-2",
        points: [[100, 100], [110, 110]],
        color: "#10b981",
        width: 4.0,
      });

      let state = useWorkspaceStore.getState();
      expect(state.penStrokes).toHaveLength(3);
      expect(state.penStrokes[0].drawingId).toBe("dwg-1");
      expect(state.penStrokes[0].points).toHaveLength(3);

      // Undo last stroke for dwg-1
      store.undoLastPenStroke("dwg-1");
      state = useWorkspaceStore.getState();
      expect(state.penStrokes).toHaveLength(2);
      expect(state.penStrokes.map((s) => s.drawingId)).toEqual(["dwg-1", "dwg-2"]);

      // Clear all strokes for dwg-1
      store.clearPenStrokes("dwg-1");
      state = useWorkspaceStore.getState();
      expect(state.penStrokes).toHaveLength(1);
      expect(state.penStrokes[0].drawingId).toBe("dwg-2");

      // Clear all strokes globally
      store.clearPenStrokes();
      expect(useWorkspaceStore.getState().penStrokes).toHaveLength(0);
    });
  });
});
