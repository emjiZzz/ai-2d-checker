/**
 * coordinateTransform.test.ts
 *
 * Characterization tests — input/output pairs derived from the *current* behavior
 * of the 6-7 duplicated inline blocks in DrawingCanvas.tsx. These are not
 * aspirational tests; they pin what the code actually does today.
 *
 * If a test fails after replacing a call site in DrawingCanvas.tsx, it means
 * the replacement changed behavior — stop and diff byte-for-byte against the original.
 */
import { describe, it, expect } from 'vitest';
import {
  getNormalization,
  worldToScreen,
  screenToWorld,
  parseBounds,
} from './coordinateTransform';

// ---------------------------------------------------------------------------
// Shared fixtures representing a typical A3-sized CAD drawing's render_bounds
// [xmin, ymin, xmax, ymax] in CAD units. Values are representative of real
// drawings seen in the app (large positive coordinates, non-zero origin).
// ---------------------------------------------------------------------------
const BOUNDS = { xmin: 100, ymin: 200, xmax: 1100, ymax: 900 }; // width=1000, height=700
const VIEWPORT = { x: 50, y: 30, scale: 1.5 };

// ---------------------------------------------------------------------------
// getNormalization()
// ---------------------------------------------------------------------------
describe('getNormalization', () => {
  it('returns hasBounds:false for null input', () => {
    const result = getNormalization(null);
    expect(result.hasBounds).toBe(false);
    expect(result.normScale).toBe(1);
    expect(result.xmin).toBe(0);
    expect(result.ymin).toBe(0);
    expect(result.ymax).toBe(0);
  });

  it('returns hasBounds:false for undefined input', () => {
    const result = getNormalization(undefined);
    expect(result.hasBounds).toBe(false);
  });

  it('returns hasBounds:false when width is zero', () => {
    const result = getNormalization({ xmin: 100, ymin: 0, xmax: 100, ymax: 500 });
    expect(result.hasBounds).toBe(false);
  });

  it('returns hasBounds:false when width is negative', () => {
    const result = getNormalization({ xmin: 200, ymin: 0, xmax: 100, ymax: 500 });
    expect(result.hasBounds).toBe(false);
  });

  it('computes correct normScale for width=1000 bounds (the standard CAD case)', () => {
    // BOUNDS width = 1100 - 100 = 1000, so normScale = 1000 / 1000 = 1.0
    const result = getNormalization(BOUNDS);
    expect(result.hasBounds).toBe(true);
    if (!result.hasBounds) return; // narrow for TS
    expect(result.normScale).toBe(1.0);
    expect(result.xmin).toBe(100);
    expect(result.ymin).toBe(200);
    expect(result.ymax).toBe(900);
  });

  it('computes correct normScale for width=500 bounds', () => {
    // normScale = 1000 / 500 = 2.0
    const result = getNormalization({ xmin: 0, ymin: 0, xmax: 500, ymax: 300 });
    expect(result.hasBounds).toBe(true);
    if (!result.hasBounds) return;
    expect(result.normScale).toBe(2.0);
  });

  it('computes correct normScale for width=2000 bounds', () => {
    // normScale = 1000 / 2000 = 0.5
    const result = getNormalization({ xmin: 0, ymin: 0, xmax: 2000, ymax: 1000 });
    expect(result.hasBounds).toBe(true);
    if (!result.hasBounds) return;
    expect(result.normScale).toBe(0.5);
  });
});

// ---------------------------------------------------------------------------
// worldToScreen()
// Sites B, C, D, G — the Y-flipping worldToScreen pattern
// ---------------------------------------------------------------------------
describe('worldToScreen', () => {
  const norm = getNormalization(BOUNDS);

  it('maps the world origin corner (xmin, ymin+height = ymax → flipped to ymin) correctly', () => {
    // Point at CAD (xmin=100, ymax=900) maps to screen origin of the drawing
    // flippedY = ymax + ymin - ymax = ymin = 200
    // x = (100 - 100) * (1.5 * 1.0) + 50 = 0 + 50 = 50
    // y = (200 - 200) * 1.5 + 30 = 0 + 30 = 30
    const result = worldToScreen(100, 900, norm, VIEWPORT);
    expect(result.x).toBeCloseTo(50);
    expect(result.y).toBeCloseTo(30);
  });

  it('maps (xmin, ymin) to the bottom-left equivalent screen position', () => {
    // flippedY = 900 + 200 - 200 = 900 (maps to "bottom" in canvas)
    // x = (100 - 100) * 1.5 + 50 = 50
    // y = (900 - 200) * 1.5 + 30 = 700 * 1.5 + 30 = 1050 + 30 = 1080
    const result = worldToScreen(100, 200, norm, VIEWPORT);
    expect(result.x).toBeCloseTo(50);
    expect(result.y).toBeCloseTo(1080);
  });

  it('maps the center of the drawing to the screen center equivalent', () => {
    // CAD center: wx=600, wy=550
    // flippedY = 900 + 200 - 550 = 550 (symmetric center)
    // x = (600 - 100) * 1.5 + 50 = 500 * 1.5 + 50 = 800
    // y = (550 - 200) * 1.5 + 30 = 350 * 1.5 + 30 = 525 + 30 = 555
    const result = worldToScreen(600, 550, norm, VIEWPORT);
    expect(result.x).toBeCloseTo(800);
    expect(result.y).toBeCloseTo(555);
  });

  it('passes Y through unchanged when hasBounds is false', () => {
    const noNorm = getNormalization(null);
    // effectiveScale = 1.5 * 1 = 1.5
    // x = (200 - 0) * 1.5 + 50 = 350
    // y = (300 - 0) * 1.5 + 30 = 480 (no flip)
    const result = worldToScreen(200, 300, noNorm, VIEWPORT);
    expect(result.x).toBeCloseTo(350);
    expect(result.y).toBeCloseTo(480);
  });

  it('round-trips correctly with screenToWorld (hasBounds=true)', () => {
    const wx = 450;
    const wy = 700;
    const screen = worldToScreen(wx, wy, norm, VIEWPORT);
    const world = screenToWorld(screen.x, screen.y, norm, VIEWPORT);
    expect(world.x).toBeCloseTo(wx, 10);
    expect(world.y).toBeCloseTo(wy, 10);
  });

  it('round-trips correctly with screenToWorld (hasBounds=false)', () => {
    const noNorm = getNormalization(null);
    const wx = 450;
    const wy = 700;
    const screen = worldToScreen(wx, wy, noNorm, VIEWPORT);
    const world = screenToWorld(screen.x, screen.y, noNorm, VIEWPORT);
    expect(world.x).toBeCloseTo(wx, 10);
    expect(world.y).toBeCloseTo(wy, 10);
  });
});

