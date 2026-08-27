import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ExportOverlay, Z_INDEX } from './ExportOverlay';

const APP_HEADER = resolve(__dirname, '../AppHeader.tsx');

describe('ExportOverlay', () => {
  it('is absent until an export is running', () => {
    render(<ExportOverlay active={false} phase="Rendering the drawing sheet…" />);
    expect(screen.queryByRole('alertdialog')).toBeNull();
  });

  it('names the phase, so a 17-second wait does not read as a hang', () => {
    render(<ExportOverlay active phase="Rendering the drawing sheet…" />);
    expect(screen.getByRole('alertdialog')).toHaveTextContent('Rendering the drawing sheet');
  });

  it('still says something when no phase has been set', () => {
    // An empty line would collapse the card's height mid-export, which reads as a flicker.
    render(<ExportOverlay active />);
    expect(screen.getByRole('alertdialog')).toHaveTextContent('Preparing…');
  });

  it('captures pointer events rather than passing them through', () => {
    // Blocking input IS the feature. The sibling drag overlay in `App.tsx` sets
    // `pointer-events-none` because it is decoration; copying that here would leave the canvas
    // clickable while the store is being read to build the document, and a marking retracted
    // halfway through yields a report whose page 1 and page 2 disagree.
    render(<ExportOverlay active phase="Writing the PDFs…" />);
    expect(screen.getByRole('alertdialog').style.pointerEvents).not.toBe('none');
  });

  it('sits BELOW the titlebar, so the window can still be minimised or closed', () => {
    // The invariant, read from `AppHeader.tsx` rather than restated here — a second copy of
    // 9999 would be correct until someone changed the header and silently wrong afterwards.
    //
    // If this inverts, a user is trapped in an app they cannot minimise for the length of a
    // 17-second render, and cannot close at all if the export ever hangs.
    const header = readFileSync(APP_HEADER, 'utf-8');
    const match = header.match(/z-\[(\d+)\]/);
    expect(match, `no z-[N] class found in ${APP_HEADER}`).toBeTruthy();
    expect(Z_INDEX).toBeLessThan(Number(match![1]));
  });

  it('covers the viewport rather than its own panel', () => {
    // Portalled to `document.body` and fixed to the viewport, because the button that starts the
    // export lives in a toolbar inside an `overflow: hidden` panel — an absolutely positioned
    // veil would be clipped to that panel and leave the rest of the app live.
    render(<ExportOverlay active />);
    const style = screen.getByRole('alertdialog').style;
    expect(style.position).toBe('fixed');
    expect(style.inset).toBe('0px');
  });
});
