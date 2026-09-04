import { describe, it, expect } from 'vitest';
import { findSectionCallouts, sectionCalloutsForLayers } from './sectionCallouts';

/**
 * The load-bearing property is NOT "hides `A`" — it is "hides the section callout and keeps the
 * frame's grid labels", which are the same string. Every test below that passes trivially when
 * the rule is `text === 'A'` is marked as such.
 */

/** Model-space text, i.e. projected onto the sheet through viewport `vp`. */
const viewText = (text: string, vp = 0) => ({
  type: 'text',
  geometry: { text },
  properties: { viewport_index: vp },
});

/** Native paper-space text — the frame, title block, tolerance table. Never projected. */
const sheetText = (text: string) => ({
  type: 'text',
  geometry: { text },
  properties: { viewport_index: -1 },
});

describe('findSectionCallouts', () => {
  it('hides the Ａ－Ａ designation and the lone Ａ at the cut arrow', () => {
    const designation = viewText('Ａ－Ａ', 1);
    const arrow = viewText('Ａ', 0);
    const found = findSectionCallouts([designation, arrow]);

    expect(found.has(designation)).toBe(true);
    expect(found.has(arrow)).toBe(true);
    expect(found.size).toBe(2);
  });

  it("keeps the sheet frame's grid labels, which are the same letter", () => {
    // The regression this rule exists to avoid. M745221N01's revision carries `Ａ` grid labels at
    // both sheet edges AND an `Ａ－Ａ` section, so text alone cannot separate them.
    const designation = viewText('Ａ－Ａ', 1);
    const arrow = viewText('Ａ', 0);
    const gridLeft = sheetText('A');
    const gridRight = sheetText('A');

    const found = findSectionCallouts([designation, arrow, gridLeft, gridRight]);

    expect(found.has(arrow)).toBe(true);
    expect(found.has(gridLeft)).toBe(false);
    expect(found.has(gridRight)).toBe(false);
  });

  it('keeps every lone letter on a sheet that has no section designation', () => {
    // A drawing with no section view: nothing qualifies, so a balloon or a part label survives.
    const found = findSectionCallouts([viewText('A'), viewText('B'), sheetText('A')]);
    expect(found.size).toBe(0);
  });

  it('does not sweep up a lone letter that no designation names', () => {
    const designation = viewText('Ａ－Ａ');
    const unrelated = viewText('Ｂ');
    const found = findSectionCallouts([designation, unrelated]);

    expect(found.has(designation)).toBe(true);
    expect(found.has(unrelated)).toBe(false);
  });

  it('will not let paper-space text license hiding a grid label', () => {
    // A title-block string that happens to read `A-A` must not qualify the border grid's `A`.
    // Both gates are needed: this passes only because the designation scan is viewport-scoped too.
    const titleBlockish = sheetText('A-A');
    const gridLabel = sheetText('A');
    const found = findSectionCallouts([titleBlockish, gridLabel]);

    expect(found.size).toBe(0);
  });

  it('accepts the dash variants the corpus actually uses', () => {
    for (const dash of ['-', '‐', '–', '—', 'ー', '－']) {
      const designation = viewText(`A${dash}A`);
      expect(findSectionCallouts([designation]).has(designation)).toBe(true);
    }
  });

  it('rejects a two-letter pair that is not the same letter', () => {
    // `A-B` is a dimension, a note or a range — never a section designation.
    const notASection = viewText('A-B');
    expect(findSectionCallouts([notASection]).size).toBe(0);
  });

  it('ignores non-text entities carrying a matching string', () => {
    const designation = viewText('Ａ－Ａ');
    const line = { type: 'line', geometry: { text: 'A' }, properties: { viewport_index: 0 } };
    const found = findSectionCallouts([designation, line]);
    expect(found.has(line)).toBe(false);
  });

  it('applies the caller-supplied text cleaner before matching', () => {
    // MTEXT formatting codes reach the renderer raw; `renderEntities` passes `cleanCadText`.
    const designation = { type: 'text', geometry: { text: '{\\fArial;Ａ－Ａ}' }, properties: { viewport_index: 0 } };
    const strip = (t: string) => t.replace(/[{}]/g, '').replace(/\\[A-Za-z][^;]*;/g, '');

    expect(findSectionCallouts([designation]).size).toBe(0);
    expect(findSectionCallouts([designation], strip).has(designation)).toBe(true);
  });

  it('reads text from the same fields, in the same order, as the renderer', () => {
    const viaContent = { type: 'text', geometry: { content: 'Ａ－Ａ' }, properties: { viewport_index: 0 } };
    const viaProps = { type: 'text', geometry: {}, properties: { text: 'Ａ', viewport_index: 0 } };
    const found = findSectionCallouts([viaContent, viaProps]);

    expect(found.has(viaContent)).toBe(true);
    expect(found.has(viaProps)).toBe(true);
  });

  it('treats a missing viewport_index as paper space, not as eligible', () => {
    // Payloads ingested before the projector stamped the field must fail closed: the label is
    // drawn, which is exactly today's behaviour, rather than a grid label silently vanishing.
    const stale = { type: 'text', geometry: { text: 'Ａ' }, properties: {} };
    const designation = { type: 'text', geometry: { text: 'Ａ－Ａ' }, properties: {} };
    expect(findSectionCallouts([stale, designation]).size).toBe(0);
  });
});

