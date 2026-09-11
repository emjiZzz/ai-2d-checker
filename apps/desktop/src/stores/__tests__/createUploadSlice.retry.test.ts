import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useWorkspaceStore } from '../workspaceStore';

/**
 * Retrying a failed extraction, rather than uploading the same file again.
 *
 * Dedupe is deliberately gone from ingestion -- two uploads of the same bytes must not share a
 * file, or purging one drawing orphans the other -- so a re-upload is a second drawing. On
 * 2026-09-07 that turned two failed ingestions into four rows for two sheets, and the only
 * recovery the UI offered was "Try Another File".
 *
 * `/reextract` is the intended path and keeps the drawing's id, room slot and history. These pin
 * the three states that decide whether it is offered at all.
 */
vi.mock('../../services/fetchUtils', () => ({
  uploadFile: vi.fn(),
  baseUrl: vi.fn(() => 'http://localhost'),
  buildHeaders: vi.fn(() => ({})),
  parseOrThrow: vi.fn(),
}));

vi.mock('../../services/drawingsApi', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../services/drawingsApi')>();
  return {
    ...actual,
    deleteDrawing: vi.fn(() => Promise.resolve()),
    reextractDrawing: vi.fn(),
  };
});

import { reextractDrawing } from '../../services/drawingsApi';

describe('retryExtraction', () => {
  beforeEach(() => {
    useWorkspaceStore.setState({
      oldUploadState: 'idle',
      newUploadState: 'idle',
      oldError: null,
      newError: null,
      oldFailedDrawingId: null,
      newFailedDrawingId: null,
      activeOldJobId: null,
      activeNewJobId: null,
    });
    vi.clearAllMocks();
  });

  it('records the drawing and the reason when an extraction fails', () => {
    useWorkspaceStore.getState().setUploadFailure('old', 'draw-1', 'ran out of memory');
    const s = useWorkspaceStore.getState();
    expect(s.oldUploadState).toBe('failed');
    expect(s.oldFailedDrawingId).toBe('draw-1');
    expect(s.oldError).toBe('ran out of memory');
  });

  it('offers nothing to retry when the failure happened before a row existed', async () => {
    /** A polling failure knows nothing about the server's state, so there is no id to retry. */
    useWorkspaceStore.getState().setUploadFailure('old', null, 'lost contact');
    const ok = await useWorkspaceStore.getState().retryExtraction('old');
    expect(ok).toBe(false);
    expect(reextractDrawing).not.toHaveBeenCalled();
  });

  it('re-extracts the existing drawing instead of creating a second one', async () => {
    vi.mocked(reextractDrawing).mockResolvedValue({ id: 'job-9' } as { id: string });
    useWorkspaceStore.getState().setUploadFailure('new', 'draw-2', 'boom');

    const ok = await useWorkspaceStore.getState().retryExtraction('new');

    expect(ok).toBe(true);
    expect(reextractDrawing).toHaveBeenCalledWith('draw-2');
    const s = useWorkspaceStore.getState();
    expect(s.newUploadState).toBe('processing');
    expect(s.activeNewJobId).toBe('job-9');
    // Cleared so the button stops being offered while the retry is in flight.
    expect(s.newFailedDrawingId).toBeNull();
  });

  it('stops offering a retry when the source file is gone', async () => {
    /**
     * 422 is what an ephemeral disk produces: the upload was discarded before extraction ran,
     * which is exactly what Render's free tier did twice. Retrying cannot fix it, so the id is
     * dropped and the message says to upload again.
     */
    vi.mocked(reextractDrawing).mockRejectedValue(new Error('Request failed: 422'));
    useWorkspaceStore.getState().setUploadFailure('old', 'draw-3', 'boom');

    const ok = await useWorkspaceStore.getState().retryExtraction('old');

    expect(ok).toBe(false);
    const s = useWorkspaceStore.getState();
    expect(s.oldUploadState).toBe('failed');
    expect(s.oldFailedDrawingId).toBeNull();
    expect(s.oldError).toMatch(/no longer on the server/i);
  });

  it('keeps the retry available when the failure is not a missing file', async () => {
    /** A 409 means an extraction is already running; that resolves on its own and is retryable. */
    vi.mocked(reextractDrawing).mockRejectedValue(new Error('Request failed: 409'));
    useWorkspaceStore.getState().setUploadFailure('old', 'draw-4', 'boom');

    await useWorkspaceStore.getState().retryExtraction('old');

    expect(useWorkspaceStore.getState().oldFailedDrawingId).toBe('draw-4');
  });
});
