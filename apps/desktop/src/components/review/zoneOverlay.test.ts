/**
 * Tests for renderZoneEditor, the single zone renderer.
 *
 * These pin the four failure modes that are silent — each one produces a plausible-looking
 * canvas rather than an error, so none would be caught by tsc or by looking at a screenshot
 * of a single drawing:
 *
 *   - a vertically mirrored overlay (the CAD Y-flip applied backwards); most zones sit
 *     roughly symmetrically about the sheet centre, so a mirrored box looks almost right
 *   - stroke/text that scales with zoom into unreadable slabs
 *   - debug geometry leaking into an exported compliance report
 *   - seven identical placeholder rectangles rendered as if they meant something
 */
import { describe, expect, it, vi } from "vitest";

import { getNormalization } from "../../utils/coordinateTransform";
import { renderZoneEditor } from "./renderEntities";
import {
  NO_SHEET_BOUNDS,
  ZONE_KEYS,
  type DrawingZonesResponse,
  type ZoneBBox,
} from "../../services/drawingsApi";
import { zoneBoxToFractions } from "../../utils/zoneFractions";
import type { RegionFractions } from "../../stores/reviewStore";

const SHEET = { xmin: 0, ymin: 0, xmax: 840, ymax: 594 };
const BOUNDS_TUPLE = [SHEET.xmin, SHEET.ymin, SHEET.xmax, SHEET.ymax] as const;

interface RectCall {
  left: number;
  top: number;
  w: number;
  h: number;
}

/** Minimal 2D-context stand-in that records the calls these tests assert on. */
/** Records the rects a Path2D is built from, so a clip's geometry can be asserted.
 *  jsdom ships no canvas implementation, so there is no real Path2D to use here. */
class FakePath2D {
  rects: RectCall[] = [];
  rect(left: number, top: number, w: number, h: number) {
    this.rects.push({ left, top, w, h });
  }
}
(globalThis as any).Path2D = FakePath2D;

function makeCtx() {
  const strokeRects: RectCall[] = [];
  const fillRects: RectCall[] = [];
  const lineWidths: number[] = [];
  const fonts: string[] = [];
  const lineDashes: number[][] = [];
  /** One entry per clip(): the rects of the path, or null for the current-path form. */
  const clips: (RectCall[] | null)[] = [];
  const pathRects: RectCall[] = [];

  const ctx = {
    _strokeRects: strokeRects,
    _fillRects: fillRects,
    _lineWidths: lineWidths,
    _fonts: fonts,
    _lineDashes: lineDashes,
    _clips: clips,
    _pathRects: pathRects,
    beginPath: () => {
      pathRects.length = 0;
    },
    rect: (left: number, top: number, w: number, h: number) =>
      pathRects.push({ left, top, w, h }),
    clip: (path?: FakePath2D) => clips.push(path ? [...path.rects] : null),
    set lineWidth(v: number) {
      lineWidths.push(v);
    },
    get lineWidth() {
      return lineWidths[lineWidths.length - 1] ?? 0;
    },
    set font(v: string) {
      fonts.push(v);
    },
    get font() {
      return fonts[fonts.length - 1] ?? "";
    },
    fillStyle: "",
    strokeStyle: "",
    globalAlpha: 1,
    textBaseline: "alphabetic" as CanvasTextBaseline,
    save: vi.fn(),
    restore: vi.fn(),
    setTransform: vi.fn(),
    fillRect: (left: number, top: number, w: number, h: number) =>
      fillRects.push({ left, top, w, h }),
    strokeRect: (left: number, top: number, w: number, h: number) =>
      strokeRects.push({ left, top, w, h }),
    setLineDash: (d: number[]) => lineDashes.push([...d]),
    measureText: (t: string) => ({ width: t.length * 6 }),
    fillText: vi.fn(),
  };
  return ctx as unknown as CanvasRenderingContext2D & typeof ctx;
}

function makeFrame(
  ctx: CanvasRenderingContext2D,
  opts: { scale?: number; isExport?: boolean } = {},
) {
  const viewport = { x: 0, y: 0, scale: opts.scale ?? 1 };
  const norm = getNormalization(SHEET);
  return {
    ctx,
    isExport: opts.isExport ?? false,
    renderWidth: 800,
    renderHeight: 600,
    width: 800,
    height: 600,
    norm,
    scale: viewport.scale * norm.normScale,
    transX: 0,
    transY: 0,
    minX: 0,
    minY: 0,
    maxX: 840,
    maxY: 594,
    currentViewportScale: viewport.scale,
    resolutionMultiplier: 1,
    viewport,
    markerPositionsRef: { current: {} },
  } as any;
}

