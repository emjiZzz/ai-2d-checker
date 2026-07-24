import React, { useEffect, useRef, useState } from 'react';
import { useReviewStore } from '../../stores/reviewStore';
import { useWorkspaceStore } from '../../stores/workspaceStore';
import { fetchWithAuth } from '../../services/fetchUtils';
import { useThemeStore } from '../../stores/themeStore';
import { useCanvasInteraction } from './useCanvasInteraction';
import { CanvasRenderer } from './CanvasRenderer';
import { ErrorBoundary } from 'react-error-boundary';
import { AlertTriangle } from 'lucide-react';
import { Skeleton } from '../ui/Skeleton';
import './DrawingCanvas.css';

import { z } from 'zod';

export const entityPayloadSchema = z.object({
  id: z.string(),
  type: z.string(),
  geometry: z.any(),
  style: z.any(),
  properties: z.any().optional(),
});

export type EntityPayload = z.infer<typeof entityPayloadSchema>;

interface DrawingCanvasProps {
  layers: Record<string, EntityPayload[]>;
  width: number;
  height: number;
  drawing?: any;
}

export interface DrawingCanvasRef {
  exportImage: (exportWidth?: number, exportHeight?: number) => string;
}

// Module-level cache to prevent refetching the background image on tab switches
const renderingCache = new Map<string, {
  bgImage: HTMLImageElement;
  lightBgImage: HTMLImageElement | null;
}>();

