/**
 * sectionCallouts.ts
 *
 * Which text entities on a sheet are section-view *identifiers* — the `Ａ－Ａ` that titles a
 * section and the lone `Ａ` sitting at each cut arrow — so the canvas can leave them undrawn.
 *
 * ## Why the canvas needs its own answer
 *
 * The comparison engine already ignores all of this. `DROP_SECTION_CALLOUT_LABELS`
 * (`orchestrator.py`) removes the labels from the drawing_views checklist via
 * `feature_classifier.refine_view_labels`, and the cut-plane line and arrow blocks were never
 * eligible in the first place — `COMPARABLE_ENTITY_TYPES` is `("text", "dimension")`, so a LINE
 * or an INSERT is invisible to the differ. Nothing here changes what is compared.
 *
 * What the engine does not touch is what gets *painted*. `renderEntities` draws the payload, and
 * the payload still contains the labels, so a section callout shows on the sheet while producing
 * no finding. This module closes that gap on the render side only.
 *
 * ## The trap: a lone `Ａ` is usually not a section callout
 *
 * On this corpus the sheet border carries grid labels — `1`–`7` across, letters down — and they
 * are lone letters too. Suppressing text by matching `A` erases the drawing frame. The backend
 * hit the same trap and documents it: on M7452A1N01 the reference's "only `Ａ` texts are two
 * frame grid labels on layer WAKU".
 *
 * Two gates keep them apart, and neither is a tuned constant:
 *
 *  1. **Drawing context.** A lone letter counts only when the same sheet also carries the
 *     matching `X-X` designation. Both letters must be the same, so a sheet with an `Ａ－Ａ`
 *     section does not sweep up an unrelated lone `Ｂ`. This mirrors `refine_view_labels`
 *     exactly — deliberately, because two implementations of one rule that disagree are worse
 *     than one rule in the wrong place.
 *  2. **Provenance.** Only text that arrived *through a viewport* is eligible. Model-space
 *     geometry is projected onto the sheet and carries `properties.viewport_index >= 0`; native
 *     paper-space furniture — the frame, the title block, the tolerance table, the border grid
 *     labels — is left alone by the projector and keeps `NO_VIEWPORT` (`-1`). Measured on
 *     M745221N01's revision: both section callouts resolve to viewports 0 and 1, and all six
 *     border grid labels plus every tolerance-table number sit at `-1`.
 *
 * The backend reaches the same separation with zone boxes and a furniture-layer list. Neither is
 * available here — this corpus's sheets put the entire drawing on `NoLayerName_001`, which is why
 * `is_furniture_layer` is documented as helping "only the AutoCAD side". `viewport_index` is
 * carried verbatim to the client (`GeometrySerializer` forwards `ent.properties` whole, and the
 * layers fetch runs through `parseOrThrow` with no Zod schema to strip it), so it is the one
 * signal the canvas can actually use.
 *
 * ⚠ A sheet whose section callouts were authored in paper space would not be matched. That is the
 * safe direction: the label is drawn, exactly as it is today.
 */

/**
 * Set `false` to draw section callouts again. Mirrors `DROP_SECTION_CALLOUT_LABELS` in
 * `orchestrator.py`, which is the same decision on the comparison side — the two are independent
 * on purpose, since one governs findings and this one governs ink.
 */
export const HIDE_SECTION_CALLOUTS: boolean = true;

/**
 * `Ａ－Ａ`, `A-A`, `Ａ ー Ａ`. Same letter both sides — `A-B` is a dimension or a note, not a
 * section designation. The separator class carries every dash the corpus actually uses:
 * ASCII hyphen, the Unicode dashes, the katakana prolonged sound mark, and the fullwidth
 * hyphen-minus that NFKC does not always fold. Kept byte-for-byte in step with
 * `_SECTION_DESIGNATION_RE` in `feature_classifier.py`.
 */
const SECTION_DESIGNATION_RE = /^([A-Za-z])\s*[-‐‑–—ー－]\s*\1$/i;

/** A bare single letter — the cut-arrow label. Meaningless on its own; gate 1 is what qualifies it. */
const LONE_LETTER_RE = /^[A-Za-z]$/;

/** Set by `viewport_transform.py` on entities the projector never resolved to a viewport. */
const NO_VIEWPORT = -1;

/**
 * Two points this close, in the projected paper units the canvas draws in, are the same point.
 *
 * A coincidence tolerance, not a tuned classifier threshold — and the measurement says so.
 * On M745221N01's revision the apparatus lands within **0.3** of a cut-path vertex (arrow-tick
 * midpoints at 0.05 and 0.07, leader tails at 0.28 and 0.3) while the nearest thing that must
 * survive — the `6-9キリ` leader — is **46.9** away. Two orders of magnitude of daylight, so the
 * exact value is not load-bearing; anything from 0.5 to 40 gives the same answer.
 */
