import { useEffect } from 'react';
import { useReviewStore } from '../stores/reviewStore';
import { useNavStore } from '../stores/navStore';
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
