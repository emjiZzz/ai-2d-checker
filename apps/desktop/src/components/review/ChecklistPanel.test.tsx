import { render, screen, within } from '@testing-library/react';
import { expect, test, vi, describe } from 'vitest';
import { ChecklistPanel } from './ChecklistPanel';
import { useWorkspaceStore } from '../../stores/workspaceStore';

// Audit finding #4 (docs/refactoring-audit-2026-07-23.md): ChecklistPanel's inline
// `isMatch` helper (used to associate a BOM/title-block diff row with a violation
// marker) changed matching semantics for short (<=2 char) and purely symbolic
// (e.g. "-") tokens to require exact equality instead of substring containment,
// to avoid tokens like "-" or "5" spuriously matching unrelated violation
// descriptions. These tests lock in that behavior via the component's actual
// rendered output (the helper itself isn't exported), using pen_type="ai_conflict"
// on the linked violation as an unambiguous "this row got linked" signal: it flips
// the row's badge text from the table's own "MATCHED" status to "CONFLICT" only
// when `matchingViolation` is truthy.

vi.mock('../../stores/workspaceStore', () => ({
  useWorkspaceStore: vi.fn(),
}));

function mockWorkspace(violations: any[]) {
  const state = {
    violations,
    hiddenViolationIds: {},
    selectedViolation: null,
    selectViolation: vi.fn(),
    toggleViolationVisibility: vi.fn(),
    setViolationsVisibility: vi.fn(),
    applyViolationReview: vi.fn(),
    activeSessionId: null,
  };
  (useWorkspaceStore as unknown as ReturnType<typeof vi.fn>).mockImplementation(
    (selector: (s: typeof state) => unknown) => selector(state)
  );
}

function tableResult(rows: Array<{ field: string; original: string; kmti: string }>) {
  const header = '| FIELD | ORIGINAL | KMTI | STATUS |';
  const separator = '|---|---|---|---|';
  const dataLines = rows.map(
    (r) => `| ${r.field} | ${r.original} | ${r.kmti} | MATCHED |`
  );
  return {
    status: 'MATCHED',
    reference_content: [header, separator, ...dataLines].join('\n'),
  };
}

/** Reads the badge text ("MATCHED" or "CONFLICT") for the row whose field label matches `field`. */
function badgeTextForRow(field: string): string {
  const fieldEl = screen.getByText(field);
  const card = fieldEl.closest('div')!.parentElement!.parentElement as HTMLElement;
  // Find the badge by its content rather than by position in the card. The original walked
  // `card.querySelector('div > span')`, which broke the moment anything else in the card led with
  // a span -- the ReviewControls verdict row did exactly that. Content is the stable handle.
  return within(card)
    .getByText((_content, el) =>
      el?.tagName === 'SPAN' && /^(MATCHED|CONFLICT|CHANGED|ADDED|REMOVED)$/.test(el.textContent?.trim() ?? '')
    )
    .textContent!;
}

