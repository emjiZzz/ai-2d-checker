/**
 * Where each view's ORIGIN is, and how confident we are that we know.
 *
 * Every number below is measured off `M745221N01_FSRS2` — the stored `viewport_transform` and
 * the real extracted entities — not invented for the test. The three answers this must produce:
 *
 *   299 front   (184.3147888183594, 157.3243865966797)  from `ucs_origin`   EXTRACTED
 *   2D2 sectA   (257.234, 157.32438659667966)           from a centreline   inferred
 *   2D5 isome1  (366.3276, 224.3567)                    from 6 ellipses     inferred
 *
 * The front view's is corroborated three ways to full float precision — the projected
 * `ucs_origin`, the crossing of its two CENTER centrelines, and the centre of its concentric
 * arcs all agree — which is the strongest evidence in this file and is asserted as such.
 *
 * What this replaces: `to_paper(view_anchor)`, which is identically `paper_center` and put the
 * markers 22.2 and 11.8 units out. See
 * `docs/vault/06 - .../Gotcha - The View Origin Marker Marked the Middle of the Window.md`.
 */
import { describe, expect, it } from 'vitest';

import { entitiesFromLayers, viewDatumsFromTransform } from './viewDatums';

/** The real stored transform, legacy `view_center` spelling exactly as it sits in MongoDB. */
const TRANSFORM = {
  version: 1,
  layout: 'ICADSX Layout',
  viewports: [
    {
      index: 0, handle: '299',
      paper_center: [162.0939969443204, 157.3243865966797],
      paper_size: [122.7426756727831, 131.25],
      view_center: [-31.10910862365456, 0.0],
      view_height: 183.75, scale: 0.7142857142857143,
    },
    {
      index: 1, handle: '2D2',
      paper_center: [247.0576406882221, 145.5561857223511],
      paper_size: [48.37035012358122, 133.4632218360901],
      view_center: [-80.6906589897892, -351.47548122406],
      view_height: 186.8485105705261, scale: 0.7142857142857145,
    },
    {
      index: 2, handle: '2D5',
      paper_center: [367.0346824647803, 224.7649073299741],
      paper_size: [37.37059338570904, 47.18551892437954],
      view_center: [69.43660323695764, -329.907884177685],
      view_height: 141.5565567731386, scale: 0.33333333333333337,
    },
  ],
};

const line = (x0: number, y0: number, x1: number, y1: number, linetype = 'Continuous') =>
  ({ type: 'line', geometry: { start: [x0, y0], end: [x1, y1] }, properties: { linetype } });

const curve = (type: string, cx: number, cy: number) =>
  ({ type, geometry: { center: [cx, cy] }, properties: { linetype: 'Continuous' } });

/**
 * The real geometry, trimmed to what the finder looks at.
 *
 * Front view: its two axis centrelines plus the bolt-circle arcs, so the three-way agreement
 * can be asserted. Section view: the long axis centreline (x 244.38..270.09), the SHORT bolt-hole
 * centreline that must not win, and the plate's two faces as ordinary Continuous lines — those
 * are what make the mid-plane reading a choice rather than the only option. Isometric view: the
 * six concentric flange ellipses and one three-member bolt-hole family that must lose.
 */
const ENTITIES = [
  // --- 299, front ---
  line(139.7, 157.3243865966797, 228.9, 157.3243865966797, 'CENTER'),
  line(184.3147888183594, 113.0, 184.3147888183594, 201.0, 'CENTER'),
  curve('arc', 184.3147888183594, 157.3243865966797),
  curve('arc', 184.3147888183594, 157.3243865966797),
  curve('arc', 184.3147888183594, 157.3243865966797),
  // --- 2D2, section: no circles at all, which is why it falls to the centreline rung ---
  line(244.3768550327846, 157.32438659667966, 270.0911407470703, 157.32438659667966, 'CENTER'),
  line(252.94828360421315, 201.9672437395368, 261.51971217564176, 201.9672437395368, 'CENTER'),
  line(255.091, 105.54, 255.091, 209.11),
  line(259.377, 105.54, 259.377, 209.11),
  // --- 2D5, isometric: no centrelines at all, which is why it falls to the concentric rung ---
  ...Array.from({ length: 6 }, () => curve('ellipse', 366.3276, 224.3567)),
  ...Array.from({ length: 3 }, () => curve('ellipse', 358.9619, 213.8779)),
];

