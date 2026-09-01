/**
 * The compliance report's paper, in millimetres, shared by everything that draws on it.
 *
 * ## Why this is stated in millimetres
 *
 * The report used `unit: "px"` with a `[1200, 800]` format, and jsPDF's `px` unit is **not** 96
 * dpi unless you opt into its `px_scaling` hotfix — its default scale factor is `96 / 72`, so
 * every coordinate was 1.333 pt. That made the page **564.4 × 376.3 mm**: wider than A2, and not
 * a size any office printer holds. A margin expressed in millimetres on that page means nothing,
 * which is why the geometry moved here and the document now measures in mm directly.
 *
 * ## A4 landscape
 *
 * Chosen because it is the size that prints anywhere. The drawings themselves are A-series CAD
 * sheets (aspect ~1.414), so they sit inside the 283 × 196 mm content box with only a hairline of
 * letterboxing. **Switch `REPORT_PAGE_MM` to `{ width: 420, height: 297 }` for A3** if these are
 * printed on a plotter — everything downstream is derived from it, including the checklist
 * sheet's own canvas aspect, so nothing else has to change.
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
 * Owner's call, 2026-08-24: 7 mm first, then "much smaller" once the drawing stopped floating
 * inside its own `render_bounds` (see `exportFit.ts`). It is uniform, which is why page 1 carries
 * no header strip — a caption band and a 3 mm top margin cannot both exist, and the drawing is
 * what the page is for.
 *
 * ⚠ **3 mm is inside most printers' unprintable border** (typically 4–5 mm), so a hard copy may
 * lose the outermost sliver of the sheet frame. That is a deliberate trade for a full-bleed
 * drawing on screen; raise this to 5 if printed copies start coming back clipped.
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
