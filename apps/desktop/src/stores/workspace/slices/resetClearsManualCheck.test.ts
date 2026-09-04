import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useWorkspaceStore } from '../../workspaceStore';

/**
 * `resetWorkspace` must clear the manual-check slice too.
 *
 * It cleared nine comparison fields and none of the manual ones until 2026-08-20. `leaveRoom`
 * calls it, so room A's session id, markings and half-made pair survived into room B — and the
 * symptom was not an error but a *plausible screen*: B's canvas rendered A's badges until B's
 * own session resolved, and `findMarkingForEntity` (which matches on handle and side, not on
 * drawing) refused to let the engineer mark any entity of B's whose handle collided with one of
 * A's. A click that does nothing, with no explanation, in the tool whose whole job is recording
 * clicks.
 *
 * Pinned as its own file rather than folded into a reset test elsewhere, because the failure is
 * an *omission*: a new manual field added later and not cleared here reproduces it exactly, and
 * this is the test that has to notice.
 */

vi.mock('../../reviewStore', () => ({
  useReviewStore: { getState: () => ({ resetCustomRegions: vi.fn() }) },
}));
vi.mock('../../historyStore', () => ({
  useHistoryStore: { getState: () => ({ clear: vi.fn() }) },
}));

const picked = {
  drawingId: 'ref1',
  side: 'ref' as const,
  entityId: 'e1',
  handle: '1B2A',
  parentHandle: null,
  entityType: 'text',
  layer: '0',
  text: '60',
  coordinates: [1, 2] as [number, number],
};

beforeEach(() => {
  useWorkspaceStore.setState({
    manualSessionId: 'sess-room-a',
    manualSessionPair: 'roomA:ref1:rev1',
    manualSessionError: 'stale',
    markingError: 'stale',
    markings: [{ id: 'm1' } as any],
    pendingPairRef: picked as any,
    pendingPairTool: 'matched',
    selectedEntities: [picked as any],
    selectionLocator: { side: 'ref', value: '60' } as any,
    selectionMenu: { x: 1, y: 2, drawingId: 'ref1' },
    selectionCounterpart: picked as any,
    hoverLocator: { side: 'rev', value: '60' } as any,
    hoveredEntityId: 'e1',
  });
});

describe('resetWorkspace', () => {
  it('leaves no manual-check state behind for the next room', () => {
    useWorkspaceStore.getState().resetWorkspace();
    const s = useWorkspaceStore.getState();

    expect(s.manualSessionId).toBeNull();
    expect(s.manualSessionPair).toBeNull();
    expect(s.manualSessionError).toBeNull();
    expect(s.markingError).toBeNull();
    expect(s.markings).toEqual([]);
    expect(s.pendingPairRef).toBeNull();
    expect(s.selectedEntities).toEqual([]);
    expect(s.selectionLocator).toBeNull();
    expect(s.selectionMenu).toBeNull();
    expect(s.selectionCounterpart).toBeNull();
    expect(s.hoverLocator).toBeNull();
    expect(s.hoveredEntityId).toBeNull();
  });

  it('returns the pairing verb to its default, not to the last room\'s', () => {
    // `pendingPairTool` is a verb, not a nullable — clearing `pendingPairRef` without it would
    // leave the next room's first pairing carrying the previous room's status.
    useWorkspaceStore.getState().resetWorkspace();
    expect(useWorkspaceStore.getState().pendingPairTool).toBe('changed');
  });

  it('is safe to run on a workspace that never opened a manual check', () => {
    useWorkspaceStore.setState({ manualSessionId: null, markings: [] });
    expect(() => useWorkspaceStore.getState().resetWorkspace()).not.toThrow();
  });
});
