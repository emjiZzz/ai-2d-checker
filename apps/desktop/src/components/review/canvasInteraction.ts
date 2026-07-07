import { getNormalization, worldToScreen, parseBounds } from '../../utils/coordinateTransform';

export interface HitTestParams {
  mx: number;
  my: number;
  violations: any[];
  drawing?: any;
  oldDrawing?: any;
  showViolations: boolean;
  viewport: { x: number; y: number; scale: number };
  markerPositions?: Record<string, { x: number, y: number }>;
}

export const hitTestMarker = ({
  mx,
  my,
  violations,
  drawing,
  oldDrawing,
  showViolations,
  viewport,
  markerPositions
}: HitTestParams): string | null => {
  if (!showViolations) return null;

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

  for (const v of sortedViolations) {
    if (isOldDrawing && v.pen_type === 'checker_blue') continue;
    if (!isOldDrawing && v.pen_type === 'ai_red') continue;

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
  const effectiveScale = viewport.scale * norm.normScale;
  const worldX = norm.xmin + (mx - viewport.x) / effectiveScale;
  const worldY = norm.ymin + (my - viewport.y) / effectiveScale;

  const [rxMin, ryMin, rxMax, ryMax] = drawing.metadata.render_bounds;
  const w = rxMax - rxMin;
  const h = ryMax - ryMin;

  if (w <= 0 || h <= 0) return null;

  const pctX = (worldX - rxMin) / w;
  const pctY = (worldY - ryMin) / h;

  return { pctX, pctY };
};
