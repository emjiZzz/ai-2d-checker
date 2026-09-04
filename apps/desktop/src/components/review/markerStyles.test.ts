import { describe, it, expect } from 'vitest';
import {
  MARKER_STYLES,
  MARKER_SIDE,
  PEN_TYPE_TO_MARKER,
  markerStyle,
  markerTypeOf,
  markerUi,
  markingsToMarkers,
  type MarkerType,
} from './markerStyles';
import { TOOL_SIDE } from '../../stores/workspace/slices/createManualCheckSlice';

/**
 * One taxonomy, one appearance, one side rule.
 *
 * These tests exist because there were two of each. The engine's markers and the manual-check
 * badges drew the same status in different colours, and neither could tell — both rendered
 * fine. The tests below are the thing that now cannot be silently reintroduced.
 */

const marking = (over: Record<string, any> = {}) => ({
  id: 'm1',
  status: 'MATCHED',
  category: 'bom_table',
  ref_text: '4 ロール：12 (2x6台)',
  rev_text: '４ロール：１２（２×６台）',
  ref_coordinates: [100, 200],
  rev_coordinates: [300, 400],
  retracted_at: null,
  is_bulk: false,
  ...over,
});

describe('the shared marker table', () => {
  it('covers every status a marking can carry', () => {
    // A status with no entry falls back to MISMATCHED — red, and labelled as something the
    // engineer never said. Cheaper to fail here than to explain a red badge on a MATCHED row.
    for (const status of ['MATCHED', 'ADDED', 'REMOVED', 'CHANGED', 'NOT_A_FINDING']) {
      expect(MARKER_STYLES[status as MarkerType], status).toBeDefined();
    }
  });

  it('covers every pen type a stored violation can carry', () => {
    // Cached audit payloads hold `pen_type`. An unmapped one would drop the marker entirely,
    // and the audit it belongs to is not re-runnable without invalidating its cache.
    for (const pen of ['ai_red', 'ai_orange', 'checker_blue', 'ai_green', 'resolved_green', 'ai_conflict']) {
      expect(PEN_TYPE_TO_MARKER[pen], pen).toBeDefined();
    }
  });

  it('reads ai_red as REMOVED, which is the only thing the generator uses it for', () => {
    // `markerGenerator`: `if (marking.status === "REMOVED") penType = "ai_red"`. The canvas
    // called it MISMATCHED for as long as it had a label, so every removal carried the wrong
    // word on its detail card and answered to a filter nobody would think to use.
    expect(PEN_TYPE_TO_MARKER.ai_red).toBe('REMOVED');
  });

  it('gives a status exactly one colour, whoever drew it', () => {
    // The defect: MATCHED was #39ff14 from the engine and #10b981 by hand, ADDED #00ffff and
    // #3b82f6. Two tables, both right on their own terms, disagreeing about one word.
    expect(markerStyle('MATCHED').color).toBe(markerStyle(PEN_TYPE_TO_MARKER.ai_green).color);
    expect(markerStyle('ADDED').color).toBe(markerStyle(PEN_TYPE_TO_MARKER.checker_blue).color);
  });

  it('falls back visibly rather than silently for an unknown status', () => {
    expect(markerStyle('NONSENSE')).toBe(MARKER_STYLES.MISMATCHED);
  });

  it('draws a status on the same side the engineer may record it', () => {
    // `TOOL_SIDE` decides what can be RECORDED and `MARKER_SIDE` what is DRAWN. If they
    // disagree, a marking vanishes the instant it is made — which reads as a failed write, and
    // sends the engineer looking at the network tab for a bug that is in the renderer.
    const recordable: Record<string, 'ref' | 'rev' | 'both'> = TOOL_SIDE;
    const pairs: [string, MarkerType][] = [
      ['removed', 'REMOVED'],
      ['added', 'ADDED'],
      ['matched', 'MATCHED'],
      ['changed', 'CHANGED'],
      ['mismatched', 'MISMATCHED'],
    ];
    for (const [tool, type] of pairs) {
      const drawnOn = MARKER_SIDE[type] ?? 'both';
      expect(drawnOn, `${tool} / ${type}`).toBe(recordable[tool]);
    }
  });
});

