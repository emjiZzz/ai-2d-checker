import { create } from 'zustand';
import type { RegionFractions } from '../utils/zoneFractions';
import type { ViolationItem, PenStroke } from './workspace/types';

/**
 * historyStore.ts
 *
 * One undo/redo stack for the whole 2D workspace.
 *
 * ## Why one stack and not one per feature
 *
 * Ctrl+Z means "take back the last thing I did", and the user does not think in terms of
 * which store owns what. Zone alignment lives in `reviewStore.customRegions` and violation
 * markers live in `workspaceStore.violations`; two separate histories would make the key's
 * behaviour depend on invisible state ownership — press it after a zone drag and a marker
 * move and you would get the marker back regardless of which came last.
 *
 * ## Entries are DATA, not closures
 *
 * Every entry carries an explicit `before` and `after` payload rather than a pair of undo/redo
 * functions. A closure would capture store values that are stale by the time it runs (the
 * whole point of an undo stack is that it runs later), and it could not be asserted on in a
 * test without mounting the component that created it. `applyHistoryEntry` in
 * `hooks/useUndoRedo.ts` is the single place that turns an entry back into a state change.
 *
 * ## This module imports no other store, on purpose
 *
 * Slices push into it (`createNavSlice` clears it on workspace reset), so if it reached back
 * into `workspaceStore` that would be an import cycle. It is a dumb stack: it holds entries
 * and hands them back. Everything that knows what an entry MEANS lives in the applier.
 *
 * ## Recording happens at the interaction layer
 *
 * Store setters (`updateCustomRegion`, `setViolations`) never record — the caller that knows
 * the gesture boundaries does. That is what keeps undo from recording its own effects: the
 * applier calls the same setters and no new entry appears.
 *
 * ## One user action is one Ctrl+Z, even across two drawings
 *
 * The 2D workspace shows the reference and the revision side by side, and the editor's toolbar
 * actions — Reset, Save to template, seeding a box from a zone chip — all operate on BOTH.
 * Written as one entry per drawing, a single click on Reset took two Ctrl+Z presses to walk
 * back, and the first press restored one pane while the other stayed empty. That reads as undo
 * being broken, not as undo being half-done, so the entries carry a shared `groupId` and
 * `performUndo` drains the whole group. Single-pane edits (a drag gesture) leave it undefined
 * and behave exactly as before.
 */

/** Every zone box for one drawing, keyed by zone. `null` = the drawing has no alignment. */
export type ZoneRegionSnapshot = Record<string, RegionFractions> | null;

export type HistoryEntry =
  /**
   * One zone changed on one drawing: dragged, resized, reshaped, or created.
   *
   * A whole drag gesture is ONE entry, not one per mousemove frame — the drag handler writes
   * to the store on every frame, so recording per write would bury a single nudge of a corner
   * under two hundred undo steps. The snapshot is taken on mousedown and committed on mouseup.
   *
   * `null` on either side is meaningful: `before: null` is a zone that did not exist yet (the
   * zone picker seeds a box for an unplaced zone), so undoing it must REMOVE the key rather
   * than write an empty box.
   */
  | {
      kind: 'zone/update';
      label: string;
      /** Set when this entry is one drawing's half of a two-pane action. See `recordHistoryGroup`. */
      groupId?: string;
      drawingId: string;
      zoneKey: string;
      before: RegionFractions | null;
      after: RegionFractions | null;
    }
  /**
   * Every zone on one drawing replaced at once: Reset, or applying a sheet template.
   *
   * `pinnedBefore`/`pinnedAfter` travel with the regions because the two are one fact. The
   * pinned list decides whether a zone renders as a human decision or as a detector guess, so
   * restoring boxes without it would leave hand-aligned zones drawn dashed-and-'?'.
   */
  | {
      kind: 'zone/bulk';
      label: string;
      groupId?: string;
      drawingId: string;
      before: ZoneRegionSnapshot;
      after: ZoneRegionSnapshot;
      pinnedBefore: string[] | null;
      pinnedAfter: string[] | null;
    }
  | {
      kind: 'violation/move';
      label: string;
      groupId?: string;
      violationId: string;
      before: { coordinates?: [number, number]; refCoordinates?: [number, number] };
      after: { coordinates?: [number, number]; refCoordinates?: [number, number] };
    }
  /**
   * A deleted marker. The whole item is kept because nothing else can reconstruct it — it is
   * not re-fetchable, having only ever existed in this session's audit results.
   */
  | {
      kind: 'violation/delete';
      label: string;
      groupId?: string;
      violationId: string;
      violation: ViolationItem;
    }
  | {
      kind: 'pen/stroke';
      label: string;
      groupId?: string;
      drawingId: string;
      stroke: PenStroke;
    }
  | {
      kind: 'pen/clear';
      label: string;
      groupId?: string;
      drawingId: string;
      strokes: PenStroke[];
    };

