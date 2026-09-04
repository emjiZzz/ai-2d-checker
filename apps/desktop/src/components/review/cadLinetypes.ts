/**
 * CAD Linetype Adaptive Segmentation Engine
 *
 * Implements JIS B 0001 / ISO 128 compliant line decomposition for mechanical drawings,
 * featuring screen-space zoom-adaptive regeneration matching iCAD SX:
 *   - When zoomed out, short lines guarantee at least 1 centered dot (dash — gap — dot — gap — dash),
 *     never collapsing into an accidental solid line.
 *   - When zoomed in, the pattern dynamically regenerates so "the center line becomes many",
 *     keeping dash and gap sizes comfortable on the monitor.
 */

export interface DashSegment {
  start: number;
  end: number;
}

/**
 * Identify the category of linetype by its name.
 */
export type CadLinetypeCategory = 'center' | 'phantom' | 'hidden' | 'other';

export function classifyLinetype(name?: string | null): CadLinetypeCategory {
  const n = String(name || '').toUpperCase();
  if (n.includes('CENTER') || n.includes('CENTRE') || n.includes('1点鎖線') || n.includes('一点鎖線')) {
    return 'center';
  }
  if (n.includes('PHANTOM') || n.includes('2点鎖線') || n.includes('二点鎖線')) {
    return 'phantom';
  }
  if (n.includes('DASH') || n.includes('HIDDEN') || n.includes('破線')) {
    return 'hidden';
  }
  return 'other';
}

/**
 * Compute symmetrical dash/dot intervals for a CENTER line (一点鎖線).
 *
 * When viewScale is provided, adapts to the display zoom (iCAD SX behavior):
 * zooming in causes more dashes and dots to appear along the line.
 */
export function computeCenterlineSegments(
  length: number,
  nominalPattern?: number[] | null,
  viewScale?: number
): DashSegment[] {
  if (length <= 0) return [];
  if (length < 0.5) return [{ start: 0, end: length }];

  let nomLongDash = 7.35;
  let nomGap = 1.47;
  let nomDot = 1.47;

  if (viewScale && viewScale > 0) {
    // Zoom-adaptive: dashes stay ~22-26px on screen, gaps ~5-6px, dots ~3-4px
    nomLongDash = 24 / viewScale;
    nomGap = 6 / viewScale;
    nomDot = 4 / viewScale;
  } else if (Array.isArray(nominalPattern) && nominalPattern.length >= 4) {
    nomLongDash = Math.max(2.0, nominalPattern[0]);
    nomGap = Math.max(0.5, nominalPattern[1]);
    nomDot = Math.max(0.5, nominalPattern[2]);
  }

  const cycle = nomLongDash + 2 * nomGap + nomDot;

  // Short to medium segment: guarantee 1 centered dot symmetrically
  if (length < 1.6 * cycle) {
    const gap = Math.min(nomGap, Math.max(0.6 / (viewScale || 1), length * 0.12));
    const dot = Math.min(nomDot, Math.max(0.6 / (viewScale || 1), length * 0.12));
    const remaining = length - (2 * gap + dot);

    if (remaining > 0.2) {
      const endDash = remaining / 2;
      return [
        { start: 0, end: endDash },
        { start: endDash + gap, end: endDash + gap + dot },
        { start: length - endDash, end: length },
      ];
    } else {
      const unit = length / 7;
      return [
        { start: 0, end: unit * 2 },
        { start: unit * 3, end: unit * 4 },
        { start: unit * 5, end: length },
      ];
    }
  }

  // Longer lines or zoomed-in lines: fit k intermediate dots symmetrically
  const gapDotGap = 2 * nomGap + nomDot;
  let k = Math.max(1, Math.floor((length - nomLongDash) / cycle));
  let totalFixed = k * gapDotGap;
  let dashTotal = length - totalFixed;

  if (dashTotal / (k + 1) < nomLongDash * 0.35 && k > 1) {
    k -= 1;
    totalFixed = k * gapDotGap;
    dashTotal = length - totalFixed;
  }

  const numDashes = k + 1;
  if (k === 1) {
    const endDash = dashTotal / 2;
    return [
      { start: 0, end: endDash },
      { start: endDash + nomGap, end: endDash + nomGap + nomDot },
      { start: length - endDash, end: length },
    ];
  }

  const midDash = Math.min(nomLongDash, dashTotal / numDashes);
  const endDash = (dashTotal - (k - 1) * midDash) / 2;

  const segments: DashSegment[] = [];
  let pos = 0;

  segments.push({ start: pos, end: pos + endDash });
  pos += endDash;

  for (let i = 0; i < k; i++) {
    pos += nomGap;
    segments.push({ start: pos, end: pos + nomDot });
    pos += nomDot;
    pos += nomGap;

    const d = (i === k - 1) ? endDash : midDash;
    segments.push({ start: pos, end: Math.min(length, pos + d) });
    pos += d;
  }

  return segments;
}

