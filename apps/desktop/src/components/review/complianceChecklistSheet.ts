import { markerStyle } from './markerStyles';
import { REPORT_PAGE_ASPECT } from './reportPageGeometry';

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
 * so the checklist is rasterised at 3x and embedded as an image. The trade is real and worth
 * naming: the text is not selectable or searchable in the resulting PDF. If that ever matters
 * more than the Japanese does, embed a font here; do not switch back to `doc.text`.
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
 * The sheet's own drawing space, in logical units — 1200 across, and whatever height the report's
 * paper makes that.
 *
 * The height is DERIVED rather than chosen. It was a round 800, which is a 1.5 aspect against A4
 * landscape's 1.414, so placing the finished bitmap across the whole page stretched every row by
 * 6% vertically — a distortion that looks like nothing more than slightly heavy type until you
 * hold it beside the drawing on page 1.
 */
export const CHECKLIST_PAGE_W = 1200;
export const CHECKLIST_PAGE_H = CHECKLIST_PAGE_W / REPORT_PAGE_ASPECT;

const SCALE = 3;
const MARGIN = 50;
const TABLE_HEAD_Y = 128;
const TABLE_HEAD_H = 26;
const BODY_TOP = TABLE_HEAD_Y + TABLE_HEAD_H + 12;
const BODY_BOTTOM = CHECKLIST_PAGE_H - 46;
const SECTION_H = 30;
const LINE_H = 16;
const ROW_PAD = 11;
const MAX_LINES = 6;

/**
 * Print-friendly palette. A compliance report is a document on paper — dark mode has no
 * place in it. White background, near-black text, light grey bands for structure.
 */
const COLORS = {
  bg: '#ffffff',
  band: '#f0f0f5',
  rowAlt: '#f8f8fa',
  border: '#d4d4d8',
  primary: '#000000',
  muted: '#27272a',
  accent: '#0f766e',
};

interface Column {
  key: keyof ChecklistRow;
  label: string;
  x: number;
  w: number;
}

const COLUMNS: Column[] = [
  { key: 'status', label: 'STATUS', x: MARGIN, w: 118 },
  { key: 'reference', label: 'REFERENCE', x: 178, w: 322 },
  { key: 'revision', label: 'REVISION', x: 510, w: 322 },
  { key: 'note', label: 'NOTES', x: 842, w: 308 },
];

const FONT = (size: number, weight: 400 | 700 = 400) =>
  weight + ' ' + size + 'px "Segoe UI", "Yu Gothic UI", Meiryo, "Hiragino Kaku Gothic ProN", sans-serif';

