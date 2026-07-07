import React, { useEffect, useRef, useState, useCallback } from 'react';
import { useReviewStore } from '../../stores/reviewStore';
import { useWorkspaceStore } from '../../stores/workspaceStore';
import { useConnectionStore } from '../../stores/connectionStore';
import { useThemeStore } from '../../stores/themeStore';
import { getNormalization, worldToScreen, screenToWorld, parseBounds } from '../../utils/coordinateTransform';


// Helper utility to strip any residual AutoCAD MTEXT formatting/styling tags
// NOTE: Primary cleaning is done on the backend in entity_mapper.py
// This is only a lightweight safety pass for any codes that slip through
const cleanCadText = (text: string): string => {
  if (!text) return "";
  let clean = text;
  // Replace CP932 decoded multiplication sign "ラ" with standard lowercase "x"
  clean = clean.replace(/ラ/g, "x");
  // Strip grouping braces {...}
  clean = clean.replace(/[{}]/g, "");
  // Strip AutoCAD backslash formatting tags (e.g., \A1;, \W0.85;, \C7;)
  // Uses \\ prefix to avoid matching Unicode/Japanese characters
  clean = clean.replace(/\\[A-Za-z][^;]*;/g, "");
  // Convert CAD paragraph breaks \P to spaces
  clean = clean.replace(/\\P/g, " ");
  return clean.trim();
};

