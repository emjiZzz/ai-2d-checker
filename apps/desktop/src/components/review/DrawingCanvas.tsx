import React, { useEffect, useRef, useState, useCallback } from 'react';
import { useReviewStore } from '../../stores/reviewStore';
import { useWorkspaceStore } from '../../stores/workspaceStore';
import { useConnectionStore } from '../../stores/connectionStore';
import { useThemeStore } from '../../stores/themeStore';

// Helper utility to strip any residual AutoCAD MTEXT formatting/styling tags
// NOTE: Primary cleaning is done on the backend in entity_mapper.py
// This is only a lightweight safety pass for any codes that slip through
const cleanCadText = (text: string): string => {
  if (!text) return "";
  let clean = text;
  // Strip grouping braces {...}
  clean = clean.replace(/[{}]/g, "");
  // Strip AutoCAD backslash formatting tags (e.g., \A1;, \W0.85;, \C7;)
  // Uses \\ prefix to avoid matching Unicode/Japanese characters
  clean = clean.replace(/\\[A-Za-z][^;]*;/g, "");
  // Convert CAD paragraph breaks \P to spaces
  clean = clean.replace(/\\P/g, " ");
  return clean.trim();
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

export const DrawingCanvas: React.FC<DrawingCanvasProps> = ({ layers, width, height, drawing }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const dpr = typeof window !== 'undefined' ? window.devicePixelRatio || 1 : 1;
  
  // Connect stores
  const { viewport, setViewport, activeLayers, showViolations, hoveredCoords, setHoveredCoords } = useReviewStore();
  const selectedViolation = useWorkspaceStore((s) => s.selectedViolation);
  const selectViolation = useWorkspaceStore((s) => s.selectViolation);
  const violations = useWorkspaceStore((s) => s.violations);
  const theme = useThemeStore((s) => s.theme);
 
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const [mouseCoords, setMouseCoords] = useState<{ x: number, y: number } | null>(null);
  const [isNeonCAD, setIsNeonCAD] = useState(false);
  const [renderDiagnostics, setRenderDiagnostics] = useState({ entityCount: 0, drawCount: 0, renderTimeMs: 0 });
  const [redrawTrigger, setRedrawTrigger] = useState(0);

  // Connect background raster image for high-fidelity rendering parity
  const [bgImage, setBgImage] = useState<HTMLImageElement | null>(null);
  const [lightBgImage, setLightBgImage] = useState<HTMLImageElement | null>(null);

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
            // Generate a perfectly color-matched light mode variant by ONLY inverting grayscale (white/black) pixels!
            // This leaves all colored dimensions (green, yellow, blue) EXACTLY as they are in the original CAD.
            const canvas = document.createElement('canvas');
            canvas.width = img.width;
            canvas.height = img.height;
            const context = canvas.getContext('2d');
            if (context) {
              context.drawImage(img, 0, 0);
              const imgData = context.getImageData(0, 0, canvas.width, canvas.height);
              const data = imgData.data;
              for (let i = 0; i < data.length; i += 4) {
                if (data[i+3] === 0) continue; // Skip fully transparent
                const r = data[i], g = data[i+1], b = data[i+2];
                // Check if pixel is grayscale (very low saturation)
                if (Math.max(r, g, b) - Math.min(r, g, b) < 25) {
                  data[i] = 255 - r;
                  data[i+1] = 255 - g;
                  data[i+2] = 255 - b;
                }
              }
              context.putImageData(imgData, 0, 0);
              const lightImg = new Image();
              lightImg.src = canvas.toDataURL();
              setLightBgImage(lightImg);
            }

            setBgImage(img);
            // Request state redraw cycle
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

  // Redraw logic
  const drawCanvas = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
 
    const dpr = typeof window !== 'undefined' ? window.devicePixelRatio || 1 : 1;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    
    // Enable high-quality image smoothing for scaling high-res drawings beautifully!
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = 'high';
 
    const startTime = performance.now();

    // Compute normalization scale and translation offset to unify coordinate bounds
    let normalizationScale = 1;
    let normXMin = 0;
    let normYMin = 0;
    
    if (drawing?.metadata?.render_bounds) {
      const [xmin, ymin, xmax] = drawing.metadata.render_bounds;
      const boundsWidth = xmax - xmin;
      if (boundsWidth > 0) {
        normalizationScale = 1000 / boundsWidth;
        normXMin = xmin;
        normYMin = ymin;
      }
    }
    
    const effectiveScale = viewport.scale * normalizationScale;
    
    // 1. Clear infinite background
    ctx.fillStyle = theme === 'hc-light' ? '#f4f4f5' : '#09090b'; 
    ctx.fillRect(0, 0, width, height);

    // 2. Draw fine engineering grids aligned to raw CAD space (rendered in screen-space for pixel-crisp lines)
    ctx.save();
    
    // Choose theme-based styling (perfect grey/zinc engineering aesthetics)
    ctx.strokeStyle = theme === 'hc-light' ? 'rgba(9, 9, 11, 0.08)' : 'rgba(63, 63, 70, 0.25)'; 
    ctx.lineWidth = 1; // 1px pixel-crisp lines
    
    const targetScreenSpacing = 50; // Tighter grid spacing for professional engineering look
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

    // Draw vertical grid lines
    const kStartX = Math.floor((0 - screenOriginX) / screenSpacing);
    const kEndX = Math.ceil((width - screenOriginX) / screenSpacing);
    for (let k = kStartX; k <= kEndX; k++) {
      const sx = Math.round(screenOriginX + k * screenSpacing);
      ctx.beginPath();
      ctx.moveTo(sx, 0);
      ctx.lineTo(sx, height);
      ctx.stroke();
    }

    // Draw horizontal grid lines
    const kStartY = Math.floor((0 - screenOriginY) / screenSpacing);
    const kEndY = Math.ceil((height - screenOriginY) / screenSpacing);
    for (let k = kStartY; k <= kEndY; k++) {
      const sy = Math.round(screenOriginY + k * screenSpacing);
      ctx.beginPath();
      ctx.moveTo(0, sy);
      ctx.lineTo(width, sy);
      ctx.stroke();
    }

    ctx.restore();
 
    // 3. Setup transformations (apply normalization!)
    ctx.save();
    ctx.translate(viewport.x, viewport.y);
    ctx.scale(effectiveScale, effectiveScale);
    ctx.translate(-normXMin, -normYMin);
 
    let currentFilter = "none";
    if (isNeonCAD) {
      currentFilter = "contrast(1.25) brightness(1.15) saturate(1.35) hue-rotate(2deg)";
    }
    ctx.filter = currentFilter;

    // Draw high-fidelity raster CAD background image if loaded, aligned exactly to CAD coordinates bounds
    const targetImage = theme === 'hc-light' ? lightBgImage : bgImage;
    if (targetImage && drawing?.metadata?.render_bounds) {
      const [xmin, ymin, xmax, ymax] = drawing.metadata.render_bounds;
      ctx.drawImage(targetImage, xmin, ymin, xmax - xmin, ymax - ymin);
    }
 
    // 4. Viewport bounds in world coordinates (for culling virtualization)
    const minX = normXMin - viewport.x / effectiveScale;
    const minY = normYMin - viewport.y / effectiveScale;
    const maxX = normXMin + (width - viewport.x) / effectiveScale;
    const maxY = normYMin + (height - viewport.y) / effectiveScale;

    let totalEntities = 0;
    let drawnEntities = 0;

    // 5. Draw entity layers
    // To prevent massive lag when drawing 40,000+ fallback vectors, we BATCH draw calls by stroke style!
    const pathBatches: Record<string, { stroke: string, width: number, path: Path2D }> = {};

    Object.entries(layers).forEach(([layerName, entities]) => {
      // Respect layer controls
      if (activeLayers[layerName] === false) return;

      entities.forEach((ent) => {
        totalEntities++;
        
        // If we have successfully drawn the background raster image, we bypass redundant vector drawing!
        if (bgImage && drawing?.metadata?.render_bounds) {
          return;
        }
        
        const geo = ent.geometry;
        if (!geo) return;

        let strokeColor = ent.style?.stroke || ent.properties?.stroke || '#00e5ff';
        if (theme === 'hc-light') {
          const lowerColor = strokeColor.toLowerCase();
          if (lowerColor === '#ffffff' || lowerColor === '#fff') strokeColor = '#18181b';
          if (lowerColor === '#00e5ff') strokeColor = '#0ea5e9';
        }
        const strokeWidth = ent.style?.strokeWidth || ent.properties?.strokeWidth || 1;
        const batchKey = `${strokeColor}_${strokeWidth}`;

        // Text is drawn directly since it requires complex sub-pixel dpr matrix scaling and cannot use Path2D
        if (ent.type === 'text' && (geo.location || geo.insert)) {
          const [tx, ty] = geo.location || geo.insert;
          
          const screenX = tx * effectiveScale + viewport.x;
          const screenY = ty * effectiveScale + viewport.y;
          const baseHeight = ent.properties?.height || ent.style?.fontSize || 12;
          const screenHeight = baseHeight * effectiveScale * 1.0;

          if (screenHeight < 4) return;
          if (screenX < -500 || screenX > width + 500 || screenY < -500 || screenY > height + 500) return;

          drawnEntities++;
          
          ctx.save();
          ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
          
          let textColor = ent.style?.stroke || ent.style?.fill || '#ffffff';
          if (theme === 'hc-light') {
            const lowerColor = textColor.toLowerCase();
            if (lowerColor === '#ffffff' || lowerColor === '#fff') textColor = '#18181b';
            if (lowerColor === '#00e5ff') textColor = '#0ea5e9';
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

        // Initialize Path2D batch if needed
        if (!pathBatches[batchKey]) {
          pathBatches[batchKey] = { stroke: strokeColor, width: strokeWidth as number, path: new Path2D() };
        }
        const p2d = pathBatches[batchKey].path;

        // Viewport Virtualization & Culling based on geometry types
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
          // Math.cos/sin ensures the path accurately connects to the start of the arc
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

    // Fire a single consolidated stroke call per unique color/thickness batch!
    Object.values(pathBatches).forEach(batch => {
      ctx.beginPath();
      ctx.strokeStyle = batch.stroke;
      ctx.lineWidth = batch.width / viewport.scale;
      ctx.stroke(batch.path);
    });

    // 6. Draw compliance violations reticles if active
    ctx.filter = 'none'; // Ensure UI/overlay elements are never inverted or contrast-altered
    if (showViolations) {
      violations.forEach((v) => {
        if (!v.coordinates) return;
        const [vx, vy] = v.coordinates;
        const radius = 24 / effectiveScale;
        const penType = v.pen_type || 'ai_red';
        const isSelected = selectedViolation?.id === v.id;
 
        ctx.save();
        
        if (penType === 'ai_green') {
          // AI Green: Soft semi-transparent green outline / halo
          ctx.beginPath();
          ctx.fillStyle = 'rgba(16, 185, 129, 0.15)';
          ctx.strokeStyle = 'rgba(16, 185, 129, 0.6)';
          ctx.lineWidth = (isSelected ? 2.5 : 1.5) / effectiveScale;
          
          // Inner halo glow shadow
          ctx.shadowBlur = 12;
          ctx.shadowColor = '#10b981';
          
          ctx.arc(vx, vy, radius * 1.5, 0, 2 * Math.PI);
          ctx.fill();
          ctx.stroke();
          
          // Tiny green center checkmark tag or dot
          ctx.beginPath();
          ctx.fillStyle = '#10b981';
          ctx.arc(vx, vy, 4 / effectiveScale, 0, 2 * Math.PI);
          ctx.fill();
        } 
        else if (penType === 'ai_red') {
          // AI Red: Crimson Pin comment card
          ctx.beginPath();
          ctx.fillStyle = isSelected ? 'rgba(239, 68, 68, 0.2)' : 'rgba(239, 68, 68, 0.05)';
          ctx.strokeStyle = '#ef4444';
          ctx.lineWidth = (isSelected ? 3 : 2) / effectiveScale;
          ctx.arc(vx, vy, radius, 0, 2 * Math.PI);
          ctx.fill();
          ctx.stroke();
          
          // Draw red teardrop pin pointing to center
          const pinHeight = 24 / effectiveScale;
          const pinWidth = 12 / effectiveScale;
          ctx.beginPath();
          ctx.fillStyle = '#ef4444';
          ctx.strokeStyle = '#ffffff';
          ctx.lineWidth = 1 / effectiveScale;
          ctx.moveTo(vx, vy);
          ctx.bezierCurveTo(vx - pinWidth, vy - pinHeight/2, vx - pinWidth, vy - pinHeight, vx, vy - pinHeight);
          ctx.bezierCurveTo(vx + pinWidth, vy - pinHeight, vx + pinWidth, vy - pinHeight/2, vx, vy);
          ctx.fill();
          ctx.stroke();
          
          // White dot inside pin head
          ctx.beginPath();
          ctx.fillStyle = '#ffffff';
          ctx.arc(vx, vy - pinHeight * 0.7, 3 / effectiveScale, 0, 2 * Math.PI);
          ctx.fill();
        }
        else if (penType === 'checker_blue') {
          // Checker Blue: Indigo-blue thick reticle or solid pin dot representing the checker's blue pen markup
          ctx.beginPath();
          ctx.fillStyle = isSelected ? 'rgba(59, 130, 246, 0.2)' : 'rgba(59, 130, 246, 0.05)';
          ctx.strokeStyle = '#3b82f6';
          ctx.lineWidth = (isSelected ? 3 : 2) / effectiveScale;
          ctx.arc(vx, vy, radius, 0, 2 * Math.PI);
          ctx.fill();
          ctx.stroke();
          
          // Draw blue teardrop pin pointing to center
          const pinHeight = 24 / effectiveScale;
          const pinWidth = 12 / effectiveScale;
          ctx.beginPath();
          ctx.fillStyle = '#3b82f6';
          ctx.strokeStyle = '#ffffff';
          ctx.lineWidth = 1 / effectiveScale;
          ctx.moveTo(vx, vy);
          ctx.bezierCurveTo(vx - pinWidth, vy - pinHeight/2, vx - pinWidth, vy - pinHeight, vx, vy - pinHeight);
          ctx.bezierCurveTo(vx + pinWidth, vy - pinHeight, vx + pinWidth, vy - pinHeight/2, vx, vy);
          ctx.fill();
          ctx.stroke();
          
          // White dot inside pin head
          ctx.beginPath();
          ctx.fillStyle = '#ffffff';
          ctx.arc(vx, vy - pinHeight * 0.7, 3 / effectiveScale, 0, 2 * Math.PI);
          ctx.fill();
        }
        else if (penType === 'resolved_green' || penType === 'resolved_pink') {
          // Resolved checks tags (green or pink)
          const isGreen = penType === 'resolved_green';
          const primaryColor = isGreen ? '#10b981' : '#ec4899';
          const bgColor = isGreen ? 'rgba(16, 185, 129, 0.2)' : 'rgba(236, 72, 153, 0.2)';
          
          ctx.beginPath();
          ctx.fillStyle = bgColor;
          ctx.strokeStyle = primaryColor;
          ctx.lineWidth = (isSelected ? 3 : 2) / effectiveScale;
          ctx.arc(vx, vy, radius * 0.8, 0, 2 * Math.PI);
          ctx.fill();
          ctx.stroke();
          
          // Draw stylized checkmark in center
          ctx.beginPath();
          ctx.strokeStyle = '#ffffff';
          ctx.lineWidth = 2.5 / effectiveScale;
          ctx.lineCap = 'round';
          ctx.lineJoin = 'round';
          const size = radius * 0.3;
          ctx.moveTo(vx - size, vy);
          ctx.lineTo(vx - size * 0.2, vy + size);
          ctx.lineTo(vx + size, vy - size);
          ctx.stroke();
        }
 
        // Draw selection pulsing tick outline
        if (isSelected) {
          ctx.beginPath();
          ctx.strokeStyle = '#ffffff';
          ctx.lineWidth = 1.2 / effectiveScale;
          ctx.setLineDash([3 / effectiveScale, 3 / effectiveScale]);
          ctx.arc(vx, vy, radius * 1.8, 0, 2 * Math.PI);
          ctx.stroke();
          ctx.setLineDash([]);
        }
 
        ctx.restore();
      });
    }

    ctx.restore();

    // 7. Dynamic Crosshair Inspector overlay
    if (mouseCoords) {
      ctx.save();
      ctx.strokeStyle = 'rgba(161, 161, 170, 0.35)'; // Sleek zinc line
      ctx.setLineDash([4, 4]);
      ctx.lineWidth = 0.8;
      
      // Horizontal
      ctx.beginPath();
      ctx.moveTo(0, mouseCoords.y);
      ctx.lineTo(width, mouseCoords.y);
      ctx.stroke();
      
      // Vertical
      ctx.beginPath();
      ctx.moveTo(mouseCoords.x, 0);
      ctx.lineTo(mouseCoords.x, height);
      ctx.stroke();
      
      // Compute CAD coordinate representation (adjusting for normalization scale and translation)
      const wx = (normXMin + (mouseCoords.x - viewport.x) / effectiveScale).toFixed(2);
      const wy = (normYMin - (mouseCoords.y - viewport.y) / effectiveScale).toFixed(2); // standard engineering inversion
      
      ctx.fillStyle = '#a1a1aa';
      ctx.font = '10px monospace';
      ctx.fillText(`X: ${wx}, Y: ${wy}`, mouseCoords.x + 8, mouseCoords.y - 8);
      ctx.restore();
    }
 
    // 7.5 Draw Synced Laser Crosshair from the other viewport!
    if (hoveredCoords && !mouseCoords) {
      const syncedX = viewport.x + effectiveScale * (hoveredCoords.x - normXMin);
      const syncedY = viewport.y - effectiveScale * (hoveredCoords.y - normYMin);
      
      // Perform screen bounds check
      if (syncedX >= 0 && syncedX <= width && syncedY >= 0 && syncedY <= height) {
        ctx.save();
        
        // Laser circle glow ring
        ctx.beginPath();
        ctx.strokeStyle = '#00ffcc'; // Glowing cyan laser
        ctx.lineWidth = 1.5;
        ctx.shadowBlur = 10;
        ctx.shadowColor = '#00ffcc';
        ctx.arc(syncedX, syncedY, 16, 0, 2 * Math.PI);
        ctx.stroke();
        
        // Inner center laser dot
        ctx.beginPath();
        ctx.fillStyle = '#00ffcc';
        ctx.arc(syncedX, syncedY, 3, 0, 2 * Math.PI);
        ctx.fill();
        
        // Synced reticle ticks
        ctx.strokeStyle = 'rgba(0, 255, 204, 0.4)';
        ctx.lineWidth = 1.0;
        ctx.shadowBlur = 0; // Disable shadow for thin lines
        
        // Top tick
        ctx.beginPath();
        ctx.moveTo(syncedX, syncedY - 26);
        ctx.lineTo(syncedX, syncedY - 10);
        ctx.stroke();
        
        // Bottom tick
        ctx.beginPath();
        ctx.moveTo(syncedX, syncedY + 10);
        ctx.lineTo(syncedX, syncedY + 26);
        ctx.stroke();
        
        // Left tick
        ctx.beginPath();
        ctx.moveTo(syncedX - 26, syncedY);
        ctx.lineTo(syncedX - 10, syncedY);
        ctx.stroke();
        
        // Right tick
        ctx.beginPath();
        ctx.moveTo(syncedX + 10, syncedY);
        ctx.lineTo(syncedX + 26, syncedY);
        ctx.stroke();
        
        ctx.restore();
      }
    }
 
    // 8. Track rendering speed diagnostics
    const endTime = performance.now();
    setRenderDiagnostics({
      entityCount: totalEntities,
      drawCount: drawnEntities,
      renderTimeMs: Math.round((endTime - startTime) * 100) / 100
    });
  }, [layers, width, height, viewport, activeLayers, showViolations, violations, selectedViolation, mouseCoords, redrawTrigger, bgImage, drawing, isNeonCAD, hoveredCoords]);

  // Handle redraw when values update
  useEffect(() => {
    drawCanvas();
  }, [drawCanvas, redrawTrigger]);

  // Zoom-to-focus selected violation coordinates (smooth dynamic viewport tracking)
  useEffect(() => {
    if (selectedViolation && selectedViolation.coordinates && drawing) {
      // Ensure only the canvas corresponding to the violation owner updates the global viewport!
      if ((selectedViolation as any).drawing_id === drawing.id) {
        const [vx, vy] = selectedViolation.coordinates;
        
        let normScale = 1;
        let xmin = 0;
        let ymin = 0;
        if (drawing?.metadata?.render_bounds) {
          const [x0, y0, x1] = drawing.metadata.render_bounds;
          const boundsWidth = x1 - x0;
          if (boundsWidth > 0) {
            normScale = 1000 / boundsWidth;
            xmin = x0;
            ymin = y0;
          }
        }
        
        const stdX = (vx - xmin) * normScale;
        const stdY = (vy - ymin) * normScale;
        
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
      if (key === 'escape') {
        e.preventDefault();
        selectViolation(null);
      } else if (key === 'f') {
        e.preventDefault();
        if (selectedViolation && selectedViolation.coordinates && drawing) {
          const [vx, vy] = selectedViolation.coordinates;
          
          let normScale = 1;
          let xmin = 0;
          let ymin = 0;
          if (drawing?.metadata?.render_bounds) {
            const [x0, y0, x1] = drawing.metadata.render_bounds;
            const boundsWidth = x1 - x0;
            if (boundsWidth > 0) {
              normScale = 1000 / boundsWidth;
              xmin = x0;
              ymin = y0;
            }
          }
          
          const stdX = (vx - xmin) * normScale;
          const stdY = (vy - ymin) * normScale;
          
          const targetScale = 2.2;
          const targetX = width / 2 - stdX * targetScale;
          const targetY = height / 2 - stdY * targetScale;
          setViewport({ x: targetX, y: targetY, scale: targetScale });
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
  const handleWheel = (e: React.WheelEvent) => {
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
  };

  // Mouse pan triggers
  const handleMouseDown = (e: React.MouseEvent) => {
    if (e.button === 0) { // Left click to drag
      setIsDragging(true);
      setDragStart({ x: e.clientX - viewport.x, y: e.clientY - viewport.y });
    }
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;

    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;

    setMouseCoords({ x: mx, y: my });

    // Calculate standardized hover coordinates to synchronize with the other viewport!
    let normScale = 1;
    let xmin = 0;
    let ymin = 0;
    if (drawing?.metadata?.render_bounds) {
      const [x0, y0, x1] = drawing.metadata.render_bounds;
      const boundsWidth = x1 - x0;
      if (boundsWidth > 0) {
        normScale = 1000 / boundsWidth;
        xmin = x0;
        ymin = y0;
      }
    }
    const effectiveScale = viewport.scale * normScale;
    const stdX = xmin + (mx - viewport.x) / effectiveScale;
    const stdY = ymin - (my - viewport.y) / effectiveScale;
    setHoveredCoords({ x: stdX, y: stdY });

    if (isDragging) {
      const newX = e.clientX - dragStart.x;
      const newY = e.clientY - dragStart.y;
      setViewport({ ...viewport, x: newX, y: newY });
    }
  };

  const handleMouseUp = () => {
    setIsDragging(false);
  };

  const handleMouseLeave = () => {
    setIsDragging(false);
    setMouseCoords(null);
    setHoveredCoords(null);
  };

  return (
    <div style={{ position: 'relative', width, height, overflow: 'hidden' }}>
      <canvas
        ref={canvasRef}
        width={width * dpr}
        height={height * dpr}
        onWheel={handleWheel}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseLeave}
        style={{ cursor: isDragging ? 'grabbing' : 'grab', display: 'block', width: `${width}px`, height: `${height}px` }}
      />
 
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
    </div>
  );
};
