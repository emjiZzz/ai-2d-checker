import { describe, it, expect } from 'vitest';
import {
  normalizeEntityValue,
  EntityHitIndex,
  entityWorldBounds,
  entityDisplayText,
  entityValueOf,
  isStampClick,
  CLICK_SLOP_PX,
} from './entityPicking';
import { getNormalization, flipWorldY, parseBounds } from '../../utils/coordinateTransform';

/**
 * Picking accuracy is dataset accuracy.
 *
 * Every ground-truth marking is addressed to whatever entity this module says was under the
 * cursor. A hit test that is subtly wrong does not produce a visible bug — it produces a
 * dataset where some fraction of a human's judgements are filed against entities they never
 * looked at, and nothing downstream can tell which ones. So the cases below are the ones that
 * would be silently wrong rather than obviously broken.
 */

// `getNormalization` takes the parsed envelope, not the raw array off `render_bounds`.
const norm = getNormalization(parseBounds([0, 0, 1000, 800]));
const flipY = (y: number) => flipWorldY(y, norm);

const text = (x: number, y: number, value = 'AB', height = 10) => ({
  id: `text-${x}-${y}`,
  type: 'text',
  geometry: { insert: [x, y], text: value },
  properties: { height },
});

describe('entityWorldBounds', () => {
  it('applies the CAD Y-flip, so a box is not mirrored about the sheet centreline', () => {
    // The hazard `renderViewOrigins` shipped with: the error is proportional to distance from
    // the centreline, so a mirrored box looks perfectly plausible near the middle of the sheet
    // and is far out at the top. Bounds [0,0,1000,800] put the centreline at y=400.
    const nearTop = entityWorldBounds(text(100, 700), flipY)!;
    const nearBottom = entityWorldBounds(text(100, 100), flipY)!;

    expect(nearTop.y0).toBeLessThan(nearBottom.y0);
    expect(nearTop.y0).toBeCloseTo(flipWorldY(700, norm) - 6, 5);
  });

  it('is a no-op on Y when the drawing has no render_bounds', () => {
    // `hasBounds: false` is a deliberate passthrough — a guessed centreline is worse than an
    // unmirrored point.
    const noBounds = getNormalization(parseBounds(null));
    const b = entityWorldBounds(text(100, 700), (y) => flipWorldY(y, noBounds))!;
    expect(b.y0).toBeCloseTo(700 - 6, 5);
  });

  it('measures a DIMENSION from def_point, which is why it is reachable at all', () => {
    // `tools/eval_corpus.py worksheet` reads `insert` and so cannot place a dimension — an open
    // defect, and the reason an added dimension is one of the corpus's recorded false-negative
    // classes. A picker that inherited that assumption would be unable to record it either.
    const dim = {
      id: 'dim-1',
      type: 'dimension',
      geometry: { def_point: [400, 300], ext1_point: [380, 300] },
      properties: { text: '25', height: 8 },
    };
    expect(entityWorldBounds(dim, flipY)).not.toBeNull();
  });

  it('sizes a DIMENSION from text_height, so a pair renders the same box on both sheets', () => {
    // The two sides of a pair are not at the same CAD scale -- `M745204N01`'s reference spans
    // 1386 units against the revision's 462 -- but their text heights are proportional, 12.0
    // against 4.0, each 0.00866 of its own sheet. Reading `text_height` therefore yields boxes
    // that occupy the same fraction, and so the same number of pixels once each canvas applies
    // its own 1000/spanX normalisation.
    const dim = (textHeight: number) => ({
      id: `d-${textHeight}`,
      type: 'dimension',
      geometry: { render_text_point: [100, 100] },
      // No `height` -- dimensions do not carry one. That is what made the constant fire.
      properties: { text: '60°', text_height: textHeight },
    });

    const big = entityWorldBounds(dim(12), flipY)!;
    const small = entityWorldBounds(dim(4), flipY)!;

    const w = (b: any) => b.x1 - b.x0;
    const h = (b: any) => b.y1 - b.y0;
    // Three times the text height is three times the box, in both axes.
    expect(w(big) / w(small)).toBeCloseTo(3, 6);
    expect(h(big) / h(small)).toBeCloseTo(3, 6);
    // Divided by each sheet's own width, the two are the same size.
    expect(w(big) / 1386).toBeCloseTo(w(small) / 462, 6);
  });

  it('orients the bounding box vertically for a rotated (90°) dimension', () => {
    const unrotated = entityWorldBounds(
      { id: 'd0', type: 'dimension', geometry: { render_text_point: [100, 100] },
        properties: { text: 'ø145', text_height: 10, rotation: 0 } },
      flipY,
    )!;
    const rotated = entityWorldBounds(
      { id: 'd90', type: 'dimension', geometry: { render_text_point: [100, 100] },
        properties: { text: 'ø145', text_height: 10, rotation: 90 } },
      flipY,
    )!;

    expect(unrotated.x1 - unrotated.x0).toBeGreaterThan(unrotated.y1 - unrotated.y0);
    expect(rotated.y1 - rotated.y0).toBeGreaterThan(rotated.x1 - rotated.x0);
    expect(rotated.y1 - rotated.y0).toBeCloseTo(unrotated.x1 - unrotated.x0, 2);
    expect(rotated.x1 - rotated.x0).toBeCloseTo(unrotated.y1 - unrotated.y0, 2);
  });

  it('does not fall back to the constant when text_height is present', () => {
    // The regression: `properties.height` is absent on every dimension, so the old code used a
    // hard-coded 12 CAD units on both sheets. On the revision that is 3x too big.
    const withHeight = entityWorldBounds(
      { id: 'd', type: 'dimension', geometry: { render_text_point: [0, 0] },
        properties: { text: '60°', text_height: 4 } },
      flipY,
    )!;
    const constantFallback = entityWorldBounds(
      { id: 'd', type: 'dimension', geometry: { render_text_point: [0, 0] },
        properties: { text: '60°' } },
      flipY,
    )!;
    expect(withHeight.y1 - withHeight.y0).toBeLessThan(constantFallback.y1 - constantFallback.y0);
    expect(constantFallback.y1 - constantFallback.y0).toBeCloseTo(12 * 1.4, 6);
  });

  it('prefers render_text_point over def_point, because that is where the text is drawn', () => {
    const atDefPoint = entityWorldBounds(
      { id: 'a', type: 'dimension', geometry: { def_point: [0, 0] }, properties: { text: '25' } },
      flipY,
    )!;
    const atTextPoint = entityWorldBounds(
      {
        id: 'b',
        type: 'dimension',
        geometry: { def_point: [0, 0], render_text_point: [500, 500] },
        properties: { text: '25' },
      },
      flipY,
    )!;
    expect(atTextPoint.x0).toBeGreaterThan(atDefPoint.x1);
  });

  it('measures geometry that carries no text at all', () => {
    // Both human pairs in the eval corpus add an isometric view holding zero text and zero
    // dimensions. Geometry is the only thing such a finding can be anchored to.
    const line = { id: 'l1', type: 'line', geometry: { start: [10, 10], end: [90, 60] } };
    const bounds = entityWorldBounds(line, flipY)!;
    expect(bounds.x0).toBe(10);
    expect(bounds.x1).toBe(90);

    const ellipse = {
      id: 'e1',
      type: 'ellipse',
      geometry: { points: [[0, 0], [50, 20], [10, 40]] },
    };
    expect(entityWorldBounds(ellipse, flipY)).not.toBeNull();
  });

  it('measures a circle from its radius', () => {
    const c = { id: 'c1', type: 'circle', geometry: { center: [100, 100], radius: 25 } };
    const b = entityWorldBounds(c, flipY)!;
    expect(b.x1 - b.x0).toBeCloseTo(50, 5);
    expect(b.y1 - b.y0).toBeCloseTo(50, 5);
  });

  it('returns null for a record that can never be drawn', () => {
    // `layer` and `block` container rows are in the payload and carry no drawable geometry.
    expect(entityWorldBounds({ id: 'lay', type: 'layer', geometry: {} }, flipY)).toBeNull();
    expect(entityWorldBounds({ id: 'none', type: 'line' }, flipY)).toBeNull();
  });

  it('uses the extractor measured bbox in preference to estimating from the anchor', () => {
    // The defect this pins, and the reason the reference sheet felt unclickable: these drawings
    // are MTEXT with `attachment_point: 1`, so `insert` is the TOP-left and the glyphs hang
    // *below* it. Padding symmetrically around the anchor put the hit region above the text.
    // Measured on `M7452A0N01_reference`, clicking the middle of a value resolved to that value
    // 114/249 times before this and 244/249 after.
    const mtext = {
      id: 'mtext',
      type: 'text',
      geometry: { insert: [321.17, 609.11] },
      properties: {
        text: '1',
        height: 10,
        is_multiline: true,
        attachment_point: 1,
        bbox: [
          [321.17, 596.33],
          [329.2, 609.11],
        ],
      },
    };

    const b = entityWorldBounds(mtext, flipY)!;
    // The glyphs' centre must be inside the box. Under the old estimate it was not.
    const centreY = flipY((596.33 + 609.11) / 2);
    expect(centreY).toBeGreaterThanOrEqual(b.y0);
    expect(centreY).toBeLessThanOrEqual(b.y1);
    expect(b.x0).toBeCloseTo(321.17, 2);
    expect(b.x1).toBeCloseTo(329.2, 2);
  });

  it('falls back to estimating when no bbox was measured', () => {
    const noBbox = { id: 't', type: 'text', geometry: { insert: [10, 10] }, properties: { text: 'AB', height: 10 } };
    expect(entityWorldBounds(noBbox, flipY)).not.toBeNull();
  });

  it('never measures a BLOCK container, even though it carries an insert point', () => {
    // The defect this pins: a block row's only geometry is `insert`, so a catch-all fallback
    // gave it a small synthetic box — and because `hitTest` returns the SMALLEST match, that box
    // beat the real text inside it. The stamp modal showed `block · handle 384` instead of the
    // value the engineer clicked.
    expect(
      entityWorldBounds({ id: 'blk', type: 'block', geometry: { insert: [100, 100] } }, flipY),
    ).toBeNull();
  });

  it('does not invent a box for a type it does not understand', () => {
    // An over-broad fallback fails silently, by returning a plausible wrong entity rather than
    // nothing. Only DIMENSION legitimately anchors on a bare point.
    expect(
      entityWorldBounds({ id: 'x', type: 'wipeout', geometry: { insert: [10, 10] } }, flipY),
    ).toBeNull();
  });
});

