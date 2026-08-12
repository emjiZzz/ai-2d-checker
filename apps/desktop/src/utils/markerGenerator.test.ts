import { describe, it, expect } from 'vitest';
import { generateComparisonMarkings, markerAnchor } from './markerGenerator';

describe('markerAnchor', () => {
  // Mirrors tests/test_extraction_logic.py::test_marker_anchor_is_the_centre_of_the_text.
  // renderEntities.ts draws the glyph with textAlign='center'/textBaseline='middle' at this
  // coordinate, so it must be the text's centre — the old formula put it a character-width
  // past the right edge, carrying the tick clear of long values.
  it('returns the centre of the bbox when one is present', () => {
    expect(markerAnchor({ bbox: [[10, 20], [30, 40]] })).toEqual([20, 30]);
  });

  it('estimates the centre from the insert point when there is no bbox', () => {
    expect(markerAnchor({ x: 10, y: 20, height: 6, text: 'ABCD' })).toEqual([17.2, 23]);
  });

  it('falls back to the insert estimate when the bbox is malformed', () => {
    expect(markerAnchor({ bbox: [[NaN, 20], [30, 40]], x: 10, y: 20, height: 6, text: 'ABCD' }))
      .toEqual([17.2, 23]);
  });

  it('returns undefined when there is nothing to anchor to', () => {
    expect(markerAnchor({})).toBeUndefined();
  });
});

