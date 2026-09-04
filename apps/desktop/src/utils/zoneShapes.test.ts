/**
 * Reshaped zones — a zone box becomes a polygon when a node is inserted on one of its edges.
 *
 * The mirroring failure `zoneFractions.test.ts` exists to catch gets a second chance here,
 * because a VERTEX conversion is not the box conversion. The box swaps min and max as it flips
 * Y — the names are about magnitude, and reversing the axis reverses which edge earns which
 * name. A vertex is the flip alone. Copying the box rule onto points yields an outline that is
 * still closed, still the right size, still inside the right bounding box, and vertically
 * mirrored: it excludes the opposite half of the zone and nothing errors.
 *
 * Mirrored by tests/test_zone_polygons.py — the backend decides the same containment question
 * about the same outline, and if the two disagree the canvas shows a region the audit is not
 * using.
 */
import { describe, expect, it } from "vitest";

import {
  MIN_ZONE_POINTS,
  cadPointToFraction,
  fractionPointToCad,
  fractionsToZoneBox,
  insertPointOnEdge,
  isPolygonZone,
  movePointTo,
  normalizeFractions,
  pointInShape,
  pointsToBounds,
  removePointAt,
  shapePoints,
  translateShape,
  type RegionFractions,
  type RenderBoundsTuple,
} from "./zoneFractions";

// The real bounds of M7452A0N01_reference.dxf. A non-zero, negative origin is what exposes an
// offset that a tidy 0-origin sheet hides.
const BOUNDS: RenderBoundsTuple = [-52.5, -37.125, 1102.5, 779.625];

const rect = (xMin: number, yMin: number, xMax: number, yMax: number): RegionFractions => ({
  xMin,
  xMax,
  yMin,
  yMax,
});

describe("shapePoints", () => {
  it("gives a rectangle's corners clockwise from top-left", () => {
    // Order is load-bearing: edge i runs from corner i to corner i+1, so "insert a node on the
    // top edge" means the same thing before and after the zone stops being a rectangle.
    expect(shapePoints(rect(0.1, 0.2, 0.7, 0.8))).toEqual([
      { x: 0.1, y: 0.2 },
      { x: 0.7, y: 0.2 },
      { x: 0.7, y: 0.8 },
      { x: 0.1, y: 0.8 },
    ]);
  });

  it("returns the outline itself once the zone has one", () => {
    const points = [
      { x: 0, y: 0 },
      { x: 1, y: 0 },
      { x: 1, y: 1 },
    ];
    expect(shapePoints({ ...rect(0, 0, 1, 1), points })).toBe(points);
  });

  it("ignores an outline too short to enclose an area", () => {
    const degenerate = {
      ...rect(0, 0, 1, 1),
      points: [
        { x: 0, y: 0 },
        { x: 1, y: 1 },
      ],
    };
    expect(isPolygonZone(degenerate)).toBe(false);
    expect(shapePoints(degenerate)).toHaveLength(4);
  });
});

describe("vertex conversion — the flip WITHOUT the min/max swap", () => {
  it("maps fraction y=0 (sheet top) to CAD ymax", () => {
    expect(fractionPointToCad({ x: 0, y: 0 }, BOUNDS)).toEqual({ x: -52.5, y: 779.625 });
  });

  it("maps fraction y=1 (sheet bottom) to CAD ymin", () => {
    const p = fractionPointToCad({ x: 1, y: 1 }, BOUNDS);
    expect(p.x).toBeCloseTo(1102.5, 6);
    expect(p.y).toBeCloseTo(-37.125, 6);
  });

  it("puts a top-edge vertex ABOVE a bottom-edge vertex in CAD", () => {
    // The single assertion that catches a mirrored outline outright.
    const top = fractionPointToCad({ x: 0.5, y: 0.05 }, BOUNDS);
    const bottom = fractionPointToCad({ x: 0.5, y: 0.95 }, BOUNDS);
    expect(top.y).toBeGreaterThan(bottom.y);
  });

  it("round-trips a vertex through CAD and back", () => {
    const original = { x: 0.31, y: 0.72 };
    const back = cadPointToFraction(fractionPointToCad(original, BOUNDS), BOUNDS)!;
    expect(back.x).toBeCloseTo(original.x, 9);
    expect(back.y).toBeCloseTo(original.y, 9);
  });

  it("agrees with the BOX conversion on a rectangle's corners", () => {
    // The two describe the same rectangle. If they disagree, the outline the engine gates on
    // and the box everything else uses are different shapes.
    const frac = rect(0.2, 0.1, 0.8, 0.6);
    const box = fractionsToZoneBox(frac, BOUNDS);
    const corners = shapePoints(frac).map((p) => fractionPointToCad(p, BOUNDS));
    expect(Math.min(...corners.map((c) => c.x))).toBeCloseTo(box.xmin, 6);
    expect(Math.max(...corners.map((c) => c.x))).toBeCloseTo(box.xmax, 6);
    expect(Math.min(...corners.map((c) => c.y))).toBeCloseTo(box.ymin, 6);
    expect(Math.max(...corners.map((c) => c.y))).toBeCloseTo(box.ymax, 6);
  });

  it("returns null for a degenerate sheet instead of emitting NaN", () => {
    expect(cadPointToFraction({ x: 1, y: 1 }, [0, 0, 0, 0])).toBeNull();
  });
});