const COINCIDENT = 1.0;

/** Entity types that can carry the arrow ticks and label tails hanging off a cut path. */
const APPARATUS_TYPES = new Set(['leader', 'polyline', 'multileader']);

/**
 * The apparatus is drawn as 2- and 3-point stubs. Capping the vertex count stops a long
 * construction polyline that happens to start on the cut path from being swallowed whole.
 */
const MAX_APPARATUS_VERTICES = 3;

/**
 * NFKC folds fullwidth `Ａ` to `A` and fullwidth `－` to `-`, which is what makes one ASCII
 * regex serve a Japanese sheet. Mirrors `_fold` in `feature_classifier.py`.
 */
const fold = (text: string): string => text.normalize('NFKC').trim();

/** Minimal shape of a canvas entity. `properties` and `geometry` arrive from the API verbatim. */
interface CanvasEntity {
  type?: string;
  geometry?: any;
  properties?: any;
}

/**
 * The text a canvas entity would paint, read in the same order `renderEntities` reads it so the
 * two can never disagree about which string an entity carries.
 */
const textOf = (e: CanvasEntity): string =>
  String(e?.geometry?.text || e?.geometry?.content || e?.properties?.text || '');

/** True when this entity was projected onto the sheet through a paper-space viewport. */
const cameFromAViewport = (e: CanvasEntity): boolean => {
  const idx = Number(e?.properties?.viewport_index);
  return Number.isFinite(idx) && idx > NO_VIEWPORT;
};

type Point = [number, number];

const isPoint = (p: any): p is Point =>
  Array.isArray(p) && p.length >= 2 && Number.isFinite(p[0]) && Number.isFinite(p[1]);

const near = (a: Point, b: Point): boolean => Math.hypot(a[0] - b[0], a[1] - b[1]) <= COINCIDENT;

const isCenterLinetype = (e: CanvasEntity): boolean =>
  String(e?.properties?.linetype ?? '').toUpperCase().includes('CENTER');

/** Every vertex of an apparatus candidate, plus its midpoint — an arrow tick straddles the cut. */
const apparatusAnchors = (verts: Point[]): Point[] => {
  if (verts.length < 2) return verts;
  const first = verts[0];
  const last = verts[verts.length - 1];
  const mid: Point = [(first[0] + last[0]) / 2, (first[1] + last[1]) / 2];
  return [...verts, mid];
};

const vertexListOf = (e: CanvasEntity): Point[] => {
  const raw = e?.geometry?.vertices ?? e?.geometry?.points;
  return Array.isArray(raw) ? raw.filter(isPoint).map((p: any) => [p[0], p[1]] as Point) : [];
};

/**
 * The cut-plane lines on this sheet, found by colour rather than by position.
 *
 * ## Why colour, and why the *minority* one
 *
 * A section cut is drawn in `CENTER` linetype — and so is every part axis centreline and every
 * bolt-hole centre mark, which must survive. Position does not separate them: on M745221N01 the
 * cut segment sits 5.1 units from its label and an axis centreline sits 7.3 from the same label,
 * a 2.2-unit margin that any threshold would be fitted to rather than derived from.
 *
 * The drafter already separates them, by colour. Measured across **every one of the 9 drawings in
 * `storage/uploads` that carries an `X-X` designation**: the cut segments are always a strict
 * minority of the sheet's `CENTER` lines (1–2 of them) in a colour distinct from the majority,
 * which is the axis-centreline colour. Reading the majority off the sheet itself keeps this
 * self-calibrating — no ACI index is hardcoded, so a client whose template inverts the convention
 * is still handled.
 *
 * Ties and single-colour sheets return nothing, which is the safe direction: the lines are drawn,
 * exactly as they are today.
 *
 * ⚠ A minority-colour `CENTER` line that is *not* a cut plane would be culled on a sheet that has
 * a section designation. No such line exists in this corpus; if one appears, this is where to add
 * the label-proximity gate that was left out for having no honest constant.
 */