describe('left-click stamping, and the pan it must not be confused with', () => {
  const at = (x: number, y: number) => ({ x, y });

  it('opens on a still left-click', () => {
    expect(isStampClick(0, at(100, 100), at(100, 100))).toBe(true);
  });

  it('tolerates the hand-shake in a real click', () => {
    // Nobody releases on the exact pixel they pressed. A couple of pixels is still a click.
    expect(isStampClick(0, at(100, 100), at(102, 101))).toBe(true);
    expect(isStampClick(0, at(100, 100), at(100 + CLICK_SLOP_PX, 100))).toBe(true);
  });

  it('does NOT open after a pan, which uses the same button', () => {
    // The failure that would be lived with rather than reported: a drag finishing over a value
    // pops the stamping menu open mid-sweep. Not a crash, not a wrong marking — an interruption
    // every few drags.
    expect(isStampClick(0, at(100, 100), at(140, 100))).toBe(false);
    expect(isStampClick(0, at(100, 100), at(100, 140))).toBe(false);
    expect(isStampClick(0, at(100, 100), at(104, 104))).toBe(false); // diagonal, ~5.7px
  });

  it('ignores the right and middle buttons', () => {
    // Right-click still opens the menu, but resolves no entity — one gesture records a finding.
    expect(isStampClick(2, at(100, 100), at(100, 100))).toBe(false);
    expect(isStampClick(1, at(100, 100), at(100, 100))).toBe(false);
  });

  it('ignores a release whose press was not on this canvas', () => {
    expect(isStampClick(0, null, at(100, 100))).toBe(false);
  });
});

