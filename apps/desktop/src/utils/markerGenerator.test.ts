import { describe, it, expect } from 'vitest';
import { generateComparisonMarkings } from './markerGenerator';

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
