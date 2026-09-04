/**
 * Rendering a RESHAPED zone: outline, vertex handles, and the edge hint.
 *
 * The silent failure this pins is a mismatch between what the canvas draws and what the
 * engine gates on. `views_exclusions` excludes a reshaped sibling on its OUTLINE; if the tint
 * punched its bounding box instead, the overlay would show content as excluded that is still
 * being compared — the exact class of defect
 * `Gotcha - The Views Overlay Showed a Region That Is Not Compared` records, reintroduced
 * through a different door.
 *
 * The edge hint has its own reason to be pinned: it is the only thing that makes node
 * insertion discoverable. It cannot be verified from a screenshot of a zone nobody is
 * hovering.
 */
import { describe, expect, it, vi } from "vitest";

import { getNormalization } from "../../utils/coordinateTransform";
import { renderZoneEditor } from "./renderEntities";
import { ZONE_KEYS, type DrawingZonesResponse } from "../../services/drawingsApi";
import { normalizeFractions, type RegionFractions } from "../../utils/zoneFractions";

const SHEET = { xmin: 0, ymin: 0, xmax: 840, ymax: 594 };
const BOUNDS_TUPLE = [SHEET.xmin, SHEET.ymin, SHEET.xmax, SHEET.ymax] as const;

class FakePath2D {
  rects: { left: number; top: number; w: number; h: number }[] = [];
  points: { x: number; y: number }[] = [];
  rect(left: number, top: number, w: number, h: number) {
    this.rects.push({ left, top, w, h });
  }
  moveTo(x: number, y: number) {
    this.points.push({ x, y });
  }
  lineTo(x: number, y: number) {
    this.points.push({ x, y });
  }
  closePath() {}
}
(globalThis as any).Path2D = FakePath2D;

function makeCtx() {
  const pathPoints: { x: number; y: number }[] = [];
  const strokedPaths: { x: number; y: number }[][] = [];
  const filledPaths: { x: number; y: number }[][] = [];
  const strokeRects: { left: number; top: number; w: number; h: number }[] = [];
  const fillRects: { left: number; top: number; w: number; h: number }[] = [];
  const arcs: { x: number; y: number; r: number }[] = [];
  const clipPaths: FakePath2D[] = [];

  const ctx = {
    _strokedPaths: strokedPaths,
    _filledPaths: filledPaths,
    _strokeRects: strokeRects,
    _fillRects: fillRects,
    _arcs: arcs,
    _clipPaths: clipPaths,
    beginPath: () => {
      pathPoints.length = 0;
    },
    rect: vi.fn(),
    moveTo: (x: number, y: number) => pathPoints.push({ x, y }),
    lineTo: (x: number, y: number) => pathPoints.push({ x, y }),
    closePath: vi.fn(),
    stroke: () => strokedPaths.push([...pathPoints]),
    fill: () => filledPaths.push([...pathPoints]),
    arc: (x: number, y: number, r: number) => arcs.push({ x, y, r }),
    clip: (p?: FakePath2D) => {
      if (p) clipPaths.push(p);
    },
    fillRect: (left: number, top: number, w: number, h: number) =>
      fillRects.push({ left, top, w, h }),
    strokeRect: (left: number, top: number, w: number, h: number) =>
      strokeRects.push({ left, top, w, h }),
    setLineDash: vi.fn(),
    measureText: (t: string) => ({ width: t.length * 6 }),
    fillText: vi.fn(),
    save: vi.fn(),
    restore: vi.fn(),
    setTransform: vi.fn(),
    lineWidth: 0,
    font: "",
    fillStyle: "",
    strokeStyle: "",
    globalAlpha: 1,
    textBaseline: "alphabetic" as CanvasTextBaseline,
  };
  return ctx as unknown as CanvasRenderingContext2D & typeof ctx;
}

function render(
  ctx: CanvasRenderingContext2D,
  customRegions: Record<string, RegionFractions>,
  opts: { selected?: string | null; hoveredHandleId?: string | null } = {},
) {
  const viewport = { x: 0, y: 0, scale: 1 };
  const norm = getNormalization(SHEET);
  renderZoneEditor({
    frame: {
      ctx,
      isExport: false,
      renderWidth: 800,
      renderHeight: 600,
      width: 800,
      height: 600,
      norm,
      scale: norm.normScale,
      transX: 0,
      transY: 0,
      minX: 0,
      minY: 0,
      maxX: 840,
      maxY: 594,
      currentViewportScale: 1,
      resolutionMultiplier: 1,
      viewport,
      markerPositionsRef: { current: {} },
    } as any,
    customRegions,
    renderBounds: BOUNDS_TUPLE,
    selectedRegion: opts.selected ?? null,
    hoveredHandleId: opts.hoveredHandleId ?? null,
    detected: {
      drawing_id: "d1",
      render_bounds: [SHEET.xmin, SHEET.ymin, SHEET.xmax, SHEET.ymax],
      ...Object.fromEntries(ZONE_KEYS.map((k) => [k, null])),
    } as DrawingZonesResponse,
  } as any);
}