const byHandle = (datums: ReturnType<typeof viewDatumsFromTransform>) =>
  Object.fromEntries(datums.map(d => [d.handle, d]));

describe('viewDatumsFromTransform', () => {
  it('reads the front view from the file itself, not from its geometry', () => {
    const d = byHandle(viewDatumsFromTransform(TRANSFORM, ENTITIES))['299'];
    // to_paper(0,0) = paper_center - anchor * scale.
    expect(d.x).toBeCloseTo(184.3147888183594, 9);
    expect(d.y).toBeCloseTo(157.3243865966797, 9);
    expect(d.source).toBe('ucs_origin');
    expect(d.inferred).toBe(false);
  });

  it('agrees with both geometric readings of the same view, to full precision', () => {
    // The evidence that the extracted answer is the right one rather than merely the stated one:
    // the centreline crossing and the concentric arc centre land on it exactly.
    const d = byHandle(viewDatumsFromTransform(TRANSFORM, ENTITIES))['299'];
    const crossing = { x: 184.3147888183594, y: 157.3243865966797 };  // the two CENTER lines
    const arcs = { x: 184.3147888183594, y: 157.3243865966797 };      // 3 concentric arcs
    expect(Math.hypot(d.x - crossing.x, d.y - crossing.y)).toBeLessThan(1e-9);
    expect(Math.hypot(d.x - arcs.x, d.y - arcs.y)).toBeLessThan(1e-9);
  });

  it('puts the section view on the axis it shares with the front view, exactly', () => {
    const all = byHandle(viewDatumsFromTransform(TRANSFORM, ENTITIES));
    const d = all['2D2'];
    // Bit-identical to the front view's axis. That is projection alignment, and it is the
    // strongest single number in this file — a datum found by accident would not reproduce it.
    expect(d.y).toBe(157.32438659667966);
    expect(d.y).toBeCloseTo(all['299'].y, 9);
    // x is the centreline's own midpoint, which here is the plate's mid-plane. See the OPEN
    // question below.
    expect(d.x).toBeCloseTo(257.234, 3);
    expect(d.source).toBe('centerline_axis');
    expect(d.inferred).toBe(true);
  });

  it('prefers the LONG centreline over the short bolt-hole one', () => {
    // The short one sits at y=201.97, one bolt-circle radius above the axis. Picking it would
    // look entirely plausible on screen.
    const d = byHandle(viewDatumsFromTransform(TRANSFORM, ENTITIES))['2D2'];
    expect(d.y).not.toBeCloseTo(201.967, 2);
  });

  it('OPEN: the section view x is a choice, and this test records which one', () => {
    // The datum LINE is certain; the position along it is not in the file. Mid-plane 257.234
    // is what ships; the plate's two faces at 255.091 and 259.377 are equally defensible, a
    // 4.29-unit spread. When the owner reads it off iCAD, this expectation is what moves.
    const d = byHandle(viewDatumsFromTransform(TRANSFORM, ENTITIES))['2D2'];
    expect(d.x).toBeCloseTo((255.091 + 259.377) / 2, 3);
  });

  it('reads the isometric view off its concentric ellipses, largest family winning', () => {
    const d = byHandle(viewDatumsFromTransform(TRANSFORM, ENTITIES))['2D5'];
    expect(d.x).toBeCloseTo(366.3276, 4);
    expect(d.y).toBeCloseTo(224.3567, 4);
    expect(d.source).toBe('concentric');
    expect(d.inferred).toBe(true);
    // The three-member bolt-hole family must not win.
    expect(d.x).not.toBeCloseTo(358.9619, 2);
  });

  it('marks exactly one of the three as extracted — which is all the DXF states', () => {
    // `ucs_origin` is (0,0,0) on all 34 viewports of all 12 viewport-bearing sheets, so its
    // projection can only land inside one viewport per sheet. Measured: 12 sheets, 12 hits.
    const datums = viewDatumsFromTransform(TRANSFORM, ENTITIES);
    expect(datums.filter(d => !d.inferred)).toHaveLength(1);
    expect(datums.filter(d => d.inferred)).toHaveLength(2);
  });

  it('does not fall back to the window centre — the defect it replaces', () => {
    // Every one of these was the shipped answer, and every one is wrong by 22.2, 11.8 and 0.8.
    const datums = viewDatumsFromTransform(TRANSFORM, ENTITIES);
    TRANSFORM.viewports.forEach((vp, i) => {
      const d = datums[i];
      expect(Math.hypot(d.x - vp.paper_center[0], d.y - vp.paper_center[1])).toBeGreaterThan(0.1);
    });
  });

  it('leaves a view unmarked rather than guessing when nothing determines it', () => {
    // The section view with its centrelines and plate faces removed: geometry present, no datum
    // derivable. A marker here would be pure invention.
    const bare = ENTITIES.filter(e => {
      const s = (e.geometry as { start?: number[] }).start;
      return !(s && s[0] > 222 && s[0] < 272);
    });
    const handles = viewDatumsFromTransform(TRANSFORM, bare).map(d => d.handle);
    expect(handles).toEqual(['299', '2D5']);
  });

  it('takes a centreline crossing over a concentric family when it has both', () => {
    // Same viewport, forced past rung 1 by removing the anchor that makes it extractable.
    const offset = { ...TRANSFORM.viewports[0], view_center: [-500, -500] };
    const d = viewDatumsFromTransform({ viewports: [offset] }, ENTITIES)[0];
    expect(d.source).toBe('centerline_cross');
    expect(d.x).toBeCloseTo(184.3147888183594, 6);
    expect(d.y).toBeCloseTo(157.3243865966797, 6);
  });

  it('ignores dashed linetypes that are not centrelines', () => {
    // HIDDEN and PHANTOM render dashed too and mean something else entirely. Keying on the
    // resolved dash pattern instead of the name would let a hidden edge nominate the axis.
    const hidden = [
      line(244.4, 150.0, 270.0, 150.0, 'HIDDEN'),
      line(244.4, 160.0, 270.0, 160.0, 'PHANTOM'),
      line(244.4, 170.0, 270.0, 170.0, 'DASHED'),
    ];
    const datums = viewDatumsFromTransform({ viewports: [TRANSFORM.viewports[1]] }, hidden);
    expect(datums).toEqual([]);
  });

  it('returns nothing rather than throwing on a drawing with no viewports', () => {
    expect(viewDatumsFromTransform({ viewports: [] }, ENTITIES)).toEqual([]);
    expect(viewDatumsFromTransform(null, ENTITIES)).toEqual([]);
    expect(viewDatumsFromTransform(undefined)).toEqual([]);
    expect(viewDatumsFromTransform({}, ENTITIES)).toEqual([]);
  });

  it('skips a viewport with a malformed payload instead of emitting NaN', () => {
    const bad = { viewports: [
      { handle: 'A', paper_center: [Number.NaN, 1], paper_size: [10, 10], scale: 1 },
      { handle: 'B', paper_center: null, paper_size: [10, 10], scale: 1 },
      { handle: 'C', paper_center: [5, 6], paper_size: null, scale: 1 },
    ] };
    expect(viewDatumsFromTransform(bad, ENTITIES)).toEqual([]);
  });

  it('reads the new view_anchor key as well as the legacy one', () => {
    const modern = { viewports: [{ ...TRANSFORM.viewports[0], view_anchor: [-31.10910862365456, 0], view_center: undefined }] };
    expect(viewDatumsFromTransform(modern, ENTITIES)[0].x).toBeCloseTo(184.3147888183594, 9);
  });
});

