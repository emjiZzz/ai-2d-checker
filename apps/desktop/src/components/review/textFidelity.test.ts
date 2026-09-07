/**
 * Tests for CAD text placement and stroke styling in `renderEntities`.
 *
 * Every case here pins a defect that produced a plausible-looking canvas rather than an error,
 * so none of them would be caught by tsc, by the existing suites, or by glancing at a
 * screenshot. All were measured against the backend's ezdxf raster by `tools/render_audit.py`
 * on M745221N01; the counts quoted are from that sheet.
 *
 *   - text anchored bottom-left regardless of `attachment_point` (106 of 228 strings displaced,
 *     worst case a full string width)
 *   - `font: {height}px` treating the DXF CAP height as an EM size (every string ~24% small)
 *   - `width_factor` extracted and never applied (248 of 249 strings 10-40% too wide)
 *   - `tracking` applied as though it were a width factor (the opposite error, found only by
 *     measuring: ezdxf does not apply it)
 *   - dimension text rebuilt from `actual_measurement`, dropping the ⌀ prefix that only exists
 *     in the rendered block (3 of 4 dimensions)
 *   - lineweight read as CSS pixels instead of millimetres, collapsing three real weights into
 *     one hairline
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { getNormalization } from '../../utils/coordinateTransform';

// `renderEntities` no longer reads the store at all — the raster/vector switch it used to
// consult is gone (ADR-011). The module mock stays only to keep this suite from pulling the
// real store in transitively.
const mockReviewState = {};
vi.mock('../../stores/reviewStore', () => {
  const mockFn: any = vi.fn(() => mockReviewState);
  mockFn.getState = () => mockReviewState;
  mockFn.subscribe = vi.fn(() => () => {});
  return { useReviewStore: mockFn };
});

class FakePath2D {
  moveTo() {}
  lineTo() {}
  arc() {}
  rect() {}
  closePath() {}
}
(globalThis as any).Path2D = FakePath2D;

const { renderEntities, mergeAdjacentDatePrefixes } = await import('./renderEntities');

interface FillTextCall {
  text: string;
  x: number;
  y: number;
  font: string;
  align: string;
  baseline: string;
}

/**
 * Minimal 2D-context stand-in.
 *
 * `measureText` returns no `actualBoundingBoxAscent`, exactly as jsdom's absent canvas does, so
 * `getCapHeightRatio` falls back to its documented MS Gothic constant. That makes the font-size
 * assertions deterministic instead of dependent on whatever font the test machine resolves.
 */
function makeCtx() {
  const fillTexts: FillTextCall[] = [];
  const scales: { x: number; y: number }[] = [];
  const rotations: number[] = [];
  const translates: { x: number; y: number }[] = [];
  const lineWidths: number[] = [];
  const lineDashes: number[][] = [];

  const ctx: any = {
    font: '10px sans-serif',
    textAlign: 'left',
    textBaseline: 'alphabetic',
    fillStyle: '#000',
    strokeStyle: '#000',
    lineWidth: 1,
    imageSmoothingEnabled: false,
    imageSmoothingQuality: 'low',
    save() {},
    restore() {},
    setTransform() {},
    beginPath() {},
    translate(x: number, y: number) { translates.push({ x, y }); },
    rotate(r: number) { rotations.push(r); },
    scale(x: number, y: number) { scales.push({ x, y }); },
    measureText(text: string) { return { width: text.length * 4 }; },
    fillText(text: string, x: number, y: number) {
      fillTexts.push({ text, x, y, font: ctx.font, align: ctx.textAlign, baseline: ctx.textBaseline });
    },
    stroke() { lineWidths.push(ctx.lineWidth); },
    fill() {},
    setLineDash(d: number[]) { if (d.length) lineDashes.push([...d]); },
    drawImage() {},
  };

  return { ctx, fillTexts, scales, rotations, translates, lineWidths, lineDashes };
}

const SCALE = 2;

function makeFrame(ctx: any) {
  return {
    ctx,
    isExport: false,
    renderWidth: 1000,
    renderHeight: 1000,
    width: 1000,
    height: 1000,
    norm: getNormalization({ xmin: 0, ymin: 0, xmax: 1000, ymax: 1000 }),
    scale: SCALE,
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
  } as any;
}

function textEntity(properties: Record<string, unknown>) {
  return {
    id: 't1',
    type: 'text',
    geometry: { insert: [100, 500, 0] },
    style: { stroke: '#ffffff' },
    properties: { text: 'SAMPLE', height: 10, is_multiline: true, ...properties },
  };
}

