/**
 * Tests for the saved-templates modal's two write paths.
 *
 * Both of these were regressions of bugs already fixed *elsewhere*: this modal is the second
 * place a template is saved and applied, and neither fix reached it.
 *
 *  - Saving rebuilt each zone from a four-field literal, dropping `points` and flattening a
 *    reshaped zone to its bounding box — then wrote the flattened version straight back over
 *    the live regions. See `Gotcha - A Reshaped Zone Was Flattened by the Template Round Trip`.
 *  - Neither path recorded history, so applying a template over both panes — the same
 *    destructive reach as Reset — had no way back at all.
 *
 * Driven through the DOM rather than by calling the handlers, because the defect in both cases
 * was in the call site, not in the helpers it should have been calling. A test that invoked
 * `zonesToTemplatePayload` directly would have passed against the broken code.
 */
import { render, screen, waitFor } from "@testing-library/react";
import { fireEvent } from "@testing-library/dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SavedTemplatesModal } from "./SavedTemplatesModal";
import { useHistoryStore } from "../../stores/historyStore";
import { useReviewStore } from "../../stores/reviewStore";
import { useWorkspaceStore } from "../../stores/workspaceStore";
import { performUndo } from "../../hooks/useUndoRedo";
import { saveZoneTemplate } from "../../services/drawingsApi";

// `zoneSignature` and `ZONE_KEYS` stay real — the signature decides whether the save button is
// even enabled, and the key list is what filters non-zone keys out of the payload.
vi.mock("../../services/drawingsApi", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../services/drawingsApi")>();
  return {
    ...actual,
    fetchAllZoneTemplates: vi.fn(async () => []),
    saveZoneTemplate: vi.fn(async () => undefined),
    deleteZoneTemplate: vi.fn(async () => undefined),
    setDefaultZoneTemplate: vi.fn(async () => undefined),
  };
});

const OLD_ID = "drawing-old";
const NEW_ID = "drawing-new";

/** A reshaped zone: five vertices, with a notch cut out of the bottom edge. */
const RESHAPED = {
  xMin: 0.1,
  xMax: 0.4,
  yMin: 0.1,
  yMax: 0.4,
  points: [
    { x: 0.1, y: 0.1 },
    { x: 0.4, y: 0.1 },
    { x: 0.4, y: 0.4 },
    { x: 0.25, y: 0.3 },
    { x: 0.1, y: 0.4 },
  ],
};

const RECTANGLE = { xMin: 0.6, xMax: 0.9, yMin: 0.6, yMax: 0.9 };

function drawing(id: string) {
  return { id, metadata: { render_bounds: [0, 0, 1414, 1000] } };
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  useHistoryStore.setState({ past: [], future: [] });
  useWorkspaceStore.setState({
    oldDrawing: drawing(OLD_ID) as never,
    newDrawing: drawing(NEW_ID) as never,
    zoneRegions: {},
  });
  useReviewStore.setState({
    customRegions: {
      [OLD_ID]: { notes: RESHAPED, title: RECTANGLE },
      [NEW_ID]: { notes: RESHAPED, title: RECTANGLE },
    },
    pinnedZoneKeys: {},
    userAlignedZoneKeys: {},
  });
});

function openModal() {
  render(<SavedTemplatesModal isOpen onClose={() => {}} />);
}

describe("saving the current alignment", () => {
  it("carries a reshaped zone's outline into the template payload", async () => {
    openModal();
    fireEvent.click(screen.getByText(/save current alignment to template/i));

    await waitFor(() => expect(saveZoneTemplate).toHaveBeenCalled());

    const [, payload] = vi.mocked(saveZoneTemplate).mock.calls[0];
    // The whole bug: an enumerated {xMin,xMax,yMin,yMax} literal here silently turned the
    // polygon back into its bounding box, and the apply below then wrote that over the live
    // regions — so the reshape disappeared at the moment of saving it.
    expect(payload.zones.notes.points).toHaveLength(5);
    expect(payload.zones.title.points).toBeUndefined();
  });

  it("does not persist non-zone keys copied in from the zones response", () => {
    useReviewStore.setState({
      customRegions: { [OLD_ID]: { title: RECTANGLE, drawing_id: "junk" } as never },
    });
    openModal();
    fireEvent.click(screen.getByText(/save current alignment to template/i));

    return waitFor(() => {
      const [, payload] = vi.mocked(saveZoneTemplate).mock.calls[0];
      // The other keys present are the second pane's DEFAULT_CUSTOM_REGIONS, which are real
      // zones and belong in the payload. `drawing_id` is the one that must not survive.
      expect(payload.zones).not.toHaveProperty("drawing_id");
      expect(Object.keys(payload.zones)).toContain("title");
    });
  });

  it("records the two panes as ONE undoable action", async () => {
    openModal();
    fireEvent.click(screen.getByText(/save current alignment to template/i));

    await waitFor(() => expect(useHistoryStore.getState().past).toHaveLength(2));

    const { past } = useHistoryStore.getState();
    expect(past[0].groupId).toBe(past[1].groupId);
    expect(past[0].groupId).toBeDefined();

    // One press takes BOTH panes back. Recording inside the loop left the reference restored
    // and the revision stamped, which is the state that reads as undo being broken.
    performUndo();
    expect(useReviewStore.getState().customRegions[OLD_ID].notes).toMatchObject(RESHAPED);
    expect(useReviewStore.getState().customRegions[NEW_ID].notes).toMatchObject(RESHAPED);
    expect(useHistoryStore.getState().past).toHaveLength(0);
  });
});

describe("applying a saved template", () => {
  it("is undoable at all, and in one press", async () => {
    vi.mocked(
      (await import("../../services/drawingsApi")).fetchAllZoneTemplates,
    ).mockResolvedValue([
      { signature: "aspect-1.414", name: "A3 Standard", zones: { title: RECTANGLE } } as never,
    ]);

    openModal();
    const applyBtn = await screen.findByTitle(/apply/i);
    fireEvent.click(applyBtn);

    await waitFor(() => expect(useHistoryStore.getState().past).toHaveLength(2));
    expect(useHistoryStore.getState().past[0].groupId).toBe(
      useHistoryStore.getState().past[1].groupId,
    );

    performUndo();
    // The template stamped `title` over both panes and dropped the reshape; undo brings the
    // user's own alignment back on both sides.
    expect(useReviewStore.getState().customRegions[OLD_ID].notes).toMatchObject(RESHAPED);
    expect(useReviewStore.getState().customRegions[NEW_ID].notes).toMatchObject(RESHAPED);
  });
});
