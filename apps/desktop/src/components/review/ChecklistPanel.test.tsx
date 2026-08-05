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
  // Card structure: outer row div > badge row div > [.., <span>STATUS</span>]
  const card = fieldEl.closest('div')!.parentElement!.parentElement as HTMLElement;
  const badgeRow = card.querySelector('div > span')?.parentElement as HTMLElement;
  return within(badgeRow).getByText(/MATCHED|CONFLICT|CHANGED|ADDED|REMOVED/).textContent!;
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
