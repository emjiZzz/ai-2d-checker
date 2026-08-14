import { flipWorldY, getNormalization, worldToScreen } from '../../utils/coordinateTransform';
import type { ViewDatum } from './viewDatums';
import {
  VIEWS_EXCLUDED_ZONES,
  ZONE_KEYS,
  isPlaceholderOnly,
  type DrawingZonesResponse,
} from '../../services/drawingsApi';
import {
  fractionsToScreenRect,
  isPolygonZone,
  shapePointsToScreen,
  type RegionFractions,
} from '../../utils/zoneFractions';
import { HIDE_SECTION_CALLOUTS, sectionCalloutsForLayers } from './sectionCallouts';


// Helper utility to strip any residual AutoCAD MTEXT formatting/styling tags and convert escape codes
export const cleanCadText = (text: string): string => {
  if (!text) return "";
  let clean = text;
  clean = clean.replace(/ラ/g, "x");
  clean = clean.replace(/[{}]/g, "");
  clean = clean.replace(/\\[A-Za-z][^;]*;/g, "");
  clean = clean.replace(/\\P/g, " ");
  // Convert legacy AutoCAD control escape codes to standard engineering symbols
  clean = clean.replace(/%%c/gi, "⌀");
  clean = clean.replace(/%%d/gi, "°");
  clean = clean.replace(/%%p/gi, "±");
  clean = clean.replace(/%%[uo]/gi, "");
  return clean.trim();
};

export const getPrintColor = (color: string): string => {
  if (!color) return '#0f172a';
  const cleanColor = color.trim().toLowerCase();

  if (cleanColor.startsWith('#')) {
    let hex = cleanColor;
    if (hex.length === 4) {
      hex = '#' + hex[1] + hex[1] + hex[2] + hex[2] + hex[3] + hex[3];
    }

    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);

    if (r > 220 && g > 220 && b > 220) {
      return '#0f172a';
    }

    const brightness = (r * 299 + g * 587 + b * 114) / 1000;
    if (brightness > 150) {
      if (r > 200 && g > 200 && b < 100) {
        return '#b45309';
      }
      if (r < 100 && g > 180 && b > 180) {
        return '#0284c7';
      }
      if (g > 180 && r < 120 && b < 120) {
        return '#15803d';
      }
      const dr = Math.round(r * 0.45);
      const dg = Math.round(g * 0.45);
      const db = Math.round(b * 0.45);
      const toHex = (c: number) => c.toString(16).padStart(2, '0');
      return `#${toHex(dr)}${toHex(dg)}${toHex(db)}`;
    }
    return hex;
  }

  const nameMap: Record<string, string> = {
    'white': '#0f172a',
    'yellow': '#b45309',
    'cyan': '#0284c7',
    'green': '#15803d',
    'lime': '#166534',
    'magenta': '#701a75',
    'pink': '#be185d',
    'lightgray': '#475569',
    'gray': '#64748b'
  };

  return nameMap[cleanColor] || color;
};

// ─── CAD text metrics and placement ───────────────────────────────────────────
//
// Everything below exists because a DXF describes text in CAD terms and a canvas draws it in
// CSS terms, and the two disagree on three separate axes: where the anchor is, how wide a
// glyph is, and what "height" means. All three were wrong at once, which is why the sheet
// could not be fixed by eye — narrowing the text and enlarging it move the same measurement in
// opposite directions. `tools/render_audit.py` measures each independently against the
// backend's own ezdxf raster; the numbers quoted here are from M745221N01.

/**
 * Font stack for CAD text.
 *
 * Mirrors the SHX→TTF substitution the raster path makes (`SHX_NAMES_TO_OVERRIDE` in
 * `dxf_render_setup.py`, which points `txt`/`extfont2` at MS Gothic). Both render modes have to
 * resolve to the same glyphs or every width measurement disagrees between them.
 */
const CAD_FONT_STACK =
  '"MS Gothic", "Yu Gothic UI", "Meiryo", "JetBrains Mono", monospace, sans-serif';

/**
 * Cap-height/em fallback, used when the canvas cannot measure — jsdom's canvas mock returns 0
 * for every TextMetrics field. 0.7617 is MS Gothic's measured value.
 */
const DEFAULT_CAP_HEIGHT_RATIO = 0.7617;

/**
 * CSS pixels per millimetre of lineweight, at any zoom.
 *
 * Only reached when the drawing asks for lineweights to be displayed — see `$LWDISPLAY` below.
 *
 * Lineweight is a *plotting* property — how thick the pen is on paper — not a dimension of the
 * geometry, so CAD viewers display it at a constant screen thickness and iCAD SX is no
 * exception. 96/25.4 is the CSS reference (1 inch = 96 px).
 *
 * ⚠ This deliberately diverges from the ezdxf raster at high zoom. ezdxf's default
 * `LineweightPolicy.ABSOLUTE` bakes the weights into the PNG proportionally to the sheet, so
 * zooming the bitmap scales them; drawing vectors that way was tried and turns a 1.00mm frame
 * line into a ~15px slab once you zoom into the title block. Matching the live CAD viewer beats
 * matching the bitmap here, because the bitmap is only a stand-in for it.
 */
const LINEWEIGHT_DISPLAY_PX_PER_MM = 96 / 25.4;

/** Nothing on a drawing needs to be thicker than this on screen. */
const MAX_LINEWEIGHT_DISPLAY_PX = 6;

/**
 * Snaps a world coordinate so the stroke centred on it lands on the device pixel grid.
 *
 * A stroke of width `w` device px centred at device coordinate `c` covers `c ± w/2`. That fills
 * whole pixels only when `c` is a half-integer for odd `w`, or an integer for even `w`. At any
 * other phase the browser splits the ink across two columns — **measured**: a 1px hairline at
 * phase 0 comes out as two columns at alpha 0.498 / 0.502. Total ink is conserved at exactly
 * 1.0, so the line is not thicker; it is *spread*, which reads as roughly half a pixel of extra
 * width per side against a CAD viewer that snaps (iCAD SX does).
 *
 * `transX`/`transY` derive from an arbitrary pan offset, so without this every axis-aligned rule
 * on the sheet lands at a random phase.
 *
 * Only meaningful for axis-aligned geometry: snapping one end of a diagonal moves the line rather
 * than sharpening it, so callers must check. See `snapPhaseFor`.
 */
export const snapWorldToDeviceGrid = (
  world: number, viewScale: number, translate: number, dpr: number, phase: number
): number => {
  const device = dpr * (translate + viewScale * world);
  const snapped = Math.round(device - phase) + phase;
  return ((snapped / dpr) - translate) / viewScale;
};

/**
 * Target sub-pixel phase for a stroke of `deviceWidth` device pixels: half-integer for odd
 * widths (the hairline case, and the only one this corpus exercises since `$LWDISPLAY` is 0),
 * integer for even. Non-integer widths cannot land cleanly at any phase; the nearest half still
 * beats a random one, so they take the odd branch.
 */
export const snapPhaseFor = (deviceWidth: number): number =>
  Math.round(deviceWidth) % 2 === 0 ? 0 : 0.5;

/** True when every segment of the vertex chain runs exactly horizontal or vertical. */
export const isAxisAlignedChain = (verts: number[][]): boolean => {
  for (let i = 1; i < verts.length; i++) {
    const dx = Math.abs(verts[i][0] - verts[i - 1][0]);
    const dy = Math.abs(verts[i][1] - verts[i - 1][1]);
    if (dx > 1e-9 && dy > 1e-9) return false;
  }
  return true;
};

/** MTEXT line advance as a multiple of char height, measured against ezdxf's own renderer. */
//
// AutoCAD documents the MTEXT default as 1.667x char height between baselines, but ezdxf --
// which produces the raster this canvas is matched against -- lays the wrapped title-block
// headers out at 1.0x (measured: 3.010 and 2.890 for a char height of 3.0). Matching ezdxf is
// the right call while the raster is the ground truth; revisit this constant first if wrapped
// text ever looks too tight or too loose.
const MTEXT_LINE_ADVANCE = 1.0;

const capHeightRatioCache = new Map<string, number>();

/**
 * Cap height as a fraction of the em square, for a given font size + stack.
 *
 * DXF text `height` is the **cap** height. CSS `font-size` sets the **em** size. ezdxf, and
 * every CAD viewer, scales glyphs so the cap height lands exactly on the DXF height — so
 * `font: ${height}px` draws every string at roughly 76% of its correct size. Measured against
 * the ezdxf raster before this fix, `height_ratio` was a flat 0.7617 across all 221 comparable
 * strings on the sheet: not a scattering of small errors, one systematic factor.
 *
 * Measured once per font stack and cached; `measureText` is transform-independent, so the
 * caller's transform does not matter.
 */
const getCapHeightRatio = (ctx: CanvasRenderingContext2D, fontStack: string): number => {
  const cached = capHeightRatioCache.get(fontStack);
  if (cached !== undefined) return cached;

  let ratio = DEFAULT_CAP_HEIGHT_RATIO;
  const previousFont = ctx.font;
  try {
    const PROBE_PX = 100;
    ctx.font = `${PROBE_PX}px ${fontStack}`;
    const ascent = ctx.measureText('H').actualBoundingBoxAscent;
    const measured = ascent / PROBE_PX;
    // Reject nonsense rather than propagate it: a stub canvas reports 0, and a ratio outside
    // this band would mean the probe resolved a font with no cap height at all.
    if (Number.isFinite(measured) && measured > 0.4 && measured < 1.0) {
      ratio = measured;
    }
  } catch {
    // Non-measuring canvas (test mock). Keep the fallback.
  } finally {
    ctx.font = previousFont;
  }

  capHeightRatioCache.set(fontStack, ratio);
  return ratio;
};