/**
 * Entries kept before the oldest is dropped.
 *
 * Bounded because a `violation/delete` entry pins an entire ViolationItem in memory and a
 * long review session is thousands of gestures. 100 is far past what anyone walks back by
 * hand, and reaching for a 101st undo is a job for Reset, not for the keyboard.
 */
export const MAX_HISTORY = 100;

interface HistoryState {
  past: HistoryEntry[];
  future: HistoryEntry[];

  /**
   * Record a completed change.
   *
   * Clears the redo stack, which is the standard linear-history rule: once you undo and then
   * do something new, the branch you undid is unreachable and keeping it would let Ctrl+Y
   * replay a change that no longer makes sense against current state.
   */
  record: (entry: HistoryEntry) => void;
  /** Pop the newest past entry and move it to the redo stack. Null when there is nothing. */
  takeUndo: () => HistoryEntry | null;
  /** Pop the newest future entry and move it back to the undo stack. */
  takeRedo: () => HistoryEntry | null;
  clear: () => void;
}

export const useHistoryStore = create<HistoryState>((set, get) => ({
  past: [],
  future: [],

  record: (entry) =>
    set((state) => {
      const past = [...state.past, entry];
      if (past.length <= MAX_HISTORY) return { past, future: [] };

      let trimmed = past.slice(past.length - MAX_HISTORY);
      // Dropping the oldest entry can cut a group in half. The surviving half would then undo
      // on its own and leave the two panes disagreeing — a state the user never actually saw.
      // Discard the rest of the torn group with it.
      const tornGroup = past[past.length - MAX_HISTORY - 1]?.groupId;
      if (tornGroup) {
        while (trimmed.length > 0 && trimmed[0].groupId === tornGroup) trimmed = trimmed.slice(1);
      }
      return { past: trimmed, future: [] };
    }),

  takeUndo: () => {
    const { past } = get();
    if (past.length === 0) return null;
    const entry = past[past.length - 1];
    set((state) => ({ past: state.past.slice(0, -1), future: [...state.future, entry] }));
    return entry;
  },

  takeRedo: () => {
    const { future } = get();
    if (future.length === 0) return null;
    const entry = future[future.length - 1];
    set((state) => ({ future: state.future.slice(0, -1), past: [...state.past, entry] }));
    return entry;
  },

  clear: () => set({ past: [], future: [] }),
}));

/** Convenience for callers that only have a store handle, not the hook. */
export const recordHistory = (entry: HistoryEntry) => useHistoryStore.getState().record(entry);

let groupSeq = 0;

/**
 * Records several entries as ONE undoable action.
 *
 * For the editor's toolbar actions, which each touch the reference and the revision: the user
 * clicked once, so one Ctrl+Z must take all of it back. Entries are still recorded (and undone)
 * individually — the group only tells `performUndo` where the action's boundary is.
 *
 * A single entry is recorded ungrouped, so the common case carries no marker at all.
 */
export function recordHistoryGroup(entries: HistoryEntry[]): void {
  if (entries.length === 0) return;
  if (entries.length === 1) {
    recordHistory(entries[0]);
    return;
  }
  groupSeq += 1;
  const groupId = `grp-${groupSeq}`;
  for (const entry of entries) recordHistory({ ...entry, groupId });
}
