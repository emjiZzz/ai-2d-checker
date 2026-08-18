import { describe, expect, it } from 'vitest';
import { renderManualMarkings, MARKING_STATUS_STYLE } from './renderManualMarkings';
import { EntityHitIndex, normalizeEntityValue } from './entityPicking';
import { getNormalization, parseBounds, worldToScreen, flipWorldY } from '../../utils/coordinateTransform';

/**
 * Where the recorded markings are drawn.
 *
 * Placement, not paint counts. This overlay's whole job is to say "you marked *that* value", so
 * a badge in the wrong place is worse than no badge at all — it asserts a claim about an entity
 * the engineer never touched. `renderViewOrigins` shipped exactly that defect twice, mirrored
 * about the sheet's centreline, and stayed green because its tests counted `stroke()` calls and
 * discarded every coordinate.
 *
 * So every test here asserts a coordinate.
 */

/** `render_bounds` of `M7452A0N01_reference`, as the app actually loads it. */
const NORM = getNormalization(parseBounds([-52.5, -37.125, 1102.5, 779.625]))!;
const VIEWPORT = { x: 40, y: 25, scale: 1.3 };

function recordingCtx() {
  const arcs: [number, number, number][] = [];
  const rects: [number, number, number, number][] = [];
  const texts: [string, number, number][] = [];
  const fills: string[] = [];
  // Whether a dash pattern was set at the moment of each strokeRect. Solid and dashed outlines
  // mean different things here — a selected pair versus a passing cursor — so the distinction is
  // behaviour, not styling.
  const dashes: boolean[] = [];
  let fillStyle = '';
  let lineDash: number[] = [];
  const noop = () => {};
  const ctx: any = new Proxy(
    {},
    {
      get: (_t, k) => {
        if (k === 'arc') return (x: number, y: number, r: number) => { arcs.push([x, y, r]); };
        if (k === 'fill') return () => { fills.push(fillStyle); };
        if (k === 'fillRect') return (x: number, y: number, w: number, h: number) => { rects.push([x, y, w, h]); };
        if (k === 'setLineDash') return (d: number[]) => { lineDash = d ?? []; };
        if (k === 'strokeRect') return (x: number, y: number, w: number, h: number) => { rects.push([x, y, w, h]); dashes.push(lineDash.length > 0); };
        if (k === 'fillText') return (t: string, x: number, y: number) => { texts.push([t, x, y]); };
        // The real 2D context measures text; the label chip sizes itself from it.
        if (k === 'measureText') return (t: string) => ({ width: t.length * 5 });
        if (k === 'fillStyle') return fillStyle;
        return noop;
      },
      set: (_t, k, v) => {
        if (k === 'fillStyle') fillStyle = v;
        return true;
      },
    },
  );
  return { ctx, arcs, rects, texts, fills, dashes };
}

const frame = (ctx: any) =>
  ({
    ctx,
    isExport: true, // keeps dpr at 1 so screen coords are comparable
    viewport: VIEWPORT,
    norm: NORM,
    scale: 0.8,
    transX: 12,
    transY: 7,
    isNeonModeActive: false,
  }) as any;

const marking = (over: Record<string, any> = {}) => ({
  id: 'm1',
  status: 'MATCHED',
  is_bulk: false,
  retracted_at: null,
  ref_coordinates: [100, 200],
  rev_coordinates: [500, 600],
  ...over,
});

