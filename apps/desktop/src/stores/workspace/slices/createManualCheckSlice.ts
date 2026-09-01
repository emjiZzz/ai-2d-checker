import { StateCreator } from "zustand";
import {
  CommitStampInput,
  EntityLocator,
  ManualCheckSlice,
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
  reopenSession,
  type CreateMarkingPayload,
  type EntityAddressPayload,
  type MarkingStatus,
} from "../../../services/groundTruthApi";
import { useEngineerStore } from "../../engineerStore";

/**
 * Manual engineer check — ground-truth capture.
 *
 * ## Every marking is written through, not batched
 *
 * `recordStamp` posts immediately and only then updates local state. A session on a dense sheet
 * is an hour of work (`M745230A01` carries 68 addressable rows); holding it in memory until a
 * submit button means one crash, one closed laptop or one dropped websocket loses all of it,
 * and an annotator who has lost an hour does not come back. `submitManualSession` finalises a
 * session that already holds its data.
 *
 * The consequence, accepted deliberately: a stamp is not instant. That is the right trade for a
 * tool whose entire output is the records it keeps.
 *
 * ## No write may fail silently — `markingError`
 *
 * Write-through is only worth anything if a failed write is *visible*. All three write actions
 * used to swallow: `SelectionMenu` caught `recordStamp`'s rejection in a bare `.catch(() => {})`
 * on the comment that "the store surfaces it" (it did not), and retract and submit caught their
 * own here. The results were, in order of cost:
 *
 *  - a failed stamp produced no UI at all, leaving the entity unmarked and looking like a
 *    mis-click;
 *  - a failed retraction dropped the row from the panel while the server kept it LIVE — and
 *    `eval_corpus.py from-manual-check` then converts a marking the engineer believes they
 *    withdrew into committed ground truth. 31 of 38 markings in the session behind
 *    `M745204N01` were retractions, so this is the busiest path in the feature;
 *  - a failed submit still rendered "Check submitted".
 *
 * Every write now reports through `markingError`, which `ManualMarkingList` renders. Retract and
 * submit return a boolean rather than throwing, because their callers need to know whether to
 * update the UI, not to handle an exception.
 *
 * ## This slice never touches the comparison engine
 *
 * No violations, no audit, no learned model. Markings land in their own collections and stop
 * there.
 *
 * ⚠ **`textWasEdited`, `isBulk` and `notes` are never populated** — no UI writes them. See
 * `CommitStampInput` in `../types` for why, and for what it means downstream.
 */

const TOOL_STATUS: Record<StampTool, MarkingStatus> = {
  matched: "MATCHED",
  mismatched: "MISMATCHED",
  added: "ADDED",
  removed: "REMOVED",
  changed: "CHANGED",
  not_a_finding: "NOT_A_FINDING",
};

/**
 * Which side a tool can be recorded from.
 *
 * Only two are directional, and each for a reason that is about the drawing rather than about
 * the UI: a REMOVED exists on the **reference** and nowhere else, an ADDED on the **revision**
 * and nowhere else. (Reference-side handle coverage of 0.8–13% is the hard case for addressing
 * precisely because REMOVED lives there.)
 *
 * MATCHED, MISMATCHED and CHANGED are claims recordable from either sheet (both).
 */
export const TOOL_SIDE: Record<StampTool, "ref" | "rev" | "both"> = {
  matched: "both",
  mismatched: "both",
  added: "rev",
  removed: "ref",
  changed: "both",
  not_a_finding: "rev",
};

/**
 * Should the workspace open a manual-check session right now?
 *
 * Extracted from the effect that asks it so the question itself is testable. The bug it encodes
 * was not a wrong answer but a wrong QUESTION: the effect asked "is a session open?" when the
 * only useful question is "is a session open *for this pair*?". On an app reload the workspace
 * restores its drawings from IndexedDB before the server's arrive, so a session opened in that
 * window belongs to the previous pair — and "a session is open" was true, which suppressed the
 * correction and left the panel listing a pair with no markings.
 *
 * @param openPair   the pair the current session belongs to, or null when none is open
 * @param wantedPair the pair now on screen, or null while the workspace is still assembling
 */
/**
 * The pair whose open request is currently in flight.
 *
 * Module scope, not store state, and deliberately so: it must be readable and writable in the
 * same synchronous tick, before any `set` has been through React. A store field would be read
 * stale by the second caller and let it through — which is exactly the thing being prevented.
 *
 * ## What it prevents
 *
 * React StrictMode double-invokes effects in development, so the workspace fires two opens ~40ms
 * apart. Both reach the server before either has inserted, both find no session to resume, and
 * both create one. That is visible in the collection as sessions in PAIRS, milliseconds apart —
 * and the app then holds whichever id came back last, which is a session with nothing in it.
 *
 * The server-side resume makes this harmless for a pair that has been opened before. It does not
 * help the FIRST open of a new pair, where there is genuinely nothing to find; that is the case
 * this guard covers, and it is the case an engineer meets on their first check of a drawing.
 */
let openInFlight: string | null = null;