describe('ChecklistPanel row-to-violation text matching', () => {
  test('short (<=2 char) kmti token requires exact match, not substring containment', () => {
    // "15" contains "5" as a substring — under the pre-fix substring-containment
    // logic this would have falsely linked; the length<=2 guard requires exact
    // equality, so it must NOT link here.
    mockWorkspace([
      {
        id: 'v1',
        description: '15',
        category: 'bill_of_materials',
        pen_type: 'ai_conflict',
      },
    ]);
    render(
      <ChecklistPanel
        aiChecklistResults={{
          bill_of_materials: tableResult([{ field: 'MassProperty', original: '9', kmti: '5' }]),
        }}
      />
    );
    expect(badgeTextForRow('MassProperty')).toBe('MATCHED'); // unlinked -> table's own status
  });

  test('symbolic-only ("-") kmti token requires exact match, not substring containment', () => {
    // "AB-100" contains "-" as a substring — under the pre-fix logic this would have
    // falsely linked any hyphenated part number to a placeholder "-" cell.
    mockWorkspace([
      {
        id: 'v2',
        description: 'AB-100',
        category: 'bill_of_materials',
        pen_type: 'ai_conflict',
      },
    ]);
    render(
      <ChecklistPanel
        aiChecklistResults={{
          bill_of_materials: tableResult([{ field: 'FinishSpec', original: '-', kmti: '-' }]),
        }}
      />
    );
    expect(badgeTextForRow('FinishSpec')).toBe('MATCHED'); // unlinked -> table's own status
  });

  // --- one marker, one row -------------------------------------------------------------
  //
  // Reported live: "I click some item cards in the side panel and it shows a different
  // pair, and vice versa." The row->violation resolution was a plain `violations.find(...)`
  // per row with no record of what had already been taken, so several rows could resolve to
  // the SAME marker. Clicking any of them selected that one marker, and the row that actually
  // owned it was left pointing at nothing or at someone else's.

  test('a violation is claimed by at most one row', () => {
    mockWorkspace([
      { id: 'v4', description: '230', category: 'title_block', pen_type: 'ai_conflict' },
    ]);
    render(
      <ChecklistPanel
        aiChecklistResults={{
          title_block: tableResult([
            { field: 'CodeNo', original: '230', kmti: '230' },
            { field: 'PartNo', original: '230', kmti: '230' },
          ]),
        }}
      />
    );
    const badges = [badgeTextForRow('CodeNo'), badgeTextForRow('PartNo')];
    expect(badges.filter((b) => b === 'CONFLICT')).toHaveLength(1);
    expect(badges.filter((b) => b === 'MATCHED')).toHaveLength(1);
  });

  test('an exact match wins the marker over an earlier row that only matches by substring', () => {
    // `1230`.includes(`230`) is true, so under a single greedy pass in row order the first
    // row stole the marker that the second row matched exactly.
    mockWorkspace([
      { id: 'v5', description: '230', category: 'title_block', pen_type: 'ai_conflict' },
    ]);
    render(
      <ChecklistPanel
        aiChecklistResults={{
          title_block: tableResult([
            { field: 'StockQty', original: '1230', kmti: '1230' },
            { field: 'CodeNo', original: '230', kmti: '230' },
          ]),
        }}
      />
    );
    expect(badgeTextForRow('CodeNo')).toBe('CONFLICT');
    expect(badgeTextForRow('StockQty')).toBe('MATCHED');
  });

  test('normal (non-symbolic, >2 char) kmti token still matches via substring containment', () => {
    mockWorkspace([
      {
        id: 'v3',
        description: 'Assembly uses Steel Grade A36 per spec sheet',
        category: 'bill_of_materials',
        pen_type: 'ai_conflict',
      },
    ]);
    render(
      <ChecklistPanel
        aiChecklistResults={{
          bill_of_materials: tableResult([
            { field: 'MaterialGrade', original: 'Steel', kmti: 'Steel Grade A36' },
          ]),
        }}
      />
    );
    expect(badgeTextForRow('MaterialGrade')).toBe('CONFLICT'); // linked -> violation's pen_type wins
  });

  test('calculates Completion Parity at item-level rather than all-or-nothing category level', () => {
    mockWorkspace([]);
    const header = '| FIELD | ORIGINAL | KMTI | STATUS |';
    const separator = '|---|---|---|---|';
    const rows = [
      '| Field1 | A | A | MATCHED |',
      '| Field2 | B | B | MATCHED |',
      '| Field3 | C | C | MATCHED |',
      '| Field4 | D | D | MATCHED |',
      '| Field5 | E | F | CHANGED |',
    ];
    render(
      <ChecklistPanel
        aiChecklistResults={{
          title_block: {
            status: 'CHANGED', // Top-level status is CHANGED
            reference_content: [header, separator, ...rows].join('\n'),
          },
        }}
      />
    );
    // 4 out of 5 rows are MATCHED -> 80% MATCHED
    expect(screen.getByText('80% MATCHED')).toBeInTheDocument();
  });
});

