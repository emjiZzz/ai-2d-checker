/**
 * zoneFractions.ts
 *
 * The single conversion between the two coordinate spaces zone boxes live in. Both are
 * correct in their own context, and they disagree on the direction of Y — which is the
 * one thing in this feature that is easy to get backwards and hard to notice.
 *
 * ## The two spaces
 *
 * 1. Detected zone boxes (`GET /drawings/:id/zones`) are absolute CAD units, Y-up:
 *    a larger `y` is nearer the top of the sheet. Verified against real entity coordinates
 *    rather than inferred — the two notes lines in `M7452A0N01_reference.dxf` sit at CAD
 *    y=599.5 and y=577.9 within bounds y −37.125…779.625, and they render 22% down from the
 *    sheet top, which is where they visibly are. Read-only rendering of these uses
 *    `worldToScreen`, which applies the flip.
 *
 * 2. `customRegions` / template fractions are 0..1 of `render_bounds`, Y-down:
 *    fraction 0 is the top of the sheet. Confirmed by the pre-existing defaults (`title`,
 *    a bottom-right title block, is `yMin: 0.75`) and by the drag hit-test in
 *    `useCanvasInteraction.ts`, where `yMin = 0` maps to `viewport.y` (screen top). That
 *    hit-test does not invert Y and is correct for this space — do not "fix" it.
 *
 * So converting between them flips Y and swaps min/max: a zone's CAD `ymax` becomes its
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
  /**
   * Optional polygon outline, same Y-DOWN fraction space, in draw order.
   *
   * A zone starts as a rectangle and stays one until the user inserts a node on an edge.
   * From then on `points` is the TRUTH about the zone's shape and the four scalars above are
   * its DERIVED bounding box — kept in sync by `normalizeFractions`, never edited directly.
   *
   * Additive on purpose. Every existing reader (drag hit-test, screen rect, template save,
   * the backend's 29 bbox-indexing sites) keeps working on the bounding box and needs no
   * knowledge of polygons; only the handful of places that decide whether an entity is
   * INSIDE a zone consult `points`. A stored template written before this existed simply has
   * no `points` and parses as the rectangle it always was — no migration.
   *
   * Fewer than 3 points is not a shape, so it is dropped back to the rectangle.
   */
  points?: FractionPoint[];
}

/** One vertex of a zone outline, as fractions of render_bounds, Y-DOWN (0 = top). */
export interface FractionPoint {
  x: number;
  y: number;
}

/** The minimum vertices that still enclose an area. Below this a polygon is meaningless. */
export const MIN_ZONE_POINTS = 3;

/**
 * A zone's outline, whatever shape it is: its own `points`, or the rectangle's four corners.
 *
 * This is the accessor every shape-aware caller should use, so that "rectangle" is simply the
 * 4-point case rather than a second code path. Corner order is clockwise on screen — top-left,
 * top-right, bottom-right, bottom-left — which matches the order the editor lays out handles,
 * so inserting a node on edge *i* always means "between corner i and corner i+1".
 */
export function shapePoints(frac: RegionFractions): FractionPoint[] {
  if (frac.points && frac.points.length >= MIN_ZONE_POINTS) return frac.points;
  return [
    { x: frac.xMin, y: frac.yMin },
    { x: frac.xMax, y: frac.yMin },
    { x: frac.xMax, y: frac.yMax },
    { x: frac.xMin, y: frac.yMax },
  ];
}

/** True when this zone has been reshaped away from a plain rectangle. */
export function isPolygonZone(frac: RegionFractions | null | undefined): boolean {
  return Boolean(frac?.points && frac.points.length >= MIN_ZONE_POINTS);
}

