import { describe, expect, it } from 'vitest';
class FakePath2D {
  moveTo() {}
  lineTo() {}
  arc() {}
  rect() {}
  closePath() {}
}
(globalThis as any).Path2D = FakePath2D;

import { MARK_PAINT, renderEntities, renderViolationReticles } from './renderEntities';
import { MARKER_STYLES, markerInkFor } from './markerStyles';
import { getNormalization, parseBounds, worldToCanvas } from '../../utils/coordinateTransform';

/**
 * How a mark is painted, per surface.
 *
 * The canvas is dark and the printed page is white, and the marks were painted for the canvas on
 * both. On paper that put a 4.3 mm neon-green tick with a 1.25 mm stroke over linework that
 * prints as a 0.42 mm near-black hairline — three times the weight of the drawing it annotates,
 * sitting on top of the value it certifies so the value could not be read.
 *
 * Nothing here is about correctness of placement (see `markerPlacement.test.ts`). These pin the
 * *relationship* between a mark and the drawing under it, which is the thing that silently
 * regresses when someone tunes one number.
 */

const NORM = getNormalization(parseBounds([-52.5, -37.125, 1102.5, 779.625]))!;
const VIEWPORT = { x: 40, y: 25, scale: 1.3 };
const SCREEN = {
  scale: VIEWPORT.scale * NORM.normScale,
  transX: VIEWPORT.x - NORM.xmin * VIEWPORT.scale * NORM.normScale,
  transY: VIEWPORT.y - NORM.ymin * VIEWPORT.scale * NORM.normScale,
};
const PAGE = { scale: 3.017, transX: 158.4, transY: 112.5 };
const EXPORT_MULTIPLIER = 3492 / 700;

/** Records each path vertex together with the style in force when the path was stroked. */
function recordingCtx() {
  const pending: [number, number][] = [];
  const strokes: { points: [number, number][]; style: string; width: number; alpha: number }[] = [];
  const arcs: { x: number; y: number; r: number; style: string; alpha: number }[] = [];
  const state = { strokeStyle: '', fillStyle: '', lineWidth: 0, globalAlpha: 1 };
  const noop = () => {};

  const ctx: any = new Proxy(
    {},
    {
      get: (_t, k) => {
        if (k === 'beginPath') return () => { pending.length = 0; };
        if (k === 'moveTo' || k === 'lineTo') {
          return (x: number, y: number) => { pending.push([x, y]); };
        }
        if (k === 'arc') {
          return (x: number, y: number, r: number) =>
            arcs.push({ x, y, r, style: state.fillStyle, alpha: state.globalAlpha });
        }
        if (k === 'stroke') {
          return (p?: any) => {
            if (p || pending.length) {
              strokes.push({
                points: [...pending],
                style: state.strokeStyle,
                width: state.lineWidth,
                alpha: state.globalAlpha,
              });
            }
          };
        }
        if (k === 'measureText') return (t: string) => ({ width: String(t).length * 5 });
        if (k in state) return (state as any)[k];
        return noop;
      },
      set: (_t, k, v) => {
        if (k in state) (state as any)[k] = v;
        return true;
      },
    },
  );
  return { ctx, strokes, arcs };
}

const frameFor = (ctx: any, isExport: boolean) =>
  ({
    ctx,
    isExport,
    renderWidth: isExport ? 3492 : 700,
    renderHeight: isExport ? 2448 : 500,
    width: 700,
    height: 500,
    norm: NORM,
    ...(isExport ? PAGE : SCREEN),
    currentViewportScale: (isExport ? PAGE.scale : SCREEN.scale) / NORM.normScale,
    resolutionMultiplier: isExport ? EXPORT_MULTIPLIER : 1,
    viewport: VIEWPORT,
    markerPositionsRef: { current: {} as Record<string, { x: number; y: number }> },
    isNeonModeActive: false,
  }) as any;

const draw = (frame: any, status: string) =>
  renderViolationReticles({
    frame,
    violations: [{ id: 'v1', status, category: 'title_block', description: 'x', coordinates: [500, 600] }],
    showViolations: true,
    showMarkerLabels: false,
    hoveredMarkerId: null,
    selectedViolation: null,
    drawing: { id: 'rev' },
    oldDrawing: { id: 'ref' },
    visibleMarkerTypes: {},
  } as any);

