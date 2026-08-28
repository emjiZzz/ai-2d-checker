import { useEffect } from 'react';
import { useHistoryStore, type HistoryEntry } from '../stores/historyStore';
import { useReviewStore } from '../stores/reviewStore';
import { useWorkspaceStore } from '../stores/workspaceStore';

/**
 * useUndoRedo.ts
 *
 * Turns history entries back into state changes, and binds the keys that drive them.
 *
 * ## Mounted exactly once
 *
 * This hook attaches a `window` keydown listener, so it belongs somewhere that renders once —
 * it is called from `useGlobalShortcuts`, which `App.tsx` mounts a single time.
 *
 * This is not a style preference. The undo binding previously lived in `useCanvasInteraction`,
 * which runs once PER CANVAS PANE, and the 2D workspace renders two panes (reference and
 * revision). Both instances registered a window-level listener, so a single Ctrl+Z press ran
 * the handler twice and walked back two actions. Anything bound to `window` must not live in
 * a per-pane hook.
 */

type Direction = 'undo' | 'redo';

/**
 * Applies one entry in one direction.
 *
 * Exported for tests: this is the whole semantic core of undo, and asserting on it directly
 * beats driving two canvases with synthetic mouse events to reach the same code.
 *
 * Deliberately calls the same store setters ordinary editing calls. Recording happens in the
 * interaction handlers, never inside the setters, so applying an entry cannot record a new
 * one — there is no re-entrancy guard here because there is no re-entrancy to guard.
 */
export function applyHistoryEntry(entry: HistoryEntry, direction: Direction): void {
  // State is read fresh at each point of use rather than snapshotted once at the top. The
  // snapshot version worked, but it made every read below silently order-dependent — one
  // `await` added inside this function later would have turned `violations` into a stale copy
  // and quietly dropped whatever changed in between.
  const review = () => useReviewStore.getState();
  const workspace = () => useWorkspaceStore.getState();

  switch (entry.kind) {
    case 'zone/update': {
      const target = direction === 'undo' ? entry.before : entry.after;
      review().restoreCustomRegion(entry.drawingId, entry.zoneKey, target);
      // Make the affected zone the selected one. Undoing a zone you cannot see edit handles on
      // looks like nothing happened — only the selected zone draws handles.
      if (review().selectedComparisonRegion !== entry.zoneKey) {
        review().setSelectedComparisonRegion(entry.zoneKey);
      }
      break;
    }

    case 'zone/bulk': {
      const regions = direction === 'undo' ? entry.before : entry.after;
      const pinned = direction === 'undo' ? entry.pinnedBefore : entry.pinnedAfter;
      review().restoreDrawingRegions(entry.drawingId, regions, pinned);
      break;
    }

    case 'violation/move': {
      const target = direction === 'undo' ? entry.before : entry.after;
      workspace().setViolations(
        workspace().violations.map((v) => {
          if (v.id !== entry.violationId) return v;
          const updated = { ...v };
          if (target.coordinates) updated.coordinates = target.coordinates;
          if (target.refCoordinates) updated.ref_coordinates = target.refCoordinates;
          return updated;
        }),
      );
      break;
    }

    case 'violation/delete': {
      if (direction === 'undo') {
        // Guard against a double restore: the context menu's "Undo Delete" reads the same
        // deletion from `deletedViolationsStack`, so without the filter below, using both
        // affordances on one deletion would put two copies of the marker on the canvas.
        const alreadyPresent = workspace().violations.some((v) => v.id === entry.violationId);
        if (!alreadyPresent) {
          workspace().setViolations([...workspace().violations, entry.violation]);
        }
        useWorkspaceStore.setState((s) => ({
          deletedViolationsStack: s.deletedViolationsStack.filter((v) => v.id !== entry.violationId),
        }));
      } else {
        workspace().setViolations(workspace().violations.filter((v) => v.id !== entry.violationId));
        // Back onto the deleted stack, so the context menu's counter and the canvas agree
        // again — redoing a delete must look exactly like performing it.
        useWorkspaceStore.setState((s) => ({
          deletedViolationsStack: [...s.deletedViolationsStack, entry.violation],
        }));
        if (workspace().selectedViolation?.id === entry.violationId) {
          workspace().selectViolation(null);
        }
      }
      break;
    }

    case 'pen/stroke': {
      if (direction === 'undo') {
        workspace().removePenStroke(entry.stroke.id);
      } else {
        useWorkspaceStore.setState((s) => ({
          penStrokes: [...s.penStrokes.filter((st) => st.id !== entry.stroke.id), entry.stroke],
        }));
      }
      break;
    }

    case 'pen/clear': {
      if (direction === 'undo') {
        useWorkspaceStore.setState((s) => {
          const currentWithoutDrawing = s.penStrokes.filter(
            (st) => st.drawingId !== entry.drawingId,
          );
          return {
            penStrokes: [...currentWithoutDrawing, ...entry.strokes],
          };
        });
      } else {
        workspace().clearPenStrokes(entry.drawingId);
      }
      break;
    }
  }
}