const zone = (
  xmin: number,
  ymin: number,
  xmax: number,
  ymax: number,
  confidence = "content_aware",
): ZoneBBox => ({ xmin, ymin, xmax, ymax, confidence });

/**
 * Drives the merged renderer the way the app does: geometry comes from `customRegions`
 * fractions seeded from the detected CAD box, and the detected payload rides along for the
 * confidence marker. Keeping the seeding in the harness means these tests exercise the same
 * CAD->fraction conversion the editor does, so a regression there fails here too.
 */
function renderFromDetected(
  ctx: CanvasRenderingContext2D,
  zones: DrawingZonesResponse,
  opts: {
    scale?: number; isExport?: boolean; selected?: string | null;
    pinnedKeys?: readonly string[];
  } = {},
) {
  const customRegions: Record<string, RegionFractions> = {};
  for (const key of ZONE_KEYS) {
    const box = zones[key];
    if (!box) continue;
    const frac = zoneBoxToFractions(box, BOUNDS_TUPLE);
    if (frac) customRegions[key] = frac;
  }
  renderZoneEditor({
    frame: makeFrame(ctx, opts),
    customRegions,
    renderBounds: BOUNDS_TUPLE,
    selectedRegion: opts.selected ?? null,
    hoveredHandleId: null,
    detected: zones,
    pinnedKeys: opts.pinnedKeys,
  });
}

/** Only `title` populated, so assertions map to a single rect. */
function onlyTitle(box: ZoneBBox): DrawingZonesResponse {
  const empty = Object.fromEntries(ZONE_KEYS.map((k) => [k, null]));
  return {
    drawing_id: "d1",
    render_bounds: [SHEET.xmin, SHEET.ymin, SHEET.xmax, SHEET.ymax],
    ...empty,
    title: box,
  } as DrawingZonesResponse;
}

describe("renderZoneEditor — CAD Y-flip", () => {
  it("maps world ymax to the SMALLER screen y", () => {
    const ctx = makeCtx();
    // A box in the sheet's lower half in CAD terms (y 0..100 of 594).
    renderFromDetected(ctx, onlyTitle(zone(0, 0, 100, 100)));

    expect(ctx._strokeRects).toHaveLength(1);
    const rect = ctx._strokeRects[0];
    // CAD y=0 is the BOTTOM of the sheet, so it must land at the LARGER screen y.
    // If the flip were dropped or inverted, this box would render at the top instead.
    const sheetHeightOnScreen = (SHEET.ymax - SHEET.ymin) * makeFrame(ctx).scale;
    expect(rect.top + rect.h).toBeCloseTo(sheetHeightOnScreen, 4);
    expect(rect.top).toBeGreaterThan(sheetHeightOnScreen / 2);
  });

  it("puts a top-of-sheet zone above a bottom-of-sheet zone on screen", () => {
    const ctxTop = makeCtx();
    const ctxBottom = makeCtx();
    // CAD-high y = visually top.
    renderFromDetected(ctxTop, onlyTitle(zone(0, 500, 100, 594)));
    renderFromDetected(ctxBottom, onlyTitle(zone(0, 0, 100, 94)));

    expect(ctxTop._strokeRects[0].top).toBeLessThan(ctxBottom._strokeRects[0].top);
  });

  it("produces a positive-area rect regardless of flip direction", () => {
    const ctx = makeCtx();
    renderFromDetected(ctx, onlyTitle(zone(10, 20, 110, 220)));

    const rect = ctx._strokeRects[0];
    expect(rect.w).toBeGreaterThan(0);
    expect(rect.h).toBeGreaterThan(0);
  });
});

describe("renderZoneEditor — constant apparent size", () => {
  // Anchored at the sheet's top-left corner in CAD terms (y near ymax), which after the
  // Y-flip is screen-space top-left — so it stays inside the canvas as zoom increases.
  // A mid-sheet box would leave an 800x600 viewport at 10x and be culled, which is
  // correct behavior but tests nothing about stroke width.
  const cornerBox = () => onlyTitle(zone(0, 574, 20, 594));

  it("keeps stroke width and font identical at 1x and 10x zoom", () => {
    const at1 = makeCtx();
    const at10 = makeCtx();

    renderFromDetected(at1, cornerBox(), { scale: 1 });
    renderFromDetected(at10, cornerBox(), { scale: 10 });

    expect(at10._strokeRects).toHaveLength(1); // guard: the box really is still on screen
    expect(at1._lineWidths).toEqual(at10._lineWidths);
    expect(at1._fonts).toEqual(at10._fonts);
    expect(at1._lineWidths[0]).toBe(1.5);
  });

  it("still scales the box itself with zoom", () => {
    const at1 = makeCtx();
    const at4 = makeCtx();

    renderFromDetected(at1, cornerBox(), { scale: 1 });
    renderFromDetected(at4, cornerBox(), { scale: 4 });

    expect(at4._strokeRects[0].w).toBeCloseTo(at1._strokeRects[0].w * 4, 4);
  });
});