/** Where the insert point sits vertically relative to the text. */
type VerticalAnchor = 'top' | 'middle' | 'bottom';

/** MTEXT attachment points 1-9, row-major from top-left. */
const MTEXT_H_ALIGN: CanvasTextAlign[] = ['left', 'center', 'right'];
const MTEXT_V_ALIGN: VerticalAnchor[] = ['top', 'middle', 'bottom'];

/**
 * Distance from the insert point down to the first line's BASELINE, in CSS pixels.
 *
 * The canvas is always drawn with `textBaseline: 'alphabetic'` and this offset applied by hand,
 * rather than letting `textBaseline` do the work. That is deliberate, and it fixes a defect that
 * touched 215 of 247 strings on M745221N01:
 *
 *   `textBaseline: 'bottom'` aligns the bottom of the font's EM BOX to the anchor. A DXF bottom
 *   attachment aligns the BASELINE. The gap between them is the font's descender — 0.18 of the
 *   cap height for MS Gothic — so every bottom-anchored string was drawn that much too HIGH:
 *   0.39 drawing units at char height 2.2, 1.44 at char height 8.0. In a title-block cell around
 *   5 units tall that is enough for the text to ride up into the rule above it, which is exactly
 *   how it was reported.
 *
 *   The measurement oracle could not catch it either, because it compares where the *insert
 *   point* lands against ezdxf's ink box and never models what the canvas does with
 *   `textBaseline`. Deriving the offset from the DXF cap height removes the browser's
 *   ascent/descent metrics from the calculation entirely, so the two can no longer disagree.
 *
 * Screen Y grows downward, so a positive result moves the baseline down the page.
 */
const baselineOffsetPx = (
  anchor: VerticalAnchor,
  capHeightPx: number,
  lineCount: number,
  lineAdvancePx: number,
): number => {
  switch (anchor) {
    case 'top':
      // The first line's cap top sits on the anchor.
      return capHeightPx;
    case 'middle':
      // The block's vertical centre sits on the anchor.
      return (capHeightPx - (lineCount - 1) * lineAdvancePx) / 2;
    default:
      // 'bottom' — the LAST line's baseline sits on the anchor.
      return -(lineCount - 1) * lineAdvancePx;
  }
};

/**
 * Canvas anchor for an MTEXT attachment point.
 *
 * The renderer used to draw every string left-aligned on the alphabetic baseline, which is
 * correct only for attachment point 7 (bottom-left). On M745221N01 that is 122 of 228 strings;
 * the other 106 — the centred and right-aligned title-block and tolerance-table cells — were
 * displaced by up to a full string width (measured max dx: 33.3 drawing units).
 *
 * Only applied to MTEXT. A plain TEXT entity with a non-default `halign`/`valign` stores its
 * real anchor in the DXF `align_point` (group 11) rather than `insert` (group 10), and the
 * mapper does not extract that — so applying alignment to TEXT would centre it on the wrong
 * point and make things worse. This corpus has exactly one TEXT entity; see the note in
 * `drawCadText`.
 */
const attachmentAnchor = (
  attachmentPoint: unknown,
): { align: CanvasTextAlign; vAlign: VerticalAnchor } => {
  const index = (Number(attachmentPoint) || 0) - 1;
  // Out of range covers both a missing value and the invalid 0 one entity on this sheet
  // carries. Bottom-left is the DXF-neutral reading and the one ezdxf's ink agrees with.
  if (index < 0 || index > 8) {
    return { align: 'left', vAlign: 'bottom' };
  }
  return {
    align: MTEXT_H_ALIGN[index % 3],
    vAlign: MTEXT_V_ALIGN[Math.floor(index / 3)],
  };
};

/**
 * How far a string must exceed its MTEXT column width before the canvas breaks it.
 *
 * Not a style choice — it is the size of a measurement error we cannot remove. The browser
 * measures with its own MS Gothic; ezdxf measures with fontTools; the two disagree by a couple
 * of percent, and a canvas `measureText` returns the ADVANCE width while a column width was
 * authored against the ink.
 *
 * Measured on M745221N01: of 247 MTEXT entities carrying a column width, **99 would wrap at
 * zero tolerance and every one of them is over by less than 6%** — most by exactly 3.0%, which
 * is the signature of an exporter that set each column to its own text's natural width. None of
 * those breaks is intended. Honouring them put a lone `）` on a line of its own in
 * `４ロール：２４（４×６台）` and split single characters off title-block headers.
 *
 * 1.15 sits clear of that noise band. The cost is that a genuine knife-edge wrap — ezdxf breaks
 * `材 質` at ~4% over — renders on one line instead of two. That is the right trade: a slightly
 * wide string reads correctly, a one-character orphan reads as a broken drawing.
 */
const MTEXT_WRAP_TOLERANCE = 1.15;

/**
 * Greedy wrap against an MTEXT column width, with an orphan guard.
 *
 * Breaks on spaces where possible and mid-string otherwise, because CJK has no spaces and a
 * two-character header still has to wrap somewhere.
 *
 * Refuses to produce a final line of one character. That is the specific damage reported on
 * this sheet — a closing parenthesis, or a single digit, dropped onto its own line — and it is
 * never what a title block intends. When the only available break would orphan a character, the
 * string is left long and allowed to overflow its cell instead.
 */
const wrapCadText = (
  ctx: CanvasRenderingContext2D,
  text: string,
  maxWidth: number,
): string[] => {
  if (!(maxWidth > 0)) return [text];
  if (ctx.measureText(text).width <= maxWidth * MTEXT_WRAP_TOLERANCE) return [text];

  const lines: string[] = [];
  let current = '';
  let lastBreak = -1;

  for (const char of text) {
    const candidate = current + char;
    if (current && ctx.measureText(candidate).width > maxWidth) {
      if (lastBreak > 0) {
        lines.push(current.slice(0, lastBreak).trimEnd());
        current = current.slice(lastBreak).trimStart() + char;
      } else {
        lines.push(current);
        current = char;
      }
      lastBreak = -1;
    } else {
      current = candidate;
      if (char === ' ') lastBreak = current.length;
    }
  }
  if (current) lines.push(current);

  if (lines.length < 2) return [text];
  // Orphan guard. A trailing single character is worse than an overlong line.
  if ([...lines[lines.length - 1]].length <= 1) return [text];
  return lines;
};

interface CadTextOptions {
  /** Screen-space anchor, in CSS pixels. */
  x: number;
  y: number;
  text: string;
  /** DXF text height (cap height) already converted to CSS pixels. */
  capHeightPx: number;
  color: string;
  /** Degrees counter-clockwise in DXF space. */
  rotation?: number;
  /** MTEXT attachment point 1-9, or undefined for baseline-left. */
  attachmentPoint?: unknown;
  /** Inline `\W` horizontal glyph scaling. */
  widthFactor?: number;
  /** MTEXT column wrap width in CSS pixels; 0 or undefined disables wrapping. */
  columnWidthPx?: number;
  /** Force a specific anchor, overriding `attachmentPoint` (dimension text is centred). */
  align?: CanvasTextAlign;
  vAlign?: VerticalAnchor;
}

/**
 * The single place CAD text reaches the canvas.
 *
 * Shared by the TEXT branch and the DIMENSION measurement branch, which previously had two
 * near-identical copies of the placement maths that had already drifted apart (different font
 * stacks, different LOD floors). Every correction — cap height, attachment point, width factor,
 * tracking, wrapping — has to apply to both or dimension values sit differently from the text
 * beside them.
 *
 * Assumes the caller has already reset the transform to device pixels.
 */
const drawCadText = (ctx: CanvasRenderingContext2D, opts: CadTextOptions): void => {
  const {
    x, y, text, capHeightPx, color, rotation = 0,
    attachmentPoint, widthFactor, columnWidthPx = 0,
  } = opts;
  if (!text || capHeightPx <= 0) return;

  // Convert the DXF cap height into the em size the canvas actually wants.
  const emPx = capHeightPx / getCapHeightRatio(ctx, CAD_FONT_STACK);

  const anchor = attachmentAnchor(attachmentPoint);
  const align = opts.align ?? anchor.align;
  const vAlign = opts.vAlign ?? anchor.vAlign;

  // `\W` scales the glyphs horizontally. It was extracted as `width_factor` and never applied,
  // so every string rendered at its natural width — on this sheet 248 of 249 MTEXT entities
  // carry a `\W` between 0.60 and 0.91, i.e. essentially the whole drawing was 10-40% too wide.
  //
  // ⛔ `\T` (tracking) is deliberately NOT applied, and this is a measured decision rather than
  // an omission. Folding it into the same scale was tried first and made every string too
  // narrow by exactly the tracking factor: across the 81 comparable strings that carry a `\T`,
  // `width_ratio` came out equal to `tracking` to within 0.019. ezdxf — which draws the raster
  // this canvas is matched against, and which the iCAD SX comparison accepts — applies `\W`
  // only. Applying tracking here would put the two render modes back out of agreement.
  // `properties.tracking` is still extracted; it is just not a glyph scale.
  const wf = Number(widthFactor);
  const horizontalScale = Number.isFinite(wf) && wf > 0 ? wf : 1;

  ctx.save();
  ctx.fillStyle = color;
  ctx.font = `${emPx}px ${CAD_FONT_STACK}`;
  ctx.textAlign = align;
  // Always 'alphabetic'. The vertical anchor is applied by hand below, from the DXF cap height
  // rather than from the font's ascent/descent — see `baselineOffsetPx`.
  ctx.textBaseline = 'alphabetic';

  ctx.translate(x, y);
  // DXF rotation is degrees counter-clockwise; screen Y is already flipped by the caller, so
  // the canvas rotation is the negation.
  if (rotation) ctx.rotate((-rotation * Math.PI) / 180);
  if (horizontalScale !== 1) ctx.scale(horizontalScale, 1);

  // Wrapping is measured in the post-scale space, which is where the column width lives.
  const lines =
    columnWidthPx > 0
      ? wrapCadText(ctx, text, columnWidthPx / (horizontalScale || 1))
      : [text];

  // MTEXT grows downward from its attachment row: a bottom-anchored block has its LAST line on
  // the anchor, a top-anchored block its first, and a middle-anchored block is centred.
  const advance = capHeightPx * MTEXT_LINE_ADVANCE;
  const firstBaseline = baselineOffsetPx(vAlign, capHeightPx, lines.length, advance);
  lines.forEach((line, i) => ctx.fillText(line, 0, firstBaseline + i * advance));

  ctx.restore();
};