describe("node insertion", () => {
  it("adds a midpoint on the requested edge and makes the zone a polygon", () => {
    const reshaped = insertPointOnEdge(rect(0, 0, 1, 1), 0); // edge 0 = top
    expect(isPolygonZone(reshaped)).toBe(true);
    expect(reshaped.points).toHaveLength(5);
    expect(reshaped.points![1]).toEqual({ x: 0.5, y: 0 });
  });

  it("inserts BETWEEN its edge's two corners, not at the end", () => {
    const reshaped = insertPointOnEdge(rect(0, 0, 1, 1), 2); // edge 2 = bottom
    expect(reshaped.points![3]).toEqual({ x: 0.5, y: 1 });
  });

  it("wraps the last edge back to the first corner", () => {
    const reshaped = insertPointOnEdge(rect(0, 0, 1, 1), 3); // edge 3 = left
    expect(reshaped.points).toHaveLength(5);
    expect(reshaped.points![4]).toEqual({ x: 0, y: 0.5 });
  });

  it("does not move the bounding box when adding a node on a straight edge", () => {
    const before = rect(0.2, 0.3, 0.8, 0.9);
    const after = insertPointOnEdge(before, 1);
    expect(after.xMin).toBeCloseTo(before.xMin, 9);
    expect(after.xMax).toBeCloseTo(before.xMax, 9);
    expect(after.yMin).toBeCloseTo(before.yMin, 9);
    expect(after.yMax).toBeCloseTo(before.yMax, 9);
  });
});

describe("node removal", () => {
  it("removes the requested vertex", () => {
    const five = insertPointOnEdge(rect(0, 0, 1, 1), 0);
    expect(removePointAt(five, 1).points).toHaveLength(4);
  });

  it("refuses to go below an enclosing shape", () => {
    // A 2-point "zone" contains nothing at all — it would empty the zone silently.
    const triangle = normalizeFractions({
      ...rect(0, 0, 1, 1),
      points: [
        { x: 0, y: 0 },
        { x: 1, y: 0 },
        { x: 0.5, y: 1 },
      ],
    });
    expect(shapePoints(triangle)).toHaveLength(MIN_ZONE_POINTS);
    expect(removePointAt(triangle, 0)).toBe(triangle);
  });
});

