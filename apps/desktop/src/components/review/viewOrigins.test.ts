/**
 * Drawing the per-view ORIGIN markers.
 *
 * Placement only — *where* each datum is comes from `viewDatums.ts` and is tested there. This
 * file covers what the renderer does with them, and exists because both of this overlay's
 * defects were invisible to the suite it had:
 *
 *  1. Every marker was drawn **mirrored** about the sheet's centreline, because world space on
 *     this canvas is Y-DOWN and this is the only overlay that stays in it.
 *     See `Gotcha - A Missing Y Flip Is Invisible Near the Centreline`.
 *  2. The datums themselves were the viewport's window centre — a tautology.
 *     See `Gotcha - The View Origin Marker Marked the Middle of the Window`.
 *
 * Neither was catchable, because the old tests drove a context that **counted paint calls and
 * discarded every coordinate**. Three markers were painted; all three were in the wrong place
 * with their arms pointing the wrong way, and the suite was green.
 */
import { describe, expect, it } from 'vitest';

import { renderViewOrigins } from './renderEntities';
import type { ViewDatum } from './viewDatums';

/** The three real datums of `M745221N01_FSRS2`, as `viewDatums.ts` computes them. */
const DATUMS: ViewDatum[] = [
  { handle: '299', x: 184.3147888183594, y: 157.3243865966797, scale: 0.7142857142857143, source: 'ucs_origin', inferred: false },
  { handle: '2D2', x: 257.234, y: 157.32438659667966, scale: 0.7142857142857145, source: 'centerline_axis', inferred: true },
  { handle: '2D5', x: 366.3276, y: 224.3567, scale: 0.33333333333333337, source: 'concentric', inferred: true },
];

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

/**
 * Records WHERE things are drawn and WITH WHAT DASH, not just how many times.
 *
 * `strokeDashes` captures the dash pattern in force at each `stroke()` — the only way to see
 * the extracted/inferred distinction, since it is carried entirely in the line style.
 */
function recordingCtx() {
  const moves: [number, number][] = [];
  const lines: [number, number][] = [];
  const rects: [number, number, number, number][] = [];
  const strokeDashes: number[][] = [];
  const rectDashes: number[][] = [];
  let dash: number[] = [];
  const noop = () => {};
  const ctx: any = new Proxy({}, {
    get: (_t, k) => {
      if (k === 'moveTo') return (x: number, y: number) => { moves.push([x, y]); };
      if (k === 'lineTo') return (x: number, y: number) => { lines.push([x, y]); };
      if (k === 'setLineDash') return (d: number[]) => { dash = d; };
      if (k === 'stroke') return () => { strokeDashes.push(dash); };
      if (k === 'strokeRect') return (x: number, y: number, w: number, h: number) => {
        rects.push([x, y, w, h]);
        rectDashes.push(dash);
      };
      return noop;
    },
    set: () => true,
  });
  return { ctx, moves, lines, rects, strokeDashes, rectDashes };
}

/** `render_bounds` of M745221N01_FSRS2, so `flipY(y) = 311.9 + -14.9 - y = 297.0 - y`. */
const NORM = { hasBounds: true, xmin: -21.0, ymin: -14.9, xmax: 441.0, ymax: 311.9 };

const frame = (ctx: any, isExport = false, norm: any = NORM) =>
  ({ ctx, isExport, scale: 0.8, resolutionMultiplier: 1, norm } as any);

