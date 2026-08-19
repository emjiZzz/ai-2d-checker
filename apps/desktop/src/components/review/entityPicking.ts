import { ZONE_KEYS, type DrawingZonesResponse } from "../../services/drawingsApi";

/**
 * Entity picking — "which CAD entity is under the cursor".
 *
 * ## Why this has to exist as its own index
 *
 * `renderEntities` batches geometry into style-keyed `Path2D` objects
 * (`${strokeColor}_${strokeWidth}_${dash}_${dashUnits}`) and flushes each with a single
 * `ctx.stroke(batch.path)`. Hundreds of entities share one path, so **entity identity is
 * destroyed at draw time** — after the loop there is nothing that maps a pixel back to an
 * `ent.id`. `ctx.isPointInStroke` would answer "is this pixel in the cyan-0.25mm-solid batch",
 * which is not a question anyone asked.
 *
 * So the index is populated *inside* the render loop, where identity is still in scope. This
 * generalises the pattern already used for violation markers
 * (`markerPositionsRef.current[v.id] = {x, y}`), which exists for the same reason.
 *
 * ## Why bounds are stored in flipped-world space
 *
 * The render loop works in "flipped world" units — CAD coordinates with `flipY` applied, which
 * `ctx` then scales and translates. Storing bounds in that space means the index survives a pan
 * or a zoom without being rebuilt, and the hit test converts the cursor once instead of
 * converting every box.
 *
 * ⚠ **Y is flipped here and that is not optional.** Entity geometry is CAD Y-up; the canvas is
 * Y-down. `flipWorldY` is the one conversion (`coordinateTransform.ts`), and it is the *same*
 * function the renderer uses, passed in rather than reimplemented. Getting it backwards
 * produces a hit box mirrored about the sheet's centreline — which, as `renderViewOrigins`
 * found, looks perfectly plausible near the middle of the sheet and is 152 units out at the
 * top.
 */

