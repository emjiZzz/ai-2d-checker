import { markerStyle } from './markerStyles';
import { cleanCadText } from './renderEntities';
import { CHECKLIST_PAGE_ASPECT } from './reportPageGeometry';

/**
 * The compliance report's checklist page, drawn onto a canvas rather than typed into the PDF.
 *
 * ## Why canvas and not `doc.text`
 *
 * jsPDF's built-in fonts are WinAnsi. Every sheet this system audits is Japanese — `シム表`,
 * `仕上げ記号`, full-width part codes — and a checklist row's REFERENCE and REVISION columns are
 * verbatim drawing text. Typed through jsPDF those columns come out empty or as mojibake, which
 * is the worst available outcome: a report that looks complete and is missing exactly the values
 * the check was about. Embedding a CJK font would fix it and costs several megabytes of TTF in
 * the bundle for a page that is generated once per audit.
 *
 * The canvas already renders this text correctly — it is the same path the drawing page uses —
 * so the checklist is rasterised at 3x and embedded as an image.
 */

export interface ChecklistRow {
  /** A `MarkerType` spelling where there is one — it decides the pill's colour and glyph. */
  status: string;
  reference: string;
  revision: string;
  note: string;
}

export interface ChecklistSectionData {
  label: string;
  rows: ChecklistRow[];
}

export interface ChecklistSheetMeta {
  title: string;
  /** One line under the title — drawing identity and when this was produced. */
  subtitle: string;
  /** Right-aligned status tally, e.g. `12 items · 3 CHANGED`. Omit for none. */
  tally?: string;
}

/**
 * The sheet's own drawing space, in logical units — 1200 across, and A4 portrait height (1697).
 */
export const CHECKLIST_PAGE_W = 1200;
export const CHECKLIST_PAGE_H = Math.round(CHECKLIST_PAGE_W / CHECKLIST_PAGE_ASPECT); // 1697 for A4 portrait

const SCALE = 3;
const MARGIN = 48;
const GAP = 28;
export const COL_W = Math.floor((CHECKLIST_PAGE_W - MARGIN * 2 - GAP) / 2); // 538 px
export const COL_X = [MARGIN, MARGIN + COL_W + GAP]; // [48, 614]

const BODY_TOP = 106;
const BODY_BOTTOM = CHECKLIST_PAGE_H - 42;
const SECTION_H = 22;
const TABLE_HEAD_H = 20;
const LINE_H = 15;
const ROW_PAD = 7;
const MAX_LINES = 5;

/**
 * Normal table clean palette: white background, standard borders, all black text except Status.
 */
const COLORS = {
  bg: '#ffffff',
  border: '#d4d4d8',
  darkBorder: '#000000',
  primary: '#000000',
};

const FONT = (size: number, weight: 400 | 700 = 400) =>
  weight + ' ' + size + 'px "Segoe UI", "Yu Gothic UI", Meiryo, "Hiragino Kaku Gothic ProN", sans-serif';

/**
 * Break `text` to fit `maxWidth`, measured in the ctx's CURRENT font.
 *
 * Splits on whitespace first, then inside a token that still does not fit.
 */
export function wrapCellText(
  ctx: CanvasRenderingContext2D,
  text: string,
  maxWidth: number,
): string[] {
  const lines: string[] = [];
  const paragraphs = String(text ?? '').split(/\r?\n/);

  for (const paragraph of paragraphs) {
    const tokens = paragraph.split(/(\s+)/).filter((t) => t !== '');
    let line = '';

    const breakOverlong = () => {
      while (ctx.measureText(line).width > maxWidth && line.length > 1) {
        let cut = line.length - 1;
        while (cut > 1 && ctx.measureText(line.slice(0, cut)).width > maxWidth) cut--;
        lines.push(line.slice(0, cut));
        line = line.slice(cut);
      }
    };

    for (const token of tokens) {
      const candidate = line + token;
      if (line && ctx.measureText(candidate).width > maxWidth) {
        lines.push(line);
        line = token.replace(/^\s+/, '');
      } else {
        line = candidate;
      }
      breakOverlong();
    }
    lines.push(line);
  }

  return lines.length ? lines : [''];
}

function cellLines(ctx: CanvasRenderingContext2D, text: string, width: number): string[] {
  const all = wrapCellText(ctx, text, width);
  if (all.length <= MAX_LINES) return all;
  const kept = all.slice(0, MAX_LINES);
  kept[MAX_LINES - 1] = kept[MAX_LINES - 1].replace(/\s+$/, '') + '…';
  return kept;
}