const findCutPlaneLines = (entities: CanvasEntity[]): CanvasEntity[] => {
  const centreLines = entities.filter(
    (e) => String(e?.type ?? '').toLowerCase() === 'line' && cameFromAViewport(e) && isCenterLinetype(e),
  );
  if (centreLines.length < 2) return [];

  const byColour = new Map<string, CanvasEntity[]>();
  for (const e of centreLines) {
    const key = String(e?.properties?.color ?? 'unknown');
    const bucket = byColour.get(key);
    if (bucket) bucket.push(e);
    else byColour.set(key, [e]);
  }
  if (byColour.size < 2) return [];

  const counts = [...byColour.values()].map((g) => g.length).sort((a, b) => b - a);
  // A tie for most-common means there is no majority to be a minority of.
  if (counts[0] === counts[1]) return [];
  const majority = counts[0];

  return [...byColour.values()].filter((g) => g.length < majority).flat();
};

/** Both ends of every cut segment, plus the vertices where a bent cut path changes direction. */
const cutPathVertices = (cutLines: CanvasEntity[]): Point[] => {
  const pts: Point[] = [];
  for (const e of cutLines) {
    const s = e?.geometry?.start;
    const t = e?.geometry?.end;
    if (isPoint(s)) pts.push([s[0], s[1]]);
    if (isPoint(t)) pts.push([t[0], t[1]]);
  }
  return pts;
};

/**
 * Every entity in `entities` that is a section-view identifier.
 *
 * Returns entity references rather than indices or ids: canvas entities carry no stable id, and
 * the caller walks the very same objects, so reference identity is both exact and free.
 *
 * @param entities - flat list of canvas entities, any mix of layers.
 * @param cleanText - optional text normaliser applied before matching, so the caller can pass
 *   `cleanCadText` and strip MTEXT formatting codes without this module importing the renderer.
 */
export const findSectionCallouts = (
  entities: CanvasEntity[],
  cleanText: (t: string) => string = (t) => t,
): Set<CanvasEntity> => {
  const found = new Set<CanvasEntity>();
  if (!Array.isArray(entities) || entities.length === 0) return found;

  // Only text, and only text that came through a viewport. Everything below reasons about this
  // pool alone, so paper-space furniture cannot contribute a designation letter either — a
  // stray `A-A` in a title block must not license hiding the border grid's `A`.
  const candidates: Array<{ entity: CanvasEntity; text: string }> = [];
  for (const e of entities) {
    if (String(e?.type ?? '').toLowerCase() !== 'text') continue;
    if (!cameFromAViewport(e)) continue;
    const text = fold(cleanText(textOf(e)));
    if (text) candidates.push({ entity: e, text });
  }

  const sectionLetters = new Set<string>();
  for (const { text } of candidates) {
    const match = SECTION_DESIGNATION_RE.exec(text);
    if (match) sectionLetters.add(match[1].toUpperCase());
  }

  // No designation on this sheet means no section view, which means every lone letter on it is
  // something else. Bail rather than guess — this is the property that makes the rule safe.
  if (sectionLetters.size === 0) return found;

  for (const { entity, text } of candidates) {
    if (SECTION_DESIGNATION_RE.test(text)) {
      found.add(entity);
    } else if (LONE_LETTER_RE.test(text) && sectionLetters.has(text.toUpperCase())) {
      found.add(entity);
    }
  }

  // The cut plane itself and the arrow ticks / label tails hanging off its ends. Gated on having
  // found a label, so a sheet with no section callout never loses a centreline.
  const cutLines = findCutPlaneLines(entities);
  if (cutLines.length === 0) return found;
  for (const line of cutLines) found.add(line);

  const vertices = cutPathVertices(cutLines);
  for (const e of entities) {
    if (!APPARATUS_TYPES.has(String(e?.type ?? '').toLowerCase())) continue;
    if (!cameFromAViewport(e)) continue;
    const verts = vertexListOf(e);
    if (verts.length < 2 || verts.length > MAX_APPARATUS_VERTICES) continue;
    if (apparatusAnchors(verts).some((a) => vertices.some((v) => near(a, v)))) found.add(e);
  }

  return found;
};

/**
 * Memoised per `layers` object.
 *
 * `renderEntities` runs on every pan, zoom and theme change, and the answer depends only on the
 * payload — which changes only when `fetchLayers` sets it. A `WeakMap` keyed on the layers object
 * makes every frame after the first a single lookup, and drops the entry when the store replaces
 * the payload.
 */
const cache = new WeakMap<object, Set<CanvasEntity>>();

export const sectionCalloutsForLayers = (
  layers: Record<string, CanvasEntity[]> | null | undefined,
  cleanText?: (t: string) => string,
): Set<CanvasEntity> => {
  if (!layers) return new Set();
  const hit = cache.get(layers);
  if (hit) return hit;

  const flat: CanvasEntity[] = [];
  for (const group of Object.values(layers)) {
    if (Array.isArray(group)) flat.push(...group);
  }

  const result = findSectionCallouts(flat, cleanText);
  cache.set(layers, result);
  return result;
};