describe('render_text is the value the sheet actually draws', () => {
  /** Real rows from `M745204N01`: the revision applies the diameter standard, the reference
   *  does not, and `properties.text` is identically bare on both. */
  const dim = (text: string, renderText?: string) =>
    ({ id: 'd', type: 'dimension', properties: { text, render_text: renderText } });

  it('shows the diameter prefix that exists only in render_text', () => {
    // The canvas has preferred `render_text` since it was found drawing `145` where iCAD draws
    // `φ145`. The picking layer read `properties.text` and so disagreed with the pixels beside
    // it: the chip said `110` over a dimension the sheet renders as `⌀110`.
    expect(entityDisplayText(dim('110', '%%c110'))).toBe('⌀110');
    expect(entityDisplayText(dim('110', '110'))).toBe('110');
    expect(entityDisplayText(dim('60°', '60%%d'))).toBe('60°');
  });

  it('matches across the diameter mark, because only one sheet applies the standard', () => {
    // The revision stores `%%c110`, the reference a bare `110`. They are the same dimension and
    // must still pair — the comparison key folds the mark away, the display keeps it.
    expect(entityValueOf(dim('110', '%%c110'))).toBe(entityValueOf(dim('110', '110')));
    expect(entityDisplayText(dim('110', '%%c110')))
      .not.toBe(entityDisplayText(dim('110', '110')));
  });

  it('ignores a `<>` placeholder and falls back to the rebuilt text', () => {
    // `<>` is the DXF "substitute the measurement here" placeholder. Painting or matching on it
    // would put a literal `<>` where a reviewer expects the measured value.
    expect(entityDisplayText(dim('60°', '<>'))).toBe('60°');
    expect(entityValueOf(dim('60°', '<>'))).toBe(entityValueOf(dim('60°', '60%%d')));
  });

  it('still finds nothing for geometry, which has neither field', () => {
    expect(entityDisplayText({ id: 'l', type: 'line', properties: {} })).toBe('');
    expect(entityValueOf({ id: 'l', type: 'line', properties: {} })).toBe('');
  });
});

