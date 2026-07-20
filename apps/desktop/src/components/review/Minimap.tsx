import React, { useRef, useState, useCallback, useEffect } from 'react';
import { useReviewStore } from '../../stores/reviewStore';
import { fetchWithAuth } from '../../services/fetchUtils';
import { getNormalization, parseBounds, clampViewport } from '../../utils/coordinateTransform';
import { Map as MapIcon } from 'lucide-react';

// Shared cache to prevent duplicate network requests when both Old and New panels load the same drawing
const thumbnailCache = new Map<string, Promise<HTMLImageElement>>();

interface MinimapProps {
  drawing: any;
  canvasWidth: number;
  canvasHeight: number;
}

export const Minimap: React.FC<MinimapProps> = ({ drawing, canvasWidth, canvasHeight }) => {
  const viewportRef = useRef(useReviewStore.getState().viewport);
  const setViewport = useReviewStore(s => s.setViewport);
  const showMinimap = useReviewStore(s => s.showMinimap);
  const mapRef = useRef<HTMLDivElement>(null);
  const thumbCanvasRef = useRef<HTMLCanvasElement>(null);
  const viewportBoxRef = useRef<HTMLDivElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [thumbImage, setThumbImage] = useState<HTMLImageElement | null>(null);

  // Constants
  const MINIMAP_WIDTH = 200;
  const MINIMAP_HEIGHT = 150;

  const boundsArray = drawing?.metadata?.render_bounds;
  const bounds = parseBounds(boundsArray);
  const norm = getNormalization(bounds);

  // Fetch the drawing thumbnail from the backend rendering endpoint
  useEffect(() => {
    if (!drawing?.id) {
      setThumbImage(null);
      return;
    }

    let active = true;

    if (!thumbnailCache.has(drawing.id)) {
      const fetchPromise = fetchWithAuth(`/api/v1/drawings/${drawing.id}/rendering`, { headers: { "Accept": "image/png" } })
        .then(async (res) => {
          if (res.status === 204) throw new Error('no rendering (204)');
          if (!res.ok) throw new Error('no rendering');
          const blob = await res.blob();
          return new Promise<HTMLImageElement>((resolve, reject) => {
            const img = new Image();
            img.src = URL.createObjectURL(blob);
            img.onload = () => resolve(img);
            img.onerror = reject;
          });
        });
      thumbnailCache.set(drawing.id, fetchPromise);
    }

    thumbnailCache.get(drawing.id)!
      .then((img) => {
        if (active) setThumbImage(img);
      })
      .catch(() => { /* fallback: no thumbnail, show outline only */ });

    return () => { active = false; };
  }, [drawing?.id]);

  const calculateViewportBox = useCallback((vp = viewportRef.current) => {
    if (!norm.hasBounds || !bounds) return { left: 0, top: 0, width: 0, height: 0, minScale: 1, offsetX: 0, offsetY: 0 };

    const worldW = bounds.xmax - bounds.xmin;
    const worldH = norm.ymax - norm.ymin;

    const scaleX = MINIMAP_WIDTH / worldW;
    const scaleY = MINIMAP_HEIGHT / worldH;
    const minScale = Math.min(scaleX, scaleY);

    const mapW = worldW * minScale;
    const mapH = worldH * minScale;

    const offsetX = (MINIMAP_WIDTH - mapW) / 2;
    const offsetY = (MINIMAP_HEIGHT - mapH) / 2;

    const effectiveScale = vp.scale * norm.normScale;

    const viewWorldX = norm.xmin + (-vp.x / effectiveScale);
    const viewWorldY = norm.ymin + (-vp.y / effectiveScale);

    const viewWorldW = canvasWidth / effectiveScale;
    const viewWorldH = canvasHeight / effectiveScale;

    const boxLeft = offsetX + (viewWorldX - norm.xmin) * minScale;
    const boxTop = offsetY + (viewWorldY - norm.ymin) * minScale;
    const boxWidth = viewWorldW * minScale;
    const boxHeight = viewWorldH * minScale;

    return {
      left: Math.max(0, boxLeft),
      top: Math.max(0, boxTop),
      width: Math.min(MINIMAP_WIDTH - Math.max(0, boxLeft), boxWidth),
      height: Math.min(MINIMAP_HEIGHT - Math.max(0, boxTop), boxHeight),
      minScale,
      offsetX,
      offsetY,
      drawW: mapW,
      drawH: mapH,
    };
  }, [norm, bounds, canvasWidth, canvasHeight]);

  // Update the viewport indicator box imperatively via DOM — no React re-render on every pan
  useEffect(() => {
    const updateBox = (vp: typeof viewportRef.current) => {
      viewportRef.current = vp;
      if (!viewportBoxRef.current) return;
      const box = calculateViewportBox(vp);
      const s = viewportBoxRef.current.style;
      s.left = `${box.left}px`;
      s.top = `${box.top}px`;
      s.width = `${box.width}px`;
      s.height = `${box.height}px`;
    };

    // Initialize
    updateBox(useReviewStore.getState().viewport);

    // Subscribe without React
    const unsub = useReviewStore.subscribe((state) => {
      if (state.viewport !== viewportRef.current) {
        updateBox(state.viewport);
      }
    });
    return unsub;
  }, [calculateViewportBox]);

  // Paint thumbnail onto the minimap canvas whenever image changes (NOT on viewport change)
  useEffect(() => {
    const canvas = thumbCanvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const box = calculateViewportBox();
    ctx.clearRect(0, 0, MINIMAP_WIDTH, MINIMAP_HEIGHT);

    if (thumbImage && bounds) {
      // Draw the thumbnail scaled to fit the drawing-bounds region
      ctx.drawImage(
        thumbImage,
        box.offsetX,
        box.offsetY,
        (box as any).drawW ?? (bounds.xmax - bounds.xmin) * box.minScale,
        (box as any).drawH ?? (norm.ymax - norm.ymin) * box.minScale,
      );
    }
  }, [thumbImage, calculateViewportBox, bounds, norm]);

  const updateViewportFromMinimap = (e: React.PointerEvent) => {
    if (!mapRef.current || !norm.hasBounds) return;
    const rect = mapRef.current.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    const vp = viewportRef.current;

    const { minScale, offsetX, offsetY } = calculateViewportBox(vp);

    const worldX = norm.xmin + (mx - offsetX) / minScale;
    const worldY = norm.ymin + (my - offsetY) / minScale;

    const effectiveScale = vp.scale * norm.normScale;
    const viewWWorld = canvasWidth / effectiveScale;
    const viewHWorld = canvasHeight / effectiveScale;

    const targetWorldX = worldX - viewWWorld / 2;
    const targetWorldY = worldY - viewHWorld / 2;

    const clampedVp = clampViewport({
      ...vp,
      x: -(targetWorldX - norm.xmin) * effectiveScale,
      y: -(targetWorldY - norm.ymin) * effectiveScale,
    }, bounds, canvasWidth, canvasHeight);

    setViewport(clampedVp);
  };

  const handlePointerDown = (e: React.PointerEvent) => {
    if (!norm.hasBounds || !mapRef.current) return;
    setIsDragging(true);
    updateViewportFromMinimap(e);
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
  };

  const handlePointerMove = (e: React.PointerEvent) => {
    if (!isDragging || !norm.hasBounds || !mapRef.current) return;
    updateViewportFromMinimap(e);
  };

  const handlePointerUp = (e: React.PointerEvent) => {
    setIsDragging(false);
    (e.target as HTMLElement).releasePointerCapture(e.pointerId);
  };

  if (!showMinimap) return null;
  if (!drawing || !norm.hasBounds || !bounds) return null;

  const box = calculateViewportBox();

  return (
    <div
      className="minimap-container"
      style={{
        boxSizing: 'content-box',
        position: 'absolute',
        top: '8px',
        left: '8px',
        width: `${MINIMAP_WIDTH}px`,
        height: `${MINIMAP_HEIGHT}px`,
        background: 'rgba(9, 9, 11, 0.88)',
        border: '1px solid rgba(255,255,255,0.12)',
        borderRadius: '6px',
        boxShadow: '0 4px 16px rgba(0,0,0,0.6)',
        zIndex: 50,
        overflow: 'hidden',
        backdropFilter: 'blur(6px)',
        cursor: isDragging ? 'grabbing' : 'crosshair',
      }}
      ref={mapRef}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      onPointerCancel={handlePointerUp}
    >
      {/* Label */}
      <div
        style={{
          position: 'absolute',
          top: '4px',
          left: '6px',
          display: 'flex',
          alignItems: 'center',
          gap: '4px',
          color: 'rgba(255,255,255,0.45)',
          fontSize: '0.6rem',
          fontWeight: 700,
          pointerEvents: 'none',
          textTransform: 'uppercase',
          letterSpacing: '0.06em',
          zIndex: 2,
        }}
      >
        <MapIcon size={10} /> Map
      </div>

      {/* Drawing thumbnail canvas */}
      <canvas
        ref={thumbCanvasRef}
        width={MINIMAP_WIDTH}
        height={MINIMAP_HEIGHT}
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          width: '100%',
          height: '100%',
          opacity: 0.7,
          pointerEvents: 'none',
        }}
      />

      {/* Fallback drawing outline when no thumbnail */}
      {!thumbImage && bounds && (
        <div
          style={{
            boxSizing: 'border-box',
            position: 'absolute',
            left: `${box.offsetX}px`,
            top: `${box.offsetY}px`,
            width: `${(bounds.xmax - bounds.xmin) * box.minScale}px`,
            height: `${(norm.ymax - norm.ymin) * box.minScale}px`,
            border: '1px solid rgba(255,255,255,0.2)',
            background: 'rgba(255,255,255,0.03)',
            pointerEvents: 'none',
          }}
        />
      )}

      {/* Viewport indicator — updated imperatively via ref, no React re-render */}
      <div
        ref={viewportBoxRef}
        style={{
          boxSizing: 'border-box',
          position: 'absolute',
          left: `${box.left}px`,
          top: `${box.top}px`,
          width: `${box.width}px`,
          height: `${box.height}px`,
          border: '2px solid #ef4444',
          borderRadius: '4px',
          boxShadow: '0 0 6px rgba(239,68,68,0.6)',
          background: 'transparent',
          pointerEvents: 'none',
          zIndex: 3,
        }}
      />
    </div>
  );
};
