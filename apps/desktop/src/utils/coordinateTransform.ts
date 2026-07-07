/**
 * coordinateTransform.ts
 *
 * Consolidates 6-7 duplicated inline coordinate-math blocks from DrawingCanvas.tsx
 * into a single verified implementation.
 *
 * Verified call-site inventory (DrawingCanvas.tsx as of 2026-07-07):
 *
 *  Site A  ~line 340   renderContent()         — derives normalizationScale/normXMin/normYMin.
 *                                                No ymax extracted here. Y-flip done inline per-marker later.
 *  Site B  ~line 1005  selectedViolation effect — full 4-tuple [xmin,ymin,xmax,ymax], worldToScreen pattern.
 *  Site C  ~line 1055  handleKeyDown 'f'        — identical to Site B.
 *  Site D  ~line 1152  handleMouseDown (hit)    — 3-tuple [xmin,ymin], no ymax; Y-flip via separate hasBounds block.
 *  Site E  ~line 1222  handleMouseDown (ROI)    — 3-tuple [xmin,ymin], NO Y-flip (intentional: percentage space).
 *  Site F  ~line 1274  handleMouseMove (laser)  — 3-tuple [xmin,ymin], sign-inverted Y
 *                                                 (stdY = ymin - (my - viewport.y) / effectiveScale).
 *                                                 // REFACTOR-NOTE: sign inversion vs all other sites is intentional —
 *                                                 // laser-sync stores a "CAD Y going up" value directly, not screen-Y.
 *                                                 // Do not "fix" to match the others; this is the correct behavior.
 *  Site G  ~line 1568  handleContextMenu        — 3-tuple [xmin,ymin], Y-flip via separate hasBounds block.
 *
 * Sites B, C, D, G all Y-flip using the same pattern: hasBounds ? (ymax + ymin - raw_vy) : raw_vy
 * Site E skips the Y-flip deliberately (percentage-space ROI calculation, Y axis isn't flipped there).
 * Site F sign-inverts Y deliberately (laser-sync coordinate convention, documented above).
 */

export interface RenderBounds {
  xmin: number;
  ymin: number;
  xmax: number;
  ymax: number;
}

export interface Viewport {
  x: number;
  y: number;
  scale: number;
}

export type NormalizationResult =
  | { hasBounds: false; normScale: 1; xmin: 0; ymin: 0; ymax: 0 }
  | { hasBounds: true; normScale: number; xmin: number; ymin: number; ymax: number };

/**
 * Derives the normalization coefficients from a drawing's render_bounds.
 *
 * The 1000-unit normalization maps the drawing width to a fixed 1000-unit
 * space so viewport.scale is always relative to that width regardless of
 * the actual CAD coordinate magnitude.
 *
 * @param bounds - The render_bounds object, or null/undefined if not available.
 * @returns Normalization result with hasBounds flag and derived coefficients.
 */
export function getNormalization(bounds: RenderBounds | null | undefined): NormalizationResult {
  if (!bounds || bounds.xmax - bounds.xmin <= 0) {
    return { hasBounds: false, normScale: 1, xmin: 0, ymin: 0, ymax: 0 };
  }
  return {
    hasBounds: true,
    normScale: 1000 / (bounds.xmax - bounds.xmin),
    xmin: bounds.xmin,
    ymin: bounds.ymin,
    ymax: bounds.ymax,
  };
}

/**
 * Converts a world (CAD) coordinate to a screen (canvas pixel) coordinate.
 *
 * CAD Y-axis is flipped relative to canvas Y-axis when render_bounds are present.
 * This matches Sites B, C, D, G of the original DrawingCanvas.tsx.
 *
 * @param wx - World X coordinate.
 * @param wy - World Y coordinate (CAD space, Y-up).
 * @param norm - Normalization result from getNormalization().
 * @param viewport - Current viewport state.
 * @returns Screen {x, y} in canvas pixel space.
 */
export function worldToScreen(
  wx: number,
  wy: number,
  norm: NormalizationResult,
  viewport: Viewport,
): { x: number; y: number } {
  const effectiveScale = viewport.scale * norm.normScale;
  // Y-flip: CAD Y increases upward, canvas Y increases downward.
  // When hasBounds is false (no render_bounds), we skip the flip (passthrough).
  const flippedY = norm.hasBounds ? norm.ymax + norm.ymin - wy : wy;
  return {
    x: (wx - norm.xmin) * effectiveScale + viewport.x,
    y: (flippedY - norm.ymin) * effectiveScale + viewport.y,
  };
}

/**
 * Converts a screen (canvas pixel) coordinate to a world (CAD) coordinate.
 *
 * This is the inverse of worldToScreen and matches the screenToWorld pattern
 * used in Sites D, E, G of the original DrawingCanvas.tsx.
 *
 * Note: Site E (ROI center drag) intentionally does NOT apply the Y-flip — it
 * works in percentage space where the Y-axis is not inverted. Callers requiring
 * that behavior should use this function and skip the Y-flip result themselves,
 * or use norm with hasBounds: false.
 *
 * @param sx - Screen X in canvas pixel space.
 * @param sy - Screen Y in canvas pixel space.
 * @param norm - Normalization result from getNormalization().
 * @param viewport - Current viewport state.
 * @returns World {x, y} in CAD coordinate space (with Y-flip applied if hasBounds).
 */
export function screenToWorld(
  sx: number,
  sy: number,
  norm: NormalizationResult,
  viewport: Viewport,
): { x: number; y: number } {
  const effectiveScale = viewport.scale * norm.normScale;
  const rawWy = norm.ymin + (sy - viewport.y) / effectiveScale;
  return {
    x: norm.xmin + (sx - viewport.x) / effectiveScale,
    // Apply Y-flip inverse: same formula as worldToScreen (it's its own inverse for the flip)
    y: norm.hasBounds ? norm.ymax + norm.ymin - rawWy : rawWy,
  };
}

/**
 * Parses a raw render_bounds array [xmin, ymin, xmax, ymax] into a RenderBounds object.
 * Convenience helper for callers reading directly from drawing.metadata.render_bounds.
 *
 * @param raw - Array in [xmin, ymin, xmax, ymax] order, as stored in drawing.metadata.render_bounds.
 * @returns RenderBounds object, or null if input is falsy/invalid.
 */
export function parseBounds(raw: number[] | null | undefined): RenderBounds | null {
  if (!raw || raw.length < 4) return null;
  const [xmin, ymin, xmax, ymax] = raw;
  return { xmin, ymin, xmax, ymax };
}