describe("normalizeFractions with an outline", () => {
  it("DERIVES the bounding box from the points rather than trusting the scalars", () => {
    // The stale scalars claim the whole sheet; the outline covers a corner. Every
    // non-shape-aware consumer reads the scalars, so a disagreement would leave the overlay,
    // the exclusion logic and the audit each using a different rectangle.
    const out = normalizeFractions({
      xMin: 0,
      xMax: 1,
      yMin: 0,
      yMax: 1,
      points: [
        { x: 0.2, y: 0.3 },
        { x: 0.6, y: 0.3 },
        { x: 0.6, y: 0.7 },
      ],
    });
    expect(out).toMatchObject({ xMin: 0.2, xMax: 0.6, yMin: 0.3, yMax: 0.7 });
  });

  it("clamps outline vertices to the unit square", () => {
    const out = normalizeFractions({
      xMin: 0,
      xMax: 1,
      yMin: 0,
      yMax: 1,
      points: [
        { x: -1, y: -1 },
        { x: 2, y: 0.5 },
        { x: 0.5, y: 3 },
      ],
    });
    expect(out.points).toEqual([
      { x: 0, y: 0 },
      { x: 1, y: 0.5 },
      { x: 0.5, y: 1 },
    ]);
  });

  it("drops an outline too short to enclose an area, keeping the rectangle", () => {
    const out = normalizeFractions({
      ...rect(0.1, 0.2, 0.7, 0.8),
      points: [
        { x: 0, y: 0 },
        { x: 1, y: 1 },
      ],
    });
    expect(out.points).toBeUndefined();
    expect(out).toEqual(rect(0.1, 0.2, 0.7, 0.8));
  });
});

describe("pointInShape", () => {
  // An L: full square with the TOP-RIGHT quadrant cut out.
  const L: RegionFractions = normalizeFractions({
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

  it("keeps a point inside the L", () => {
    expect(pointInShape(L, 0.25, 0.25)).toBe(true);
  });

  it("rejects a point in the notch that the bounding box would keep", () => {
    expect(pointInShape(L, 0.8, 0.2)).toBe(false);
    // ...and the bounding box really does contain it, which is the entire point.
    expect(L.xMin <= 0.8 && 0.8 <= L.xMax && L.yMin <= 0.2 && 0.2 <= L.yMax).toBe(true);
  });

  it("uses plain bounds for an un-reshaped zone", () => {
    expect(pointInShape(rect(0, 0, 0.5, 0.5), 0.25, 0.25)).toBe(true);
    expect(pointInShape(rect(0, 0, 0.5, 0.5), 0.75, 0.25)).toBe(false);
  });
});

describe("translateShape", () => {
  it("moves every vertex of a polygon", () => {
    const L = normalizeFractions({
      xMin: 0,
      xMax: 1,
      yMin: 0,
      yMax: 1,
      points: [
        { x: 0, y: 0 },
        { x: 0.4, y: 0 },
        { x: 0.4, y: 0.4 },
      ],
    });
    // Float-tolerant: 0.4 + 0.2 is 0.6000000000000001 in IEEE754, which is the right answer.
    const moved = translateShape(L, 0.1, 0.2).points!;
    const expected = [
      { x: 0.1, y: 0.2 },
      { x: 0.5, y: 0.2 },
      { x: 0.5, y: 0.6 },
    ];
    expect(moved).toHaveLength(expected.length);
    moved.forEach((p, i) => {
      expect(p.x).toBeCloseTo(expected[i].x, 9);
      expect(p.y).toBeCloseTo(expected[i].y, 9);
    });
  });

  it("moves a rectangle by its edges, unchanged from before", () => {
    const moved = translateShape(rect(0.1, 0.1, 0.3, 0.3), 0.2, 0.1);
    expect(moved.xMin).toBeCloseTo(0.3, 9);
    expect(moved.xMax).toBeCloseTo(0.5, 9);
    expect(moved.yMin).toBeCloseTo(0.2, 9);
    expect(moved.yMax).toBeCloseTo(0.4, 9);
    expect(moved.points).toBeUndefined();
  });
});

describe("movePointTo", () => {
  it("moves one vertex and re-derives the bounds", () => {
    const five = insertPointOnEdge(rect(0.2, 0.2, 0.8, 0.8), 0);
    const moved = movePointTo(five, 1, { x: 0.5, y: 0.05 });
    expect(moved.points![1]).toEqual({ x: 0.5, y: 0.05 });
    expect(moved.yMin).toBeCloseTo(0.05, 9);
  });
});

describe("pointsToBounds", () => {
  it("is the axis-aligned hull of the vertices", () => {
    expect(
      pointsToBounds([
        { x: 0.3, y: 0.9 },
        { x: 0.1, y: 0.4 },
        { x: 0.7, y: 0.6 },
      ]),
    ).toEqual({ xMin: 0.1, xMax: 0.7, yMin: 0.4, yMax: 0.9 });
  });
});
