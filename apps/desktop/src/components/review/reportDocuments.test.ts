import { describe, expect, it } from 'vitest';
import { PDFDocument } from 'pdf-lib';

import { reportFileNames, splitReportDocuments } from './reportDocuments';

/**
 * Real `pdf-lib` documents throughout, never mocks.
 *
 * The defect these guard against is a file that opens, is the right paper size, and carries the
 * wrong pages — so a test asserting "the code called copyPages" would pass while the export was
 * broken. Every assertion here loads the produced bytes back and looks at what is actually in
 * them.
 *
 * Pages are built at DISTINGUISHABLE sizes because that is the only way to tell page 0 from page
 * 1 after the split. A test that only counted pages would pass with the halves swapped, which is
 * precisely the mistake worth catching in the fallback branch.
 */
const DRAWING_W = 800;
const CHECKLIST_W = 400;
const HEIGHT = 600;

/** A jsPDF-shaped document: `pageWidths[i]` becomes page i's width. */
async function pdfWithPages(pageWidths: number[]): Promise<ArrayBuffer> {
  const doc = await PDFDocument.create();
  for (const width of pageWidths) doc.addPage([width, HEIGHT]);
  const bytes = await doc.save();
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer;
}

async function widthsOf(bytes: Uint8Array): Promise<number[]> {
  const doc = await PDFDocument.load(bytes);
  return doc.getPages().map((page) => Math.round(page.getWidth()));
}

describe('splitReportDocuments — vector path', () => {
  it('hands back the backend sheet untouched as the drawing', async () => {
    // The vector sheet is the acceptance criterion of the whole export: 100% vector with an
    // invisible searchable text layer. Re-encoding it through pdf-lib for no reason is how that
    // gets quietly degraded, so this asserts the EXACT bytes come back out.
    const sheet = new Uint8Array(await pdfWithPages([DRAWING_W]));
    const { drawing } = await splitReportDocuments(sheet, await pdfWithPages([CHECKLIST_W]), 1);

    expect(drawing).toBe(sheet);
  });

  it('returns the jsPDF document as the checklist', async () => {
    const { checklist } = await splitReportDocuments(
      new Uint8Array(await pdfWithPages([DRAWING_W])),
      await pdfWithPages([CHECKLIST_W, CHECKLIST_W]),
      2,
    );

    expect(checklist).not.toBeNull();
    expect(await widthsOf(checklist!)).toEqual([CHECKLIST_W, CHECKLIST_W]);
  });

  it('writes no checklist when the report has no rows', async () => {
    // jsPDF still hands over a ONE-PAGE document here — `new jsPDF()` always creates a page
    // whether or not anything was drawn on it. Trusting the PDF's own page count instead of the
    // rendered-sheet count saves a blank file that reads as a broken checklist.
    const { checklist } = await splitReportDocuments(
      new Uint8Array(await pdfWithPages([DRAWING_W])),
      await pdfWithPages([CHECKLIST_W]),
      0,
    );

    expect(checklist).toBeNull();
  });
});

describe('splitReportDocuments — raster fallback', () => {
  it('takes page 0 as the drawing and everything after it as the checklist', async () => {
    // The asymmetry this module exists for: with no vector sheet, jsPDF drew the canvas capture
    // as its own page 0 and the checklist after it. Swapping the halves produces two valid PDFs
    // of the right size, and `-drawing.pdf` opens on a checklist sheet.
    const { drawing, checklist } = await splitReportDocuments(
      null,
      await pdfWithPages([DRAWING_W, CHECKLIST_W, CHECKLIST_W]),
      2,
    );

    expect(await widthsOf(drawing)).toEqual([DRAWING_W]);
    expect(await widthsOf(checklist!)).toEqual([CHECKLIST_W, CHECKLIST_W]);
  });

  it('writes no checklist when the fallback page is all there is', async () => {
    const { drawing, checklist } = await splitReportDocuments(
      null,
      await pdfWithPages([DRAWING_W]),
      0,
    );

    expect(await widthsOf(drawing)).toEqual([DRAWING_W]);
    expect(checklist).toBeNull();
  });

  it('copies pages rather than deleting them, so neither half carries the other', async () => {
    // `removePage` would leave every object the dropped pages referenced still in the file. Both
    // halves come out near the size of the whole and neither looks wrong. A 3-page fallback split
    // into 1 + 2 must not produce two documents that each weigh as much as the original.
    const whole = await pdfWithPages([DRAWING_W, CHECKLIST_W, CHECKLIST_W]);
    const { drawing, checklist } = await splitReportDocuments(null, whole, 2);

    expect(drawing.byteLength).toBeLessThan(whole.byteLength);
    expect(checklist!.byteLength).toBeLessThan(whole.byteLength);
  });
});

describe('reportFileNames', () => {
  it('derives both names from the drawing stem', () => {
    expect(reportFileNames('M745221N01')).toEqual({
      drawing: 'M745221N01-drawing.pdf',
      checklist: 'M745221N01-checklist.pdf',
    });
  });

  it('returns BARE names, carrying no directory of their own', () => {
    // The caller joins these onto the folder Tauri authorised, using `@tauri-apps/api/path`'s
    // `join`. A separator baked in here would be a second opinion about the platform — and one
    // that is wrong on whichever platform it was not written on.
    for (const name of Object.values(reportFileNames('M745221N01'))) {
      expect(name).not.toMatch(/[\\/]/);
    }
  });

  it('strips a trailing .pdf so the stem is not doubled up', () => {
    expect(reportFileNames('report.pdf').drawing).toBe('report-drawing.pdf');
    expect(reportFileNames('report.PDF').checklist).toBe('report-checklist.pdf');
  });

  it('never gives the two halves the same name', () => {
    const names = reportFileNames('report');
    expect(names.drawing).not.toBe(names.checklist);
  });
});