interface Sheet {
  canvas: HTMLCanvasElement;
  ctx: CanvasRenderingContext2D;
}

function newSheet(meta: ChecklistSheetMeta, continued: boolean): Sheet {
  const canvas = document.createElement('canvas');
  canvas.width = Math.round(CHECKLIST_PAGE_W * SCALE);
  canvas.height = Math.round(CHECKLIST_PAGE_H * SCALE);
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('Checklist page could not be rendered: no 2D canvas context.');
  ctx.scale(SCALE, SCALE);
  ctx.textBaseline = 'alphabetic';

  ctx.fillStyle = COLORS.bg;
  ctx.fillRect(0, 0, CHECKLIST_PAGE_W, CHECKLIST_PAGE_H);

  // Top Page Header: "CHECKLIST" in black
  ctx.fillStyle = COLORS.primary;
  ctx.font = FONT(20, 700);
  ctx.textAlign = 'left';
  ctx.fillText(continued ? 'CHECKLIST (CONTINUED)' : 'CHECKLIST', MARGIN, 52);

  ctx.fillStyle = COLORS.primary;
  ctx.font = FONT(11);
  ctx.fillText(meta.subtitle, MARGIN, 74);

  if (meta.tally) {
    ctx.textAlign = 'right';
    ctx.fillStyle = COLORS.primary;
    ctx.font = FONT(11, 700);
    ctx.fillText(meta.tally, CHECKLIST_PAGE_W - MARGIN, 52);
    ctx.textAlign = 'left';
  }

  // Top header separator line
  ctx.strokeStyle = COLORS.border;
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(MARGIN, 90.5);
  ctx.lineTo(CHECKLIST_PAGE_W - MARGIN, 90.5);
  ctx.stroke();

  return { canvas, ctx };
}

function drawTableHeader(ctx: CanvasRenderingContext2D, colX: number, y: number) {
  ctx.strokeStyle = COLORS.darkBorder;
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(colX, y + 0.5);
  ctx.lineTo(colX + COL_W, y + 0.5);
  ctx.stroke();

  ctx.font = FONT(9, 700);
  ctx.fillStyle = COLORS.primary;
  ctx.fillText('STATUS', colX + 4, y + 14);
  ctx.fillText('REFERENCE', colX + 96, y + 14);
  ctx.fillText('REVISION', colX + 312, y + 14);

  ctx.strokeStyle = COLORS.border;
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(colX, y + TABLE_HEAD_H + 0.5);
  ctx.lineTo(colX + COL_W, y + TABLE_HEAD_H + 0.5);
  ctx.stroke();
}

function drawSectionHeading(
  ctx: CanvasRenderingContext2D,
  label: string,
  count: number,
  colX: number,
  y: number,
) {
  ctx.font = FONT(11, 700);
  ctx.fillStyle = COLORS.primary;
  ctx.fillText(label.toUpperCase(), colX, y + 16);
  ctx.font = FONT(10, 700);
  ctx.fillStyle = COLORS.primary;
  ctx.textAlign = 'right';
  ctx.fillText(String(count), colX + COL_W, y + 16);
  ctx.textAlign = 'left';
}

function measureRow(
  ctx: CanvasRenderingContext2D,
  row: ChecklistRow,
): { linesRef: string[]; linesRev: string[]; linesNote: string[]; height: number } {
  ctx.font = FONT(10);
  const refText = cleanCadText(row.reference);
  const revText = cleanCadText(row.revision);
  const noteText = row.note ? cleanCadText(row.note) : '';
  const linesRef = cellLines(ctx, refText, 202);
  const linesRev = cellLines(ctx, revText, 210);
  const linesNote = noteText ? cellLines(ctx, noteText, COL_W - 24) : [];
  const baseLines = Math.max(linesRef.length, linesRev.length, 1);
  const noteHeight = linesNote.length > 0 ? linesNote.length * LINE_H + 4 : 0;
  const height = Math.max(28, baseLines * LINE_H + noteHeight + ROW_PAD * 2);
  return { linesRef, linesRev, linesNote, height };
}

