/**
 * Hairline pixel snapping.
 *
 * Why this exists: a 1-device-pixel stroke is only crisp when its centreline lands on a
 * half-integer device coordinate. At any other sub-pixel phase the browser splits the ink across
 * two columns — measured in Chrome at phase 0: two columns at alpha 0.498 / 0.502, total ink
 * exactly 1.0. The line is not thicker, it is *spread*, and against a CAD viewer that snaps
 * (iCAD SX does) that reads as roughly half a pixel of extra width per side.
 *
 * `transX`/`transY` come from an arbitrary pan offset, so without snapping every axis-aligned
 * rule on the sheet lands at a random phase.
 *
 * Verified end-to-end in a real browser after this landed: a horizontal hairline drawn through
 * `renderEntities` lit exactly 1 row at alpha 1.000 at all 8 phases tested (0 → 0.9), while a
 * diagonal control stayed at 2 rows / 0.373 / 0.627 — untouched, as intended.
 */
import { describe, expect, it } from 'vitest';

import {
  isAxisAlignedChain,
  snapPhaseFor,
  snapWorldToDeviceGrid,
} from './renderEntities';

/** Where a world coordinate actually lands in device pixels, given the renderer's transform. */
const toDevice = (world: number, scale: number, translate: number, dpr: number) =>
  dpr * (translate + scale * world);

describe('snapPhaseFor', () => {
  it('puts odd-width strokes on half-integers — the hairline case', () => {
    // $LWDISPLAY is 0 across this corpus, so every stroke is the 1px hairline.
    expect(snapPhaseFor(1)).toBe(0.5);
    expect(snapPhaseFor(3)).toBe(0.5);
  });

  it('puts even-width strokes on integers', () => {
    expect(snapPhaseFor(2)).toBe(0);
    expect(snapPhaseFor(4)).toBe(0);
  });

  it('picks the phase for the nearest integer width, not the fractional one', () => {
    // The lineweight-display widths, at 96/25.4 px per mm. None is a whole number of pixels,
    // so none can be perfectly crisp — the phase for the width it rounds to is the best
    // available, and it beats leaving the phase to chance.
    expect(snapPhaseFor(0.94)).toBe(0.5); // 0.25mm -> rounds to 1px, odd
    expect(snapPhaseFor(1.89)).toBe(0);   // 0.50mm -> rounds to 2px, even
    expect(snapPhaseFor(3.78)).toBe(0);   // 1.00mm -> rounds to 4px, even
  });
});

describe('snapWorldToDeviceGrid', () => {
  const scale = 0.813;

  it.each([1, 1.25, 1.5, 2])('lands on a half-integer device pixel at dpr %s', (dpr) => {
    for (const translate of [0, 0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.9, 13.37]) {
      for (const world of [0, 3.5, 91.27, 512.9]) {
        const snapped = snapWorldToDeviceGrid(world, scale, translate, dpr, 0.5);
        const device = toDevice(snapped, scale, translate, dpr);
        // Exactly half way between two pixel boundaries => the stroke fills one whole column.
        expect(Math.abs(device - Math.floor(device) - 0.5)).toBeLessThan(1e-9);
      }
    }
  });

  it('lands on an integer device pixel when asked for phase 0', () => {
    const snapped = snapWorldToDeviceGrid(91.27, scale, 0.37, 1.25, 0);
    const device = toDevice(snapped, scale, 0.37, 1.25);
    expect(Math.abs(device - Math.round(device))).toBeLessThan(1e-9);
  });

  it('never moves a coordinate by as much as one device pixel', () => {
    // The whole safety argument: at fit-to-screen this is well under a drawing unit, far below
    // the placement oracle's 1.27 max |dx|.
    for (const world of [0, 3.5, 91.27, 512.9, -44.1]) {
      const dpr = 1.5;
      const snapped = snapWorldToDeviceGrid(world, scale, 0.42, dpr, 0.5);
      const movedDevicePx = Math.abs(toDevice(snapped, scale, 0.42, dpr) - toDevice(world, scale, 0.42, dpr));
      expect(movedDevicePx).toBeLessThanOrEqual(0.5 + 1e-9);
    }
  });
});

describe('isAxisAlignedChain', () => {
  it('accepts a closed rectangle — the title-block and frame case', () => {
    expect(isAxisAlignedChain([[0, 0], [10, 0], [10, 5], [0, 5], [0, 0]])).toBe(true);
  });

  it('accepts a single horizontal or vertical segment', () => {
    expect(isAxisAlignedChain([[0, 3], [10, 3]])).toBe(true);
    expect(isAxisAlignedChain([[7, 0], [7, 9]])).toBe(true);
  });

  it('rejects a chain containing any diagonal', () => {
    // Snapping one segment of a mixed chain detaches it from its diagonal neighbour and opens
    // a visible kink, so these must be left alone entirely.
    expect(isAxisAlignedChain([[0, 0], [10, 0], [12, 4]])).toBe(false);
  });

  it('tolerates float noise rather than calling it a diagonal', () => {
    expect(isAxisAlignedChain([[0, 0], [10, 1e-12]])).toBe(true);
  });
});