/**
 * Cut plane + arrows. Geometry below is M745221N01's revision in projected paper units, straight
 * from the serialized payload — the bent cut path (184.3,100.3)→(184.3,157.3)→(139.7,234.6) in
 * colour 8, against six colour-4 centrelines that must survive.
 */
const centreLine = (start: number[], end: number[], color: number) => ({
  type: 'line',
  geometry: { start, end },
  properties: { linetype: 'CENTER', color, viewport_index: 0 },
});

const stub = (type: string, vertices: number[][], color = 2) => ({
  type,
  geometry: { vertices },
  properties: { color, viewport_index: 0 },
});

const cutA = centreLine([184.3, 100.3], [184.3, 157.3], 8);
const cutB = centreLine([184.3, 157.3], [139.7, 234.6], 8);
const axisVertical = centreLine([184.3, 94.8], [184.3, 219.8], 4);
const axisHorizontal = centreLine([121.8, 157.3], [191.3, 157.3], 4);
const boltMark = centreLine([164.7, 123.3], [159.3, 114.0], 4);
const sectionViewAxis = centreLine([244.4, 157.3], [270.1, 157.3], 4);

const realSheet = () => [
  viewText('Ａ－Ａ', 1),
  viewText('Ａ', 0),
  cutA,
  cutB,
  axisVertical,
  axisHorizontal,
  boltMark,
  sectionViewAxis,
  centreLine([159.3, 200.6], [164.7, 191.3], 4),
  centreLine([252.9, 202.0], [261.5, 202.0], 4),
];