/** A drawing whose `$LWDISPLAY` is on, so lineweights are actually drawn. */
const LW_ON = { metadata: { lineweight_display: true } };

function run(entities: any[], ctx: any, drawing?: any) {
  renderEntities({
    frame: makeFrame(ctx),
    layers: { '0': entities },
    activeLayers: {},
    theme: 'hc-dark',
    drawing,
  });
}

/** MS Gothic cap height / em, the fallback `getCapHeightRatio` uses when it cannot measure. */
const CAP_RATIO = 0.7617;

describe('CAD text anchoring', () => {
  beforeEach(() => vi.clearAllMocks());

  // height 10 at scale 2 => 20 CSS px of cap height.
  const CAP_PX = 10 * SCALE;

  it.each([
    [7, 'left', 0],
    [8, 'center', 0],
    [9, 'right', 0],
    [4, 'left', CAP_PX / 2],
    [5, 'center', CAP_PX / 2],
    [2, 'center', CAP_PX],
  ])('attachment point %i anchors %s with baseline offset %f', (ap, align, offset) => {
    const { ctx, fillTexts } = makeCtx();
    run([textEntity({ attachment_point: ap })], ctx);

    expect(fillTexts).toHaveLength(1);
    expect(fillTexts[0].align).toBe(align);
    expect(fillTexts[0].y).toBeCloseTo(offset, 6);
  });

  it('never uses a font-metric textBaseline', () => {
    // `textBaseline: 'bottom'` aligns the EM BOX bottom; a DXF bottom attachment aligns the
    // BASELINE. The gap is the descender — 0.18 of the cap height in MS Gothic — which drew
    // 215 of 247 strings that much too high and pushed title-block text into the rule above.
    // The vertical anchor is applied from the DXF cap height instead, so the browser's
    // ascent/descent metrics cannot reintroduce the offset.
    const { ctx, fillTexts } = makeCtx();
    run([textEntity({ attachment_point: 8 })], ctx);

    expect(fillTexts[0].baseline).toBe('alphabetic');
    expect(fillTexts[0].y).toBe(0);
  });

  it('stacks a wrapped block upward from a bottom anchor', () => {
    // Bottom-anchored means the LAST line sits on the anchor, so earlier lines are negative.
    const { ctx, fillTexts } = makeCtx();
    run([textEntity({ text: 'ABCDEFGH', attachment_point: 7, column_width: 12 / SCALE })], ctx);

    expect(fillTexts.length).toBeGreaterThan(1);
    expect(fillTexts[fillTexts.length - 1].y).toBeCloseTo(0, 6);
    expect(fillTexts[0].y).toBeLessThan(0);
  });

  it('leaves a plain TEXT entity bottom-left, since its align_point is not extracted', () => {
    const { ctx, fillTexts } = makeCtx();
    // halign/valign are present but must be ignored: honouring them against `insert` rather
    // than the DXF `align_point` would move the string somewhere new and wrong.
    run([textEntity({ is_multiline: false, attachment_point: 9, halign: 2, valign: 3 })], ctx);

    expect(fillTexts[0].align).toBe('left');
    expect(fillTexts[0].y).toBe(0);
  });
});