describe('markingsToMarkers', () => {
  it('carries BOTH coordinates, so a pair draws on each sheet at its own point', () => {
    // The renderer picks `ref_coordinates` or `coordinates` by which sheet it is drawing. A
    // mapping that kept only one would put a pair's badge on one sheet, which is exactly the
    // "why is the checkmark only on one side" report this replaced.
    const [m] = markingsToMarkers([marking()]);
    expect(m.ref_coordinates).toEqual([100, 200]);
    expect(m.coordinates).toEqual([300, 400]);
  });

  it('does not draw a retracted marking', () => {
    // Retraction is not deletion — the row stays as the audit trail of who asserted what — but
    // the sheet must not show a judgement its author withdrew.
    expect(markingsToMarkers([marking({ retracted_at: '2026-08-18T00:00:00Z' })])).toEqual([]);
  });

  it('passes the status straight through as the marker type', () => {
    // Not via `pen_type`: that vocabulary has no REMOVED, so routing one through `ai_red` would
    // label a removal "MISMATCHED" on its own card and file it under the wrong filter.
    const [m] = markingsToMarkers([marking({ status: 'REMOVED' })]);
    expect(m.status).toBe('REMOVED');
    expect(MARKER_SIDE.REMOVED).toBe('ref');
  });

  it('namespaces the id so a marking cannot collide with a violation', () => {
    // `markerPositionsRef` is keyed by id and shared by both. A collision would put one
    // marker's click target on another's coordinates.
    expect(markingsToMarkers([marking()])[0].id).toBe('marking:m1');
  });

  it('flags a bulk marking so it can be ringed', () => {
    // One editorial act standing for forty entities must not read as a single stamp; the corpus
    // reports bulk counts separately and there is no other way to reconcile the two by eye.
    expect(markingsToMarkers([marking({ is_bulk: true })])[0].is_bulk).toBe(true);
    expect(markingsToMarkers([marking()])[0].is_bulk).toBe(false);
  });

  it('keeps each sheet text on its own side', () => {
    // The card shows the reference value on the reference and the revision value on the
    // revision. Swapping them is invisible until someone reads a card on the wrong sheet.
    const [m] = markingsToMarkers([marking()]);
    expect(m.original_value).toBe('4 ロール：12 (2x6台)');
    expect(m.description).toBe('４ロール：１２（２×６台）');
  });

  it('survives a row with nothing in it', () => {
    // Markings come off the wire; a field the server stopped sending must not throw inside a
    // render pass, where the failure takes the whole canvas rather than one badge.
    expect(() => markingsToMarkers([{ id: 'x' }, null as any])).not.toThrow();
  });
});

describe('markerUi — the panel half of the table', () => {
  it('gives every status a panel colour in both themes', () => {
    for (const type of Object.keys(MARKER_STYLES) as MarkerType[]) {
      expect(markerUi(type, false).color, type).toMatch(/^#[0-9a-f]{6}$/i);
      expect(markerUi(type, true).color, type).toMatch(/^#[0-9a-f]{6}$/i);
    }
  });

  it('is NOT the canvas colour', () => {
    // The distinction the fold exists to preserve. `#39ff14` is right over a dark CAD sheet and
    // unreadable on a white card — one status, one table, two contexts. Collapsing them would
    // fix the drift and break the contrast, which is the wrong trade.
    expect(markerUi('MATCHED', false).color).not.toBe(MARKER_STYLES.MATCHED.color);
    expect(markerUi('ADDED', false).color).not.toBe(MARKER_STYLES.ADDED.color);
  });

  it('darkens for the light theme', () => {
    // A light-theme card needs a darker ink than a dark-theme one, or the pill washes out.
    for (const type of ['MATCHED', 'CHANGED', 'ADDED', 'MISMATCHED'] as MarkerType[]) {
      expect(markerUi(type, true).color, type).not.toBe(markerUi(type, false).color);
    }
  });

  it('backs the colour with a wash of itself', () => {
    // Hex alpha, the idiom the section pill and the finding card already use — one less colour
    // format to keep in step, and it cannot drift from the foreground it sits behind.
    const { color, background } = markerUi('CHANGED', false);
    expect(background.startsWith(color)).toBe(true);
  });

  it('falls back visibly rather than silently for an unknown status', () => {
    // `MISSING` and other LLM spellings are mapped by the caller; anything that slips through
    // must be conspicuous rather than quietly green.
    expect(markerUi('NONSENSE', false).color).toBe(MARKER_STYLES.MISMATCHED.ui);
  });
});

describe('markerTypeOf — which vocabulary a marker is speaking', () => {
  it('prefers the engine verdict over the pen', () => {
    // `status` is the engine's own word and a manual marking's only vocabulary. `pen_type` is
    // the older rendering hint, kept for cached payloads written before `status` was passed
    // through — so it answers second, not first.
    expect(markerTypeOf({ status: 'CHANGED', pen_type: 'ai_red' })).toBe('CHANGED');
  });

  it('falls back to the pen when there is no status', () => {
    expect(markerTypeOf({ pen_type: 'checker_blue' })).toBe('ADDED');
    expect(markerTypeOf({ pen_type: 'ai_green' })).toBe('MATCHED');
  });

  it('folds MISSING onto REMOVED', () => {
    // The engine says MISSING where the taxonomy says REMOVED — `ChecklistPanel` has always
    // tested for both. Unmapped, it returns null and the marker is not drawn AT ALL: the finding
    // sits in the panel and appears nowhere on the sheet, which reads as a detection failure.
    expect(markerTypeOf({ status: 'MISSING' })).toBe('REMOVED');
  });

  it('is not case- or whitespace-sensitive', () => {
    expect(markerTypeOf({ status: '  changed ' })).toBe('CHANGED');
  });

  it('returns null for something it does not recognise', () => {
    // Loudly, not quietly. Defaulting an unknown to MISMATCHED would paint a red mark on
    // something nobody flagged, which is the one error a reviewer cannot detect by looking.
    expect(markerTypeOf({ status: 'WAT' })).toBeNull();
    expect(markerTypeOf({ pen_type: 'ai_puce' })).toBeNull();
    expect(markerTypeOf({})).toBeNull();
  });
});
