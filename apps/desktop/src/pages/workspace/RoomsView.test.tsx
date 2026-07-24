import { render, screen, fireEvent } from '@testing-library/react';
import { expect, test, vi, describe } from 'vitest';
import { RoomsView } from './RoomsView';

// Audit finding #5 (docs/refactoring-audit-2026-07-23.md): RoomsView.tsx was manually
// merged (per REFACTORING_SUMMARY.md §1: light-theme modal forms + a 4-column
// comparison-engine selector grid) with zero automated coverage. This is a smoke test
// only — it does not forensically re-verify the merge, just guards against a future
// change silently dropping one of the 4 engine options or breaking selection.

vi.mock('../../hooks/useRooms', () => ({
  useRooms: () => ({
    rooms: [],
    isLoading: false,
    createRoom: vi.fn(),
    deleteRoom: vi.fn(),
  }),
}));

vi.mock('../../stores/roomStore', () => ({
  useRoomStore: () => ({
    openRoom: vi.fn(),
  }),
}));

describe('RoomsView — Create Room comparison-engine selector', () => {
  test('all 4 engine options render and are individually selectable', () => {
    render(<RoomsView />);

    // Both the header button and the empty-state button open the same modal.
    fireEvent.click(screen.getAllByRole('button', { name: /create room/i })[0]);

    const ragBtn = document.getElementById('method-rag') as HTMLButtonElement;
    const ragAiBtn = document.getElementById('method-rag-ai') as HTMLButtonElement;
    const aiVisionBtn = document.getElementById('method-ai-vision') as HTMLButtonElement;
    const hybridBtn = document.getElementById('method-hybrid') as HTMLButtonElement;

    expect(ragBtn).toBeTruthy();
    expect(ragAiBtn).toBeTruthy();
    expect(aiVisionBtn).toBeTruthy();
    expect(hybridBtn).toBeTruthy();

    expect(screen.getByText('RAG')).toBeInTheDocument();
    expect(screen.getByText('RAG + AI')).toBeInTheDocument();
    expect(screen.getByText('AI Vision')).toBeInTheDocument();
    expect(screen.getByText('HYBRID')).toBeInTheDocument();

    // Default selection is "rag" (RoomsView.tsx: useState<ComparisonMethod>("rag")).
    expect(ragBtn.style.background).toBe('rgb(255, 255, 255)');
    expect(hybridBtn.style.background).toBe('transparent');

    // Selecting HYBRID must flip which button is visually "active" (white bg + border).
    fireEvent.click(hybridBtn);
    expect(hybridBtn.style.background).toBe('rgb(255, 255, 255)');
    expect(ragBtn.style.background).toBe('transparent');
  });
});
