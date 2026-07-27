/**
 * coordinateTransform.ts
 *
 * The single implementation of screen <-> world coordinate maths for the review canvas.
 *
 * ## Three conversions, not one
 *
 * Most call sites want `worldToScreen` / `screenToWorld`, which apply the CAD Y-flip
 * (CAD Y increases upward, canvas Y increases downward). Two call sites deliberately do
 * not, and they used to hand-roll their own inline maths with a "do not fix this" comment
 * as the only thing holding the deviation in place. They are now named functions, so the
 * deviation is expressed in the call rather than in a comment a future refactor can miss:
 *
 *  - `screenToWorldUnflipped` — ROI region editing works in percentage space against
 *    `render_bounds` directly, where the Y axis is not inverted. Applying the flip here
 *    would mirror every region box vertically.
 *
 *  - `screenDeltaToWorldDelta` — dragging a marker or pin converts a screen *delta*, not
 *    a point. The Y-flip `y -> (ymax + ymin) - y` has linear part -1, so it negates
 *    differences: a downward drag must decrease world Y. Transforming both endpoints and
 *    subtracting yields the same number, but a drag is tracked as a delta from a start
 *    position, so expressing it directly is what the call sites actually need — and it
 *    puts the sign inversion in one named place instead of four inline copies.
 *
 * ## Coordinate provenance
 *
 * Persisted coordinates carry a `CadPoint` envelope (space, layout, viewport index,
 * transform version, and the render bounds they were authored against) — see
 * `packages/types/src/coordinates.ts`. The canvas still works in bare `[x, y]`; the
 * envelope is unwrapped at the API boundary in `services/annotationsApi.ts`. Use
 * `boundsMatch` to check whether a stored point still refers to the bounds currently in
 * force before trusting its on-screen position.
 */

/**
 * NOTE: these mirror `packages/types/src/coordinates.ts` and
 * `services/backend/domain/models/cad_point.py`. They are redeclared here rather than
 * imported because `apps/desktop` has no dependency on `@ai-2d-checker/types` — nothing
 * in the app imports that package today, and wiring it up is a build-system change
 * (workspace dep, tsconfig paths, turbo build ordering) rather than a typing one.
 * Keep all three in step until that is addressed.
 */
export type CoordinateSpace = "model" | "paper" | "render";

export interface CadPoint {
  x: number;
  y: number;
  space: CoordinateSpace;
  layout: string | null;
  viewport_index: number;
  transform_version: number;
  /** Snapshot of render_bounds [xmin, ymin, xmax, ymax] at authoring time. */
  bounds: number[] | null;
}

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
 * Screen -> world WITHOUT the CAD Y-flip.
 *
 * ROI region editing works in percentage space measured directly against
 * `render_bounds`, where the Y axis is not inverted. Applying the flip would mirror
 * every region box vertically.
 *
 * This is a deliberate deviation from `screenToWorld`, not an oversight — it exists as
 * its own named function so the difference is visible at the call site instead of living
 * in a comment. Previously both ROI call sites hand-rolled this maths inline.
 */
export function screenToWorldUnflipped(
  sx: number,
  sy: number,
  norm: NormalizationResult,
  viewport: Viewport,
): { x: number; y: number } {
  const effectiveScale = viewport.scale * norm.normScale;
  return {
    x: norm.xmin + (sx - viewport.x) / effectiveScale,
    y: norm.ymin + (sy - viewport.y) / effectiveScale,
  };
}

/**
 * Converts a screen-space drag delta into a world-space delta.
 *
 * The Y-flip negates differences (its linear part is -1), so under bounds a downward
 * drag must *decrease* world Y. With no bounds there is no flip and the delta passes
 * through unchanged.
 *
 * Transforming both drag endpoints and subtracting gives the same result; this exists
 * because drags are tracked as a delta from a start position, and because the sign
 * inversion was previously copy-pasted inline at each drag site.
 */
export function screenDeltaToWorldDelta(
  dx: number,
  dy: number,
  norm: NormalizationResult,
  viewport: Viewport,
): { dx: number; dy: number } {
  const effectiveScale = viewport.scale * norm.normScale;
  const worldDx = dx / effectiveScale;
  const worldDy = dy / effectiveScale;
  return {
    dx: worldDx,
    dy: norm.hasBounds ? -worldDy : worldDy,
  };
}

/**
 * Projects a provenance-carrying CadPoint to screen space.
 *
 * Convenience over `worldToScreen` for callers holding an envelope rather than a pair.
 * It does not attempt to re-project across spaces: a point stamped in a different space
 * than the canvas is currently displaying cannot be corrected here, only detected — see
 * `boundsMatch`.
 */
export function cadPointToScreen(
  point: CadPoint,
  norm: NormalizationResult,
  viewport: Viewport,
): { x: number; y: number } {
  return worldToScreen(point.x, point.y, norm, viewport);
}

/**
 * Whether a stored point's authoring bounds still match the bounds now in force.
 *
 * `false` means the drawing was re-rendered against different bounds since the point was
 * placed, so its on-screen position no longer marks what the user marked. This condition
 * was previously undetectable — the pin simply moved. The backend reports the same thing
 * as `coordinate_drift` on annotation responses; this is the client-side equivalent for
 * points already in hand.
 *
 * Returns `true` when either side is unknown: absence of evidence is not drift.
 */
export function boundsMatch(
  point: CadPoint | null | undefined,
  bounds: RenderBounds | null | undefined,
  epsilon = 1e-6,
): boolean {
  if (!point?.bounds || point.bounds.length < 4 || !bounds) return true;
  const [xmin, ymin, xmax, ymax] = point.bounds;
  return (
    Math.abs(xmin - bounds.xmin) <= epsilon &&
    Math.abs(ymin - bounds.ymin) <= epsilon &&
    Math.abs(xmax - bounds.xmax) <= epsilon &&
    Math.abs(ymax - bounds.ymax) <= epsilon
  );
}

/** Extract the bare `[x, y]` the canvas works in from a coordinate envelope. */
export function cadPointToPair(point: CadPoint | null | undefined): [number, number] | null {
  if (!point || typeof point.x !== "number" || typeof point.y !== "number") return null;
  return [point.x, point.y];
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

/**
 * Clamps the viewport so that the zooming respects a minimum bound
 * and the panning respects the drawing boundaries, preventing the user
 * from losing the drawing off-screen.
 */
export function clampViewport(
  v: Viewport,
  bounds: RenderBounds | null | undefined,
  width: number,
  height: number
): Viewport {
  let drawW = 1000 * v.scale;
  let drawH = 1000 * v.scale;
  
  if (bounds && bounds.xmax - bounds.xmin > 0) {
    drawH = (bounds.ymax - bounds.ymin) * (1000 / (bounds.xmax - bounds.xmin)) * v.scale;
  }
  
  const scale = Math.max(0.81, Math.min(25, v.scale));
  
  if (bounds && bounds.xmax - bounds.xmin > 0) {
    drawW = 1000 * scale;
    drawH = (bounds.ymax - bounds.ymin) * (1000 / (bounds.xmax - bounds.xmin)) * scale;
  } else {
    drawW = 1000 * scale;
    drawH = 1000 * scale;
  }

  const paddingX = width * 0.5;
  const paddingY = height * 0.5;

  const minX = -drawW + width - paddingX;
  const maxX = paddingX;

  const minY = -drawH + height - paddingY;
  const maxY = paddingY;

  return {
    x: Math.min(Math.max(v.x, minX), maxX),
    y: Math.min(Math.max(v.y, minY), maxY),
    scale
  };
}