/** Bounding box of an outline, in the same Y-DOWN fraction space. */
export function pointsToBounds(points: FractionPoint[]): RegionFractions {
  const xs = points.map((p) => p.x);
  const ys = points.map((p) => p.y);
  return {
    xMin: Math.min(...xs),
    xMax: Math.max(...xs),
    yMin: Math.min(...ys),
    yMax: Math.max(...ys),
  };
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

/**
 * One outline vertex (Y-DOWN fraction) -> CAD point (Y-up).
 *
 * NOTE the asymmetry with `fractionsToZoneBox`: a *box* conversion swaps min and max, because
 * "min" and "max" are names about magnitude and the flip reverses which edge is which. A
 * *point* has no min/max to swap — it is only the flip, `by1 - y * h`. Applying the box rule
 * to a point (or vice versa) is the mistake this whole module exists to prevent, and it
 * produces a mirrored outline that still looks like a plausible zone.
 */
export function fractionPointToCad(
  point: FractionPoint,
  bounds: RenderBoundsTuple,
): { x: number; y: number } {
  const { bx0, by1, w, h } = spans(bounds);
  return { x: bx0 + point.x * w, y: by1 - point.y * h };
}

/** CAD point (Y-up) -> outline vertex (Y-DOWN fraction). Inverse of `fractionPointToCad`. */
export function cadPointToFraction(
  point: { x: number; y: number },
  bounds: RenderBoundsTuple,
): FractionPoint | null {
  const { bx0, by1, w, h } = spans(bounds);
  if (!(w > 0) || !(h > 0)) return null;
  return { x: (point.x - bx0) / w, y: (by1 - point.y) / h };
}

/**
 * Outline vertices -> screen points.
 *
 * Uses the same mapping as `fractionsToScreenRect`, including its lack of Y inversion, so the
 * polygon and its drag handles land in the same place. See that function's note.
 */
export function shapePointsToScreen(
  frac: RegionFractions,
  bounds: RenderBoundsTuple,
  norm: { xmin: number; ymin: number; normScale: number },
  viewport: { x: number; y: number; scale: number },
): { x: number; y: number }[] {
  const { bx0, by0, w, h } = spans(bounds);
  const effectiveScale = viewport.scale * norm.normScale;
  return shapePoints(frac).map((p) => ({
    x: (bx0 + w * p.x - norm.xmin) * effectiveScale + viewport.x,
    y: (by0 + h * p.y - norm.ymin) * effectiveScale + viewport.y,
  }));
}

/**
 * Clamps to the unit square and repairs inverted edges, so a drag can't persist a bad box.
 *
 * For a polygon the scalars are DERIVED, not repaired: they are recomputed from the clamped
 * points, so the bounding box every non-shape-aware consumer reads can never disagree with the
 * outline. A `points` array too short to enclose an area is discarded, which degrades the zone
 * to its rectangle rather than storing a shape nothing can test containment against.
 */
export function normalizeFractions(frac: RegionFractions): RegionFractions {
  const clamp = (v: number) => Math.min(1, Math.max(0, v));

  if (frac.points && frac.points.length >= MIN_ZONE_POINTS) {
    const points = frac.points.map((p) => ({ x: clamp(p.x), y: clamp(p.y) }));
    return { ...pointsToBounds(points), points };
  }

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

/**
 * Inserts a vertex at the midpoint of edge `edgeIndex` (between vertex i and i+1).
 *
 * Converts a rectangle to an explicit 4-point outline on the first insert, which is why the
 * corner order in `shapePoints` is load-bearing: edge 0 is the top edge, so "add a node on the
 * top edge" has to mean the same thing before and after the zone stops being a rectangle.
 */
export function insertPointOnEdge(frac: RegionFractions, edgeIndex: number): RegionFractions {
  const points = shapePoints(frac);
  const i = ((edgeIndex % points.length) + points.length) % points.length;
  const a = points[i];
  const b = points[(i + 1) % points.length];
  const next = [...points];
  next.splice(i + 1, 0, { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 });
  return normalizeFractions({ ...frac, points: next });
}

/**
 * Removes vertex `pointIndex`. A no-op at the floor, so a zone can never be reduced below an
 * enclosing shape — deleting the third-to-last node would leave a line, which contains nothing
 * and would silently empty the zone.
 */
export function removePointAt(frac: RegionFractions, pointIndex: number): RegionFractions {
  const points = shapePoints(frac);
  if (points.length <= MIN_ZONE_POINTS) return frac;
  const next = points.filter((_, idx) => idx !== pointIndex);
  return normalizeFractions({ ...frac, points: next });
}

/** Moves vertex `pointIndex` to a new position, keeping the derived bounds in step. */
export function movePointTo(
  frac: RegionFractions,
  pointIndex: number,
  position: FractionPoint,
): RegionFractions {
  const points = shapePoints(frac).map((p, idx) => (idx === pointIndex ? position : p));
  return normalizeFractions({ ...frac, points });
}

/**
 * Translates a whole zone — the "drag inside to move" gesture.
 *
 * A polygon moves by its vertices; a rectangle keeps its existing edge-based path so an
 * un-reshaped zone behaves exactly as it always did. Clamping happens per-vertex in
 * `normalizeFractions`, so dragging a polygon hard against the sheet edge flattens it against
 * that edge rather than refusing to move, which is the same thing the rectangle does.
 */
export function translateShape(
  frac: RegionFractions,
  dx: number,
  dy: number,
): RegionFractions {
  if (isPolygonZone(frac)) {
    const points = shapePoints(frac).map((p) => ({ x: p.x + dx, y: p.y + dy }));
    return normalizeFractions({ ...frac, points });
  }
  return normalizeFractions({
    xMin: frac.xMin + dx,
    xMax: frac.xMax + dx,
    yMin: frac.yMin + dy,
    yMax: frac.yMax + dy,
  });
}

/**
 * Winding-number point-in-polygon, in fraction space. Mirrors the backend
 * `zone_geometry.point_in_polygon` — the two decide the same question about the same shape,
 * and if they disagree the canvas shows a region the audit is not using.
 */
export function pointInShape(frac: RegionFractions, x: number, y: number): boolean {
  if (!isPolygonZone(frac)) {
    return x >= frac.xMin && x <= frac.xMax && y >= frac.yMin && y <= frac.yMax;
  }
  const pts = shapePoints(frac);
  let inside = false;
  for (let i = 0, j = pts.length - 1; i < pts.length; j = i, i += 1) {
    const a = pts[i];
    const b = pts[j];
    if (a.y > y !== b.y > y && x < ((b.x - a.x) * (y - a.y)) / (b.y - a.y) + a.x) {
      inside = !inside;
    }
  }
  return inside;
}

/**
 * The one zone set to save, from the two panes' regions plus which zones the user aligned where.
 *
 * Pure, for the same reason as `zonesToTemplatePayload` below: the defect was invisible inside a
 * component that cannot be mounted without flexlayout, a canvas and a ResizeObserver.
 *
 * The defect this exists to prevent. The call site was `{ ...oldReg, ...newReg }`, described
 * as merging the two sides so "the REVISION's boxes win on any zone aligned differently on the
 * two sides". That reads correctly only if the two arguments hold *edited* zones. They do not —
 * `getRegionsFor` returns a drawing's COMPLETE zone set, seeded from detection and stamped from
 * the template on every editor open, so both objects always carry all seven keys and the spread
 * resolves to "the revision's boxes, always".
 *
 * The consequence was that editing a zone on the reference pane and saving was a silent
 * no-op: the reference's box was dropped before the request was built, and `applyZoneTemplate`
 * then wrote the revision-derived set back over both panes, so the edit visibly snapped back and
 * `userAlignedZoneKeys` was cleared along with it. The user's report was "I adjusted it and
 * clicked save, it just pops back there."
 *
 * The tie-break is unchanged where the user has expressed no preference — the revision still
 * wins, which keeps every existing template stable. It is overridden only for a zone the user
 * aligned on the reference and NOT on the revision, which is the only case where the old
 * behaviour discarded information it had.
 *
 * This does not make one template fit two differently-laid-out sides; nothing here can. See
 * `docs/vault/06 - .../Gotcha - One Zone Template Cannot Fit Two Sides.md`.
 */
export function mergeSidesForTemplate(
  referenceRegions: Record<string, RegionFractions | undefined | null>,
  revisionRegions: Record<string, RegionFractions | undefined | null>,
  referenceAligned: readonly string[] = [],
  revisionAligned: readonly string[] = [],
): Record<string, RegionFractions> {
  const merged: Record<string, RegionFractions> = {};
  for (const [key, frac] of Object.entries({ ...referenceRegions, ...revisionRegions })) {
    if (frac) merged[key] = frac;
  }

  const revisionOwns = new Set(revisionAligned);
  for (const key of referenceAligned) {
    // Aligned on BOTH sides is a genuine conflict, and the documented tie-break stands.
    if (revisionOwns.has(key)) continue;
    const frac = referenceRegions[key];
    if (frac) merged[key] = frac;
  }
  return merged;
}

/**
 * Shapes a drawing's zone regions into the payload `saveZoneTemplate` sends.
 *
 * Pure, and extracted from `TwoDWorkspace` on purpose: the bug it fixes was invisible in a
 * component that cannot be mounted without flexlayout, a canvas and a ResizeObserver. Same
 * reason `zoneGate.ts` is pure.
 *
 * The defect this exists to prevent. The original built each zone as a four-field object
 * literal — `{ xMin, xMax, yMin, yMax }` — which was complete when a zone *was* four scalars.
 * Reshaping added `points`, and this construction site was never updated, so every hand-drawn
 * outline was silently flattened to its bounding box on save. Silent because the outline is
 * additive: a zone with no `points` is a valid rectangle, so the field simply vanished rather
 * than erroring, and the caller then wrote the flattened version back over the live regions.
 *
 * Spreads `frac` first so a future field added to `RegionFractions` cannot be dropped the
 * same way — the failure mode is a missing key, and a spread has no key list to fall behind.
 */
export function zonesToTemplatePayload(
  regions: Record<string, RegionFractions | undefined | null>,
): Record<string, RegionFractions> {
  const clamp01 = (v: number) => Math.max(0, Math.min(1, Number(v) || 0));
  const zones: Record<string, RegionFractions> = {};

  for (const [key, frac] of Object.entries(regions)) {
    if (!frac) continue;
    const shaped: RegionFractions = {
      ...frac,
      xMin: clamp01(frac.xMin),
      xMax: clamp01(frac.xMax),
      yMin: clamp01(frac.yMin),
      yMax: clamp01(frac.yMax),
    };

    // Fewer than MIN_ZONE_POINTS is not a shape — it would contain nothing — so a degenerate
    // outline is DELETED rather than left to ride through on the spread above. Setting it
    // conditionally is not enough: the spread has already copied it.
    if (frac.points && frac.points.length >= MIN_ZONE_POINTS) {
      shaped.points = frac.points.map((p) => ({ x: clamp01(p.x), y: clamp01(p.y) }));
    } else {
      delete shaped.points;
    }
    zones[key] = shaped;
  }
  return zones;
}
