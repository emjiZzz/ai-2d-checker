import { describe, expect, test } from 'vitest';

import {
  EXPORT_REFERENCE_WIDTH_PX,
  computeExportFit,
  cropIsWorthwhile,
  findInkBounds,
  fitSpaceFromPixels,
  resolutionMultiplierFor,
  type FitRect,
} from './exportFit';

/**
 * A canvas of `width` x `height` white pixels with one opaque black rectangle painted on it,
 * exposed through the only method `findInkBounds` uses.
 *
 * Hand-built rather than drawn, because jsdom's `getContext('2d')` is null and the thing under
 * test is the pixel scan, not the renderer.
 */
function inkCanvas(
  width: number,
  height: number,
  rect?: { x: number; y: number; w: number; h: number },
): CanvasRenderingContext2D {
  const px = new Uint32Array(width * height).fill(0xffffffff);
  if (rect) {
    for (let y = rect.y; y < rect.y + rect.h; y++) {
      for (let x = rect.x; x < rect.x + rect.w; x++) px[y * width + x] = 0xff000000;
    }
  }
  const data = new Uint8ClampedArray(px.buffer);
  return { getImageData: () => ({ data }) } as unknown as CanvasRenderingContext2D;
}

describe('computeExportFit', () => {
  test('centres the content and never stretches it', () => {
    // A square fitted into a wide capture: height-limited, centred horizontally.
    const fit = computeExportFit([0, 0, 100, 100], 1000, 500);
    const inner = 500 - 2 * fit.padding;
    expect(fit.scale).toBeCloseTo(inner / 100, 10);

    const topLeft = { x: fit.transX, y: fit.transY };
    const bottomRight = { x: fit.transX + 100 * fit.scale, y: fit.transY + 100 * fit.scale };
    expect(bottomRight.y - topLeft.y).toBeCloseTo(bottomRight.x - topLeft.x, 10);
    // Equal gutters left and right.
    expect(topLeft.x).toBeCloseTo(1000 - bottomRight.x, 10);
  });

  test('a rectangle offset from the origin lands in the same place as one at it', () => {
    // The fit must depend on the rectangle's SIZE, not on where in CAD space it sits — a drawing
    // whose coordinates start at 400000 is ordinary.
    const a = computeExportFit([0, 0, 200, 100], 800, 600);
    const b = computeExportFit([400000, -9000, 400200, -8900], 800, 600);
    expect(b.scale).toBeCloseTo(a.scale, 10);
    expect(b.transX + 400000 * b.scale).toBeCloseTo(a.transX, 6);
    expect(b.transY + -9000 * b.scale).toBeCloseTo(a.transY, 6);
  });
});

describe('fitSpaceFromPixels', () => {
  test('inverts computeExportFit exactly', () => {
    // The two-pass crop turns painted pixels back into fit-space coordinates. An inversion that
    // is one padding-width off shifts the whole second pass, and the result still looks like a
    // drawing — just the wrong one, slightly.
    const rect: FitRect = [10, -5, 210, 95];
    const fit = computeExportFit(rect, 1234, 789);

    const topLeftPx = { x: fit.transX + rect[0] * fit.scale, y: fit.transY + rect[1] * fit.scale };
    const back = fitSpaceFromPixels(fit, topLeftPx.x, topLeftPx.y);
    expect(back.x).toBeCloseTo(rect[0], 8);
    expect(back.y).toBeCloseTo(rect[1], 8);
  });

  test('a full-canvas crop reproduces the original fit', () => {
    const rect: FitRect = [0, 0, 300, 200];
    const first = computeExportFit(rect, 1000, 700);
    const a = fitSpaceFromPixels(first, first.transX, first.transY);
    const b = fitSpaceFromPixels(
      first,
      first.transX + 300 * first.scale,
      first.transY + 200 * first.scale,
    );
    const second = computeExportFit([a.x, a.y, b.x, b.y], 1000, 700);
    expect(second.scale).toBeCloseTo(first.scale, 8);
    expect(second.transX).toBeCloseTo(first.transX, 6);
    expect(second.transY).toBeCloseTo(first.transY, 6);
  });
});

describe('findInkBounds', () => {
  test('an all-white canvas has no ink', () => {
    // Not an error: layers arrive after the drawing, so a capture taken in that window paints
    // nothing. The caller must keep its original fit rather than crop to an empty rectangle.
    expect(findInkBounds(inkCanvas(40, 30), 40, 30)).toBeNull();
  });

  test('finds the painted rectangle, inclusive of its last pixel', () => {
    const ctx = inkCanvas(100, 80, { x: 12, y: 7, w: 30, h: 20 });
    expect(findInkBounds(ctx, 100, 80)).toEqual([12, 7, 42, 27]);
  });

  test('ink touching the canvas edge is not lost', () => {
    const ctx = inkCanvas(50, 40, { x: 0, y: 0, w: 50, h: 40 });
    expect(findInkBounds(ctx, 50, 40)).toEqual([0, 0, 50, 40]);
  });

  test('a single pixel is found', () => {
    const ctx = inkCanvas(60, 60, { x: 59, y: 0, w: 1, h: 1 });
    expect(findInkBounds(ctx, 60, 60)).toEqual([59, 0, 60, 1]);
  });
});

describe('cropIsWorthwhile', () => {
  test('no second render when the ink already fills the padded area', () => {
    expect(cropIsWorthwhile([8, 8, 992, 692], 1000, 700, 8)).toBe(false);
  });

  test('a second render when the drawing floats inside its bounds', () => {
    // Matplotlib's 5%-a-side autoscale margin, which is the whole reason this path exists.
    expect(cropIsWorthwhile([50, 35, 950, 665], 1000, 700, 8)).toBe(true);
  });
});

describe('resolutionMultiplierFor', () => {
  test('on screen it is 1, whatever size the panel is', () => {
    // `renderContent` defaults `renderWidth` to the CSS width for a screen pass, so every pixel
    // size in the renderer is a CSS pixel — the behaviour this must not change.
    for (const w of [480, 700, 1280, 1919]) {
      expect(resolutionMultiplierFor(false, w, w)).toBe(1);
    }
  });

  test('on export it does not depend on the window at all', () => {
    // The defect: the same audit exported from a maximised window and a narrow one came out with
    // different line weights, because the denominator was the canvas pane's width.
    const capture = 3492;
    const narrow = resolutionMultiplierFor(true, capture, 480);
    const typical = resolutionMultiplierFor(true, capture, 700);
    const wide = resolutionMultiplierFor(true, capture, 1600);
    expect(narrow).toBe(typical);
    expect(wide).toBe(typical);
    expect(typical).toBeCloseTo(capture / EXPORT_REFERENCE_WIDTH_PX, 10);
  });

  test('on export it scales with the capture, so a bigger page is not a bolder one', () => {
    // Doubling the capture must double the multiplier: a stroke then covers the same fraction of
    // the page, which is what keeps a hairline a fixed weight in millimetres.
    expect(resolutionMultiplierFor(true, 7000, 700) / resolutionMultiplierFor(true, 3500, 700)).toBeCloseTo(2, 10);
  });

  test('the reference width puts a hairline at a sane printed weight', () => {
    // 1 design pixel, at the report's A4 capture of 3492 px across 291 mm. Stated in millimetres
    // because that is the unit the decision is actually in — the constant is only a proxy for it.
    const hairlineMm = (1 * resolutionMultiplierFor(true, 3492, 700)) / (3492 / 291);
    expect(hairlineMm).toBeGreaterThan(0.2);
    expect(hairlineMm).toBeLessThan(0.6);
  });
});