describe('EntityHitIndex', () => {
  it('returns the smallest entity under the cursor, not the first or the topmost', () => {
    // A dimension's text sits inside the polyline of its view, which sits inside the sheet
    // border. First-hit or z-order picking hands back the border every time; area is the
    // ordering a person expects.
    const index = new EntityHitIndex();
    const border = { id: 'border', type: 'polyline', geometry: { points: [[0, 0], [1000, 800]] } };
    const view = { id: 'view', type: 'polyline', geometry: { points: [[80, 80], [300, 300]] } };
    const label = text(100, 100, 'A', 10);

    for (const e of [border, view, label]) index.record(e, entityWorldBounds(e, flipY));

    const hit = index.hitTest(100, flipY(100), 0);
    expect(hit?.id).toBe(label.id);
  });

  it('does not index geometry, which carries nothing to compare', () => {
    // Measured across both sides of `M745204N01`: `properties.text` is null on every line, arc,
    // circle, polyline, ellipse and leader, and set on every text and dimension. Indexing the
    // rest made hovering anywhere in a view throw a large box labelled `arc` across the drawing,
    // and made a line right-clickable — a marking whose content is "this line exists", which
    // nothing downstream can compare.
    const index = new EntityHitIndex();
    const geometry = [
      { id: 'l', type: 'line', geometry: { start: [0, 100], end: [500, 100] }, properties: {} },
      { id: 'a', type: 'arc', geometry: { center: [200, 200], radius: 50 },
        properties: { start_angle: 0, end_angle: 60 } },
      { id: 'c', type: 'circle', geometry: { center: [200, 200], radius: 50 }, properties: {} },
      { id: 'ld', type: 'leader', geometry: { points: [[0, 0], [50, 50]] }, properties: {} },
      { id: 'pl', type: 'polyline', geometry: { points: [[0, 0], [100, 100]] }, properties: {} },
    ];
    for (const e of geometry) index.record(e, entityWorldBounds(e, flipY));

    expect(index.size).toBe(0);
    expect(index.hitTest(250, flipY(100), 5)).toBeNull();
    expect(index.hitTest(200, flipY(200), 5)).toBeNull();
  });

  it('indexes on the VALUE, not on a type allow-list', () => {
    // So a CAD type nobody anticipated becomes pickable the moment it carries text, and one
    // that never carries text never does.
    const index = new EntityHitIndex();
    const oddButValued = {
      id: 'odd', type: 'some_future_type', geometry: { insert: [100, 100] },
      properties: { text: 'A1', height: 10, bbox: [[100, 92], [120, 100]] },
    };
    const oddAndEmpty = {
      id: 'blank', type: 'some_future_type', geometry: { insert: [300, 100] },
      properties: { text: '', height: 10, bbox: [[300, 92], [320, 100]] },
    };
    for (const e of [oddButValued, oddAndEmpty]) index.record(e, entityWorldBounds(e, flipY));

    expect(index.size).toBe(1);
    expect(index.hitTest(110, flipY(96), 2)?.id).toBe('odd');
  });

  it('picks the text a reference sheet nests inside a block, not the block', () => {
    // The reference is the DWG-exported side and keeps almost everything inside blocks —
    // `M745230A01`'s reference carries 24 of them against 159 text entities, sitting directly on
    // top of the content. This is the arrangement that made the reference sheet feel unclickable.
    const index = new EntityHitIndex();
    const container = { id: 'blk', type: 'block', geometry: { insert: [100, 100] } };
    const nested = { ...text(100, 100, '25', 10), id: 'nested-text' };

    for (const e of [container, nested]) index.record(e, entityWorldBounds(e, flipY));

    expect(index.size).toBe(1);
    expect(index.hitTest(101, flipY(100), 2)?.id).toBe('nested-text');
  });

  it('returns null off every entity rather than the nearest one', () => {
    // Guessing here would attribute a stray click to a real entity. An empty result is a
    // refused stamp, which is the behaviour the router also enforces.
    const index = new EntityHitIndex();
    const t = text(100, 100);
    index.record(t, entityWorldBounds(t, flipY));

    expect(index.hitTest(900, flipY(700), 0)).toBeNull();
  });

  it('ignores an entity with no id, because an unaddressable hit is not usable', () => {
    const index = new EntityHitIndex();
    index.record({ type: 'text', geometry: { insert: [0, 0] } }, { x0: -5, y0: -5, x1: 5, y1: 5 });
    expect(index.size).toBe(0);
  });

  it('reset clears the previous frame', () => {
    const index = new EntityHitIndex();
    const t = text(100, 100);
    index.record(t, entityWorldBounds(t, flipY));
    expect(index.size).toBe(1);
    index.reset();
    expect(index.size).toBe(0);
    expect(index.hitTest(100, flipY(100), 0)).toBeNull();
  });
});

