/* eslint-disable no-restricted-syntax --
 * Arranging store state IS the test fixture here, which is the "not production data flow" case
 * the rule's own message carves out. Going through named actions would mean opening a real
 * manual-check session over the network just to assert on a badge.
 *
 * Suppressed rather than left to accumulate: five other test files already trip this rule
 * unsuppressed (createUploadSlice, historyStore, createAnnotationsSlice, roomStore.openRoom,
 * SavedTemplatesModal). That backlog is not this change's to fix, but it is not this change's to
 * grow either.
 */

/**
 * The stale-extraction warning must be reachable in a manual-check room.
 *
 * This is a regression test for a *structural* blind spot rather than a rendering bug.
 * `StaleExtractionBadge` used to live only in `TwoDRightPanel`, which renders only when
 * `isPhysicalComparisonEnabled || aiScanProgress === "completed" || isStandardsAuditCompleted`.
 * The first of those is written in exactly one place — `usePhysicalComparison`, after the
 * comparison engine runs — and prototype mode forces every room to `manual_check`, so the engine
 * never runs and the panel is never created. The badge was therefore unreachable in precisely the
 * build handed to engineers to collect ground truth, on an estate where
 * `tools/extraction_status.py` reported 38 of 65 drawings stale and 20 at v2.
 *
 * A stale sheet renders wrong while looking ordinary, so nothing else would have flagged it.
 */
import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ManualMarkingList } from './ManualMarkingList';
import { useWorkspaceStore } from '../../stores/workspaceStore';
import { useRoomStore } from '../../stores/roomStore';

// The export hook reaches for canvases, jsPDF and Tauri dialogs; none of that is under test here.
vi.mock('../../hooks/useComplianceReportExport', () => ({
  useComplianceReportExport: () => ({
    exportToPDF: vi.fn(),
    isExporting: false,
    exportPhase: null,
    exportStatus: null,
    revealExport: vi.fn(),
  }),
}));

const drawing = (over: Record<string, unknown> = {}) => ({
  id: 'd1',
  file_name: 'M7452A2N01_reference.dxf',
  file_path: '/storage/uploads/d1.dxf',
  format: 'dxf',
  entity_counts: {},
  metadata: {},
  created_at: '2026-08-20T00:00:00Z',
  ...over,
});

const stale = (over: Record<string, unknown> = {}) =>
  drawing({
    extraction_is_stale: true,
    extraction_schema_version: 2,
    current_extraction_schema_version: 7,
    ...over,
  });

beforeEach(() => {
  // A manual-check room, which is what a prototype build forces every room to be.
  useRoomStore.setState({ activeRoom: { id: 'r1', room_mode: 'manual_check' } as never });
  useWorkspaceStore.setState({
    markings: [],
    annotations: [],
    manualSessionId: 's1',
    manualSessionError: null,
    manualSessionStatus: 'in_progress',
    markingError: null,
    pendingPairRef: null,
    oldDrawing: null,
    newDrawing: null,
  } as never);
});

afterEach(() => {
  useRoomStore.setState({ activeRoom: null });
  vi.unstubAllEnvs();
});

describe('ManualMarkingList — stale extraction', () => {
  it('warns when the reference drawing is stale', () => {
    useWorkspaceStore.setState({
      oldDrawing: stale({ id: 'ref' }),
      newDrawing: drawing({ id: 'rev', extraction_is_stale: false }),
    } as never);

    render(<ManualMarkingList />);

    expect(screen.getByText(/Reference/)).toBeInTheDocument();
  });

  it('warns when the revision drawing is stale', () => {
    useWorkspaceStore.setState({
      oldDrawing: drawing({ id: 'ref', extraction_is_stale: false }),
      newDrawing: stale({ id: 'rev' }),
    } as never);

    render(<ManualMarkingList />);

    expect(screen.getByText(/Revision/)).toBeInTheDocument();
  });

  it('stays silent when both drawings are current', () => {
    /**
     * The half that makes the warning mean something. An always-on badge is one engineers stop
     * seeing within a day, and most of the estate is stale — so the healthy state must be
     * invisible, not a reassuring tick.
     */
    useWorkspaceStore.setState({
      oldDrawing: drawing({ id: 'ref', extraction_is_stale: false }),
      newDrawing: drawing({ id: 'rev', extraction_is_stale: false }),
    } as never);

    render(<ManualMarkingList />);

    expect(screen.queryByText(/Reference/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Revision/)).not.toBeInTheDocument();
  });

  it('stays silent when the backend never sent the flag', () => {
    // `undefined` means "cannot judge", which is not the same claim as "stale". Inventing a
    // warning from missing data is how a badge loses its credibility.
    useWorkspaceStore.setState({
      oldDrawing: drawing({ id: 'ref' }),
      newDrawing: drawing({ id: 'rev' }),
    } as never);

    render(<ManualMarkingList />);

    expect(screen.queryByText(/Reference/)).not.toBeInTheDocument();
  });
});