describe("renderZoneEditor — confidence styling", () => {
  it("draws a solid border for content_aware zones", () => {
    const ctx = makeCtx();
    renderFromDetected(ctx, onlyTitle(zone(100, 100, 200, 200, "content_aware")));
    // First setLineDash of the pair is the style applied to strokeRect.
    expect(ctx._lineDashes[0]).toEqual([]);
  });

  it("draws a dashed border for percentage_fallback zones", () => {
    const ctx = makeCtx();
    renderFromDetected(ctx, onlyTitle(zone(100, 100, 200, 200, "percentage_fallback")));
    expect(ctx._lineDashes[0]).toEqual([6, 4]);
  });

  it("marks a fallback zone's badge with '?'", () => {
    const ctx = makeCtx();
    renderFromDetected(ctx, onlyTitle(zone(100, 100, 200, 200, "percentage_fallback")));
    const labels = (ctx.fillText as any).mock.calls.map((c: any[]) => c[0]);
    expect(labels[0]).toContain("?");
  });

  // A hand-pinned zone is the most authoritative source of a zone box there is, but it is
  // by definition NOT something the detector anchored. Reading `confidence` alone therefore
  // drew the user's own alignment as a dashed guess — the visible half of the zone template
  // being write-only.
  it("draws a solid border for a pinned zone the detector only guessed", () => {
    const ctx = makeCtx();
    renderFromDetected(
      ctx, onlyTitle(zone(100, 100, 200, 200, "percentage_fallback")),
      { pinnedKeys: ["title"] },
    );
    expect(ctx._lineDashes[0]).toEqual([]);
  });

  it("omits the '?' badge for a pinned zone", () => {
    const ctx = makeCtx();
    renderFromDetected(
      ctx, onlyTitle(zone(100, 100, 200, 200, "percentage_fallback")),
      { pinnedKeys: ["title"] },
    );
    const labels = (ctx.fillText as any).mock.calls.map((c: any[]) => c[0]);
    expect(labels[0]).not.toContain("?");
  });

  it("a pin on a DIFFERENT zone does not clear this one's guess marker", () => {
    const ctx = makeCtx();
    renderFromDetected(
      ctx, onlyTitle(zone(100, 100, 200, 200, "percentage_fallback")),
      { pinnedKeys: ["bom"] },
    );
    expect(ctx._lineDashes[0]).toEqual([6, 4]);
  });
});

describe("renderZoneEditor — cases that must draw nothing", () => {
  it("suppresses the whole overlay when detection had no sheet bounds", () => {
    const ctx = makeCtx();
    const placeholder = zone(0, 0, 1000, 1000, NO_SHEET_BOUNDS);
    const zones = {
      drawing_id: "d1",
      render_bounds: null,
      ...Object.fromEntries(ZONE_KEYS.map((k) => [k, placeholder])),
    } as DrawingZonesResponse;

    renderFromDetected(ctx, zones);

    expect(ctx._strokeRects).toHaveLength(0);
    expect(ctx._fillRects).toHaveLength(0);
  });

  it("never draws into an export (compliance report images use this same path)", () => {
    const ctx = makeCtx();
    renderFromDetected(ctx, onlyTitle(zone(100, 100, 200, 200)), { isExport: true });

    expect(ctx._strokeRects).toHaveLength(0);
  });

  it("culls a box entirely outside the viewport", () => {
    const ctx = makeCtx();
    // Far to the right of an 800px-wide canvas.
    renderFromDetected(ctx, onlyTitle(zone(50_000, 100, 50_100, 200)));

    expect(ctx._strokeRects).toHaveLength(0);
  });

  it("handles a null payload without throwing", () => {
    const ctx = makeCtx();
    expect(() =>
      renderZoneEditor({
        frame: makeFrame(ctx),
        customRegions: {},
        renderBounds: BOUNDS_TUPLE,
        selectedRegion: null,
        hoveredHandleId: null,
        detected: null,
      }),
    ).not.toThrow();
    expect(ctx._strokeRects).toHaveLength(0);
  });

  it("skips individual null zones but still draws the populated ones", () => {
    const ctx = makeCtx();
    renderFromDetected(ctx, onlyTitle(zone(100, 100, 200, 200)));
    // Six of seven keys are null in onlyTitle().
    expect(ctx._strokeRects).toHaveLength(1);
  });
});

