/**
 * Tests for the CAD<->fraction conversion (docs/zone-template-alignment-implementation-plan.md, A.5).
 *
 * The failure these exist to catch is a vertically mirrored set of boxes. It is not
 * self-evident on screen: most zones sit near the sheet's vertical centre, so a mirrored
 * box lands close to where a correct one would and reads as "slightly off" rather than
 * "inverted". An earlier revision of the plan document specified this conversion backwards,
 * which is precisely why it is pinned by an orientation assertion and not by inspection.
 */
import { describe, expect, it } from "vitest";

import {
  fractionsToScreenRect,
  fractionsToZoneBox,
  normalizeFractions,
  zoneBoxToFractions,
  zonesToTemplatePayload,
  type RenderBoundsTuple,
} from "./zoneFractions";

// The real bounds of M7452A0N01_reference.dxf, deliberately not a tidy 0..1000 box:
// a non-zero, negative origin is what exposes an offset that a 0-origin sheet hides.
const BOUNDS: RenderBoundsTuple = [-52.5, -37.125, 1102.5, 779.625];
const W = 1102.5 - -52.5; // 1155
const H = 779.625 - -37.125; // 816.75

describe("zoneBoxToFractions — orientation", () => {
  it("maps a CAD box near ymax (visual TOP) to a small yMin fraction", () => {
    // title_upper_left as actually detected: CAD y 696.3..714.8, near ymax 779.625.
    // It is visibly at the top-left of the sheet.
    const frac = zoneBoxToFractions(
      { xmin: 65.7, ymin: 696.3, xmax: 227.7, ymax: 714.8 },
      BOUNDS,
    )!;

    expect(frac.yMin).toBeLessThan(0.15);
    expect(frac.yMax).toBeLessThan(0.2);
  });

  it("maps a CAD box near ymin (visual BOTTOM) to a large yMax fraction", () => {
    const frac = zoneBoxToFractions(
      { xmin: 275.6, ymin: 69.2, xmax: 950.7, ymax: 388.5 },
      BOUNDS,
    )!;

    expect(frac.yMax).toBeGreaterThan(0.85);
  });

  it("puts a CAD-higher zone ABOVE a CAD-lower zone in fraction space", () => {
    const upper = zoneBoxToFractions({ xmin: 0, ymin: 700, xmax: 100, ymax: 760 }, BOUNDS)!;
    const lower = zoneBoxToFractions({ xmin: 0, ymin: 40, xmax: 100, ymax: 100 }, BOUNDS)!;

    expect(upper.yMin).toBeLessThan(lower.yMin);
  });

  it("keeps X as a plain ratio with no inversion", () => {
    const frac = zoneBoxToFractions(
      { xmin: -52.5, ymin: 0, xmax: 1102.5, ymax: 100 },
      BOUNDS,
    )!;

    expect(frac.xMin).toBeCloseTo(0, 6);
    expect(frac.xMax).toBeCloseTo(1, 6);
  });

  it("produces yMin < yMax (never an inverted box)", () => {
    const frac = zoneBoxToFractions(
      { xmin: 10, ymin: 100, xmax: 200, ymax: 700 },
      BOUNDS,
    )!;

    expect(frac.yMin).toBeLessThan(frac.yMax);
  });
});

describe("zoneBoxToFractions — degenerate input", () => {
  it("returns null for a zero-area sheet instead of NaN fractions", () => {
    // NaN would serialize into a saved template and quietly corrupt it.
    expect(zoneBoxToFractions({ xmin: 0, ymin: 0, xmax: 1, ymax: 1 }, [0, 0, 0, 0])).toBeNull();
  });
});

describe("round-trip", () => {
  it("CAD -> fractions -> CAD returns the original", () => {
    const original = { xmin: 275.6, ymin: 69.2, xmax: 950.7, ymax: 388.5 };
    const back = fractionsToZoneBox(zoneBoxToFractions(original, BOUNDS)!, BOUNDS);

    expect(back.xmin).toBeCloseTo(original.xmin, 6);
    expect(back.ymin).toBeCloseTo(original.ymin, 6);
    expect(back.xmax).toBeCloseTo(original.xmax, 6);
    expect(back.ymax).toBeCloseTo(original.ymax, 6);
  });

  it("survives a full-sheet box", () => {
    const original = { xmin: -52.5, ymin: -37.125, xmax: 1102.5, ymax: 779.625 };
    const frac = zoneBoxToFractions(original, BOUNDS)!;

    expect(frac).toMatchObject({ xMin: 0, yMin: 0 });
    expect(frac.xMax).toBeCloseTo(1, 6);
    expect(frac.yMax).toBeCloseTo(1, 6);

    const back = fractionsToZoneBox(frac, BOUNDS);
    expect(back.ymin).toBeCloseTo(original.ymin, 6);
    expect(back.ymax).toBeCloseTo(original.ymax, 6);
  });

  it("transfers between two sheets of the same aspect ratio at different scale", () => {
    // This is the property the whole per-template approach rests on: the reference sheet
    // is 1155x817 and the revision 462x327 -- 2.5x apart, identical 1.4141 aspect.
    const REV: RenderBoundsTuple = [-21, -14.85, 441, 311.85];
    const frac = zoneBoxToFractions(
      { xmin: 275.6, ymin: 69.2, xmax: 950.7, ymax: 388.5 },
      BOUNDS,
    )!;

    const onRev = fractionsToZoneBox(frac, REV);
    const revW = 441 - -21;
    const revH = 311.85 - -14.85;

    // Same proportional position and size on the smaller sheet.
    expect((onRev.xmax - onRev.xmin) / revW).toBeCloseTo(frac.xMax - frac.xMin, 6);
    expect((onRev.ymax - onRev.ymin) / revH).toBeCloseTo(frac.yMax - frac.yMin, 6);
  });
});

