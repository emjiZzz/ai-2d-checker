import { describe, it, expect, beforeEach, vi } from 'vitest';

/**
 * Re-entering a room must bring back the checkmarks, not just the findings.
 *
 * `orchestrator.py` persists an `AuditViolation` only for NON-MATCHED rows
 * (`non_matched = [m for m in clean_markings if m.get("status") != "MATCHED"]`), because there
 * is nothing to review about a row that matched. Every green checkmark therefore lives only in
 * the room's `physical_comparison_results.canvas_markings`.
 *
 * `openRoom` used to restore from the session's violations whenever the room had an
 * `active_audit_session_id` — which is every room a comparison has been run in — and the
 * canvas_markings restore sat in the unreachable `else`. Results came back; checkmarks did not.
 */

vi.mock('../../services/fetchUtils', () => ({
  baseUrl: () => 'http://localhost',
  buildHeaders: () => ({}),
  parseOrThrow: (res: any) => Promise.resolve(res._body),
  parseAndValidate: (res: any) => Promise.resolve(res._body),
}));

vi.mock('../workspaceStore', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../workspaceStore')>();
  return {
    ...actual,
    saveWorkspaceState: vi.fn(() => Promise.resolve()),
    loadWorkspaceState: vi.fn(() => Promise.resolve()),
  };
});

import { useRoomStore } from '../roomStore';
import { useWorkspaceStore } from '../workspaceStore';

const SESSION_ID = 'sess_1';

/** MATCHED rows are the checkmarks; the CHANGED row is the only one with a persisted violation. */
const CANVAS_MARKINGS = [
  { status: 'MATCHED', category: 'title_block', text_content: 'SCALE 1/1', entity_id: 'h1' },
  { status: 'MATCHED', category: 'bill_of_materials', text_content: 'SS400', entity_id: 'h2' },
  {
    status: 'CHANGED',
    category: 'title_block',
    text_content: '0.12',
    details: 'weight changed',
    entity_id: 'h3',
  },
];

const PERSISTED_VIOLATIONS = [
  {
    id: 'viol_real_1',
    category: 'comparison_title_block',
    description: '[CHANGED] weight changed',
    recommendation: "Resolve discrepancy in '0.12' against the reference drawing.",
    affected_entities: [{ entity_id: 'h3' }],
  },
];

function mockRoomFetches(room: Record<string, unknown>) {
  global.fetch = vi.fn((url: any) => {
    const u = String(url);
    const body = (b: any) => Promise.resolve({ _body: b, ok: true } as any);

    if (u.includes('/rooms/')) return body(room);
    if (u.includes('/drawings/')) {
      return body({ id: 'dwg', file_name: 'd.dxf', file_path: 'p', format: 'dxf', entity_counts: {}, metadata: {}, created_at: '' });
    }
    if (u.includes(`/sessions/${SESSION_ID}/violations`)) return body(PERSISTED_VIOLATIONS);
    if (u.includes(`/sessions/${SESSION_ID}`)) return body({ compliance_score: 92, client_name: 'KMTI' });
    return body({});
  }) as any;
}

const baseRoom = {
  id: 'room_228',
  name: '228',
  description: null,
  active_old_drawing_id: 'old_1',
  active_new_drawing_id: 'new_1',
};

describe('roomStore.openRoom — restoring a compared room', () => {
  beforeEach(() => {
    useRoomStore.setState({ activeRoom: null, rooms: [], isLoading: false, error: null });
    useWorkspaceStore.setState({ violations: [], activeSessionId: null });
    vi.clearAllMocks();
  });

  it('restores MATCHED checkmarks for a room that has an audit session', async () => {
    mockRoomFetches({
      ...baseRoom,
      active_audit_session_id: SESSION_ID,
      physical_comparison_results: { canvas_markings: CANVAS_MARKINGS },
    });

    await useRoomStore.getState().openRoom('room_228');

    const { violations } = useWorkspaceStore.getState();
    const matched = violations.filter((v: any) => v.status === 'MATCHED');

    // The regression: this used to be 0 — the session carries only the CHANGED finding.
    expect(matched).toHaveLength(2);
    expect(violations).toHaveLength(3);
    expect(matched.every((v: any) => v.is_resolved)).toBe(true);
    expect(matched.every((v: any) => v.pen_type === 'resolved_green')).toBe(true);
  });

  it('still gives the reviewable finding its real persisted id', async () => {
    // Restoring from canvas_markings must not cost the review identity that the session
    // violations provide — the markers carry synthetic ids, so the join is what makes a
    // supervisor verdict PATCH a document that exists.
    mockRoomFetches({
      ...baseRoom,
      active_audit_session_id: SESSION_ID,
      physical_comparison_results: { canvas_markings: CANVAS_MARKINGS },
    });

    await useRoomStore.getState().openRoom('room_228');

    const { violations } = useWorkspaceStore.getState();
    const changed = violations.find((v: any) => v.status === 'CHANGED') as any;

    expect(changed.persisted_id).toBe('viol_real_1');
    // MATCHED rows are never persisted, so they stay unreviewable — by design, not by accident.
    violations
      .filter((v: any) => v.status === 'MATCHED')
      .forEach((v: any) => expect(v.persisted_id).toBeUndefined());
  });

  it('falls back to the session violations when the room stored no markings', async () => {
    // An audit that was not a physical comparison has no canvas_markings. The new branch must
    // add rows, never remove them.
    mockRoomFetches({
      ...baseRoom,
      active_audit_session_id: SESSION_ID,
      physical_comparison_results: null,
    });

    await useRoomStore.getState().openRoom('room_228');

    const { violations, activeSessionId } = useWorkspaceStore.getState();
    expect(activeSessionId).toBe(SESSION_ID);
    expect(violations).toHaveLength(PERSISTED_VIOLATIONS.length);
  });

  it('still restores markings for a room with no audit session', async () => {
    // The pre-existing no-session path, which was the only one that worked.
    mockRoomFetches({
      ...baseRoom,
      active_audit_session_id: null,
      physical_comparison_results: { canvas_markings: CANVAS_MARKINGS },
    });

    await useRoomStore.getState().openRoom('room_228');

    const { violations } = useWorkspaceStore.getState();
    expect(violations.filter((v: any) => v.status === 'MATCHED')).toHaveLength(2);
  });
});