describe('renderManualMarkings', () => {
  it('draws a badge exactly where the marking was recorded', () => {
    const { ctx, arcs } = recordingCtx();
    renderManualMarkings({
      frame: frame(ctx),
      markings: [marking()],
      side: 'rev',
      hoveredEntityId: null,
      pendingPairRef: null,
    });

    // The stored coordinate is CAD Y-up; `worldToScreen` applies the flip. If an extra
    // `flipWorldY` ever creeps in, this y goes to the wrong side of the centreline.
    const expected = worldToScreen(500, 600, NORM, VIEWPORT);
    expect(arcs.length).toBeGreaterThan(0);
    for (const [x, y] of arcs) {
      expect(x).toBeCloseTo(expected.x, 6);
      expect(y).toBeCloseTo(expected.y, 6);
    }
  });

  it('is not mirrored: two markings either side of the centreline keep their order', () => {
    // The failure mode `renderViewOrigins` shipped — error proportional to distance from the
    // centreline, so it looks fine in the middle of the sheet and is far out at the edges.
    const { ctx, arcs } = recordingCtx();
    renderManualMarkings({
      frame: frame(ctx),
      markings: [
        marking({ id: 'low', rev_coordinates: [500, 0] }),
        marking({ id: 'high', rev_coordinates: [500, 700] }),
      ],
      side: 'rev',
      hoveredEntityId: null,
      pendingPairRef: null,
    });

    const low = arcs[0][1];
    const high = arcs[arcs.length - 1][1];
    // Higher in CAD Y must be *smaller* in screen Y once flipped.
    expect(high).toBeLessThan(low);
    expect(high).toBeCloseTo(worldToScreen(500, 700, NORM, VIEWPORT).y, 6);
  });

  it('uses each sheet own coordinate for a CHANGED pair', () => {
    // The pair takes two clicks precisely because the two sides sit at different places. Reusing
    // one coordinate for both canvases would put the reference badge on the revision geometry.
    const changed = marking({ status: 'CHANGED', ref_coordinates: [10, 20], rev_coordinates: [900, 700] });

    const ref = recordingCtx();
    renderManualMarkings({ frame: frame(ref.ctx), markings: [changed], side: 'ref', hoveredEntityId: null, pendingPairRef: null });
    const rev = recordingCtx();
    renderManualMarkings({ frame: frame(rev.ctx), markings: [changed], side: 'rev', hoveredEntityId: null, pendingPairRef: null });

    expect(ref.arcs[0][0]).toBeCloseTo(worldToScreen(10, 20, NORM, VIEWPORT).x, 6);
    expect(rev.arcs[0][0]).toBeCloseTo(worldToScreen(900, 700, NORM, VIEWPORT).x, 6);
    expect(ref.arcs[0][0]).not.toBeCloseTo(rev.arcs[0][0], 1);
  });

  it('skips a marking that has no coordinate for this sheet', () => {
    // An ADDED exists only on the revision; drawing it on the reference would assert a finding
    // against geometry that has none.
    const { ctx, arcs } = recordingCtx();
    renderManualMarkings({
      frame: frame(ctx),
      markings: [marking({ status: 'ADDED', ref_coordinates: null })],
      side: 'ref',
      hoveredEntityId: null,
      pendingPairRef: null,
    });
    expect(arcs).toHaveLength(0);
  });

  it('does not draw a retracted marking', () => {
    const { ctx, arcs } = recordingCtx();
    renderManualMarkings({
      frame: frame(ctx),
      markings: [marking({ retracted_at: '2026-08-18T00:00:00Z' })],
      side: 'rev',
      hoveredEntityId: null,
      pendingPairRef: null,
    });
    expect(arcs).toHaveLength(0);
  });

  it('draws each status with its own glyph', () => {
    for (const [status, style] of Object.entries(MARKING_STATUS_STYLE)) {
      const { ctx, texts } = recordingCtx();
      renderManualMarkings({
        frame: frame(ctx),
        markings: [marking({ status })],
        side: 'rev',
        hoveredEntityId: null,
        pendingPairRef: null,
      });
      expect(texts[0][0], `${status} glyph`).toBe(style.glyph);
    }
  });

  it('rings a bulk anchor so it does not read as a single stamp', () => {
    const plain = recordingCtx();
    renderManualMarkings({ frame: frame(plain.ctx), markings: [marking()], side: 'rev', hoveredEntityId: null, pendingPairRef: null });
    const bulk = recordingCtx();
    renderManualMarkings({ frame: frame(bulk.ctx), markings: [marking({ is_bulk: true })], side: 'rev', hoveredEntityId: null, pendingPairRef: null });

    expect(bulk.arcs.length).toBeGreaterThan(plain.arcs.length);
    expect(Math.max(...bulk.arcs.map((a) => a[2]))).toBeGreaterThan(Math.max(...plain.arcs.map((a) => a[2])));
  });

  it('marks the half-finished pair on the sheet it was started from, and nowhere else', () => {
    const pending = { side: 'ref', coordinates: [100, 200] as [number, number] };

    const onRef = recordingCtx();
    renderManualMarkings({ frame: frame(onRef.ctx), markings: [], side: 'ref', hoveredEntityId: null, pendingPairRef: pending });
    const onRev = recordingCtx();
    renderManualMarkings({ frame: frame(onRev.ctx), markings: [], side: 'rev', hoveredEntityId: null, pendingPairRef: pending });

    expect(onRef.arcs).toHaveLength(1);
    expect(onRef.arcs[0][0]).toBeCloseTo(worldToScreen(100, 200, NORM, VIEWPORT).x, 6);
    expect(onRev.arcs).toHaveLength(0);
  });

  it('labels the highlight with the VALUE alone, not the entity type', () => {
    // It read `dimension - 183`, which earned its space when arcs and lines were indexed too
    // and a large unexplained box needed to say `arc`. Only value carriers are indexed now, so
    // the type is the same answer every time and the number is the whole point.
    const bounds = {
      id: 'e1',
      entity: { type: 'dimension', properties: { text: '183' } },
      x0: 0, y0: 0, x1: 30, y1: 10,
    };
    const index: any = { boundsFor: () => bounds };
    const { ctx, texts } = recordingCtx();
    renderManualMarkings({
      frame: frame(ctx), markings: [], side: 'rev',
      hoveredEntityId: 'e1', entityHitIndex: index, pendingPairRef: null,
    });
    const label = texts.map((t) => t[0]).join(' ');
    expect(label).toContain('183');
    expect(label, 'the entity type is noise now').not.toContain('dimension');
  });

  it('strips CAD markup from the label', () => {
    const bounds = {
      id: 'e1',
      entity: { type: 'text', properties: { text: '%%c145' } },
      x0: 0, y0: 0, x1: 30, y1: 10,
    };
    const index: any = { boundsFor: () => bounds };
    const { ctx, texts } = recordingCtx();
    renderManualMarkings({
      frame: frame(ctx), markings: [], side: 'rev',
      hoveredEntityId: 'e1', entityHitIndex: index, pendingPairRef: null,
    });
    const label = texts.map((t) => t[0]).join(' ');
    expect(label).toContain('145');
    expect(label, 'CAD markup must not reach the label').not.toContain('%%c');
    expect(label, 'the entity type is noise now').not.toContain('text');
  });

  it('still draws the markings when the hovered entity has no value', () => {
    // The chip is skipped, never the pass. An early return here would silently take the
    // recorded markings and the cross-sheet boxes with it.
    const bounds = { id: 'e1', entity: { type: 'line', properties: {} }, x0: 0, y0: 0, x1: 20, y1: 5 };
    const index: any = { boundsFor: () => bounds };
    const { ctx, arcs } = recordingCtx();
    renderManualMarkings({
      frame: frame(ctx), markings: [{ status: 'ADDED', rev_coordinates: [100, 100] }],
      side: 'rev', hoveredEntityId: 'e1', entityHitIndex: index, pendingPairRef: null,
    });
    expect(arcs.length, 'the ADDED badge must still be drawn').toBeGreaterThan(0);
  });

  it('highlights the hovered entity using the index own flipped-world bounds', () => {
    // The hover box comes from a DIFFERENT space than the badges: the index already stores
    // flipped-world units, so it maps with the frame's scale/translation rather than through
    // `worldToScreen`. Mixing the two silently offsets the highlight from the thing it marks.
    const bounds = { id: 'e1', entity: {}, x0: 100, y0: 50, x1: 140, y1: 62 };
    const index: any = { boundsFor: (id: string | null) => (id === 'e1' ? bounds : null) };

    const { ctx, rects } = recordingCtx();
    renderManualMarkings({
      frame: frame(ctx),
      markings: [],
      side: 'rev',
      hoveredEntityId: 'e1',
      entityHitIndex: index,
      pendingPairRef: null,
    });

    // The region fill sits exactly on the entity's bounds — no padding, so the highlight
    // cannot overstate how large the entity is.
    expect(rects.length).toBeGreaterThan(0);
    const region = rects.find((r) => Math.abs(r[2] - 40 * 0.8) < 1e-6)!;
    expect(region, 'no rect matched the entity extent').toBeDefined();
    expect(region[0]).toBeCloseTo(100 * 0.8 + 12, 6);
    expect(region[1]).toBeCloseTo(50 * 0.8 + 7, 6);
    expect(region[3]).toBeCloseTo(12 * 0.8, 6);
  });

  it('draws no highlight when nothing is hovered', () => {
    const index: any = { boundsFor: () => null };
    const { ctx, rects } = recordingCtx();
    renderManualMarkings({
      frame: frame(ctx),
      markings: [],
      side: 'rev',
      hoveredEntityId: null,
      entityHitIndex: index,
      pendingPairRef: null,
    });
    expect(rects).toHaveLength(0);
  });

  it('flipWorldY is applied once, not twice', () => {
    // A direct statement of the invariant, so a future reader does not have to infer it: the
    // badge's screen Y equals worldToScreen's, which already contains exactly one flip.
    const { ctx, arcs } = recordingCtx();
    renderManualMarkings({ frame: frame(ctx), markings: [marking({ rev_coordinates: [500, 600] })], side: 'rev', hoveredEntityId: null, pendingPairRef: null });

    const onceFlipped = worldToScreen(500, 600, NORM, VIEWPORT).y;
    const twiceFlipped = worldToScreen(500, flipWorldY(600, NORM), NORM, VIEWPORT).y;
    expect(arcs[0][1]).toBeCloseTo(onceFlipped, 6);
    expect(arcs[0][1]).not.toBeCloseTo(twiceFlipped, 1);
  });
});