/** An L: full square with the top-right quadrant cut out. */
const L_SHAPE: RegionFractions = normalizeFractions({
  xMin: 0,
  xMax: 1,
  yMin: 0,
  yMax: 1,
  points: [
    { x: 0, y: 0 },
    { x: 0.5, y: 0 },
    { x: 0.5, y: 0.5 },
    { x: 1, y: 0.5 },
    { x: 1, y: 1 },
    { x: 0, y: 1 },
  ],
});

const RECT: RegionFractions = { xMin: 0.1, xMax: 0.5, yMin: 0.1, yMax: 0.5 };

describe("renderZoneEditor — reshaped zones", () => {
  it("strokes a polygon path rather than a rectangle", () => {
    const ctx = makeCtx();
    render(ctx, { iso: L_SHAPE });

    expect(ctx._strokedPaths.some((p) => p.length === 6)).toBe(true);
    // The rectangle path must NOT also run, or the zone would be outlined twice and the
    // bounding box would read as the zone's edge.
    expect(ctx._strokeRects).toHaveLength(0);
  });

  it("still strokes a rect for an un-reshaped zone", () => {
    const ctx = makeCtx();
    render(ctx, { iso: RECT });

    expect(ctx._strokeRects).toHaveLength(1);
    expect(ctx._strokedPaths.filter((p) => p.length > 0)).toHaveLength(0);
  });

  it("fills the polygon, not its bounding box", () => {
    const ctx = makeCtx();
    render(ctx, { iso: L_SHAPE });

    expect(ctx._filledPaths.some((p) => p.length === 6)).toBe(true);
    // A filled bbox would tint the notch — showing content as inside a zone that excludes it.
    expect(ctx._fillRects.filter((r) => r.w > 700 && r.h > 500)).toHaveLength(0);
  });

  it("cuts a reshaped sibling out of the views tint on its OUTLINE, not its bbox", () => {
    const ctx = makeCtx();
    render(ctx, { views: { xMin: 0, xMax: 1, yMin: 0, yMax: 1 }, notes: L_SHAPE });

    // The hole path carries the outline's vertices. Punching the bounding box instead would
    // claim the notch is excluded from `views` while the engine still compares it.
    const holeWithOutline = ctx._clipPaths.find((p) => p.points.length === 6);
    expect(holeWithOutline).toBeDefined();
  });

  it("draws one handle per vertex when selected", () => {
    const ctx = makeCtx();
    render(ctx, { iso: L_SHAPE }, { selected: "iso" });

    // Six vertices; the four fixed corner handles would be wrong — there is no opposite edge
    // to hold on a polygon, so a corner resize has nothing to mean.
    const handleSquares = ctx._fillRects.filter((r) => r.w === 18 && r.h === 18);
    expect(handleSquares).toHaveLength(6);
  });

  it("keeps four corner handles on an un-reshaped zone", () => {
    const ctx = makeCtx();
    render(ctx, { iso: RECT }, { selected: "iso" });

    expect(ctx._fillRects.filter((r) => r.w === 18 && r.h === 18)).toHaveLength(4);
  });

  it("draws the add-node ghost on the hovered edge", () => {
    const ctx = makeCtx();
    render(ctx, { iso: RECT }, { selected: "iso", hoveredHandleId: "edge:0" });

    // Edge 0 is the top edge: the ghost sits at its midpoint.
    expect(ctx._arcs).toHaveLength(1);
    const screen = (v: number, min: number) => (v - min) * getNormalization(SHEET).normScale;
    expect(ctx._arcs[0].x).toBeCloseTo(screen(840 * 0.3, 0), 3);
    expect(ctx._arcs[0].y).toBeCloseTo(screen(594 * 0.1, 0), 3);
  });

  it("draws no ghost when no edge is hovered", () => {
    const ctx = makeCtx();
    render(ctx, { iso: RECT }, { selected: "iso", hoveredHandleId: "top-left" });
    expect(ctx._arcs).toHaveLength(0);
  });

  it("draws no ghost or handles when the zone is not selected", () => {
    const ctx = makeCtx();
    render(ctx, { iso: L_SHAPE }, { selected: null, hoveredHandleId: "edge:0" });
    expect(ctx._arcs).toHaveLength(0);
    expect(ctx._fillRects.filter((r) => r.w === 18 && r.h === 18)).toHaveLength(0);
  });
});
