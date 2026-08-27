import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { ExportStatusNote } from './ExportStatusNote';

/**
 * The bug this component was written for: after picking a folder, nothing in the app said the
 * export had happened. "Building…" simply stopped saying "Building…" — which is also precisely
 * what cancelling the picker looks like.
 *
 * So the assertions are about what a user can actually see and act on, not about props being
 * passed through: that two files were written, where they went, and that the two outcomes are
 * distinguishable from one another.
 */
const saved = {
  kind: 'saved' as const,
  folder: 'D:\\RAYSAN\\AI-2D-Checker-DATA',
  names: ['M745221N01-drawing.pdf', 'M745221N01-checklist.pdf'],
  paths: [
    'D:\\RAYSAN\\AI-2D-Checker-DATA\\M745221N01-drawing.pdf',
    'D:\\RAYSAN\\AI-2D-Checker-DATA\\M745221N01-checklist.pdf',
  ],
};

describe('ExportStatusNote', () => {
  it('renders nothing before an export has happened', () => {
    const { container } = render(<ExportStatusNote status={null} onReveal={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('says how many files were written and where', () => {
    render(<ExportStatusNote status={saved} onReveal={vi.fn()} />);
    expect(screen.getByRole('status')).toHaveTextContent('Saved 2 files to AI-2D-Checker-DATA');
  });

  it('keeps the full path and both filenames on the title, where they cannot wrap', () => {
    // The visible line shows the folder's own NAME — an absolute Windows path in a 200 px
    // sidebar wraps to three lines to report something the user just chose. The detail still has
    // to be recoverable, so it lives on the tooltip.
    render(<ExportStatusNote status={saved} onReveal={vi.fn()} />);
    const title = screen.getByRole('status').getAttribute('title') ?? '';
    expect(title).toContain(saved.folder);
    for (const name of saved.names) expect(title).toContain(name);
  });

  it('counts one file in the singular, for a report with no findings', () => {
    // A checklist with no rows is not written at all, so this is a real state and not a nicety.
    render(
      <ExportStatusNote
        status={{ ...saved, names: [saved.names[0]], paths: [saved.paths[0]] }}
        onReveal={vi.fn()}
      />,
    );
    expect(screen.getByRole('status')).toHaveTextContent('Saved 1 file to');
  });

  it('offers Show, and it reveals the files', () => {
    const onReveal = vi.fn();
    render(<ExportStatusNote status={saved} onReveal={onReveal} />);
    fireEvent.click(screen.getByRole('button', { name: /show/i }));
    expect(onReveal).toHaveBeenCalledTimes(1);
  });

  it('reports a cancelled export as cancelled, not as a save', () => {
    // The whole point. These two must never read alike: the picker appears only after the sheet
    // has been rendered, so by then the user has waited long enough to assume it worked.
    render(<ExportStatusNote status={{ kind: 'cancelled' }} onReveal={vi.fn()} />);
    expect(screen.getByRole('status')).toHaveTextContent('Export cancelled');
    expect(screen.queryByRole('button', { name: /show/i })).toBeNull();
  });

  it('still offers Show when compact, because a toolbar has no other way to say where', () => {
    render(<ExportStatusNote status={saved} onReveal={vi.fn()} compact />);
    expect(screen.getByRole('button', { name: /show/i })).toBeTruthy();
    expect(screen.getByRole('status')).toHaveTextContent('Saved 2');
  });
});