/**
 * The `views` tint must show what is COMPARED, not the rectangle.
 *
 * A pinned `views` is a plain rectangle over the whole drawing area, so on screen it swallows
 * notes / BOM / title / iso — while the backend has already excluded every one of them
 * (`scope_entities_to_views` + `VIEWS_EXCLUDED_ZONES`; measured on the M7452A0N01 pair, 423 of
 * 508 anchors inside the reference's views rectangle sit in a sibling zone). Filling the raw
 * rectangle asserts those regions are being diffed as drawing geometry. They are not, and the
 * discrepancy was reported as a scoping bug.
 *
 * Silent failure mode: this is a tint. Getting it wrong produces a plausible canvas, never an
 * error, and the thing it misrepresents is invisible unless you already know the answer.
 */
function viewsWith(
  viewsBox: ZoneBBox,
  siblings: Partial<Record<string, ZoneBBox>> = {},
): DrawingZonesResponse {
  const empty = Object.fromEntries(ZONE_KEYS.map((k) => [k, null]));
  return {
    drawing_id: "d1",
    render_bounds: [SHEET.xmin, SHEET.ymin, SHEET.xmax, SHEET.ymax],
    ...empty,
    views: viewsBox,
    ...siblings,
  } as DrawingZonesResponse;
}

describe("renderZoneEditor — the views tint excludes sibling zones", () => {
  it("cuts a hole for each sibling that has a box", () => {
    const ctx = makeCtx();
    renderFromDetected(
      ctx,
      viewsWith(zone(0, 0, 840, 594), {
        notes: zone(50, 400, 250, 550),
        bom: zone(500, 400, 800, 550),
      }),
    );

    // One clip per sibling, each an even-odd (outer canvas + hole) path.
    const holeClips = ctx._clips.filter((c): c is RectCall[] => c !== null);
    expect(holeClips).toHaveLength(2);
    for (const rects of holeClips) {
      expect(rects).toHaveLength(2);
      // First rect is the full canvas, second is the hole.
      expect(rects[0]).toEqual({ left: 0, top: 0, w: 800, h: 600 });
      expect(rects[1].w).toBeGreaterThan(0);
      expect(rects[1].h).toBeGreaterThan(0);
    }
    // The tint is still painted — the zone is subtracted, not suppressed.
    expect(ctx._fillRects.length).toBeGreaterThan(0);
  });

  it("cuts no holes when views is the only zone", () => {
    const ctx = makeCtx();
    renderFromDetected(ctx, viewsWith(zone(0, 0, 840, 594)));

    expect(ctx._clips.filter((c) => c !== null)).toHaveLength(0);
    // Still clipped to its own rect, so the fill cannot bleed outside the zone.
    expect(ctx._clips.some((c) => c === null)).toBe(true);
  });

  it("leaves the full outline so the box stays draggable and resizable", () => {
    const ctx = makeCtx();
    renderFromDetected(
      ctx,
      viewsWith(zone(0, 0, 840, 594), { notes: zone(50, 400, 250, 550) }),
    );

    // The stroke is the whole rectangle regardless of what the tint subtracts — the editor
    // manipulates the real box, and a clipped outline would make it un-grabbable.
    const viewsStroke = ctx._strokeRects.find((r) => r.w > 700 && r.h > 500);
    expect(viewsStroke).toBeDefined();
  });

  it("does not clip any zone other than views", () => {
    const ctx = makeCtx();
    // A notes box overlapping a title box: neither may punch a hole in the other.
    renderFromDetected(
      ctx,
      viewsWith(zone(0, 0, 1, 1), {
        notes: zone(50, 400, 250, 550),
        title: zone(100, 420, 300, 500),
      }),
    );

    // views is degenerate-but-present; only its own clip pair may appear, never one per
    // sibling for notes or title.
    const holeClips = ctx._clips.filter((c) => c !== null);
    expect(holeClips.length).toBeLessThanOrEqual(2);
    expect(ctx._fillRects.length).toBeGreaterThanOrEqual(2);
  });

  it("ignores a sibling whose box collapses to zero area", () => {
    const ctx = makeCtx();
    renderFromDetected(
      ctx,
      viewsWith(zone(0, 0, 840, 594), { notes: zone(100, 100, 100, 100) }),
    );

    // A zero-area hole would clip everything away on some engines; it is skipped instead.
    expect(ctx._clips.filter((c) => c !== null)).toHaveLength(0);
  });
});
