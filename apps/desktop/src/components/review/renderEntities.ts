import { getNormalization, worldToScreen } from '../../utils/coordinateTransform';

// Helper utility to strip any residual AutoCAD MTEXT formatting/styling tags
export const cleanCadText = (text: string): string => {
  if (!text) return "";
  let clean = text;
  clean = clean.replace(/ラ/g, "x");
  clean = clean.replace(/[{}]/g, "");
  clean = clean.replace(/\\[A-Za-z][^;]*;/g, "");
  clean = clean.replace(/\\P/g, " ");
  return clean.trim();
};

export const getPrintColor = (color: string): string => {
  if (!color) return '#18181b';
  const cleanColor = color.trim().toLowerCase();

  if (cleanColor.startsWith('#')) {
    let hex = cleanColor;
    if (hex.length === 4) {
      hex = '#' + hex[1] + hex[1] + hex[2] + hex[2] + hex[3] + hex[3];
    }

    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);

    if (r > 220 && g > 220 && b > 220) {
      return '#18181b';
    }

    const brightness = (r * 299 + g * 587 + b * 114) / 1000;
    if (brightness > 150) {
      if (r > 200 && g > 200 && b < 100) {
        return '#b45309';
      }
      if (r < 100 && g > 180 && b > 180) {
        return '#0369a1';
      }
      if (g > 180 && r < 120 && b < 120) {
        return '#15803d';
      }
      const dr = Math.round(r * 0.45);
      const dg = Math.round(g * 0.45);
      const db = Math.round(b * 0.45);
      const toHex = (c: number) => c.toString(16).padStart(2, '0');
      return `#${toHex(dr)}${toHex(dg)}${toHex(db)}`;
    }
    return hex;
  }

  const nameMap: Record<string, string> = {
    'white': '#18181b',
    'yellow': '#b45309',
    'cyan': '#0369a1',
    'green': '#15803d',
    'lime': '#166534',
    'magenta': '#701a75',
    'pink': '#be185d',
    'lightgray': '#52525b',
    'gray': '#71717a'
  };

  return nameMap[cleanColor] || color;
};

export interface RenderFrame {
  ctx: CanvasRenderingContext2D;
  isExport: boolean;
  renderWidth: number;
  renderHeight: number;
  width: number;
  height: number;
  norm: ReturnType<typeof getNormalization>;
  scale: number;
  transX: number;
  transY: number;
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
  currentViewportScale: number;
  resolutionMultiplier: number;
  viewport: { x: number; y: number; scale: number };
  markerPositionsRef: React.MutableRefObject<Record<string, { x: number, y: number }>>;
  isNeonModeActive?: boolean;
}

export interface RenderEntitiesParams {
  frame: RenderFrame;
  layers: Record<string, any[]>;
  activeLayers: Record<string, boolean>;
  theme: string;
  bgImage: HTMLImageElement | null;
  lightBgImage: HTMLImageElement | null;
  drawing?: any;
}