describe("fractionsToScreenRect", () => {
  const norm = { xmin: -52.5, ymin: -37.125, normScale: 1000 / W };
  const viewport = { x: 0, y: 0, scale: 1 };

  it("matches the hit-test mapping in useCanvasInteraction (no Y inversion)", () => {
    const frac = { xMin: 0.25, xMax: 0.75, yMin: 0.1, yMax: 0.4 };
    const rect = fractionsToScreenRect(frac, BOUNDS, norm, viewport);

    // Recomputed here with the hit-test's own expression, independently of the helper.
    const effectiveScale = viewport.scale * norm.normScale;
    expect(rect.left).toBeCloseTo(
      (-52.5 + W * 0.25 - norm.xmin) * effectiveScale + viewport.x,
      6,
    );
    expect(rect.top).toBeCloseTo(
      (-37.125 + H * 0.1 - norm.ymin) * effectiveScale + viewport.y,
      6,
    );
  });

  it("puts a small yMin near the top of the screen", () => {
    const rect = fractionsToScreenRect(
      { xMin: 0, xMax: 1, yMin: 0, yMax: 0.1 },
      BOUNDS,
      norm,
      viewport,
    );

    expect(rect.top).toBeCloseTo(viewport.y, 6);
    expect(rect.bottom).toBeGreaterThan(rect.top);
  });
});

describe("normalizeFractions", () => {
  it("clamps outside the unit square", () => {
    expect(normalizeFractions({ xMin: -0.4, xMax: 1.7, yMin: -2, yMax: 3 })).toEqual({
      xMin: 0,
      xMax: 1,
      yMin: 0,
      yMax: 1,
    });
  });

  it("repairs an inverted box produced by dragging a handle past its opposite edge", () => {
    expect(normalizeFractions({ xMin: 0.8, xMax: 0.2, yMin: 0.9, yMax: 0.3 })).toEqual({
      xMin: 0.2,
      xMax: 0.8,
      yMin: 0.3,
      yMax: 0.9,
    });
  });

  it("leaves a valid box untouched", () => {
    const ok = { xMin: 0.1, xMax: 0.9, yMin: 0.2, yMax: 0.8 };
    expect(normalizeFractions(ok)).toEqual(ok);
  });
});

describe("zonesToTemplatePayload — a reshaped zone must survive being saved", () => {
  const RESHAPED = {
    xMin: 0.1, xMax: 0.5, yMin: 0.1, yMax: 0.5,
    points: [
      { x: 0.1, y: 0.1 },
      { x: 0.5, y: 0.1 },
      { x: 0.5, y: 0.3 },
      { x: 0.3, y: 0.3 },
      { x: 0.3, y: 0.5 },
      { x: 0.1, y: 0.5 },
    ],
  };

  it("carries the outline through instead of flattening it to a bounding box", () => {
    const payload = zonesToTemplatePayload({ views: RESHAPED });
    expect(payload.views.points).toHaveLength(6);
    expect(payload.views.points).toEqual(RESHAPED.points);
  });

  it("keeps a plain rectangle a rectangle", () => {
    const payload = zonesToTemplatePayload({
      title: { xMin: 0.2, xMax: 0.8, yMin: 0.2, yMax: 0.8 },
    });
    expect(payload.title.points).toBeUndefined();
  });

  it("clamps outline vertices the same way it clamps the scalars", () => {
    const payload = zonesToTemplatePayload({
      views: {
        xMin: -3, xMax: 9, yMin: -1, yMax: 4,
        points: [{ x: -2, y: 0.5 }, { x: 0.5, y: 7 }, { x: 0.5, y: 0.5 }],
      },
    });
    expect(payload.views.xMin).toBe(0);
    expect(payload.views.xMax).toBe(1);
    expect(payload.views.points).toEqual([
      { x: 0, y: 0.5 }, { x: 0.5, y: 1 }, { x: 0.5, y: 0.5 },
    ]);
  });

  it("drops an outline with too few vertices — it would contain nothing", () => {
    const payload = zonesToTemplatePayload({
      views: { xMin: 0.1, xMax: 0.5, yMin: 0.1, yMax: 0.5, points: [{ x: 0.1, y: 0.1 }] },
    });
    expect(payload.views.points).toBeUndefined();
  });

  it("skips null and undefined zones rather than emitting empty entries", () => {
    const payload = zonesToTemplatePayload({ views: null, notes: undefined });
    expect(Object.keys(payload)).toHaveLength(0);
  });
});