export const DrawingCanvas = React.forwardRef<DrawingCanvasRef, DrawingCanvasProps>(
  ({ layers, width, height, drawing }, ref) => {
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const markerPositionsRef = useRef<Record<string, { x: number, y: number }>>({});


    const showMarkerLabels = useReviewStore(s => s.showMarkerLabels);
    const toggleMarkerLabels = useReviewStore(s => s.toggleMarkerLabels);
    const oldDrawing = useWorkspaceStore((s) => s.oldDrawing);
    const theme = useThemeStore((s) => s.theme);

    const [renderDiagnostics, setRenderDiagnostics] = useState({ entityCount: 0, drawCount: 0, renderTimeMs: 0 });
    const [redrawTrigger, setRedrawTrigger] = useState(0);

    const [bgImage, setBgImage] = useState<HTMLImageElement | null>(null);
    const [lightBgImage, setLightBgImage] = useState<HTMLImageElement | null>(null);
    const [isFetchingBg, setIsFetchingBg] = useState(false);

    // Zod validation for incoming layers to catch malformed structures early
    const validatedLayers = React.useMemo(() => {
      const result: Record<string, EntityPayload[]> = {};
      Object.keys(layers).forEach((layerName) => {
        const rawLayer = layers[layerName];
        if (!Array.isArray(rawLayer)) {
          result[layerName] = [];
          return;
        }
        result[layerName] = rawLayer.filter((item) => {
          const res = entityPayloadSchema.safeParse(item);
          if (!res.success) {
            console.warn(`Filtering invalid entity in layer ${layerName}:`, res.error);
            return false;
          }
          return true;
        });
      });
      return result;
    }, [layers]);

    const { handlers, state } = useCanvasInteraction({
      canvasRef,
      width,
      height,
      drawing,
      oldDrawing,
      setRedrawTrigger,
      markerPositionsRef
    });

    const {
      isDraggingRef,
      contextMenu,
      setContextMenu,
      isHoveringMarkerState,
      hoveredMarkerId,
      hoveredAnnotationId,
      cursorStyle
    } = state;

    useEffect(() => {
      if (!drawing?.id) {
        setBgImage(null);
        setLightBgImage(null);
        return;
      }

      const cached = renderingCache.get(drawing.id);
      if (cached) {
        setBgImage(cached.bgImage);
        setLightBgImage(cached.lightBgImage);
        return;
      }

      let active = true;
      const loadBackground = async () => {
        setIsFetchingBg(true);
        try {
          const res = await fetchWithAuth(`/api/v1/drawings/${drawing.id}/rendering`, {
            headers: { "Accept": "image/png" }
          });

          if (!active) return;

          if (res.status === 204) {
            setBgImage(null);
            setLightBgImage(null);
            return;
          }

          if (!res.ok) {
            throw new Error(`No rendering generated (HTTP ${res.status})`);
          }

          const blob = await res.blob();
          const img = new Image();
          img.src = URL.createObjectURL(blob);
          img.onload = () => {
            if (!active) return;

            // The raster rendering has thin, anti-aliased CAD linework that loses most of its
            // pixel coverage when the browser downsamples it at low zoom — lines fade or vanish
            // instead of just looking smaller. Thicken every line by ~1px before it's ever used,
            // so it survives minification. Cheap GPU-accelerated approximation of morphological
            // dilation: composite the same image at a few 1px offsets — any pixel that was line
            // content in ANY of those offset copies ends up opaque in the result, growing every
            // stroke outward by ~1px in each direction. Much faster than a manual per-pixel loop
            // over an ~8000px-wide image.
            const thickenCanvas = document.createElement('canvas');
            thickenCanvas.width = img.width;
            thickenCanvas.height = img.height;
            const thickenCtx = thickenCanvas.getContext('2d');
            if (thickenCtx) {
              const offsets: [number, number][] = [[0, 0], [1, 0], [-1, 0], [0, 1], [0, -1]];
              offsets.forEach(([dx, dy]) => thickenCtx.drawImage(img, dx, dy));
            }
            const thickenedImg = new Image();
            thickenedImg.onload = () => {
              if (!active) return;
              proceedWithImage(thickenedImg);
            };
            thickenedImg.onerror = () => {
              // Fall back to the untouched raster if thickening somehow fails to encode.
              if (active) proceedWithImage(img);
            };
            thickenedImg.src = thickenCtx ? thickenCanvas.toDataURL() : img.src;
          };

          const proceedWithImage = (img: HTMLImageElement) => {
            if (!active) return;

            setBgImage(img);
            setRedrawTrigger((prev) => prev + 1);

            // Save to cache immediately so tab switches don't trigger another fetch
            renderingCache.set(drawing.id, { bgImage: img, lightBgImage: null });

            const canvas = document.createElement('canvas');
            canvas.width = img.width;
            canvas.height = img.height;
            const context = canvas.getContext('2d');
            if (context) {
              context.drawImage(img, 0, 0);
              const imgData = context.getImageData(0, 0, canvas.width, canvas.height);
              const data = imgData.data;

              // Chunked via setTimeout so a big rendering doesn't block the UI thread, but each
              // setTimeout hop is throttled to a ~4ms floor by the browser — with too small a
              // chunk size, that per-hop overhead dominates and the light-theme variant takes
              // noticeably longer to finish than the processing itself needs, leaving the raw
              // dark-tuned image (wrong colors for light theme) visible for a stretch. A larger
              // chunk trades a slightly bigger per-chunk pause for far fewer hops overall.
              const PIXELS_PER_CHUNK = 2000000;
              const CHUNK_SIZE = PIXELS_PER_CHUNK * 4;
              let offset = 0;

              const processChunk = () => {
                if (!active) return;
                const end = Math.min(offset + CHUNK_SIZE, data.length);
                for (let i = offset; i < end; i += 4) {
                  if (data[i + 3] === 0) continue;
                  const r = data[i], g = data[i + 1], b = data[i + 2];
                  if (Math.max(r, g, b) - Math.min(r, g, b) < 25) {
                    data[i] = 255 - r;
                    data[i + 1] = 255 - g;
                    data[i + 2] = 255 - b;
                  } else {
                    const brightness = (r * 299 + g * 587 + b * 114) / 1000;
                    if (brightness > 150) {
                      data[i] = Math.round(r * 0.45);
                      data[i + 1] = Math.round(g * 0.45);
                      data[i + 2] = Math.round(b * 0.45);
                    }
                  }
                }
                offset = end;

                if (offset < data.length) {
                  setTimeout(processChunk, 0);
                } else {
                  context.putImageData(imgData, 0, 0);
                  const lightImg = new Image();
                  lightImg.src = canvas.toDataURL();
                  lightImg.onload = () => {
                    // Update the cache with the light mode variant once ready
                    const currentCache = renderingCache.get(drawing.id);
                    if (currentCache) {
                      currentCache.lightBgImage = lightImg;
                    }

                    if (active) {
                      setLightBgImage(lightImg);
                      setRedrawTrigger((prev) => prev + 1);
                    }
                  };
                }
              };

              // Run the first chunk synchronously (no setTimeout hop) — only subsequent
              // chunks need to yield back to the browser.
              processChunk();
            }
          };
        } catch (err) {
          console.warn("Background rendering loading failed. Falling back to vector.", err);
          if (active) {
            setBgImage(null);
            setLightBgImage(null);
          }
        } finally {
          if (active) setIsFetchingBg(false);
        }
      };

      loadBackground();
      return () => {
        active = false;
      };
    }, [drawing?.id]);

    return (
      <div style={{ position: 'relative', width: '100%', height: '100%', overflow: 'hidden' }}>
        <ErrorBoundary
          fallbackRender={({ error, resetErrorBoundary }) => (
            <div className="absolute inset-0 flex flex-col items-center justify-center bg-bg-dark text-text-primary z-50">
              <div className="flex flex-col items-center p-6 border border-red-500/30 bg-red-500/10 rounded-xl shadow-lg max-w-[400px] text-center">
                <AlertTriangle size={48} className="text-red-500 mb-4 animate-bounce" />
                <h3 className="text-lg font-bold text-red-400 mb-2">Rendering Engine Crashed</h3>
                <p className="text-sm text-text-muted mb-4 font-mono overflow-auto max-h-[100px] bg-black/40 p-2 rounded w-full border border-border-color">
                  {error instanceof Error ? error.message : String(error)}
                </p>
                <button
                  onClick={resetErrorBoundary}
                  className="px-4 py-2 bg-red-500 hover:bg-red-600 text-white font-bold rounded shadow-md transition-colors w-full"
                >
                  Reset Renderer
                </button>
              </div>
            </div>
          )}
          onReset={() => {
            // Optional: reset any specific state here if needed when trying to recover
            setRedrawTrigger(prev => prev + 1);
          }}
        >
          <CanvasRenderer
            ref={ref}
            width={width}
            height={height}
            layers={validatedLayers}
            drawing={drawing}
            isHoveringMarkerState={isHoveringMarkerState}
            hoveredMarkerId={hoveredMarkerId}
            hoveredAnnotationId={hoveredAnnotationId}
            isNeonCAD={false}
            bgImage={bgImage}
            lightBgImage={lightBgImage}
            setRenderDiagnostics={setRenderDiagnostics}
            markerPositionsRef={markerPositionsRef}
            redrawTrigger={redrawTrigger}
            isDraggingRef={isDraggingRef}
            canvasInteractionHandlers={handlers}
            cursorStyle={cursorStyle}
            sharedCanvasRef={canvasRef}
          />
        </ErrorBoundary>



        {isFetchingBg && (
          <div className="absolute inset-0 flex items-center justify-center p-8 bg-bg-dark/50 backdrop-blur-[2px] z-40 transition-opacity">
            <Skeleton className="w-full h-full rounded-2xl shadow-2xl border border-border-color/50 opacity-90" />
            <div className="absolute flex flex-col items-center gap-4">
              <div className="w-12 h-12 border-4 border-accent-cyan border-t-transparent rounded-full animate-spin"></div>
              <span className="text-accent-cyan font-bold tracking-widest uppercase text-sm drop-shadow-md">
                Ingesting CAD Geometry...
              </span>
            </div>
          </div>
        )}

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
              {showMarkerLabels ? "捷 Hide Labels" : "捷 Show Labels"}
            </div>
            <div
              className={`context-menu-item ${useWorkspaceStore.getState().deletedViolationsStack.length === 0 ? "disabled" : ""}`}
              onClick={() => {
                useWorkspaceStore.getState().popAndRestoreViolation();
                setContextMenu(null);
              }}
            >
              <span>竊ｩ Undo Delete</span>
              {useWorkspaceStore.getState().deletedViolationsStack.length > 0 && (
                <span style={{ fontSize: '0.65rem', background: 'rgba(255,255,255,0.1)', padding: '1px 5px', borderRadius: '4px', marginLeft: '6px' }}>
                  {useWorkspaceStore.getState().deletedViolationsStack.length}
                </span>
              )}
            </div>
            <div style={{ borderBottom: '1px solid rgba(255,255,255,0.08)', margin: '4px 0' }} />
            <div style={{ padding: '4px 14px', fontSize: '0.65rem', textTransform: 'uppercase', letterSpacing: '0.05em', color: '#71717a', fontWeight: 600 }}>Filter Markers</div>
            {/*
              Keys here MUST match the markerType values renderViolationReticles
              derives from pen_type (see renderEntities.ts) and reviewStore's
              visibleMarkerTypes default state: MISMATCHED/CHANGED/ADDED/MATCHED/CONFLICT.
              A prior refactor swapped these for dimensional/clearance/missing_entity,
              which renderViolationReticles never reads — the checkboxes rendered
              but silently did nothing. Restored to the working taxonomy.
              CONFLICT is hybrid-method-only (docs/hybrid-comparison-engine-
              implementation-plan.md) — the two generators disagreed and the crop
              verifier couldn't confirm either side; never emitted by rag/rag_ai/ai_vision.
            */}
            {[
              { label: "MISMATCHED", key: "MISMATCHED", color: "#ef4444" },
              { label: "CHANGED", key: "CHANGED", color: "#f97316" },
              { label: "ADDED", key: "ADDED", color: "#3b82f6" },
              { label: "MATCHED", key: "MATCHED", color: "#10b981" },
              { label: "CONFLICT", key: "CONFLICT", color: "#a855f7" }
            ].map(item => {
              const isActive = useReviewStore.getState().visibleMarkerTypes[item.key] ?? true;
              return (
                <div
                  key={item.key}
                  className="context-menu-item"
                  onClick={(e) => {
                    e.stopPropagation();
                    useReviewStore.getState().toggleMarkerTypeVisibility(item.key);
                    setRedrawTrigger(prev => prev + 1);
                  }}
                  style={{ opacity: isActive ? 1 : 0.5 }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <div style={{ width: '10px', height: '10px', borderRadius: '50%', backgroundColor: item.color }} />
                    {item.label}
                  </div>
                  {!isActive && <span style={{ fontSize: '0.7rem' }}>Hidden</span>}
                </div>
              );
            })}
            <div style={{ borderBottom: '1px solid rgba(255,255,255,0.08)', margin: '4px 0' }} />
            <div className="context-menu-item has-submenu">
              <span>Add Marker</span>
              <span style={{ fontSize: '0.6rem', opacity: 0.6 }}>▶</span>
              <div className="context-submenu">
                {[
                  { label: "MATCHED", type: "ai_green", isResolved: true, status: "MATCHED" },
                  { label: "MISMATCHED", type: "ai_red", isResolved: false, status: "MISMATCHED" },
                  { label: "CHANGED", type: "ai_orange", isResolved: false, status: "CHANGED" },
                  { label: "ADDED", type: "checker_blue", isResolved: false, status: "ADDED" }
                ].map((opt) => (
                  <div
                    key={opt.label}
                    className="context-menu-item"
                    onClick={() => {
                      const newMarker: any = {
                        id: `custom_marker_${Date.now()}`,
                        severity: opt.status === "MATCHED" ? "low" : "high",
                        category: "Manual Marker",
                        description: "Manually added marker",
                        recommendation: "Manual verification check",
                        affected_entities: [],
                        confidence: 1.0,
                        coordinates: [contextMenu.wx, contextMenu.wy] as [number, number],
                        ref_coordinates: [contextMenu.wx, contextMenu.wy] as [number, number],
                        pen_type: opt.type,
                        is_resolved: opt.isResolved,
                        status: opt.status
                      };
                      // Named store action (setViolations), not useWorkspaceStore.setState —
                      // keeps this consistent with the Phase 8 ESLint guard.
                      const current = useWorkspaceStore.getState().violations;
                      useWorkspaceStore.getState().setViolations([...current, newMarker]);
                      setRedrawTrigger(prev => prev + 1);
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



        {/* High-Fidelity HUD Engineering Diagnostics Overlay */}
        <div
          className={`absolute bottom-3 left-3 flex items-center gap-3 px-3 py-1.5 rounded-xl border backdrop-blur-md pointer-events-none font-mono text-xs shadow-xl ${
            theme === 'hc-light'
              ? 'bg-[var(--bg-card)]/85 border-zinc-200/80 text-zinc-600'
              : 'bg-zinc-950/80 border-white/10 text-zinc-400'
          }`}
        >
          <ZoomDisplay />
          <div className="w-[1px] h-3 bg-white/10" />
          <div>VIRTUALIZED: <span className="text-emerald-400 font-bold">{renderDiagnostics.drawCount}/{renderDiagnostics.entityCount}</span></div>
          <div className="w-[1px] h-3 bg-white/10" />
          <div>RENDER: <span className="text-amber-400 font-bold">{renderDiagnostics.renderTimeMs}ms</span></div>
        </div>
      </div>
    );
  }
);

/**
 * Zoom percentage display — imperative DOM update, no React re-render on zoom.
 */
const ZoomDisplay = () => {
  const spanRef = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    const unsub = useReviewStore.subscribe((state) => {
      if (spanRef.current) spanRef.current.textContent = `${(state.viewport.scale * 100).toFixed(0)}%`;
    });
    return unsub;
  }, []);
  const initScale = useReviewStore.getState().viewport.scale;
  return <div>ZOOM: <span ref={spanRef} style={{ color: '#00e5ff', fontWeight: 600 }}>{(initScale * 100).toFixed(0)}%</span></div>;
};