/** A pickable entity and where it sits, in flipped-world units. */
export interface EntityBox {
  id: string;
  entity: any;
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

/** Half-height added around a text entity's baseline anchor, as a multiple of cap height. */
const TEXT_BOX_PAD = 0.6;

/** Minimum half-extent, in world units, given to an entity with no measurable size. */
const MIN_HALF_EXTENT = 0.5;

/**
 * Types that exist in the payload but are never drawn, and must never be picked.
 *
 * `block` and `layer` rows are *containers* — CLAUDE.md's render census subtracts "6 `layer` +
 * 12 `block` containers" from the denominator for exactly this reason. Their children are
 * already in the payload as separate exploded entities, which is what the engineer can see and
 * therefore what they are aiming at.
 *
 * ⚠ Leaving `block` in was a real defect, and a nasty one because it fails *plausibly*: a block
 * row carries only `insert`, so it used to get a small synthetic box from the fallback below —
 * and since `hitTest` returns the SMALLEST match, that box beat the real text sitting inside it.
 * The stamp modal then showed `block · handle 384` instead of the value. It bites hardest on
 * the **reference** sheet, which is the DWG-exported side that keeps almost everything inside
 * blocks (24 of them on `M745230A01`), so the containers sit directly on top of the content.
 */
const CONTAINER_TYPES = new Set(['block', 'layer']);

/**
 * Types that carry a value a person reads, as opposed to geometry they see.
 *
 * A checker sweeping a drawing aims at numbers. Ranking these above geometry is what makes a
 * label printed across a circle selectable at all — see `hitTest`.
 */
const ANNOTATION_TYPES = new Set(['text', 'dimension', 'leader']);

/**
 * The value a person reads off an entity, normalized so the two exporters agree about it.
 *
 * ## Why normalizing is not optional here
 *
 * The reference and revision sheets are written by different exporters and they disagree about
 * how to spell the same value. Measured over `M745230A01`, both sides of one pair:
 *
 *  - the revision writes FULL-WIDTH (`Ｒ2`, `１`), the reference half-width (`C2`, `3-9キリ`);
 *  - the reference still carries RAW DXF override codes (`%%c8`), undecoded;
 *  - the diameter prefix is often not in the data at all — on `M745204N01` both sides store a
 *    bare `145` and the `ø` the engineer sees is printed by the dimension style.
 *
 * So a raw string comparison matches almost nothing, and the one thing worse than no match here
 * is a confident wrong one. `%%d` and `%%p` are decoded rather than dropped, because both sides
 * spell those the same way once decoded and discarding them would let `60°` match a bare `60`.
 * The diameter mark IS dropped, because that is the notation the two sides genuinely disagree
 * about.
 *
 * ⚠ The value lives in `properties.text`. `geometry.text` is `None` on every entity in the
 * corpus — measured across dimension, text and mtext on both sides of `M745230A01`. Reading
 * only the geometry field yields an index that silently matches nothing.
 */
const DXF_OVERRIDES: [RegExp, string][] = [
  [/%%[cC]/g, '⌀'], // diameter
  [/%%[dD]/g, '°'], // degree
  [/%%[pP]/g, '±'], // plus/minus
  [/%%%/g, '%'],
];

/** Marks the two sides spell differently for the same dimension, so they cannot be compared. */
const DIAMETER_MARKS = /[⌀øØφϕф]/g;

/**
 * Multiplication signs, folded onto the letter `x`.
 *
 * ⚠ **NFKC does not do this.** It folds the revision's full-width digits, parens and colon onto
 * the reference's half-width ones, so `４ロール：１２（２×６台）` and `4 ロール：12 (2x6台)` come
 * within one character of each other and then differ forever on U+00D7 versus the letter — the
 * only surviving difference in a string a person reads as identical.
 *
 * ⚠ **The backend already folded these; this layer did not.** `spatial_differ._normalize_text`
 * has done `× ✕ ✖ ⨯ → x` for as long as it has existed, and `infrastructure/utils/text.py`
 * folds `[xX×ラｘＸ]` (the `ラ` is a CP932 mis-decode of the same glyph). So the engine paired
 * this row and the manual-check overlay did not — two implementations of one rule, one of which
 * learned something. Pinned against the backend's set by
 * `entityPicking.test.ts`'s "the multiplication fold matches the backend's".
 */
const MULTIPLY_MARKS = /[×✕✖⨯⨉ｘ]/g;

/** MTEXT inline formatting: `\A1;` alignment, `\P` paragraph break, `{...}` grouping. */
const MTEXT_CODES = /\\[A-Za-z][^;\\]*;|\\P|[{}]/g;

export function normalizeEntityValue(raw: unknown): string {
  let v = String(raw ?? '');
  if (!v) return '';
  for (const [re, ch] of DXF_OVERRIDES) v = v.replace(re, ch);
  v = v.replace(MTEXT_CODES, '');
  // NFKC is what folds the revision's full-width digits onto the reference's half-width ones.
  v = v.normalize('NFKC');
  v = v.replace(DIAMETER_MARKS, '');
  // After NFKC: the full-width `ｘ` is folded by it, but `×` and the dingbat crosses are not.
  v = v.replace(MULTIPLY_MARKS, 'x');
  // `\s` misses the ideographic space U+3000 in some engines, and a Japanese sheet is full of
  // them — NFKC maps it to U+0020, so this runs after that and not before.
  return v.replace(/\s+/g, '').toUpperCase();
}

/**
 * The raw string the sheet ACTUALLY draws, before any normalization.
 *
 * ⚠ **`render_text` first, and it is not the same as `text`.** `render_text` is harvested from
 * the dimension's anonymous block at extraction — what the CAD application composited — while
 * `properties.text` is the DXF override field, which `map_dimension` rebuilds from
 * `actual_measurement` and which therefore **loses every prefix, suffix and tolerance stack the
 * dimstyle bakes in**. `renderEntities` has preferred `render_text` since the canvas was found
 * showing `145` where iCAD shows `φ145`; the picking layer read the impoverished field and so
 * disagreed with the pixels next to it.
 *
 * On `M745204N01` the difference is the whole point: the revision stores `%%c110` and the
 * reference a bare `110`, because the diameter standard was applied on the revision only. That
 * is a real difference between the sheets and the chip should show it.
 *
 * `<>` is the DXF placeholder for "substitute the measurement here". A file that omits
 * `actual_measurement` leaves it intact, and it must never be displayed or matched on, so it
 * falls through to the rebuilt text — which is exactly the case the degrees fix repaired.
 */
function preferredRawText(ent: any): string {
  const render = String(ent?.properties?.render_text ?? '');
  if (render && !render.includes('<>')) return render;
  return String(ent?.properties?.text ?? ent?.geometry?.text ?? ent?.geometry?.content ?? '');
}

/**
 * The value as a person reads it off the sheet: CAD markup resolved to real glyphs, nothing
 * folded away. `%%c110` becomes `⌀110`.
 *
 * Distinct from `entityValueOf`, deliberately. This is for display, so it keeps the diameter
 * mark, the original case and the full-width characters. The comparison key throws all three
 * away so that two exporters can agree — which is right for matching and wrong on screen.
 */
export function entityDisplayText(ent: any): string {
  let v = preferredRawText(ent);
  if (!v) return '';
  for (const [re, ch] of DXF_OVERRIDES) v = v.replace(re, ch);
  return v.replace(MTEXT_CODES, '').trim();
}

/** The readable value of an entity, or `''` for pure geometry that carries none. */
/**
 * What a chip shows: the entity's value as the sheet prints it, truncated to fit.
 *
 * Lives here rather than in one renderer because three overlays label a value — the hover chip,
 * the cross-sheet match and the selection — and they must not disagree about a value they have
 * just agreed on. `entityDisplayText` reads `render_text`, the string the CAD application
 * actually composited, so `⌀110` on a sheet applying the diameter standard shows as `⌀110` while
 * the sheet that does not shows `110`. That difference is real and the two still MATCH, because
 * the comparison key folds the diameter mark away and the display does not.
 */
export function displayValueOf(ent: any): string {
  const raw = entityDisplayText(ent);
  return raw.length > 22 ? `${raw.slice(0, 22)}...` : raw;
}

export function entityValueOf(ent: any): string {
  return normalizeEntityValue(preferredRawText(ent));
}

/**
 * A dimension's KIND — 0 linear, 1 aligned, 2 angular, 3 diameter, 4 radius, 5 angular-3p.
 *
 * The low 3 bits of `dim_type`; the high bits are flags. Same mask the backend's
 * `spatial_differ._dimension_key` uses, so the overlay and the engine cannot disagree about
 * what kind of dimension something is. `null` for anything that is not a dimension.
 *
 * This separates an 80° angular dimension from a linear `80` — which read identically once
 * normalized, and are not the same measurement.
 */
export function dimensionKindOf(ent: any): number | null {
  if (String(ent?.type) !== 'dimension') return null;
  return (Number(ent?.properties?.dim_type) || 0) & 0b111;
}

/**
 * Which semantic zone a box sits in, or `null`.
 *
 * ⚠ **Detected zone boxes are CAD Y-up; this index is flipped-world.** Comparing them without
 * flipping produces a zone assignment that is mirrored about the sheet centreline — correct
 * near the middle and wrong at the top and bottom, which is CLAUDE.md's constraint 3 and the
 * `renderViewOrigins` failure in another costume. The flip is applied to the zone, once, here.
 *
 * The SMALLEST containing zone wins, because zones nest: `title_upper_left` sits inside
 * `title`, and the answer wanted is the most specific one.
 */
export function zoneKeyForBox(
  zones: DrawingZonesResponse | null | undefined,
  bx: { x0: number; y0: number; x1: number; y1: number },
  flipY: (y: number) => number,
): string | null {
  if (!zones) return null;
  const cx = (bx.x0 + bx.x1) / 2;
  const cy = (bx.y0 + bx.y1) / 2;

  let best: string | null = null;
  let bestArea = Infinity;
  for (const key of ZONE_KEYS) {
    const z = (zones as any)[key];
    if (!z) continue;
    // flipY reverses order, so the flipped pair has to be re-sorted into min/max.
    const zy0 = Math.min(flipY(z.ymin), flipY(z.ymax));
    const zy1 = Math.max(flipY(z.ymin), flipY(z.ymax));
    if (cx < z.xmin || cx > z.xmax || cy < zy0 || cy > zy1) continue;
    const area = Math.abs(z.xmax - z.xmin) * Math.abs(zy1 - zy0);
    if (area < bestArea) {
      best = key;
      bestArea = area;
    }
  }
  return best;
}

/**
 * Where a box sits INSIDE its zone, as a fraction of that zone.
 *
 * Sheet-relative position does not correspond between the two drawings — that is the whole
 * finding behind this module's cross-sheet matching. Zone-relative position is a different
 * claim and a much weaker one: within a single view or table, the two revisions of a drawing
 * do arrange their content alike, which is visible on `M745204N01` where the 60°/50°/80°
 * callouts occupy the same clock positions on both sheets even though the sheets themselves do
 * not line up. Used ONLY to separate candidates that already agree on value, type and zone.
 */
export function zoneRelativePos(
  zones: DrawingZonesResponse | null | undefined,
  zoneKey: string | null,
  bx: { x0: number; y0: number; x1: number; y1: number },
  flipY: (y: number) => number,
): { zfx: number; zfy: number } | null {
  if (!zones || !zoneKey) return null;
  const z = (zones as any)[zoneKey];
  if (!z) return null;
  const zy0 = Math.min(flipY(z.ymin), flipY(z.ymax));
  const zy1 = Math.max(flipY(z.ymin), flipY(z.ymax));
  const w = z.xmax - z.xmin;
  const h = zy1 - zy0;
  if (!(w > 0) || !(h > 0)) return null;
  return {
    zfx: ((bx.x0 + bx.x1) / 2 - z.xmin) / w,
    zfy: ((bx.y0 + bx.y1) / 2 - zy0) / h,
  };
}

/**
 * Whether a zone box is a MEASUREMENT rather than a guess.
 *
 * `percentage_fallback` means no semantic anchor was found and the box is a percentage grid over
 * the sheet — the schema's own docstring calls it "a guess, not a measurement". Those boxes land
 * wherever the grid puts them, so the two sides of a pair disagree about which zone an entity is
 * in, and a zone equality test against one is worse than no test at all.
 *
 * Measured on `M745204N01`: the reference resolves `tolerance`, `notes` and `iso` by percentage
 * fallback while the revision detects all three, putting them in different halves of the sheet
 * (`tolerance` at 0.68–0.94 of sheet height against 0.06–0.23). Gating on zone equality across
 * that blanked **120 of 184** hovers, against 18 with no zone test at all.
 */
export function isZoneMeasured(
  zones: DrawingZonesResponse | null | undefined,
  zoneKey: string | null,
): boolean {
  if (!zones || !zoneKey) return false;
  return (zones as any)[zoneKey]?.confidence === 'content_aware';
}

/**
 * Position as a fraction of the whole sheet. **The weak tie-break, and only ever a tie-break.**
 *
 * Sheet-relative position does not identify a counterpart — that is the finding this module was
 * rebuilt around. It is used only to order candidates that already agree on value, type and
 * dimension kind, and only when zone cannot separate them. Ordering equals by a weak signal is
 * not the same as matching on one.
 */
export function sheetRelativePos(
  bx: { x0: number; y0: number; x1: number; y1: number },
  norm: { hasBounds: boolean; normScale: number; xmin: number; ymin: number; ymax: number },
): { sfx: number; sfy: number } | null {
  if (!norm.hasBounds) return null;
  const spanX = 1000 / norm.normScale;
  const spanY = norm.ymax - norm.ymin;
  if (!(spanX > 0) || !(spanY > 0)) return null;
  return {
    sfx: ((bx.x0 + bx.x1) / 2 - norm.xmin) / spanX,
    sfy: ((bx.y0 + bx.y1) / 2 - norm.ymin) / spanY,
  };
}

/** How the target canvas answers questions about its own boxes. */
export interface TargetSheetResolver {
  zoneOf(b: EntityBox): string | null;
  zoneMeasured(zone: string | null): boolean;
  zonePos(b: EntityBox, zone: string | null): { zfx: number; zfy: number } | null;
  sheetPos(b: EntityBox): { sfx: number; sfy: number } | null;
}

/** Travel beyond which a left-button press is a pan, not a click on an entity. */
export const CLICK_SLOP_PX = 4;

/**
 * Whether a completed left-button gesture should open the stamping menu.
 *
 * Extracted from the hook because this is the part that fails *silently and constantly*: the
 * same button pans the drawing, so a pan that happens to finish over a value would pop the menu
 * open mid-sweep. That is not a crash and not a wrong marking — it is an interruption on every
 * few drags, which is the kind of thing that gets lived with rather than reported.
 *
 * `press` is null when the gesture did not start with the left button on this canvas — a release
 * that drifted in from elsewhere is not a click here.
 */
export function isStampClick(
  button: number,
  press: { x: number; y: number } | null,
  release: { x: number; y: number },
): boolean {
  if (button !== 0 || !press) return false;
  return Math.hypot(release.x - press.x, release.y - press.y) <= CLICK_SLOP_PX;
}

/**
 * Whether the menu-opening event that follows this release should be swallowed.
 *
 * The other half of `isStampClick`, and kept beside it on purpose: both answer "was this gesture
 * a click on an entity, or a drag?", both turn on `CLICK_SLOP_PX`, and two copies of that
 * question drifting apart is how you get a canvas that stamps when it should pan.
 *
 * `grabbed` means the press landed on something draggable — a marker, an annotation pin, a zone
 * handle, the ROI centre. That suppresses whatever the distance travelled: a marker press that
 * never moves is still a select-or-delete, not a stamp. A pan has to clear the slop first,
 * because every ordinary click drifts a pixel or two and must remain a click.
 */
export function shouldSuppressNextMenu(
  grabbed: boolean,
  panning: boolean,
  travelPx: number,
): boolean {
  return grabbed || (panning && travelPx > CLICK_SLOP_PX);
}

/** What the other sheet is looking for. Every field must agree for a box to be a candidate. */
export interface ValueMatchSpec {
  value: string;
  entityType: string;
  dimKind: number | null;
  zone: string | null;
  /** Whether the SOURCE sheet measured that zone. A guessed zone is not filtered on. */
  zoneMeasured: boolean;
  /** Position within the zone. Tie-break only, when both sides measured the same zone. */
  zfx: number | null;
  zfy: number | null;
  /**
   * Where this entity sits among the OTHER copies of its own value on its sheet, as a fraction
   * of that group's bounding box. The tie-break that actually corresponds across two sheets:
   * absolute position does not, because the sheets differ in scale and placement, but "the
   * left-most of the three 60° dimensions" is the same claim on both.
   */
  cfx: number | null;
  cfy: number | null;
  /** Position within the sheet. The weakest tie-break, for when nothing above separates. */
  sfx: number | null;
  sfy: number | null;
}

function box(x0: number, y0: number, x1: number, y1: number) {
  return {
    x0: Math.min(x0, x1),
    y0: Math.min(y0, y1),
    x1: Math.max(x0, x1),
    y1: Math.max(y0, y1),
  };
}

/**
 * The bounding box of a set of boxes, or null if the set is empty.
 *
 * Used to normalise a value-group's layout away, so two sheets that place the same view at
 * different scales and offsets still agree about which member is which.
 */
function groupBounds(boxes: { x0: number; y0: number; x1: number; y1: number }[]) {
  if (!boxes.length) return null;
  return {
    x0: Math.min(...boxes.map((b) => b.x0)),
    y0: Math.min(...boxes.map((b) => b.y0)),
    x1: Math.max(...boxes.map((b) => b.x1)),
    y1: Math.max(...boxes.map((b) => b.y1)),
  };
}

/**
 * A box's centre as fractions of an enclosing box.
 *
 * A degenerate axis collapses to 0.5 rather than dividing by zero — three values in a vertical
 * column genuinely have no horizontal ordering, and 0.5 on both sides makes that axis
 * contribute nothing to the distance instead of poisoning it. `null` only when BOTH axes are
 * degenerate, which means the group carries no ordering at all.
 */
function fractionIn(
  outer: { x0: number; y0: number; x1: number; y1: number },
  inner: { x0: number; y0: number; x1: number; y1: number },
): { fx: number; fy: number } | null {
  const w = outer.x1 - outer.x0;
  const h = outer.y1 - outer.y0;
  if (w <= 0 && h <= 0) return null;
  const cx = (inner.x0 + inner.x1) / 2;
  const cy = (inner.y0 + inner.y1) / 2;
  return {
    fx: w > 0 ? (cx - outer.x0) / w : 0.5,
    fy: h > 0 ? (cy - outer.y0) / h : 0.5,
  };
}

/**
 * The true extent of a swept arc, in flipped-world units.
 *
 * The endpoints alone are not enough: an arc crossing due-east bulges past both of them. So the
 * box is the two endpoints plus whichever cardinal directions (0°, 90°, 180°, 270°) the sweep
 * actually passes through — those are the only places a circular arc can reach an extreme.
 *
 * Angles are CAD degrees, counter-clockwise, and DXF arcs always sweep counter-clockwise from
 * `start_angle` to `end_angle` — which is why `end < start` means the arc crosses 0° rather than
 * being reversed.
 */
function arcBounds(
  cx: number,
  cyRaw: number,
  r: number,
  startDeg: number,
  endDeg: number,
  flipY: (y: number) => number,
) {
  const norm = (d: number) => ((d % 360) + 360) % 360;
  const a0 = norm(startDeg);
  const sweep = norm(endDeg - startDeg) || 360;

  const at = (deg: number): [number, number] => {
    const rad = (deg * Math.PI) / 180;
    return [cx + r * Math.cos(rad), flipY(cyRaw + r * Math.sin(rad))];
  };

  const pts: [number, number][] = [at(a0), at(a0 + sweep)];
  for (const cardinal of [0, 90, 180, 270]) {
    // Distance travelled from the start to this cardinal, going counter-clockwise.
    if (norm(cardinal - a0) <= sweep) pts.push(at(cardinal));
  }

  const xs = pts.map((p) => p[0]);
  const ys = pts.map((p) => p[1]);
  return box(Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys));
}

