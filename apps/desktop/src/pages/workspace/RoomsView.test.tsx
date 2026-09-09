import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { expect, test, vi, describe, beforeEach } from 'vitest';
import { RoomsView } from './RoomsView';

const createRoom = vi.fn(async (_params: Record<string, unknown>) => ({ id: 'room-1' }));
let mockRooms: any[] = [];

vi.mock('../../hooks/useRooms', () => ({
  useRooms: () => ({
    rooms: mockRooms,
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

vi.mock('../../components/review/RealDrawingThumbnail', () => ({
  RealDrawingThumbnail: () => <div data-testid="real-drawing-thumbnail" />,
  CadFileIcon: () => <div data-testid="cad-file-icon" />,
}));

function generateRooms(count: number) {
  return Array.from({ length: count }, (_, i) => ({
    id: `room-${i + 1}`,
    name: `Room ${String(i + 1).padStart(2, '0')}`,
    room_mode: 'manual_check',
    active_old_drawing_name: `drawing_${i + 1}_v1.dxf`,
    active_new_drawing_name: `drawing_${i + 1}_v2.dxf`,
    active_old_drawing_id: `draw-old-${i + 1}`,
    active_new_drawing_id: `draw-new-${i + 1}`,
    created_at: new Date(2026, 0, 1, 10, i).toISOString(),
    updated_at: new Date(2026, 0, 1, 12, i).toISOString(),
    last_opened_at: new Date(2026, 0, 1, 14, i).toISOString(),
  }));
}

function openCreateDialog() {
  render(<RoomsView />);
  // When rooms is empty or present, click the primary "Create Room" button
  fireEvent.click(screen.getAllByRole('button', { name: /create room/i })[0]);
}

describe('RoomsView — Create Room dialog', () => {
  beforeEach(() => {
    mockRooms = [];
  });

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
    openCreateDialog();

    const nameInput = screen.getByPlaceholderText(/identify this drawing/i);
    fireEvent.change(nameInput, { target: { value: 'Bracket Rev C vs Rev D' } });
    fireEvent.click(screen.getByRole('button', { name: /^create$/i }));

    await waitFor(() => expect(createRoom).toHaveBeenCalled());
    const payload = createRoom.mock.calls[0][0];
    expect(payload.name).toBe('Bracket Rev C vs Rev D');
    expect(payload).not.toHaveProperty('comparison_method');
  });
});

describe('RoomsView — Pagination (Max 3 Rows)', () => {
  beforeEach(() => {
    mockRooms = generateRooms(25);
  });

  test('page 1 renders Create New card plus at most 11 rooms (3 rows max)', () => {
    render(<RoomsView />);

    // Quick Action "Create New" card is on page 1
    expect(screen.getByText(/^Create New$/i)).toBeInTheDocument();

    // Showing 1-11 of 25
    expect(screen.getByText(/Showing 1–11 of 25 rooms/i)).toBeInTheDocument();
    expect(screen.getByText(/\(Page 1 of 3\)/i)).toBeInTheDocument();

    // Sorted by recent descending: Room 25 is newest (page 1), Room 14 is 12th (page 2)
    expect(screen.getByText('Room 25')).toBeInTheDocument();
    expect(screen.getByText('Room 15')).toBeInTheDocument();
    expect(screen.queryByText('Room 14')).toBeNull();

    // Prev button should be disabled on page 1
    const prevBtn = screen.getByTitle(/Previous Page/i);
    expect(prevBtn).toBeDisabled();
  });

  test('clicking Next navigates to page 2 with at most 12 rooms (3 rows max)', () => {
    render(<RoomsView />);

    const nextBtn = screen.getByTitle(/Next Page/i);
    expect(nextBtn).not.toBeDisabled();
    fireEvent.click(nextBtn);

    // Page 2 shows items 12 to 23
    expect(screen.getByText(/Showing 12–23 of 25 rooms/i)).toBeInTheDocument();
    expect(screen.getByText(/\(Page 2 of 3\)/i)).toBeInTheDocument();

    // "Create New" card is NOT on page 2
    expect(screen.queryByText(/^Create New$/i)).toBeNull();

    // Room 14 (12th) and Room 03 (23rd) are on page 2
    expect(screen.getByText('Room 14')).toBeInTheDocument();
    expect(screen.getByText('Room 03')).toBeInTheDocument();
    expect(screen.queryByText('Room 25')).toBeNull();
    expect(screen.queryByText('Room 01')).toBeNull();
  });

  test('clicking specific page button navigates to that page', () => {
    render(<RoomsView />);

    // Click page "3" button
    const page3Btn = screen.getByRole('button', { name: '3' });
    fireEvent.click(page3Btn);

    // Page 3 shows remaining items (Room 02 and Room 01)
    expect(screen.getByText(/Showing 24–25 of 25 rooms/i)).toBeInTheDocument();
    expect(screen.getByText(/\(Page 3 of 3\)/i)).toBeInTheDocument();
    expect(screen.getByText('Room 02')).toBeInTheDocument();
    expect(screen.getByText('Room 01')).toBeInTheDocument();

    // Next button should now be disabled on the last page
    const nextBtn = screen.getByTitle(/Next Page/i);
    expect(nextBtn).toBeDisabled();
  });

  test('keyboard ArrowLeft and ArrowRight navigate between pages', () => {
    render(<RoomsView />);

    expect(screen.getByText(/\(Page 1 of 3\)/i)).toBeInTheDocument();

    // Press ArrowRight -> page 2
    fireEvent.keyDown(window, { key: 'ArrowRight' });
    expect(screen.getByText(/\(Page 2 of 3\)/i)).toBeInTheDocument();

    // Press ArrowLeft -> page 1
    fireEvent.keyDown(window, { key: 'ArrowLeft' });
    expect(screen.getByText(/\(Page 1 of 3\)/i)).toBeInTheDocument();
  });

  test('searching resets current page to page 1', () => {
    render(<RoomsView />);

    // Navigate to page 2 first
    const nextBtn = screen.getByTitle(/Next Page/i);
    fireEvent.click(nextBtn);
    expect(screen.getByText(/\(Page 2 of 3\)/i)).toBeInTheDocument();

    // Type a search query in the search input
    const searchInput = screen.getByPlaceholderText(/Search/i);
    fireEvent.change(searchInput, { target: { value: 'Room 25' } });

    // Page resets to 1 and shows only matching room
    expect(screen.getByText('Room 25')).toBeInTheDocument();
    expect(screen.queryByText('Room 12')).toBeNull();
  });
});
