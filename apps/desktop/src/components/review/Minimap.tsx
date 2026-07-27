import React, { useRef, useState, useCallback, useEffect } from 'react';
import { useReviewStore } from '../../stores/reviewStore';
import { useThemeStore } from '../../stores/themeStore';
import { fetchWithAuth } from '../../services/fetchUtils';
import { getNormalization, parseBounds, clampViewport } from '../../utils/coordinateTransform';
import { Map as MapIcon } from 'lucide-react';

// Shared cache to prevent duplicate network requests when both Old and New panels load the same drawing
const thumbnailCache = new Map<string, Promise<HTMLImageElement>>();
// Lazily-computed light-theme variant per drawing, keyed the same as thumbnailCache
const lightThumbnailCache = new Map<string, HTMLImageElement>();

// The backend rendering is tuned for a dark viewport (near-white linework, bright
// cyan/yellow markers) and anti-aliases thin CAD linework, leaving most line-edge
// pixels at low partial alpha. On a light minimap frame that reads as nearly
// invisible, so for hc-light we derive a variant the same way DrawingCanvas.tsx
// does for the main canvas — invert near-grayscale pixels, darken bright saturated
// ones — PLUS an alpha gamma-lift the main canvas doesn't need: the minimap squeezes
// the ~8000px-wide native rendering down to 200x150 (a ~40x downscale), and synthetic
// testing confirmed that at realistic anti-aliased alphas (~0.15) that downscale
// dilutes line content to fully invisible (0 visible pixels) unless boosted first.
// The lift is monotonic (never reduces alpha) so it can't hide anything that was
// already visible.
const ALPHA_GAMMA = 0.35;

function buildLightVariant(img: HTMLImageElement): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const canvas = document.createElement('canvas');
    canvas.width = img.width;
    canvas.height = img.height;
    const ctx = canvas.getContext('2d');
    if (!ctx) { reject(new Error('no 2d context')); return; }

    ctx.drawImage(img, 0, 0);
    const imgData = ctx.getImageData(0, 0, canvas.width, canvas.height);
    const data = imgData.data;

    // Chunked (not one giant synchronous pass) so an ~8000px-wide rendering doesn't
    // freeze the UI thread — mirrors the pattern already used for the same job in
    // DrawingCanvas.tsx.
    const PIXELS_PER_CHUNK = 250000;
    const CHUNK_SIZE = PIXELS_PER_CHUNK * 4;
    let offset = 0;

    const processChunk = () => {
      const end = Math.min(offset + CHUNK_SIZE, data.length);
      for (let i = offset; i < end; i += 4) {
        const a = data[i + 3];
        if (a === 0) continue;

        const r = data[i], g = data[i + 1], b = data[i + 2];
        if (Math.max(r, g, b) - Math.min(r, g, b) < 30) {
          const brightness = (r * 299 + g * 587 + b * 114) / 1000;
          if (brightness < 70) {
            data[i] = 235;
            data[i + 1] = 235;
            data[i + 2] = 235;
          } else {
            const invR = 255 - r;
            const invG = 255 - g;
            const invB = 255 - b;
            if (invR > 215 && invG > 215 && invB > 215) {
              data[i] = 235;
              data[i + 1] = 235;
              data[i + 2] = 235;
            } else {
              data[i] = invR;
              data[i + 1] = invG;
              data[i + 2] = invB;
            }
          }
        } else {
          const brightness = (r * 299 + g * 587 + b * 114) / 1000;
          if (brightness > 150) {
            data[i] = Math.round(r * 0.45);
            data[i + 1] = Math.round(g * 0.45);
            data[i + 2] = Math.round(b * 0.45);
          }
        }

        const boostedAlpha = 255 * Math.pow(a / 255, ALPHA_GAMMA);
        data[i + 3] = Math.max(a, Math.round(boostedAlpha));
      }
      offset = end;

      if (offset < data.length) {
        setTimeout(processChunk, 0);
      } else {
        ctx.putImageData(imgData, 0, 0);
        const lightImg = new Image();
        lightImg.onload = () => resolve(lightImg);
        lightImg.onerror = reject;
        lightImg.src = canvas.toDataURL();
      }
    };

    processChunk();
  });
}

interface MinimapProps {
  drawing: any;
  canvasWidth: number;
  canvasHeight: number;
}

export const Minimap: React.FC<MinimapProps> = ({ drawing, canvasWidth, canvasHeight }) => {
  const viewportRef = useRef(useReviewStore.getState().viewport);
  const setViewport = useReviewStore(s => s.setViewport);
  const showMinimap = useReviewStore(s => s.showMinimap);
  const theme = useThemeStore(s => s.theme);
  const mapRef = useRef<HTMLDivElement>(null);
  const thumbCanvasRef = useRef<HTMLCanvasElement>(null);
  const viewportBoxRef = useRef<HTMLDivElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [thumbImage, setThumbImage] = useState<HTMLImageElement | null>(null);
  const [lightThumbImage, setLightThumbImage] = useState<HTMLImageElement | null>(null);

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
      setLightThumbImage(null);
      return;
    }

    let active = true;
    setLightThumbImage(lightThumbnailCache.get(drawing.id) || null);

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

  // Derive the light-theme variant once per drawing, the first time it's actually needed
  useEffect(() => {
    if (theme !== 'hc-light' || !thumbImage || !drawing?.id) return;
    if (lightThumbnailCache.has(drawing.id)) return;

    let active = true;
    buildLightVariant(thumbImage)
      .then((lightImg) => {
        lightThumbnailCache.set(drawing.id, lightImg);
        if (active) setLightThumbImage(lightImg);
      })
      .catch(() => { /* fall back to the raw dark-tuned rendering */ });

    return () => { active = false; };
  }, [theme, thumbImage, drawing?.id]);

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

  // Paint thumbnail onto the minimap canvas whenever the image or theme changes (NOT on viewport change)
  useEffect(() => {
    const canvas = thumbCanvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const box = calculateViewportBox();
    ctx.clearRect(0, 0, MINIMAP_WIDTH, MINIMAP_HEIGHT);

    const imageToDraw = theme === 'hc-light' && lightThumbImage ? lightThumbImage : thumbImage;

    if (imageToDraw && bounds) {
      // Draw the thumbnail scaled to fit the drawing-bounds region
      ctx.drawImage(
        imageToDraw,
        box.offsetX,
        box.offsetY,
        (box as any).drawW ?? (bounds.xmax - bounds.xmin) * box.minScale,
        (box as any).drawH ?? (norm.ymax - norm.ymin) * box.minScale,
      );
    }
  }, [thumbImage, lightThumbImage, theme, calculateViewportBox, bounds, norm]);

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
  // Auto-hide minimap on narrow panes/screens to prevent obstructing canvas view
  if (canvasWidth < 480 || canvasHeight < 350) return null;

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
        background: 'var(--bg-sidebar)',
        border: '1px solid var(--border-color)',
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
          color: 'var(--text-muted)',
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

      {/* Drawing thumbnail canvas — draws the theme-appropriate variant (see
          buildLightVariant above), so no synthetic backdrop is needed here. */}
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
          opacity: 0.9,
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
            border: '1px solid var(--border-color)',
            background: 'var(--sidebar-item-hover)',
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
