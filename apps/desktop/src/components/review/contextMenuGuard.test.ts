import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { shouldSuppressNextMenu, CLICK_SLOP_PX } from './entityPicking';

/**
 * The context-menu guard, and the shape of failure it actually had.
 *
 * `preventNextContextMenu` spent months as a `useState` that `handleContextMenu` could CLEAR and
 * nothing could ever SET. Every unit test of every surrounding behaviour passed, `tsc` passed,
 * and the guard was inert: a check with nothing on the other end of it.
 *
 * It was not written that way. `243582e` and `d98e3bb` both armed it —
 * `if (e.buttons === 2) setPreventNextContextMenu(true)` in the pan path — and `92e3d3c` dropped
 * that line while rewriting the pan fast path. **The check survived the refactor; the thing it
 * checked did not.** No behavioural test could have caught that, because the predicate was never
 * the broken part.
 *
 * So this file tests both halves, deliberately:
 *
 *  1. the RULE, as a pure function; and
 *  2. the WIRING, by reading the source and asserting the ref is written as well as read —
 *     the same crude-on-purpose approach as `componentReachability.test.ts`, for the same
 *     reason: a precise tool would be a dependency nobody wants for a property this coarse.
 */

const here = dirname(fileURLToPath(import.meta.url));
const interactionSource = readFileSync(resolve(here, 'useCanvasInteraction.ts'), 'utf8');

describe('shouldSuppressNextMenu', () => {
  it('suppresses after dragging something, whatever the distance', () => {
    // A marker press that never moves is still a select-or-delete. Stamping on top of it would
    // put a ground-truth record on an entity the engineer was only nudging.
    expect(shouldSuppressNextMenu(true, false, 0)).toBe(true);
    expect(shouldSuppressNextMenu(true, false, 2)).toBe(true);
    expect(shouldSuppressNextMenu(true, true, 500)).toBe(true);
  });

  it('suppresses after a pan that actually travelled', () => {
    expect(shouldSuppressNextMenu(false, true, CLICK_SLOP_PX + 1)).toBe(true);
    expect(shouldSuppressNextMenu(false, true, 200)).toBe(true);
  });

  it('does NOT suppress an ordinary click, which always drifts a pixel or two', () => {
    // The regression risk in the other direction: arm too eagerly and stamping stops working,
    // because no real click lands on the exact pixel it started from.
    expect(shouldSuppressNextMenu(false, true, 0)).toBe(false);
    expect(shouldSuppressNextMenu(false, true, CLICK_SLOP_PX)).toBe(false);
    expect(shouldSuppressNextMenu(false, false, 999)).toBe(false);
  });
});

describe('the guard is wired, not just checked', () => {
  it('writes the ref as well as reading it', () => {
    // The exact regression: a refactor removes the arming line and leaves the check behind.
    const reads = interactionSource.match(/if \(preventNextContextMenuRef\.current\)/g) ?? [];
    const writes = interactionSource.match(/preventNextContextMenuRef\.current\s*=/g) ?? [];

    expect(reads.length, 'the guard must still be checked').toBeGreaterThan(0);
    expect(
      writes.length,
      'the guard is checked but never armed — this is exactly how it broke in 92e3d3c',
    ).toBeGreaterThanOrEqual(2); // armed on mouse-up, reset on mouse-down and when consumed
  });

  it('arms from mouse-up, where the drag state is still readable', () => {
    // Arming after `handleMouseUp` clears `dragMarkerId` and friends would read them as already
    // null and never fire — inert again, in a way that still looks wired.
    const mouseUp = interactionSource.slice(interactionSource.indexOf('const handleMouseUp'));
    const armIndex = mouseUp.indexOf('preventNextContextMenuRef.current = shouldSuppressNextMenu');
    const clearIndex = mouseUp.indexOf('setActiveDragHandle(null)');

    expect(armIndex, 'mouse-up must arm the guard').toBeGreaterThan(-1);
    expect(clearIndex).toBeGreaterThan(-1);
    expect(armIndex, 'the guard must be armed BEFORE the drag state is cleared').toBeLessThan(
      clearIndex,
    );
  });

  it('resets on mouse-down before the non-left early return', () => {
    // `mousedown` precedes `contextmenu`. If the reset sat after the early return that ignores
    // non-left buttons, a pan would eat the next deliberate right-click.
    const mouseDown = interactionSource.slice(interactionSource.indexOf('const handleMouseDown'));
    const resetIndex = mouseDown.indexOf('preventNextContextMenuRef.current = false');
    const earlyReturn = mouseDown.indexOf('if (e.button !== 0 && !isSpacePressed)');

    expect(resetIndex).toBeGreaterThan(-1);
    expect(earlyReturn).toBeGreaterThan(-1);
    expect(resetIndex, 'the reset must run for every button').toBeLessThan(earlyReturn);
  });
});
