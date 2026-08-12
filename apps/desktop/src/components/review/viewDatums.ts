/**
 * viewDatums.ts
 *
 * Where each view's own ORIGIN sits on the sheet — the point iCAD SX marks, and the point a
 * drafter dimensions from.
 *
 * ## Why this is not a one-liner off the transform
 *
 * The obvious reading is `to_paper(view_anchor)`, and it is a **tautology**: the anchor is
 * defined as the model point that lands at the viewport's window centre, so projecting it back
 * returns the window centre and nothing else. That shipped, and it put markers 22.2 and 11.8
 * units from the real datum on two of `M745221N01_FSRS2`'s three views — see
 * `docs/vault/06 - .../Gotcha - The View Origin Marker Marked the Middle of the Window.md`.
 *
 * The file states exactly one origin per sheet. Measured across the whole corpus: `ucs_origin`
 * is `(0,0,0)` on **all 34 viewports of all 12** viewport-bearing sheets, `view_direction_vector`
 * is `(0,0,1)` and `view_twist_angle` is `0.0` everywhere — and the projected WCS origin lands
 * inside **exactly one viewport per sheet, 12 sheets, 12 hits, never two**. iCAD knows the other
 * views' origins from the 3D model; the DXF export dropped them along with the UCS.
 *
 * So one view's datum is EXTRACTED and the rest are INFERRED from the view's own geometry. That
 * distinction is carried on every result as `inferred`, and the overlay draws inferred markers
 * dashed — the same idiom `renderZoneEditor` already uses for a zone the detector never anchored,
 * so a guess is never mistaken for a measurement.
 *
 * ## The ladder, strongest evidence first
 *
 *  1. `ucs_origin` projected — `to_paper(0, 0)` — when it lands inside the viewport's own
 *     rectangle. This is the file speaking. On M745221N01_FSRS2's front view it agrees with
 *     both geometric readings below to full float precision.
 *  2. The crossing of the view's own `CENTER`-linetype centrelines: one horizontal, one
 *     vertical. This is the drafter's datum, drawn on the sheet.
 *  3. The centre of the largest family of concentric circles/arcs/ellipses. A bolt circle or a
 *     flange ring is centred on the part axis by construction, so it fixes BOTH coordinates —
 *     which is why it outranks rung 4. This is what carries the isometric view, which has no
 *     centrelines at all.
 *  4. A single centreline: the axis is certain, the position ALONG it is not. Takes the
 *     centreline's own midpoint, which is symmetric about the part because that is how
 *     centrelines are drawn. **This is the weakest rung and the one open question in the note**
 *     — on the section view it puts the marker on the plate's mid-plane (257.234) when the two
 *     faces (255.091 / 259.377) are equally defensible, a 4.29-unit spread. One constant to
 *     change once it is read off iCAD.
 *
 * A view matching none of these gets **no marker**. Falling back to the window centre is exactly
 * the defect this module replaces: a marker that is always present and sometimes lying is worse
 * than one that is absent.
 */

export interface ViewportPayload {
  index?: number;
  handle?: string;
  paper_center: [number, number];
  paper_size: [number, number];
  /** MODEL point that lands at `paper_center`. `view_center` is the pre-2026-08-11 key. */
  view_anchor?: [number, number];
  view_center?: [number, number];
  scale: number;
}

/** Which rung of the ladder produced the point. `ucs_origin` is the only extracted one. */
export type DatumSource = 'ucs_origin' | 'centerline_cross' | 'centerline_axis' | 'concentric';

export interface ViewDatum {
  x: number;
  y: number;
  handle: string;
  scale: number;
  source: DatumSource;
  /** False only for `ucs_origin`: everything else is read off the drawn geometry. */
  inferred: boolean;
}

/** Minimal shape of a canvas entity — `geometry` and `properties` arrive from the API verbatim. */
interface CanvasEntity {
  type?: string;
  geometry?: any;
  properties?: any;
}

interface Rect { x0: number; y0: number; x1: number; y1: number }