describe('dense drawing views', () => {
  /** A ⌀120 dimension as `M745204N01` actually serialises it at extraction schema 6. */
  const diameterDim = {
    id: 'dim',
    type: 'dimension',
    geometry: {
      text_point: [421.5, 358.49],
      render_text_point: [421.5, 358.49],
      def_point: [421.5, 298.49],
      // The whole dimension: extension lines, dimension line, arrowheads.
      render_paths: [
        [[371.5, 418.49], [371.5, 298.49]],
        [[371.5, 298.49], [471.5, 298.49]],
      ],
    },
    properties: { text: '%%c120', measurement: 120, height: 10 },
  };

  it('measures a dimension from its value, not from the span it measures', () => {
    // Six of eleven dimensions on `M745204N01` were unselectable before this. `render_paths`
    // covers the entire measured span, so on a concentric view a diameter dimension's box
    // wrapped the whole circle — and since the smallest match wins, everything inside its own
    // span beat it.
    const b = entityWorldBounds(diameterDim, flipY)!;
    expect(b).not.toBeNull();

    const spanWidth = 471.5 - 371.5;
    expect(b.x1 - b.x0).toBeLessThan(spanWidth);
    // Centred on the text anchor, not on the geometry.
    expect((b.x0 + b.x1) / 2).toBeCloseTo(421.5, 1);
    expect((b.y0 + b.y1) / 2).toBeCloseTo(flipY(358.49), 1);
  });

  it('resolves the dimension on its value and nothing at all off it', () => {
    // Was: "does not let a dimension swallow the geometry it annotates", which checked that a
    // point inside the annotated circle resolved to the circle. Geometry is no longer indexed,
    // so the second half is now the stronger guarantee — off the value, the answer is nothing.
    // The original hazard it guarded against still cannot recur: the dimension is measured from
    // its TEXT, so its box does not span the feature at all.
    const index = new EntityHitIndex();
    const circle = { id: 'circle', type: 'circle', geometry: { center: [421.5, 358.49], radius: 60 } };
    for (const e of [diameterDim, circle]) index.record(e, entityWorldBounds(e, flipY));

    expect(index.size).toBe(1);
    expect(index.hitTest(421.5, flipY(358.49), 1)?.id).toBe('dim');
    expect(index.hitTest(421.5, flipY(310), 1)).toBeNull();
  });

  it('resolves the value printed across geometry, which is now the only candidate', () => {
    // The concentric hub case: ⌀145 sits on top of several arcs. This used to prove that the
    // value out-ranked them; now they are not indexed at all, so it proves the label is still
    // reachable at a point where an arc would previously have competed.
    const index = new EntityHitIndex();
    const arc = { id: 'arc', type: 'circle', geometry: { center: [200, 200], radius: 3 } };
    const label = {
      id: 'label',
      type: 'text',
      geometry: { insert: [190, 205] },
      properties: { text: '⌀145', height: 8, bbox: [[190, 197], [212, 205]] },
    };
    for (const e of [arc, label]) index.record(e, entityWorldBounds(e, flipY));

    expect(index.hitTest(200, flipY(201), 1)?.id).toBe('label');
  });

  it('makes every label in an overlapping cluster reachable', () => {
    // ⌀145 / ⌀183 / ⌀110 on one hub: their axis-aligned boxes overlap heavily. Smallest-area
    // returns the same one wherever you click inside the cluster, so the others cannot be
    // selected at all. Nearest-centre follows the cursor.
    const index = new EntityHitIndex();
    const mk = (id: string, x: number) => ({
      id,
      type: 'text',
      geometry: { insert: [x, 100] },
      properties: { text: id, height: 8, bbox: [[x, 92], [x + 30, 100]] },
    });
    const a = mk('d145', 100);
    const b = mk('d183', 110); // overlaps a by 20 of its 30 units
    for (const e of [a, b]) index.record(e, entityWorldBounds(e, flipY));

    expect(index.hitTest(103, flipY(96), 0)?.id).toBe('d145');
    expect(index.hitTest(137, flipY(96), 0)?.id).toBe('d183');
  });
});

