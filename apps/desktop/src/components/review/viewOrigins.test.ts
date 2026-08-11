/**
 * Per-view ORIGIN markers.
 *
 * iCAD SX draws one ORIGIN per view. On `M745221N01_FSRS2` that is three — 正面図, sectA and
 * isome1 — and each sits at its viewport's **anchor** (the DXF `view_target_point`), which by
 * construction projects to that viewport's paper centre.
 *
 * The distinction this file exists to protect: that is NOT the global model origin. `(0,0)`
 * projected through the same viewports lands outside two of the three viewport rectangles on
 * this sheet — visible only in the front view. Reading the anchor as if it were
 * `view_center_point` (which is `(0,0,0)` on all three of this sheet's viewports) produces the
 * second answer while looking like the first, and every number involved stays finite.
 *
 * Mirrors `Viewport.origin_paper_point` in `viewport_transform.py`.
 */
import { describe, expect, it } from 'vitest';

import { renderViewOrigins, viewOriginsFromTransform } from './renderEntities';

/** The real stored transform, legacy `view_center` spelling exactly as it sits in MongoDB. */
const TRANSFORM = {
  version: 1,
  layout: 'ICADSX Layout',
  viewports: [
    {
      index: 0, handle: '299',
      paper_center: [162.0939969443204, 157.3243865966797],
      paper_size: [122.7426756727831, 131.25],
      view_center: [-31.10910862365456, 0.0],
      view_height: 183.75, scale: 0.7142857142857143,
    },
    {
      index: 1, handle: '2D2',
      paper_center: [247.0576406882221, 145.5561857223511],
      paper_size: [48.37035012358122, 133.4632218360901],
      view_center: [-80.6906589897892, -351.47548122406],
      view_height: 186.8485105705261, scale: 0.7142857142857145,
    },
    {
      index: 2, handle: '2D5',
      paper_center: [367.0346824647803, 224.7647857666016],
      paper_size: [37.371, 47.186],
      view_center: [69.437, -329.908],
      view_height: 141.5566, scale: 0.3333333333333333,
    },
  ],
};

/** Counts the paint calls without needing a real canvas. */
function countingCtx() {
  const calls = { stroke: 0, fill: 0, strokeRect: 0 };
  const noop = () => {};
  const ctx: any = new Proxy({}, {
    get: (_t, k) => {
      if (k === 'stroke') return () => { calls.stroke++; };
      if (k === 'fill') return () => { calls.fill++; };
      if (k === 'strokeRect') return () => { calls.strokeRect++; };
      return noop;
    },
    set: () => true,
  });
  return { ctx, calls };
}

const frame = (ctx: any, isExport = false) =>
  ({ ctx, isExport, scale: 0.8, resolutionMultiplier: 1 } as any);

describe('viewOriginsFromTransform', () => {
  it('locates all three of this sheet\'s view origins', () => {
    const origins = viewOriginsFromTransform(TRANSFORM);
    expect(origins.map(o => o.handle)).toEqual(['299', '2D2', '2D5']);
    // Measured against the backend's own projection of the same stored transform.
    expect(origins[0].x).toBeCloseTo(162.094, 3);
    expect(origins[0].y).toBeCloseTo(157.324, 3);
    expect(origins[1].x).toBeCloseTo(247.058, 3);
    expect(origins[1].y).toBeCloseTo(145.556, 3);
    expect(origins[2].x).toBeCloseTo(367.035, 3);
    expect(origins[2].y).toBeCloseTo(224.765, 3);
  });

  it('puts every origin inside its own viewport rectangle', () => {
    // The property that distinguishes the anchor reading from the global-origin one: read it
    // wrong and two of these three fall outside the box they are supposed to mark.
    viewOriginsFromTransform(TRANSFORM).forEach((o, i) => {
      const vp = TRANSFORM.viewports[i];
      expect(Math.abs(o.x - vp.paper_center[0])).toBeLessThanOrEqual(vp.paper_size[0] / 2);
      expect(Math.abs(o.y - vp.paper_center[1])).toBeLessThanOrEqual(vp.paper_size[1] / 2);
    });
  });

  it('reads the new view_anchor key as well as the legacy one', () => {
    const modern = { viewports: [{ ...TRANSFORM.viewports[0], view_anchor: [-31.109, 0], view_center: undefined }] };
    expect(viewOriginsFromTransform(modern)[0].x).toBeCloseTo(162.094, 3);
  });

  it('returns nothing rather than throwing on a drawing with no viewports', () => {
    expect(viewOriginsFromTransform({ viewports: [] })).toEqual([]);
    expect(viewOriginsFromTransform(null)).toEqual([]);
    expect(viewOriginsFromTransform(undefined)).toEqual([]);
    expect(viewOriginsFromTransform({})).toEqual([]);
  });

  it('skips a viewport with a malformed paper_center instead of drawing at NaN', () => {
    const bad = { viewports: [
      { handle: 'A', paper_center: [Number.NaN, 1], scale: 1 },
      { handle: 'B', paper_center: null, scale: 1 },
      { handle: 'C', paper_center: [5, 6], scale: 1 },
    ] };
    expect(viewOriginsFromTransform(bad).map(o => o.handle)).toEqual(['C']);
  });
});

describe('renderViewOrigins', () => {
  it('paints one marker per view — two arrowheads and a datum box each', () => {
    const { ctx, calls } = countingCtx();
    renderViewOrigins({ frame: frame(ctx), drawing: { metadata: { viewport_transform: TRANSFORM } } });
    expect(calls.stroke).toBe(3);      // the two arms, one stroke per marker
    expect(calls.fill).toBe(6);        // X and Y arrowheads
    expect(calls.strokeRect).toBe(3);  // the datum square
  });

  it('paints nothing on a drawing with no paper-space viewports', () => {
    // The DWG-exported reference sheets: everything in model space, no viewports, no origins.
    const { ctx, calls } = countingCtx();
    renderViewOrigins({ frame: frame(ctx), drawing: { metadata: { viewport_transform: { viewports: [] } } } });
    expect(calls).toEqual({ stroke: 0, fill: 0, strokeRect: 0 });
  });

  it('paints nothing when the drawing has no metadata at all', () => {
    const { ctx, calls } = countingCtx();
    renderViewOrigins({ frame: frame(ctx), drawing: {} });
    renderViewOrigins({ frame: frame(ctx), drawing: undefined });
    expect(calls).toEqual({ stroke: 0, fill: 0, strokeRect: 0 });
  });

  it('is skipped on export — it is a reference overlay, not part of the sheet', () => {
    const { ctx, calls } = countingCtx();
    renderViewOrigins({ frame: frame(ctx, true), drawing: { metadata: { viewport_transform: TRANSFORM } } });
    expect(calls).toEqual({ stroke: 0, fill: 0, strokeRect: 0 });
  });
});