// ---------------------------------------------------------------------------
// screenToWorld()
// Inverse of worldToScreen. Used in hit-testing (Sites D, G) and ROI (Site E).
// ---------------------------------------------------------------------------
describe('screenToWorld', () => {
  const norm = getNormalization(BOUNDS);

  it('converts screen (50, 30) back to world origin (100, 900)', () => {
    // This is the inverse of the first worldToScreen test
    const result = screenToWorld(50, 30, norm, VIEWPORT);
    expect(result.x).toBeCloseTo(100);
    expect(result.y).toBeCloseTo(900);
  });

  it('converts screen (50, 1080) back to world (100, 200)', () => {
    const result = screenToWorld(50, 1080, norm, VIEWPORT);
    expect(result.x).toBeCloseTo(100);
    expect(result.y).toBeCloseTo(200);
  });

  it('passes Y through unchanged when hasBounds is false', () => {
    const noNorm = getNormalization(null);
    // sx=350, sy=480 → wx=200, wy=300 (inverse of the worldToScreen no-bounds test)
    const result = screenToWorld(350, 480, noNorm, VIEWPORT);
    expect(result.x).toBeCloseTo(200);
    expect(result.y).toBeCloseTo(300);
  });
});

// ---------------------------------------------------------------------------
// Site F — laser-sync sign-inverted Y
// REFACTOR-NOTE: handleMouseMove (line ~1274) computes:
//   stdY = ymin - (my - viewport.y) / effectiveScale
// This is NOT screenToWorld — it deliberately inverts Y sign for laser sync.
// This behavior is NOT consolidated into coordinateTransform.ts; it stays inline
// because it has a different semantic (laser coords, not CAD Y-flip).
// The test below documents what that site actually computes, for reference.
// ---------------------------------------------------------------------------
describe('Site F laser-sync stdY (documented, stays inline in DrawingCanvas.tsx)', () => {
  it('sign-inverted Y matches original formula: ymin - (sy - viewport.y) / effectiveScale', () => {
    const norm = getNormalization(BOUNDS);
    const effectiveScale = VIEWPORT.scale * norm.normScale; // 1.5 * 1 = 1.5
    const my = 555; // a mouse Y position
    // Original site F formula:
    const stdY_original = BOUNDS.ymin - (my - VIEWPORT.y) / effectiveScale;
    // = 200 - (555 - 30) / 1.5
    // = 200 - 525 / 1.5
    // = 200 - 350 = -150

    // For comparison, screenToWorld Y (with Y-flip) would give:
    const via_screenToWorld = screenToWorld(0, my, getNormalization(BOUNDS), VIEWPORT).y;
    // rawWy = 200 + (555 - 30) / 1.5 = 200 + 350 = 550
    // flipped = 900 + 200 - 550 = 550

    expect(stdY_original).toBeCloseTo(-150);
    // Confirm they are NOT the same — this is the intentional behavioral difference
    expect(stdY_original).not.toBeCloseTo(via_screenToWorld);
  });
});

// ---------------------------------------------------------------------------
// parseBounds()
// ---------------------------------------------------------------------------
describe('parseBounds', () => {
  it('returns null for null input', () => {
    expect(parseBounds(null)).toBeNull();
  });

  it('returns null for undefined input', () => {
    expect(parseBounds(undefined)).toBeNull();
  });

  it('returns null for array shorter than 4', () => {
    expect(parseBounds([1, 2, 3])).toBeNull();
  });

  it('correctly parses a 4-element array', () => {
    const result = parseBounds([100, 200, 1100, 900]);
    expect(result).toEqual({ xmin: 100, ymin: 200, xmax: 1100, ymax: 900 });
  });

  it('correctly parses from drawing.metadata.render_bounds style array', () => {
    const drawing = { metadata: { render_bounds: [0, 0, 500, 300] } };
    const result = parseBounds(drawing.metadata.render_bounds);
    expect(result).toEqual({ xmin: 0, ymin: 0, xmax: 500, ymax: 300 });
  });

  it('getNormalization works correctly when fed output of parseBounds', () => {
    const bounds = parseBounds([100, 200, 1100, 900]);
    const norm = getNormalization(bounds);
    expect(norm.hasBounds).toBe(true);
    if (!norm.hasBounds) return;
    expect(norm.normScale).toBe(1.0);
  });
});