describe('cross-sheet value match', () => {
  /** A second sheet with DIFFERENT render_bounds — the normal case, since the two sides come
   *  from different exporters and do not share an origin. */
  const OTHER = getNormalization(parseBounds([-21.0, -14.85, 441.0, 311.85]))!;
  // flipY(y) = ymax + ymin - y = 297 - y, so a CAD zone spanning y 200..297 covers flipped 0..97.
  const zone = (xmin: number, xmax: number, confidence = 'content_aware') =>
    ({ xmin, ymin: 200, xmax, ymax: 297, confidence });
  const zonesOf = (o: Record<string, any>) =>
    ({ drawing_id: 'd', render_bounds: null, views: null, notes: null, bom: null, title: null,
       tolerance: null, iso: null, title_upper_left: null, shim: null, ...o }) as any;

  /** Boxes land at x = i*100..i*100+40, flipped y 50..70 — inside the zones above. */
  const indexOf = (...ents: any[]) => {
    const ix = new EntityHitIndex();
    ents.forEach((e, i) => ix.record(e, { x0: i * 100, y0: 50, x1: i * 100 + 40, y1: 70 }));
    return ix;
  };

  const val = (id: string, text: string) => ({ id, type: 'text', properties: { text } });
  const dim = (id: string, text: string, dimType: number) =>
    ({ id, type: 'dimension', properties: { text, dim_type: dimType } });

  const otherFrame = (ctx: any) =>
    ({ ctx, isExport: true, viewport: VIEWPORT, norm: OTHER, scale: 0.8, transX: 12, transY: 7 }) as any;

  /** A locator with plain defaults; each test overrides what it is exercising. */
  const loc = (o: Record<string, any> = {}) =>
    ({ side: 'rev' as const, value: '145', entityType: 'text', dimKind: null,
       zone: null, zoneMeasured: false, zfx: null, zfy: null, sfx: null, sfy: null, ...o });

  const run = (ctx: any, side: 'ref' | 'rev', locator: any, ix?: EntityHitIndex, zones?: any) =>
    renderManualMarkings({
      frame: otherFrame(ctx), markings: [], side, hoveredEntityId: null,
      pendingPairRef: null, hoverLocator: locator, entityHitIndex: ix, zones,
    });

  /** Outline rects are the ones the height of a recorded box; the label chip is not. */
  const outlines = (rects: number[][]) => rects.filter((r) => Math.abs(r[3] - 20 * 0.8) < 1e-6);

  it('outlines only on the sheet the cursor is NOT on', () => {
    const ix = indexOf(val('a', '145'));
    const away = recordingCtx();
    run(away.ctx, 'ref', loc(), ix);
    const same = recordingCtx();
    run(same.ctx, 'rev', loc(), ix);

    expect(outlines(away.rects)).toHaveLength(1);
    expect(same.rects).toHaveLength(0);
  });

  it('outlines the match at ITS OWN coordinates, not the source rectangle', () => {
    // The defect this replaced: the fraction round-trip cancelled to the source box's pixel,
    // so the outline never depended on the target sheet at all.
    const ix = indexOf(val('a', 'zzz'), val('b', '145'));
    const { ctx, rects } = recordingCtx();
    run(ctx, 'ref', loc(), ix);

    const box = outlines(rects)[0];
    expect(box[0]).toBeCloseTo(100 * 0.8 + 12, 6);
    expect(box[1]).toBeCloseTo(50 * 0.8 + 7, 6);
    expect(box[2]).toBeCloseTo(40 * 0.8, 6);
  });

  it('matches across the two exporters spellings', () => {
    expect(normalizeEntityValue('１４５')).toBe(normalizeEntityValue('145'));
    expect(normalizeEntityValue('%%c8')).toBe(normalizeEntityValue('8'));
    expect(normalizeEntityValue('ø145')).toBe(normalizeEntityValue('145'));
    expect(normalizeEntityValue('６－１２キリ')).toBe(normalizeEntityValue('6-12キリ'));
    expect(normalizeEntityValue(' 145 ')).toBe(normalizeEntityValue('145'));
  });

  it('keeps degree and plus/minus, so 60 degrees does not match a bare 60', () => {
    expect(normalizeEntityValue('60%%d')).toBe(normalizeEntityValue('60°'));
    expect(normalizeEntityValue('60°')).not.toBe(normalizeEntityValue('60'));
    expect(normalizeEntityValue('1%%p0.5')).toBe(normalizeEntityValue('1±0.5'));
  });

  it('does not match a different ENTITY TYPE', () => {
    const ix = indexOf(val('note', '145'));
    const { ctx, rects } = recordingCtx();
    run(ctx, 'ref', loc({ entityType: 'dimension', dimKind: 2 }), ix);
    expect(rects).toHaveLength(0);
  });

  it('does not match a different DIMENSION KIND', () => {
    const ix = indexOf(dim('linear', '80', 0));
    const { ctx, rects } = recordingCtx();
    run(ctx, 'ref', loc({ value: '80', entityType: 'dimension', dimKind: 2 }), ix);
    expect(rects).toHaveLength(0);

    const hit = recordingCtx();
    run(hit.ctx, 'ref', loc({ value: '80', entityType: 'dimension', dimKind: 0 }), ix);
    expect(outlines(hit.rects)).toHaveLength(1);
  });

  it('does not match the same value in a different ZONE', () => {
    const ix = indexOf(val('inViews', '145'), val('spacer', 'zz'), val('inBom', '145'));
    const zones = zonesOf({ views: zone(-50, 150), bom: zone(160, 400) });

    const v = recordingCtx();
    run(v.ctx, 'ref', loc({ zone: 'views', zoneMeasured: true }), ix, zones);
    expect(outlines(v.rects)).toHaveLength(1);
    expect(outlines(v.rects)[0][0]).toBeCloseTo(0 * 0.8 + 12, 6);

    const b = recordingCtx();
    run(b.ctx, 'ref', loc({ zone: 'bom', zoneMeasured: true }), ix, zones);
    expect(outlines(b.rects)).toHaveLength(1);
    expect(outlines(b.rects)[0][0]).toBeCloseTo(200 * 0.8 + 12, 6);
  });

  it('narrows several equal candidates in ONE zone to the perfect match', () => {
    // The `x3` reported from the app: three 60° angular dimensions in the same view. Within a
    // single zone the two revisions DO arrange alike, so zone-relative position separates them.
    const ix = indexOf(dim('a', '60°', 2), dim('b', '60°', 2));
    const zones = zonesOf({ views: zone(-50, 150) });

    const near0 = recordingCtx();
    run(near0.ctx, 'ref', loc({ value: '60°', entityType: 'dimension', dimKind: 2,
                                zone: 'views', zoneMeasured: true, zfx: 0.34, zfy: 0.62 }), ix, zones);
    expect(outlines(near0.rects)).toHaveLength(1);
    expect(outlines(near0.rects)[0][0]).toBeCloseTo(0 * 0.8 + 12, 6);

    const near1 = recordingCtx();
    run(near1.ctx, 'ref', loc({ value: '60°', entityType: 'dimension', dimKind: 2,
                                zone: 'views', zoneMeasured: true, zfx: 0.86, zfy: 0.62 }), ix, zones);
    expect(outlines(near1.rects)).toHaveLength(1);
    expect(outlines(near1.rects)[0][0]).toBeCloseTo(100 * 0.8 + 12, 6);
  });

  it('ignores zone when the SOURCE sheet only guessed it', () => {
    // M745204N01's reference resolves `tolerance`, `notes` and `iso` by percentage fallback, so
    // its zone for an entity disagrees with the revision's. Gating on a guess blanked 120 of 184
    // hovers. The source zone here is a guessed `tolerance` that no candidate is in; the match
    // must still be found on value + type + kind.
    const ix = indexOf(val('a', '145'));
    const zones = zonesOf({ views: zone(-50, 400) });
    const { ctx, rects } = recordingCtx();
    run(ctx, 'ref', loc({ zone: 'tolerance', zoneMeasured: false }), ix, zones);
    expect(outlines(rects)).toHaveLength(1);
  });

  it('ignores zone when the TARGET sheet only guessed it', () => {
    // The same rule from the other side: a candidate sitting in a percentage-fallback box has
    // no trustworthy zone, so its zone must not exclude it.
    const ix = indexOf(val('a', '145'));
    const zones = zonesOf({ views: zone(-50, 400, 'percentage_fallback') });
    const { ctx, rects } = recordingCtx();
    run(ctx, 'ref', loc({ zone: 'bom', zoneMeasured: true }), ix, zones);
    expect(outlines(rects)).toHaveLength(1);
  });

  it('still excludes a different zone when BOTH sides measured it', () => {
    // The filter has to keep working where it is trustworthy, or the relaxation above would be
    // indistinguishable from dropping zone altogether.
    const ix = indexOf(val('inViews', '145'), val('spacer', 'zz'), val('inBom', '145'));
    const zones = zonesOf({ views: zone(-50, 150), bom: zone(160, 400) });
    const { ctx, rects } = recordingCtx();
    run(ctx, 'ref', loc({ zone: 'bom', zoneMeasured: true }), ix, zones);
    expect(outlines(rects)).toHaveLength(1);
    expect(outlines(rects)[0][0]).toBeCloseTo(200 * 0.8 + 12, 6);
  });

  it('falls back to sheet position to separate candidates zone cannot', () => {
    // The weak tie-break, ordering candidates already equal on value, type and kind. Boxes sit
    // at flipped-world x 0 and 100 (centres 20 and 120); the sheet spans 462 from xmin -21.
    const ix = indexOf(val('a', '145'), val('b', '145'));
    const { ctx, rects } = recordingCtx();
    run(ctx, 'ref', loc({ sfx: (120 + 21) / 462, sfy: (60 + 14.85) / 326.7 }), ix);
    expect(outlines(rects)).toHaveLength(1);
    expect(outlines(rects)[0][0]).toBeCloseTo(100 * 0.8 + 12, 6);
  });

  it('outlines every candidate when there is nothing to break the tie with', () => {
    // No zone on either side means no basis to choose. Returning one arbitrary box would be
    // indistinguishable from a confident answer.
    const ix = indexOf(val('a', '145'), val('b', '145'));
    const { ctx, rects } = recordingCtx();
    run(ctx, 'ref', loc(), ix);
    expect(outlines(rects)).toHaveLength(2);
  });

  it('draws nothing when the value appears nowhere on this sheet', () => {
    const { ctx, rects } = recordingCtx();
    run(ctx, 'ref', loc({ value: 'NOTHERE' }), indexOf(val('a', '145')));
    expect(rects).toHaveLength(0);
  });

  it('draws nothing for an entity with no value, rather than outlining all geometry', () => {
    const ix = indexOf({ id: 'line-1', type: 'line', properties: {} });
    const { ctx, rects } = recordingCtx();
    run(ctx, 'ref', loc({ value: '', entityType: 'line' }), ix);
    expect(rects).toHaveLength(0);
  });

  it('draws nothing when there is no locator', () => {
    const { ctx, rects } = recordingCtx();
    run(ctx, 'ref', null, indexOf(val('a', '145')));
    expect(rects).toHaveLength(0);
  });
});