describe('the checkmark on the printed page', () => {
  it('uses the white-surface ink, not the dark-canvas neon', () => {
    const onScreen = recordingCtx();
    draw(frameFor(onScreen.ctx, false), 'MATCHED');
    expect(onScreen.strokes[0].style).toBe(MARKER_STYLES.MATCHED.color);

    const onPage = recordingCtx();
    draw(frameFor(onPage.ctx, true), 'MATCHED');
    expect(onPage.strokes[0].style).toBe(MARKER_STYLES.MATCHED.uiLight);
    // The table's own words: `#39ff14` is "unusable on white".
    expect(onPage.strokes[0].style).not.toBe(MARKER_STYLES.MATCHED.color);
    expect(markerInkFor('MATCHED', 'print')).toBe(MARKER_STYLES.MATCHED.uiLight);
  });

  it('is lighter than opaque on paper, and opaque on the canvas', () => {
    const onScreen = recordingCtx();
    draw(frameFor(onScreen.ctx, false), 'MATCHED');
    expect(onScreen.strokes[0].alpha).toBe(1);

    const onPage = recordingCtx();
    draw(frameFor(onPage.ctx, true), 'MATCHED');
    expect(onPage.strokes[0].alpha).toBe(MARK_PAINT.print.alpha);
    expect(onPage.strokes[0].alpha).toBeLessThan(1);
  });

  it('does not out-weigh the linework it annotates', () => {
    // The drawing's own profile on this path is `0.60 * resolutionMultiplier` canvas pixels. A
    // mark must read as visible beside a line — it is an annotation, not geometry.
    const onPage = recordingCtx();
    draw(frameFor(onPage.ctx, true), 'MATCHED');
    const hairline = 0.60 * EXPORT_MULTIPLIER;
    const ratio = onPage.strokes[0].width / hairline;
    expect(ratio).toBeGreaterThanOrEqual(0.8);
    expect(ratio).toBeLessThanOrEqual(2);
  });

  it('is about the size of a character, not of a whole value', () => {
    // Title-block text prints at roughly 2.5 mm; the capture is 3492 px across 291 mm. The tick
    // spans 1.7 of its own size unit.
    const onPage = recordingCtx();
    draw(frameFor(onPage.ctx, true), 'MATCHED');
    const xs = onPage.strokes[0].points.map((p) => p[0]);
    const spanMm = (Math.max(...xs) - Math.min(...xs)) / (3492 / 291);
    expect(spanMm).toBeGreaterThan(1.5);
    expect(spanMm).toBeLessThan(3.5);
  });

  it('steps up off the value on paper, and shifts to the right of the data', () => {
    // The coordinate is the entity's bounding-box CENTRE — the middle of the glyphs on a single
    // line of text. The checkmark is shifted to the right so it never obscures the value.
    const onPage = recordingCtx();
    draw(frameFor(onPage.ctx, true), 'MATCHED');
    const anchorY = worldToCanvas(500, 600, NORM, PAGE).y;
    const anchorX = worldToCanvas(500, 600, NORM, PAGE).x;
    const drawnCentreX = onPage.strokes[0].points[1][0];
    const drawnCentreY = onPage.strokes[0].points[1][1];
    const size = MARK_PAINT.print.checkPx * EXPORT_MULTIPLIER;
    expect(drawnCentreX).toBeGreaterThan(anchorX);
    expect(drawnCentreY).toBeCloseTo(
      anchorY - MARK_PAINT.print.checkRisePx * EXPORT_MULTIPLIER + size * 0.6,
      6,
    );

    const onScreen = recordingCtx();
    draw(frameFor(onScreen.ctx, false), 'MATCHED');
    const screenAnchorY = worldToCanvas(500, 600, NORM, SCREEN).y;
    const screenAnchorX = worldToCanvas(500, 600, NORM, SCREEN).x;
    const screenDrawnX = onScreen.strokes[0].points[1][0];
    const screenSize = MARK_PAINT.canvas.checkPx;
    expect(screenDrawnX).toBeGreaterThan(screenAnchorX);
    expect(MARK_PAINT.canvas.checkRisePx).toBe(0);
    expect(onScreen.strokes[0].points[1][1]).toBeCloseTo(screenAnchorY + screenSize * 0.6, 6);
  });
});