export const renderEntities = ({
  frame,
  layers,
  activeLayers,
  theme,
  bgImage,
  lightBgImage,
  drawing
}: RenderEntitiesParams): { totalEntities: number; drawnEntities: number } => {
  const { ctx, isExport, renderWidth, renderHeight, scale, transX, transY, minX, minY, maxX, maxY, resolutionMultiplier } = frame;

  let totalEntities = 0;
  let drawnEntities = 0;

  // Draw high-fidelity raster CAD background image if loaded, aligned exactly to CAD coordinates bounds.
  // lightBgImage is computed asynchronously (see DrawingCanvas.tsx) and can briefly be null right
  // after a theme switch or on first load — fall back to the raw dark-tuned bgImage rather than
  // drawing nothing, so the canvas isn't blank while the light variant finishes processing.
  const targetImage = (isExport || theme === 'hc-light') ? (lightBgImage || bgImage) : bgImage;
  if (targetImage && drawing?.metadata?.render_bounds) {
    const [xmin, ymin, xmax, ymax] = drawing.metadata.render_bounds;
    ctx.drawImage(targetImage, xmin, ymin, xmax - xmin, ymax - ymin);
  }

  const pathBatches: Record<string, { stroke: string, width: number, path: Path2D }> = {};

  // If a high-fidelity raster image is loaded, skip ALL vector entity rendering.
  // The loop below is O(entities) and would be wasted work — the image covers everything.
  // Must check targetImage (what was actually drawn above), not bgImage — bgImage is always
  // truthy once fetched even when targetImage was null and nothing was painted.
  const skipEntities = !!(targetImage && drawing?.metadata?.render_bounds);

  Object.entries(layers).forEach(([layerName, entities]) => {
    if (activeLayers[layerName] === false) return;

    entities.forEach((ent) => {
      totalEntities++;

      if (skipEntities) {
        return;
      }

      const geo = ent.geometry;
      if (!geo) return;

      let strokeColor = ent.style?.stroke || ent.properties?.stroke || '#00e5ff';
      if (isExport || theme === 'hc-light') {
        strokeColor = getPrintColor(strokeColor);
      }
      const strokeWidth = ent.style?.strokeWidth || ent.properties?.strokeWidth || 1;
      const batchKey = `${strokeColor}_${strokeWidth}`;

      if (ent.type === 'text' && (geo.location || geo.insert)) {
        const [tx, ty] = geo.location || geo.insert;

        const screenX = tx * scale + transX;
        const screenY = ty * scale + transY;
        const baseHeight = ent.properties?.height || ent.style?.fontSize || 12;
        const screenHeight = baseHeight * scale * 1.0;

        if (screenHeight < (isExport ? 1 : 4)) return;
        if (!isExport && (screenX < -500 || screenX > renderWidth + 500 || screenY < -500 || screenY > renderHeight + 500)) return;

        drawnEntities++;

        ctx.save();
        const localDpr = typeof window !== 'undefined' ? window.devicePixelRatio || 1 : 1;
        ctx.setTransform(localDpr, 0, 0, localDpr, 0, 0);

        let textColor = ent.style?.stroke || ent.style?.fill || '#ffffff';
        if (isExport || theme === 'hc-light') {
          textColor = getPrintColor(textColor);
        }
        ctx.fillStyle = textColor;
        ctx.font = `${screenHeight}px "Yu Gothic", "MS Gothic", "Meiryo", "Noto Sans CJK JP", "Noto Sans JP", sans-serif`;

        const rawText = geo.text || geo.content || ent.properties?.text || '';
        const textVal = cleanCadText(rawText);

        if (textVal) {
          ctx.fillText(textVal, screenX, screenY);
        }
        ctx.restore();
        return;
      }

      if (!pathBatches[batchKey]) {
        pathBatches[batchKey] = { stroke: strokeColor, width: strokeWidth as number, path: new Path2D() };
      }
      const p2d = pathBatches[batchKey].path;

      if (ent.type === 'line' && geo.start && geo.end) {
        const [x1, y1] = geo.start;
        const [x2, y2] = geo.end;
        const left = Math.min(x1, x2);
        const right = Math.max(x1, x2);
        const top = Math.min(y1, y2);
        const bottom = Math.max(y1, y2);
        if (right < minX || left > maxX || bottom < minY || top > maxY) return;
        drawnEntities++;
        p2d.moveTo(x1, y1);
        p2d.lineTo(x2, y2);
      }
      else if (ent.type === 'circle' && (geo.center || geo.location)) {
        const [cx, cy] = geo.center || geo.location;
        const r = geo.radius || ent.properties?.radius || 1;
        if (cx + r < minX || cx - r > maxX || cy + r < minY || cy - r > maxY) return;
        drawnEntities++;
        p2d.moveTo(cx + r, cy);
        p2d.arc(cx, cy, r, 0, 2 * Math.PI);
      }
      else if (ent.type === 'arc' && (geo.center || geo.location)) {
        const [cx, cy] = geo.center || geo.location;
        const r = geo.radius || ent.properties?.radius || 1;
        const startAngle = ((ent.properties?.start_angle ?? 0) * Math.PI) / 180;
        const endAngle = ((ent.properties?.end_angle ?? 0) * Math.PI) / 180;
        if (cx + r < minX || cx - r > maxX || cy + r < minY || cy - r > maxY) return;
        drawnEntities++;
        p2d.moveTo(cx + r * Math.cos(startAngle), cy + r * Math.sin(startAngle));
        p2d.arc(cx, cy, r, startAngle, endAngle, false);
      }
      else if (ent.type === 'polyline' && (geo.vertices || geo.points)) {
        const vertices = geo.vertices || geo.points;
        if (vertices.length < 2) return;
        let pMinX = Infinity, pMaxX = -Infinity, pMinY = Infinity, pMaxY = -Infinity;
        vertices.forEach(([vx, vy]: [number, number]) => {
          if (vx < pMinX) pMinX = vx;
          if (vx > pMaxX) pMaxX = vx;
          if (vy < pMinY) pMinY = vy;
          if (vy > pMaxY) pMaxY = vy;
        });
        if (pMaxX < minX || pMinX > maxX || pMaxY < minY || pMinY > maxY) return;
        drawnEntities++;
        p2d.moveTo(vertices[0][0], vertices[0][1]);
        for (let i = 1; i < vertices.length; i++) {
          p2d.lineTo(vertices[i][0], vertices[i][1]);
        }
      }
    });
  });

  Object.values(pathBatches).forEach(batch => {
    ctx.beginPath();
    ctx.strokeStyle = batch.stroke;
    
    // Use the true absolute context scale (`scale` from frame) to ensure constant screen-space thickness.
    // Enforce a minimum of 1.5px on screen for better visibility, 1.0px for exports.
    const baseThickness = isExport ? 1.0 : 1.5;
    const effectiveWidth = Math.max(baseThickness, batch.width);
    ctx.lineWidth = (effectiveWidth / scale) * resolutionMultiplier;
    
    ctx.stroke(batch.path);
  });

  return { totalEntities, drawnEntities };
};