function fromPoints(
  points: any[],
  flipY: (y: number) => number,
): { x0: number; y0: number; x1: number; y1: number } | null {
  let x0 = Infinity;
  let y0 = Infinity;
  let x1 = -Infinity;
  let y1 = -Infinity;
  for (const p of points) {
    if (!Array.isArray(p) || p.length < 2) continue;
    const x = Number(p[0]);
    const y = flipY(Number(p[1]));
    if (!Number.isFinite(x) || !Number.isFinite(y)) continue;
    x0 = Math.min(x0, x);
    y0 = Math.min(y0, y);
    x1 = Math.max(x1, x);
    y1 = Math.max(y1, y);
  }
  return Number.isFinite(x0) ? box(x0, y0, x1, y1) : null;
}

/**
 * Bounds for one entity in flipped-world units, or null if it has no drawable geometry.
 *
 * The geometry keys mirror the ones `renderEntities` itself reads — `location`/`insert`,
 * `start`/`end`, `center`+`radius`, `points`, `vertices`, `render_paths`, and a dimension's
 * `render_text_point`/`def_point`. Keeping the two lists aligned matters: an entity this
 * function cannot measure is one the engineer can see but not click, and there is nothing on
 * screen to explain why.
 *
 * ⚠ **A DIMENSION anchors on `def_point`, not `insert`.** That mismatch is exactly the open
 * defect that stops `tools/eval_corpus.py worksheet` placing a dimension at all, and a labelling
 * tool that inherited it would be unable to record the one false-negative class the corpus has
 * already caught. `render_text_point` is preferred where present because it is where the
 * measurement text is actually drawn — which is what the engineer is aiming at.
 */