export interface RenderFrame {
  ctx: CanvasRenderingContext2D;
  isExport: boolean;
  renderWidth: number;
  renderHeight: number;
  width: number;
  height: number;
  norm: ReturnType<typeof getNormalization>;
  scale: number;
  transX: number;
  transY: number;
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
  currentViewportScale: number;
  resolutionMultiplier: number;
  viewport: { x: number; y: number; scale: number };
  markerPositionsRef: React.MutableRefObject<Record<string, { x: number, y: number }>>;
  isNeonModeActive?: boolean;
}

export interface RenderEntitiesParams {
  frame: RenderFrame;
  layers: Record<string, any[]>;
  activeLayers: Record<string, boolean>;
  theme: string;
  drawing?: any;
}

export const renderEntities = ({
  frame,
  layers,
  activeLayers,
  theme: _theme,
  drawing
}: RenderEntitiesParams): { totalEntities: number; drawnEntities: number } => {
  const { ctx, isExport, renderWidth, renderHeight, scale, transX, transY, minX, minY, maxX, maxY, resolutionMultiplier, norm } = frame;

  const flipY = (y: number) => flipWorldY(y, norm);

  const dpr = typeof window !== 'undefined' ? window.devicePixelRatio || 1 : 1;

  let totalEntities = 0;
  let drawnEntities = 0;

  // Section-view identifiers (`Ａ－Ａ` and the lone `Ａ` at each cut arrow). Resolved once per
  // payload and memoised on the layers object, because the answer needs the whole sheet — a lone
  // letter only qualifies when a matching designation exists elsewhere on it — and this function
  // reruns on every pan and zoom. See sectionCallouts.ts for why the frame's grid labels survive.
  const sectionCallouts = HIDE_SECTION_CALLOUTS
    ? sectionCalloutsForLayers(layers, cleanCadText)
    : null;

  // One device pixel. This is the floor for every stroke, and it is the whole point of
  // rendering vectors: 1.5 CSS px cannot land on the pixel grid, so it straddles two device
  // pixels and antialiases into a pair of greys — the same soft edge the raster path produces.
  // `1 / dpr` CSS px is exactly 1 device pixel, which is what a CAD viewer draws a hairline as
  // at every zoom level.
  const hairlinePx = isExport ? 1.0 : 1 / dpr;

  // `$LWDISPLAY` — does this drawing want its lineweights drawn at all?
  //
  // An entity can record 1.00mm and still be meant to display as a hairline: the weight is a
  // plotting instruction, and this header is the switch deciding whether the viewer honours it
  // on screen. It is **0 on both M745221N01 files**, which is exactly why iCAD SX shows uniform
  // thin linework on a sheet carrying 1.00mm on 136 entities and 0.50mm on 331.
  //
  // Defaults to OFF when absent, which covers both the DXF default and any drawing ingested
  // before this was extracted. That is also the conservative direction: too-thin linework looks
  // like the old behaviour, too-thick looks broken.
  const showLineweights = drawing?.metadata?.lineweight_display === true;

  /** Device-pixel width this entity's stroke will actually be painted at. */
  const deviceWidthFor = (strokeWidthMm: number): number => {
    const widthPx = showLineweights
      ? Math.min(MAX_LINEWEIGHT_DISPLAY_PX, strokeWidthMm * LINEWEIGHT_DISPLAY_PX_PER_MM)
      : 0;
    return Math.max(hairlinePx, widthPx) * dpr;
  };

  // Pixel snapping is a screen-crispness fix and is skipped on export: that path renders at
  // 7016px with its own transform and no dpr, where half a pixel is meaningless.
  const snapEnabled = !isExport;
  const snapX = (wx: number, phase: number) =>
    snapEnabled ? snapWorldToDeviceGrid(wx, scale, transX, dpr, phase) : wx;
  const snapY = (wy: number, phase: number) =>
    snapEnabled ? snapWorldToDeviceGrid(wy, scale, transY, dpr, phase) : wy;

  const pathBatches: Record<string, { stroke: string, width: number, dash: number[] | null, dashUnits: string, path: Path2D }> = {};
  // Filled polygons, kept separate from the stroked batches because they need `fill()`
  // rather than `stroke()`. In practice these are dimension arrowheads.
  const fillBatches: Record<string, { color: string, path: Path2D }> = {};

  Object.entries(layers).forEach(([layerName, entities]) => {
    if (activeLayers[layerName] === false) return;

    entities.forEach((ent) => {
      // Counted before any cull so the HUD denominator is every entity in the payload —
      // including the `layer` and `block` records that can never be drawn. On M745221N01
      // the healthy reading is 497/518, not 518/518. See ADR-011.
      totalEntities++;

      const geo = ent.geometry;
      if (!geo) return;

      // Model-space geometry that fell outside every paper-space viewport window. The
      // projector still gives it a coordinate (deterministic and invertible, by design),
      // but a viewport shows only its own window, so CAD clips this and the ezdxf raster
      // never draws it. Rendering it anyway put a phantom section label on the sheet at a
      // plausible-but-wrong position — present in vector mode, absent in raster and in
      // iCAD SX. Skipped only for drawing; the entity stays in the comparison set.
      if (ent.properties?.outside_viewport) return;

      // The section IDENTIFIER is draughting furniture: which letter names a cut says nothing
      // about the part, and it re-letters freely between revisions. The comparison already
      // ignores it (orchestrator.DROP_SECTION_CALLOUT_LABELS); this stops it being painted too,
      // so the sheet does not show a label that produces no finding. The section's CONTENT — the
      // dimensions and callouts inside the view it names — is drawn and compared as before.
      if (sectionCallouts?.has(ent)) return;

      let strokeColor = ent.style?.stroke || ent.properties?.stroke || '#00e5ff';
      if (isExport) {
        strokeColor = getPrintColor(strokeColor);
      }
      const strokeWidth = ent.style?.strokeWidth || ent.properties?.strokeWidth || 1;
      // Dash pattern joins the batch key: batching purely on colour+width merged hidden
      // and centre lines into the solid batch, so a mechanical drawing rendered every
      // construction line as continuous. That is a semantic error, not a cosmetic one.
      const dashPattern: number[] | null = Array.isArray(ent.style?.dash) ? ent.style.dash : null;
      // 'world' = real LTYPE elements in drawing units; 'screen' = the legacy fixed [5,5] in
      // CSS pixels, kept for payloads ingested before the pattern was extracted. The two need
      // different conversions, so the unit space has to travel with the array — and it joins
      // the batch key, or a stale entity's screen-space dashes would be applied to a
      // world-space batch.
      const dashUnits: string = dashPattern ? (ent.style?.dashUnits || 'screen') : 'none';
      const batchKey = `${strokeColor}_${strokeWidth}_${dashPattern ? dashPattern.join(',') : 'solid'}_${dashUnits}`;

      if (ent.type === 'text' && (geo.location || geo.insert)) {
        const [tx, tyRaw] = geo.location || geo.insert;
        const ty = flipY(tyRaw);

        const screenX = tx * scale + transX;
        const screenY = ty * scale + transY;
        const baseHeight = ent.properties?.height || ent.style?.fontSize || 12;
        const screenHeight = baseHeight * scale * 1.0;

        // LOD floor for text. Dropped from 4px to 2px: at fit-to-screen zoom a 4px floor
        // culled the entire general-tolerance table and most of the title block, so the
        // vector render showed those tables as empty grids. 2px is still a smear, but a
        // reviewer can see that content EXISTS there and zoom in; absent content reads as
        // a drawing that does not have it, which in a checking tool is the dangerous
        // failure. Below 2px the glyphs carry no information at all, so the cull stays.
        if (screenHeight < (isExport ? 1 : 2)) return;
        if (!isExport && (screenX < -500 || screenX > renderWidth + 500 || screenY < -500 || screenY > renderHeight + 500)) return;

        drawnEntities++;

        ctx.save();
        const localDpr = typeof window !== 'undefined' ? window.devicePixelRatio || 1 : 1;
        ctx.setTransform(localDpr, 0, 0, localDpr, 0, 0);

        let textColor = ent.style?.stroke || ent.style?.fill || '#ffffff';
        if (isExport) {
          textColor = getPrintColor(textColor);
        }

        const rawText = geo.text || geo.content || ent.properties?.text || '';
        const textVal = cleanCadText(rawText);

        if (textVal) {
          // Regular weight, not bold. The `bold` here was compensating for the raster path's
          // washed-out downsampled glyphs; applied to text actually rasterised at screen size
          // it just thickens every stroke into its neighbours, which on 4-6px CJK title-block
          // text is the difference between legible and a smudge. CAD text is not bold.
          //
          // Alignment is applied for MTEXT only. A plain TEXT entity with a non-default
          // halign/valign anchors on the DXF `align_point` (group 11), which `map_text` does
          // not extract — so honouring its alignment against the `insert` point would move it
          // to the wrong place. Passing `undefined` keeps the old baseline-left behaviour,
          // which is correct for default-aligned TEXT. This corpus has one TEXT entity in 250.
          const isMText = ent.properties?.is_multiline === true;
          drawCadText(ctx, {
            x: screenX,
            y: screenY,
            text: textVal,
            capHeightPx: screenHeight,
            color: textColor,
            rotation: Number(ent.properties?.rotation) || 0,
            attachmentPoint: isMText ? ent.properties?.attachment_point : undefined,
            widthFactor: ent.properties?.width_factor,
            columnWidthPx: isMText ? (Number(ent.properties?.column_width) || 0) * scale : 0,
          });
        }
        ctx.restore();
        return;
      }

      if (!pathBatches[batchKey]) {
        pathBatches[batchKey] = { stroke: strokeColor, width: strokeWidth as number, dash: dashPattern, dashUnits, path: new Path2D() };
      }
      const p2d = pathBatches[batchKey].path;

      if (ent.type === 'line' && geo.start && geo.end) {
        const [x1, y1Raw] = geo.start;
        const [x2, y2Raw] = geo.end;
        let y1 = flipY(y1Raw);
        let y2 = flipY(y2Raw);
        let sx1 = x1, sx2 = x2;
        const left = Math.min(x1, x2);
        const right = Math.max(x1, x2);
        const top = Math.min(y1, y2);
        const bottom = Math.max(y1, y2);
        if (right < minX || left > maxX || bottom < minY || top > maxY) return;
        drawnEntities++;
        // Snap only the constant axis of an axis-aligned line, so the stroke lands on whole
        // device pixels instead of splitting across two. The varying axis is left alone —
        // moving an endpoint would shorten the line rather than sharpen it. Diagonals are
        // skipped entirely: there is no phase that makes a diagonal crisp.
        const phase = snapPhaseFor(deviceWidthFor(strokeWidth as number));
        if (Math.abs(y1 - y2) <= 1e-9) {
          y1 = y2 = snapY(y1, phase);
        } else if (Math.abs(x1 - x2) <= 1e-9) {
          sx1 = sx2 = snapX(x1, phase);
        }
        p2d.moveTo(sx1, y1);
        p2d.lineTo(sx2, y2);
      }
      else if (ent.type === 'circle' && (geo.center || geo.location)) {
        const [cx, cyRaw] = geo.center || geo.location;
        const cy = flipY(cyRaw);
        const r = geo.radius || ent.properties?.radius || 1;
        if (cx + r < minX || cx - r > maxX || cy + r < minY || cy - r > maxY) return;
        drawnEntities++;
        p2d.moveTo(cx + r, cy);
        p2d.arc(cx, cy, r, 0, 2 * Math.PI);
      }
      else if (ent.type === 'arc' && (geo.center || geo.location)) {
        const [cx, cyRaw] = geo.center || geo.location;
        const cy = flipY(cyRaw);
        const r = geo.radius || ent.properties?.radius || 1;
        const rawStart = (ent.properties?.start_angle ?? 0);
        const rawEnd = (ent.properties?.end_angle ?? 0);
        const startAngle = norm.hasBounds ? ((-rawEnd) * Math.PI) / 180 : (rawStart * Math.PI) / 180;
        const endAngle = norm.hasBounds ? ((-rawStart) * Math.PI) / 180 : (rawEnd * Math.PI) / 180;
        if (cx + r < minX || cx - r > maxX || cy + r < minY || cy - r > maxY) return;
        drawnEntities++;
        p2d.moveTo(cx + r * Math.cos(startAngle), cy + r * Math.sin(startAngle));
        p2d.arc(cx, cy, r, startAngle, endAngle, false);
      }
      else if (ent.type === 'dimension') {
        // A DIMENSION carries no drawable geometry of its own — only anchors, a
        // `measurement` and a dimstyle. `render_paths` / `render_fills` are the flattened
        // contents of its anonymous geometry block, produced server-side by
        // `EntityMapper._dimension_render_geometry`. Without this branch every dimension on
        // the sheet renders as nothing at all, which is exactly what sank the first attempt
        // to make vectors the default.
        const renderPaths: number[][][] = Array.isArray(geo.render_paths) ? geo.render_paths : [];
        const renderFills: number[][][] = Array.isArray(geo.render_fills) ? geo.render_fills : [];
        // `render_text` is the string the dimension's anonymous block ACTUALLY draws, harvested
        // at extraction by `_dimension_render_geometry`. Preferred over `properties.text`,
        // which `map_dimension` rebuilds from `actual_measurement` and which therefore loses
        // every prefix, suffix and tolerance stack the dimstyle bakes in. On this sheet
        // `dimpost` is empty and the override text is a bare '<>', so the ⌀ on three of the
        // four dimensions exists only here — the canvas showed "145" where iCAD shows "φ145".
        // `cleanCadText` converts the surviving `%%c` into the real symbol.
        //
        // '<>' is the DXF placeholder meaning "substitute the measurement here". When a file
        // omits `actual_measurement` the placeholder survives, and painting it literally would
        // stamp "<>" onto the drawing exactly where a reviewer expects the measured value.
        const rawDimText = String(ent.properties?.render_text ?? ent.properties?.text ?? '');
        const dimText = rawDimText.includes('<>') ? '' : cleanCadText(rawDimText);
        if (!renderPaths.length && !renderFills.length && !dimText) return;

        // Cull once against the union of every point rather than per sub-path.
        let dMinX = Infinity, dMaxX = -Infinity, dMinY = Infinity, dMaxY = -Infinity;
        const scan = (groups: number[][][]) => groups.forEach((pts) => pts.forEach((pt) => {
          const px = pt[0];
          const py = flipY(pt[1]);
          if (px < dMinX) dMinX = px;
          if (px > dMaxX) dMaxX = px;
          if (py < dMinY) dMinY = py;
          if (py > dMaxY) dMaxY = py;
        }));
        scan(renderPaths);
        scan(renderFills);
        if (dMinX !== Infinity && (dMaxX < minX || dMinX > maxX || dMaxY < minY || dMinY > maxY)) return;
        drawnEntities++;

        renderPaths.forEach((pts) => {
          if (pts.length < 2) return;
          p2d.moveTo(pts[0][0], flipY(pts[0][1]));
          for (let i = 1; i < pts.length; i++) p2d.lineTo(pts[i][0], flipY(pts[i][1]));
        });

        if (renderFills.length) {
          if (!fillBatches[strokeColor]) {
            fillBatches[strokeColor] = { color: strokeColor, path: new Path2D() };
          }
          const fp = fillBatches[strokeColor].path;
          renderFills.forEach((pts) => {
            if (pts.length < 3) return;
            fp.moveTo(pts[0][0], flipY(pts[0][1]));
            for (let i = 1; i < pts.length; i++) fp.lineTo(pts[i][0], flipY(pts[i][1]));
            fp.closePath();
          });
        }

        // The measurement string. `text_point` is the DXF text MIDPOINT, so it is drawn
        // centred on both axes rather than from a baseline-left origin like TEXT entities.
        const tp = geo.text_point || geo.def_point;
        if (dimText && tp) {
          const baseHeight = ent.properties?.text_height || ent.properties?.height || 2.5;
          const screenTextHeight = baseHeight * scale;
          if (screenTextHeight >= (isExport ? 1 : 4)) {
            const tx = tp[0] * scale + transX;
            const ty = flipY(tp[1]) * scale + transY;
            ctx.save();
            const localDpr = isExport ? 1 : dpr;
            ctx.setTransform(localDpr, 0, 0, localDpr, 0, 0);
            // The measurement string uses the colour of the text INSIDE the dimension block,
            // not the dimension's own stroke. They differ by design — green dimension lines
            // with yellow measurement text is the norm on this corpus — so falling back to
            // `stroke` painted every measurement green.
            let dimColor = ent.style?.textStroke || ent.style?.stroke || '#ffffff';
            if (isExport) dimColor = getPrintColor(dimColor);
            // `text_point` is the DXF text MIDPOINT, so the anchor is centred on both axes
            // rather than derived from an attachment point. The width factor and tracking come
            // from the block's MTEXT (all four dimensions here carry \W0.8;\T0.875;), which
            // the DIMENSION entity itself never records.
            drawCadText(ctx, {
              x: tx,
              y: ty,
              text: dimText,
              capHeightPx: screenTextHeight,
              color: dimColor,
              rotation: Number(ent.properties?.text_rotation ?? ent.properties?.rotation) || 0,
              widthFactor: ent.properties?.width_factor,
              align: 'center',
              vAlign: 'middle',
            });
            ctx.restore();
          }
        }
      }
      else if (
        // LEADER and MULTILEADER join this branch rather than getting their own: both are
        // just vertex chains, already extracted with `vertices` and already covered by
        // GEOMETRY_SCHEMA's projection. They had no branch at all, so every leader line on
        // the sheet rendered as nothing — the pointer strokes on callouts like `6-9キリ`
        // vanished while their text stayed, leaving annotations floating unattached.
        (ent.type === 'polyline' || ent.type === 'ellipse' || ent.type === 'spline' ||
          ent.type === 'leader' || ent.type === 'multileader') &&
        (geo.vertices || geo.points)
      ) {
        const rawVertices = geo.vertices || geo.points;
        if (rawVertices.length < 2) return;
        let vertices = rawVertices.map(([vx, vy]: [number, number]) => [vx, flipY(vy)]);
        // Snap only when EVERY segment is axis-aligned — the frames, title-block cells and
        // table rules, which is the bulk of the sheet (194 of 249 straight segments on
        // M745221N01_FSRS2_KMTI). Snapping both axes of every vertex keeps such a chain closed,
        // so rectangles stay rectangles. A mixed chain is left alone: snapping one segment of it
        // detaches that segment from its diagonal neighbour and opens a visible kink.
        if (snapEnabled && isAxisAlignedChain(vertices)) {
          const phase = snapPhaseFor(deviceWidthFor(strokeWidth as number));
          vertices = vertices.map(([vx, vy]: [number, number]) => [
            snapX(vx, phase),
            snapY(vy, phase),
          ]);
        }
        let pMinX = Infinity, pMaxX = -Infinity, pMinY = Infinity, pMaxY = -Infinity;
        vertices.forEach(([vx, vy]: [number, number]) => {
          if (vx < pMinX) pMinX = vx;
          if (vx > pMaxX) pMaxX = vx;
          if (vy < pMinY) pMinY = vy;
          if (vy > pMaxY) pMaxY = vy;
        });
        if (pMaxX < minX || pMinX > maxX || pMaxY < minY || pMinY > maxY) return;
        drawnEntities++;
        p2d.moveTo(vertices[0][0], vertices[0][1]);
        for (let i = 1; i < vertices.length; i++) {
          p2d.lineTo(vertices[i][0], vertices[i][1]);
        }
        // A closed ellipse or polyline was stroked as an open chain, leaving a visible gap
        // where the outline should meet. On an isometric view — which is mostly closed
        // ellipses, and is why ellipses are extracted at all — that reads as broken geometry.
        if (ent.properties?.is_closed || ent.properties?.closed) {
          p2d.closePath();
        }
      }
    });
  });

  Object.values(pathBatches).forEach(batch => {
    ctx.strokeStyle = batch.stroke;

    // `strokeWidth` is MILLIMETRES OF PAPER (the DXF lineweight enum / 100) and has to be
    // converted before use — it used to be read as though it were already CSS pixels, so 0.25,
    // 0.50 and 1.00 all fell under the one-pixel floor and collapsed to a single hairline.
    //
    // Converted at a fixed px-per-mm and NOT scaled by the view, because lineweight is a
    // plotting property rather than a dimension of the geometry. See
    // LINEWEIGHT_DISPLAY_PX_PER_MM for why that beats matching the raster bitmap.
    const widthPx = showLineweights
      ? Math.min(MAX_LINEWEIGHT_DISPLAY_PX, batch.width * LINEWEIGHT_DISPLAY_PX_PER_MM)
      : 0;
    ctx.lineWidth = (Math.max(hairlinePx, widthPx) / scale) * resolutionMultiplier;

    if (batch.dash) {
      // World-space dashes are already in the transform's units and pass through untouched —
      // a dash length is a property of the drawing, not of the zoom. The legacy screen-space
      // fallback still needs converting, since [5, 5] means CSS pixels and nothing else.
      ctx.setLineDash(
        batch.dashUnits === 'world'
          ? batch.dash
          : batch.dash.map((d) => (d / scale) * resolutionMultiplier)
      );
    }
    ctx.stroke(batch.path);
    if (batch.dash) ctx.setLineDash([]);
  });

  // Filled polygons last so arrowheads sit on top of the dimension lines they terminate.
  Object.values(fillBatches).forEach(batch => {
    ctx.fillStyle = batch.color;
    ctx.fill(batch.path);
  });

  return { totalEntities, drawnEntities };
};

