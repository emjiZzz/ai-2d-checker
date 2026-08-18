import { StateCreator } from "zustand";
import {
  CommitStampInput,
  EntityLocator,
  ManualCheckSlice,
  PendingStamp,
  PickedEntity,
  StampTool,
  WorkspaceState,
} from "../types";
import {
  createManualCheckSession,
  createMarking,
  listMarkings,
  retractMarking,
  submitSession,
  type CreateMarkingPayload,
  type EntityAddressPayload,
  type MarkingStatus,
} from "../../../services/groundTruthApi";

/**
 * Manual engineer check — ground-truth capture.
 *
 * ## Every marking is written through, not batched
 *
 * `commitStamp` posts immediately and only then updates local state. A session on a dense sheet
 * is an hour of work (`M745230A01` carries 68 addressable rows); holding it in memory until a
 * submit button means one crash, one closed laptop or one dropped websocket loses all of it,
 * and an annotator who has lost an hour does not come back. `submitManualSession` finalises a
 * session that already holds its data.
 *
 * The consequence, accepted deliberately: a stamp is not instant. That is the right trade for a
 * tool whose entire output is the records it keeps.
 *
 * ## This slice never touches the comparison engine
 *
 * No violations, no audit, no learned model. Markings land in their own collections and stop
 * there.
 */

const TOOL_STATUS: Record<StampTool, MarkingStatus> = {
  matched: "MATCHED",
  added: "ADDED",
  removed: "REMOVED",
  changed: "CHANGED",
  not_a_finding: "NOT_A_FINDING",
};

/**
 * Which side a tool stamps on.
 *
 * REMOVED anchors on the **reference** — a removal exists there and nowhere else, which is also
 * why reference-side handle coverage (0.8–13%) is the hard case for addressing. Everything else
 * anchors on the revision, and CHANGED needs both.
 */
export const TOOL_SIDE: Record<StampTool, "ref" | "rev" | "both"> = {
  matched: "rev",
  added: "rev",
  removed: "ref",
  changed: "both",
  not_a_finding: "rev",
};

function toAddress(picked: PickedEntity | null): EntityAddressPayload | null {
  if (!picked) return null;
  return {
    drawing_id: picked.drawingId,
    handle: picked.handle,
    parent_handle: picked.parentHandle,
    entity_type: picked.entityType,
    layer: picked.layer,
    text: picked.text,
    // Sent as a bare pair; the server stamps coordinate space, layout, viewport index and the
    // render-bounds snapshot, because it owns the DrawingDocument and this client does not.
    coordinates: picked.coordinates,
  };
}

/**
 * Whether two locators would produce the same cross-sheet outline.
 *
 * Shared by the hover and selection setters rather than written twice: both guard a canvas
 * repaint, and a copy that forgot a field would let one of them repaint on every pointer event
 * while the other stayed quiet — a performance bug that looks like nothing at all.
 */
function sameLocator(a: EntityLocator | null, b: EntityLocator | null): boolean {
  if (!a && !b) return true;
  if (!a || !b) return false;
  return (
    a.side === b.side &&
    a.value === b.value &&
    a.entityType === b.entityType &&
    a.dimKind === b.dimKind &&
    a.zone === b.zone &&
    a.zoneMeasured === b.zoneMeasured &&
    a.zfx === b.zfx &&
    a.zfy === b.zfy &&
    a.cfx === b.cfx &&
    a.cfy === b.cfy &&
    a.sfx === b.sfx &&
    a.sfy === b.sfy
  );
}

export const createManualCheckSlice: StateCreator<
  WorkspaceState,
  [],
  [],
  ManualCheckSlice