describe('the selected entity pair', () => {
  // The bug the owner caught from a screenshot: clicking an entity boxed it on its own sheet and
  // left the counterpart on the other sheet unmarked. The matcher and the outline already
  // existed — only hover published a locator, so selecting one published nothing to match on.
  const OTHER = getNormalization(parseBounds([-21.0, -14.85, 441.0, 311.85]))!;
  const indexOf = (...ents: any[]) => {
    const ix = new EntityHitIndex();
    ents.forEach((e, i) => ix.record(e, { x0: i * 100, y0: 50, x1: i * 100 + 40, y1: 70 }));
    return ix;
  };
  const val = (id: string, text: string) => ({ id, type: 'text', properties: { text } });
  const otherFrame = (ctx: any) =>
    ({ ctx, isExport: true, viewport: VIEWPORT, norm: OTHER, scale: 0.8, transX: 12, transY: 7 }) as any;
  const loc = (o: Record<string, any> = {}) =>
    ({ side: 'rev' as const, value: '145', entityType: 'text', dimKind: null,
       zone: null, zoneMeasured: false, zfx: null, zfy: null, sfx: null, sfy: null, ...o });

  const run = (
    ctx: any,
    side: 'ref' | 'rev',
    locators: { hover?: any; selection?: any },
    ix?: EntityHitIndex,
  ) =>
    renderManualMarkings({
      frame: otherFrame(ctx), markings: [], side, hoveredEntityId: null,
      pendingPairRef: null, hoverLocator: locators.hover ?? null,
      selectionLocator: locators.selection ?? null, entityHitIndex: ix,
    });

  const outlines = (rects: number[][]) => rects.filter((r) => Math.abs(r[3] - 20 * 0.8) < 1e-6);

  it('outlines the counterpart of a SELECTED entity, with the cursor nowhere near it', () => {
    // `hoverLocator: null` is the whole point — this is the state the engineer is in when they
    // have clicked something and moved the mouse away to look at the other sheet.
    const ix = indexOf(val('a', '145'));
    const { ctx, rects } = recordingCtx();
    run(ctx, 'ref', { selection: loc() }, ix);
    expect(outlines(rects)).toHaveLength(1);
  });

  it('outlines only on the sheet the selection is NOT on', () => {
    // Same gate hover obeys: a locator describes an entity on the other canvas, and re-boxing
    // the sheet it came from would just double the box already drawn there.
    const ix = indexOf(val('a', '145'));
    const same = recordingCtx();
    run(same.ctx, 'rev', { selection: loc() }, ix);
    expect(same.rects).toHaveLength(0);
  });

  it('draws the selected pair SOLID and a hover DASHED', () => {
    // The two states have to stay distinguishable: "these two are the pair I am judging" versus
    // "the same value happens to be over here". Collapsing them to one style loses that.
    const ix = indexOf(val('a', '145'));

    const sel = recordingCtx();
    run(sel.ctx, 'ref', { selection: loc() }, ix);
    expect(sel.dashes.slice(0, 1)).toEqual([false]);

    const hov = recordingCtx();
    run(hov.ctx, 'ref', { hover: loc() }, ix);
    expect(hov.dashes.slice(0, 1)).toEqual([true]);
  });

  it('draws both when the cursor rests on a different value than the selection', () => {
    const ix = indexOf(val('a', '145'), val('b', '183'));
    const { ctx, rects } = recordingCtx();
    run(ctx, 'ref', { selection: loc(), hover: loc({ value: '183' }) }, ix);
    expect(outlines(rects)).toHaveLength(2);
  });

  it('draws nothing when the selection is cleared', () => {
    const ix = indexOf(val('a', '145'));
    const { ctx, rects } = recordingCtx();
    run(ctx, 'ref', {}, ix);
    expect(rects).toHaveLength(0);
  });
});