export function entityWorldBounds(
  ent: any,
  flipY: (y: number) => number,
): { x0: number; y0: number; x1: number; y1: number } | null {
  const geo = ent?.geometry;
  if (!geo) return null;
  if (CONTAINER_TYPES.has(String(ent.type))) return null;

  // `properties.bbox` is the extractor's OWN measured extent, and for text it is present on
  // every entity (249/249 on `M7452A0N01_reference`). Prefer it over anything derived here.
  //
  // ⚠ This is the fix for text being unclickable. The estimate below anchors on `insert` and
  // pads symmetrically, which assumes `insert` is a baseline — but this client's sheets are
  // MTEXT with `attachment_point: 1`, where `insert` is the TOP-left and the glyphs hang
  // *below* it. Measured against the real bbox, the synthetic box was off by a median of 2.8
  // drawing units (p90 6.3, max 17.7) on a box only ~12 units tall, so for much of the sheet
  // the hit region did not overlap the text at all. It fails silently: the cursor is visibly on
  // a value and nothing reports a hit.
  const bbox = ent.properties?.bbox;
  if (Array.isArray(bbox) && bbox.length === 2 && Array.isArray(bbox[0]) && Array.isArray(bbox[1])) {
    const [[bx0, by0], [bx1, by1]] = bbox;
    if ([bx0, by0, bx1, by1].every((v) => Number.isFinite(Number(v)))) {
      return box(Number(bx0), flipY(Number(by0)), Number(bx1), flipY(Number(by1)));
    }
  }

  // Fallback for text with no measured bbox: a baseline anchor plus a cap height. Generous on
  // purpose — a 2px smear at fit-to-screen zoom still has to be clickable, because that is the
  // zoom at which a checker reads the sheet.
  if (ent.type === 'text' && (geo.location || geo.insert)) {
    const anchor = geo.location || geo.insert;
    const x = Number(anchor[0]);
    const y = flipY(Number(anchor[1]));
    if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
    const height = Number(ent.properties?.height || ent.style?.fontSize || 12) || 12;
    const raw = String(geo.text || geo.content || ent.properties?.text || '');
    const halfWidth = Math.max(raw.length, 1) * height * 0.5;
    return box(x, y - height * TEXT_BOX_PAD, x + halfWidth, y + height * TEXT_BOX_PAD);
  }

  // ⚠ A DIMENSION is measured from its TEXT, and this branch must come before `render_paths`.
  //
  // `render_paths` describes the whole dimension — extension lines, the dimension line, the
  // arrowheads — so on a re-extracted drawing it produced a box spanning the entire measured
  // span. On a concentric view a diameter dimension then covers the whole circle, and since
  // `hitTest` prefers the smallest match, the dimension became **unpickable**: every smaller
  // thing inside its own span won instead. What the engineer is aiming at is the value.
  if (ent.type === 'dimension') {
    const point = geo.render_text_point || geo.text_point || geo.def_point;
    if (!Array.isArray(point) || point.length < 2) return null;
    const x = Number(point[0]);
    const y = flipY(Number(point[1]));
    if (!Number.isFinite(x) || !Number.isFinite(y)) return null;

    // `text` carries CAD markup (`%%c120` renders as ⌀120), so measure the rendered length
    // rather than the raw string — otherwise every diameter reads four characters too wide.
    const raw = String(ent.properties?.text ?? '');
    const shown = raw.replace(/%%[cdp]/gi, '#').trim() || String(ent.properties?.measurement ?? '');

    // (!) The height is `text_height`. A DIMENSION carries no `height` at all -- absent on every
    // dimension on both sides of `M745204N01` -- so this fell through to the constant 12.
    //
    // That constant is an ABSOLUTE CAD length, and the two sheets of a pair are not drawn at the
    // same CAD scale: the reference spans 1386 units against the revision's 462. One fixed box is
    // therefore 0.0218 of one sheet and 0.0655 of the other, so the hover box rendered THREE TIMES
    // larger on the revision than the matching box on the reference, for the same value.
    //
    // It hid because 12 happens to be the reference's real text height, so that side looked right
    // and only the revision looked wrong -- which reads as a bug in the revision's rendering
    // rather than in a shared default. `text_height` is present on every dimension and is
    // proportional (12.0 against 4.0, both 0.00866 of their own sheet), so reading it makes the
    // box the same size on screen on both. The 12 stays only as a last resort.
    const height =
      Number(ent.properties?.text_height || ent.properties?.height || 12) || 12;
    const halfWidth = Math.max(shown.length, 2) * height * 0.42;
    return box(x - halfWidth, y - height * 0.7, x + halfWidth, y + height * 0.7);
  }

  if (Array.isArray(geo.render_paths) && geo.render_paths.length) {
    const flat: any[] = [];
    for (const path of geo.render_paths) {
      if (Array.isArray(path)) flat.push(...path);
    }
    const bounds = fromPoints(flat, flipY);
    if (bounds) return bounds;
  }

  if (geo.start && geo.end) {
    return fromPoints([geo.start, geo.end], flipY);
  }

  if (geo.center && geo.radius !== undefined) {
    const cx = Number(geo.center[0]);
    const cyRaw = Number(geo.center[1]);
    const r = Math.abs(Number(geo.radius)) || MIN_HALF_EXTENT;
    if (!Number.isFinite(cx) || !Number.isFinite(cyRaw)) return null;

    // ⚠ An ARC is not its circle. Using `center ± radius` gave a 60° arc a box covering the
    // whole circle it is part of — which is what made the hover highlight look absurdly large,
    // and worse, let one arc blanket every entity inside its own radius.
    const a0 = Number(ent.properties?.start_angle);
    const a1 = Number(ent.properties?.end_angle);
    if (Number.isFinite(a0) && Number.isFinite(a1)) {
      return arcBounds(cx, cyRaw, r, a0, a1, flipY);
    }

    const cy = flipY(cyRaw);
    return box(cx - r, cy - r, cx + r, cy + r);
  }

  if (Array.isArray(geo.points) && geo.points.length) return fromPoints(geo.points, flipY);
  if (Array.isArray(geo.vertices) && geo.vertices.length) return fromPoints(geo.vertices, flipY);

  // Anything left is a type whose geometry this function does not understand. Return nothing
  // rather than inventing a box: an over-broad fallback fails silently, by handing back a
  // plausible wrong entity instead of none. That is how block containers became pickable.
  return null;
}

