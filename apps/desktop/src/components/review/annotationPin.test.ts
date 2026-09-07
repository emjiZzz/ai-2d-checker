/**
 * annotationPin.test.ts
 *
 * Verifies the coordinate contract that annotation pinning depends on:
 * a pin created from a canvas click must render back at the same pixel, and
 * the stored coordinates must live in the same CAD space as violation
 * coordinates (so the zoom-to-pin effect can reuse the violation transform).
 *
 * Bounds fixtures are the real render_bounds of the two drawings currently
 * ingested in the app's database, so this exercises production geometry rather
 * than idealised values.
 */
import { describe, it, expect } from 'vitest';
import {
  getNormalization,
  worldToScreen,
  screenToWorld,
  parseBounds,
} from '../../utils/coordinateTransform';

// Real render_bounds from the ingested drawings (see GET /api/v1/drawings).
const KMTI_BOUNDS = [-21.0, -14.850000000000001, 441.0, 311.85];
const REFERENCE_BOUNDS = [-52.5, -37.125, 1102.5, 779.625];

describe('annotation pin placement round-trip', () => {
  // Clicking the canvas stores screenToWorld(...) output as the pin's
  // coordinates; rendering feeds those back through worldToScreen. If these
  // aren't exact inverses the pin visibly drifts from where the user clicked.
  it.each([
    ['kmti', KMTI_BOUNDS],
    ['reference', REFERENCE_BOUNDS],
  ])('renders a pin at the exact pixel it was placed (%s drawing)', (_name, rawBounds) => {
    const norm = getNormalization(parseBounds(rawBounds));
    const viewport = { x: 120, y: -45, scale: 2.3 };

    // A few representative click positions across the canvas.
    const clicks = [
      { mx: 0, my: 0 },
      { mx: 640, my: 360 },
      { mx: 1279, my: 719 },
      { mx: 37.5, my: 512.25 },
    ];

    for (const { mx, my } of clicks) {
      const world = screenToWorld(mx, my, norm, viewport);
      const back = worldToScreen(world.x, world.y, norm, viewport);
      expect(back.x).toBeCloseTo(mx, 6);
      expect(back.y).toBeCloseTo(my, 6);
    }
  });

  it('round-trips across zoom levels, so pins stay anchored while zooming', () => {
    const norm = getNormalization(parseBounds(KMTI_BOUNDS));
    const mx = 400;
    const my = 275;

    for (const scale of [0.81, 1, 2.2, 6, 25]) {
      const viewport = { x: 15, y: 60, scale };
      const world = screenToWorld(mx, my, norm, viewport);
      const back = worldToScreen(world.x, world.y, norm, viewport);
      expect(back.x).toBeCloseTo(mx, 6);
      expect(back.y).toBeCloseTo(my, 6);
    }
  });

  it('stores pins in CAD space (Y-up), matching the violation coordinate convention', () => {
    const bounds = parseBounds(KMTI_BOUNDS)!;
    const norm = getNormalization(bounds);
    const viewport = { x: 0, y: 0, scale: 1 };

    // Clicking nearer the top of the canvas must yield a LARGER CAD Y than
    // clicking nearer the bottom — this is the Y-flip the zoom-to-pin effect
    // re-applies via (ymax + ymin - y). If this inverts, zoom-to-pin jumps to
    // a mirrored location.
    const top = screenToWorld(500, 50, norm, viewport);
    const bottom = screenToWorld(500, 650, norm, viewport);
    expect(top.y).toBeGreaterThan(bottom.y);

    // And resulting values sit inside the drawing's CAD bounds.
    expect(top.y).toBeGreaterThanOrEqual(bounds.ymin);
    expect(top.y).toBeLessThanOrEqual(bounds.ymax);
  });

  it('reproduces the zoom-to-pin centering math used for selected annotations', () => {
    // Mirrors the selectedAnnotationId effect in useCanvasInteraction.ts:
    // a pin at a known CAD point should end up centered in the viewport.
    const bounds = parseBounds(KMTI_BOUNDS)!;
    const norm = getNormalization(bounds);
    const width = 1280;
    const height = 720;

    const ax = 210.0;
    const ay = 148.5;

    const stdX = (ax - norm.xmin) * norm.normScale;
    const ay_inverted = norm.hasBounds ? norm.ymax + norm.ymin - ay : ay;
    const stdY = (ay_inverted - norm.ymin) * norm.normScale;

    const drawingDim = Math.max(bounds.xmax - bounds.xmin, bounds.ymax - bounds.ymin);
    const targetScale = Math.min(6.0, Math.max(1.5, (width * 0.45) / (drawingDim * norm.normScale)));
    const popoverOffsetX = 80;
    const popoverOffsetY = -50;
    const targetX = width / 2 - stdX * targetScale - popoverOffsetX;
    const targetY = height / 2 - stdY * targetScale - popoverOffsetY;

    // Feeding the computed viewport back through worldToScreen must land the
    // pin at the canvas offset center.
    const screen = worldToScreen(ax, ay, norm, { x: targetX, y: targetY, scale: targetScale });
    expect(screen.x).toBeCloseTo(width / 2 - popoverOffsetX, 6);
    expect(screen.y).toBeCloseTo(height / 2 - popoverOffsetY, 6);

    // Scale must stay inside the clamp range the effect promises.
    expect(targetScale).toBeGreaterThanOrEqual(1.5);
    expect(targetScale).toBeLessThanOrEqual(6.0);
  });
});