/**
 * Compute symmetrical dash intervals for a HIDDEN / DASHED line (破線).
 */
export function computeDashedSegments(
  length: number,
  nominalPattern?: number[] | null,
  viewScale?: number
): DashSegment[] {
  if (length <= 0) return [];
  if (length < 0.5) return [{ start: 0, end: length }];

  let nomDash = 3.5;
  let nomGap = 1.5;

  if (viewScale && viewScale > 0) {
    nomDash = 18 / viewScale;
    nomGap = 8 / viewScale;
  } else if (Array.isArray(nominalPattern) && nominalPattern.length >= 2) {
    nomDash = Math.max(1.0, nominalPattern[0]);
    nomGap = Math.max(0.5, nominalPattern[1]);
  }

  const cycle = nomDash + nomGap;

  if (length < 2 * cycle) {
    const gap = Math.min(nomGap, Math.max(0.5 / (viewScale || 1), length * 0.25));
    const endDash = (length - gap) / 2;
    if (endDash > 0.2) {
      return [
        { start: 0, end: endDash },
        { start: length - endDash, end: length },
      ];
    }
    return [{ start: 0, end: length }];
  }

  let k = Math.max(1, Math.round((length - nomDash) / cycle));
  let dashTotal = length - k * nomGap;
  if (dashTotal / (k + 1) < nomDash * 0.4 && k > 1) {
    k -= 1;
    dashTotal = length - k * nomGap;
  }

  const dashLen = dashTotal / (k + 1);
  const segments: DashSegment[] = [];
  let pos = 0;

  for (let i = 0; i < k; i++) {
    segments.push({ start: pos, end: pos + dashLen });
    pos += dashLen + nomGap;
  }
  segments.push({ start: pos, end: length });

  return segments;
}

/**
 * Compute symmetrical dash intervals for a PHANTOM line (二点鎖線).
 */
export function computePhantomSegments(
  length: number,
  nominalPattern?: number[] | null,
  viewScale?: number
): DashSegment[] {
  if (length <= 0) return [];
  if (length < 0.5) return [{ start: 0, end: length }];

  let nomLongDash = 7.0;
  let nomGap = 1.2;
  let nomDot = 1.0;

  if (viewScale && viewScale > 0) {
    nomLongDash = 24 / viewScale;
    nomGap = 5 / viewScale;
    nomDot = 3 / viewScale;
  } else if (Array.isArray(nominalPattern) && nominalPattern.length >= 6) {
    nomLongDash = Math.max(2.0, nominalPattern[0]);
    nomGap = Math.max(0.5, nominalPattern[1]);
    nomDot = Math.max(0.5, nominalPattern[2]);
  }

  const blockGapDots = 3 * nomGap + 2 * nomDot;
  const cycle = nomLongDash + blockGapDots;

  if (length < 1.8 * cycle) {
    const gap = Math.min(nomGap, Math.max(0.4 / (viewScale || 1), length * 0.08));
    const dot = Math.min(nomDot, Math.max(0.4 / (viewScale || 1), length * 0.08));
    const fixed = 3 * gap + 2 * dot;
    const remaining = length - fixed;

    if (remaining > 0.4) {
      const endDash = remaining / 2;
      return [
        { start: 0, end: endDash },
        { start: endDash + gap, end: endDash + gap + dot },
        { start: endDash + 2 * gap + dot, end: endDash + 2 * gap + 2 * dot },
        { start: length - endDash, end: length },
      ];
    }
  }

  return computeCenterlineSegments(length, [nomLongDash, nomGap, nomDot, nomGap], viewScale);
}