export interface RenderViolationReticlesParams {
  frame: RenderFrame;
  violations: any[];
  showViolations: boolean;
  showMarkerLabels: boolean;
  hoveredMarkerId: string | null;
  selectedViolation: any | null;
  drawing?: any;
  oldDrawing?: any;
  visibleMarkerTypes: Record<string, boolean>;
}

export const renderViolationReticles = ({
  frame,
  violations,
  showViolations,
  showMarkerLabels,
  hoveredMarkerId,
  selectedViolation,
  drawing,
  oldDrawing,
  visibleMarkerTypes
}: RenderViolationReticlesParams) => {
  const { ctx, isExport, renderWidth, viewport, norm, resolutionMultiplier, markerPositionsRef } = frame;

  // Critical constraint: explicit filter reset to clear any Neon-CAD filter applied earlier in the pass
  if (frame.isNeonModeActive && !isExport) {
    ctx.filter = 'none';
  }

  if (!showViolations) return;

  // Marker cards are drawn on the canvas (not DOM), so they don't pick up the app's
  // CSS theme variables automatically — check the live theme attribute once per pass.
  const isLightTheme = typeof document !== 'undefined' && document.documentElement.getAttribute('data-theme') === 'hc-light';
  const cardBg = isLightTheme ? 'rgba(229, 233, 240, 0.95)' : 'rgba(38, 43, 54, 0.95)';
  const cardPrimaryText = isLightTheme ? '#18181b' : '#ffffff';
  const cardSecondaryText = isLightTheme ? 'rgba(24, 24, 27, 0.7)' : 'rgba(255, 255, 255, 0.7)';
  const cardBulletRing = isLightTheme ? '#e5e9f0' : '#262b36';

  const isOldDrawing = oldDrawing && drawing?.id === oldDrawing.id;
  const placedCardRects: { xMin: number; xMax: number; yMin: number; yMax: number }[] = [];

  const getPriority = (penType: string) => {
    if (penType === 'ai_red' || penType === 'checker_blue') return 3;
    if (penType === 'ai_orange') return 2;
    return 1;
  };

  const sortedViolationsWithIndex = violations.map((v: any, i: number) => ({ v, i })).sort((a, b) => {
    return getPriority(a.v.pen_type || 'ai_red') - getPriority(b.v.pen_type || 'ai_red');
  });

  sortedViolationsWithIndex.forEach(({ v, i: idx }) => {
    const penType = v.pen_type || 'ai_red';
    if (penType !== 'ai_red' && penType !== 'ai_orange' && penType !== 'checker_blue' && penType !== 'ai_green' && penType !== 'resolved_green' && penType !== 'ai_conflict') return;

    if (isOldDrawing && penType === 'checker_blue') return;
    if (!isOldDrawing && penType === 'ai_red') return;

    let markerType = 'MISMATCHED';
    if (penType === 'ai_orange') markerType = 'CHANGED';
    else if (penType === 'checker_blue') markerType = 'ADDED';
    else if (penType === 'ai_green' || penType === 'resolved_green') markerType = 'MATCHED';
    else if (penType === 'ai_conflict') markerType = 'CONFLICT';

    if (!visibleMarkerTypes[markerType]) return;

    // Level-of-Detail (LOD): Skip entirely if zoomed way out, unless it's the actively selected violation
    if (viewport.scale < 0.1 && selectedViolation?.id !== v.id) return;

    let coords = isOldDrawing ? v.ref_coordinates : v.coordinates;
    if (!coords) return;

    const [vx, raw_vy] = coords;
    const screenPos = worldToScreen(vx, raw_vy, norm, viewport);
    const isSelected = selectedViolation?.id === v.id;

    const bulletColor = penType === 'ai_red' ? '#ff2850' : penType === 'ai_orange' ? '#ff9600' : penType === 'checker_blue' ? '#00ffff' : penType === 'ai_conflict' ? '#c084fc' : '#39ff14';
    const statusLabel = penType === 'ai_red' ? 'MISMATCHED' : penType === 'ai_orange' ? 'CHANGED' : penType === 'checker_blue' ? 'ADDED' : penType === 'ai_conflict' ? 'CONFLICT' : 'MATCHED';

    let screenX = screenPos.x;
    let screenY = screenPos.y;

    // Threading marker positions ref directly for handleMouseMove click targets
    markerPositionsRef.current[v.id] = { x: screenX, y: screenY };

    ctx.save();
    const localDpr = isExport ? 1 : (typeof window !== 'undefined' ? window.devicePixelRatio || 1 : 1);
    ctx.setTransform(localDpr, 0, 0, localDpr, 0, 0);

    const isHoveredOrSelected = hoveredMarkerId === v.id || isSelected;
    // Level-of-Detail (LOD): Hide detailed text cards when zoomed out, unless explicitly hovered/selected
    const lodSkipCard = viewport.scale < 0.3 && !isHoveredOrSelected;
    
    const SHOW_MARKER_TARGETS = (showMarkerLabels && !lodSkipCard) || isHoveredOrSelected;
    if (SHOW_MARKER_TARGETS) {
      const displayVal = (isOldDrawing && v.original_value) ? v.original_value : (v.description || "");
      const displayCat = (v.category || "Physical Checklist").replace('_', ' ');
      const displayStat = `Stat: ${statusLabel}`;

      // For CONFLICT (hybrid method only), reuse the same card slot/sizing CHANGED
      // already uses for its extra line — a CONFLICT pin's whole point is "needs a
      // human look," so surfacing that here is the highest-value single addition,
      // without touching the card's pixel-layout math for a third text line.
      const subValueText = markerType === 'CHANGED'
        ? (isOldDrawing ? `Revised Drawing: ${v.description}` : (v.original_value ? `Original Drawing: ${v.original_value}` : null))
        : markerType === 'CONFLICT'
          ? '⚠ Generators disagreed — needs manual review'
          : null;

      ctx.font = `bold ${10 * resolutionMultiplier}px "Yu Gothic", "MS Gothic", monospace`;
      const seqId = `M${String(idx + 1).padStart(3, '0')}`;

      ctx.font = `bold ${12 * resolutionMultiplier}px "Yu Gothic", "MS Gothic", monospace`;
      const valWidth = ctx.measureText(displayVal).width;

      ctx.font = `${10 * resolutionMultiplier}px "Yu Gothic", "MS Gothic", monospace`;
      const catWidth = ctx.measureText(`Cat:  ${displayCat}`).width;
      const statWidth = ctx.measureText(displayStat).width;
      const subWidth = subValueText ? ctx.measureText(subValueText).width : 0;

      const maxTextWidth = Math.max(valWidth + 24 * resolutionMultiplier, catWidth, statWidth, subWidth);
      const cardWidth = Math.max(160 * resolutionMultiplier, maxTextWidth + 16 * resolutionMultiplier);
      const cardHeight = subValueText ? 72 * resolutionMultiplier : 58 * resolutionMultiplier;

      let labelX = screenX - cardWidth / 2;
      let labelY = screenY - cardHeight - 12 * resolutionMultiplier;

      if (labelX < 4 * resolutionMultiplier) labelX = 4 * resolutionMultiplier;
      const screenLimitWidth = isExport ? renderWidth : frame.width;
      if (labelX + cardWidth > screenLimitWidth - 4 * resolutionMultiplier) {
        labelX = screenLimitWidth - cardWidth - 4 * resolutionMultiplier;
      }

      let collisionDetected = true;
      let safetyCounter = 0;
      while (collisionDetected && safetyCounter < 15) {
        collisionDetected = false;
        for (const rect of placedCardRects) {
          const overlapX = (labelX < rect.xMax && labelX + cardWidth > rect.xMin);
          const overlapY = (labelY < rect.yMax && labelY + cardHeight > rect.yMin);
          if (overlapX && overlapY) {
            labelY = rect.yMin - cardHeight - 6 * resolutionMultiplier;
            collisionDetected = true;
            break;
          }
        }
        safetyCounter++;
      }

      placedCardRects.push({
        xMin: labelX,
        xMax: labelX + cardWidth,
        yMin: labelY,
        yMax: labelY + cardHeight
      });

      ctx.shadowColor = 'rgba(0, 0, 0, 0.45)';
      ctx.shadowBlur = 8 * resolutionMultiplier;
      ctx.shadowOffsetX = 2 * resolutionMultiplier;
      ctx.shadowOffsetY = 3 * resolutionMultiplier;

      ctx.fillStyle = cardBg;
      ctx.strokeStyle = bulletColor;
      ctx.lineWidth = 1.2 * resolutionMultiplier;

      ctx.fillRect(labelX, labelY, cardWidth, cardHeight);
      ctx.strokeRect(labelX, labelY, cardWidth, cardHeight);

      ctx.shadowBlur = 0;
      ctx.shadowOffsetX = 0;
      ctx.shadowOffsetY = 0;

      ctx.fillStyle = cardPrimaryText;
      ctx.font = `bold ${10 * resolutionMultiplier}px "Yu Gothic", "MS Gothic", monospace`;
      ctx.fillText(`[${seqId}]`, labelX + 8 * resolutionMultiplier, labelY + 14 * resolutionMultiplier);

      const cardBulletRadius = 4 * resolutionMultiplier;
      const cardBulletX = labelX + 14 * resolutionMultiplier;
      const cardBulletY = labelY + 28 * resolutionMultiplier;

      ctx.beginPath();
      ctx.arc(cardBulletX, cardBulletY, cardBulletRadius, 0, 2 * Math.PI);
      ctx.fillStyle = bulletColor;
      ctx.strokeStyle = cardBulletRing;
      ctx.lineWidth = 1 * resolutionMultiplier;
      ctx.fill();
      ctx.stroke();

      ctx.fillStyle = cardPrimaryText;
      ctx.font = `bold ${12 * resolutionMultiplier}px "Yu Gothic", "MS Gothic", monospace`;
      ctx.fillText(displayVal, labelX + 24 * resolutionMultiplier, labelY + 32 * resolutionMultiplier);

      ctx.fillStyle = cardSecondaryText;
      ctx.font = `${10 * resolutionMultiplier}px "Yu Gothic", "MS Gothic", monospace`;
      ctx.fillText(`Cat:  ${displayCat}`, labelX + 8 * resolutionMultiplier, labelY + 43 * resolutionMultiplier);

      ctx.fillStyle = bulletColor;
      ctx.font = `bold ${10 * resolutionMultiplier}px "Yu Gothic", "MS Gothic", monospace`;
      ctx.fillText(displayStat, labelX + 8 * resolutionMultiplier, labelY + 53 * resolutionMultiplier);

      if (subValueText) {
        ctx.fillStyle = '#f97316';
        ctx.font = `bold ${10 * resolutionMultiplier}px "Yu Gothic", "MS Gothic", monospace`;
        ctx.fillText(subValueText, labelX + 8 * resolutionMultiplier, labelY + 65 * resolutionMultiplier);
      }
    } // <-- Added missing closing brace

    const radius = (v.category === 'drawing_views' ? 4 : 2.5) * resolutionMultiplier * viewport.scale;
    
    if (statusLabel === 'MATCHED') {
      ctx.beginPath();
      ctx.strokeStyle = bulletColor;
      ctx.lineWidth = 3 * resolutionMultiplier;
      ctx.lineCap = 'round';
      ctx.lineJoin = 'round';
      const cx = screenX;
      const cy = screenY;
      const size = 6 * resolutionMultiplier;
      ctx.moveTo(cx - size * 0.8, cy - size * 0.1);
      ctx.lineTo(cx - size * 0.1, cy + size * 0.6);
      ctx.lineTo(cx + size * 0.9, cy - size * 0.7);
      ctx.stroke();

      if (isSelected) {
        ctx.beginPath();
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 1.2 * resolutionMultiplier;
        ctx.setLineDash([3 * resolutionMultiplier, 3 * resolutionMultiplier]);
        ctx.arc(screenX, screenY, size * 1.5, 0, 2 * Math.PI);
        ctx.stroke();
        ctx.setLineDash([]);
      }
    } else {
      ctx.beginPath();
      ctx.fillStyle = isSelected
        ? (penType === 'ai_red' ? 'rgba(255, 40, 80, 0.7)' : penType === 'ai_orange' ? 'rgba(255, 150, 0, 0.7)' : penType === 'checker_blue' ? 'rgba(0, 255, 255, 0.7)' : penType === 'ai_conflict' ? 'rgba(192, 132, 252, 0.7)' : 'rgba(57, 255, 20, 0.7)')
        : (penType === 'ai_red' ? 'rgba(255, 40, 80, 0.4)' : penType === 'ai_orange' ? 'rgba(255, 150, 0, 0.4)' : penType === 'checker_blue' ? 'rgba(0, 255, 255, 0.4)' : penType === 'ai_conflict' ? 'rgba(192, 132, 252, 0.4)' : 'rgba(57, 255, 20, 0.4)');
      
      // Draw the neon dot centered at the exact coordinate
      ctx.arc(screenX, screenY, radius, 0, 2 * Math.PI);
      ctx.fill();

      if (isSelected) {
        ctx.beginPath();
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 1.2 * resolutionMultiplier;
        ctx.setLineDash([2 * resolutionMultiplier, 2 * resolutionMultiplier]);
        ctx.arc(screenX, screenY, radius + 4 * resolutionMultiplier, 0, 2 * Math.PI);
        ctx.stroke();
        ctx.setLineDash([]);
      }
    }


    ctx.restore();
  });
};