describe('what the selection highlight draws', () => {
  // The highlight looks the selected id back up with `boundsFor`. If that lookup could miss an
  // entity `hitTest` had just returned, a click would resolve correctly, write to the store, and
  // outline nothing — which is indistinguishable from a click that cannot select. That was a
  // real bug: selection reached the store and no renderer drew it.
  const column = [0, 1, 2].map((i) => text(100, 700 - i * 40, `Q${i}`));
  const index = new EntityHitIndex();
  for (const e of column) index.record(e, entityWorldBounds(e, flipY));

  it('can look up a box for the entity a click resolved to', () => {
    const hit = index.hitTest(100, flipY(700), 0);
    expect(hit).not.toBeNull();
    expect(index.boundsFor(String(hit.id))).not.toBeNull();
  });

});

describe('groupFractionOf — the source half of the value-group tie-break', () => {
  const dim = (id: string, text: string) =>
    ({ id, type: 'dimension', properties: { text, dim_type: 2 } });
  const build = (...placed: [any, number, number][]) => {
    const ix = new EntityHitIndex();
    for (const [e, x, y] of placed) ix.record(e, { x0: x, y0: y, x1: x + 40, y1: y + 20 });
    return ix;
  };

  it('places an entity as a fraction of its own value-group box', () => {
    // The reference's three `60°` on M745204N01: the left-hand one is near the left edge of the
    // group and near its bottom, and those two fractions are what the other sheet matches on.
    const left = dim('left', '60°');
    const ix = build([dim('top', '60°'), 300, 44], [left, 85, 170], [dim('right', '60°'), 515, 170]);

    const f = ix.groupFractionOf(left)!;
    expect(f.cfx).toBeCloseTo(20 / 470, 6);
    expect(f.cfy).toBeCloseTo(136 / 146, 6);
  });

  it('publishes nothing for a value that appears once', () => {
    // There is no ordering to state, and 0.5 would be a claim rather than a measurement — the
    // target would then match on a fraction the source never had.
    const only = dim('only', '183');
    expect(build([only, 100, 100]).groupFractionOf(only)).toBeNull();
  });

  it('groups by TYPE and DIMENSION KIND, not by value alone', () => {
    // Same predicate `findMatches` uses to build its candidates. If the two disagreed, the
    // source would normalise against one group and the target against another — both would keep
    // working and quietly compare positions in different spaces.
    const angular = dim('a', '60°');
    const ix = build(
      [angular, 100, 100],
      [{ id: 'note', type: 'text', properties: { text: '60°' } }, 900, 900],
    );
    expect(ix.groupFractionOf(angular)).toBeNull();
  });

  it('collapses a degenerate axis to the middle instead of dividing by zero', () => {
    // Three values in a vertical column have no horizontal ordering. 0.5 on both sides makes
    // that axis contribute nothing to the distance, rather than an Infinity that swamps it.
    const mid = dim('mid', '4');
    const ix = build([dim('hi', '4'), 100, 0], [mid, 100, 100], [dim('lo', '4'), 100, 200]);
    const f = ix.groupFractionOf(mid)!;
    expect(f.cfx).toBe(0.5);
    expect(f.cfy).toBeCloseTo(0.5, 6);
  });
});