describe('findSectionCallouts — cut plane and arrows', () => {
  it('hides the bent cut path and keeps every axis centreline', () => {
    const found = findSectionCallouts(realSheet());

    expect(found.has(cutA)).toBe(true);
    expect(found.has(cutB)).toBe(true);
    for (const keep of [axisVertical, axisHorizontal, boltMark, sectionViewAxis]) {
      expect(found.has(keep)).toBe(false);
    }
  });

  it('hides arrow ticks by their midpoint and label tails by their endpoint', () => {
    // Real geometry: the tick straddles the cut end (midpoint 0.05 away), the leader starts on it.
    const tick = stub('polyline', [[184.3, 101.4], [184.3, 99.1]]);
    const bendTick = stub('polyline', [[184.3, 156.1], [184.3, 157.3], [183.7, 158.4]]);
    const tail = stub('leader', [[184.6, 100.3], [187.6, 100.3]]);
    const found = findSectionCallouts([...realSheet(), tick, bendTick, tail]);

    expect(found.has(tick)).toBe(true);
    expect(found.has(bendTick)).toBe(true);
    expect(found.has(tail)).toBe(true);
  });

  it('keeps a leader that merely points somewhere else', () => {
    // The `6-9キリ` callout leader: 46.9 units from the nearest cut vertex. The regression that
    // matters — culling this would erase a real engineering annotation.
    const kiriLeader = stub('leader', [[137.4, 155.0], [128.0, 142.2], [125.0, 142.2]], 3);
    const found = findSectionCallouts([...realSheet(), kiriLeader]);
    expect(found.has(kiriLeader)).toBe(false);
  });

  it('keeps the finish symbol in the section view', () => {
    const finishSymbol = stub('polyline', [[240.6, 125.9], [243.1, 121.6], [245.6, 125.9]], 0);
    const found = findSectionCallouts([...realSheet(), finishSymbol]);
    expect(found.has(finishSymbol)).toBe(false);
  });

  it('hides nothing when the sheet carries no section designation', () => {
    // Same geometry, no `X-X`. Every centreline survives — the gate is the whole safety story.
    const found = findSectionCallouts([viewText('Ａ'), cutA, cutB, axisVertical, axisHorizontal]);
    expect(found.size).toBe(0);
  });

  it('hides no centreline when they are all one colour', () => {
    // No minority means no cut plane can be identified. Fail safe rather than guess.
    const uniform = [
      viewText('Ａ－Ａ'),
      centreLine([184.3, 100.3], [184.3, 157.3], 4),
      centreLine([184.3, 94.8], [184.3, 219.8], 4),
    ];
    const found = findSectionCallouts(uniform);
    expect(found.size).toBe(1); // the designation label only
  });

  it('hides no centreline when the colours tie', () => {
    const tied = [
      viewText('Ａ－Ａ'),
      centreLine([0, 0], [0, 10], 8),
      centreLine([1, 0], [1, 10], 4),
    ];
    expect(findSectionCallouts(tied).size).toBe(1);
  });

  it('ignores paper-space centrelines when picking the majority colour', () => {
    // Sheet furniture must not vote. A frame line in the minority colour would otherwise flip
    // which colour reads as the cut plane.
    const paperCentre = {
      type: 'line',
      geometry: { start: [0, 0], end: [0, 5] },
      properties: { linetype: 'CENTER', color: 8, viewport_index: -1 },
    };
    const found = findSectionCallouts([...realSheet(), paperCentre]);
    expect(found.has(paperCentre)).toBe(false);
    expect(found.has(cutA)).toBe(true);
  });

  it('does not swallow a long polyline that merely starts on the cut path', () => {
    const longRun = stub('polyline', [
      [184.3, 100.3], [200, 100], [220, 100], [240, 100], [260, 100],
    ]);
    const found = findSectionCallouts([...realSheet(), longRun]);
    expect(found.has(longRun)).toBe(false);
  });
});

describe('sectionCalloutsForLayers', () => {
  it('finds callouts across separate layer groups', () => {
    const designation = viewText('Ａ－Ａ', 1);
    const arrow = viewText('Ａ', 0);
    const found = sectionCalloutsForLayers({ NoLayerName_001: [designation], WAKU: [arrow] });

    expect(found.has(designation)).toBe(true);
    expect(found.has(arrow)).toBe(true);
  });

  it('returns the same set object for a repeated payload', () => {
    // renderEntities reruns on every pan and zoom; the scan must not.
    const layers = { L: [viewText('Ａ－Ａ'), viewText('Ａ')] };
    expect(sectionCalloutsForLayers(layers)).toBe(sectionCalloutsForLayers(layers));
  });

  it('handles a null or empty payload', () => {
    expect(sectionCalloutsForLayers(null).size).toBe(0);
    expect(sectionCalloutsForLayers({}).size).toBe(0);
  });
});