/**
 * Break `text` to fit `maxWidth`, measured in the ctx's CURRENT font.
 *
 * Splits on whitespace first, then inside a token that still does not fit. The second pass is not
 * a nicety — Japanese runs and part codes like `M745204N01-REV2` carry no spaces at all, so a
 * word-only wrap leaves them overflowing their column and painting over the next one.
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

  ctx.fillStyle = COLORS.accent;
  ctx.font = FONT(22, 700);
  ctx.textAlign = 'left';
  ctx.fillText(continued ? meta.title + ' (CONTINUED)' : meta.title, MARGIN, 62);

  ctx.fillStyle = COLORS.muted;
  ctx.font = FONT(12);
  ctx.fillText(meta.subtitle, MARGIN, 86);

  if (meta.tally) {
    ctx.textAlign = 'right';
    ctx.fillStyle = COLORS.primary;
    ctx.font = FONT(12, 700);
    ctx.fillText(meta.tally, CHECKLIST_PAGE_W - MARGIN, 62);
    ctx.textAlign = 'left';
  }

  ctx.fillStyle = COLORS.band;
  ctx.fillRect(MARGIN, TABLE_HEAD_Y, CHECKLIST_PAGE_W - MARGIN * 2, TABLE_HEAD_H);
  ctx.font = FONT(10, 700);
  ctx.fillStyle = COLORS.muted;
  for (const col of COLUMNS) ctx.fillText(col.label, col.x + 10, TABLE_HEAD_Y + 17);

  return { canvas, ctx };
}

function drawSectionHeading(
  ctx: CanvasRenderingContext2D,
  label: string,
  count: number,
  y: number,
) {
  ctx.fillStyle = COLORS.band;
  ctx.fillRect(MARGIN, y, CHECKLIST_PAGE_W - MARGIN * 2, SECTION_H);
  ctx.fillStyle = COLORS.accent;
  ctx.fillRect(MARGIN, y, 3, SECTION_H);
  ctx.font = FONT(12, 700);
  ctx.fillStyle = COLORS.primary;
  ctx.fillText(label.toUpperCase(), MARGIN + 14, y + 20);
  ctx.font = FONT(11);
  ctx.fillStyle = COLORS.muted;
  ctx.textAlign = 'right';
  ctx.fillText(String(count), CHECKLIST_PAGE_W - MARGIN - 12, y + 20);
  ctx.textAlign = 'left';
}

function measureRow(
  ctx: CanvasRenderingContext2D,
  row: ChecklistRow,
): { lines: string[][]; height: number } {
  ctx.font = FONT(11);
  const lines = COLUMNS.map((col) =>
    col.key === 'status' ? [] : cellLines(ctx, row[col.key], col.w - 20),
  );
  const tallest = lines.reduce((max, l) => Math.max(max, l.length), 1);
  return { lines, height: Math.max(34, tallest * LINE_H + ROW_PAD * 2) };
}

function drawRow(
  ctx: CanvasRenderingContext2D,
  row: ChecklistRow,
  lines: string[][],
  y: number,
  height: number,
  zebra: boolean,
) {
  if (zebra) {
    ctx.fillStyle = COLORS.rowAlt;
    ctx.fillRect(MARGIN, y, CHECKLIST_PAGE_W - MARGIN * 2, height);
  }

  // The pill's colour and glyph come from the SHARED marker table, so a MATCHED row in the report
  // is the same green, and the same tick, as the marker sitting on the drawing one page earlier.
  // We use uiLight because the report is rendered on white paper.
  const style = markerStyle(row.status);
  const label = style.glyph + ' ' + (row.status || style.label).replace(/_/g, ' ');
  ctx.font = FONT(10, 700);
  const pillW = Math.min(COLUMNS[0].w - 12, ctx.measureText(label).width + 16);
  ctx.globalAlpha = 0.15;
  ctx.fillStyle = style.uiLight;
  ctx.fillRect(COLUMNS[0].x + 10, y + ROW_PAD - 2, pillW, 18);
  ctx.globalAlpha = 1;
  ctx.fillStyle = style.uiLight;
  ctx.fillText(label, COLUMNS[0].x + 18, y + ROW_PAD + 11);

  ctx.font = FONT(11);
  COLUMNS.forEach((col, i) => {
    if (col.key === 'status') return;
    ctx.fillStyle = col.key === 'note' ? COLORS.muted : COLORS.primary;
    lines[i].forEach((line, n) => {
      ctx.fillText(line, col.x + 10, y + ROW_PAD + 11 + n * LINE_H);
    });
  });

  ctx.strokeStyle = COLORS.border;
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(MARGIN, y + height + 0.5);
  ctx.lineTo(CHECKLIST_PAGE_W - MARGIN, y + height + 0.5);
  ctx.stroke();
}

/**
 * Every checklist page, as PNG data URLs in order.
 *
 * Always returns at least one page. An empty check is a result — "nothing was recorded" printed
 * on a page is a statement an engineer can act on, whereas a report that silently drops its
 * second page is indistinguishable from one that failed to generate.
 */
export function renderChecklistSheets(
  sections: ChecklistSectionData[],
  meta: ChecklistSheetMeta,
): string[] {
  const sheets: Sheet[] = [];
  let sheet = newSheet(meta, false);
  sheets.push(sheet);
  let y = BODY_TOP;

  const nextPage = () => {
    sheet = newSheet(meta, true);
    sheets.push(sheet);
    y = BODY_TOP;
  };

  const populated = sections.filter((s) => s.rows.length > 0);

  if (populated.length === 0) {
    sheet.ctx.font = FONT(12);
    sheet.ctx.fillStyle = COLORS.muted;
    sheet.ctx.fillText(
      'No checklist items were recorded for this drawing revision.',
      MARGIN,
      y + 14,
    );
  }

  for (const section of populated) {
    // A heading with no room for its first row underneath is an orphan — it lands at the foot of
    // one page while the rows it names begin on the next, so both pages misdescribe what they
    // hold.
    if (y + SECTION_H + 34 > BODY_BOTTOM) nextPage();
    drawSectionHeading(sheet.ctx, section.label, section.rows.length, y);
    y += SECTION_H + 6;

    section.rows.forEach((row, index) => {
      const { lines, height } = measureRow(sheet.ctx, row);
      if (y + height > BODY_BOTTOM) {
        nextPage();
        drawSectionHeading(sheet.ctx, section.label + ' (cont.)', section.rows.length, y);
        y += SECTION_H + 6;
      }
      drawRow(sheet.ctx, row, lines, y, height, index % 2 === 1);
      y += height;
    });

    y += 16;
  }

  // Footers last, because the total is only known once every row has been placed. Numbered from
  // 2: the drawing is page 1 of the report and is not one of these sheets.
  return sheets.map(({ canvas, ctx }, index) => {
    ctx.font = FONT(10);
    ctx.fillStyle = COLORS.muted;
    ctx.textAlign = 'right';
    ctx.fillText(
      'Page ' + (index + 2) + ' of ' + (sheets.length + 1),
      CHECKLIST_PAGE_W - MARGIN,
      CHECKLIST_PAGE_H - 24,
    );
    ctx.textAlign = 'left';
    return canvas.toDataURL('image/png');
  });
}
