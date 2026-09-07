/**
 * The compliance report's paper, in millimetres, shared by everything that draws on it.
 *
 * In millimetres because the report used `unit: "px"` with a `[1200, 800]` format, and jsPDF's
 * `px` is not 96 dpi without its `px_scaling` hotfix -- the default scale factor is `96 / 72`, so
 * every coordinate was 1.333 pt and the page came out 564.4 × 376.3 mm, wider than A2 and a size
 * no office printer holds. A margin expressed in mm on that page means nothing.
 *
 * A4 landscape, because it prints anywhere. The drawings are A-series CAD sheets (aspect ~1.414)
 * and sit inside the 283 × 196 mm content box with a hairline of letterboxing. For A3 on a
 * plotter, switch `REPORT_PAGE_MM` to `{ width: 420, height: 297 }`: everything downstream
 * derives from it, including the checklist sheet's canvas aspect.
 */
export const REPORT_PAGE_MM = Object.freeze({ width: 297, height: 210 });

/**
 * Checklist pages use A4 Portrait orientation (210 x 297 mm) with a two-column layout.
 */
export const CHECKLIST_PAGE_MM = Object.freeze({ width: 210, height: 297 });
export const CHECKLIST_PAGE_ASPECT = CHECKLIST_PAGE_MM.width / CHECKLIST_PAGE_MM.height;

/**
 * The margin on all four sides of a report page.
 *
 * Owner's call, 2026-08-24: 7 mm first, then much smaller once the drawing stopped floating
 * inside its own `render_bounds` (see `exportFit.ts`). Uniform, which is why page 1 carries no
 * header strip -- a caption band and a 3 mm top margin cannot both exist, and the drawing is what
 * the page is for. 3 mm is inside most printers' unprintable border of 4-5 mm, so a hard copy may
 * lose the outermost sliver of the sheet frame; that is a deliberate trade for a full-bleed
 * drawing on screen. Raise it to 5 if printed copies start coming back clipped.
 */
export const REPORT_MARGIN_MM = 3;

export const REPORT_PAGE_ASPECT = REPORT_PAGE_MM.width / REPORT_PAGE_MM.height;

/** The printable box: the page inset by {@link REPORT_MARGIN_MM} on every side. */
export const REPORT_CONTENT_MM = Object.freeze({
  x: REPORT_MARGIN_MM,
  y: REPORT_MARGIN_MM,
  width: REPORT_PAGE_MM.width - REPORT_MARGIN_MM * 2,
  height: REPORT_PAGE_MM.height - REPORT_MARGIN_MM * 2,
});

/**
 * Raster density for the drawing capture, in pixels per millimetre.
 *
 * 12 px/mm is 304.8 dpi — print resolution for line art, and the density at which a title
 * block's 2.5 mm characters survive being rasterised. Raising it costs Flate time on the main
 * thread quadratically for no visible gain on paper.
 */
export const REPORT_RASTER_PX_PER_MM = 12;
