import { describe, expect, it } from 'vitest';
import { renderManualMarkings } from './renderManualMarkings';
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


describe('renderManualMarkings', () => {
  // The badge tests that stood here moved to `markerStyles.test.ts` on 2026-08-18, when
  // recorded markings started drawing through `renderViolationReticles` — the same renderer as
  // engine findings. What they pinned is split in two now: which rows become markers and with
  // what coordinates is `markingsToMarkers`, and how a marker is painted is the shared renderer
  // the AI markers have always used. Asserting either here would be asserting about a function
  // that no longer does it.

  it('marks the half-finished pair on the sheet it was started from, and nowhere else', () => {
    const pending = { side: 'ref', coordinates: [100, 200] as [number, number] };

    const onRef = recordingCtx();
    renderManualMarkings({ frame: frame(onRef.ctx), side: 'ref', hoveredEntityId: null, pendingPairRef: pending });
    const onRev = recordingCtx();
    renderManualMarkings({ frame: frame(onRev.ctx), side: 'rev', hoveredEntityId: null, pendingPairRef: pending });

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
      frame: frame(ctx), side: 'rev',
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
      frame: frame(ctx), side: 'rev',
      hoveredEntityId: 'e1', entityHitIndex: index, pendingPairRef: null,
    });
    const label = texts.map((t) => t[0]).join(' ');
    expect(label).toContain('145');
    expect(label, 'CAD markup must not reach the label').not.toContain('%%c');
    expect(label, 'the entity type is noise now').not.toContain('text');
  });

  it('still finishes the pass when the hovered entity has no value', () => {
    // The chip is skipped, never the pass. An early return here would silently take the
    // cross-sheet boxes and the half-finished pair with it — all drawn from different state,
    // so nothing about the hover branch would tell you they had been lost.
    const bounds = { id: 'e1', entity: { type: 'line', properties: {} }, x0: 0, y0: 0, x1: 20, y1: 5 };
    const index: any = { boundsFor: () => bounds };
    const { ctx, arcs } = recordingCtx();
    renderManualMarkings({
      frame: frame(ctx),
      side: 'rev', hoveredEntityId: 'e1', entityHitIndex: index,
      pendingPairRef: { side: 'rev', coordinates: [100, 100] },
    });
    expect(arcs.length, 'the pending-pair ring must still be drawn').toBeGreaterThan(0);
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
      side: 'rev',
      hoveredEntityId: null,
      entityHitIndex: index,
      pendingPairRef: null,
    });
    expect(rects).toHaveLength(0);
  });

  it('flipWorldY is applied once, not twice', () => {
    // A direct statement of the invariant, so a future reader does not have to infer it: the
    // ring's screen Y equals worldToScreen's, which already contains exactly one flip. Asserted
    // on the pending pair now that badges draw elsewhere — same coordinate space, same hazard,
    // and this is the last thing in this module positioned from a CAD-space point.
    const { ctx, arcs } = recordingCtx();
    renderManualMarkings({
      frame: frame(ctx), side: 'rev', hoveredEntityId: null,
      pendingPairRef: { side: 'rev', coordinates: [500, 600] },
    });

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
       zone: null, zoneMeasured: false, zfx: null, zfy: null, cfx: null, cfy: null,
       sfx: null, sfy: null, ...o });

  const run = (ctx: any, side: 'ref' | 'rev', locator: any, ix?: EntityHitIndex, zones?: any) =>
    renderManualMarkings({
      frame: otherFrame(ctx), side, hoveredEntityId: null,
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
       zone: null, zoneMeasured: false, zfx: null, zfy: null, cfx: null, cfy: null,
       sfx: null, sfy: null, ...o });

  const run = (
    ctx: any,
    side: 'ref' | 'rev',
    locators: { hover?: any; selection?: any },
    ix?: EntityHitIndex,
  ) =>
    renderManualMarkings({
      frame: otherFrame(ctx), side, hoveredEntityId: null,
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

describe('which of several identical values is the counterpart', () => {
  // The case the owner caught on `M745204N01`: three `60°` angular dimensions per sheet, and
  // selecting the reference's LEFT one outlined the revision's TOP one. Both sheets draw the
  // same view, at different scales and in different places, so the nearest sheet fraction is
  // simply not the corresponding dimension — it is whichever one the layout happens to put
  // closest.
  const OTHER = getNormalization(parseBounds([-21.0, -14.85, 441.0, 311.85]))!;
  const otherFrame = (ctx: any) =>
    ({ ctx, isExport: true, viewport: VIEWPORT, norm: OTHER, scale: 1, transX: 0, transY: 0 }) as any;

  /** The revision's three `60°`, placed as they sit on that sheet. */
  const target = () => {
    const ix = new EntityHitIndex();
    const at = (id: string, x: number, y: number) =>
      ix.record({ id, type: 'dimension', properties: { text: '60°', dim_type: 2 } },
                { x0: x, y0: y, x1: x + 40, y1: y + 20 });
    at('top', 1005, 165);
    at('left', 830, 270);
    at('right', 1170, 255);
    return ix;
  };

  const loc = (o: Record<string, any> = {}) =>
    ({ side: 'ref' as const, value: '60°', entityType: 'dimension', dimKind: 2,
       zone: null, zoneMeasured: false, zfx: null, zfy: null, cfx: null, cfy: null,
       sfx: null, sfy: null, ...o });

  const run = (ctx: any, locator: any, ix: EntityHitIndex) =>
    renderManualMarkings({
      frame: otherFrame(ctx), side: 'rev', hoveredEntityId: null,
      pendingPairRef: null, selectionLocator: locator, entityHitIndex: ix,
    });

  /** Outlines are box-height; the chip is not. Returns each outline's left edge. */
  const outlineXs = (rects: number[][]) =>
    rects.filter((r) => Math.abs(r[3] - 20) < 1e-6).map((r) => r[0]);

  it('picks the counterpart by where it sits AMONG the other copies of its value', () => {
    // The reference's own three `60°` span x 85..555, y 44..190; its left-hand one is centred at
    // (105, 180), i.e. 4% across and 93% down that group. The revision's left-hand one is the
    // only candidate anywhere near those fractions.
    const { ctx, rects } = recordingCtx();
    run(ctx, loc({ cfx: 20 / 470, cfy: 136 / 146 }), target());

    expect(outlineXs(rects)).toEqual([830]);
  });

  it('is not fooled by the two sheets drawing that view at different scales', () => {
    // Same source fractions, target scaled 3x and shifted far away. Fractions are invariant to
    // both, which is the entire reason this beats an absolute position.
    const ix = new EntityHitIndex();
    const at = (id: string, x: number, y: number) =>
      ix.record({ id, type: 'dimension', properties: { text: '60°', dim_type: 2 } },
                { x0: x, y0: y, x1: x + 120, y1: y + 60 });
    at('top', 5015, 495);
    at('left', 4490, 810);
    at('right', 5510, 765);

    const { ctx, rects } = recordingCtx();
    run(ctx, loc({ cfx: 20 / 470, cfy: 136 / 146 }), ix);
    expect(rects.filter((r) => Math.abs(r[3] - 60) < 1e-6).map((r) => r[0])).toEqual([4490]);
  });

  it('picks the TOP one when that is genuinely the one selected', () => {
    // The reference's top `60°` is centred at (320, 54): 50% across, 7% down. The check that the
    // test above is measuring the tie-break rather than a constant.
    const { ctx, rects } = recordingCtx();
    run(ctx, loc({ cfx: 235 / 470, cfy: 10 / 146 }), target());
    expect(outlineXs(rects)).toEqual([1005]);
  });

  it('outlines every candidate when the group fraction is absent', () => {
    // `groupFractionOf` returns null for a value appearing once, and a locator built before this
    // field existed carries undefined. Neither may be read as a position — the honest answer is
    // all three, which is what the overlay did before any tie-break existed.
    const { ctx, rects } = recordingCtx();
    run(ctx, loc(), target());
    expect(outlineXs(rects)).toHaveLength(3);
  });

  it('treats an undefined fraction as absent, not as a number', () => {
    // A null check would pass `undefined` through and poison every distance with NaN, which
    // looks exactly like a tie-break that ran and found nothing.
    const { ctx, rects } = recordingCtx();
    run(ctx, loc({ cfx: undefined, cfy: undefined }), target());
    expect(outlineXs(rects)).toHaveLength(3);
  });
});
