---
tags: [gotcha, frontend, undo, keyboard, hooks, react]
status: fixed
cache-version: n/a — desktop UI state only, no engine or zone-extraction behaviour
date: 2026-08-06
---

# Gotcha — A Window Listener in a Per-Pane Hook Fires Once Per Pane

> [!WARNING] Ctrl+Z undid **two** actions per press. The handler was correct; it was simply
> installed twice, because the hook that installed it runs once per canvas pane and the 2D
> workspace renders two.

## What happened

`useCanvasInteraction` registered the undo shortcut on `window`:

```ts
useEffect(() => {
  const handleKeyDown = (e: KeyboardEvent) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') {
      useWorkspaceStore.getState().undoLastAction();
    }
  };
  window.addEventListener('keydown', handleKeyDown);
  return () => window.removeEventListener('keydown', handleKeyDown);
}, [...]);
```

That hook is called from `DrawingCanvas`, and `TwoDWorkspace` renders `DrawingCanvas` twice —
once in `OriginalDrawingPanel` (reference) and once in `KMTIDrawingPanel` (revision). Two
mounts, two listeners, two calls to `undoLastAction()` per keypress.

Nothing about the code looks wrong in isolation, and the cleanup function is correct. The bug
lives entirely in the **relationship between the listener's scope and the hook's lifetime**:
the listener is global, the hook is per-instance.

## Why it stayed invisible

The old undo stack only ever held violation-marker moves and alt-click deletes, which are rare
compared to panning and zooming. Undoing two marker moves instead of one reads as "I must have
nudged it twice" — there is no error, no console warning, and the result is *plausible*. It
would have become obvious the moment undo covered zone alignment, where every gesture is
deliberate and losing two of them is unmistakable.

The general shape: **a duplicated global side effect degrades quality silently rather than
failing.** Two listeners do not conflict; they cooperate, and do the job twice.

## The rule

**Anything bound to `window`, `document`, or any other singleton belongs in a hook that is
mounted exactly once.** For this app that means `useGlobalShortcuts`, called from `App.tsx`.
Per-pane hooks may only attach listeners to elements they own — the canvas element, via React's
own `onMouseDown`/`onKeyDown` props.

Before adding a `window.addEventListener` inside a hook, ask how many components call that
hook. If the answer is not "exactly one", the listener does not go there.

Undo/redo now lives in `apps/desktop/src/hooks/useUndoRedo.ts`, called by `useGlobalShortcuts`.
`useCanvasInteraction` keeps its *other* window listeners (space-to-pan, Escape, `F`, Ctrl+±)
— those are idempotent, so duplication is harmless, which is precisely why the undo case was
the only one that mattered and the only one that was moved.

## Two smaller defects found in the same handler

1. **The Delete/Backspace branch was dead code.** It compared `e.key === 'delete'` and
   `e.key === 'backspace'`, but `KeyboardEvent.key` reports `'Delete'` and `'Backspace'`
   capitalised, so neither branch could ever run. The surrounding branches compared against a
   pre-lowercased `key` variable; these two used the raw `e.key`. Now fixed to use the same
   lowercased variable — which means the key *starts working*, so it was also made undoable in
   the same change.

2. **Keyboard deletion recorded no history at all.** Alt-click delete pushed onto the undo
   stack; the (dead) keyboard path did not. Had the comparison bug been fixed on its own, it
   would have introduced the only unrecoverable destructive action in the workspace.

## The transferable lesson

Two of the three defects here are invisible to `tsc` and to the test suite, because each line
is individually valid. They are **wiring** faults: the right code in the wrong scope, and a
comparison against the wrong casing. When a keyboard handler misbehaves, check *how many times
it is installed* before you debug what it does.

## See also

- [[Gotcha - One Click on Two Panes Recorded Two Undo Steps]] — the same pane count biting undo
  from the other direction: not two handlers per press, but two entries per click
- [[Gotcha - A Reshaped Zone Is Not Its Bounding Box]] — the zone geometry that undo now has to
  restore faithfully, `points` and all
- [[Gotcha - Zone Detection Accuracy & Stability]] — why the zone boxes are hand-aligned in the
  first place, and therefore why losing an alignment is expensive