/** The box whose delta is smallest, or null when no candidate could be measured. */
function nearest(
  boxes: EntityBox[],
  delta: (b: EntityBox) => [number, number] | null,
): EntityBox | null {
  let best: EntityBox | null = null;
  let bestD = Infinity;
  for (const b of boxes) {
    const d = delta(b);
    if (!d) continue;
    const dist = Math.hypot(d[0], d[1]);
    if (dist < bestD) {
      bestD = dist;
      best = b;
    }
  }
  return best;
}

/**
 * Every pickable entity on one canvas, rebuilt each render.
 *
 * Held in a ref by the canvas rather than in React state: it is written during the render loop,
 * which must not trigger a re-render, and read synchronously by the mouse handler.
 */
export class EntityHitIndex {
  private boxes: EntityBox[] = [];

  reset() {
    this.boxes = [];
  }

  /**
   * Called from inside the entity loop, where `ent.id` is still in scope.
   *
   * ## Only things a person reads are indexed
   *
   * An ARC, CIRCLE, LINE, POLYLINE, ELLIPSE or LEADER carries nothing to compare -- measured,
   * `properties.text` is `None` on every one of them across both sides of `M745204N01`, while
   * `text` and `dimension` carry a value on every instance. Indexing the rest bought nothing and
   * cost a great deal: hovering anywhere in a view resolved to whichever arc happened to be
   * under the cursor and threw a large highlight box across the drawing, labelled `arc`. It also
   * made those entities right-clickable, so a checker could stamp a ground-truth marking onto a
   * line -- a finding whose whole content is "this line exists", which nothing downstream can
   * compare and no engineer meant to record.
   *
   * The gate is the VALUE, not a type list, so it stays correct as new CAD types appear: a type
   * that carries text becomes pickable automatically, and one that does not never will.
   *
   * (!) The consequence, stated rather than buried: a purely geometric change -- an added hole,
   * a moved edge -- can no longer be stamped directly. It has to be recorded against the
   * dimension or note that describes it. Owner's call, 2026-08-18.
   */
  record(ent: any, bounds: { x0: number; y0: number; x1: number; y1: number } | null) {
    if (!bounds || !ent?.id) return;
    if (!entityValueOf(ent)) return;
    this.boxes.push({ id: String(ent.id), entity: ent, ...bounds });
  }

