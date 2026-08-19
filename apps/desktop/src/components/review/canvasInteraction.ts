import { getNormalization, worldToScreen, screenToWorldUnflipped, parseBounds } from '../../utils/coordinateTransform';
import { MARKER_SIDE, markerTypeOf } from './markerStyles';

export interface HitTestParams {
  mx: number;
  my: number;
  violations: any[];
  drawing?: any;
  oldDrawing?: any;
  showViolations: boolean;
  viewport: { x: number; y: number; scale: number };
  markerPositions?: Record<string, { x: number, y: number }>;
  /** Manual markings, already in marker shape. Hit-tested whatever `showViolations` says. */
  markings?: any[];
}

export const hitTestMarker = ({
  mx,
  my,
  violations,
  drawing,
  oldDrawing,
  showViolations,
  viewport,
  markerPositions,
  markings = [],
}: HitTestParams): string | null => {
  const isOldDrawing = oldDrawing && drawing?.id === oldDrawing.id;
  const norm = getNormalization(parseBounds(drawing?.metadata?.render_bounds));

  const getPriority = (penType: string) => {
    if (penType === 'ai_red' || penType === 'checker_blue') return 3;
    if (penType === 'ai_orange') return 2;
    return 1;
  };

  const sortedViolations = [...violations].sort((a, b) => {
    return getPriority(b.pen_type || 'ai_red') - getPriority(a.pen_type || 'ai_red');
  });

  // Manual markings are hit-tested FIRST and are not gated by `showViolations`.
  //
  // That flag is about the engine's conclusions — a manual-check room forces it off so the
  // checker stays an independent observer — and it used to short-circuit this whole function, so
  // a recorded marking was drawn on the canvas and un-hoverable. The engine's detail card and
  // the marking's are the same card from the same renderer; only the hover that reveals it was
  // missing, which is why the two modes felt different.
  const candidates = [
    ...markings.map((m: any) => ({ marker: m, gated: false })),
    ...(showViolations ? sortedViolations.map((v: any) => ({ marker: v, gated: true })) : []),
  ];

  for (const { marker: v } of candidates) {
    // One side rule for drawing and for hit-testing. `MARKER_SIDE` also answers for REMOVED,
    // which the two hard-coded `pen_type` tests here never did.
    const type = markerTypeOf(v);
    const belongsOn = type ? MARKER_SIDE[type] : null;
    if (belongsOn === 'rev' && isOldDrawing) continue;
    if (belongsOn === 'ref' && !isOldDrawing) continue;

    const coords = isOldDrawing ? v.ref_coordinates : v.coordinates;
    if (!coords) continue;
    const [vx, raw_vy] = coords;

    // Read from cached positions first for write-then-read thread accuracy, fallback to worldToScreen
    const cached = markerPositions?.[v.id];
    const screenPos = cached ?? worldToScreen(vx, raw_vy, norm, viewport);

    if (Math.hypot(mx - screenPos.x, my - screenPos.y) <= 12) {
      return v.id;
    }
  }

  return null;
};

export interface RoiDragStartParams {
  mx: number;
  my: number;
  drawing: any;
  viewport: { x: number; y: number; scale: number };
}

export const getRoiDragPercentages = ({
  mx,
  my,
  drawing,
  viewport
}: RoiDragStartParams): { pctX: number; pctY: number } | null => {
  if (!drawing?.metadata?.render_bounds) return null;

  const norm = getNormalization(parseBounds(drawing.metadata.render_bounds));
  // Unflipped on purpose: ROI regions are percentages measured directly against
  // render_bounds, where Y is not inverted. See screenToWorldUnflipped's docstring.
  const { x: worldX, y: worldY } = screenToWorldUnflipped(mx, my, norm, viewport);

  const [rxMin, ryMin, rxMax, ryMax] = drawing.metadata.render_bounds;
  const w = rxMax - rxMin;
  const h = ryMax - ryMin;

  if (w <= 0 || h <= 0) return null;

  const pctX = (worldX - rxMin) / w;
  const pctY = (worldY - ryMin) / h;

  return { pctX, pctY };
};
