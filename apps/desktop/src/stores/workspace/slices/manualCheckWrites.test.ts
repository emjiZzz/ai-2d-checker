import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useWorkspaceStore } from '../../workspaceStore';

/**
 * The three write paths of a manual check, and the rule they all broke.
 *
 * Every one of them swallowed its own failure until 2026-08-20, and the store is where the
 * swallowing has to be fixed because it is the only place all three meet. The costs were not
 * equal, and the middle one is why this file exists at all:
 *
 *  - a failed stamp produced no UI whatsoever — the menu closed, the entity stayed unmarked, and
 *    it was indistinguishable from a mis-click;
 *  - a failed retraction dropped the row from the panel while the server kept it LIVE.
 *    `eval_corpus.py from-manual-check` filters on `retracted_at`, so a retraction the server
 *    never applied is converted into a corpus finding the engineer explicitly withdrew — with
 *    the UI agreeing that it is gone. 31 of the 38 markings behind `M745204N01` were
 *    retractions, so this is the busiest path in the feature;
 *  - a failed submit still rendered "Check submitted".
 *
 * None of these raise. All three produce a plausible screen, which is why nothing caught them.
 */

vi.mock('../../../services/groundTruthApi', () => ({
  createManualCheckSession: vi.fn(),
  listMarkings: vi.fn(),
  createMarking: vi.fn(),
  retractMarking: vi.fn(),
  submitSession: vi.fn(),
}));

import {
  createMarking,
  retractMarking,
  submitSession,
} from '../../../services/groundTruthApi';

const picked = (side: 'ref' | 'rev', handle: string) => ({
  drawingId: side === 'ref' ? 'ref1' : 'rev1',
  side,
  entityId: `e-${handle}`,
  handle,
  parentHandle: null,
  entityType: 'text',
  layer: '0',
  text: '60',
  coordinates: [10, 20] as [number, number],
  zone: 'notes',
});

const marking = (id: string) => ({ id, status: 'ADDED', category: 'notes_section' }) as any;

const input = {
  category: 'notes_section',
  categorySource: 'human' as const,
  refText: '',
  revText: '60',
  textWasEdited: false,
  isBulk: false,
  notes: '',
};

beforeEach(() => {
  vi.clearAllMocks();
  useWorkspaceStore.setState({
    manualSessionId: 'sess1',
    markings: [],
    markingError: null,
    pendingPairRef: null,
  });
});

describe('recordStamp', () => {
  it('sends the address the engineer clicked, on the side the tool belongs to', async () => {
    vi.mocked(createMarking).mockResolvedValue(marking('m1'));

    await useWorkspaceStore
      .getState()
      .recordStamp({ tool: 'added', ref: null, rev: picked('rev', '1F7') as any }, input);

    const [sessionId, payload] = vi.mocked(createMarking).mock.calls[0];
    expect(sessionId).toBe('sess1');
    expect(payload.status).toBe('ADDED');
    expect(payload.ref_address).toBeNull();
    expect(payload.rev_address).toMatchObject({ drawing_id: 'rev1', handle: '1F7' });
    // Sent as a bare pair. The server stamps coordinate space and render bounds, because it owns
    // the DrawingDocument and this client does not.
    expect(payload.rev_address?.coordinates).toEqual([10, 20]);
  });

  it('records where the category came from, because attribution depends on it', async () => {
    // The mutation corpus's attribution figure is a known tautology — its labels come from
    // `zone_detector`. The human pairs were the first non-tautological numbers, and that holds
    // only while an evaluator can tell a derived category from a chosen one.
    vi.mocked(createMarking).mockResolvedValue(marking('m1'));

    await useWorkspaceStore
      .getState()
      .recordStamp({ tool: 'added', ref: null, rev: picked('rev', '1F7') as any }, {
        ...input,
        categorySource: 'zone',
      });

    expect(vi.mocked(createMarking).mock.calls[0][1].category_source).toBe('zone');
  });

  it('appends only what the server confirmed', async () => {
    vi.mocked(createMarking).mockResolvedValue(marking('m1'));

    await useWorkspaceStore
      .getState()
      .recordStamp({ tool: 'added', ref: null, rev: picked('rev', '1F7') as any }, input);

    expect(useWorkspaceStore.getState().markings).toHaveLength(1);
    expect(useWorkspaceStore.getState().markingError).toBeNull();
  });

  it('surfaces a failed write instead of leaving the entity silently unmarked', async () => {
    vi.mocked(createMarking).mockRejectedValue(new Error('createMarking failed (500): boom'));

    await useWorkspaceStore
      .getState()
      .recordStamp({ tool: 'added', ref: null, rev: picked('rev', '1F7') as any }, input);

    expect(useWorkspaceStore.getState().markings).toHaveLength(0);
    expect(useWorkspaceStore.getState().markingError).toMatch(/NOT recorded/);
  });

  it('does not reject — the caller has no error UI of its own', async () => {
    // `SelectionMenu` used to hold a bare `.catch(() => {})` on the comment that the store
    // surfaces failures. It did not. The store settles and reports through `markingError`, so
    // there is nothing left for the menu to swallow.
    vi.mocked(createMarking).mockRejectedValue(new Error('boom'));

    await expect(
      useWorkspaceStore
        .getState()
        .recordStamp({ tool: 'added', ref: null, rev: picked('rev', '1F7') as any }, input),
    ).resolves.toBeUndefined();
  });

  it('repairs a dead session id so the app does not dead-end', async () => {
    /*
      The self-heal: `TwoDWorkspace`'s open effect watches `manualSessionId` and reopens as soon
      as it goes null, so the next stamp lands in a live session. The id lives only in memory, so
      without this every retry re-sends the same dead id and the only way out is a restart.

      This branch had NEVER run. Its test read a word-boundary form whose escapes had been
      mangled into two literal backspace bytes (0x08), so the regex matched only a message
      containing a backspace character. Found 2026-08-20 by reading the file's bytes.
    */
    vi.mocked(createMarking).mockRejectedValue(
      new Error('createMarking failed (404): Manual check session not found: sess1'),
    );

    await useWorkspaceStore
      .getState()
      .recordStamp({ tool: 'added', ref: null, rev: picked('rev', '1F7') as any }, input);

    expect(useWorkspaceStore.getState().manualSessionId).toBeNull();
    expect(useWorkspaceStore.getState().markingError).toMatch(/no longer exists/);
  });

  it('reports a stamp made before a session was open', async () => {
    useWorkspaceStore.setState({ manualSessionId: null });

    await useWorkspaceStore
      .getState()
      .recordStamp({ tool: 'added', ref: null, rev: picked('rev', '1F7') as any }, input);

    expect(createMarking).not.toHaveBeenCalled();
    expect(useWorkspaceStore.getState().markingError).toMatch(/No check session/);
  });
});

