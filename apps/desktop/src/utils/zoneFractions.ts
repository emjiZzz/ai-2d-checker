/**
 * zoneFractions.ts
 *
 * The single conversion between the two coordinate spaces zone boxes live in. Both are
 * correct in their own context, and they disagree on the direction of Y — which is the
 * one thing in this feature that is easy to get backwards and hard to notice.
 *
 * ## The two spaces
 *
 * 1. **Detected zone boxes** (`GET /drawings/:id/zones`) are absolute CAD units, **Y-up**:
 *    a larger `y` is nearer the top of the sheet. Verified against real entity coordinates
 *    rather than inferred — the two notes lines in `M7452A0N01_reference.dxf` sit at CAD
 *    y=599.5 and y=577.9 within bounds y −37.125…779.625, and they render 22% down from the
 *    sheet top, which is where they visibly are. Read-only rendering of these uses
 *    `worldToScreen`, which applies the flip.
 *
 * 2. **`customRegions` / template fractions** are 0..1 of `render_bounds`, **Y-down**:
 *    fraction 0 is the top of the sheet. Confirmed by the pre-existing defaults (`title`,
 *    a bottom-right title block, is `yMin: 0.75`) and by the drag hit-test in
 *    `useCanvasInteraction.ts`, where `yMin = 0` maps to `viewport.y` (screen top). That
 *    hit-test does not invert Y and is correct for this space — do not "fix" it.
 *
 * So converting between them flips Y **and swaps min/max**: a zone's CAD `ymax` becomes its
 * fractional `yMin`. X is a plain ratio in both directions.
 *
 * Getting this wrong produces a vertically mirrored set of boxes, which reads as plausible
 * because most zones sit near the sheet's vertical centre — hence the orientation test in
 * `zoneFractions.test.ts` rather than trusting a visual check.
 */

/**
 * A zone box as fractions of render_bounds, Y-DOWN (0 = top of sheet).
 *
 * Declared here rather than in reviewStore so the fraction vocabulary lives with the
 * fraction maths: reviewStore imports these helpers, so keeping the type there formed a
 * cycle, and consumers of the geometry should not have to import a zustand store (which
 * also broke tests that mock that store).
 */
export interface RegionFractions {
  xMin: number;
  xMax: number;
  yMin: number;
  yMax: number;
}

/**
 * Fallback zone layout, used before any alignment exists for a drawing.
 *
 * Y-DOWN like everything else in this module — which is why `title`, a bottom-right title
 * block, is 0.75..0.98 rather than 0.02..0.25.
 *
 * These are a coarse guess unrelated to what zone_detector.py produces. The editor seeds
 * from detected boxes in preference to them.
 */
export const DEFAULT_CUSTOM_REGIONS: Record<string, RegionFractions> = {
  views: { xMin: 0.05, xMax: 0.65, yMin: 0.15, yMax: 0.85 },
  notes: { xMin: 0.05, xMax: 0.35, yMin: 0.20, yMax: 0.60 },
  bom: { xMin: 0.65, xMax: 0.98, yMin: 0.05, yMax: 0.42 },
  title: { xMin: 0.40, xMax: 0.98, yMin: 0.75, yMax: 0.98 },
  iso: { xMin: 0.65, xMax: 0.98, yMin: 0.45, yMax: 0.72 },
  tolerance: { xMin: 0.02, xMax: 0.98, yMin: 0.70, yMax: 0.98 },
  title_upper_left: { xMin: 0.00, xMax: 0.38, yMin: 0.00, yMax: 0.28 },
};

export interface ZoneBoxCad {
  xmin: number;
  ymin: number;
  xmax: number;
  ymax: number;
}

/** `[xmin, ymin, xmax, ymax]` as stored in `drawing.metadata.render_bounds`. */
export type RenderBoundsTuple = readonly [number, number, number, number];

function spans(bounds: RenderBoundsTuple) {
  const [bx0, by0, bx1, by1] = bounds;
  return { bx0, by0, bx1, by1, w: bx1 - bx0, h: by1 - by0 };
}

/**
 * CAD box (Y-up) -> fractions of render_bounds (Y-down).
 *
 * Returns null for a degenerate sheet rather than dividing by zero and emitting NaN
 * fractions, which would silently poison a saved template.
 */
export function zoneBoxToFractions(
  zone: ZoneBoxCad,
  bounds: RenderBoundsTuple,
): RegionFractions | null {
  const { bx0, by1, w, h } = spans(bounds);
  if (!(w > 0) || !(h > 0)) return null;

  return {
    xMin: (zone.xmin - bx0) / w,
    xMax: (zone.xmax - bx0) / w,
    // Flip and swap: CAD ymax is the visual top, which is the smaller fraction.
    yMin: (by1 - zone.ymax) / h,
    yMax: (by1 - zone.ymin) / h,
  };
}

/** Fractions (Y-down) -> CAD box (Y-up). Inverse of `zoneBoxToFractions`. */
export function fractionsToZoneBox(
  frac: RegionFractions,
  bounds: RenderBoundsTuple,
): ZoneBoxCad {
  const { bx0, by1, w, h } = spans(bounds);
  return {
    xmin: bx0 + frac.xMin * w,
    xmax: bx0 + frac.xMax * w,
    // Inverse of the flip above; yMax (larger fraction, lower on screen) is the CAD min.
    ymin: by1 - frac.yMax * h,
    ymax: by1 - frac.yMin * h,
  };
}

/**
 * Fractions (Y-down) -> screen rect.
 *
 * Mirrors the mapping in `useCanvasInteraction.ts`'s ROI hit-test exactly, including its
 * lack of Y inversion, so a drawn handle is always where the hit-test looks for it. Do not
 * substitute `worldToScreen` here — that applies the CAD flip and would put the boxes and
 * their handles in different places.
 */
export function fractionsToScreenRect(
  frac: RegionFractions,
  bounds: RenderBoundsTuple,
  norm: { xmin: number; ymin: number; normScale: number },
  viewport: { x: number; y: number; scale: number },
): { left: number; top: number; right: number; bottom: number } {
  const { bx0, by0, w, h } = spans(bounds);
  const effectiveScale = viewport.scale * norm.normScale;

  return {
    left: (bx0 + w * frac.xMin - norm.xmin) * effectiveScale + viewport.x,
    right: (bx0 + w * frac.xMax - norm.xmin) * effectiveScale + viewport.x,
    top: (by0 + h * frac.yMin - norm.ymin) * effectiveScale + viewport.y,
    bottom: (by0 + h * frac.yMax - norm.ymin) * effectiveScale + viewport.y,
  };
}

/** Clamps to the unit square and repairs inverted edges, so a drag can't persist a bad box. */
export function normalizeFractions(frac: RegionFractions): RegionFractions {
  const clamp = (v: number) => Math.min(1, Math.max(0, v));
  const xMin = clamp(frac.xMin);
  const xMax = clamp(frac.xMax);
  const yMin = clamp(frac.yMin);
  const yMax = clamp(frac.yMax);
  return {
    xMin: Math.min(xMin, xMax),
    xMax: Math.max(xMin, xMax),
    yMin: Math.min(yMin, yMax),
    yMax: Math.max(yMin, yMax),
  };
}
