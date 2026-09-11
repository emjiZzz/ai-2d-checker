import { useEffect } from 'react';
import { useReviewStore } from '../stores/reviewStore';
import { useNavStore } from '../stores/navStore';
import { useWorkspaceStore } from '../stores/workspaceStore';
import { hasThreeDMesh } from '../config/drawingFormats';
import { useUndoRedo } from './useUndoRedo';

export const useGlobalShortcuts = () => {
  const setViewport = useReviewStore(s => s.setViewport);
  const { setCurrentNav } = useNavStore();

  // Ctrl+Z / Ctrl+Y. Lives here because this hook is mounted exactly once (App.tsx), which
  // is a hard requirement for a window-level listener — see the note in useUndoRedo.ts.
  useUndoRedo();

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Don't trigger shortcuts if user is typing in an input or textarea
      if (
        e.target instanceof HTMLInputElement ||
        e.target instanceof HTMLTextAreaElement ||
        (e.target as HTMLElement).isContentEditable
      ) {
        return;
      }

      // F1 — flip the focused pane between its drawing and its 3D model.
      //
      // This hook is mounted exactly once, from App.tsx, and that is the whole reason the key
      // lives here. `TwoDWorkspace` renders its pane twice, so a window listener added in a
      // per-pane hook is installed twice and fires twice per press -- which for a TOGGLE means
      // it flips and immediately flips back, presenting as a dead key rather than an error.
      // The project has paid for this once already; see
      // `06 - .../Gotcha - A Window Listener in a Per-Pane Hook Fires Once Per Pane.md`.
      //
      // preventDefault suppresses the browser help panel.
      if (e.key === 'F1') {
        e.preventDefault();
        // Shift+F1 reaches the reference pane; F1 alone the revision, which is the one being
        // checked and therefore the one being looked at.
        const side = e.shiftKey ? 'old' : 'new';
        const ws = useWorkspaceStore.getState();
        const drawing = side === 'old' ? ws.oldDrawing : ws.newDrawing;
        // A no-op on a pane with no model, rather than flipping it to a viewer with nothing to
        // show. Every reference drawing here is 2D, so that is the common case for Shift+F1.
        if (!hasThreeDMesh(drawing)) return;
        useReviewStore.getState().toggleViewMode(side);
        return;
      }

      // Zooming and Viewport Control
      if (e.ctrlKey || e.metaKey) {
        const viewport = useReviewStore.getState().viewport;
        switch (e.key) {
          case '=':
          case '+':
            e.preventDefault();
            setViewport({
              ...viewport,
              scale: Math.min(25, viewport.scale * 1.25)
            });
            break;
          case '-':
            e.preventDefault();
            setViewport({
              ...viewport,
              scale: Math.max(0.1, viewport.scale / 1.25)
            });
            break;
          case '0':
            e.preventDefault();
            setViewport({ x: 0, y: 0, scale: 1 });
            break;
          // Navigation shortcuts
          case '1':
            e.preventDefault();
            setCurrentNav('workspace');
            break;
          case '2':
            e.preventDefault();
            setCurrentNav('3d-workspace');
            break;
          case '3':
            e.preventDefault();
            setCurrentNav('standards');
            break;
          case '4':
            e.preventDefault();
            setCurrentNav('history');
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [setViewport, setCurrentNav]);
};