const getPrintColor = (color: string): string => {
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
        return '#b45309'; // Dark amber/orange-brown for yellow
      }
      if (r < 100 && g > 180 && b > 180) {
        return '#0369a1'; // Dark cyan/blue
      }
      if (g > 180 && r < 120 && b < 120) {
        return '#15803d'; // Dark green
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

interface EntityPayload {
  id: string;
  type: string;
  geometry: any;
  style: any;
  properties?: any;
}

interface DrawingCanvasProps {
  layers: Record<string, EntityPayload[]>;
  width: number;
  height: number;
  drawing?: any;
}

export interface DrawingCanvasRef {
  exportImage: (exportWidth?: number, exportHeight?: number) => string;
}

export const DrawingCanvas = React.forwardRef<DrawingCanvasRef, DrawingCanvasProps>(
  ({ layers, width, height, drawing }, ref) => {
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const rafId = useRef<number | null>(null);
    const markerPositionsRef = useRef<Record<string, { x: number, y: number }>>({});

    // Connect stores
    const {
      viewport,
      setViewport,
      activeLayers,
      showViolations,
      showMarkerLabels,
      toggleMarkerLabels,
      hoveredCoords,
      setHoveredCoords,
      isLaserSyncEnabled,
      selectedComparisonRegion,
      isRoiEditModeEnabled,
      customRegions,
      updateCustomRegion,
      visibleMarkerTypes,
      toggleMarkerTypeVisibility
    } = useReviewStore();
    const selectedViolation = useWorkspaceStore((s) => s.selectedViolation);
    const selectViolation = useWorkspaceStore((s) => s.selectViolation);
    const violations = useWorkspaceStore((s) => s.violations);
    const oldDrawing = useWorkspaceStore((s) => s.oldDrawing);
    const theme = useThemeStore((s) => s.theme);
    const dpr = typeof window !== 'undefined' ? window.devicePixelRatio || 1 : 1;

    const [isDragging, setIsDragging] = useState(false);
    const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
    const [mouseCoords, setMouseCoords] = useState<{ x: number, y: number } | null>(null);
    const [isNeonCAD, setIsNeonCAD] = useState(false);
    const [renderDiagnostics, setRenderDiagnostics] = useState({ entityCount: 0, drawCount: 0, renderTimeMs: 0 });
    const [redrawTrigger, setRedrawTrigger] = useState(0);
    const [isSpacePressed, setIsSpacePressed] = useState(false);

    // Draggable Markers State
    const [dragMarkerId, setDragMarkerId] = useState<string | null>(null);
    const [hoveredMarkerId, setHoveredMarkerId] = useState<string | null>(null);
    const [dragMarkerStartPos, setDragMarkerStartPos] = useState<[number, number] | null | undefined>(null);
    const [dragMarkerMouseStart, setDragMarkerMouseStart] = useState<{ x: number, y: number }>({ x: 0, y: 0 });
    const [hasDragMarkerMoved, setHasDragMarkerMoved] = useState(false);
    const [dragMarkerOriginalCoords, setDragMarkerOriginalCoords] = useState<{ coordinates?: [number, number], ref_coordinates?: [number, number] } | null>(null);

    // Custom Context Menu State
    const [contextMenu, setContextMenu] = useState<{
      visible: boolean;
      x: number;
      y: number;
      wx: number; // CAD world coordinates
      wy: number;
    } | null>(null);
    const [preventNextContextMenu, setPreventNextContextMenu] = useState(false);

    // Close context menu on outside click
    useEffect(() => {
      const closeMenu = () => {
        setContextMenu(null);
      };
      if (contextMenu) {
        window.addEventListener('click', closeMenu);
        window.addEventListener('mousedown', closeMenu);
      }
      return () => {
        window.removeEventListener('click', closeMenu);
        window.removeEventListener('mousedown', closeMenu);
      };
    }, [contextMenu]);

    // Track Spacebar for panning override
    useEffect(() => {
      const handleKeyDown = (e: KeyboardEvent) => {
        if (e.key === ' ' && document.activeElement?.tagName !== 'INPUT' && document.activeElement?.tagName !== 'TEXTAREA') {
          setIsSpacePressed(true);
          e.preventDefault();
        }
      };
      const handleKeyUp = (e: KeyboardEvent) => {
        if (e.key === ' ') {
          setIsSpacePressed(false);
        }
      };
      window.addEventListener('keydown', handleKeyDown);
      window.addEventListener('keyup', handleKeyUp);
      const handleBlur = () => setIsSpacePressed(false);
      window.addEventListener('blur', handleBlur);
      return () => {
        window.removeEventListener('keydown', handleKeyDown);
        window.removeEventListener('keyup', handleKeyUp);
        window.removeEventListener('blur', handleBlur);
      };
    }, []);

    // ROI Interactive Drag handles local states
    const [activeDragHandle, setActiveDragHandle] = useState<{
      regionKey: string;
      handleId: 'top-left' | 'top-right' | 'bottom-left' | 'bottom-right' | 'center';
    } | null>(null);
    const [hoveredHandleInfo, setHoveredHandleInfo] = useState<{
      regionKey: string;
      handleId: string;
      cursor: string;
    } | null>(null);
    const [centerDragStart, setCenterDragStart] = useState<{
      pctX: number;
      pctY: number;
      originalXMin: number;
      originalXMax: number;
      originalYMin: number;
      originalYMax: number;
    } | null>(null);

    // Connect background raster image for high-fidelity rendering parity
    const [bgImage, setBgImage] = useState<HTMLImageElement | null>(null);
    const [lightBgImage, setLightBgImage] = useState<HTMLImageElement | null>(null);

    const [isHoveringMarkerState, setIsHoveringMarkerState] = useState(false);

    // Throttled Console logging for Marker Targets semantic correctness validation
    useEffect(() => {
      if (showViolations && violations.length > 0) {
        console.log("=== COMPLIANCE MARKERS TARGETS VERIFICATION AUDIT ===");
        violations.forEach((v, idx) => {
          let matchedTextEnt: any = null;
          Object.values(layers).forEach((entities) => {
            entities.forEach((ent) => {
              if (ent.type === 'text') {
                const rawText = ent.geometry?.text || ent.geometry?.content || ent.properties?.text || '';
                if (cleanCadText(rawText).trim() === cleanCadText(v.description).trim()) {
                  matchedTextEnt = ent;
                }
              }
            });
          });

          const bboxStr = matchedTextEnt?.properties?.bbox
            ? `[ [${matchedTextEnt.properties.bbox[0][0].toFixed(2)}, ${matchedTextEnt.properties.bbox[0][1].toFixed(2)}], [${matchedTextEnt.properties.bbox[1][0].toFixed(2)}, ${matchedTextEnt.properties.bbox[1][1].toFixed(2)}] ]`
            : "None (Fallback)";

          const coordStr = v.coordinates
            ? `[${v.coordinates[0].toFixed(2)}, ${v.coordinates[1].toFixed(2)}]`
            : "None";

          console.log(
            `Marker #${idx + 1} | ` +
            `ID: ${v.id} | ` +
            `Text Value: "${v.description}" | ` +
            `Category: ${v.category} | ` +
            `Coords: ${coordStr} | ` +
            `BBox: ${bboxStr} | ` +
            `Comparison: "${v.recommendation}"`
          );
        });
        console.log("=====================================================");
      }
    }, [violations, showViolations, layers]);

    useEffect(() => {
      if (!drawing?.id) {
        setBgImage(null);
        setLightBgImage(null);
        return;
      }

      const { backendUrl, apiToken } = useConnectionStore.getState();
      const headers: Record<string, string> = { "Accept": "image/png" };
      if (apiToken) {
        headers["Authorization"] = `Bearer ${apiToken}`;
      }

      let active = true;
      const loadBackground = async () => {
        try {
          const res = await fetch(`${backendUrl}/api/v1/drawings/${drawing.id}/rendering`, { headers });
          if (!res.ok) {
            throw new Error("No rendering generated");
          }
          const blob = await res.blob();
          if (!active) return;

          const img = new Image();
          img.src = URL.createObjectURL(blob);
          img.onload = () => {
            if (active) {
              const canvas = document.createElement('canvas');
              canvas.width = img.width;
              canvas.height = img.height;
              const context = canvas.getContext('2d');
              if (context) {
                context.drawImage(img, 0, 0);
                const imgData = context.getImageData(0, 0, canvas.width, canvas.height);
                const data = imgData.data;
                for (let i = 0; i < data.length; i += 4) {
                  if (data[i + 3] === 0) continue; // Skip fully transparent
                  const r = data[i], g = data[i + 1], b = data[i + 2];
                  // Check if pixel is grayscale (very low saturation)
                  if (Math.max(r, g, b) - Math.min(r, g, b) < 25) {
                    data[i] = 255 - r;
                    data[i + 1] = 255 - g;
                    data[i + 2] = 255 - b;
                  } else {
                    // Darken bright colored pixels to be visible on white backgrounds
                    const brightness = (r * 299 + g * 587 + b * 114) / 1000;
                    if (brightness > 150) {
                      data[i] = Math.round(r * 0.45);
                      data[i + 1] = Math.round(g * 0.45);
                      data[i + 2] = Math.round(b * 0.45);
                    }
                  }
                }
                context.putImageData(imgData, 0, 0);
                const lightImg = new Image();
                lightImg.src = canvas.toDataURL();
                setLightBgImage(lightImg);
              }

              setBgImage(img);
              setRedrawTrigger((prev) => prev + 1);
            }
          };
        } catch (err) {
          console.warn("Background rendering not found or failed to load. Falling back to vector rendering.", err);
          if (active) {
            setBgImage(null);
            setLightBgImage(null);
          }
        }
      };

      loadBackground();
      return () => {
        active = false;
      };
    }, [drawing?.id]);

    const renderContent = useCallback((ctx: CanvasRenderingContext2D, isExport: boolean, renderWidth: number = width, renderHeight: number = height) => {
      // Site A: renderContent normalization — consolidated via getNormalization()
      const norm = getNormalization(parseBounds(drawing?.metadata?.render_bounds));
      const normalizationScale = norm.normScale;
      const normXMin = norm.xmin;
      const normYMin = norm.ymin;

      const effectiveScale = viewport.scale * normalizationScale;
      const resolutionMultiplier = renderWidth / width;

      // 1. Clear infinite background
      if (isExport) {
        ctx.fillStyle = '#ffffff'; // Clean white background for print
      } else {
        ctx.fillStyle = theme === 'hc-light' ? '#f4f4f5' : '#09090b';
      }
      ctx.fillRect(0, 0, renderWidth, renderHeight);

      // 2. Draw fine engineering grids (Skip if exporting!)
      if (!isExport) {
        ctx.save();
        ctx.strokeStyle = theme === 'hc-light' ? 'rgba(9, 9, 11, 0.08)' : 'rgba(63, 63, 70, 0.25)';
        ctx.lineWidth = 1;

        const targetScreenSpacing = 50;
        const rawWorldSpacing = targetScreenSpacing / effectiveScale;
        const exponent = Math.floor(Math.log10(rawWorldSpacing));
        const powerOf10 = Math.pow(10, exponent);
        const ratio = rawWorldSpacing / powerOf10;

        let worldSpacing = powerOf10;
        if (ratio > 5) {
          worldSpacing = powerOf10 * 5;
        } else if (ratio > 2) {
          worldSpacing = powerOf10 * 2;
        }

        const screenSpacing = worldSpacing * effectiveScale;
        const screenOriginX = viewport.x - normXMin * effectiveScale;
        const screenOriginY = viewport.y - normYMin * effectiveScale;

        const kStartX = Math.floor((0 - screenOriginX) / screenSpacing);
        const kEndX = Math.ceil((renderWidth - screenOriginX) / screenSpacing);
        for (let k = kStartX; k <= kEndX; k++) {
          const sx = Math.round(screenOriginX + k * screenSpacing);
          ctx.beginPath();
          ctx.moveTo(sx, 0);
          ctx.lineTo(sx, renderHeight);
          ctx.stroke();
        }

        const kStartY = Math.floor((0 - screenOriginY) / screenSpacing);
        const kEndY = Math.ceil((renderHeight - screenOriginY) / screenSpacing);
        for (let k = kStartY; k <= kEndY; k++) {
          const sy = Math.round(screenOriginY + k * screenSpacing);
          ctx.beginPath();
          ctx.moveTo(0, sy);
          ctx.lineTo(renderWidth, sy);
          ctx.stroke();
        }
        ctx.restore();
      }

      // 3. Setup transformations (apply normalization or fit bounds for export)
      let scale = effectiveScale;
      let transX = viewport.x - normXMin * effectiveScale;
      let transY = viewport.y - normYMin * effectiveScale;

      if (isExport && drawing?.metadata?.render_bounds) {
        const [xmin, ymin, xmax, ymax] = drawing.metadata.render_bounds;
        const drawingW = xmax - xmin;
        const drawingH = ymax - ymin;
        if (drawingW > 0 && drawingH > 0) {
          const padding = Math.max(30, Math.round(renderWidth * 0.04)); // Dynamic padding proportional to output resolution
          const scaleX = (renderWidth - 2 * padding) / drawingW;
          const scaleY = (renderHeight - 2 * padding) / drawingH;
          scale = Math.min(scaleX, scaleY);
          transX = padding + (renderWidth - 2 * padding - drawingW * scale) / 2 - xmin * scale;
          transY = padding + (renderHeight - 2 * padding - drawingH * scale) / 2 - ymin * scale;
        }
      }

      ctx.save();
      ctx.translate(transX, transY);
      ctx.scale(scale, scale);

      let currentFilter = "none";
      if (isNeonCAD && !isExport) {
        currentFilter = "contrast(1.25) brightness(1.15) saturate(1.35) hue-rotate(2deg)";
      }
      ctx.filter = currentFilter;

      // Draw high-fidelity raster CAD background image if loaded, aligned exactly to CAD coordinates bounds
      const targetImage = (isExport || theme === 'hc-light') ? lightBgImage : bgImage;
      if (targetImage && drawing?.metadata?.render_bounds) {
        const [xmin, ymin, xmax, ymax] = drawing.metadata.render_bounds;
        ctx.drawImage(targetImage, xmin, ymin, xmax - xmin, ymax - ymin);
      }

      // 4. Viewport bounds in world coordinates (for culling virtualization)
      const minX = -transX / scale;
      const minY = -transY / scale;
      const maxX = (renderWidth - transX) / scale;
      const maxY = (renderHeight - transY) / scale;
      const currentViewportScale = scale / normalizationScale;

      let totalEntities = 0;
      let drawnEntities = 0;

      // 5. Draw entity layers
      const pathBatches: Record<string, { stroke: string, width: number, path: Path2D }> = {};

      Object.entries(layers).forEach(([layerName, entities]) => {
        if (activeLayers[layerName] === false) return;

        entities.forEach((ent) => {
          totalEntities++;

          if (bgImage && drawing?.metadata?.render_bounds) {
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
        ctx.lineWidth = (batch.width / currentViewportScale) * resolutionMultiplier;
        ctx.stroke(batch.path);
      });

      // 6. Draw compliance violations reticles if active
      ctx.filter = 'none';
      if (showViolations) {
        // norm is already computed above for Site A — hasBounds, ymin, ymax all available via norm
        const isOldDrawing = oldDrawing && drawing?.id === oldDrawing.id;
        const placedCardRects: { xMin: number; xMax: number; yMin: number; yMax: number }[] = [];

        // Sort violations to enforce visual Z-Index: MATCHED (bottom) < CHANGED < ADDED/REMOVED (top)
        const getPriority = (penType: string) => {
          if (penType === 'ai_red' || penType === 'checker_blue') return 3;
          if (penType === 'ai_orange') return 2;
          return 1; // ai_green, resolved_green
        };

        const sortedViolationsWithIndex = violations.map((v, i) => ({ v, i })).sort((a, b) => {
          return getPriority(a.v.pen_type || 'ai_red') - getPriority(b.v.pen_type || 'ai_red');
        });

        sortedViolationsWithIndex.forEach(({ v, i: idx }) => {
          const penType = v.pen_type || 'ai_red';
          if (penType !== 'ai_red' && penType !== 'ai_orange' && penType !== 'checker_blue' && penType !== 'ai_green' && penType !== 'resolved_green') return;

          // Sheet Isolation filters — strict per-canvas rules:
          // ORIGINAL canvas: only MATCHED (green) + REMOVED (red) are visible.
          // KMTI canvas:     only MATCHED (green) + CHANGED (orange) + ADDED (blue) are visible.
          //
          // ADDED (blue)    — new content in KMTI only     → hide on ORIGINAL
          if (isOldDrawing && penType === 'checker_blue') return;
          // CHANGED (orange) — revision of a value in KMTI → hide on ORIGINAL (belongs on the revision side)
          // Removed: if (isOldDrawing && penType === 'ai_orange') return; -> Users want to see the orange pin on the Original to know what changed.
          // REMOVED (red)   — content deleted in KMTI      → hide on KMTI (it only existed in ORIGINAL)
          if (!isOldDrawing && penType === 'ai_red') return;

          let markerType = 'MISMATCHED';
          if (penType === 'ai_orange') markerType = 'CHANGED';
          else if (penType === 'checker_blue') markerType = 'ADDED';
          else if (penType === 'ai_green' || penType === 'resolved_green') markerType = 'MATCHED';

          if (!visibleMarkerTypes[markerType]) return;

          // Strictly use ref_coordinates for old/original drawing, and coordinates for new/revised drawing.
          // Never fall back to the other drawing's coordinates, which leads to floating markers!
          let coords = isOldDrawing ? v.ref_coordinates : v.coordinates;
          let bbox: any = isOldDrawing ? (v as any).ref_bbox : (v as any).bbox;
          if (!coords) return;

          const [vx, raw_vy] = coords;
          // Use worldToScreen with the shared norm from Site A — applies Y-flip when hasBounds
          const screenPos = worldToScreen(vx, raw_vy, norm, viewport);
          const isSelected = selectedViolation?.id === v.id;

          const bulletColor = penType === 'ai_red' ? '#ef4444' : penType === 'ai_orange' ? '#f97316' : penType === 'checker_blue' ? '#3b82f6' : '#10b981';
          const statusLabel = penType === 'ai_red' ? 'MISMATCHED' : penType === 'ai_orange' ? 'CHANGED' : penType === 'checker_blue' ? 'ADDED' : 'MATCHED';

          // Project CAD coordinates onto absolute screen/CSS coordinates
          let screenX = screenPos.x;
          let screenY = screenPos.y;

          // Cache final visual coordinates for accurate hover detection (read by handleMouseMove hit-testing)
          markerPositionsRef.current[v.id] = { x: screenX, y: screenY };

          // Reset context matrix to pixel space scaled by localDpr for stable rendering
          ctx.save();
          const localDpr = isExport ? 1 : (typeof window !== 'undefined' ? window.devicePixelRatio || 1 : 1);
          ctx.setTransform(localDpr, 0, 0, localDpr, 0, 0);

          const SHOW_MARKER_TARGETS = (showMarkerLabels && hoveredMarkerId === v.id) || isSelected;
          if (SHOW_MARKER_TARGETS) {
            // Text values to display without truncation
            const displayVal = (isOldDrawing && v.original_value) ? v.original_value : (v.description || "");
            const displayCat = (v.category || "Physical Checklist").replace('_', ' ');
            const displayStat = `Stat: ${statusLabel}`;

            // Only add secondary text if it's a CHANGED status
            const subValueText = markerType === 'CHANGED'
              ? (isOldDrawing ? `Revised Drawing: ${v.description}` : (v.original_value ? `Original Drawing: ${v.original_value}` : null))
              : null;

            ctx.font = `bold ${10 * resolutionMultiplier}px "Yu Gothic", "MS Gothic", monospace`;
            const seqId = `M${String(idx + 1).padStart(3, '0')}`;

            ctx.font = `bold ${12 * resolutionMultiplier}px "Yu Gothic", "MS Gothic", monospace`;
            const valWidth = ctx.measureText(displayVal).width;

            ctx.font = `${10 * resolutionMultiplier}px "Yu Gothic", "MS Gothic", monospace`;
            const catWidth = ctx.measureText(`Cat:  ${displayCat}`).width;
            const statWidth = ctx.measureText(displayStat).width;
            const subWidth = subValueText ? ctx.measureText(subValueText).width : 0;

            // Compute dynamic card size to fit all text values comfortably
            const maxTextWidth = Math.max(valWidth + 24 * resolutionMultiplier, catWidth, statWidth, subWidth);
            const cardWidth = Math.max(160 * resolutionMultiplier, maxTextWidth + 16 * resolutionMultiplier);
            const cardHeight = subValueText ? 72 * resolutionMultiplier : 58 * resolutionMultiplier;

            // Center card horizontally above the marker
            let labelX = screenX - cardWidth / 2;
            let labelY = screenY - cardHeight - 12 * resolutionMultiplier;

            // Screen boundaries check (keep on screen)
            if (labelX < 4 * resolutionMultiplier) labelX = 4 * resolutionMultiplier;
            const screenLimitWidth = isExport ? renderWidth : width;
            if (labelX + cardWidth > screenLimitWidth - 4 * resolutionMultiplier) {
              labelX = screenLimitWidth - cardWidth - 4 * resolutionMultiplier;
            }

            // Screen-space vertical collision resolution loop to prevent label overlaps
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

            // Draw premium shadow
            ctx.shadowColor = 'rgba(0, 0, 0, 0.45)';
            ctx.shadowBlur = 8 * resolutionMultiplier;
            ctx.shadowOffsetX = 2 * resolutionMultiplier;
            ctx.shadowOffsetY = 3 * resolutionMultiplier;

            ctx.fillStyle = 'rgba(9, 9, 11, 0.95)';
            ctx.strokeStyle = bulletColor;
            ctx.lineWidth = 1.2 * resolutionMultiplier;

            ctx.fillRect(labelX, labelY, cardWidth, cardHeight);
            ctx.strokeRect(labelX, labelY, cardWidth, cardHeight);

            // Restore shadow state for texts
            ctx.shadowBlur = 0;
            ctx.shadowOffsetX = 0;
            ctx.shadowOffsetY = 0;

            // Sequence ID line
            ctx.fillStyle = '#ffffff';
            ctx.font = `bold ${10 * resolutionMultiplier}px "Yu Gothic", "MS Gothic", monospace`;
            ctx.fillText(`[${seqId}]`, labelX + 8 * resolutionMultiplier, labelY + 14 * resolutionMultiplier);

            // Bullet marker inline to the left of the text value
            // Format: [Bullet Marker] Value
            const cardBulletRadius = 4 * resolutionMultiplier;
            const cardBulletX = labelX + 14 * resolutionMultiplier;
            const cardBulletY = labelY + 28 * resolutionMultiplier;

            ctx.beginPath();
            ctx.arc(cardBulletX, cardBulletY, cardBulletRadius, 0, 2 * Math.PI);
            ctx.fillStyle = bulletColor;
            ctx.strokeStyle = '#ffffff';
            ctx.lineWidth = 1 * resolutionMultiplier;
            ctx.fill();
            ctx.stroke();

            // Value text
            ctx.fillStyle = '#ffffff';
            ctx.font = `bold ${12 * resolutionMultiplier}px "Yu Gothic", "MS Gothic", monospace`;
            ctx.fillText(displayVal, labelX + 24 * resolutionMultiplier, labelY + 32 * resolutionMultiplier);

            // Category & Status lines
            ctx.fillStyle = 'rgba(255, 255, 255, 0.7)';
            ctx.font = `${10 * resolutionMultiplier}px "Yu Gothic", "MS Gothic", monospace`;
            ctx.fillText(`Cat:  ${displayCat}`, labelX + 8 * resolutionMultiplier, labelY + 43 * resolutionMultiplier);

            ctx.fillStyle = bulletColor;
            ctx.font = `bold ${10 * resolutionMultiplier}px "Yu Gothic", "MS Gothic", monospace`;
            ctx.fillText(displayStat, labelX + 8 * resolutionMultiplier, labelY + 53 * resolutionMultiplier);

            // Render Original/Revised value underneath if applicable
            if (subValueText) {
              ctx.fillStyle = '#f97316'; // Same as changed marker color
              ctx.font = `bold ${10 * resolutionMultiplier}px "Yu Gothic", "MS Gothic", monospace`;
              ctx.fillText(subValueText, labelX + 8 * resolutionMultiplier, labelY + 65 * resolutionMultiplier);
            }
          }

          // Use Box rendering for Title Block, BOM, Notes, Isometric. Use Checkmark for Drawing Views.
          if (v.category !== 'drawing_views') {
            // Default to fixed box around center coordinate if bbox is missing
            let pxmin = screenX - 10 * resolutionMultiplier;
            let pymin = screenY - 10 * resolutionMultiplier;
            let rectW = 20 * resolutionMultiplier;
            let rectH = 20 * resolutionMultiplier;

            if (bbox && bbox.length >= 2) {
              const [[bxmin, bymin_raw], [bxmax, bymax_raw]] = bbox;
              // Use worldToScreen for both bbox corners — Y-flip applied via norm
              const bMinScreen = worldToScreen(bxmin, bymin_raw, norm, viewport);
              const bMaxScreen = worldToScreen(bxmax, bymax_raw, norm, viewport);

              pxmin = bMinScreen.x;
              pymin = Math.min(bMinScreen.y, bMaxScreen.y);
              const pxmax = bMaxScreen.x;
              const pymax = Math.max(bMinScreen.y, bMaxScreen.y);
              rectW = Math.max(pxmax - pxmin, 1);
              rectH = Math.max(pymax - pymin, 1);
            }

            // Draw precise polygonal highlight box
            ctx.beginPath();
            ctx.rect(pxmin, pymin, rectW, rectH);
            ctx.fillStyle = isSelected
              ? (penType === 'ai_red' ? 'rgba(239, 68, 68, 0.25)' : penType === 'ai_orange' ? 'rgba(249, 115, 22, 0.25)' : penType === 'checker_blue' ? 'rgba(59, 130, 246, 0.25)' : 'rgba(16, 185, 129, 0.25)')
              : (penType === 'ai_red' ? 'rgba(239, 68, 68, 0.12)' : penType === 'ai_orange' ? 'rgba(249, 115, 22, 0.12)' : penType === 'checker_blue' ? 'rgba(59, 130, 246, 0.12)' : 'rgba(16, 185, 129, 0.12)');
            ctx.fill();
            ctx.strokeStyle = bulletColor;
            ctx.lineWidth = 1.5 * resolutionMultiplier;
            ctx.stroke();

            // Draw selection dashed ring over it
            if (isSelected) {
              ctx.beginPath();
              ctx.strokeStyle = '#ffffff';
              ctx.lineWidth = 1.2 * resolutionMultiplier;
              ctx.setLineDash([3 * resolutionMultiplier, 3 * resolutionMultiplier]);
              ctx.rect(pxmin - 4 * resolutionMultiplier, pymin - 4 * resolutionMultiplier, rectW + 8 * resolutionMultiplier, rectH + 8 * resolutionMultiplier);
              ctx.stroke();
              ctx.setLineDash([]);
            }
          } else {
            // Drawing Views: Draw a Checkmark (no circle)
            // 1. Draw glowing circular background to help it stand out
            const radius = 12 * resolutionMultiplier;
            ctx.beginPath();
            ctx.fillStyle = isSelected
              ? (penType === 'ai_red' ? 'rgba(239, 68, 68, 0.25)' : penType === 'ai_orange' ? 'rgba(249, 115, 22, 0.25)' : penType === 'checker_blue' ? 'rgba(59, 130, 246, 0.25)' : 'rgba(16, 185, 129, 0.25)')
              : (penType === 'ai_red' ? 'rgba(239, 68, 68, 0.08)' : penType === 'ai_orange' ? 'rgba(249, 115, 22, 0.08)' : penType === 'checker_blue' ? 'rgba(59, 130, 246, 0.08)' : 'rgba(16, 185, 129, 0.08)');
            ctx.arc(screenX, screenY, radius * 1.6, 0, 2 * Math.PI);
            ctx.fill();

            // 2. Draw Checkmark
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

            // 3. Draw selection dashed ring
            if (isSelected) {
              ctx.beginPath();
              ctx.strokeStyle = '#ffffff';
              ctx.lineWidth = 1.2 * resolutionMultiplier;
              ctx.setLineDash([3 * resolutionMultiplier, 3 * resolutionMultiplier]);
              ctx.arc(screenX, screenY, radius * 1.8, 0, 2 * Math.PI);
              ctx.stroke();
              ctx.setLineDash([]);
            }
          }

          ctx.restore();
        });
      }

      ctx.restore();

      // 7. Dynamic Crosshair Inspector overlay
      if (!isExport && mouseCoords) {
        ctx.save();
        ctx.strokeStyle = 'rgba(161, 161, 170, 0.35)';
        ctx.setLineDash([4, 4]);
        ctx.lineWidth = 0.8;

        ctx.beginPath();
        ctx.moveTo(0, mouseCoords.y);
        ctx.lineTo(width, mouseCoords.y);
        ctx.stroke();

        ctx.beginPath();
        ctx.moveTo(mouseCoords.x, 0);
        ctx.lineTo(mouseCoords.x, height);
        ctx.stroke();

        const wx = (normXMin + (mouseCoords.x - viewport.x) / effectiveScale).toFixed(2);
        // REFACTOR-NOTE (Site F pattern): raw_wy uses sign-inverted Y convention for display coords.
        // screenToWorld applies Y-flip; the value below matches original behavior (display only, not stored).
        const worldCoords = screenToWorld(mouseCoords.x, mouseCoords.y, norm, viewport);
        const wy = worldCoords.y.toFixed(2);

        ctx.fillStyle = isHoveringMarkerState ? '#ef4444' : '#a1a1aa';
        ctx.font = '10px monospace';
        const tooltipText = isHoveringMarkerState ? `X: ${wx}, Y: ${wy} (Alt + Click to Delete)` : `X: ${wx}, Y: ${wy}`;
        ctx.fillText(tooltipText, mouseCoords.x + 8, mouseCoords.y - 8);
        ctx.restore();
      }

      // 7.5 Draw Synced Laser Crosshair from the other viewport!
      if (!isExport && isLaserSyncEnabled && hoveredCoords && !mouseCoords) {
        // hoveredCoords stores world (CAD) coordinates from handleMouseMove (Site F).
        // worldToScreen applies the Y-flip to map back to canvas pixel space.
        const synced = worldToScreen(hoveredCoords.x, hoveredCoords.y, norm, viewport);
        const syncedX = synced.x;
        const syncedY = synced.y;

        if (syncedX >= 0 && syncedX <= width && syncedY >= 0 && syncedY <= height) {
          ctx.save();
          ctx.beginPath();
          ctx.strokeStyle = '#00ffcc';
          ctx.lineWidth = 1.5;
          ctx.shadowBlur = 10;
          ctx.shadowColor = '#00ffcc';
          ctx.arc(syncedX, syncedY, 16, 0, 2 * Math.PI);
          ctx.stroke();

          ctx.beginPath();
          ctx.fillStyle = '#00ffcc';
          ctx.arc(syncedX, syncedY, 3, 0, 2 * Math.PI);
          ctx.fill();

          ctx.strokeStyle = 'rgba(0, 255, 204, 0.4)';
          ctx.lineWidth = 1.0;
          ctx.shadowBlur = 0;

          ctx.beginPath();
          ctx.moveTo(syncedX, syncedY - 26);
          ctx.lineTo(syncedX, syncedY - 10);
          ctx.stroke();

          ctx.beginPath();
          ctx.moveTo(syncedX, syncedY + 10);
          ctx.lineTo(syncedX, syncedY + 26);
          ctx.stroke();

          ctx.beginPath();
          ctx.moveTo(syncedX - 26, syncedY);
          ctx.lineTo(syncedX - 10, syncedY);
          ctx.stroke();

          ctx.beginPath();
          ctx.moveTo(syncedX + 10, syncedY);
          ctx.lineTo(syncedX + 26, syncedY);
          ctx.stroke();

          ctx.restore();
        }
      }

      return { totalEntities, drawnEntities };
    }, [layers, width, height, viewport, activeLayers, showViolations, showMarkerLabels, violations, selectedViolation, mouseCoords, bgImage, drawing, isNeonCAD, hoveredCoords, isLaserSyncEnabled, theme, lightBgImage, isHoveringMarkerState, oldDrawing, hoveredMarkerId]);

    // Redraw logic
    const drawCanvas = useCallback(() => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const ctx = canvas.getContext('2d');
      if (!ctx) return;

      const localDpr = typeof window !== 'undefined' ? window.devicePixelRatio || 1 : 1;
      ctx.setTransform(localDpr, 0, 0, localDpr, 0, 0);

      ctx.imageSmoothingEnabled = true;
      ctx.imageSmoothingQuality = 'high';

      const startTime = performance.now();
      const stats = renderContent(ctx, false);
      const endTime = performance.now();

      if (stats) {
        setRenderDiagnostics({
          entityCount: stats.totalEntities,
          drawCount: stats.drawnEntities,
          renderTimeMs: Math.round((endTime - startTime) * 100) / 100
        });
      }
    }, [renderContent]);

    React.useImperativeHandle(ref, () => ({
      exportImage: (exportWidth?: number, exportHeight?: number) => {
        const canvas = document.createElement('canvas');
        const targetW = exportWidth || 7016;
        const targetH = exportHeight || 4960;
        canvas.width = targetW;
        canvas.height = targetH;
        const ctx = canvas.getContext('2d');
        if (!ctx) return '';
        ctx.imageSmoothingEnabled = true;
        ctx.imageSmoothingQuality = 'high';
        renderContent(ctx, true, targetW, targetH);
        return canvas.toDataURL('image/png');
      }
    }));

    // Handle redraw when values update
    useEffect(() => {
      if (rafId.current) cancelAnimationFrame(rafId.current);
      rafId.current = requestAnimationFrame(() => {
        drawCanvas();
      });
      return () => {
        if (rafId.current) cancelAnimationFrame(rafId.current);
      };
    }, [drawCanvas, redrawTrigger]);

    // Zoom-to-focus selected violation coordinates (smooth dynamic viewport tracking)
    useEffect(() => {
      if (selectedViolation && selectedViolation.coordinates && drawing) {
        // Ensure only the canvas corresponding to the violation owner updates the global viewport!
        if ((selectedViolation as any).drawing_id === drawing.id) {
          const [vx, vy] = selectedViolation.coordinates;

          // Site B: zoom-to-focus normalization — consolidated via getNormalization()
          const norm = getNormalization(parseBounds(drawing?.metadata?.render_bounds));
          // worldToScreen gives absolute canvas pixels; we need normalized coords for viewport math.
          // stdX/stdY are in the 0-1000 normalization space (world - xmin) * normScale
          const stdX = (vx - norm.xmin) * norm.normScale;
          const vy_inverted = norm.hasBounds ? (norm.ymax + norm.ymin - vy) : vy;
          const stdY = (vy_inverted - norm.ymin) * norm.normScale;

          const targetScale = 2.2;
          const targetX = width / 2 - stdX * targetScale;
          const targetY = height / 2 - stdY * targetScale;

          // Update the shared viewport store instantly so both baseline and revision sync focus
          setViewport({ x: targetX, y: targetY, scale: targetScale });
        }
      }
    }, [selectedViolation, drawing, width, height, setViewport]);

    // Keyboard shortcut actions
    useEffect(() => {
      const handleKeyDown = (e: KeyboardEvent) => {
        if (document.activeElement?.tagName === 'INPUT' || document.activeElement?.tagName === 'TEXTAREA') {
          return;
        }

        const key = e.key.toLowerCase();
        if ((e.ctrlKey || e.metaKey) && key === 'z') {
          e.preventDefault();
          useWorkspaceStore.getState().undoLastAction();
          return;
        }
        if (key === 'escape') {
          e.preventDefault();
          selectViolation(null);
        } else if (key === 'f') {
          e.preventDefault();
          if (selectedViolation && selectedViolation.coordinates && drawing) {
            const [vx, vy] = selectedViolation.coordinates;

            // Site C: key 'f' zoom-to-focus — same normalization pattern as Site B
            const norm = getNormalization(parseBounds(drawing?.metadata?.render_bounds));
            const stdX = (vx - norm.xmin) * norm.normScale;
            const vy_inverted = norm.hasBounds ? (norm.ymax + norm.ymin - vy) : vy;
            const stdY = (vy_inverted - norm.ymin) * norm.normScale;

            const targetScale = 2.2;
            const targetX = width / 2 - stdX * targetScale;
            const targetY = height / 2 - stdY * targetScale;
            setViewport({ x: targetX, y: targetY, scale: targetScale });
          }
        } else if (e.key === 'delete' || e.key === 'backspace') {
          if (selectedViolation) {
            e.preventDefault();
            const currentViolations = useWorkspaceStore.getState().violations;
            useWorkspaceStore.setState({
              violations: currentViolations.filter(v => v.id !== selectedViolation.id),
              selectedViolation: null
            });
          }
        } else if (e.ctrlKey && (e.key === '=' || e.key === '+')) {
          e.preventDefault();
          setViewport({ ...viewport, scale: Math.min(25, viewport.scale * 1.25) });
        } else if (e.ctrlKey && e.key === '-') {
          e.preventDefault();
          setViewport({ ...viewport, scale: Math.max(0.1, viewport.scale / 1.25) });
        }
      };

      window.addEventListener('keydown', handleKeyDown);
      return () => {
        window.removeEventListener('keydown', handleKeyDown);
      };
    }, [viewport, selectedViolation, width, height, setViewport, selectViolation]);

    // Mouse wheel zoom
    const handleWheel = useCallback((e: WheelEvent) => {
      e.preventDefault();
      const zoomFactor = e.deltaY > 0 ? 0.9 : 1.1;

      const rect = canvasRef.current?.getBoundingClientRect();
      if (!rect) return;

      const mouseX = e.clientX - rect.left;
      const mouseY = e.clientY - rect.top;

      const worldX = (mouseX - viewport.x) / viewport.scale;
      const worldY = (mouseY - viewport.y) / viewport.scale;

      const newScale = Math.max(0.1, Math.min(viewport.scale * zoomFactor, 25));
      const newX = mouseX - worldX * newScale;
      const newY = mouseY - worldY * newScale;

      setViewport({ x: newX, y: newY, scale: newScale });
    }, [viewport, setViewport]);

    useEffect(() => {
      const canvas = canvasRef.current;
      if (canvas) {
        canvas.addEventListener('wheel', handleWheel, { passive: false });
      }
      return () => {
        if (canvas) {
          canvas.removeEventListener('wheel', handleWheel);
        }
      };
    }, [handleWheel]);

    // Mouse pan triggers
    const handleMouseDown = (e: React.MouseEvent) => {
      if (e.button === 1 || e.button === 2 || isSpacePressed) {
        // Middle click, Right click, or Spacebar+Left click strictly reserved for seamless panning!
        // Skip all marker and boundary checks to guarantee immediate panning capability
        setIsDragging(true);
        setDragStart({ x: e.clientX - viewport.x, y: e.clientY - viewport.y });
        e.preventDefault();
        return;
      }
      if (e.button === 0) { // Left click to drag or calibrate
        const rect = canvasRef.current?.getBoundingClientRect();
        if (rect) {
          const mx = e.clientX - rect.left;
          const my = e.clientY - rect.top;

          // Site D: handleMouseDown hit-test normalization — consolidated via getNormalization()
          const norm = getNormalization(parseBounds(drawing?.metadata?.render_bounds));
          const isOldDrawing = oldDrawing && drawing?.id === oldDrawing.id;

          let clickedViolationId: string | null = null;
          if (showViolations) {
            for (const v of violations) {
              const coords = isOldDrawing ? v.ref_coordinates : v.coordinates;
              if (!coords) continue;
              const [vx, raw_vy] = coords;
              // worldToScreen applies Y-flip when hasBounds — same as original hasBounds block
              const screenPos = worldToScreen(vx, raw_vy, norm, viewport);
              const sx = screenPos.x;
              const sy = screenPos.y;

              // Reduced detection radius from 24 to 12 for seamless navigation without blocking drags
              if (Math.hypot(mx - sx, my - sy) <= 12) {
                clickedViolationId = v.id;
                break;
              }
            }
          }

          if (clickedViolationId) {
            const markerItem = violations.find(v => v.id === clickedViolationId);
            if (markerItem) {
              setDragMarkerId(clickedViolationId);
              setDragMarkerStartPos(isOldDrawing ? markerItem.ref_coordinates : markerItem.coordinates);
              setDragMarkerOriginalCoords({
                coordinates: markerItem.coordinates ? [...markerItem.coordinates] : undefined,
                ref_coordinates: markerItem.ref_coordinates ? [...markerItem.ref_coordinates] : undefined
              });
              setDragMarkerMouseStart({ x: e.clientX, y: e.clientY });
              setHasDragMarkerMoved(false);
            }
            return;
          }
        }

        if (isRoiEditModeEnabled && hoveredHandleInfo) {
          setActiveDragHandle({
            regionKey: hoveredHandleInfo.regionKey,
            handleId: hoveredHandleInfo.handleId as any
          });

          if (hoveredHandleInfo.handleId === 'center') {
            const rect = canvasRef.current?.getBoundingClientRect();
            if (rect && drawing?.metadata?.render_bounds) {
              const mx = e.clientX - rect.left;
              const my = e.clientY - rect.top;

              // Site E: ROI center drag — NO Y-flip (percentage-space, Y-axis not inverted here)
              // We use screenToWorld but with no Y-flip by passing norm with hasBounds=false semantics,
              // because the ROI percentages are computed in raw canvas space not CAD-flipped space.
              const norm = getNormalization(parseBounds(drawing?.metadata?.render_bounds));
              const effectiveScale = viewport.scale * norm.normScale;
              const worldX = norm.xmin + (mx - viewport.x) / effectiveScale;
              const worldY = norm.ymin + (my - viewport.y) / effectiveScale;

              const [rxMin, ryMin, rxMax, ryMax] = drawing.metadata.render_bounds;
              const w = rxMax - rxMin;
              const h = ryMax - ryMin;

              const pctX = (worldX - rxMin) / w;
              const pctY = (worldY - ryMin) / h;

              const current = customRegions[hoveredHandleInfo.regionKey];
              if (current) {
                setCenterDragStart({
                  pctX,
                  pctY,
                  originalXMin: current.xMin,
                  originalXMax: current.xMax,
                  originalYMin: current.yMin,
                  originalYMax: current.yMax
                });
              }
            }
          }
        } else {
          setIsDragging(true);
          setDragStart({ x: e.clientX - viewport.x, y: e.clientY - viewport.y });
        }
      }
    };

    const handleMouseMove = (e: React.MouseEvent) => {
      const rect = canvasRef.current?.getBoundingClientRect();
      if (!rect) return;

      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;

      setMouseCoords({ x: mx, y: my });

      // Calculate standardized hover coordinates to synchronize with the other viewport!
      // Site F: sign-inverted Y (laser-sync convention — NOT screenToWorld). Keep inline.
      // See coordinateTransform.test.ts "Site F" test for documentation of this behavioral difference.
      const norm = getNormalization(parseBounds(drawing?.metadata?.render_bounds));
      const effectiveScale = viewport.scale * norm.normScale;
      const stdX = norm.xmin + (mx - viewport.x) / effectiveScale;
      const stdY = norm.ymin - (my - viewport.y) / effectiveScale; // intentional sign inversion for laser-sync

      if (dragMarkerId && dragMarkerStartPos) {
        const deltaX = (e.clientX - dragMarkerMouseStart.x) / effectiveScale;
        let hasBounds = false;
        if (drawing?.metadata?.render_bounds) {
          hasBounds = true;
        }
        const deltaY = (e.clientY - dragMarkerMouseStart.y) / effectiveScale;
        const adjustedDeltaY = hasBounds ? -deltaY : deltaY;

        const newX = dragMarkerStartPos[0] + deltaX;
        const newY = dragMarkerStartPos[1] + adjustedDeltaY;

        if (Math.hypot(e.clientX - dragMarkerMouseStart.x, e.clientY - dragMarkerMouseStart.y) > 3) {
          setHasDragMarkerMoved(true);
        }

        const isOldDrawing = oldDrawing && drawing?.id === oldDrawing.id;
        const currentViolations = useWorkspaceStore.getState().violations;
        useWorkspaceStore.setState({
          violations: currentViolations.map(v => {
            if (v.id === dragMarkerId) {
              return isOldDrawing
                ? { ...v, ref_coordinates: [newX, newY] as [number, number] }
                : { ...v, coordinates: [newX, newY] as [number, number] };
            }
            return v;
          })
        });
        return;
      }



      let isHoveringMarker = false;
      let hoveredMId: string | null = null;
      if (showViolations) {
        const isOldDrawing = oldDrawing && drawing?.id === oldDrawing.id;
        // norm is already computed above in the Site F block for laser-sync
        const getPriority = (penType: string) => {
          if (penType === 'ai_red' || penType === 'checker_blue') return 3;
          if (penType === 'ai_orange') return 2;
          return 1;
        };

        const sortedViolations = [...violations].sort((a, b) => {
          return getPriority(b.pen_type || 'ai_red') - getPriority(a.pen_type || 'ai_red');
        });

        for (const v of sortedViolations) {
          // Skip sheet isolation violations to match rendering logic!
          if (isOldDrawing && v.pen_type === 'checker_blue') continue;
          if (!isOldDrawing && v.pen_type === 'ai_red') continue;

          const coords = isOldDrawing ? v.ref_coordinates : v.coordinates;
          if (!coords) continue;
          const [vx, raw_vy] = coords;
          // Prefer cached markerPositionsRef (written by renderViolationReticles) for accuracy.
          // Fall back to worldToScreen only when the ref isn't populated yet (first frame).
          const pos = markerPositionsRef.current[v.id];
          const screenPos = pos ?? worldToScreen(vx, raw_vy, norm, viewport);
          const sx = screenPos.x;
          const sy = screenPos.y;

          // Reduced detection radius from 18 to 12 for seamless hover transition
          if (Math.hypot(mx - sx, my - sy) <= 12) {
            isHoveringMarker = true;
            hoveredMId = v.id;
            break;
          }
        }
      }
      setIsHoveringMarkerState(isHoveringMarker);
      setHoveredMarkerId(hoveredMId);

      if (isLaserSyncEnabled) {
        setHoveredCoords({ x: stdX, y: stdY });
      } else if (hoveredCoords !== null) {
        setHoveredCoords(null);
      }

      // ROI Drag Handle interaction
      if (isRoiEditModeEnabled && selectedComparisonRegion && drawing?.metadata?.render_bounds) {
        const [rxMin, ryMin, rxMax, ryMax] = drawing.metadata.render_bounds;
        const w = rxMax - rxMin;
        const h = ryMax - ryMin;
        const regionKey = selectedComparisonRegion;
        const customReg = customRegions[regionKey];

        if (customReg) {
          // Use norm from Site F block above — xmin/ymin/effectiveScale all derived from it
          const screenXMin = (rxMin + w * customReg.xMin - norm.xmin) * effectiveScale + viewport.x;
          const screenXMax = (rxMin + w * customReg.xMax - norm.xmin) * effectiveScale + viewport.x;
          const screenYMin = (ryMin + h * customReg.yMin - norm.ymin) * effectiveScale + viewport.y;
          const screenYMax = (ryMin + h * customReg.yMax - norm.ymin) * effectiveScale + viewport.y;

          const handles = [
            { id: 'top-left', x: screenXMin, y: screenYMin, cursor: 'nwse-resize' },
            { id: 'top-right', x: screenXMax, y: screenYMin, cursor: 'nesw-resize' },
            { id: 'bottom-left', x: screenXMin, y: screenYMax, cursor: 'nesw-resize' },
            { id: 'bottom-right', x: screenXMax, y: screenYMax, cursor: 'nwse-resize' }
          ];

          const hovered = handles.find(hd => Math.hypot(mx - hd.x, my - hd.y) <= 12);
          if (hovered) {
            setHoveredHandleInfo({
              regionKey,
              handleId: hovered.id,
              cursor: hovered.cursor
            });
          } else {
            // If not hovering corners, check if we are hovering inside the selected region box!
            if (mx >= screenXMin && mx <= screenXMax && my >= screenYMin && my <= screenYMax) {
              setHoveredHandleInfo({
                regionKey,
                handleId: 'center',
                cursor: 'move'
              });
            } else {
              setHoveredHandleInfo(null);
            }
          }
        }
      } else {
        if (hoveredHandleInfo) setHoveredHandleInfo(null);
      }

      if (activeDragHandle && drawing?.metadata?.render_bounds) {
        const [rxMin, ryMin, rxMax, ryMax] = drawing.metadata.render_bounds;
        const w = rxMax - rxMin;
        const h = ryMax - ryMin;

        const worldX = norm.xmin + (mx - viewport.x) / effectiveScale;
        const worldY = norm.ymin + (my - viewport.y) / effectiveScale;

        const pctX = Math.max(0.0, Math.min(1.0, (worldX - rxMin) / w));
        const pctY = Math.max(0.0, Math.min(1.0, (worldY - ryMin) / h));

        const currentBounds = { ...customRegions[activeDragHandle.regionKey] };

        if (activeDragHandle.handleId === 'center' && centerDragStart) {
          const deltaPctX = pctX - centerDragStart.pctX;
          const deltaPctY = pctY - centerDragStart.pctY;

          const boxW = centerDragStart.originalXMax - centerDragStart.originalXMin;
          const boxH = centerDragStart.originalYMax - centerDragStart.originalYMin;

          // Apply shift with boundaries clamped to [0.0, 1.0]
          let newXMin = centerDragStart.originalXMin + deltaPctX;
          let newXMax = centerDragStart.originalXMax + deltaPctX;
          let newYMin = centerDragStart.originalYMin + deltaPctY;
          let newYMax = centerDragStart.originalYMax + deltaPctY;

          if (newXMin < 0) {
            newXMin = 0;
            newXMax = boxW;
          } else if (newXMax > 1) {
            newXMax = 1;
            newXMin = 1 - boxW;
          }

          if (newYMin < 0) {
            newYMin = 0;
            newYMax = boxH;
          } else if (newYMax > 1) {
            newYMax = 1;
            newYMin = 1 - boxH;
          }

          currentBounds.xMin = newXMin;
          currentBounds.xMax = newXMax;
          currentBounds.yMin = newYMin;
          currentBounds.yMax = newYMax;
        } else if (activeDragHandle.handleId === 'top-left') {
          currentBounds.xMin = Math.min(pctX, currentBounds.xMax - 0.02);
          currentBounds.yMin = Math.min(pctY, currentBounds.yMax - 0.02);
        } else if (activeDragHandle.handleId === 'top-right') {
          currentBounds.xMax = Math.max(pctX, currentBounds.xMin + 0.02);
          currentBounds.yMin = Math.min(pctY, currentBounds.yMax - 0.02);
        } else if (activeDragHandle.handleId === 'bottom-left') {
          currentBounds.xMin = Math.min(pctX, currentBounds.xMax - 0.02);
          currentBounds.yMax = Math.max(pctY, currentBounds.yMin + 0.02);
        } else if (activeDragHandle.handleId === 'bottom-right') {
          currentBounds.xMax = Math.max(pctX, currentBounds.xMin + 0.02);
          currentBounds.yMax = Math.max(pctY, currentBounds.yMin + 0.02);
        }

        updateCustomRegion(activeDragHandle.regionKey, currentBounds);
        setRedrawTrigger(prev => prev + 1);
      } else if (isDragging) {
        const newX = e.clientX - dragStart.x;
        const newY = e.clientY - dragStart.y;
        setViewport({ ...viewport, x: newX, y: newY });
        if (e.buttons === 2) {
          setPreventNextContextMenu(true);
        }
      }
    };

    const handleMouseUp = (e: React.MouseEvent) => {
      setIsDragging(false);
      setActiveDragHandle(null);
      setCenterDragStart(null);

      if (dragMarkerId) {
        if (!hasDragMarkerMoved) {
          const currentViolations = useWorkspaceStore.getState().violations;
          const markerToDelete = currentViolations.find(v => v.id === dragMarkerId);
          if (markerToDelete) {
            if (e.altKey) {
              // Alt + Click deletes the marker (matching the tooltip instructions!)
              useWorkspaceStore.getState().pushDeletedViolation(markerToDelete);
              useWorkspaceStore.setState({
                violations: currentViolations.filter(v => v.id !== dragMarkerId),
                selectedViolation: selectedViolation?.id === dragMarkerId ? null : selectedViolation
              });
            } else {
              // Standard Left-click selects the violation instead of deleting it!
              selectViolation(markerToDelete);
            }
          }
        } else {
          const currentViolations = useWorkspaceStore.getState().violations;
          const markerItem = currentViolations.find(v => v.id === dragMarkerId);
          if (markerItem && dragMarkerOriginalCoords) {
            const coordsChanged =
              markerItem.coordinates?.[0] !== dragMarkerOriginalCoords.coordinates?.[0] ||
              markerItem.coordinates?.[1] !== dragMarkerOriginalCoords.coordinates?.[1] ||
              markerItem.ref_coordinates?.[0] !== dragMarkerOriginalCoords.ref_coordinates?.[0] ||
              markerItem.ref_coordinates?.[1] !== dragMarkerOriginalCoords.ref_coordinates?.[1];

            if (coordsChanged) {
              useWorkspaceStore.getState().pushUndoAction({
                type: "move",
                violationId: dragMarkerId,
                oldCoords: dragMarkerOriginalCoords.coordinates,
                newCoords: markerItem.coordinates,
                oldRefCoords: dragMarkerOriginalCoords.ref_coordinates,
                newRefCoords: markerItem.ref_coordinates
              });
            }
          }
        }
        setDragMarkerId(null);
        setDragMarkerStartPos(null);
        setDragMarkerOriginalCoords(null);
      }
    };

    const handleMouseLeave = () => {
      setIsDragging(false);
      setActiveDragHandle(null);
      setCenterDragStart(null);
      setMouseCoords(null);
      setHoveredCoords(null);
      setHoveredHandleInfo(null);
      setIsHoveringMarkerState(false);
      setDragMarkerId(null);
      setDragMarkerStartPos(null);
      setHoveredMarkerId(null);
    };

    const handleContextMenu = (e: React.MouseEvent) => {
      e.preventDefault();
      if (preventNextContextMenu) {
        setPreventNextContextMenu(false);
        return;
      }
      const rect = canvasRef.current?.getBoundingClientRect();
      if (!rect) return;

      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;

      // Site G: handleContextMenu normalization — consolidated via getNormalization() + screenToWorld()
      const norm = getNormalization(parseBounds(drawing?.metadata?.render_bounds));
      const effectiveScale = viewport.scale * norm.normScale;
      // wx is raw screen-to-world X (no Y-flip needed for wx)
      const wx = norm.xmin + (mx - viewport.x) / effectiveScale;
      // screenToWorld applies the Y-flip: matches original hasBounds ? (yMax + yMin - wy_screen) : wy_screen
      const worldPos = screenToWorld(mx, my, norm, viewport);
      const wy = worldPos.y;

      // Shift menu slightly if too close to right/bottom edges to fit cleanly
      let menuX = mx;
      let menuY = my;
      const menuWidth = 190;
      const menuHeight = 120;
      if (mx + menuWidth > width) {
        menuX = mx - menuWidth;
      }
      if (my + menuHeight > height) {
        menuY = my - menuHeight;
      }

      setContextMenu({
        visible: true,
        x: menuX,
        y: menuY,
        wx,
        wy
      });
    };

    return (
      <div style={{ position: 'relative', width: '100%', height: '100%', overflow: 'hidden' }}>
        <canvas
          ref={canvasRef}
          width={width * dpr}
          height={height * dpr}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseLeave}
          onContextMenu={handleContextMenu}
          style={{
            cursor: isSpacePressed
              ? (isDragging ? 'grabbing' : 'grab')
              : activeDragHandle
                ? (activeDragHandle.handleId === 'top-left' || activeDragHandle.handleId === 'bottom-right' ? 'nwse-resize' : 'nesw-resize')
                : hoveredHandleInfo
                  ? (hoveredHandleInfo.cursor as any)
                  : isHoveringMarkerState
                    ? 'pointer'
                    : isDragging
                      ? 'grabbing'
                      : 'grab',
            display: 'block',
            width: '100%',
            height: '100%'
          }}
        />

        {contextMenu && (
          <div
            className="custom-context-menu"
            style={{
              position: 'absolute',
              left: contextMenu.x,
              top: contextMenu.y,
            }}
            onMouseDown={(e) => e.stopPropagation()}
            onClick={(e) => e.stopPropagation()}
          >
            <div
              className="context-menu-item"
              onClick={() => {
                toggleMarkerLabels();
                setContextMenu(null);
              }}
            >
              {showMarkerLabels ? "🏷 Hide Labels" : "🏷 Show Labels"}
            </div>
            <div
              className={`context-menu-item ${useWorkspaceStore.getState().deletedViolationsStack.length === 0 ? "disabled" : ""}`}
              onClick={() => {
                useWorkspaceStore.getState().popAndRestoreViolation();
                setContextMenu(null);
              }}
            >
              <span>↩ Undo Delete</span>
              {useWorkspaceStore.getState().deletedViolationsStack.length > 0 && (
                <span style={{ fontSize: '0.65rem', background: 'rgba(255,255,255,0.1)', padding: '1px 5px', borderRadius: '4px', marginLeft: '6px' }}>
                  {useWorkspaceStore.getState().deletedViolationsStack.length}
                </span>
              )}
            </div>
            <div style={{ borderBottom: '1px solid rgba(255,255,255,0.08)', margin: '4px 0' }} />
            <div style={{ padding: '4px 14px', fontSize: '0.65rem', textTransform: 'uppercase', letterSpacing: '0.05em', color: '#71717a', fontWeight: 600 }}>Filter Markers</div>
            {[
              { label: "🔴 MISMATCHED", key: "MISMATCHED" },
              { label: "🟠 CHANGED", key: "CHANGED" },
              { label: "🔵 ADDED", key: "ADDED" },
              { label: "🟢 MATCHED", key: "MATCHED" }
            ].map((item) => (
              <div
                key={item.key}
                className="context-menu-item"
                style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '6px 14px' }}
                onClick={() => {
                  toggleMarkerTypeVisibility(item.key);
                  setRedrawTrigger(prev => prev + 1);
                }}
              >
                <span style={{ display: 'flex', alignItems: 'center', gap: '8px', pointerEvents: 'none' }}>
                  <input
                    type="checkbox"
                    checked={visibleMarkerTypes[item.key] ?? false}
                    onChange={() => { }}
                    style={{ cursor: 'pointer', accentColor: '#00e5ff' }}
                  />
                  <span>{item.label}</span>
                </span>
              </div>
            ))}
            <div style={{ borderBottom: '1px solid rgba(255,255,255,0.08)', margin: '4px 0' }} />
            <div className="context-menu-item has-submenu">
              <span>➕ Add Marker</span>
              <span style={{ fontSize: '0.6rem', opacity: 0.6 }}>▶</span>
              <div className="context-submenu">
                {[
                  { label: "🟢 MATCHED", type: "ai_green", isResolved: true, status: "MATCHED" },
                  { label: "🔴 MISMATCHED", type: "ai_red", isResolved: false, status: "MISMATCHED" },
                  { label: "🟠 CHANGE", type: "ai_orange", isResolved: false, status: "CHANGED" },
                  { label: "🔵 ADDED", type: "checker_blue", isResolved: false, status: "ADDED" }
                ].map((opt) => (
                  <div
                    key={opt.label}
                    className="context-menu-item"
                    onClick={() => {
                      // Add new marker at click coordinates wx, wy
                      // Populating BOTH coordinates and ref_coordinates to sync on both drawings!
                      const newMarker: any = {
                        id: `custom_marker_${Date.now()}`,
                        severity: opt.status === "MATCHED" ? "low" : "high",
                        category: "Manual Marker",
                        description: "Manually added marker",
                        recommendation: "Manual verification check",
                        affected_entities: [],
                        confidence: 1.0,
                        coordinates: [contextMenu.wx, contextMenu.wy],
                        ref_coordinates: [contextMenu.wx, contextMenu.wy],
                        pen_type: opt.type,
                        is_resolved: opt.isResolved,
                        status: opt.status
                      };
                      const current = useWorkspaceStore.getState().violations;
                      useWorkspaceStore.setState({
                        violations: [...current, newMarker]
                      });
                      setContextMenu(null);
                    }}
                  >
                    {opt.label}
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Floating CAD Compass & Navigation HUD Overlay (Top Right) */}
        <div
          style={{
            position: 'absolute',
            top: 12,
            right: 12,
            background: theme === 'hc-light' ? 'rgba(255, 255, 255, 0.85)' : 'rgba(9, 9, 11, 0.75)',
            backdropFilter: 'blur(12px)',
            border: theme === 'hc-light' ? '1px solid rgba(228, 228, 231, 0.8)' : '1px solid rgba(63, 63, 70, 0.4)',
            padding: '10px 14px',
            borderRadius: '10px',
            fontFamily: 'sans-serif',
            color: theme === 'hc-light' ? '#3f3f46' : '#e4e4e7',
            display: 'flex',
            alignItems: 'center',
            gap: '14px',
            boxShadow: theme === 'hc-light' ? '0 4px 20px rgba(0, 0, 0, 0.08)' : '0 4px 20px rgba(0, 0, 0, 0.4)',
            pointerEvents: 'none',
            userSelect: 'none',
            transition: 'all 0.3s ease'
          }}
        >
          {/* Animated Cyber Dial */}
          <div style={{ position: 'relative', width: '36px', height: '36px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <svg width="36" height="36" viewBox="0 0 36 36" style={{ transform: `rotate(${(viewport.x + viewport.y) * 0.05}deg)`, transition: 'transform 0.1s linear' }}>
              <circle cx="18" cy="18" r="16" fill="none" stroke={theme === 'hc-light' ? 'rgba(0, 0, 0, 0.08)' : 'rgba(255, 255, 255, 0.08)'} strokeWidth="1.5" />
              <circle cx="18" cy="18" r="16" fill="none" stroke={isNeonCAD ? "#00ffcc" : (theme === 'hc-light' ? '#0ea5e9' : '#00e5ff')} strokeWidth="1.5" strokeDasharray="8, 6" />
              <line x1="18" y1="2" x2="18" y2="8" stroke={isNeonCAD ? "#00ffcc" : (theme === 'hc-light' ? '#0ea5e9' : '#00e5ff')} strokeWidth="1.5" />
              <line x1="18" y1="28" x2="18" y2="34" stroke={theme === 'hc-light' ? 'rgba(0, 0, 0, 0.2)' : 'rgba(255, 255, 255, 0.2)'} strokeWidth="1.5" />
              <line x1="2" y1="18" x2="8" y2="18" stroke={theme === 'hc-light' ? 'rgba(0, 0, 0, 0.2)' : 'rgba(255, 255, 255, 0.2)'} strokeWidth="1.5" />
              <line x1="28" y1="18" x2="34" y2="18" stroke={theme === 'hc-light' ? 'rgba(0, 0, 0, 0.2)' : 'rgba(255, 255, 255, 0.2)'} strokeWidth="1.5" />
            </svg>
            <div style={{
              position: 'absolute',
              width: '6px',
              height: '6px',
              borderRadius: '50%',
              backgroundColor: isNeonCAD ? '#00ffcc' : (theme === 'hc-light' ? '#0ea5e9' : '#00e5ff'),
              boxShadow: `0 0 8px ${isNeonCAD ? '#00ffcc' : (theme === 'hc-light' ? '#0ea5e9' : '#00e5ff')}`
            }} />
          </div>

          {/* Nav Stats */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
            <div style={{ fontSize: '0.65rem', textTransform: 'uppercase', letterSpacing: '0.05em', color: theme === 'hc-light' ? '#71717a' : '#a1a1aa', fontWeight: 600 }}>CAD Navigation HUD</div>
            <div style={{ fontFamily: 'monospace', fontSize: '0.7rem', display: 'flex', gap: '10px' }}>
              <span>X: <span style={{ color: isNeonCAD ? '#00ffcc' : (theme === 'hc-light' ? '#0ea5e9' : '#00e5ff') }}>{viewport.x.toFixed(0)}</span></span>
              <span>Y: <span style={{ color: isNeonCAD ? '#00ffcc' : (theme === 'hc-light' ? '#0ea5e9' : '#00e5ff') }}>{viewport.y.toFixed(0)}</span></span>
              <span>MAG: <span style={{ color: '#ec4899' }}>{viewport.scale.toFixed(2)}x</span></span>
            </div>
          </div>
        </div>

        {/* Floating Visual Quality Controller Panel (Bottom Right) */}
        <div
          style={{
            position: 'absolute',
            bottom: 12,
            right: 12,
            background: theme === 'hc-light' ? 'rgba(255, 255, 255, 0.85)' : 'rgba(9, 9, 11, 0.75)',
            backdropFilter: 'blur(12px)',
            border: theme === 'hc-light' ? '1px solid rgba(228, 228, 231, 0.8)' : '1px solid rgba(63, 63, 70, 0.4)',
            padding: '8px 12px',
            borderRadius: '10px',
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
            boxShadow: theme === 'hc-light' ? '0 4px 20px rgba(0, 0, 0, 0.08)' : '0 4px 20px rgba(0, 0, 0, 0.4)',
            userSelect: 'none',
            zIndex: 10
          }}
        >
          {/* Render Quality Badge */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1px' }}>
            <span style={{ fontSize: '0.55rem', color: theme === 'hc-light' ? '#a1a1aa' : '#71717a', textTransform: 'uppercase', fontWeight: 600 }}>Engine Mode</span>
            <span style={{ fontSize: '0.68rem', color: '#10b981', fontWeight: 500, display: 'flex', alignItems: 'center', gap: '4px' }}>
              <span style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: '#10b981', display: 'inline-block' }} />
              350 DPI High-Res
            </span>
          </div>

          <div style={{ width: '1px', height: '24px', backgroundColor: theme === 'hc-light' ? 'rgba(228, 228, 231, 1)' : 'rgba(63, 63, 70, 0.5)' }} />

          {/* Neon CAD Toggle Button */}
          <button
            onClick={() => {
              setIsNeonCAD(prev => !prev);
              setRedrawTrigger(prev => prev + 1);
            }}
            style={{
              background: isNeonCAD ? 'rgba(0, 255, 204, 0.12)' : (theme === 'hc-light' ? 'rgba(0, 0, 0, 0.03)' : 'rgba(255, 255, 255, 0.03)'),
              border: `1px solid ${isNeonCAD ? '#00ffcc' : (theme === 'hc-light' ? 'rgba(212, 212, 216, 0.8)' : 'rgba(63, 63, 70, 0.8)')}`,
              padding: '4px 10px',
              borderRadius: '6px',
              fontSize: '0.68rem',
              fontWeight: 600,
              color: isNeonCAD ? '#00ffcc' : (theme === 'hc-light' ? '#71717a' : '#a1a1aa'),
              cursor: 'pointer',
              transition: 'all 0.2s cubic-bezier(0.4, 0, 0.2, 1)',
              outline: 'none',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              boxShadow: isNeonCAD ? '0 0 10px rgba(0, 255, 204, 0.25)' : 'none'
            }}
            onMouseEnter={(e) => {
              if (!isNeonCAD) e.currentTarget.style.borderColor = theme === 'hc-light' ? 'rgba(161, 161, 170, 0.8)' : 'rgba(255, 255, 255, 0.3)';
            }}
            onMouseLeave={(e) => {
              if (!isNeonCAD) e.currentTarget.style.borderColor = theme === 'hc-light' ? 'rgba(212, 212, 216, 0.8)' : 'rgba(63, 63, 70, 0.8)';
            }}
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" />
            </svg>
            NEON GLOW
          </button>
        </div>

        {/* High-Fidelity HUD Engineering Diagnostics Overlay (Bottom Left) */}
        <div
          style={{
            position: 'absolute',
            bottom: 12,
            left: 12,
            background: theme === 'hc-light' ? 'rgba(255, 255, 255, 0.85)' : 'rgba(9, 9, 11, 0.75)',
            backdropFilter: 'blur(12px)',
            border: theme === 'hc-light' ? '1px solid rgba(228, 228, 231, 0.8)' : '1px solid rgba(63, 63, 70, 0.4)',
            padding: '8px 12px',
            borderRadius: '10px',
            fontFamily: 'monospace',
            fontSize: '0.62rem',
            color: theme === 'hc-light' ? '#71717a' : '#a1a1aa',
            display: 'flex',
            gap: '12px',
            pointerEvents: 'none',
            boxShadow: theme === 'hc-light' ? '0 4px 20px rgba(0, 0, 0, 0.08)' : '0 4px 20px rgba(0, 0, 0, 0.4)'
          }}
        >
          <div>ZOOM: <span style={{ color: '#00e5ff', fontWeight: 600 }}>{(viewport.scale * 100).toFixed(0)}%</span></div>
          <div>VIRTUALIZED: <span style={{ color: '#10b981', fontWeight: 600 }}>{renderDiagnostics.drawCount}/{renderDiagnostics.entityCount}</span></div>
          <div>RENDER: <span style={{ color: '#eab308', fontWeight: 600 }}>{renderDiagnostics.renderTimeMs}ms</span></div>
        </div>

        <style>{`
        .custom-context-menu {
          position: absolute;
          background: rgba(18, 18, 24, 0.95);
          backdrop-filter: blur(12px);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 8px;
          padding: 6px 0;
          min-width: 190px;
          z-index: 10000;
          box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
          display: flex;
          flex-direction: column;
        }

        .context-menu-item {
          padding: 8px 14px;
          font-size: 0.8rem;
          color: #e4e4e7;
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: space-between;
          transition: background 0.15s ease, color 0.15s ease;
          position: relative;
        }

        .context-menu-item:hover {
          background: rgba(0, 229, 255, 0.1);
          color: var(--accent-cyan);
        }

        .context-menu-item.disabled {
          color: #52525b;
          pointer-events: none;
          opacity: 0.5;
        }

        .context-submenu {
          position: absolute;
          left: 100%;
          top: 0;
          background: rgba(18, 18, 24, 0.98);
          backdrop-filter: blur(12px);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 8px;
          padding: 6px 0;
          min-width: 145px;
          display: none;
          box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
        }

        .context-menu-item.has-submenu:hover .context-submenu {
          display: flex;
          flex-direction: column;
        }
      `}</style>
      </div>
    );
  });
