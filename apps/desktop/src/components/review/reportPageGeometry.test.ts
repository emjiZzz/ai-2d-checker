import { describe, expect, test } from 'vitest';

import { CHECKLIST_PAGE_H, CHECKLIST_PAGE_W } from './complianceChecklistSheet';
import {
  REPORT_CONTENT_MM,
  REPORT_MARGIN_MM,
  REPORT_PAGE_ASPECT,
  REPORT_PAGE_MM,
  REPORT_RASTER_PX_PER_MM,
} from './reportPageGeometry';

/**
 * The report's paper, pinned.
 *
 * These are not arithmetic tests. Each one fails only in a way that is invisible in the generated
 * PDF until someone measures a printout with a ruler — a margin that is 7 on three sides, a
 * checklist page stretched 6% because its canvas stopped matching the paper, a capture density
 * that quietly halved.
 */

describe('report page geometry', () => {
  test('the page is A4 landscape', () => {
    // Switching to A3 is legitimate and everything derives from this constant — but it is a
    // decision about what people print on, not a refactor, so it should not move silently.
    expect([REPORT_PAGE_MM.width, REPORT_PAGE_MM.height]).toEqual([297, 210]);
    expect(REPORT_PAGE_MM.width).toBeGreaterThan(REPORT_PAGE_MM.height);
  });

  test('the content box is inset by the margin on all four sides', () => {
    const left = REPORT_CONTENT_MM.x;
    const right = REPORT_PAGE_MM.width - (REPORT_CONTENT_MM.x + REPORT_CONTENT_MM.width);
    const top = REPORT_CONTENT_MM.y;
    const bottom = REPORT_PAGE_MM.height - (REPORT_CONTENT_MM.y + REPORT_CONTENT_MM.height);

    expect([left, right, top, bottom]).toEqual([
      REPORT_MARGIN_MM,
      REPORT_MARGIN_MM,
      REPORT_MARGIN_MM,
      REPORT_MARGIN_MM,
    ]);
  });

  test('the margin is 3 mm', () => {
    expect(REPORT_MARGIN_MM).toBe(3);
    expect(REPORT_CONTENT_MM.width).toBe(291);
    expect(REPORT_CONTENT_MM.height).toBe(204);
  });

  test('the checklist canvas has the paper’s aspect ratio', () => {
    // Placed full-bleed by the exporter, so any disagreement here is a silent vertical stretch of
    // every row of type on the page.
    expect(CHECKLIST_PAGE_W / CHECKLIST_PAGE_H).toBeCloseTo(REPORT_PAGE_ASPECT, 10);
  });

  test('the drawing is captured at print resolution', () => {
    const dpi = REPORT_RASTER_PX_PER_MM * 25.4;
    expect(dpi).toBeGreaterThanOrEqual(300);

    // The capture the exporter asks for, spelled out: a title block's 2.5 mm characters land on
    // roughly 30 pixels, which is what keeps them legible after Flate and printing.
    expect(Math.round(REPORT_CONTENT_MM.width * REPORT_RASTER_PX_PER_MM)).toBe(3492);
    expect(Math.round(REPORT_CONTENT_MM.height * REPORT_RASTER_PX_PER_MM)).toBe(2448);
  });
});