describe('markerGenerator tests', () => {
  it('assigns correct pen types and statuses based on values', () => {
    const rawMarkings = [
      {
        text_content: '100',
        details: 'no change',
        coordinates: [500, 500] as [number, number],
        ref_coordinates: [500, 500] as [number, number],
        status: 'MATCHED'
      },
      {
        text_content: '120',
        original_value: '100',
        details: 'changed value',
        coordinates: [600, 500] as [number, number],
        ref_coordinates: [600, 500] as [number, number],
        status: 'CHANGED'
      }
    ];

    const bounds = { xMin: 0, xMax: 1000, yMin: 0, yMax: 1000 };

    const regionsMock = {
      views: { xMin: 0.04, xMax: 0.68, yMin: 0.12, yMax: 0.88 },
      notes: { xMin: 0.04, xMax: 0.38, yMin: 0.18, yMax: 0.62 },
      bom: { xMin: 0.62, xMax: 0.98, yMin: 0.04, yMax: 0.44 },
      title: { xMin: 0.38, xMax: 0.98, yMin: 0.72, yMax: 0.98 },
      titleUpperLeft: { xMin: 0.02, xMax: 0.35, yMin: 0.02, yMax: 0.35 },
      iso: { xMin: 0.62, xMax: 0.98, yMin: 0.42, yMax: 0.74 }
    };

    const result = generateComparisonMarkings({
      rawMarkings,
      textEntities: [],
      refTextEntities: [],
      drawing: {
        id: 'rev',
        metadata: {
          render_bounds: [0, 0, 1000, 1000],
          regions: regionsMock
        }
      },
      oldDrawing: {
        id: 'base',
        metadata: {
          render_bounds: [0, 0, 1000, 1000],
          regions: regionsMock
        }
      },
      bounds,
      refBounds: bounds
    });

    expect(result).toHaveLength(2);
    expect(result[0].pen_type).toBe('resolved_green');
    expect(result[0].is_resolved).toBe(true);
    expect(result[1].pen_type).toBe('ai_orange');
    expect(result[1].is_resolved).toBe(false);
  });

  it('does NOT re-ground a title_block value to a same-valued tolerance cell (uses backend coords)', () => {
    // Regression: a title field value like "4" must anchor at its backend coordinate, not be
    // text-matched to a "4" elsewhere on the sheet (e.g. a tolerance-grid cell). See the
    // tolerance-table false-marker fix.
    const rawMarkings = [
      {
        text_content: '4',
        details: 'checked',
        status: 'MATCHED',
        category: 'title_block',
        coordinates: [750, 250] as [number, number],      // rev title-block cell (authoritative)
        ref_coordinates: [186, 685] as [number, number],  // ref upper-left table cell
      },
    ];
    const bounds = { xMin: 0, xMax: 1000, yMin: 0, yMax: 1000 };
    // Decoy "4" entities sitting in the (bottom-left) tolerance grid on both drawings.
    const revTolCell = [{ text: '4', x: 75, y: 30, height: 3 }] as any;
    const refTolCell = [{ text: '4', x: 372, y: 77, height: 3 }] as any;

    const result = generateComparisonMarkings({
      rawMarkings,
      textEntities: revTolCell,
      refTextEntities: refTolCell,
      drawing: { id: 'rev', metadata: { render_bounds: [0, 0, 1000, 1000] } },
      oldDrawing: { id: 'base', metadata: { render_bounds: [0, 0, 1000, 1000] } },
      bounds,
      refBounds: bounds,
    });

    expect(result).toHaveLength(1);
    // Must use the backend coordinates, NOT the tolerance-cell decoys.
    expect(result[0].coordinates).toEqual([750, 250]);
    expect(result[0].ref_coordinates).toEqual([186, 685]);
  });

  it('does NOT scatter an UNRESOLVED bom value across every same-valued cell on the sheet', () => {
    // Regression, reported from a live review on M745227N01 and the failure path the test
    // above never exercised: the guard it pins used to require `hasBackendCoord`, so it
    // **failed open in exactly the case it was written for**. The backend could not place
    // this BOM row (`Q'ty: 1 vs 1` arrives with `coordinates: null`,
    // `resolution_method: "unresolved"`), the guard therefore did not apply, and the
    // marking was text-matched against every entity reading "1" — one marker per match —
    // painting MATCHED checkmarks down the 一組分個数 column of the シム表, a SAFE zone that
    // is never compared.
    //
    // With no coordinate from the backend, a structured value gets NO marker. The value is
    // still reported in the BOM table; what is dropped is an unsupportable claim about where.
    const rawMarkings = [
      {
        text_content: '1',
        details: "BOM [Item 1]  / Q'ty checked: 1 vs 1",
        status: 'MATCHED',
        category: 'bill_of_materials',
        coordinates: null,
        ref_coordinates: null,
      },
    ];
    const bounds = { xMin: 0, xMax: 1000, yMin: 0, yMax: 1000 };
    // The quantity column of the shim table: three cells all reading "1".
    const shimQtyCells = [
      { text: '1', x: 800, y: 500, height: 3 },
      { text: '1', x: 800, y: 460, height: 3 },
      { text: '1', x: 800, y: 420, height: 3 },
    ] as any;

    const result = generateComparisonMarkings({
      rawMarkings,
      textEntities: shimQtyCells,
      refTextEntities: shimQtyCells,
      drawing: { id: 'rev', metadata: { render_bounds: [0, 0, 1000, 1000] } },
      oldDrawing: { id: 'base', metadata: { render_bounds: [0, 0, 1000, 1000] } },
      bounds,
      refBounds: bounds,
    });

    const placed = result.filter(
      (r: any) => Array.isArray(r.coordinates) || Array.isArray(r.ref_coordinates)
    );
    expect(placed).toHaveLength(0);
    expect(result.length).toBeLessThanOrEqual(1);
  });

  it('passes `feature` through untouched, and leaves it undefined when the backend omits it', () => {
    const rawMarkings = [
      {
        text_content: '45',
        details: 'checked',
        coordinates: [500, 500] as [number, number],
        ref_coordinates: [500, 500] as [number, number],
        status: 'MATCHED',
        category: 'title_block',
        feature: 'scale'
      },
      {
        text_content: '2',
        details: 'checked',
        coordinates: [600, 500] as [number, number],
        ref_coordinates: [600, 500] as [number, number],
        status: 'MATCHED',
        category: 'bill_of_materials'
        // no `feature` — simulates a pre-Phase-5 cached payload
      }
    ];

    const bounds = { xMin: 0, xMax: 1000, yMin: 0, yMax: 1000 };

    const result = generateComparisonMarkings({
      rawMarkings,
      textEntities: [],
      refTextEntities: [],
      drawing: { id: 'rev', metadata: { render_bounds: [0, 0, 1000, 1000] } },
      oldDrawing: { id: 'base', metadata: { render_bounds: [0, 0, 1000, 1000] } },
      bounds,
      refBounds: bounds
    });

    expect(result).toHaveLength(2);
    expect(result[0].feature).toBe('scale');
    expect(result[1].feature).toBeUndefined();
  });
});
