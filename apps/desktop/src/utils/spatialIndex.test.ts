import { describe, expect, test } from 'vitest';
import { QuadTree } from './spatialIndex';

describe('QuadTree Spatial Index', () => {
  test('inserts items and queries range correctly', () => {
    const quad = new QuadTree({ xmin: 0, ymin: 0, xmax: 1000, ymax: 1000 });
    
    quad.insert({ bounds: { xmin: 10, ymin: 10, xmax: 20, ymax: 20 }, data: 'item1' });
    quad.insert({ bounds: { xmin: 500, ymin: 500, xmax: 520, ymax: 520 }, data: 'item2' });
    quad.insert({ bounds: { xmin: 900, ymin: 900, xmax: 950, ymax: 950 }, data: 'item3' });

    const viewArea1 = quad.queryRange({ xmin: 0, ymin: 0, xmax: 100, ymax: 100 });
    expect(viewArea1).toEqual(['item1']);

    const viewArea2 = quad.queryRange({ xmin: 400, ymin: 400, xmax: 600, ymax: 600 });
    expect(viewArea2).toEqual(['item2']);

    const allArea = quad.queryRange({ xmin: 0, ymin: 0, xmax: 1000, ymax: 1000 });
    expect(allArea).toHaveLength(3);
  });

  test('handles subdivision under capacity overload', () => {
    const quad = new QuadTree({ xmin: 0, ymin: 0, xmax: 100, ymax: 100 }, 4, 4);

    for (let i = 0; i < 20; i++) {
      quad.insert({
        bounds: { xmin: i * 2, ymin: i * 2, xmax: i * 2 + 1, ymax: i * 2 + 1 },
        data: `item_${i}`
      });
    }

    const result = quad.queryRange({ xmin: 0, ymin: 0, xmax: 10, ymax: 10 });
    expect(result.length).toBeGreaterThan(0);
    expect(result.length).toBeLessThan(20);
  });
});