export interface RenderViolationReticlesParams {
  frame: RenderFrame;
  violations: any[];
  showViolations: boolean;
  showMarkerLabels: boolean;
  hoveredMarkerId: string | null;
  selectedViolation: any | null;
  drawing?: any;
  oldDrawing?: any;
  visibleMarkerTypes: Record<string, boolean>;
}

export const renderViolationReticles = ({
  frame,
  violations,
  showViolations,
  showMarkerLabels,
  hoveredMarkerId,
  selectedViolation,
  drawing,
  oldDrawing,
  visibleMarkerTypes
}: RenderViolationReticlesParams) => {
  const { ctx, isExport, renderWidth, viewport, norm, resolutionMultiplier, markerPositionsRef } = frame;

  // Critical constraint: explicit filter reset to clear any Neon-CAD filter applied earlier in the pass
  if (frame.isNeonModeActive && !isExport) {
    ctx.filter = 'none';
  }

  if (!showViolations) return;

  // Marker cards are drawn on the canvas (not DOM), so they don't pick up the app's
  // CSS theme variables automatically — check the live theme attribute once per pass.
  const isLightTheme = typeof document !== 'undefined' && document.documentElement.getAttribute('data-theme') === 'hc-light';
  const cardBg = isLightTheme ? 'rgba(229, 233, 240, 0.95)' : 'rgba(38, 43, 54, 0.95)';
  const cardPrimaryText = isLightTheme ? '#18181b' : '#ffffff';
  const cardSecondaryText = isLightTheme ? 'rgba(24, 24, 27, 0.7)' : 'rgba(255, 255, 255, 0.7)';
  const cardBulletRing = isLightTheme ? '#e5e9f0' : '#262b36';

  const isOldDrawing = oldDrawing && drawing?.id === oldDrawing.id;
  const placedCardRects: { xMin: number; xMax: number; yMin: number; yMax: number }[] = [];

  const getPriority = (penType: string) => {
    if (penType === 'ai_red' || penType === 'checker_blue') return 3;
    if (penType === 'ai_orange') return 2;
    return 1;
  };

  const sortedViolationsWithIndex = violations.map((v: any, i: number) => ({ v, i })).sort((a, b) => {
    return getPriority(a.v.pen_type || 'ai_red') - getPriority(b.v.pen_type || 'ai_red');
  });

  sortedViolationsWithIndex.forEach(({ v, i: idx }) => {
    const penType = v.pen_type || 'ai_red';
    if (penType !== 'ai_red' && penType !== 'ai_orange' && penType !== 'checker_blue' && penType !== 'ai_green' && penType !== 'resolved_green' && penType !== 'ai_conflict') return;

    if (isOldDrawing && penType === 'checker_blue') return;
    if (!isOldDrawing && penType === 'ai_red') return;

    let markerType = 'MISMATCHED';
    if (penType === 'ai_orange') markerType = 'CHANGED';
    else if (penType === 'checker_blue') markerType = 'ADDED';
    else if (penType === 'ai_green' || penType === 'resolved_green') markerType = 'MATCHED';
    else if (penType === 'ai_conflict') markerType = 'CONFLICT';

    if (!visibleMarkerTypes[markerType]) return;

    // Level-of-Detail (LOD): Skip entirely if zoomed way out, unless it's the actively selected violation
    if (viewport.scale < 0.1 && selectedViolation?.id !== v.id) return;

    let coords = isOldDrawing ? v.ref_coordinates : v.coordinates;
    if (!coords) return;

    const [vx, raw_vy] = coords;
    const screenPos = worldToScreen(vx, raw_vy, norm, viewport);
    const isSelected = selectedViolation?.id === v.id;

    const bulletColor = penType === 'ai_red' ? '#ff2850' : penType === 'ai_orange' ? '#ff9600' : penType === 'checker_blue' ? '#00ffff' : penType === 'ai_conflict' ? '#c084fc' : '#39ff14';
    const statusLabel = penType === 'ai_red' ? 'MISMATCHED' : penType === 'ai_orange' ? 'CHANGED' : penType === 'checker_blue' ? 'ADDED' : penType === 'ai_conflict' ? 'CONFLICT' : 'MATCHED';

    let screenX = screenPos.x;
    let screenY = screenPos.y;

    // Threading marker positions ref directly for handleMouseMove click targets
    markerPositionsRef.current[v.id] = { x: screenX, y: screenY };

    ctx.save();
    const localDpr = isExport ? 1 : (typeof window !== 'undefined' ? window.devicePixelRatio || 1 : 1);
    ctx.setTransform(localDpr, 0, 0, localDpr, 0, 0);

    const isHoveredOrSelected = hoveredMarkerId === v.id || isSelected;
    // Level-of-Detail (LOD): Hide detailed text cards when zoomed out, unless explicitly hovered/selected
    const lodSkipCard = viewport.scale < 0.3 && !isHoveredOrSelected;

    const SHOW_MARKER_TARGETS = (showMarkerLabels && !lodSkipCard) || isHoveredOrSelected;
    if (SHOW_MARKER_TARGETS) {
      const rawVal = (isOldDrawing && v.original_value) ? v.original_value : (v.description || "");
      const displayVal = cleanCadText(rawVal);
      const displayCat = (v.category || "Physical Checklist").replace('_', ' ');
      const displayStat = `Stat: ${statusLabel}`;

      // For CONFLICT — only ever produced by the `hybrid` method, removed in ADR-006, so
      // this is reachable now only from a cached payload written before that. Kept for
      // exactly that reason: dropping the branch would render an old audit's pin wrong.
      // Reuse the same card slot/sizing CHANGED
      // already uses for its extra line — a CONFLICT pin's whole point is "needs a
      // human look," so surfacing that here is the highest-value single addition,
      // without touching the card's pixel-layout math for a third text line.
      const subValueText = markerType === 'CHANGED'
        ? (isOldDrawing ? `Revised Drawing: ${cleanCadText(v.description)}` : (v.original_value ? `Original Drawing: ${cleanCadText(v.original_value)}` : null))
        : markerType === 'CONFLICT'
          ? '⚠ Generators disagreed — needs manual review'
          : null;

      ctx.font = `bold ${10 * resolutionMultiplier}px "Yu Gothic", "MS Gothic", monospace`;
      const seqId = `M${String(idx + 1).padStart(3, '0')}`;

      ctx.font = `bold ${12 * resolutionMultiplier}px "Yu Gothic", "MS Gothic", monospace`;
      const valWidth = ctx.measureText(displayVal).width;

      ctx.font = `${10 * resolutionMultiplier}px "Yu Gothic", "MS Gothic", monospace`;
      const catWidth = ctx.measureText(`Cat:  ${displayCat}`).width;
      const statWidth = ctx.measureText(displayStat).width;
      const subWidth = subValueText ? ctx.measureText(subValueText).width : 0;

      const maxTextWidth = Math.max(valWidth + 24 * resolutionMultiplier, catWidth, statWidth, subWidth);
      const cardWidth = Math.max(160 * resolutionMultiplier, maxTextWidth + 16 * resolutionMultiplier);
      const cardHeight = subValueText ? 72 * resolutionMultiplier : 58 * resolutionMultiplier;

      let labelX = screenX - cardWidth / 2;
      let labelY = screenY - cardHeight - 12 * resolutionMultiplier;

      if (labelX < 4 * resolutionMultiplier) labelX = 4 * resolutionMultiplier;
      const screenLimitWidth = isExport ? renderWidth : frame.width;
      if (labelX + cardWidth > screenLimitWidth - 4 * resolutionMultiplier) {
        labelX = screenLimitWidth - cardWidth - 4 * resolutionMultiplier;
      }

      let collisionDetected = true;
      let safetyCounter = 0;
      while (collisionDetected && safetyCounter < 15) {
        collisionDetected = false;
        for (const rect of placedCardRects) {
          const overlapX = (labelX < rect.xMax && labelX + cardWidth > rect.xMin);
          const overlapY = (labelY < rect.yMax && labelY + cardHeight > rect.yMin);
          if (overlapX && overlapY) {
            labelY = rect.yMin - cardHeight - 6 * resolutionMultiplier;
            collisionDetected = true;
            break;
          }
        }
        safetyCounter++;
      }

      placedCardRects.push({
        xMin: labelX,
        xMax: labelX + cardWidth,
        yMin: labelY,
        yMax: labelY + cardHeight
      });

      ctx.shadowColor = 'rgba(0, 0, 0, 0.45)';
      ctx.shadowBlur = 8 * resolutionMultiplier;
      ctx.shadowOffsetX = 2 * resolutionMultiplier;
      ctx.shadowOffsetY = 3 * resolutionMultiplier;

      ctx.fillStyle = cardBg;
      ctx.strokeStyle = bulletColor;
      ctx.lineWidth = 1.2 * resolutionMultiplier;

      ctx.fillRect(labelX, labelY, cardWidth, cardHeight);
      ctx.strokeRect(labelX, labelY, cardWidth, cardHeight);

      ctx.shadowBlur = 0;
      ctx.shadowOffsetX = 0;
      ctx.shadowOffsetY = 0;

      ctx.fillStyle = cardPrimaryText;
      ctx.font = `bold ${10 * resolutionMultiplier}px "Yu Gothic", "MS Gothic", monospace`;
      ctx.fillText(`[${seqId}]`, labelX + 8 * resolutionMultiplier, labelY + 14 * resolutionMultiplier);

      const cardBulletRadius = 4 * resolutionMultiplier;
      const cardBulletX = labelX + 14 * resolutionMultiplier;
      const cardBulletY = labelY + 28 * resolutionMultiplier;

      ctx.beginPath();
      ctx.arc(cardBulletX, cardBulletY, cardBulletRadius, 0, 2 * Math.PI);
      ctx.fillStyle = bulletColor;
      ctx.strokeStyle = cardBulletRing;
      ctx.lineWidth = 1 * resolutionMultiplier;
      ctx.fill();
      ctx.stroke();

      ctx.fillStyle = cardPrimaryText;
      ctx.font = `bold ${12 * resolutionMultiplier}px "Yu Gothic", "MS Gothic", monospace`;
      ctx.fillText(displayVal, labelX + 24 * resolutionMultiplier, labelY + 32 * resolutionMultiplier);

      ctx.fillStyle = cardSecondaryText;
      ctx.font = `${10 * resolutionMultiplier}px "Yu Gothic", "MS Gothic", monospace`;
      ctx.fillText(`Cat:  ${displayCat}`, labelX + 8 * resolutionMultiplier, labelY + 43 * resolutionMultiplier);

      ctx.fillStyle = bulletColor;
      ctx.font = `bold ${10 * resolutionMultiplier}px "Yu Gothic", "MS Gothic", monospace`;
      ctx.fillText(displayStat, labelX + 8 * resolutionMultiplier, labelY + 53 * resolutionMultiplier);

      if (subValueText) {
        ctx.fillStyle = '#f97316';
        ctx.font = `bold ${10 * resolutionMultiplier}px "Yu Gothic", "MS Gothic", monospace`;
        ctx.fillText(subValueText, labelX + 8 * resolutionMultiplier, labelY + 65 * resolutionMultiplier);
      }
    } // <-- Added missing closing brace

    const radius = (v.category === 'drawing_views' ? 4 : 2.5) * resolutionMultiplier * viewport.scale;

    if (statusLabel === 'MATCHED') {
      ctx.beginPath();
      ctx.strokeStyle = bulletColor;
      ctx.lineWidth = 3 * resolutionMultiplier;
      ctx.lineCap = 'round';
      ctx.lineJoin = 'round';
      const cx = screenX;
      const cy = screenY;
      const size = 6 * resolutionMultiplier;
      ctx.moveTo(cx - size * 0.8, cy - size * 0.1);
      ctx.lineTo(cx - size * 0.1, cy + size * 0.6);
      ctx.lineTo(cx + size * 0.9, cy - size * 0.7);
      ctx.stroke();

      if (isSelected) {
        ctx.beginPath();
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 1.2 * resolutionMultiplier;
        ctx.setLineDash([3 * resolutionMultiplier, 3 * resolutionMultiplier]);
        ctx.arc(screenX, screenY, size * 1.5, 0, 2 * Math.PI);
        ctx.stroke();
        ctx.setLineDash([]);
      }
    } else {
      ctx.beginPath();
      ctx.fillStyle = isSelected
        ? (penType === 'ai_red' ? 'rgba(255, 40, 80, 0.7)' : penType === 'ai_orange' ? 'rgba(255, 150, 0, 0.7)' : penType === 'checker_blue' ? 'rgba(0, 255, 255, 0.7)' : penType === 'ai_conflict' ? 'rgba(192, 132, 252, 0.7)' : 'rgba(57, 255, 20, 0.7)')
        : (penType === 'ai_red' ? 'rgba(255, 40, 80, 0.4)' : penType === 'ai_orange' ? 'rgba(255, 150, 0, 0.4)' : penType === 'checker_blue' ? 'rgba(0, 255, 255, 0.4)' : penType === 'ai_conflict' ? 'rgba(192, 132, 252, 0.4)' : 'rgba(57, 255, 20, 0.4)');

      // Draw the neon dot centered at the exact coordinate
      ctx.arc(screenX, screenY, radius, 0, 2 * Math.PI);
      ctx.fill();

      if (isSelected) {
        ctx.beginPath();
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 1.2 * resolutionMultiplier;
        ctx.setLineDash([2 * resolutionMultiplier, 2 * resolutionMultiplier]);
        ctx.arc(screenX, screenY, radius + 4 * resolutionMultiplier, 0, 2 * Math.PI);
        ctx.stroke();
        ctx.setLineDash([]);
      }
    }


    ctx.restore();
  });
};

