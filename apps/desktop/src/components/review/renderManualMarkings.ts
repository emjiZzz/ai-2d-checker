import { worldToScreen } from '../../utils/coordinateTransform';
import type { RenderFrame } from './renderEntities';
import {
  zoneKeyForBox,
  zoneRelativePos,
  sheetRelativePos,
  isZoneMeasured,
  entityDisplayText,
  type EntityHitIndex,
} from './entityPicking';
import { flipWorldY } from '../../utils/coordinateTransform';
import type { DrawingZonesResponse } from '../../services/drawingsApi';
import type { EntityLocator } from '../../stores/workspace/types';

/**
 * Draws what the engineer has recorded, back onto the drawing.
 *
 * ## Why this is not optional polish
 *
 * A checker works by sweeping a sheet and marking as they go. Without a mark on the canvas the
 * only record of "I have looked at this" is a list in a side panel, which means the engineer has
 * to hold the swept region in their head — so they re-check things they have already done and,
 * worse, believe they have covered regions they have not. On a 68-row sheet that is the
 * difference between a complete pass and a partial one that reads as complete.
 *
 * The marks are also the only feedback that a stamp landed on the entity the engineer aimed at.
 * A badge in the wrong place is a visible bug; a correct list beside a silent canvas is not.
 *
 * ## Coordinates
 *
 * A marking's stored coordinate is CAD (Y-up): it was captured with `screenToWorld`, which
 * applies the flip inverse. `worldToScreen` flips again on the way back, so the pair round-trips
 * and no extra `flipWorldY` belongs here — adding one would mirror every badge about the
 * sheet's centreline, plausibly near the middle and far out at the edges.
 *
 * The hover box and the cross-sheet value matches are different: the picking index already
 * stores FLIPPED-world bounds, so both map with the frame's own `scale`/`transX`/`transY`
 * instead. Two spaces, two conversions, and they are not interchangeable.
 *
 * Drawn in screen space with the transform reset, matching `renderViolationReticles`.
 */

const STATUS_STYLE: Record<string, { color: string; glyph: string }> = {
  MATCHED: { color: '#10b981', glyph: '✓' },
  ADDED: { color: '#3b82f6', glyph: '+' },
  REMOVED: { color: '#ef4444', glyph: '−' },
  CHANGED: { color: '#f97316', glyph: '⇄' },
  NOT_A_FINDING: { color: '#a1a1aa', glyph: '×' },
};

const BADGE_RADIUS = 9;

export interface RenderManualMarkingsParams {
  frame: RenderFrame;
  markings: any[];
  /** Which sheet this canvas shows; decides which of the two stored coordinates to use. */
  side: 'ref' | 'rev';
  /** Highlighted while the cursor is over it, so a stamp is aimed rather than guessed. */
  hoveredEntityId: string | null;
  entityHitIndex?: EntityHitIndex;
  /** The reference half of a CHANGED pair still waiting for its counterpart. */
  pendingPairRef: { side: string; coordinates: [number, number] } | null;
  /**
   * The value under the cursor on the OTHER sheet.
   *
   * The named type rather than the structural copy this used to spell out: the copy had already
   * drifted — it was missing nothing yet, but `findMatches` reads all ten fields and a locally
   * declared shape is free to fall behind the one the store publishes.
   */
  hoverLocator?: EntityLocator | null;
  /**
   * The value SELECTED on the other sheet. Same shape and same matcher as hover; it differs only
   * in living until the selection changes, which is what lets the engineer look away from the
   * entity and still see its counterpart.
   */
  selectionLocator?: EntityLocator | null;
  /** THIS sheet's zones, so a match is confined to the same zone. */
  zones?: DrawingZonesResponse | null;
}

/**
 * What the chip shows: the entity's value as the sheet prints it, truncated to fit.
 *
 * Shared by the hover chip and the cross-sheet match chip so the two cannot disagree about a
 * value they have just agreed on. `entityDisplayText` reads `render_text` — the string the CAD
 * application actually composited — so `⌀110` on a sheet that applies the diameter standard
 * shows as `⌀110`, while the sheet that does not shows `110`. That difference is real and the
 * two still MATCH, because the comparison key folds the diameter mark away and the display does
 * not.
 */
