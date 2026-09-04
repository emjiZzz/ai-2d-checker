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
    render(<ExportOverlay active />);
    expect(screen.getByRole('alertdialog')).toHaveTextContent('Preparing…');
  });

  it('updates dynamic phase text sequentially as export progresses', () => {
    const { rerender } = render(<ExportOverlay active phase="Rendering the drawing sheet…" />);
    const dialog = screen.getByRole('alertdialog');

    // Step 1 active
    expect(dialog).toHaveTextContent('Rendering the drawing sheet…');
    expect(dialog).not.toHaveTextContent('Building the checklist…');

    // Transition to Step 2
    rerender(<ExportOverlay active phase="Building the checklist…" />);
    expect(dialog).toHaveTextContent('Building the checklist…');
    expect(dialog).not.toHaveTextContent('Rendering the drawing sheet…');

    // Transition to Step 3
    rerender(<ExportOverlay active phase="Waiting for you to choose a folder…" />);
    expect(dialog).toHaveTextContent('Waiting for you to choose a folder…');

    // Transition to Step 4
    rerender(<ExportOverlay active phase="Writing the PDFs…" />);
    expect(dialog).toHaveTextContent('Writing the PDFs…');
  });

  it('captures pointer events rather than passing them through', () => {
    render(<ExportOverlay active phase="Writing the PDFs…" />);
    expect(screen.getByRole('alertdialog').style.pointerEvents).not.toBe('none');
  });

  it('sits BELOW the titlebar, so the window can still be minimised or closed', () => {
    const header = readFileSync(APP_HEADER, 'utf-8');
    const match = header.match(/z-\[(\d+)\]/);
    expect(match, `no z-[N] class found in ${APP_HEADER}`).toBeTruthy();
    expect(Z_INDEX).toBeLessThan(Number(match![1]));
  });

  it('covers the viewport rather than its own panel', () => {
    render(<ExportOverlay active />);
    const style = screen.getByRole('alertdialog').style;
    expect(style.position).toBe('fixed');
    expect(style.inset).toBe('0px');
  });
});
