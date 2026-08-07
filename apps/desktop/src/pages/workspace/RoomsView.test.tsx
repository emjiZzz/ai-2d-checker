import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { expect, test, vi, describe } from 'vitest';
import { RoomsView } from './RoomsView';

// Audit finding #5 (docs/refactoring-audit-2026-07-23.md): RoomsView.tsx was manually merged
// with zero automated coverage, and this file was the smoke test that guarded the merge.
//
// It used to assert that all four comparison-engine options rendered and were individually
// selectable. `rag_ai`, `ai_vision` and `hybrid` were removed in ADR-006, and a chooser with
// one option is not a choice, so the whole COMPARISON ENGINE section went with them. The test
// now asserts the *inverse*: that the picker is gone, and that creating a room no longer sends
// a method. Written this way on purpose — a deleted test would let the picker come back
// unnoticed, and the DEV-badged section reappearing is exactly the regression worth catching.
//
// (This also retires a long-standing failure: the old test asserted a literal
// `rgb(255, 255, 255)` background that had since become a CSS variable.)

const createRoom = vi.fn(async (_params: Record<string, unknown>) => ({ id: 'room-1' }));

vi.mock('../../hooks/useRooms', () => ({
  useRooms: () => ({
    rooms: [],
    isLoading: false,
    createRoom,
    deleteRoom: vi.fn(),
  }),
}));

vi.mock('../../stores/roomStore', () => ({
  useRoomStore: () => ({
    openRoom: vi.fn(),
  }),
}));

function openCreateDialog() {
  render(<RoomsView />);
  // Both the header button and the empty-state button open the same modal.
  fireEvent.click(screen.getAllByRole('button', { name: /create room/i })[0]);
}

describe('RoomsView — Create Room dialog', () => {
  test('no comparison-engine picker is offered', () => {
    openCreateDialog();

    // The section, its DEV badge, and every per-method button.
    expect(screen.queryByText(/comparison engine/i)).toBeNull();
    expect(screen.queryByText('DEV')).toBeNull();
    for (const id of ['method-rag', 'method-rag-ai', 'method-ai-vision', 'method-hybrid']) {
      expect(document.getElementById(id)).toBeNull();
    }
    for (const label of ['RAG + AI', 'AI Vision', 'HYBRID']) {
      expect(screen.queryByText(label)).toBeNull();
    }
  });

  test('the dialog still renders and creates a room without a method', async () => {
    // The removal must not have taken the form with it — the picker sat inside the <form>,
    // and deleting a block by line range is exactly the edit that can swallow a sibling.
    openCreateDialog();

    const nameInput = screen.getByPlaceholderText(/architectural phase/i);
    fireEvent.change(nameInput, { target: { value: 'Bracket Rev C vs Rev D' } });
    fireEvent.click(screen.getByRole('button', { name: /create & open/i }));

    await waitFor(() => expect(createRoom).toHaveBeenCalled());
    const payload = createRoom.mock.calls[0][0];
    expect(payload.name).toBe('Bracket Rev C vs Rev D');
    // The server defaults it to "rag"; sending it from here would be the picker's ghost.
    expect(payload).not.toHaveProperty('comparison_method');
  });
});