  get size() {
    return this.boxes.length;
  }

  /** Bounds of one entity, for drawing the hover highlight over what the hit test resolved. */
  boundsFor(id: string | null): EntityBox | null {
    if (!id) return null;
    return this.boxes.find((b) => b.id === id) ?? null;
  }

  /**
   * The counterpart of a hovered entity on THIS sheet.
   *
   * ## The rule, and how it got here
   *
   * Matching on value alone outlined everything sharing a value - three boxes labelled `x3` for
   * one hovered angle. Every candidate must now agree on:
   *
   *  - **value**, normalized so the two exporters' spellings agree;
   *  - **entity type**, so a dimension never matches a note reading the same;
   *  - **dimension kind**, so an 80 degree angular never matches a linear `80`;
   *  - **zone** - but only where BOTH sides measured that zone.
   *
   * (!) **That last qualification is load-bearing.** Requiring zone equality unconditionally was
   * measured on `M745204N01` and it blanked **120 of 184** hovers, against 18 with no zone test
   * at all: the reference resolves `tolerance`, `notes` and `iso` by `percentage_fallback`, so
   * the same physical dimension is `views` on one sheet and `tolerance` on the other. A guessed
   * box is not evidence, and filtering on one is worse than not filtering. Where either side
   * guessed, zone is ignored and the other three fields carry the match.
   *
   * Survivors are separated in three stages, strongest first: position within the zone when both
   * sides measured the same one; then position within the GROUP of same-value entities; then
   * position within the sheet.
   *
   * (!) **The group stage exists because the sheet stage picked wrong.** On `M745204N01` the
   * reference's upper-left `60°` paired with the revision's TOP `60°` — the two sheets place
   * that view differently, so the nearest sheet fraction is not the corresponding dimension.
   * Normalising against the group's own bounding box cancels exactly that difference: both
   * sheets agree the one in question is the left-most of three, whatever the scale or where the
   * view sits. Sheet position is kept below it, unchanged, for the case where a value appears
   * once per group and the group carries no ordering.
   */
  findMatches(spec: ValueMatchSpec, r: TargetSheetResolver): EntityBox[] {
    if (!spec.value) return [];

    const typed = this.peersOf(spec.value, spec.entityType, spec.dimKind);
    if (typed.length <= 1) return typed;

    // Zone filters only between two measured boxes; a guess on either side disqualifies the test.
    const sourceZoneUsable = Boolean(spec.zone) && spec.zoneMeasured;
    const candidates = typed.filter((b) => {
      if (!sourceZoneUsable) return true;
      const z = r.zoneOf(b);
      if (!r.zoneMeasured(z)) return true;
      return z === spec.zone;
    });
    if (candidates.length <= 1) return candidates;

    // Strong tie-break: same measured zone on both sides, compared by position inside it.
    if (sourceZoneUsable && spec.zfx !== null && spec.zfy !== null) {
      const sameZone = candidates.filter((b) => r.zoneOf(b) === spec.zone);
      const best = nearest(sameZone, (b) => {
        const q = r.zonePos(b, spec.zone);
        return q ? [q.zfx - (spec.zfx as number), q.zfy - (spec.zfy as number)] : null;
      });
      if (best) return [best];
    }

    // Group tie-break: where the entity sits among the other copies of its own value. Measured
    // against `typed` rather than `candidates` so both sheets normalise against the same thing —
    // the source applied no zone filter when it built its own fraction, and a bounding box taken
    // over a filtered subset would be a different box, silently comparing two different spaces.
    // `Number.isFinite`, not `!== null`: a locator built before these fields existed carries
    // `undefined`, which passes a null check and then poisons every distance with NaN — a
    // tie-break that silently stops discriminating while still looking like it ran.
    if (Number.isFinite(spec.cfx) && Number.isFinite(spec.cfy)) {
      const group = groupBounds(typed);
      if (group) {
        const best = nearest(candidates, (b) => {
          const q = fractionIn(group, b);
          return q ? [q.fx - (spec.cfx as number), q.fy - (spec.cfy as number)] : null;
        });
        if (best) return [best];
      }
    }

    // Weakest tie-break: position on the sheet. Orders equals; establishes nothing.
    if (Number.isFinite(spec.sfx) && Number.isFinite(spec.sfy)) {
      const best = nearest(candidates, (b) => {
        const q = r.sheetPos(b);
        return q ? [q.sfx - (spec.sfx as number), q.sfy - (spec.sfy as number)] : null;
      });
      if (best) return [best];
    }

    // Nothing to choose with: show them all rather than pick one arbitrarily.
    return candidates;
  }