/** A line is axis-aligned if it deviates by less than this many drawing units end to end. */
const AXIS_EPSILON = 0.01;
/** Concentric centres closer than this are the same axis. Bolt holes on this corpus sit ~7 apart. */
const CONCENTRIC_TOLERANCE = 0.05;

const isFinitePair = (p: any): p is [number, number] =>
  Array.isArray(p) && p.length >= 2 && Number.isFinite(p[0]) && Number.isFinite(p[1]);

const rectOf = (vp: ViewportPayload): Rect | null => {
  if (!isFinitePair(vp?.paper_center) || !isFinitePair(vp?.paper_size)) return null;
  const [cx, cy] = vp.paper_center;
  const [w, h] = vp.paper_size;
  return { x0: cx - w / 2, y0: cy - h / 2, x1: cx + w / 2, y1: cy + h / 2 };
};

const contains = (r: Rect, x: number, y: number) =>
  x >= r.x0 && x <= r.x1 && y >= r.y0 && y <= r.y1;

/**
 * `CENTER` in the linetype name, not merely "this renders dashed".
 *
 * `HIDDEN` and `PHANTOM` are dashed too and mean something else entirely, so keying on the
 * resolved dash pattern would let a hidden edge nominate itself as the part's axis. A
 * `BYLAYER` entity whose layer carries CENTER is missed by this and falls through to the
 * concentric rung — the safe direction.
 */
const isCenterLine = (e: CanvasEntity): boolean =>
  String(e?.properties?.linetype ?? '').toUpperCase().includes('CENTER');

interface Segment { x0: number; y0: number; x1: number; y1: number; length: number }

const segmentOf = (e: CanvasEntity): Segment | null => {
  const s = e?.geometry?.start;
  const t = e?.geometry?.end;
  if (!isFinitePair(s) || !isFinitePair(t)) return null;
  return { x0: s[0], y0: s[1], x1: t[0], y1: t[1], length: Math.hypot(t[0] - s[0], t[1] - s[1]) };
};

const longest = (segments: Segment[]): Segment | null =>
  segments.reduce<Segment | null>((best, s) => (best && best.length >= s.length ? best : s), null);

/**
 * Model point (0,0) projected onto the sheet through this viewport.
 *
 * `to_paper(x, y) = paper_center + (x - anchor) * scale`, mirroring `Viewport.to_paper` in
 * `viewport_transform.py`. Only `(0,0)` is asked for here because that is what `ucs_origin`
 * is on every sheet in the corpus.
 */
const projectedModelOrigin = (vp: ViewportPayload): { x: number; y: number } | null => {
  const anchor = isFinitePair(vp?.view_anchor)
    ? vp.view_anchor
    : isFinitePair(vp?.view_center)
      ? vp.view_center
      : [0, 0];
  const scale = Number(vp?.scale);
  if (!isFinitePair(vp?.paper_center) || !Number.isFinite(scale)) return null;
  return {
    x: vp.paper_center[0] - anchor[0] * scale,
    y: vp.paper_center[1] - anchor[1] * scale,
  };
};

/** The centre of the largest set of curves sharing an axis, or null if nothing is concentric. */
const concentricAxis = (entities: CanvasEntity[], rect: Rect): { x: number; y: number; count: number } | null => {
  const buckets = new Map<string, { x: number; y: number; count: number }>();
  for (const e of entities) {
    const t = String(e?.type ?? '').toLowerCase();
    if (t !== 'circle' && t !== 'arc' && t !== 'ellipse') continue;
    const c = e?.geometry?.center ?? e?.geometry?.location;
    if (!isFinitePair(c) || !contains(rect, c[0], c[1])) continue;
    const key = `${Math.round(c[0] / CONCENTRIC_TOLERANCE)}:${Math.round(c[1] / CONCENTRIC_TOLERANCE)}`;
    const hit = buckets.get(key);
    if (hit) hit.count += 1;
    else buckets.set(key, { x: c[0], y: c[1], count: 1 });
  }
  let best: { x: number; y: number; count: number } | null = null;
  for (const b of buckets.values()) {
    // Ties keep the first seen rather than flipping on map order — a stable marker matters more
    // than picking between two families that are equally concentric.
    if (b.count >= 2 && (!best || b.count > best.count)) best = b;
  }
  return best;
};