export interface RenderAnnotationPinsParams {
  frame: RenderFrame;
  annotations: any[];
  selectedAnnotationId: string | null;
  hoveredAnnotationId?: string | null;
  badgeMap?: Record<string, string>;
}

const PEN_COLORS: Record<string, string> = {
  alert_red: '#ff4d4f',
  warning_orange: '#ffa940',
  amber_gold: '#ffec3d',
  checker_blue: '#00ffff',
  resolved_green: '#39ff14',
  resolved_pink: '#ff7ab6',
};

// Reviewer annotation pins.
// Screen positions are stored under "ann:<id>" keys so annotation hit-testing
// never collides with violation marker keys in the same markerPositionsRef.
export const renderAnnotationPins = ({
  frame,
  annotations,
  selectedAnnotationId,
  hoveredAnnotationId,
  badgeMap,
}: RenderAnnotationPinsParams) => {
  const { ctx, isExport, viewport, norm, resolutionMultiplier, markerPositionsRef } = frame;

  if (frame.isNeonModeActive && !isExport) {
    ctx.filter = 'none';
  }

  annotations.forEach((ann, idx) => {
    const coords = ann.coordinates;
    if (!coords || !Array.isArray(coords) || coords.length < 2) return;

    const [ax, ay] = coords;
    if (!Number.isFinite(ax) || !Number.isFinite(ay)) return;

    const screenPos = worldToScreen(ax, ay, norm, viewport);
    const isSelected = selectedAnnotationId === ann.id;
    const isHovered = hoveredAnnotationId === ann.id;
    const isResolved = ann.status === 'resolved';

    const color = isResolved ? '#39ff14' : (PEN_COLORS[ann.pen_type] || '#00ffff');
    const badgeText = badgeMap?.[ann.id] || `A${String(idx + 1).padStart(3, '0')}`;

    markerPositionsRef.current[`ann:${ann.id}`] = { x: screenPos.x, y: screenPos.y };

    ctx.save();
    const localDpr = isExport ? 1 : (typeof window !== 'undefined' ? window.devicePixelRatio || 1 : 1);
    ctx.setTransform(localDpr, 0, 0, localDpr, 0, 0);

    const r = (isSelected || isHovered ? 7 : 5) * resolutionMultiplier;

    // Outer aura ring for hover/selection
    if (isSelected || isHovered) {
      ctx.beginPath();
      ctx.strokeStyle = isSelected ? '#ffffff' : color;
      ctx.lineWidth = 1.5 * resolutionMultiplier;
      ctx.setLineDash([3 * resolutionMultiplier, 3 * resolutionMultiplier]);
      ctx.arc(screenPos.x, screenPos.y, r + 4 * resolutionMultiplier, 0, 2 * Math.PI);
      ctx.stroke();
      ctx.setLineDash([]);
    }

    // Pin dot
    ctx.beginPath();
    ctx.fillStyle = color;
    ctx.arc(screenPos.x, screenPos.y, r, 0, 2 * Math.PI);
    ctx.fill();
    ctx.lineWidth = 1.5 * resolutionMultiplier;
    ctx.strokeStyle = '#0b0b0b';
    ctx.stroke();

    // Content label & badge tag — visible when zoomed, hovered, or selected
    const showLabel = (viewport.scale >= 0.5 || isSelected || isHovered) && ann.content;
    if (showLabel) {
      const raw = String(ann.content);
      const text = `${badgeText}: ${raw.length > 28 ? raw.slice(0, 27) + '…' : raw}`;
      ctx.font = `bold ${11 * resolutionMultiplier}px "Yu Gothic", "MS Gothic", monospace`;
      const textWidth = ctx.measureText(text).width;
      const padX = 6 * resolutionMultiplier;
      const boxH = 20 * resolutionMultiplier;
      const boxX = screenPos.x + 10 * resolutionMultiplier;
      const boxY = screenPos.y - boxH / 2;

      ctx.fillStyle = 'rgba(11, 11, 11, 0.88)';
      ctx.fillRect(boxX, boxY, textWidth + padX * 2, boxH);
      ctx.lineWidth = 1 * resolutionMultiplier;
      ctx.strokeStyle = color;
      ctx.strokeRect(boxX, boxY, textWidth + padX * 2, boxH);

      ctx.fillStyle = color;
      ctx.textBaseline = 'middle';
      ctx.fillText(text, boxX + padX, screenPos.y);
    }

    ctx.restore();
  });
};