/**
 * General router to compute segments for any linetype.
 */
export function computeLinetypeSegments(
  length: number,
  linetypeName?: string | null,
  nominalPattern?: number[] | null,
  viewScale?: number
): DashSegment[] {
  const cat = classifyLinetype(linetypeName);
  switch (cat) {
    case 'center':
      return computeCenterlineSegments(length, nominalPattern, viewScale);
    case 'phantom':
      return computePhantomSegments(length, nominalPattern, viewScale);
    case 'hidden':
      return computeDashedSegments(length, nominalPattern, viewScale);
    default: {
      if (Array.isArray(nominalPattern) && nominalPattern.length >= 4) {
        return computeCenterlineSegments(length, nominalPattern, viewScale);
      }
      if (Array.isArray(nominalPattern) && nominalPattern.length >= 2) {
        return computeDashedSegments(length, nominalPattern, viewScale);
      }
      return [{ start: 0, end: length }];
    }
  }
}

/**
 * Append adaptive dashed segments for a straight line directly into a Path2D.
 */
export function appendDashedLine(
  p2d: Path2D,
  x1: number,
  y1: number,
  x2: number,
  y2: number,
  linetypeName?: string | null,
  nominalPattern?: number[] | null,
  viewScale?: number
): void {
  const dx = x2 - x1;
  const dy = y2 - y1;
  const len = Math.hypot(dx, dy);
  if (len <= 1e-6) return;

  const ux = dx / len;
  const uy = dy / len;

  const segments = computeLinetypeSegments(len, linetypeName, nominalPattern, viewScale);

  for (let i = 0; i < segments.length; i++) {
    const s = segments[i];
    const sx = x1 + s.start * ux;
    const sy = y1 + s.start * uy;
    const ex = x1 + s.end * ux;
    const ey = y1 + s.end * uy;
    p2d.moveTo(sx, sy);
    p2d.lineTo(ex, ey);
  }
}

/**
 * Append adaptive dashed segments for an arc directly into a Path2D.
 */
export function appendDashedArc(
  p2d: Path2D,
  cx: number,
  cy: number,
  r: number,
  startAngle: number,
  endAngle: number,
  counterClockwise: boolean,
  linetypeName?: string | null,
  nominalPattern?: number[] | null,
  viewScale?: number
): void {
  if (r <= 1e-6) return;

  let sweep = counterClockwise
    ? startAngle - endAngle
    : endAngle - startAngle;

  while (sweep < 0) sweep += 2 * Math.PI;
  while (sweep > 2 * Math.PI) sweep -= 2 * Math.PI;

  const arcLen = r * sweep;
  if (arcLen <= 1e-6) return;

  const segments = computeLinetypeSegments(arcLen, linetypeName, nominalPattern, viewScale);
  const dir = counterClockwise ? -1 : 1;

  for (let i = 0; i < segments.length; i++) {
    const s = segments[i];
    const a1 = startAngle + dir * (s.start / arcLen) * sweep;
    const a2 = startAngle + dir * (s.end / arcLen) * sweep;
    p2d.moveTo(cx + r * Math.cos(a1), cy + r * Math.sin(a1));
    p2d.arc(cx, cy, r, a1, a2, counterClockwise);
  }
}