describe('the dot on the printed page', () => {
  it('also takes the white-surface ink', () => {
    // The dot and the check are the same statement in two shapes; only one of them having been
    // recoloured for print is the drift this table exists to prevent.
    const onPage = recordingCtx();
    draw(frameFor(onPage.ctx, true), 'CHANGED');
    expect(onPage.arcs[0].style).toBe(MARKER_STYLES.CHANGED.uiLight);

    const onScreen = recordingCtx();
    draw(frameFor(onScreen.ctx, false), 'CHANGED');
    expect(onScreen.arcs[0].style).toBe(MARKER_STYLES.CHANGED.color);
  });
});

describe('drawing lineweights on the printed page', () => {
  it('strokes dimension lines noticeably thinner than geometry lines on export', () => {
    const onPage = recordingCtx();
    const frame = frameFor(onPage.ctx, true);
    frame.minX = -1000;
    frame.maxX = 2000;
    frame.minY = -1000;
    frame.maxY = 2000;

    renderEntities({
      frame,
      layers: {
        '0': [
          { type: 'line', geometry: { start: [0, 0], end: [100, 100] } },
          {
            type: 'dimension',
            geometry: {
              render_paths: [[[0, 0], [100, 0]]],
            },
          },
        ],
      },
      activeLayers: {},
      theme: 'hc-dark',
    });

    const geoStroke = onPage.strokes.find((s) => s.width > (0.45 / PAGE.scale) * EXPORT_MULTIPLIER);
    const dimStroke = onPage.strokes.find((s) => s.width < (0.35 / PAGE.scale) * EXPORT_MULTIPLIER);
    expect(geoStroke).toBeDefined();
    expect(dimStroke).toBeDefined();
    expect(geoStroke!.width / dimStroke!.width).toBeGreaterThan(1.7);
  });

  it('strokes centerlines and dashed lines with the same thin hairline as dimensions on export', () => {
    const onPage = recordingCtx();
    const frame = frameFor(onPage.ctx, true);
    frame.minX = -1000;
    frame.maxX = 2000;
    frame.minY = -1000;
    frame.maxY = 2000;

    renderEntities({
      frame,
      layers: {
        '0': [
          { type: 'line', geometry: { start: [0, 0], end: [100, 100] } },
          {
            type: 'line',
            geometry: { start: [0, 50], end: [100, 50] },
            properties: { linetype: 'CENTER' },
            style: { dash: [7.35, 1.47, 1.47, 1.47], dashUnits: 'world' },
          },
        ],
      },
      activeLayers: {},
      theme: 'hc-dark',
    });

    const solidGeo = onPage.strokes.find((s) => s.width > (0.45 / PAGE.scale) * EXPORT_MULTIPLIER);
    const centerLine = onPage.strokes.find((s) => s.width < (0.35 / PAGE.scale) * EXPORT_MULTIPLIER);
    expect(solidGeo).toBeDefined();
    expect(centerLine).toBeDefined();
    expect(solidGeo!.width / centerLine!.width).toBeGreaterThan(1.7);
  });

  it('strokes chamfer callout lines and arrows with the same thin hairline as dimensions on export', () => {
    const onPage = recordingCtx();
    const frame = frameFor(onPage.ctx, true);
    frame.minX = -1000;
    frame.maxX = 2000;
    frame.minY = -1000;
    frame.maxY = 2000;

    renderEntities({
      frame,
      layers: {
        '1': [
          // Part visible outline (Layer 1)
          { type: 'line', geometry: { start: [0, 0], end: [100, 100] } },
        ],
        '5': [
          // Chamfer leader polyline on Layer 5
          { type: 'polyline', geometry: { vertices: [[10, 10], [20, 20]] }, properties: { parent_handle: '248' } },
          // Chamfer arrow line on Layer 5
          { type: 'line', geometry: { start: [10, 10], end: [12, 8] }, properties: { parent_handle: '248' } },
        ],
      },
      activeLayers: {},
      theme: 'hc-dark',
    });

    const partOutline = onPage.strokes.find((s) => s.width > (0.45 / PAGE.scale) * EXPORT_MULTIPLIER);
    const chamferArrow = onPage.strokes.find((s) => s.width < (0.35 / PAGE.scale) * EXPORT_MULTIPLIER);
    expect(partOutline).toBeDefined();
    expect(chamferArrow).toBeDefined();
    expect(partOutline!.width / chamferArrow!.width).toBeGreaterThan(1.7);
  });

  it('strokes machining symbols (triangles ▽) with the same thin hairline as dimensions on export', () => {
    const onPage = recordingCtx();
    const frame = frameFor(onPage.ctx, true);
    frame.minX = -1000;
    frame.maxX = 2000;
    frame.minY = -1000;
    frame.maxY = 2000;

    renderEntities({
      frame,
      layers: {
        '1': [
          // Part visible outline (Layer 1)
          { type: 'line', geometry: { start: [0, 0], end: [100, 100] } },
        ],
        '8': [
          // Machining symbol (equilateral triangle on Layer 8 / JZB block)
          { type: 'line', geometry: { start: [2, 0], end: [0, 3.46] }, properties: { parent_handle: '246', block_name: 'JZB_0004' } },
          { type: 'line', geometry: { start: [0, 3.46], end: [4, 3.46] }, properties: { parent_handle: '246', block_name: 'JZB_0004' } },
          { type: 'line', geometry: { start: [4, 3.46], end: [2, 0] }, properties: { parent_handle: '246', block_name: 'JZB_0004' } },
        ],
      },
      activeLayers: {},
      theme: 'hc-dark',
    });

    const partOutline = onPage.strokes.find((s) => s.width > (0.45 / PAGE.scale) * EXPORT_MULTIPLIER);
    const triangleStroke = onPage.strokes.find((s) => s.width < (0.35 / PAGE.scale) * EXPORT_MULTIPLIER);
    expect(partOutline).toBeDefined();
    expect(triangleStroke).toBeDefined();
    expect(partOutline!.width / triangleStroke!.width).toBeGreaterThan(1.7);
  });

  it('strokes Layer 2 part geometry (circles, outlines) with bold weight on export', () => {
    const onPage = recordingCtx();
    const frame = frameFor(onPage.ctx, true);
    frame.minX = -1000;
    frame.maxX = 2000;
    frame.minY = -1000;
    frame.maxY = 2000;

    renderEntities({
      frame,
      layers: {
        '2': [
          // Part visible geometry on Layer 2 (e.g. collar inner/outer circle, keyway)
          { type: 'arc', geometry: { center: [100, 100], radius: 20 }, properties: { linetype: 'Continuous' } },
        ],
        '5': [
          // Dimension line on Layer 5
          { type: 'dimension', geometry: { render_paths: [[[0, 0], [100, 0]]] } },
        ],
      },
      activeLayers: {},
      theme: 'hc-dark',
    });

    const layer2Geometry = onPage.strokes.find((s) => s.width > (0.45 / PAGE.scale) * EXPORT_MULTIPLIER);
    const dimStroke = onPage.strokes.find((s) => s.width < (0.35 / PAGE.scale) * EXPORT_MULTIPLIER);
    expect(layer2Geometry).toBeDefined();
    expect(dimStroke).toBeDefined();
    expect(layer2Geometry!.width / dimStroke!.width).toBeGreaterThan(1.7);
  });

  it('strokes template lines (RAHM2 / WAKU / title block tables) with thin hairline on export', () => {
    const onPage = recordingCtx();
    const frame = frameFor(onPage.ctx, true);
    frame.minX = -1000;
    frame.maxX = 2000;
    frame.minY = -1000;
    frame.maxY = 2000;

    renderEntities({
      frame,
      layers: {
        '2': [
          // Part visible geometry on Layer 2
          { type: 'line', geometry: { start: [0, 0], end: [100, 100] } },
        ],
        'RAHM2': [
          // Template title block grid / general tolerance table rule
          { type: 'line', geometry: { start: [0, 0], end: [200, 0] } },
        ],
      },
      activeLayers: {},
      theme: 'hc-dark',
    });

    const partGeometry = onPage.strokes.find((s) => s.width > (0.45 / PAGE.scale) * EXPORT_MULTIPLIER);
    const templateLine = onPage.strokes.find((s) => s.width < (0.35 / PAGE.scale) * EXPORT_MULTIPLIER);
    expect(partGeometry).toBeDefined();
    expect(templateLine).toBeDefined();
    expect(partGeometry!.width / templateLine!.width).toBeGreaterThan(1.7);
  });
});