describe('CAD text metrics', () => {
  beforeEach(() => vi.clearAllMocks());

  it('scales the font so the DXF cap height lands on the cap height, not the em', () => {
    const { ctx, fillTexts } = makeCtx();
    run([textEntity({ height: 10 })], ctx);

    // height 10 at scale 2 is 20 CSS px of CAP height, so the em must be larger than that.
    const match = fillTexts[0].font.match(/([\d.]+)px/);
    const emPx = match ? parseFloat(match[1]) : parseFloat(fillTexts[0].font);
    expect(emPx).toBeCloseTo((10 * SCALE * 0.80) / CAP_RATIO, 3);
    expect(emPx).toBeGreaterThan(10 * SCALE * 0.80);
  });

  it('applies width_factor as a horizontal scale', () => {
    const { ctx, scales } = makeCtx();
    run([textEntity({ width_factor: 0.6 })], ctx);

    expect(scales).toContainEqual({ x: 0.6, y: 1 });
  });

  it('does NOT fold tracking into the horizontal scale', () => {
    // Measured: ezdxf applies \W and ignores \T. Folding tracking in made every string too
    // narrow by exactly the tracking factor across all 81 strings that carry one.
    const { ctx, scales } = makeCtx();
    run([textEntity({ width_factor: 0.8, tracking: 0.5 })], ctx);

    expect(scales).toContainEqual({ x: 0.8, y: 1 });
    expect(scales).not.toContainEqual({ x: 0.4, y: 1 });
  });

  it('rotates by the negated DXF angle, since screen Y is already flipped', () => {
    const { ctx, rotations } = makeCtx();
    run([textEntity({ rotation: 90 })], ctx);

    expect(rotations[0]).toBeCloseTo(-Math.PI / 2, 6);
  });

  it('wraps to the MTEXT column width instead of running one long line', () => {
    const { ctx, fillTexts } = makeCtx();
    // measureText is 4px/char, so 'ABCDEFGH' is 32px; a 12px column is far past the tolerance.
    run([textEntity({ text: 'ABCDEFGH', column_width: 12 / SCALE })], ctx);

    expect(fillTexts.length).toBeGreaterThan(1);
    expect(fillTexts.map((f) => f.text).join('')).toBe('ABCDEFGH');
  });

  it('does not wrap a string that only just exceeds its column', () => {
    // 99 of 247 strings on M745221N01 sit within 6% of their column width -- that is our
    // measurement running ~3% wider than ezdxf's, not a requested line break.
    const { ctx, fillTexts } = makeCtx();
    // 6 chars = 24px against a 23px column: 4% over, inside the tolerance.
    run([textEntity({ text: 'ABCDEF', column_width: 23 / SCALE })], ctx);

    expect(fillTexts).toHaveLength(1);
    expect(fillTexts[0].text).toBe('ABCDEF');
  });

  it('never orphans a single trailing character onto its own line', () => {
    // The reported damage: a lone closing parenthesis dropped below its line in
    // '４ロール：２４（４×６台）'. An overlong line beats a broken-looking one.
    const { ctx, fillTexts } = makeCtx();
    // 7 chars = 28px; a 24px column would break exactly one character off the end.
    run([textEntity({ text: 'ABCDEF)', column_width: 24 / SCALE })], ctx);

    expect(fillTexts).toHaveLength(1);
    expect(fillTexts[0].text).toBe('ABCDEF)');
  });

  it('distributes characters across cell width when column_width exceeds natural width (title block alignment)', () => {
    const { ctx, fillTexts } = makeCtx();
    // 5 chars = 20px natural width (at 4px/char). column_width = 30px (scaled 30 / SCALE).
    // ratio = 1.5, in the distribution range [1.05 .. 2.8].
    run([textEntity({ text: 'FSRS2', column_width: 30 / SCALE, attachment_point: 4 })], ctx);

    // Instead of one clustered string, characters are distributed individually across the cell width.
    expect(fillTexts).toHaveLength(5);
    expect(fillTexts.map((f) => f.text).join('')).toBe('FSRS2');
    expect(fillTexts[0].x).toBe(0);
    expect(fillTexts[4].x + 4).toBeCloseTo(30 * 0.915, 1);
  });

  it('does not distribute short 2-character tokens like "20" across column_width', () => {
    const { ctx, fillTexts } = makeCtx();
    // 2 chars = 8px natural width. column_width = 15px.
    // Short 2-character tokens like century '20' must stay together and not be stretched with a huge gap.
    run([textEntity({ text: '20', column_width: 15 / SCALE, attachment_point: 7 })], ctx);

    expect(fillTexts).toHaveLength(1);
    expect(fillTexts[0].text).toBe('20');
  });

  it('merges adjacent date prefix "20" and "04/12/22" into unified "2004/12/22"', () => {
    const entPrefix = {
      id: 'e_prefix',
      type: 'text',
      geometry: { insert: [404.72, 51.12, 0.0] },
      properties: {
        text: '20',
        render_text: '20',
        column_width: 8.5,
        bbox: [[404.72, 51.12], [413.22, 57.83]],
      },
    };
    const entDate = {
      id: 'e_date',
      type: 'text',
      geometry: { insert: [413.03, 51.15, 0.0] },
      properties: {
        text: '04/12/22',
        render_text: '04/12/22',
        column_width: 34.85,
        bbox: [[413.03, 51.15], [447.88, 57.86]],
      },
    };

    const merged = mergeAdjacentDatePrefixes([entPrefix, entDate]);
    expect(merged).toHaveLength(1);
    expect(merged[0].properties.text).toBe('2004/12/22');
    expect(merged[0].properties.render_text).toBe('2004/12/22');
    expect(merged[0].geometry.insert[0]).toBe(404.72);
    expect(merged[0].properties.column_width).toBeCloseTo(43.35, 2);
    expect(merged[0].properties.bbox[0][0]).toBe(404.72);
    expect(merged[0].properties.bbox[1][0]).toBe(447.88);
  });
});