describe('retractManualMarking', () => {
  it('drops the row once the server has confirmed it', async () => {
    vi.mocked(retractMarking).mockResolvedValue(undefined as any);
    useWorkspaceStore.setState({ markings: [marking('m1'), marking('m2')] });

    const ok = await useWorkspaceStore.getState().retractManualMarking('m1');

    expect(ok).toBe(true);
    expect(useWorkspaceStore.getState().markings.map((m) => m.id)).toEqual(['m2']);
  });

  it('KEEPS the row when the server did not confirm it', async () => {
    /*
      The one that fabricates ground truth. Dropping locally on failure leaves the panel agreeing
      with the engineer and the database disagreeing — and the export path reads the database.
      `from-manual-check` filters on `retracted_at`, so a retraction that never applied comes
      back as a live marking and becomes a finding the engineer withdrew, in a committed label
      file, with nothing downstream able to tell.
    */
    vi.mocked(retractMarking).mockRejectedValue(new Error('retract failed (503)'));
    useWorkspaceStore.setState({ markings: [marking('m1'), marking('m2')] });

    const ok = await useWorkspaceStore.getState().retractManualMarking('m1');

    expect(ok).toBe(false);
    expect(useWorkspaceStore.getState().markings.map((m) => m.id)).toEqual(['m1', 'm2']);
    expect(useWorkspaceStore.getState().markingError).toMatch(/still recorded on the server/);
  });
});

describe('submitManualSession', () => {
  it('reports success only when the server accepted it', async () => {
    vi.mocked(submitSession).mockResolvedValue(undefined as any);

    await expect(useWorkspaceStore.getState().submitManualSession()).resolves.toBe(true);
  });

  it('reports failure so the panel cannot say "Check submitted"', async () => {
    // `ManualMarkingList` set `submitted` unconditionally after awaiting this, and the store
    // swallowed — so a session still marked `in_progress` on the server rendered as finished,
    // and the engineer walked away from it.
    vi.mocked(submitSession).mockRejectedValue(new Error('submit failed (500)'));

    await expect(useWorkspaceStore.getState().submitManualSession()).resolves.toBe(false);
    expect(useWorkspaceStore.getState().markingError).toMatch(/NOT submitted/);
  });

  it('says so rather than silently doing nothing when no session is open', async () => {
    useWorkspaceStore.setState({ manualSessionId: null });

    await expect(useWorkspaceStore.getState().submitManualSession()).resolves.toBe(false);
    expect(submitSession).not.toHaveBeenCalled();
  });
});

describe('clearMarkingError', () => {
  it('clears, and is a no-op when there is nothing to clear', async () => {
    useWorkspaceStore.setState({ markingError: 'boom' });
    useWorkspaceStore.getState().clearMarkingError();
    expect(useWorkspaceStore.getState().markingError).toBeNull();

    // Identity guard: a `set` here on every render would repaint the panel for nothing.
    const before = useWorkspaceStore.getState();
    useWorkspaceStore.getState().clearMarkingError();
    expect(useWorkspaceStore.getState()).toBe(before);
  });
});