  /**
   * Every box on this sheet carrying the same value, type and dimension kind — including the
   * entity asked about.
   *
   * One predicate, used by `findMatches` to build its candidates and by `groupFractionOf` to
   * place an entity among its peers. Two copies of "what counts as the same value here" would
   * put the two sides of the comparison in different groups while both kept working.
   */
  private peersOf(value: string, entityType: string, dimKind: number | null): EntityBox[] {
    return this.boxes.filter(
      (b) =>
        entityValueOf(b.entity) === value &&
        String(b.entity?.type) === entityType &&
        dimensionKindOf(b.entity) === dimKind,
    );
  }

  /**
   * Where an entity sits inside the bounding box of its own value-group, as fractions.
   *
   * This is the SOURCE half of the group tie-break; `findMatches` computes the target half the
   * same way. `null` when the value appears only once, or when the group is degenerate along
   * both axes — there is no ordering to publish, and a fabricated 0.5 would be a claim.
   */
  groupFractionOf(ent: any): { cfx: number; cfy: number } | null {
    const id = String(ent?.id ?? '');
    const peers = this.peersOf(entityValueOf(ent), String(ent?.type), dimensionKindOf(ent));
    if (peers.length <= 1) return null;
    const self = peers.find((b) => b.id === id);
    const group = groupBounds(peers);
    if (!self || !group) return null;
    const q = fractionIn(group, self);
    return q ? { cfx: q.fx, cfy: q.fy } : null;
  }

