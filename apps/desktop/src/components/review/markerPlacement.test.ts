import { describe, expect, it } from 'vitest';

import { renderAnnotationPins, renderViolationReticles } from './renderEntities';
import {
  getNormalization,
  parseBounds,
  worldToCanvas,
  worldToScreen,
} from '../../utils/coordinateTransform';

/**
 * Where a mark lands on the sheet — on screen and, crucially, on export.
 *
 * Every marker, checkmark and annotation pin was positioned with `worldToScreen`, which derives
 * its transform from the live `viewport`. The export pass does not use the viewport: it replaces
 * `scale`/`transX`/`transY` with a fit-to-page transform and leaves `viewport` exactly as the
 * user left it. So the geometry was fitted to the page while every mark was drawn at the pixel
 * position it occupied in the app's panel — the whole set collapsed into the top-left corner of
 * a 3492-pixel page, pointing at nothing.
 *
 * On screen the two agree to the last decimal, which is why nothing caught it. These tests are
 * therefore written as a PAIR: the screen frame pins the equivalence, and the export frame — one
 * the viewport cannot reproduce — pins that the renderer reads the frame it was handed.
 */

const NORM = getNormalization(parseBounds([-52.5, -37.125, 1102.5, 779.625]))!;
const VIEWPORT = { x: 40, y: 25, scale: 1.3 };

/** What `CanvasRenderer` derives for an on-screen pass. */
const SCREEN = {
  scale: VIEWPORT.scale * NORM.normScale,
  transX: VIEWPORT.x - NORM.xmin * VIEWPORT.scale * NORM.normScale,
  transY: VIEWPORT.y - NORM.ymin * VIEWPORT.scale * NORM.normScale,
};

/** A fit-to-page transform. Deliberately unrelated to VIEWPORT — that is the whole point. */
const EXPORT = { scale: 3.017, transX: 158.4, transY: 112.5 };

function recordingCtx() {
  const arcs: [number, number, number][] = [];
  const paths: [number, number][] = [];
  const texts: [string, number, number][] = [];
  const noop = () => {};
  const ctx: any = new Proxy(
    {},
    {
      get: (_t, k) => {
        if (k === 'arc') return (x: number, y: number, r: number) => arcs.push([x, y, r]);
        if (k === 'moveTo' || k === 'lineTo') return (x: number, y: number) => paths.push([x, y]);
        if (k === 'fillText') return (t: string, x: number, y: number) => texts.push([t, x, y]);
        if (k === 'measureText') return (t: string) => ({ width: String(t).length * 5 });
        return noop;
      },
      set: () => true,
    },
  );
  return { ctx, arcs, paths, texts };
}

const frameFor = (
  ctx: any,
  transform: { scale: number; transX: number; transY: number },
  isExport: boolean,
) =>
  ({
    ctx,
    isExport,
    renderWidth: isExport ? 3492 : 700,
    renderHeight: isExport ? 2448 : 500,
    width: 700,
    height: 500,
    norm: NORM,
    ...transform,
    // As `CanvasRenderer` computes it: the pass's own effective zoom, whichever pass it is.
    currentViewportScale: transform.scale / NORM.normScale,
    resolutionMultiplier: isExport ? 3492 / 700 : 1,
    viewport: VIEWPORT,
    markerPositionsRef: { current: {} as Record<string, { x: number; y: number }> },
    isNeonModeActive: false,
  }) as any;

const CHANGED_AT = (coords: [number, number]) => ({
  id: 'v1',
  status: 'CHANGED',
  category: 'title_block',
  description: 'x',
  coordinates: coords,
});

const drawMarker = (frame: any, coords: [number, number] = [500, 600]) =>
  renderViolationReticles({
    frame,
    violations: [CHANGED_AT(coords)],
    showViolations: true,
    showMarkerLabels: false,
    hoveredMarkerId: null,
    selectedViolation: null,
    drawing: { id: 'rev' },
    oldDrawing: { id: 'ref' },
    visibleMarkerTypes: {},
  } as any);