describe('ChecklistPanel finding-card layout structure', () => {
  /** A 24-hex Mongo ObjectId. `isPersistedViolationId` gates the verdict controls on this shape,
   *  so a placeholder like 'v1' would silently render a card with no verdict block. */
  const PERSISTED_ID = '507f1f77bcf86cd799439011';

  /** Renders one linked finding and returns its card element. */
  function renderLinkedFinding(violationOverrides: Record<string, unknown> = {}): HTMLElement {
    mockWorkspace([
      {
        id: PERSISTED_ID,
        description: 'B',
        category: 'title_block',
        pen_type: 'ai_conflict',
        resolution_type: null,
        checker_remarks: null,
        ...violationOverrides,
      },
    ]);
    // Field name deliberately not a taxonomy label ("Scale", "Title", ...) — those also render as
    // feature-group headers, and getByText would find two elements.
    render(<ChecklistPanel aiChecklistResults={{ title_block: tableResult([{ field: 'WidgetRef', original: 'A', kmti: 'B' }]) }} />);
    return screen.getByText('WidgetRef').closest('div')!.parentElement!.parentElement as HTMLElement;
  }

  test('verdict controls are a child of the card, not of the Dismiss/Correct row', () => {
    // The bug this pins: ReviewControls was appended as a fourth inline child of the badge row,
    // which is a nowrap flex row. Its own `flex: 0 0 100%` could not wrap there, so it overflowed
    // into the panel's overflow-x:hidden and "Approve" rendered as "Ap". Being a direct child of
    // the card's COLUMN flex is what actually gives it a full-width line -- no CSS can rescue it
    // from inside that row.
    const card = renderLinkedFinding();
    const controls = within(card).getByTestId('review-controls');

    expect(controls.parentElement).toBe(card);

    const dismissRow = within(card).getByText('Dismiss').closest('div')!.parentElement!;
    expect(dismissRow.contains(controls)).toBe(false);
  });

  test('verdict controls render below the comparison values, not above them', () => {
    // Evidence before verdict: a reviewer should see Original vs Revision before deciding.
    const card = renderLinkedFinding();
    const grid = card.querySelector('.cmp-grid-diff')!;
    const controls = within(card).getByTestId('review-controls');

    expect(grid.compareDocumentPosition(controls) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  test('comparison values keep both columns in the DOM order a two-up grid needs', () => {
    // The grid is deliberately never stacked -- two values you cannot see side by side are not a
    // comparison. That makes source order load-bearing: header, header, value, value.
    const card = renderLinkedFinding();
    const grid = card.querySelector('.cmp-grid-diff')!;

    expect([...grid.children].map((c) => c.className)).toEqual([
      'cmp-title',
      'cmp-h-ref',
      'cmp-h-rev',
      'cmp-v-ref',
      'cmp-v-rev',
    ]);
  });
});

describe('ChecklistPanel offers a verdict only where one can be recorded', () => {
  /* These pin a live 500. The verdict block was gated on `matchingViolation` alone, so it
     appeared on rows the server cannot accept a review for, and clicking Approve produced
     `PATCH /audits/violations/phys_chk_restored_1_1786329084013/review -> 500`.

     The backend now answers 404 for a malformed id (tests/test_malformed_id_is_404.py), but a
     404 rendered in red still tells a reviewer their verdict failed to save on a row that was
     never reviewable. The control must not be offered in the first place. */

  const PERSISTED_ID = '507f1f77bcf86cd799439011';

  function renderWith(violation: Record<string, unknown>) {
    mockWorkspace([{ category: 'title_block', description: 'B', ...violation }]);
    render(
      <ChecklistPanel
        aiChecklistResults={{ title_block: tableResult([{ field: 'WidgetRef', original: 'A', kmti: 'B' }]) }}
      />
    );
  }

  test('a client-side canvas marker gets no verdict controls', () => {
    // The exact id from the production traceback. Synthesised in markerGenerator.ts; there is no
    // AuditViolation document behind it, so no review can be recorded against it.
    renderWith({ id: 'phys_chk_restored_1_1786329084013', pen_type: 'ai_conflict' });

    expect(screen.queryByTestId('review-controls')).toBeNull();
  });

  test('a MATCHED row gets no verdict controls', () => {
    // The engine reporting no change. There is nothing to approve, and the orchestrator never
    // persists one as an AuditViolation — so even a well-formed id would have nothing behind it.
    renderWith({ id: PERSISTED_ID, pen_type: 'resolved_green' });

    expect(screen.queryByTestId('review-controls')).toBeNull();
  });

  test('a persisted, non-MATCHED finding still gets them', () => {
    // The guard must not be so broad that it removes the feature it is protecting.
    renderWith({ id: PERSISTED_ID, pen_type: 'ai_conflict' });

    expect(screen.getByTestId('review-controls')).toBeTruthy();
  });

  test('a synthetic marker joined to a persisted violation becomes reviewable', () => {
    // The actual production shape: the canvas id is always synthetic, and `reconcilePersistedIds`
    // attaches `persisted_id` from GET /audits/sessions/{id}/violations. This is what puts the
    // verdict back on real findings rather than removing it everywhere.
    renderWith({
      id: 'phys_chk_restored_1_1786329084013',
      persisted_id: PERSISTED_ID,
      pen_type: 'ai_conflict',
    });

    expect(screen.getByTestId('review-controls')).toBeTruthy();
  });
});