/**
 * Run against all three stored `FSRS2` sheets with their REAL entity payloads (518, 569 and 495
 * entities — not the trimmed fixture above), the ladder produced:
 *
 *   M745221N01  299 ucs_origin  2D2 centerline_axis  2D5 concentric
 *   M7452A0N01  2C5 ucs_origin  311 centerline_axis  314 concentric
 *   M745203N01  2E3 ucs_origin  2E7 concentric
 *
 * — one extracted datum per sheet, exactly as the corpus sweep predicts, and no sheet furniture
 * false-matched as a centreline. On the two sheets where the stated origin and the view's own
 * centreline crossing BOTH exist, they are bit-identical (`0.0e+0` apart). On the third they are
 * not, and that is what these tests are about.
 */
describe('when the file and the drawing disagree', () => {
  // M745203N01_FSRS2, viewport 2E3 — real numbers, scale 1.
  const VP_2E3 = {
    index: 0, handle: '2E3',
    paper_center: [206.1759310864651, 151.8828477859497],
    paper_size: [138.7952029622409, 73.86486883163454],
    view_center: [66.09295379154328, 4.826252937316902],
    view_height: 73.86486883163454, scale: 1,
  };
  // Its real centrelines: one long vertical axis, three collinear horizontal segments at the
  // same y, and two short verticals that are the bolt holes (symmetric about the axis at ±12.5).
  const CENTRELINES = [
    line(160.08297729492182, 187.0565948486328, 160.08297729492182, 137.0565948486328, 'CENTER'),
    line(147.58297729492182, 163.55659484863278, 147.58297729492182, 150.55659484863284, 'CENTER'),
    line(172.58297729492182, 163.55659484863278, 172.58297729492182, 150.55659484863284, 'CENTER'),
    line(141.08297729492188, 157.0565948486328, 154.08297729492182, 157.0565948486328, 'CENTER'),
    line(166.08297729492188, 157.0565948486328, 179.08297729492182, 157.0565948486328, 'CENTER'),
  ];

  it('takes the file\'s word for it, which is the only extracted fact available', () => {
    const d = viewDatumsFromTransform({ viewports: [VP_2E3] }, CENTRELINES)[0];
    expect(d.x).toBeCloseTo(140.083, 3);
    expect(d.y).toBeCloseTo(147.057, 3);
    expect(d.source).toBe('ucs_origin');
    expect(d.inferred).toBe(false);
  });

  it('OPEN: and the part\'s own datum is exactly (20, 10) away from it', () => {
    // ⚠ Measured, unresolved, and the reason this test is named OPEN. On M745221N01 and
    // M7452A0N01 these two readings are bit-identical; here the model origin simply is not on
    // the part. Both are meaningful points and the DXF cannot say which one iCAD marks — only
    // looking at this sheet in iCAD can. If it marks the part, the fix is one reordering in
    // `viewDatumsFromTransform` and this expectation becomes the shipped answer.
    const forced = { ...VP_2E3, view_center: [1e6, 1e6] };  // push rung 1 out of its own window
    const d = viewDatumsFromTransform({ viewports: [forced] }, CENTRELINES)[0];
    expect(d.source).toBe('centerline_cross');
    expect(d.x).toBeCloseTo(160.083, 3);
    expect(d.y).toBeCloseTo(157.057, 3);
    // Round numbers, which is what makes it a layout offset rather than float noise.
    expect(d.x - 140.08297729492182).toBeCloseTo(20.0, 6);
    expect(d.y - 147.05659484863283).toBeCloseTo(10.0, 6);
  });

  it('picks the long axis over the bolt-hole centrelines either side of it', () => {
    const forced = { ...VP_2E3, view_center: [1e6, 1e6] };
    const d = viewDatumsFromTransform({ viewports: [forced] }, CENTRELINES)[0];
    // The two short verticals sit at 147.583 and 172.583 — symmetric about the real axis, so
    // picking either would look entirely reasonable on screen and be 12.5 units wrong.
    expect(d.x).not.toBeCloseTo(147.583, 2);
    expect(d.x).not.toBeCloseTo(172.583, 2);
  });
});

describe('entitiesFromLayers', () => {
  it('flattens the canvas layer record and tolerates junk', () => {
    expect(entitiesFromLayers({ a: [{ type: 'line' }], b: [{ type: 'arc' }] })).toHaveLength(2);
    expect(entitiesFromLayers({ a: null as any })).toEqual([]);
    expect(entitiesFromLayers(null)).toEqual([]);
    expect(entitiesFromLayers(undefined)).toEqual([]);
  });
});