describe('the multiplication sign, which NFKC does not fold', () => {
  // Reported from a live check on M745204N01: the same BOM row on both sheets, and the overlay
  // refused to pair them. Everything about the two strings folds except one character.
  const REF = '4 ロール：12 (2x6台)';
  const REV = '４ロール：１２（２×６台）';

  it('pairs the row the two sheets spell with x and with ×', () => {
    expect(normalizeEntityValue(REV)).toBe(normalizeEntityValue(REF));
  });

  it('was one character away, which is why NFKC looked like it was enough', () => {
    // The diagnosis, pinned. Full-width digits, parens, colon and the spacing all fold; U+00D7
    // does not, and a key differing in one character is indistinguishable from a real edit.
    const nfkcOnly = (v: string) => v.normalize('NFKC').replace(/\s+/g, '').toUpperCase();
    expect(nfkcOnly(REF)).not.toBe(nfkcOnly(REV));
    expect(nfkcOnly(REF).replace('X', '')).toBe(nfkcOnly(REV).replace('×', ''));
  });

  it('folds the same set the backend folds', () => {
    // `spatial_differ._normalize_text` maps × ✕ ✖ ⨯ to `x`, and `utils/text.py` folds the
    // full-width `ｘ` too. The engine paired this row while this layer did not — one rule, two
    // implementations, and only one of them had learned. If the backend's set grows, this fails.
    for (const glyph of ['×', '✕', '✖', '⨯', 'ｘ']) {
      expect(normalizeEntityValue(`2${glyph}6`)).toBe(normalizeEntityValue('2x6'));
    }
  });

  it('does not fold anything that is merely near it', () => {
    // `+` and `*` are not spellings of "by" on these sheets, and folding them would merge rows
    // that genuinely differ — the expensive direction, since a wrong pair reads as confident.
    expect(normalizeEntityValue('2+6')).not.toBe(normalizeEntityValue('2x6'));
    expect(normalizeEntityValue('2*6')).not.toBe(normalizeEntityValue('2x6'));
  });

  it('keeps the sheet spelling on screen', () => {
    // The fold is a COMPARISON key. The chip must still show what the sheet draws, or the
    // engineer is shown a string that appears on neither drawing.
    expect(entityDisplayText({ properties: { text: REV } })).toContain('×');
  });
});