> = (set, get) => ({
  manualSessionId: null,
  markings: [],
  pendingPairRef: null,
  hoveredEntityId: null,
  hoverLocator: null,
  selectionLocator: null,
  selectedEntities: [],
  pendingStamp: null,

  setSelectedEntities: (picked) => {
    // Identity matters: the renderer and the context menu both subscribe, and a fresh empty
    // array on every click into blank canvas would repaint the whole sheet for nothing.
    const prev = get().selectedEntities;
    if (prev.length === 0 && picked.length === 0) return;
    if (
      prev.length === picked.length &&
      prev.every((p, i) => p.entityId === picked[i].entityId)
    ) return;
    set({ selectedEntities: picked });
  },

  setHoveredEntityId: (id) => {
    if (get().hoveredEntityId === id) return; // avoid a re-render per mousemove
    set({ hoveredEntityId: id });
  },

  setHoverLocator: (locator) => {
    // Only a change of VALUE moves the locator, so this fires on transitions rather than on
    // every mousemove — the canvas repaint is too expensive to run per pointer event. Sweeping
    // across three entities that all read `145` is one repaint, not three, because the other
    // sheet would be outlining the same set each time.
    if (sameLocator(get().hoverLocator, locator)) return;
    set({ hoverLocator: locator });
  },

  setSelectionLocator: (locator) => {
    // Same guard as hover, and for a sharper reason: clicking a second entity that carries the
    // same value outlines the identical set on the other sheet, so repainting both canvases
    // would be pure cost.
    if (sameLocator(get().selectionLocator, locator)) return;
    set({ selectionLocator: locator });
  },

  setPendingPairRef: (picked) => set({ pendingPairRef: picked }),

  openStamp: (stamp: PendingStamp | null) => set({ pendingStamp: stamp }),

  startManualSession: async (roomId, refDrawingId, revDrawingId) => {
    try {
      const session = await createManualCheckSession({
        room_id: roomId,
        ref_drawing_id: refDrawingId,
        rev_drawing_id: revDrawingId,
      });
      // Reload rather than assume empty: reopening a room must show the markings already made,
      // which is the visible half of the write-through guarantee above.
      const existing = await listMarkings(session.id);
      set({ manualSessionId: session.id, markings: existing, pendingPairRef: null });
    } catch (err: any) {
      console.error("Failed to open manual check session:", err?.message ?? err);
      set({ manualSessionId: null, markings: [] });
    }
  },

  commitStamp: async (input: CommitStampInput) => {
    const { manualSessionId, pendingStamp } = get();
    if (!manualSessionId || !pendingStamp) return;

    const payload: CreateMarkingPayload = {
      status: TOOL_STATUS[pendingStamp.tool],
      category: input.category,
      ref_address: toAddress(pendingStamp.ref),
      rev_address: toAddress(pendingStamp.rev),
      ref_text: input.refText,
      rev_text: input.revText,
      text_was_edited: input.textWasEdited,
      is_bulk: input.isBulk,
      notes: input.notes,
    };

    try {
      const saved = await createMarking(manualSessionId, payload);
      set((state) => ({
        markings: [...state.markings, saved],
        pendingStamp: null,
        pendingPairRef: null,
      }));
    } catch (err: any) {
      // Left open on failure, with the engineer's typing intact. Closing the modal would
      // discard a judgement they have already made and show no sign that it was not recorded.
      console.error("Failed to record marking:", err?.message ?? err);
      throw err;
    }
  },

  retractManualMarking: async (markingId) => {
    try {
      await retractMarking(markingId);
      // Dropped from the local list, but the server keeps the row marked rather than deleted —
      // the collection is the audit trail of who asserted what.
      set((state) => ({ markings: state.markings.filter((m) => m.id !== markingId) }));
    } catch (err: any) {
      console.error("Failed to retract marking:", err?.message ?? err);
    }
  },

  submitManualSession: async () => {
    const { manualSessionId } = get();
    if (!manualSessionId) return;
    try {
      await submitSession(manualSessionId);
    } catch (err: any) {
      console.error("Failed to submit manual check:", err?.message ?? err);
    }
  },
});
