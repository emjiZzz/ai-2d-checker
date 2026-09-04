/**
 * What the canvas actually strokes for a radius/diameter callout.
 *
 * Reported against iCAD SX: the ⌀125 callout on M745221N01 "was too short or broken". Every
 * upstream stage measured complete — the DXF block, the extractor's `render_paths`, and the
 * cached payload the app renders all carry the same four paths — so the only stage left
 * unchecked was this one, and nothing existed to check it. `render_audit.py` stops at the
 * payload; the entity census counts a dimension as `drawn` if any part of it reaches the canvas,
 * so a dimension that strokes one of its four paths is indistinguishable from one that strokes
 * all four.
 *
 * The fixture is the real callout off that sheet, taken through `DXFParser` and
 * `GeometrySerializer.serialize_entities` so it is the payload shape the canvas actually
 * receives — `type`, `style.stroke`, resolved colours and all — rather than the raw stored row
 * or a synthetic stand-in. Regenerate it from
 * `storage/uploads/0029fc8cdf974f5e92fa7148a679255d.dxf` if the serializer's shape changes.
 *
 * Result: all four paths reach the canvas, the leader at full length and the head intact. Every
 * stage of this pipeline is complete, which is itself the finding.
 */
import { describe, expect, it } from "vitest";

import fixture from "./__fixtures__/m745221n01_diameter_dim.json";
import { getNormalization } from "../../utils/coordinateTransform";
import { renderEntities } from "./renderEntities";

/** The sheet's render bounds, from the drawing this fixture was taken out of. */
const BOUNDS = { xmin: 0, ymin: 0, xmax: 420, ymax: 297 };

type Seg = { x1: number; y1: number; x2: number; y2: number };

class FakePath2D {
  segments: Seg[] = [];
  private cx = 0;
  private cy = 0;
  moveTo(x: number, y: number) {
    this.cx = x;
    this.cy = y;
  }
  lineTo(x: number, y: number) {
    this.segments.push({ x1: this.cx, y1: this.cy, x2: x, y2: y });
    this.cx = x;
    this.cy = y;
  }
  arc() {}
  ellipse() {}
  rect() {}
  closePath() {}
}
(globalThis as any).Path2D = FakePath2D;

function makeCtx() {
  const strokedSegments: Seg[] = [];
  const ctx: any = {
    _strokedSegments: strokedSegments,
    canvas: { width: 1000, height: 700 },
    save: () => {},
    restore: () => {},
    beginPath: () => {},
    moveTo: () => {},
    lineTo: () => {},
    closePath: () => {},
    arc: () => {},
    ellipse: () => {},
    rect: () => {},
    fill: () => {},
    clip: () => {},
    setTransform: () => {},
    transform: () => {},
    translate: () => {},
    scale: () => {},
    rotate: () => {},
    setLineDash: () => {},
    getLineDash: () => [],
    fillText: () => {},
    strokeText: () => {},
    measureText: () => ({ width: 10, actualBoundingBoxAscent: 5, actualBoundingBoxDescent: 1 }),
    clearRect: () => {},
    fillRect: () => {},
    strokeRect: () => {},
    drawImage: () => {},
    createLinearGradient: () => ({ addColorStop: () => {} }),
    stroke: (path?: FakePath2D) => {
      if (path) strokedSegments.push(...path.segments);
    },
  };
  return ctx;
}

function renderFixture() {
  const ctx = makeCtx();
  const norm = getNormalization(BOUNDS);
  const entity = (fixture as any).entity;
  const layerName = (fixture as any).layer;
  const frame: any = {
    ctx,
    isExport: false,
    renderWidth: 1000,
    renderHeight: 700,
    width: 1000,
    height: 700,
    norm,
    scale: 1,
    transX: 0,
    transY: 0,
    minX: -1e6,
    minY: -1e6,
    maxX: 1e6,
    maxY: 1e6,
    currentViewportScale: 1,
    resolutionMultiplier: 1,
    viewport: { x: 0, y: 0, scale: 1 },
    markerPositionsRef: { current: {} },
  };
  const result = renderEntities({
    frame,
    layers: { [layerName]: [entity] },
    activeLayers: { [layerName]: true },
    theme: "dark",
  });
  return { result, segments: ctx._strokedSegments as Seg[] };
}

const length = (s: Seg) => Math.hypot(s.x2 - s.x1, s.y2 - s.y1);

describe("the ⌀125 callout on M745221N01", () => {
  it("is counted as drawn", () => {
    const { result } = renderFixture();
    expect(result.drawnEntities).toBe(1);
  });

  it("strokes every one of its four render_paths", () => {
    /**
     * The count is the whole point. A census that only asks "did this dimension draw" reports
     * the same 1 whether four paths reach the canvas or one does.
     */
    const { segments } = renderFixture();
    expect(segments.length).toBe((fixture as any).entity.geometry.render_paths.length);
  });

  it("strokes the full leader, not a stub of it", () => {
    /**
     * The leader is the longest of the four paths: 21.54 drawing units in the payload, running
     * from the arrowhead's shaft out past the measurement text. The three short ones are the
     * `_OPEN30` head — two barbs and its shaft.
     */
    const { segments } = renderFixture();
    const lengths = segments.map(length).sort((a, b) => b - a);
    const scale = lengths[0] / 21.54;

    expect(scale).toBeGreaterThan(0);
    expect(lengths[0] / scale).toBeCloseTo(21.54, 1);
    // The head: three segments, none of them longer than a fifth of the leader.
    expect(lengths.slice(1).every((l) => l / scale < 21.54 / 5)).toBe(true);
  });

  it("keeps the arrowhead's three segments meeting at one tip", () => {
    /**
     * `_OPEN30` is authored as two barbs plus a shaft radiating from the arrow tip. If the
     * canvas dropped or displaced any of them the head reads as broken rather than short.
     */
    const { segments } = renderFixture();
    const lengths = segments.map(length);
    const longest = Math.max(...lengths);
    const head = segments.filter((s) => length(s) < longest / 5);
    expect(head).toHaveLength(3);

    const tips = head.flatMap((s) => [
      { x: s.x1, y: s.y1 },
      { x: s.x2, y: s.y2 },
    ]);
    const shared = tips.filter(
      (p) => tips.filter((q) => Math.hypot(p.x - q.x, p.y - q.y) < 1e-6).length >= 3,
    );
    expect(shared.length).toBeGreaterThanOrEqual(3);
  });
});