  /**
   * The entity under a flipped-world point, or null.
   *
   * **Smallest match wins.** A dimension's text sits inside the polyline of the view that
   * contains it, and inside the border rectangle of the whole sheet; picking by z-order or by
   * first-hit would hand back the border every time. Area is the ordering a person expects —
   * the thing you aimed at is the smallest thing under the cursor.
   *
   * `tolerance` is in world units and is applied as a uniform outset, so a zero-area entity (a
   * horizontal line has no height) is still reachable.
   */
  hitTest(worldX: number, worldY: number, tolerance = 0): any | null {
    const hits: { b: EntityBox; annotation: boolean; centreDist: number; area: number }[] = [];

    for (const b of this.boxes) {
      if (
        worldX < b.x0 - tolerance ||
        worldX > b.x1 + tolerance ||
        worldY < b.y0 - tolerance ||
        worldY > b.y1 + tolerance
      ) {
        continue;
      }
      const cx = (b.x0 + b.x1) / 2;
      const cy = (b.y0 + b.y1) / 2;
      hits.push({
        b,
        annotation: ANNOTATION_TYPES.has(String(b.entity?.type)),
        centreDist: Math.hypot(worldX - cx, worldY - cy),
        // A degenerate box (a horizontal line has no height) would otherwise always win on
        // area 0, beating the text drawn on top of it. Floor both extents.
        area:
          Math.max(b.x1 - b.x0, MIN_HALF_EXTENT) * Math.max(b.y1 - b.y0, MIN_HALF_EXTENT),
      });
    }

    if (!hits.length) return null;

    // **Annotations outrank geometry.** Someone aiming inside a view is aiming at a value, not
    // at the circle it is printed over. Without this, a dimension label sitting on a concentric
    // arc is unreachable whenever the arc's box happens to be the smaller of the two.
    const annotations = hits.filter((h) => h.annotation);
    const pool = annotations.length ? annotations : hits;

    // The two classes want opposite tie-breaks, and using one rule for both is wrong twice.
    //
    // **Annotations: nearest centre.** Dense radial views stack labels whose axis-aligned boxes
    // overlap heavily (`⌀145`, `⌀183`, `⌀110` on one hub). Smallest-area returns the same label
    // wherever you click inside the cluster, so the others cannot be selected at all;
    // nearest-centre follows the cursor and makes each reachable by clicking toward it.
    //
    // **Geometry: smallest area.** Here nearest-centre is actively wrong — a large circle
    // centred near the cursor would beat the short line segment actually under it. Size is what
    // separates "the thing I pointed at" from "the thing it sits inside".
    if (annotations.length) {
      pool.sort((p, q) => p.centreDist - q.centreDist || p.area - q.area);
    } else {
      pool.sort((p, q) => p.area - q.area || p.centreDist - q.centreDist);
    }
    return pool[0].b.entity;
  }
}