/**
 * Runs the newest undoable change backwards. No-op when the stack is empty.
 *
 * When the entry belongs to a group, the rest of the group goes with it — the editor's toolbar
 * actions each write one entry per pane, and stopping after the first left the reference
 * restored and the revision not. Returns the first entry applied, which is the whole group's
 * label; grouped entries always share one.
 */
export function performUndo(): HistoryEntry | null {
  const first = useHistoryStore.getState().takeUndo();
  if (!first) return null;
  applyHistoryEntry(first, 'undo');
  if (first.groupId) {
    // Peek rather than pop-and-push-back: the group's members are contiguous, because
    // `recordHistoryGroup` writes them with nothing in between.
    while (peek(useHistoryStore.getState().past)?.groupId === first.groupId) {
      const next = useHistoryStore.getState().takeUndo();
      if (!next) break;
      applyHistoryEntry(next, 'undo');
    }
  }
  return first;
}

/** Re-applies the most recently undone change, group and all. No-op when nothing was undone. */
export function performRedo(): HistoryEntry | null {
  const first = useHistoryStore.getState().takeRedo();
  if (!first) return null;
  applyHistoryEntry(first, 'redo');
  if (first.groupId) {
    while (peek(useHistoryStore.getState().future)?.groupId === first.groupId) {
      const next = useHistoryStore.getState().takeRedo();
      if (!next) break;
      applyHistoryEntry(next, 'redo');
    }
  }
  return first;
}

const peek = (stack: HistoryEntry[]): HistoryEntry | undefined => stack[stack.length - 1];

/**
 * True when the event targets somewhere the user is typing, where Ctrl+Z belongs to the text
 * field's own native undo. Checks `e.target` AND `document.activeElement`: a listener on
 * `window` sees events whose target is the focused control, but composition and some custom
 * inputs re-target to a wrapper, so the focused element is the more reliable of the two.
 */
function isTypingTarget(e: KeyboardEvent): boolean {
  const candidates = [e.target, document.activeElement];
  return candidates.some((node) => {
    const el = node as HTMLElement | null;
    if (!el || !el.tagName) return false;
    return el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.isContentEditable === true;
  });
}

export const useUndoRedo = () => {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey)) return;
      if (isTypingTarget(e)) return;

      const key = e.key.toLowerCase();

      // Ctrl+Y and Ctrl+Shift+Z are both redo. Ctrl+Y is the Windows convention this app is
      // built for; Ctrl+Shift+Z is what anyone arriving from CAD or design tooling will try,
      // and on macOS it is the only redo binding, since Ctrl+Y there means something else.
      if (key === 'y' || (key === 'z' && e.shiftKey)) {
        e.preventDefault();
        performRedo();
        return;
      }

      if (key === 'z') {
        e.preventDefault();
        performUndo();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);
};
