import { describe, it, expect } from 'vitest';
import {
  computeCenterlineSegments,
  computeDashedSegments,
  computePhantomSegments,
  classifyLinetype,
} from './cadLinetypes';

describe('cadLinetypes', () => {
  describe('classifyLinetype', () => {
    it('recognizes centerlines', () => {
      expect(classifyLinetype('CENTER')).toBe('center');
      expect(classifyLinetype('CENTER2')).toBe('center');
      expect(classifyLinetype('CENTERX2')).toBe('center');
      expect(classifyLinetype('一点鎖線')).toBe('center');
    });

    it('recognizes phantom lines', () => {
      expect(classifyLinetype('PHANTOM')).toBe('phantom');
      expect(classifyLinetype('PHANTOM2')).toBe('phantom');
      expect(classifyLinetype('二点鎖線')).toBe('phantom');
    });

    it('recognizes hidden/dashed lines', () => {
      expect(classifyLinetype('HIDDEN')).toBe('hidden');
      expect(classifyLinetype('DASHED')).toBe('hidden');
      expect(classifyLinetype('破線')).toBe('hidden');
    });

    it('falls back to other for continuous', () => {
      expect(classifyLinetype('Continuous')).toBe('other');
      expect(classifyLinetype(null)).toBe('other');
    });
  });

  describe('computeCenterlineSegments', () => {
    it('renders a short centerline (8.57mm) as dash - dot - dash with centered dot', () => {
      const length = 8.57;
      const segs = computeCenterlineSegments(length, [7.35, 1.47, 1.47, 1.47]);
      
      expect(segs).toHaveLength(3);
      // Starts at 0
      expect(segs[0].start).toBe(0);
      // Ends at length
      expect(segs[2].end).toBeCloseTo(length, 2);

      // Symmetrical end dashes
      const end1Len = segs[0].end - segs[0].start;
      const end2Len = segs[2].end - segs[2].start;
      expect(end1Len).toBeCloseTo(end2Len, 2);

      // Center dot is centered at length / 2
      const dotMid = (segs[1].start + segs[1].end) / 2;
      expect(dotMid).toBeCloseTo(length / 2, 2);
    });

    it('renders a crosshair centerline (10.7mm) as dash - dot - dash with centered dot', () => {
      const length = 10.70;
      const segs = computeCenterlineSegments(length, [7.35, 1.47, 1.47, 1.47]);
      
      expect(segs).toHaveLength(3);
      expect(segs[0].start).toBe(0);
      expect(segs[2].end).toBeCloseTo(length, 2);

      const dotMid = (segs[1].start + segs[1].end) / 2;
      expect(dotMid).toBeCloseTo(length / 2, 2);
    });

    it('renders a long centerline with multiple dots and symmetric end dashes', () => {
      const length = 79.87;
      const segs = computeCenterlineSegments(length, [7.35, 1.47, 1.47, 1.47]);
      
      expect(segs.length).toBeGreaterThan(3);
      expect(segs[0].start).toBe(0);
      expect(segs[segs.length - 1].end).toBeCloseTo(length, 2);

      // Symmetrical first and last dashes
      const firstDash = segs[0].end - segs[0].start;
      const lastDash = segs[segs.length - 1].end - segs[segs.length - 1].start;
      expect(firstDash).toBeCloseTo(lastDash, 1);
    });

    it('dynamically increases the number of center dots when zooming in (iCAD SX behavior)', () => {
      const length = 8.57; // mm
      const zoomedOut = computeCenterlineSegments(length, null, 2.0); // 2 px/mm
      const zoomedIn = computeCenterlineSegments(length, null, 20.0); // 20 px/mm

      expect(zoomedOut).toHaveLength(3); // 1 dot
      expect(zoomedIn.length).toBeGreaterThan(3); // multiple dots ("becomes many")
    });
  });

  describe('computeDashedSegments', () => {
    it('renders a short hidden line as dash - gap - dash', () => {
      const length = 6.0;
      const segs = computeDashedSegments(length, [3.5, 1.5]);
      
      expect(segs).toHaveLength(2);
      expect(segs[0].start).toBe(0);
      expect(segs[1].end).toBeCloseTo(length, 2);

      const d1 = segs[0].end - segs[0].start;
      const d2 = segs[1].end - segs[1].start;
      expect(d1).toBeCloseTo(d2, 2);
    });
  });

  describe('computePhantomSegments', () => {
    it('renders a short phantom line with paired dots', () => {
      const length = 14.0;
      const segs = computePhantomSegments(length);
      
      expect(segs).toHaveLength(4); // dash, dot, dot, dash
      expect(segs[0].start).toBe(0);
      expect(segs[3].end).toBeCloseTo(length, 2);
    });
  });
});