describe('renderViewOrigins', () => {
  it('paints one marker per datum — two arrowheads and a corner box each', () => {
    const { ctx, calls } = countingCtx();
    renderViewOrigins({ frame: frame(ctx), datums: DATUMS });
    expect(calls.stroke).toBe(3);      // the two arms, one stroke per marker
    expect(calls.fill).toBe(6);        // X and Y arrowheads
    expect(calls.strokeRect).toBe(3);  // the corner square
  });

  it('paints nothing when no view had a determinable datum', () => {
    // Not a degenerate case: a view with no centrelines and nothing concentric is left unmarked
    // rather than guessed, and the DWG-exported reference sheets have no viewports at all.
    const { ctx, calls } = countingCtx();
    renderViewOrigins({ frame: frame(ctx), datums: [] });
    renderViewOrigins({ frame: frame(ctx), datums: undefined });
    expect(calls).toEqual({ stroke: 0, fill: 0, strokeRect: 0 });
  });

  it('mirrors each datum into the canvas Y-DOWN world instead of drawing at the raw paper Y', () => {
    // `CanvasRenderer` uses `ctx.scale(scale, scale)` with NO negative, and entities are mirrored
    // at draw time via `flipY`. A marker drawn at the raw paper `y` is reflected about the
    // sheet's centreline. The error grows with distance from that line, so the two central views
    // looked fine and only the isometric one gave it away — 152 units, drawn at the bottom of a
    // sheet whose view sits at the top.
    const { ctx, moves } = recordingCtx();
    renderViewOrigins({ frame: frame(ctx), datums: DATUMS });

    // Four moveTo per marker: the two arms, then the two arrowheads. The corner is the first.
    const corners = [moves[0], moves[4], moves[8]];
    expect(corners[0][1]).toBeCloseTo(297.0 - 157.3243865966797, 6);
    expect(corners[1][1]).toBeCloseTo(297.0 - 157.32438659667966, 6);
    expect(corners[2][1]).toBeCloseTo(297.0 - 224.3567, 6);
    // The isometric marker belongs in the TOP half of a sheet spanning -14.9..311.9.
    expect(corners[2][1]).toBeLessThan(148.5);
  });

  it('draws X unmirrored — the flip is one axis, and mirroring both would look plausible too', () => {
    const { ctx, moves } = recordingCtx();
    renderViewOrigins({ frame: frame(ctx), datums: DATUMS });
    expect(moves[0][0]).toBeCloseTo(184.3147888183594, 6);
    expect(moves[8][0]).toBeCloseTo(366.3276, 6);
  });

  it('points the Y arm UP on screen, which is toward -y in this world', () => {
    const { ctx, moves, lines } = recordingCtx();
    renderViewOrigins({ frame: frame(ctx), datums: DATUMS });

    const cornerY = moves[0][1];
    const armEnds = lines.slice(0, 2); // X arm then Y arm, for the first marker
    expect(armEnds[0][0]).toBeGreaterThan(moves[0][0]);  // X arm runs right
    expect(armEnds[1][1]).toBeLessThan(cornerY);         // Y arm runs up (smaller y)
  });

  it('draws the corner square into the same quadrant as the arms', () => {
    // Up and to the right. A positive height would put it below the corner, on the opposite
    // side from both arms.
    const { ctx, moves, rects } = recordingCtx();
    renderViewOrigins({ frame: frame(ctx), datums: DATUMS });
    const [rx, ry, rw, rh] = rects[0];
    expect(rx).toBeCloseTo(moves[0][0], 6);
    expect(ry + rh).toBeCloseTo(moves[0][1], 6);
    expect(rw).toBeGreaterThan(0);
  });

  it('dashes the arms of an INFERRED datum and leaves an extracted one solid', () => {
    // The whole point of the distinction being visible: only one view per sheet has its origin
    // stated by the DXF. The other two are read off the drawn geometry, and a marker that does
    // not say so is the defect this overlay already shipped once.
    const { ctx, strokeDashes } = recordingCtx();
    renderViewOrigins({ frame: frame(ctx), datums: DATUMS });
    expect(strokeDashes[0]).toEqual([]);               // 299, from ucs_origin
    expect(strokeDashes[1].length).toBeGreaterThan(0); // 2D2, inferred
    expect(strokeDashes[2].length).toBeGreaterThan(0); // 2D5, inferred
  });

  it('scales the dash with zoom, so it cannot dissolve or go solid', () => {
    // Screen-constant like the arm lengths. A world-space pattern would read as solid when you
    // zoom in — silently upgrading a guess to a measurement.
    const near = recordingCtx();
    const far = recordingCtx();
    renderViewOrigins({ frame: { ...frame(near.ctx), scale: 0.4 } as any, datums: DATUMS });
    renderViewOrigins({ frame: { ...frame(far.ctx), scale: 4 } as any, datums: DATUMS });
    expect(near.strokeDashes[1][0]).toBeCloseTo(far.strokeDashes[1][0] * 10, 6);
  });

  it('keeps the corner square solid even on an inferred datum', () => {
    // A dashed 5px box reads as a rendering fault rather than as a caveat; the arms carry it.
    const { ctx, rectDashes } = recordingCtx();
    renderViewOrigins({ frame: frame(ctx), datums: DATUMS });
    expect(rectDashes.every(d => d.length === 0)).toBe(true);
  });

  it('passes the coordinate through unchanged when there are no bounds to mirror about', () => {
    // Same shape as `renderEntities`' own flip: no bounds means nothing to reflect, and a
    // guessed centreline would be worse than an unmirrored marker.
    const { ctx, moves } = recordingCtx();
    renderViewOrigins({ frame: frame(ctx, false, { hasBounds: false }), datums: DATUMS });
    expect(moves[0][1]).toBeCloseTo(157.324, 3);
  });

  it('is skipped on export — it is a reference overlay, not part of the sheet', () => {
    const { ctx, calls } = countingCtx();
    renderViewOrigins({ frame: frame(ctx, true), datums: DATUMS });
    expect(calls).toEqual({ stroke: 0, fill: 0, strokeRect: 0 });
  });
});