const displayValue = (ent: any): string => {
  const raw = entityDisplayText(ent);
  return raw.length > 22 ? `${raw.slice(0, 22)}...` : raw;
};

export const renderManualMarkings = ({
  frame,
  markings,
  side,
  hoveredEntityId,
  entityHitIndex,
  pendingPairRef,
  hoverLocator,
  selectionLocator,
  zones,
}: RenderManualMarkingsParams) => {
  const { ctx, isExport, viewport, norm, scale, transX, transY } = frame;

  // Canvas drawing does not pick up CSS variables, so the live theme is read off the attribute
  // once per pass — same approach as `renderViolationReticles`.
  const isLight =
    typeof document !== 'undefined' &&
    document.documentElement.getAttribute('data-theme') === 'hc-light';
  const haloColor = isLight ? 'rgba(255,255,255,0.95)' : 'rgba(15,17,22,0.9)';

  if (frame.isNeonModeActive && !isExport) ctx.filter = 'none';

  ctx.save();
  const dpr = isExport ? 1 : typeof window !== 'undefined' ? window.devicePixelRatio || 1 : 1;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

  // ── hover highlight ───────────────────────────────────────────────────────────────
  // Corner brackets plus a label, not a filled rectangle. A translucent fill reads as "this
  // whole area IS the thing", which on a large entity (a 176-degree arc, a long polyline) looks
  // like a bug — the box is honest, it is just describing something big. Brackets read as
  // "extent of", and the label removes the guesswork: you can see you are about to mark the arc
  // rather than the value printed across it, BEFORE you right-click.
  const hovered = entityHitIndex?.boundsFor(hoveredEntityId);
  if (hovered) {
    // The index is already in flipped-world units, so it converts with the frame's own scale
    // and translation rather than going back through worldToScreen.
    const x0 = hovered.x0 * scale + transX;
    const y0 = hovered.y0 * scale + transY;
    const x1 = hovered.x1 * scale + transX;
    const y1 = hovered.y1 * scale + transY;
    const w = x1 - x0;
    const h = y1 - y0;

    ctx.strokeStyle = '#22d3ee';
    ctx.lineWidth = 1.5;

    // Corner brackets, each a quarter of the shorter side, so they stay readable on a long thin
    // entity without ever meeting in the middle.
    const arm = Math.max(4, Math.min(14, Math.min(Math.abs(w), Math.abs(h)) * 0.25));
    const corners: [number, number, number, number][] = [
      [x0, y0, 1, 1],
      [x1, y0, -1, 1],
      [x0, y1, 1, -1],
      [x1, y1, -1, -1],
    ];
    ctx.beginPath();
    for (const [cx, cy, sx, sy] of corners) {
      ctx.moveTo(cx + arm * sx, cy);
      ctx.lineTo(cx, cy);
      ctx.lineTo(cx, cy + arm * sy);
    }
    ctx.stroke();

    // A whisper of fill so the region still reads as one object, without claiming the area.
    ctx.fillStyle = 'rgba(34,211,238,0.06)';
    ctx.fillRect(x0, y0, w, h);

    // The value, and only the value. It used to read `dimension - 183`, which was worth the
    // space when the index also held arcs and lines and a large unexplained box needed to say
    // `arc`. Now that only value carriers are indexed the type is the same answer every time
    // and the number is the whole point — so the chip echoes what is printed on the sheet.
    //
    // Only the chip is skipped when there is no value, never the rest of the pass — the
    // recorded markings and the cross-sheet boxes below are drawn from different state and an
    // early return here would silently take them with it.
    const label = displayValue(hovered.entity);
    if (label) {
      ctx.font = '600 10px system-ui, sans-serif';
      ctx.textAlign = 'left';
      ctx.textBaseline = 'alphabetic';
      const padX = 4;
      const tw = ctx.measureText(label).width;
      const chipH = 14;
      // Above the box, unless that would leave the canvas, in which case below it.
      const chipY = y0 - chipH - 3 < 0 ? y1 + 3 : y0 - chipH - 3;

      ctx.fillStyle = '#22d3ee';
      ctx.fillRect(x0, chipY, tw + padX * 2, chipH);
      ctx.fillStyle = '#06222a';
      ctx.fillText(label, x0 + padX, chipY + chipH - 4);
    }
  }

  // ── the same VALUE on the other sheet ─────────────────────────────────────────────
  // Drawn only on the canvas the cursor is NOT on. Hovering `145` here outlines every `145`
  // there, matched through `normalizeEntityValue` so the two exporters' spellings agree —
  // full-width against half-width, raw `%%c` against a decoded glyph.
  //
  // ## Why this replaced a positional hint
  //
  // Until 2026-08-18 this drew the same FRACTION of the other sheet's `render_bounds`. That was
  // wrong twice over. It was arithmetically inert — both canvases share one `viewport`, so a
  // fraction resolves to `f*1000*viewport.scale + viewport.x` on either sheet and the target's
  // span cancels; measured dx = 0.000000 across a 3x bounds difference, i.e. the source
  // rectangle redrawn at the same pixel. And the premise was wrong anyway: the sheets do not lay
  // out alike, so the same fraction is a different feature. `M745204N01` proves it — a clean 3x
  // uniform scaling of the bounding box, matching aspect, still arranging its views differently.
  //
  // ## What counts as a match
  //
  // Value alone was too loose — it outlined three boxes for one hovered angle. A candidate must
  // agree on value, entity TYPE (a dimension is not a note that reads the same), dimension KIND
  // (an 80° angular is not a linear `80`; they normalize identically) and ZONE (a value in the
  // BOM is not the same value in a view). Remaining ties are separated by position within the
  // zone — the one positional claim that holds, since a single view's contents do correspond
  // even though the sheets do not.
  //
  // ⚠ When there is nothing to break a tie with — no zone on either side — every candidate is
  // outlined rather than one being chosen. An arbitrary pick is indistinguishable from a
  // confident answer, which is the failure this overlay must not produce.
  //
  // ⚠ This does suggest a pairing where the fraction version withheld one, which is a real cost
  // to the independence of a CHANGED marking (owner's call, 2026-08-18). The category selector
  // is still never pre-filled — that remains the load-bearing half of the guarantee.
  const flipY = (y: number) => flipWorldY(y, norm);

  /**
   * Outline this sheet's counterpart of an entity picked on the OTHER sheet.
   *
   * One body for hover and selection. They were one gesture's feature until 2026-08-18 and the
   * matcher, the tie-break commentary above and the chip are all identical between them — the
   * only honest difference is how long the outline lives, and therefore how it is drawn.
   */
  const drawMatches = (locator: EntityLocator | null | undefined, opts: { dashed: boolean }) => {
    // `side !== side` is the whole point: a locator describes an entity on the OTHER canvas, and
    // outlining the sheet the cursor is already on would just re-box what is already boxed.
    if (!locator || locator.side === side) return;
    const matches =
      entityHitIndex?.findMatches(locator, {
        zoneOf: (b) => zoneKeyForBox(zones, b, flipY),
        zoneMeasured: (zone) => isZoneMeasured(zones, zone),
        zonePos: (b, zone) => zoneRelativePos(zones, zone, b, flipY),
        sheetPos: (b) => sheetRelativePos(b, norm),
      }) ?? [];
    if (!matches.length) return;

    // Full opacity, and thick enough to read over dense green geometry. It was 1px at 0.55 alpha
    // with a 2/3 dash, which on a drawing this busy was nearly invisible — and an outline the
    // engineer cannot find is the same as no outline, on the half of the workspace they are not
    // looking at.
    //
    // DASHED for hover, SOLID for the selection — the same distinction `renderSelectionHighlight`
    // draws on the near sheet, so a pair reads as two solid boxes and a passing cursor reads as
    // two dashed ones. Neither adopts the hover box's corner brackets, which mean "this is what
    // your cursor is on" and belong to one sheet only.
    ctx.strokeStyle = '#22d3ee';
    ctx.lineWidth = 1.5;
    if (opts.dashed) ctx.setLineDash([5, 3]);
    for (const m of matches) {
      const mx0 = m.x0 * scale + transX;
      const my0 = m.y0 * scale + transY;
      ctx.strokeRect(mx0, my0, (m.x1 - m.x0) * scale, (m.y1 - m.y0) * scale);
    }
    ctx.setLineDash([]);

    // Labelled with the value and, when it repeats, how many carry it — so "three places match"
    // is visible rather than looking like three unexplained boxes. Anchored on the first match
    // in index order, which is render order and therefore stable between frames.
    const first = matches[0];
    // The matched entity's OWN text, not `locator.value` — that is the comparison key, and
    // `normalizeEntityValue` upper-cases it and strips whitespace and the diameter mark. Showing
    // the key would print `6-12キリ` as its folded form and a lower-case `t` as `T`, so the two
    // chips would disagree about a value they had just agreed on.
    const matchText = displayValue(first.entity) || locator.value;
    const label = matches.length > 1 ? `${matchText} x${matches.length}` : matchText;
    ctx.font = '600 10px system-ui, sans-serif';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'alphabetic';
    const lx = first.x0 * scale + transX;
    const ly0 = first.y0 * scale + transY;
    const ly1 = first.y1 * scale + transY;
    const chipH = 13;
    const chipY = ly0 - chipH - 3 < 0 ? ly1 + 3 : ly0 - chipH - 3;
    // Solid, matching the hover chip: a translucent chip over green geometry left the label
    // unreadable, which defeats the point of labelling the match at all.
    ctx.fillStyle = '#22d3ee';
    ctx.fillRect(lx, chipY, ctx.measureText(label).width + 8, chipH);
    ctx.fillStyle = '#06222a';
    ctx.fillText(label, lx + 4, chipY + chipH - 4);
  };

  // Selection first, hover second: when the cursor happens to rest on the counterpart of what is
  // selected, the dashed box is the one that should win — it is the live gesture.
  drawMatches(selectionLocator, { dashed: false });
  drawMatches(hoverLocator, { dashed: true });

  // ── recorded markings ─────────────────────────────────────────────────────────────
  for (const m of markings) {
    if (m.retracted_at) continue;

    // A CHANGED marking is drawn on BOTH sheets, at each side's own coordinate. The two are
    // genuinely different points — that is why the pair takes two clicks — so there is no single
    // position that would be correct on both canvases.
    const coords = side === 'ref' ? m.ref_coordinates : m.rev_coordinates;
    if (!coords || coords.length < 2) continue;

    const style = STATUS_STYLE[m.status] ?? STATUS_STYLE.NOT_A_FINDING;
    const pos = worldToScreen(coords[0], coords[1], norm, viewport);

    // Halo first, so a badge stays legible over dense green geometry.
    ctx.beginPath();
    ctx.arc(pos.x, pos.y, BADGE_RADIUS + 1.5, 0, Math.PI * 2);
    ctx.fillStyle = haloColor;
    ctx.fill();

    ctx.beginPath();
    ctx.arc(pos.x, pos.y, BADGE_RADIUS, 0, Math.PI * 2);
    ctx.fillStyle = style.color;
    ctx.fill();

    if (m.is_bulk) {
      // A bulk anchor stands for several entities, so it reads differently from a single stamp.
      ctx.beginPath();
      ctx.arc(pos.x, pos.y, BADGE_RADIUS + 3.5, 0, Math.PI * 2);
      ctx.strokeStyle = style.color;
      ctx.lineWidth = 1.5;
      ctx.stroke();
    }

    ctx.fillStyle = '#ffffff';
    ctx.font = '700 11px system-ui, sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(style.glyph, pos.x, pos.y + 0.5);
  }

  // ── the half-finished pair ────────────────────────────────────────────────────────
  // Shown on the reference canvas while the engineer goes looking for the counterpart. Without
  // it the first click of a CHANGED pair leaves no trace on the drawing, and the sheet they are
  // now scanning gives no reminder of what they were pairing.
  if (pendingPairRef && pendingPairRef.side === side && pendingPairRef.coordinates) {
    const [px, py] = pendingPairRef.coordinates;
    const pos = worldToScreen(px, py, norm, viewport);
    ctx.beginPath();
    ctx.arc(pos.x, pos.y, BADGE_RADIUS + 2, 0, Math.PI * 2);
    ctx.strokeStyle = '#f97316';
    ctx.lineWidth = 2;
    ctx.setLineDash([3, 3]);
    ctx.stroke();
    ctx.setLineDash([]);
  }

  ctx.restore();
};

/** Exported so the marking list and the canvas cannot disagree about what a status looks like. */
export const MARKING_STATUS_STYLE = STATUS_STYLE;