function drawRow(
  ctx: CanvasRenderingContext2D,
  row: ChecklistRow,
  measured: { linesRef: string[]; linesRev: string[]; linesNote: string[] },
  colX: number,
  y: number,
  height: number,
) {
  // Status pill (only Status has color)
  const isAnnotationBadge = /^X[₀-₉0-9]*/i.test(row.status.trim());
  let label: string;
  let pillColor: string;

  if (isAnnotationBadge) {
    label = row.status.trim();
    pillColor = '#dc2626'; // Red color for annotation badge (X₁, X₂, X₃)
  } else {
    const style = markerStyle(row.status);
    label = style.glyph + ' ' + (row.status || style.label).replace(/_/g, ' ');
    pillColor = style.uiLight;
  }

  ctx.font = FONT(9, 700);
  const pillW = Math.min(86, ctx.measureText(label).width + 12);
  ctx.globalAlpha = 0.15;
  ctx.fillStyle = pillColor;
  ctx.fillRect(colX + 2, y + ROW_PAD - 1, pillW, 16);
  ctx.globalAlpha = 1;
  ctx.fillStyle = pillColor;
  ctx.fillText(label, colX + 8, y + ROW_PAD + 11);

  // Reference & Revision in pure black
  ctx.font = FONT(10);
  ctx.fillStyle = COLORS.primary;
  measured.linesRef.forEach((line, n) => {
    ctx.fillText(line, colX + 96, y + ROW_PAD + 11 + n * LINE_H);
  });
  measured.linesRev.forEach((line, n) => {
    ctx.fillText(line, colX + 312, y + ROW_PAD + 11 + n * LINE_H);
  });

  // Notes in pure black if present
  if (measured.linesNote.length > 0) {
    const noteTop = y + ROW_PAD + Math.max(measured.linesRef.length, measured.linesRev.length, 1) * LINE_H + 11;
    ctx.font = FONT(9);
    ctx.fillStyle = COLORS.primary;
    measured.linesNote.forEach((line, n) => {
      ctx.fillText(line, colX + 8, noteTop + n * LINE_H);
    });
  }

  // Bottom row divider line
  ctx.strokeStyle = COLORS.border;
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(colX, y + height + 0.5);
  ctx.lineTo(colX + COL_W, y + height + 0.5);
  ctx.stroke();
}

/**
 * Every checklist page, as PNG data URLs in order.
 *
 * Rendered in Portrait orientation with a clean normal Two-Column table layout.
 */
export function renderChecklistSheets(
  sections: ChecklistSectionData[],
  meta: ChecklistSheetMeta,
): string[] {
  const sheets: Sheet[] = [];
  let sheet = newSheet(meta, false);
  sheets.push(sheet);

  let colIdx = 0; // 0 (left) or 1 (right)
  let y = BODY_TOP;

  const nextColumn = () => {
    if (colIdx === 0) {
      colIdx = 1;
      y = BODY_TOP;
    } else {
      sheet = newSheet(meta, true);
      sheets.push(sheet);
      colIdx = 0;
      y = BODY_TOP;
    }
  };

  const populated = sections.filter((s) => s.rows.length > 0);

  if (populated.length === 0) {
    sheet.ctx.font = FONT(12);
    sheet.ctx.fillStyle = COLORS.primary;
    sheet.ctx.fillText(
      'No checklist items were recorded for this drawing revision.',
      MARGIN,
      y + 24,
    );
  }

  for (const section of populated) {
    // Check if section heading + table header + 1 row can fit
    const headerBlockH = SECTION_H + TABLE_HEAD_H + 30;
    if (y + headerBlockH > BODY_BOTTOM) {
      nextColumn();
    }

    const colX = COL_X[colIdx];
    drawSectionHeading(sheet.ctx, section.label, section.rows.length, colX, y);
    y += SECTION_H;
    drawTableHeader(sheet.ctx, colX, y);
    y += TABLE_HEAD_H + 2;

    section.rows.forEach((row) => {
      const measured = measureRow(sheet.ctx, row);
      if (y + measured.height > BODY_BOTTOM) {
        nextColumn();
        const nextColX = COL_X[colIdx];
        drawSectionHeading(sheet.ctx, section.label + ' (cont.)', section.rows.length, nextColX, y);
        y += SECTION_H;
        drawTableHeader(sheet.ctx, nextColX, y);
        y += TABLE_HEAD_H + 2;
      }
      drawRow(sheet.ctx, row, measured, COL_X[colIdx], y, measured.height);
      y += measured.height;
    });

    y += 14; // gap between sections
  }

  // Footers last, numbered from 2 (the drawing is page 1 of the report)
  return sheets.map(({ canvas, ctx }, index) => {
    ctx.font = FONT(10);
    ctx.fillStyle = COLORS.primary;
    ctx.textAlign = 'right';
    ctx.fillText(
      'Page ' + (index + 2) + ' of ' + (sheets.length + 1),
      CHECKLIST_PAGE_W - MARGIN,
      CHECKLIST_PAGE_H - 18,
    );
    ctx.textAlign = 'left';
    return canvas.toDataURL('image/png');
  });
}
