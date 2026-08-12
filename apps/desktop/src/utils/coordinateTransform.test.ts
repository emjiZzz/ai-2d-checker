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
  screenToWorldUnflipped,
  screenDeltaToWorldDelta,
  flipWorldY,
  boundsMatch,
  cadPointToPair,
  cadPointToScreen,
  parseBounds,
  type CadPoint,
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
// flipWorldY()
// The mirror on its own, for callers that stay in world space and let the canvas
// ctx transform apply scale and pan. Extracted after renderViewOrigins shipped
// without it — see the function's own note.
// ---------------------------------------------------------------------------
describe('flipWorldY', () => {
  const norm = getNormalization(BOUNDS);

  it('mirrors about the centreline of the bounds', () => {
    // BOUNDS spans y 200..900, so the centreline is 550 and ymax+ymin = 1100.
    expect(flipWorldY(200, norm)).toBe(900);
    expect(flipWorldY(900, norm)).toBe(200);
    expect(flipWorldY(550, norm)).toBe(550); // the fixed point
  });

  it('moves a point far from the centreline much further than a point near it', () => {
    // Why the missing flip in renderViewOrigins looked plausible: the two central
    // viewports moved a handful of units, the isometric one moved half the sheet.
    expect(Math.abs(flipWorldY(560, norm) - 560)).toBe(20);
    expect(Math.abs(flipWorldY(880, norm) - 880)).toBe(660);
  });

  it('is its own inverse', () => {
    expect(flipWorldY(flipWorldY(742.5, norm), norm)).toBeCloseTo(742.5, 10);
  });

  it('passes through unchanged with no bounds — a guessed centreline is worse', () => {
    expect(flipWorldY(742.5, getNormalization(null))).toBe(742.5);
  });

  it('agrees with the Y that worldToScreen bakes in', () => {
    // The two must not drift apart: worldToScreen is the screen-space path, flipWorldY
    // the world-space one, and they have to mirror about the same line.
    const screen = worldToScreen(300, 880, norm, VIEWPORT);
    const effectiveScale = VIEWPORT.scale * norm.normScale;
    expect(screen.y).toBeCloseTo((flipWorldY(880, norm) - norm.ymin) * effectiveScale + VIEWPORT.y, 10);
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
// ---------------------------------------------------------------------------
// The two deliberate deviations from the Y-flip, now named functions rather than
// inline maths guarded by a "do not fix" comment.
//
// CORRECTION: this block previously characterized a "Site F laser-sync" formula
// (`ymin - (sy - viewport.y) / effectiveScale`) described as staying inline in
// DrawingCanvas.tsx. No such call site exists — it is a pure-arithmetic assertion that
// passed regardless of the code. What actually deviates is the drag-delta sign
// inversion, covered below.
// ---------------------------------------------------------------------------
describe('screenToWorldUnflipped (ROI percentage space)', () => {
  it('skips the Y-flip that screenToWorld applies', () => {
    const norm = getNormalization(BOUNDS);
    // Deliberately not the vertical midpoint of BOUNDS: the flip is an involution, so
    // at y = (ymin + ymax) / 2 = 550 it is the identity and the two agree by accident.
    const sy = 300;
    const flipped = screenToWorld(400, sy, norm, VIEWPORT);
    const unflipped = screenToWorldUnflipped(400, sy, norm, VIEWPORT);

    // X is unaffected by the flip.
    expect(unflipped.x).toBeCloseTo(flipped.x);
    // Y is the raw, unmirrored value: ymin + (sy - viewport.y) / effectiveScale.
    expect(unflipped.y).toBeCloseTo(200 + (300 - 30) / 1.5); // 380
    expect(flipped.y).toBeCloseTo(900 + 200 - 380); // 720
    expect(unflipped.y).not.toBeCloseTo(flipped.y);
  });

  it('is the identity relative to screenToWorld at the fixed point of the flip', () => {
    // Documents the coincidence above so a future reader does not mistake it for a bug.
    const norm = getNormalization(BOUNDS);
    const midpointScreen = 555; // maps to world Y 550 = (200 + 900) / 2
    expect(screenToWorldUnflipped(0, midpointScreen, norm, VIEWPORT).y).toBeCloseTo(
      screenToWorld(0, midpointScreen, norm, VIEWPORT).y,
    );
  });

  it('matches screenToWorld exactly when there are no bounds (no flip to skip)', () => {
    const norm = getNormalization(null);
    expect(screenToWorldUnflipped(400, 555, norm, VIEWPORT)).toEqual(
      screenToWorld(400, 555, norm, VIEWPORT),
    );
  });
});

describe('screenDeltaToWorldDelta (marker and pin drags)', () => {
  it('sign-inverts Y under a flip so a downward drag decreases world Y', () => {
    const norm = getNormalization(BOUNDS);
    const { dx, dy } = screenDeltaToWorldDelta(30, 60, norm, VIEWPORT);
    expect(dx).toBeCloseTo(30 / 1.5); // 20
    expect(dy).toBeCloseTo(-(60 / 1.5)); // -40
  });

  it('passes Y through unchanged when there are no bounds', () => {
    const norm = getNormalization(null);
    const { dy } = screenDeltaToWorldDelta(0, 60, norm, VIEWPORT);
    expect(dy).toBeCloseTo(60 / 1.5);
  });

  it('agrees with the difference of two point transforms', () => {
    // The Y-flip's linear part is -1, so it negates differences and transforming both
    // drag endpoints gives the same answer. This function is not a correction to that;
    // it exists because drags are tracked as a delta from a start position, and to keep
    // the sign inversion in one named place rather than copy-pasted at each drag site.
    const norm = getNormalization(BOUNDS);
    const a = screenToWorld(0, 100, norm, VIEWPORT);
    const b = screenToWorld(0, 160, norm, VIEWPORT);
    const { dy } = screenDeltaToWorldDelta(0, 60, norm, VIEWPORT);

    expect(b.y - a.y).toBeCloseTo(dy);
    expect(dy).toBeLessThan(0); // downward drag decreases world Y
  });
});

// ---------------------------------------------------------------------------
// Coordinate provenance
// ---------------------------------------------------------------------------
const stampedPoint = (overrides: Partial<CadPoint> = {}): CadPoint => ({
  x: 600,
  y: 550,
  space: 'paper',
  layout: 'Layout1',
  viewport_index: 0,
  transform_version: 1,
  bounds: [100, 200, 1100, 900],
  ...overrides,
});

describe('cadPointToPair', () => {
  it('unwraps an envelope to the bare pair the canvas works in', () => {
    expect(cadPointToPair(stampedPoint())).toEqual([600, 550]);
  });

  it('returns null for missing or malformed input', () => {
    expect(cadPointToPair(null)).toBeNull();
    expect(cadPointToPair(undefined)).toBeNull();
    expect(cadPointToPair({ x: 'a' } as unknown as CadPoint)).toBeNull();
  });
});

describe('cadPointToScreen', () => {
  it('agrees with worldToScreen on the same coordinates', () => {
    const norm = getNormalization(BOUNDS);
    const point = stampedPoint();
    expect(cadPointToScreen(point, norm, VIEWPORT)).toEqual(
      worldToScreen(point.x, point.y, norm, VIEWPORT),
    );
  });
});

describe('boundsMatch (drift detection)', () => {
  it('is true when the drawing has not been re-rendered', () => {
    expect(boundsMatch(stampedPoint(), BOUNDS)).toBe(true);
  });

  it('is false once the drawing is re-rendered against different bounds', () => {
    // A different paper-space layout becomes the render target on re-ingest, which
    // used to displace every stored pin silently.
    expect(boundsMatch(stampedPoint(), { xmin: 0, ymin: 0, xmax: 841, ymax: 594 })).toBe(false);
  });

  it('treats unknown provenance as not-drifted — absence of evidence is not drift', () => {
    expect(boundsMatch(stampedPoint({ bounds: null }), BOUNDS)).toBe(true);
    expect(boundsMatch(null, BOUNDS)).toBe(true);
    expect(boundsMatch(stampedPoint(), null)).toBe(true);
  });

  it('tolerates float noise within epsilon', () => {
    const nudged = { xmin: 100 + 1e-9, ymin: 200, xmax: 1100, ymax: 900 };
    expect(boundsMatch(stampedPoint(), nudged)).toBe(true);
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
