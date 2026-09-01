import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';

import {
  ChecklistSectionData,
  renderChecklistSheets,
  wrapCellText,
} from './complianceChecklistSheet';

/**
 * The checklist page's failure mode is silence.
 *
 * Every defect this file pins produces a PDF that opens, looks like a report and is missing rows
 * an engineer recorded — a row wrapped off the side of its column, a row that fell past the
 * bottom of the last page, a section heading standing over rows that are on the next page. None
 * of them throws, and none is visible without opening the export and counting.
 */

interface FakeCtx {
  calls: { text: string; x: number; y: number }[];
  [key: string]: any;
}

const contexts: FakeCtx[] = [];

function makeCtx(): FakeCtx {
  const ctx: FakeCtx = {
    calls: [],
    // 7px a character. Fixed rather than realistic: the point is that wrapping and pagination are
    // driven by measurement at all, and a deterministic width makes the page counts assertable.
    measureText: (t: string) => ({ width: String(t).length * 7 }),
    fillText: (text: string, x: number, y: number) => ctx.calls.push({ text, x, y }),
    scale: () => {},
    fillRect: () => {},
    beginPath: () => {},
    moveTo: () => {},
    lineTo: () => {},
    stroke: () => {},
  };
  return ctx;
}

beforeEach(() => {
  contexts.length = 0;
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation((() => {
    const ctx = makeCtx();
    contexts.push(ctx);
    return ctx;
  }) as any);
  vi.spyOn(HTMLCanvasElement.prototype, 'toDataURL').mockImplementation(
    () => 'data:image/png;base64,STUB',
  );
});

afterEach(() => vi.restoreAllMocks());

const META = { title: 'CHECKLIST', subtitle: 'rev vs ref', tally: '1 items' };

const textOn = (page: number) => contexts[page].calls.map((c) => c.text).join('\n');
const allText = () => contexts.map((c) => c.calls.map((k) => k.text).join('\n')).join('\n');

describe('renderChecklistSheets', () => {
  test('prints a page even when nothing was recorded', () => {
    const pages = renderChecklistSheets([], META);
    expect(pages).toHaveLength(1);
    expect(textOn(0)).toContain('No checklist items were recorded');
  });

  test('an empty section does not print a heading with nothing under it', () => {
    renderChecklistSheets([{ label: 'BOM', rows: [] }], META);
    expect(textOn(0)).not.toContain('BOM');
    expect(textOn(0)).toContain('No checklist items were recorded');
  });

  test('every row reaches a page, however many there are', () => {
    const rows = Array.from({ length: 120 }, (_, i) => ({
      status: 'CHANGED',
      reference: 'ref-value-' + i,
      revision: 'rev-value-' + i,
      note: '',
    }));
    const pages = renderChecklistSheets([{ label: 'Drawing Views', rows }], META);

    expect(pages.length).toBeGreaterThan(1);
    const printed = allText();
    for (let i = 0; i < 120; i++) {
      expect(printed).toContain('ref-value-' + i);
      expect(printed).toContain('rev-value-' + i);
    }
  });

  test('a continued section repeats its heading across columns/pages, so no section misdescribes its rows', () => {
    const rows = Array.from({ length: 120 }, (_, i) => ({
      status: 'MATCHED',
      reference: 'r' + i,
      revision: 'v' + i,
      note: '',
    }));
    renderChecklistSheets([{ label: 'Drawing Views', rows }], META);

    expect(contexts.length).toBeGreaterThan(1);
    expect(allText()).toContain('DRAWING VIEWS (CONT.)');
    expect(textOn(1)).toContain('(CONTINUED)');
  });

  test('findings sort above matches only when the caller sorts — rows are printed in order', () => {
    const sections: ChecklistSectionData[] = [
      {
        label: 'Title Block',
        rows: [
          { status: 'CHANGED', reference: 'A', revision: 'B', note: '' },
          { status: 'MATCHED', reference: 'C', revision: 'C', note: '' },
        ],
      },
    ];
    renderChecklistSheets(sections, META);
    const texts = contexts[0].calls.map((c) => c.text);
    expect(texts.indexOf('A')).toBeLessThan(texts.indexOf('C'));
  });

  test('transcodes AutoCAD %%c, %%d, %%p escape codes to clean symbols on the sheet', () => {
    const sections: ChecklistSectionData[] = [
      {
        label: 'BOM',
        rows: [
          { status: 'CHANGED', reference: '%%c55-15', revision: '%%c55×15', note: '12.5%%d ± 0.05%%p' },
        ],
      },
    ];
    renderChecklistSheets(sections, META);
    const printed = allText();
    expect(printed).toContain('⌀55-15');
    expect(printed).toContain('⌀55×15');
    expect(printed).not.toContain('%%c');
  });

  test('renders annotation status badge like X₁ in status pill', () => {
    const sections: ChecklistSectionData[] = [
      {
        label: 'Annotations',
        rows: [
          { status: 'X₁', reference: '—', revision: 'wrong dimension', note: '' },
        ],
      },
    ];
    renderChecklistSheets(sections, META);
    const printed = allText();
    expect(printed).toContain('X₁');
    expect(printed).not.toContain('+ ADDED');
  });

  test('page footers count the drawing as page 1', () => {
    renderChecklistSheets([], META);
    expect(textOn(0)).toContain('Page 2 of 2');
  });
});

describe('wrapCellText', () => {
  const ctx = makeCtx() as unknown as CanvasRenderingContext2D;

  test('breaks inside a token with no spaces in it', () => {
    // A Japanese run or a part code carries no whitespace. A word-only wrap leaves it one long
    // line that paints straight over the next column.
    const lines = wrapCellText(ctx, 'M745204N01-REVISION-2-ISOMETRIC', 70);
    expect(lines.length).toBeGreaterThan(1);
    for (const line of lines) expect(line.length).toBeLessThanOrEqual(10);
    expect(lines.join('')).toBe('M745204N01-REVISION-2-ISOMETRIC');
  });

  test('keeps whole words together when they fit', () => {
    expect(wrapCellText(ctx, 'ab cd', 700)).toEqual(['ab cd']);
  });

  test('preserves explicit line breaks', () => {
    expect(wrapCellText(ctx, 'one\ntwo', 700)).toEqual(['one', 'two']);
  });

  test('an empty cell is one empty line, not zero lines', () => {
    // Zero lines would collapse the row's measured height and overlap the row beneath it.
    expect(wrapCellText(ctx, '', 700)).toEqual(['']);
  });
});