describe('dimension measurement text', () => {
  beforeEach(() => vi.clearAllMocks());

  const dimension = (properties: Record<string, unknown>) => ({
    id: 'd1',
    type: 'dimension',
    geometry: { text_point: [100, 500, 0], render_paths: [[[0, 0], [10, 0]]] },
    style: { stroke: '#00ff00', textStroke: '#ffff00' },
    properties: { text_height: 10, ...properties },
  });

  it('prefers render_text so the block ⌀ prefix survives', () => {
    const { ctx, fillTexts } = makeCtx();
    run([dimension({ text: '145', render_text: '%%c145' })], ctx);

    expect(fillTexts[0].text).toBe('⌀145');
  });

  it('falls back to the reconstructed measurement when there is no render_text', () => {
    const { ctx, fillTexts } = makeCtx();
    run([dimension({ text: '145' })], ctx);

    expect(fillTexts[0].text).toBe('145');
  });

  it('never paints an unresolved <> placeholder', () => {
    const { ctx, fillTexts } = makeCtx();
    run([dimension({ text: '<>', render_text: '\\W0.8;<>' })], ctx);

    expect(fillTexts).toHaveLength(0);
  });
});

describe('stroke styling', () => {
  beforeEach(() => vi.clearAllMocks());

  const line = (style: Record<string, unknown>) => ({
    id: 'l1',
    type: 'line',
    geometry: { start: [0, 0, 0], end: [100, 100, 0] },
    style,
    properties: {},
  });

  it('draws a 1.00mm line thicker than a 0.25mm one when $LWDISPLAY is on', () => {
    // The whole point: these used to floor to the same hairline, so the sheet border and the
    // dimension lines were indistinguishable.
    const { ctx, lineWidths } = makeCtx();
    run([line({ stroke: '#fff', strokeWidth: 1.0 }), line({ stroke: '#eee', strokeWidth: 0.25 })], ctx, LW_ON);

    expect(lineWidths).toHaveLength(2);
    const [thick, thin] = lineWidths;
    expect(thick).toBeGreaterThan(thin);
    // 1.00mm at 96dpi is ~3.78 CSS px; 0.25mm is under one device pixel and floors there.
    expect(thick / thin).toBeGreaterThan(2);
  });

  it.each([
    ['the flag is off', { metadata: { lineweight_display: false } }],
    ['the drawing predates the flag', { metadata: {} }],
    ['there is no drawing at all', undefined],
  ])('draws every stroke as a hairline when %s', (_label, drawing) => {
    // $LWDISPLAY is 0 on both M745221N01 files, which is why iCAD shows them with uniform thin
    // linework despite the FSRS2 sheet recording 1.00mm on 136 entities. Honouring the recorded
    // weight regardless turned the whole template into slabs.
    const { ctx, lineWidths } = makeCtx();
    run([line({ stroke: '#fff', strokeWidth: 1.0 }), line({ stroke: '#eee', strokeWidth: 0.25 })], ctx, drawing);

    expect(lineWidths[0]).toBeCloseTo(lineWidths[1], 9);
  });

  it('keeps lineweight constant in screen space as the view scales', () => {
    // ctx.lineWidth is in world units under the view transform, so a screen-constant width has
    // to shrink as `scale` grows. Rendering at two scales must give the same screen thickness.
    const at = (viewScale: number) => {
      const c = makeCtx();
      renderEntities({
        frame: { ...makeFrame(c.ctx), scale: viewScale },
        layers: { '0': [line({ stroke: '#fff', strokeWidth: 1.0 })] },
        activeLayers: {}, theme: 'hc-dark', drawing: LW_ON,
      } as any);
      return c.lineWidths[0] * viewScale;
    };

    expect(at(2)).toBeCloseTo(at(8), 6);
  });

  it('passes a world-unit dash pattern through unscaled', () => {
    const { ctx, lineDashes } = makeCtx();
    run([line({ stroke: '#0ff', strokeWidth: 0.25, dash: [7.35, 1.47, 1.47, 1.47], dashUnits: 'world' })], ctx);

    expect(lineDashes[0]).toEqual([7.35, 1.47, 1.47, 1.47]);
  });

  it('still converts a legacy screen-unit dash from a stale payload', () => {
    const { ctx, lineDashes } = makeCtx();
    run([line({ stroke: '#0ff', strokeWidth: 0.25, dash: [5, 5], dashUnits: 'screen' })], ctx);

    expect(lineDashes[0]).toEqual([5 / SCALE, 5 / SCALE]);
  });
});