describe('marker placement', () => {
  it('on screen, the frame transform and the viewport agree exactly', () => {
    const { ctx, arcs } = recordingCtx();
    drawMarker(frameFor(ctx, SCREEN, false));

    const expected = worldToScreen(500, 600, NORM, VIEWPORT);
    expect(arcs).toHaveLength(1);
    expect(arcs[0][0]).toBeCloseTo(expected.x, 6);
    expect(arcs[0][1]).toBeCloseTo(expected.y, 6);
  });

  it('on export, the marker follows the page fit and NOT the viewport', () => {
    const { ctx, arcs } = recordingCtx();
    drawMarker(frameFor(ctx, EXPORT, true));

    const onPage = worldToCanvas(500, 600, NORM, EXPORT);
    const onScreen = worldToScreen(500, 600, NORM, VIEWPORT);

    expect(arcs).toHaveLength(1);
    expect(arcs[0][0]).toBeCloseTo(onPage.x, 6);
    expect(arcs[0][1]).toBeCloseTo(onPage.y, 6);
    // The failure mode, stated: the two must not be the same number here, or the test would pass
    // against the very bug it exists to catch.
    expect(arcs[0][0]).not.toBeCloseTo(onScreen.x, 1);
  });

  it('an export pass does not overwrite the pointer hit targets', () => {
    // These positions are what a click is tested against. An export writes them in a 3492-pixel
    // page's coordinates, so leaving the write unguarded moved every clickable marker until the
    // next repaint.
    const exportFrame = frameFor(recordingCtx().ctx, EXPORT, true);
    drawMarker(exportFrame);
    expect(exportFrame.markerPositionsRef.current).toEqual({});

    const screenFrame = frameFor(recordingCtx().ctx, SCREEN, false);
    drawMarker(screenFrame);
    expect(screenFrame.markerPositionsRef.current.v1).toBeDefined();
  });

  it('a marker is not culled by the zoom the user happened to leave behind', () => {
    // `viewport.scale < 0.1` skipped the marker entirely. On export that read the app's live
    // zoom, so a checker who had zoomed out exported a drawing with no marks on it — and the
    // report looked like a clean sheet rather than a broken export.
    const zoomedOut = { ...VIEWPORT, scale: 0.05 };
    const { ctx, arcs } = recordingCtx();
    const frame = frameFor(ctx, EXPORT, true);
    frame.viewport = zoomedOut;
    drawMarker(frame);
    expect(arcs).toHaveLength(1);
  });

  it('the dot scales with the page fit, not with the window size', () => {
    // Its radius was `MARKER_DOT_PX * (renderWidth / panelWidth) * viewport.scale`, so the same
    // audit exported from a maximised window and a narrow one produced different-sized marks.
    const wide = recordingCtx();
    const wideFrame = frameFor(wide.ctx, EXPORT, true);
    wideFrame.resolutionMultiplier = 2;
    drawMarker(wideFrame);

    const narrow = recordingCtx();
    const narrowFrame = frameFor(narrow.ctx, EXPORT, true);
    narrowFrame.resolutionMultiplier = 8;
    drawMarker(narrowFrame);

    expect(wide.arcs[0][2]).toBeCloseTo(narrow.arcs[0][2], 10);
  });
});

describe('annotation pin placement', () => {
  const drawPin = (frame: any) =>
    renderAnnotationPins({
      frame,
      annotations: [{ id: 'a1', coordinates: [500, 600], pen_type: 'checker_blue', status: 'open' }],
      selectedAnnotationId: null,
      hoveredAnnotationId: null,
      badgeMap: {},
    } as any);

  it('on screen, agrees with the viewport', () => {
    const { ctx, texts } = recordingCtx();
    drawPin(frameFor(ctx, SCREEN, false));
    const expected = worldToScreen(500, 600, NORM, VIEWPORT);
    expect(texts).toHaveLength(1);
    expect(texts[0][1]).toBeCloseTo(expected.x, 6);
    expect(texts[0][2]).toBeCloseTo(expected.y, 6);
  });

  it('on export, follows the page fit', () => {
    const { ctx, texts } = recordingCtx();
    drawPin(frameFor(ctx, EXPORT, true));
    const onPage = worldToCanvas(500, 600, NORM, EXPORT);
    expect(texts).toHaveLength(1);
    expect(texts[0][1]).toBeCloseTo(onPage.x, 6);
    expect(texts[0][2]).toBeCloseTo(onPage.y, 6);
  });
});