export function shouldOpenManualSession(
  isManualCheckRoom: boolean,
  openPair: string | null,
  wantedPair: string | null,
): boolean {
  if (!isManualCheckRoom) return false;
  // Nothing to open for yet — a room with one drawing, or mid-load.
  if (!wantedPair) return false;
  return openPair !== wantedPair;
}

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
  manualSessionStatus: null,
  manualSessionPair: null,
  manualSessionError: null,
  markings: [],
  pendingPairRef: null,
  pendingPairTool: "changed",
  hoveredEntityId: null,
  hoverLocator: null,
  selectionLocator: null,
  selectionMenu: null,
  selectionCounterpart: null,
  selectedEntities: [],
  markingError: null,

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

  setSelectionMenu: (menu) => set({ selectionMenu: menu }),

  setSelectionCounterpart: (picked) => {
    // Compared by entity id: the resolving pane recomputes this on every render of a frame that
    // changed, and a fresh object each time would repaint both canvases continuously.
    const prev = get().selectionCounterpart;
    if (prev?.entityId === picked?.entityId) return;
    set({ selectionCounterpart: picked });
  },

  setSelectionLocator: (locator) => {
    // Same guard as hover, and for a sharper reason: clicking a second entity that carries the
    // same value outlines the identical set on the other sheet, so repainting both canvases
    // would be pure cost.
    if (sameLocator(get().selectionLocator, locator)) return;
    set({ selectionLocator: locator });
  },

  // Both fields in ONE `set`, so the half and what it will become cannot drift apart. Two
  // setters would allow a pair carrying the previous gesture's verb — a MATCHED completing as a
  // CHANGED, which is a wrong record rather than a visible fault.
  setPendingPairRef: (picked, tool = "changed") =>
    set({ pendingPairRef: picked, pendingPairTool: picked ? tool : "changed" }),

  clearMarkingError: () => {
    if (get().markingError === null) return;
    set({ markingError: null });
  },

  startManualSession: async (roomId, refDrawingId, revDrawingId) => {
    const pair = `${roomId}:${refDrawingId}:${revDrawingId}`;
    // A second caller for the same pair while the first is still waiting is the StrictMode
    // double-invoke, not a real second intent. Dropped rather than queued: the first request
    // will populate the store, and running it twice can only produce a duplicate session.
    if (openInFlight === pair) return;
    openInFlight = pair;
    try {
      const annotator = useEngineerStore.getState().engineerName || undefined;
      const session = await createManualCheckSession({
        room_id: roomId,
        ref_drawing_id: refDrawingId,
        rev_drawing_id: revDrawingId,
        annotator,
      });
      // Reload rather than assume empty: reopening a room must show the markings already made.
      //
      // This depends on the server RESUMING the open session for this pair rather than minting
      // a fresh one — `POST /ground-truth/sessions` is idempotent per (room, pair, annotator)
      // while the session is in progress. It was not until 2026-08-18, and the symptom was
      // precisely here: this call returned a new empty session's id, `listMarkings` returned
      // nothing for it, and the panel came up blank after every app reload with the engineer's
      // work orphaned under the previous id. Pinned by
      // `tests/test_ground_truth_submission.py::test_reopening_a_pair_resumes_the_session_already_in_progress`.
      const existing = await listMarkings(session.id);
      set({
        manualSessionId: session.id,
        manualSessionStatus: (session as any).status || null,
        manualSessionPair: pair,
        manualSessionError: null,
        // A write error from the previous session cannot describe this one.
        markingError: null,
        markings: existing,
        pendingPairRef: null,
      });
    } catch (err: any) {
      // Recorded, not swallowed. This used to `set({ manualSessionId: null, markings: [] })` —
      // both already their current values, so React saw no change, the open effect never re-ran,
      // and the panel sat empty looking exactly like a session with nothing in it. An error the
      // user can see is the difference between "retry this" and "my work is gone".
      const message = String(err?.message ?? err);
      console.error("Failed to open manual check session:", message);
      set({
        manualSessionId: null,
        manualSessionPair: null,
        manualSessionError: message,
        markings: [],
      });
    } finally {
      // Released on both paths. Leaving it set after a failure would make the panel's Retry a
      // no-op — a button that visibly does nothing, for a user already looking at an error.
      if (openInFlight === pair) openInFlight = null;
    }
  },

  /**
   * Write one marking. The single path to the server.
   *
   * Takes the stamp as an ARGUMENT rather than from store state, which is what lets the
   * no-dialog path work at all: setting the stamp and then reading it back would read the store
   * before React had flushed the write, and record against whatever the previous stamp was.
   */
  recordStamp: async (stamp, input: CommitStampInput) => {
    const { manualSessionId } = get();
    if (!manualSessionId) {
      // Not silent. The panel already says "Opening session…", but a stamp made in that window
      // is a judgement the engineer believes they recorded.
      set({
        markingError:
          "No check session is open yet, so that marking was not recorded. Wait for the " +
          "session to open and stamp it again.",
      });
      return;
    }
    const pendingStamp = stamp;

    const payload: CreateMarkingPayload = {
      status: TOOL_STATUS[pendingStamp.tool],
      category: input.category,
      feature: input.feature ?? null,
      // Says whether a person chose that category or the zone did. See
      // `GroundTruthMarking.category_source` — an evaluator filters attribution on it.
      category_source: input.categorySource ?? 'human',
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
      const isCurrentlySubmitted = get().manualSessionStatus === 'completed' || get().manualSessionStatus === 'submitted';
      set((state) => ({
        markings: [...state.markings, saved],
        pendingPairRef: null,
        manualSessionStatus: 'in_progress',
        // Cleared only by a write that actually succeeded. A stale error standing over a panel
        // that is recording fine is its own kind of lie.
        markingError: null,
      }));
      if (isCurrentlySubmitted) {
        reopenSession(manualSessionId).catch((err) => console.warn('[manualCheck] Reopen on stamp warning:', err));
      }
    } catch (err: any) {
      console.error("Failed to record marking:", err?.message ?? err);

      // The session this client is holding no longer exists on the server — it was deleted, or
      // the database was replaced under a running app. Clearing the id is a REPAIR, not just a
      // reset: `TwoDWorkspace`'s open effect watches `manualSessionId` and reopens as soon as it
      // goes null, so the next attempt lands in a live session.
      //
      // Without this the app dead-ends. The id lives only in memory, so every retry re-sends the
      // same dead id and the only way out is a full restart.
      //
      // ⚠ Plain `/404/`, with no word-boundary escapes, deliberately.
      //
      // This test was written with word-boundary escapes until 2026-08-20 and they had been
      // mangled into two literal BACKSPACE bytes (0x08) by whatever wrote the file. The regex
      // therefore matched only a message containing a backspace character — i.e. never — so
      // the repair below had not run once since it was written, and the app dead-ended on a
      // dead session id exactly as the comment above says it must not. `unwrap` in
      // `groundTruthApi` builds the message as `... failed (404): ...`, so there is nothing
      // here that needs bounding. Keep it escape-free: this file is the one place in the repo
      // that has already been bitten by that mangling.
      const message = String(err?.message ?? err);
      if (/404/.test(message) || /session not found/i.test(message)) {
        set({
          manualSessionId: null,
          markingError:
            "That check session no longer exists on the server, so this marking was NOT " +
            "recorded. A new session is opening — select the entity and stamp it again.",
        });
        return;
      }
      set({ markingError: `That marking was NOT recorded — stamp it again. ${message}` });
    }
  },

  /**
   * Retract, and drop the row locally ONLY once the server has confirmed it.
   *
   * The ordering is the whole point. Dropping first and reconciling on failure would leave the
   * engineer looking at a panel that agrees with them and a database that does not — and the
   * export path reads the database. `from-manual-check` filters on `retracted_at`, so a
   * retraction the server never applied comes back as a LIVE marking and is converted into a
   * finding the engineer explicitly withdrew. That is fabricated ground truth, and nothing
   * downstream could tell. 31 of the 38 markings behind `M745204N01` were retractions.
   */
  retractManualMarking: async (markingId) => {
    const { manualSessionId } = get();
    const isCurrentlySubmitted = get().manualSessionStatus === 'completed' || get().manualSessionStatus === 'submitted';
    try {
      await retractMarking(markingId);
      // The server keeps the row marked rather than deleted — the collection is the audit trail
      // of who asserted what. Only the local view drops it.
      set((state) => ({
        markings: state.markings.filter((m) => m.id !== markingId),
        manualSessionStatus: 'in_progress',
        markingError: null,
      }));
      if (isCurrentlySubmitted && manualSessionId) {
        reopenSession(manualSessionId).catch((err) => console.warn('[manualCheck] Reopen on retract warning:', err));
      }
      return true;
    } catch (err: any) {
      const message = String(err?.message ?? err);
      console.error("Failed to retract marking:", message);
      set({
        markingError:
          "That marking was NOT retracted and is still recorded on the server — try again. " +
          message,
      });
      return false;
    }
  },

  submitManualSession: async () => {
    const { manualSessionId } = get();
    if (!manualSessionId) {
      set({ markingError: "No check session is open, so there was nothing to finish." });
      return false;
    }
    try {
      await submitSession(manualSessionId);
      set({ manualSessionStatus: "completed", markingError: null });
      return true;
    } catch (err: any) {
      const message = String(err?.message ?? err);
      console.error("Failed to submit manual check:", message);
      set({
        markingError:
          "This check was NOT submitted — your markings are still saved, but the session is " +
          "not finished. Try again. " +
          message,
      });
      return false;
    }
  },

  reopenManualSession: async () => {
    const { manualSessionId } = get();
    if (!manualSessionId) return false;
    try {
      await reopenSession(manualSessionId);
      set({ manualSessionStatus: "in_progress", markingError: null });
      return true;
    } catch (err: any) {
      console.error("Failed to reopen manual session:", err);
      set({ manualSessionStatus: "in_progress", markingError: null });
      return true;
    }
  },
});