/**
 * One datum per viewport that has one. Views with no determinable datum are omitted entirely,
 * so the returned array is NOT index-aligned with `transform.viewports`.
 *
 * @param transform - `drawing.metadata.viewport_transform`, or anything falsy.
 * @param entities  - every canvas entity, in paper coordinates. Assigned to viewports by
 *                    containment rather than by `viewport_index`, which the client payload does
 *                    not carry.
 */
export const viewDatumsFromTransform = (
  transform: any,
  entities: CanvasEntity[] = [],
): ViewDatum[] => {
  const viewports: ViewportPayload[] = transform?.viewports;
  if (!Array.isArray(viewports)) return [];

  return viewports.flatMap((vp) => {
    const rect = rectOf(vp);
    if (!rect) return [];
    const handle = String(vp?.handle ?? '');
    const scale = Number(vp?.scale) || 1;
    const emit = (x: number, y: number, source: DatumSource): ViewDatum[] =>
      Number.isFinite(x) && Number.isFinite(y)
        ? [{ x, y, handle, scale, source, inferred: source !== 'ucs_origin' }]
        : [];

    // 1. The file's own statement, when this is the view it applies to.
    const stated = projectedModelOrigin(vp);
    if (stated && contains(rect, stated.x, stated.y)) {
      return emit(stated.x, stated.y, 'ucs_origin');
    }

    // Assigned by MIDPOINT, not by "both endpoints inside". A centreline is drawn overhanging
    // the feature it marks, and the projector gives every entity its full extent regardless of
    // where the viewport clips it — so demanding containment of both ends silently discards the
    // longest centrelines, which are exactly the ones that mark the axis. Centroid scoping is
    // also what the backend does (`_entity_points`), for the same reason.
    const inThisView = entities.filter((e) => {
      const seg = segmentOf(e);
      if (seg) return contains(rect, (seg.x0 + seg.x1) / 2, (seg.y0 + seg.y1) / 2);
      const c = e?.geometry?.center ?? e?.geometry?.location;
      return isFinitePair(c) && contains(rect, c[0], c[1]);
    });

    // 2 & 3. The drafter's own centrelines.
    const centreSegments = inThisView
      .filter((e) => String(e?.type ?? '').toLowerCase() === 'line' && isCenterLine(e))
      .map(segmentOf)
      .filter((s): s is Segment => s !== null && s.length > 0);

    const horizontals = centreSegments.filter((s) => Math.abs(s.y1 - s.y0) <= AXIS_EPSILON);
    const verticals = centreSegments.filter((s) => Math.abs(s.x1 - s.x0) <= AXIS_EPSILON);
    const h = longest(horizontals);
    const v = longest(verticals);

    if (h && v) return emit(v.x0, h.y0, 'centerline_cross');

    // 4. A concentric family outranks a lone centreline: a bolt circle fixes BOTH coordinates,
    // where one centreline fixes an axis and leaves its midpoint standing in for the other.
    const axis = concentricAxis(inThisView, rect);
    if (axis) return emit(axis.x, axis.y, 'concentric');

    if (h) return emit((h.x0 + h.x1) / 2, h.y0, 'centerline_axis');
    if (v) return emit(v.x0, (v.y0 + v.y1) / 2, 'centerline_axis');

    return [];
  });
};

/** Flattens the canvas's `layers` record into the flat entity list the datum finder wants. */
export const entitiesFromLayers = (layers: Record<string, CanvasEntity[]> | null | undefined): CanvasEntity[] => {
  if (!layers) return [];
  const out: CanvasEntity[] = [];
  for (const group of Object.values(layers)) {
    if (Array.isArray(group)) out.push(...group);
  }
  return out;
};