export interface RenderAnnotationPinsParams {
  frame: RenderFrame;
  annotations: any[];
  selectedAnnotationId: string | null;
  hoveredAnnotationId?: string | null;
  badgeMap?: Record<string, string>;
}

const PEN_COLORS: Record<string, string> = {
  alert_red: '#ff4d4f',
  warning_orange: '#ffa940',
  amber_gold: '#ffec3d',
  checker_blue: '#00ffff',
  resolved_green: '#39ff14',
  resolved_pink: '#ff7ab6',
};

// Reviewer annotation pins.
// Screen positions are stored under "ann:<id>" keys so annotation hit-testing
// never collides with violation marker keys in the same markerPositionsRef.
// NOTE — unfinished feature, not dead code: `badgeMap` is fully plumbed through from
// CanvasRenderer.tsx (built by getAnnotationBadgeMap, which assigns stable A001/A002…
// labels by creation order) but no draw call ever uses it, so pins currently render as
// a bare "!" or "✓" glyph with no label. The parameter is kept rather than deleted so
// the intent — and the missing half — stays discoverable.
export const renderAnnotationPins = ({
  frame,
  annotations,
  selectedAnnotationId,
  hoveredAnnotationId,
  badgeMap: _badgeMap,
}: RenderAnnotationPinsParams) => {
  const { ctx, isExport, viewport, norm, resolutionMultiplier, markerPositionsRef } = frame;

  if (!Array.isArray(annotations)) return;

  if (frame.isNeonModeActive && !isExport) {
    ctx.filter = 'none';
  }

  annotations.forEach((ann) => {
    const coords = ann.coordinates;
    if (!coords || !Array.isArray(coords) || coords.length < 2) return;

    const [ax, ay] = coords;
    if (!Number.isFinite(ax) || !Number.isFinite(ay)) return;

    const screenPos = worldToScreen(ax, ay, norm, viewport);
    const isSelected = selectedAnnotationId === ann.id;
    const isHovered = hoveredAnnotationId === ann.id;
    const isResolved = ann.status === 'resolved';

    const color = isResolved ? '#39ff14' : (PEN_COLORS[ann.pen_type] || '#00ffff');

    markerPositionsRef.current[`ann:${ann.id}`] = { x: screenPos.x, y: screenPos.y };

    ctx.save();
    const localDpr = isExport ? 1 : (typeof window !== 'undefined' ? window.devicePixelRatio || 1 : 1);
    ctx.setTransform(localDpr, 0, 0, localDpr, 0, 0);

    const r = (isSelected || isHovered ? 9 : 7) * resolutionMultiplier;

    // Outer aura ring for hover/selection
    if (isSelected || isHovered) {
      ctx.beginPath();
      ctx.strokeStyle = isSelected ? '#ffffff' : color;
      ctx.lineWidth = 1.5 * resolutionMultiplier;
      ctx.setLineDash([3 * resolutionMultiplier, 3 * resolutionMultiplier]);
      ctx.arc(screenPos.x, screenPos.y, r + 4 * resolutionMultiplier, 0, 2 * Math.PI);
      ctx.stroke();
      ctx.setLineDash([]);
    }

    // Pin glyph — just the '!' (or a check for resolved) in the severity color,
    // no disc and no outline stroke either — a plain colored glyph.
    const glyphChar = isResolved ? '\u2713' : '!';
    const glyphSize = Math.round(r * 3.6);
    ctx.font = `900 ${glyphSize}px "Yu Gothic", "MS Gothic", Arial, sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillStyle = color;
    ctx.fillText(glyphChar, screenPos.x, screenPos.y);
    ctx.textAlign = 'left';
    ctx.textBaseline = 'alphabetic';

    ctx.restore();
  });
};

// ─── Zone overlay / alignment editor ──────────────────────────────────────────
//
// One renderer, deliberately. There used to be two: a read-only overlay drawing the
// detector's CAD-space output, and an editor drawing the hand-aligned fractions. They
// showed near-identical box sets with different meanings, and in practice nobody could tell
// which one a drag would affect — so they are merged. Geometry comes from `customRegions`
// (what you edit and what gets saved); the detected payload is still passed in, purely to
// report how each zone was originally resolved.
//
// Never drawn into exports: renderContent is the same path useComplianceReportExport drives
// for PDF report images, and debug geometry must not reach a customer-facing report.

/** Per-zone border/badge colors, distinguishable at low opacity on either theme. */
const ZONE_COLORS: Record<string, string> = {
  title: '#818cf8',            // indigo
  title_upper_left: '#2dd4bf', // teal
  bom: '#34d399',              // emerald
  tolerance: '#fbbf24',        // amber
  notes: '#fb7185',            // rose
  iso: '#c084fc',              // violet
  views: '#38bdf8',            // sky
  shim: '#f472b6',             // pink
};

const ZONE_LABELS: Record<string, string> = {
  title: 'TITLE BLOCK',
  title_upper_left: 'TITLE (UL)',
  bom: 'BOM TABLE',
  tolerance: 'GENERAL TOLERANCE',
  notes: 'NOTES',
  iso: 'ISO VIEW',
  views: 'DRAWING VIEWS',
  shim: 'SHIM TABLE',
};

export interface RenderZoneEditorParams {
  frame: RenderFrame;
  /** Zone geometry being edited, as fractions of render_bounds (Y-down). */
  customRegions: Record<string, RegionFractions>;
  /** `render_bounds` the fractions are relative to. */
  renderBounds: readonly [number, number, number, number];
  /** The one zone the hit-test accepts drags for; only this zone gets handles. */
  selectedRegion: string | null;
  hoveredHandleId: string | null;
  /**
   * Detected zones for this drawing, used only for the confidence marker. A box the
   * detector guessed from the percentage grid looks exactly as authoritative as a measured
   * one unless it is marked, which is the distinction this whole feature exists to expose.
   */
  detected?: DrawingZonesResponse | null;
  /**
   * Zone keys taken from the hand-aligned template.
   *
   * These outrank `detected` confidence entirely. A pinned zone is by definition NOT
   * something the detector anchored, so keying the guess marker off detection alone marks
   * the user's own alignment as a guess — exactly backwards, since a human decision is the
   * most authoritative source of a zone box there is.
   */
  pinnedKeys?: readonly string[];
}

/**
 * Draws one marker at each view's own ORIGIN: a right-pointing X arm and an up-pointing Y arm.
 *
 * Takes the datums already computed by `viewDatumsFromTransform` rather than deriving them
 * here — that walk is over every entity on the sheet and belongs in a memo, not in a function
 * that runs on every pan frame.
 *
 * **An inferred datum is drawn DASHED.** Only one view per sheet has its origin stated by the
 * file (`ucs_origin` projected); the rest are read off the drawn geometry, and the overlay says
 * which is which — the same idiom `renderZoneEditor` uses for a zone the detector never
 * anchored, so a guess is never mistaken for a measurement. See `viewDatums.ts` for the ladder
 * and for what shipped before it: a marker at the viewport's window CENTRE, which is what
 * `to_paper(anchor)` returns identically, and which was 22.2 and 11.8 units from the real datum
 * on two of this sheet's three views.
 *
 * Screen-constant, like lineweight and for the same reason — this is an annotation about the
 * drawing, not a feature of it, so it must not grow when you zoom in. Skipped on export: it
 * is a reference overlay, not part of the sheet.
 *
 * ## The Y flip belongs HERE, not in the canvas transform
 *
 * This function previously claimed *"the canvas transform already carries the flip, so the up
 * arm is drawn toward +y here and lands upward on screen."* **That was false.**
 * `CanvasRenderer` sets `ctx.scale(scale, scale)` — no negative — and every entity is mirrored
 * at draw time instead, through `flipY(y) = ymax + ymin - y` against `render_bounds`. So world
 * space on this canvas is **Y-DOWN**, and a marker drawn at a raw CAD `y` lands mirrored about
 * the sheet's horizontal centreline while its "up" arm points down.
 *
 * It survived because the error is proportional to distance from that centreline. On
 * `M745221N01` the two viewports near the middle were 18 and 6 units out — visually fine — and
 * only the isometric view, high on the sheet at paper y 224.8 against a centreline of 148.5,
 * was **152 units out**: drawn at the bottom of the sheet while the view it marks is at the top.
 * The same "mirrored overlay that looks plausible" failure the zone-fraction conversion carries
 * a warning about.
 *
 * This is the **only** overlay in this file that stays in world space. `renderViolationReticles`,
 * `renderAnnotationPins` and `renderZoneEditor` all open with
 * `ctx.setTransform(dpr, 0, 0, dpr, 0, 0)` and place things in screen pixels via `worldToScreen`
 * / `fractionsToScreenRect`, which apply the flip themselves. So "does this renderer owe the
 * mirror?" is answered by whether it resets the transform — and this one does not, because
 * dividing its sizes by `scale` is how it stays screen-constant while tracking the geometry.
 */
export const renderViewOrigins = ({
  frame,
  datums,
}: {
  frame: RenderFrame;
  datums?: readonly ViewDatum[];
}): void => {
  const { ctx, isExport, scale, resolutionMultiplier, norm } = frame;
  if (isExport) return;
  if (!datums?.length) return;

  const flipY = (y: number) => flipWorldY(y, norm);

  const dpr = typeof window !== 'undefined' ? window.devicePixelRatio || 1 : 1;
  const ARM_PX = 26;
  const HEAD_PX = 7;
  const arm = (ARM_PX / scale) * resolutionMultiplier;
  const head = (HEAD_PX / scale) * resolutionMultiplier;
  // Screen-space dash, like the arm lengths: a world-space pattern would dissolve when you
  // zoom out and turn solid when you zoom in, which is the one thing this dash must not do.
  const dash = [(5 / scale) * resolutionMultiplier, (3.5 / scale) * resolutionMultiplier];

  ctx.save();
  ctx.strokeStyle = '#22d3ee';
  ctx.fillStyle = '#22d3ee';
  ctx.lineWidth = (Math.max(1 / dpr, 1.25 / dpr) / scale) * resolutionMultiplier;
  ctx.lineCap = 'butt';
  ctx.lineJoin = 'miter';

  datums.forEach(({ x, y: paperY, inferred }) => {
    // Paper Y is CAD-up. World space here is Y-DOWN (see the flip note above), so the marker
    // is mirrored into it and the "up" arm is drawn toward -y.
    const y = flipY(paperY);

    // Dashed ARMS only. The arrowheads and the corner box stay solid: they are filled and a
    // small filled triangle with a dash pattern reads as a rendering fault, not as a caveat.
    ctx.setLineDash(inferred ? dash : []);

    ctx.beginPath();
    ctx.moveTo(x, y);
    ctx.lineTo(x + arm, y);
    ctx.moveTo(x, y);
    ctx.lineTo(x, y - arm);
    ctx.stroke();

    ctx.setLineDash([]);

    // Solid arrowheads, matching how iCAD draws them.
    ctx.beginPath();
    ctx.moveTo(x + arm, y);
    ctx.lineTo(x + arm - head, y + head * 0.42);
    ctx.lineTo(x + arm - head, y - head * 0.42);
    ctx.closePath();
    ctx.fill();

    ctx.beginPath();
    ctx.moveTo(x, y - arm);
    ctx.lineTo(x + head * 0.42, y - arm + head);
    ctx.lineTo(x - head * 0.42, y - arm + head);
    ctx.closePath();
    ctx.fill();

    // A small open square at the corner reads as "this is a datum", and distinguishes the
    // marker from a leader or a dimension witness line at a glance. Drawn into the same
    // quadrant the two arms occupy — up and to the right — so a negative height, not positive.
    const box = head * 0.85;
    ctx.strokeRect(x, y - box, box, box);
  });

  ctx.restore();
};

export const renderZoneEditor = ({
  frame,
  customRegions,
  renderBounds,
  selectedRegion,
  hoveredHandleId,
  detected,
  pinnedKeys,
}: RenderZoneEditorParams): void => {
  const { ctx, isExport, norm, viewport, renderWidth, renderHeight, resolutionMultiplier } = frame;
  if (isExport) return;

  // Zone detection found no sheet bounds: every detected box is the literal
  // (0,0,1000,1000) placeholder describing no drawing at all, so its confidence tells us
  // nothing and the seeded geometry is meaningless. Suppress rather than present fiction.
  if (isPlaceholderOnly(detected)) return;

  const localDpr = typeof window !== 'undefined' ? window.devicePixelRatio || 1 : 1;
  ctx.save();
  ctx.setTransform(localDpr, 0, 0, localDpr, 0, 0);

  ZONE_KEYS.forEach((key) => {
    const frac = customRegions[key];
    if (!frac) return;

    const isSelected = key === selectedRegion;
    const color = ZONE_COLORS[key] ?? '#94a3b8';
    const { left, top, right, bottom } = fractionsToScreenRect(frac, renderBounds, norm, viewport);
    const w = right - left;
    const h = bottom - top;
    if (w <= 0 || h <= 0) return;
    // Cull fully off-screen boxes; zone boxes can sit far outside the viewport when zoomed.
    if (right < 0 || bottom < 0 || left > renderWidth || top > renderHeight) return;

    // A zone the detector never anchored is a guess about where this feature sits. Dashed
    // and '?'-suffixed so an unaligned guess is never mistaken for a measurement.
    //
    // A PINNED zone is never a guess, and must not be drawn as one. It is also, by
    // definition, not something the detector anchored -- so keying this off `confidence`
    // alone labelled the user's own hand-aligned boxes as guesses, which is backwards: an
    // explicit human decision outranks `content_aware`. That was the visible half of the
    // template being write-only (the geometry not loading was the other half).
    const isPinned = pinnedKeys?.includes(key) ?? false;
    const wasMeasured = isPinned || detected?.[key]?.confidence === 'content_aware';

    // A zone the user reshaped has an explicit outline; every other zone is its rectangle.
    // `shapePointsToScreen` returns the rectangle's four corners in the un-reshaped case, so
    // the polygon path below is the single drawing path for both.
    const polygon = isPolygonZone(frac);
    const screenPoints = shapePointsToScreen(frac, renderBounds, norm, viewport);
    const tracePath = () => {
      ctx.beginPath();
      screenPoints.forEach((p, i) => (i === 0 ? ctx.moveTo(p.x, p.y) : ctx.lineTo(p.x, p.y)));
      ctx.closePath();
    };

    ctx.strokeStyle = color;
    ctx.globalAlpha = isSelected ? 1 : 0.4;
    ctx.lineWidth = (isSelected ? 2 : 1.5) * resolutionMultiplier;
    ctx.setLineDash(wasMeasured ? [] : [6 * resolutionMultiplier, 4 * resolutionMultiplier]);
    if (polygon) {
      tracePath();
      ctx.stroke();
    } else {
      ctx.strokeRect(left, top, w, h);
    }
    ctx.setLineDash([]);

    ctx.fillStyle = color;
    ctx.globalAlpha = isSelected ? 0.1 : 0.06;
    if (key === 'views') {
      // The tint shows what is actually COMPARED as drawing_views, which is the rectangle
      // minus every sibling zone — not the rectangle. A pinned `views` covers the whole
      // drawing area and therefore swallows notes/BOM/title/iso on screen, while the backend
      // has already excluded all of it (scope_entities_to_views + VIEWS_EXCLUDED_ZONES).
      // Filling the raw rectangle claimed those regions were being diffed as geometry, which
      // reads as a scoping bug and was reported as one.
      //
      // Subtracted by chaining an even-odd clip per sibling rather than one even-odd fill over
      // all of them: chained clips INTERSECT, so two overlapping siblings still cut a single
      // hole. A single even-odd path would re-fill their intersection — and sibling overlap is
      // real here; the orchestrator logs "Spatial region overlap detected!" for BOM vs title.
      ctx.save();
      tracePath();
      ctx.clip();
      VIEWS_EXCLUDED_ZONES.forEach((siblingKey) => {
        const siblingFrac = customRegions[siblingKey];
        if (!siblingFrac) return;
        // A reshaped sibling cuts its OUTLINE out of the views tint, not its bounding box —
        // matching `views_exclusions`, which excludes on the outline for the same reason.
        // Punching the bbox would show content as excluded that the engine still compares.
        const hole = new Path2D();
        hole.rect(0, 0, renderWidth, renderHeight);
        if (isPolygonZone(siblingFrac)) {
          const sp = shapePointsToScreen(siblingFrac, renderBounds, norm, viewport);
          sp.forEach((p, i) => (i === 0 ? hole.moveTo(p.x, p.y) : hole.lineTo(p.x, p.y)));
          hole.closePath();
        } else {
          const s = fractionsToScreenRect(siblingFrac, renderBounds, norm, viewport);
          const sw = s.right - s.left;
          const sh = s.bottom - s.top;
          if (sw <= 0 || sh <= 0) return;
          hole.rect(s.left, s.top, sw, sh);
        }
        ctx.clip(hole, 'evenodd');
      });
      if (polygon) {
        tracePath();
        ctx.fill();
      } else {
        ctx.fillRect(left, top, w, h);
      }
      ctx.restore();
    } else if (polygon) {
      tracePath();
      ctx.fill();
    } else {
      ctx.fillRect(left, top, w, h);
    }
    ctx.globalAlpha = 1;

    const label = (ZONE_LABELS[key] ?? key.toUpperCase()) + (wasMeasured ? '' : ' ?');
    const fontPx = Math.round((isSelected ? 11 : 10) * resolutionMultiplier);
    ctx.font = `700 ${fontPx}px ui-sans-serif, system-ui, sans-serif`;
    const padX = 4 * resolutionMultiplier;
    const badgeH = fontPx + 6 * resolutionMultiplier;
    const badgeW = ctx.measureText(label).width + padX * 2;
    // Clamped into view so a partly off-screen zone still says which zone it is.
    const badgeX = Math.max(0, Math.min(left, renderWidth - badgeW));
    const badgeY = Math.max(0, Math.min(top, renderHeight - badgeH));
    ctx.globalAlpha = isSelected ? 1 : 0.55;
    ctx.fillStyle = color;
    ctx.fillRect(badgeX, badgeY, badgeW, badgeH);
    // Dark text: every zone color is a light 300/400-weight tone, so near-black reads
    // better on all seven than white does.
    ctx.fillStyle = '#0b0f19';
    ctx.textBaseline = 'middle';
    ctx.fillText(label, badgeX + padX, badgeY + badgeH / 2);
    ctx.textBaseline = 'alphabetic';
    ctx.globalAlpha = 1;

    if (!isSelected) return;

    // Handles. Ids and positions mirror the hit-test in useCanvasInteraction.ts; its hit
    // radius is 12px, so these are drawn at 9px half-width — visibly smaller than the grab
    // area, which makes the target forgiving rather than fiddly.
    //
    // A RECTANGLE keeps its four corner handles and its rectangular resize, unchanged. A
    // RESHAPED zone's handles are its vertices, because once an outline exists "resize the
    // box" has no meaning — there are five or nine corners and no opposite edge to hold.
    const HALF = 9 * resolutionMultiplier;
    const handles: Array<{ id: string; x: number; y: number }> = polygon
      ? screenPoints.map((p, i) => ({ id: `node:${i}`, x: p.x, y: p.y }))
      : [
          { id: 'top-left', x: left, y: top },
          { id: 'top-right', x: right, y: top },
          { id: 'bottom-left', x: left, y: bottom },
          { id: 'bottom-right', x: right, y: bottom },
        ];
    handles.forEach((c) => {
      ctx.fillStyle = hoveredHandleId === c.id ? '#ffffff' : color;
      ctx.strokeStyle = '#0b0f19';
      ctx.lineWidth = 1.5 * resolutionMultiplier;
      ctx.fillRect(c.x - HALF, c.y - HALF, HALF * 2, HALF * 2);
      ctx.strokeRect(c.x - HALF, c.y - HALF, HALF * 2, HALF * 2);
    });

    // Edge hint — the affordance that makes node insertion discoverable at all. When the
    // cursor is over an edge, a hollow "+" ghost appears at the point the node would be
    // added, so the gesture is visible before it is committed rather than being something
    // you have to already know about.
    const hoveredEdge = hoveredHandleId?.startsWith('edge:')
      ? Number(hoveredHandleId.slice('edge:'.length))
      : null;
    if (hoveredEdge !== null && Number.isFinite(hoveredEdge) && screenPoints.length > 0) {
      const a = screenPoints[hoveredEdge % screenPoints.length];
      const b = screenPoints[(hoveredEdge + 1) % screenPoints.length];
      const mx = (a.x + b.x) / 2;
      const my = (a.y + b.y) / 2;
      const r = 7 * resolutionMultiplier;

      ctx.strokeStyle = color;
      ctx.fillStyle = '#0b0f19';
      ctx.lineWidth = 2 * resolutionMultiplier;
      ctx.beginPath();
      ctx.arc(mx, my, r, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();

      ctx.strokeStyle = '#ffffff';
      ctx.lineWidth = 2 * resolutionMultiplier;
      ctx.beginPath();
      ctx.moveTo(mx - r * 0.5, my);
      ctx.lineTo(mx + r * 0.5, my);
      ctx.moveTo(mx, my - r * 0.5);
      ctx.lineTo(mx, my + r * 0.5);
      ctx.stroke();
    }
  });

  ctx.restore();
};
