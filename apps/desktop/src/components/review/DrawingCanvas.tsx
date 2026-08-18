import React, { useMemo, useRef, useState } from 'react';
import { useReviewStore } from '../../stores/reviewStore';
import { useWorkspaceStore } from '../../stores/workspaceStore';
import { AnnotationSeverity, getAnnotationBadgeMap } from '../../stores/workspace/types';
import { useThemeStore } from '../../stores/themeStore';
import { useCanvasInteraction } from './useCanvasInteraction';
import { useEntityPicking } from './useEntityPicking';
import { CanvasRenderer } from './CanvasRenderer';
import { CanvasContextMenu } from './CanvasContextMenu';
import { AnnotationCreateModal } from './AnnotationCreateModal';
import { AnnotationCardPopover } from './AnnotationCardPopover';
import { ErrorBoundary } from 'react-error-boundary';
import { AlertTriangle } from 'lucide-react';
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

export const DrawingCanvas = React.forwardRef<DrawingCanvasRef, DrawingCanvasProps>(
  ({ layers, width, height, drawing }, ref) => {
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const markerPositionsRef = useRef<Record<string, { x: number, y: number }>>({});


    const selectedAnnotationId = useWorkspaceStore((s) => s.selectedAnnotationId);
    const selectAnnotation = useWorkspaceStore((s) => s.selectAnnotation);
    const annotations = useWorkspaceStore((s) => s.annotations);
    // Stable A001/A002… labels derived from annotation order; recomputed only
    // when the annotation set changes. No such field exists on the store —
    // it's a pure projection of `annotations`.
    const annotationBadgeMap = useMemo(() => getAnnotationBadgeMap(annotations), [annotations]);
    const oldDrawing = useWorkspaceStore((s) => s.oldDrawing);
    const theme = useThemeStore((s) => s.theme);

    const [redrawTrigger, setRedrawTrigger] = useState(0);

    const [annotationModal, setAnnotationModal] = useState<{
      visible: boolean;
      x: number;
      y: number;
      wx: number;
      wy: number;
      severity: AnnotationSeverity;
      content: string;
    } | null>(null);

    // Zod validation for incoming layers to catch malformed structures early.
    //
    // NOTE — do NOT filter these by `layout_space`. It looks like the obvious fix for
    // model-space annotation appearing on the sheet, and it is wrong: on a paper-space
    // drawing the PART lives in model space and only the sheet border, title block and
    // tables live in the paper layout. Measured on M745221N01, filtering to the paper
    // layout removes 86 entities including all 33 ellipses (the entire isometric view)
    // and all 4 dimensions. Model-space geometry is projected into paper space at
    // extraction and is supposed to be drawn; the raster gets the same content because
    // ezdxf renders the paper layout's VIEWPORT, which pulls model space through it.
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

    // Manual-check picking, layered on top. When the mode is off this returns `handlers`
    // unchanged and no index, so the existing canvas behaves exactly as it did.
    const { entityHitIndex, handlers: canvasHandlers } = useEntityPicking({
      handlers,
      drawing,
      oldDrawing,
      canvasRef,
    });

    const {
      isDraggingRef,
      contextMenu,
      setContextMenu,
      isHoveringMarkerState,
      hoveredMarkerId,
      hoveredAnnotationId,
      cursorStyle,
      hoveredHandleId
    } = state;

    return (
      <div 
        className="drawing-canvas-viewport-container" 
        style={{ 
          position: 'relative', 
          width: '100%', 
          height: '100%', 
          overflow: 'hidden',
          border: 'none',
          borderRadius: '2px',
          boxShadow: theme === 'hc-light' ? 'inset 0 1px 3px rgba(15,23,42,0.06)' : 'none'
        }}
      >
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
            hoveredHandleId={hoveredHandleId}
            isHoveringMarkerState={isHoveringMarkerState}
            hoveredMarkerId={hoveredMarkerId}
            hoveredAnnotationId={hoveredAnnotationId}
            isNeonCAD={true}
            markerPositionsRef={markerPositionsRef}
            redrawTrigger={redrawTrigger}
            isDraggingRef={isDraggingRef}
            canvasInteractionHandlers={canvasHandlers}
            entityHitIndex={entityHitIndex}
            cursorStyle={cursorStyle}
            sharedCanvasRef={canvasRef}
          />
        </ErrorBoundary>

        <AnnotationSummaryOverlay drawingId={drawing?.id} theme={theme} />

        {/* No loading overlay here any more. It existed to cover the canvas while the ~8400px
            background PNG downloaded and its light-theme variant was built pixel by pixel.
            The vectors arrive with the layers payload and draw on the first frame, so there is
            nothing left to wait for. */}

        {contextMenu && contextMenu.visible && (
          <CanvasContextMenu
            x={contextMenu.x}
            y={contextMenu.y}
            wx={contextMenu.wx}
            wy={contextMenu.wy}
            drawingId={drawing?.id}
            canvasWidth={width}
            canvasHeight={height}
            theme={theme}
            onOpenAnnotationModal={(severity) => {
              setAnnotationModal({
                visible: true,
                x: contextMenu.x,
                y: contextMenu.y,
                wx: contextMenu.wx,
                wy: contextMenu.wy,
                severity,
                content: '',
              });
              setContextMenu(null);
            }}
            onClose={() => setContextMenu(null)}
            setRedrawTrigger={setRedrawTrigger}
          />
        )}

        {annotationModal && annotationModal.visible && (
          <AnnotationCreateModal
            x={annotationModal.x}
            y={annotationModal.y}
            wx={annotationModal.wx}
            wy={annotationModal.wy}
            severity={annotationModal.severity}
            drawingId={drawing?.id}
            canvasWidth={width}
            canvasHeight={height}
            theme={theme}
            onClose={() => setAnnotationModal(null)}
            setRedrawTrigger={setRedrawTrigger}
          />
        )}

        {(() => {
          if (!selectedAnnotationId || !Array.isArray(annotations)) return null;
          const selectedAnn = annotations.find((a) => a.id === selectedAnnotationId);
          if (!selectedAnn || selectedAnn.drawing_id !== drawing?.id) return null;
          const pos = markerPositionsRef.current ? markerPositionsRef.current[`ann:${selectedAnnotationId}`] : null;
          if (!pos) return null;

          return (
            <AnnotationCardPopover
              annotation={selectedAnn}
              badgeNumber={annotationBadgeMap ? annotationBadgeMap[selectedAnn.id] : undefined}
              x={pos.x}
              y={pos.y}
              canvasWidth={width}
              canvasHeight={height}
              theme={theme}
              onClose={() => selectAnnotation(null)}
              setRedrawTrigger={setRedrawTrigger}
            />
          );
        })()}
      </div>
    );
  }
);

const SEVERITY_ORDER: AnnotationSeverity[] = ['critical', 'high', 'medium', 'low', 'info'];

/**
 * Sticky, text-only warning summary for THIS canvas's open annotations — pinned
 * to the top-right corner so a reviewer can tell "this drawing has open notes"
 * without hunting the linework for a small '!' pin first. Each canvas gets its
 * own instance (mirrors the per-drawing filtering renderAnnotationPins already
 * does), so the old/new panes never leak counts into each other.
 */
const AnnotationSummaryOverlay: React.FC<{ drawingId?: string; theme: string }> = ({ drawingId, theme }) => {
  // Deliberately NOT gated behind showAnnotations — this is the passive "you have
  // open notes" signal, so it needs to work precisely when the panel/pins are
  // hidden. Gating it the same as the panel made it useless (it only appeared
  // once the panel was already open, which already lists everything).
  const annotations = useWorkspaceStore((s) => s.annotations);
  const selectAnnotation = useWorkspaceStore((s) => s.selectAnnotation);
  const toggleAnnotations = useReviewStore((s) => s.toggleAnnotations);
  const showAnnotations = useReviewStore((s) => s.showAnnotations);

  const openForDrawing = useMemo(
    () => (Array.isArray(annotations) ? annotations.filter((a) => a.drawing_id === drawingId && a.status !== 'resolved') : []),
    [annotations, drawingId]
  );

  if (!drawingId || openForDrawing.length === 0) return null;

  const counts: Partial<Record<AnnotationSeverity, number>> = {};
  openForDrawing.forEach((a) => {
    const sev = (a.severity as AnnotationSeverity) || 'info';
    counts[sev] = (counts[sev] || 0) + 1;
  });

  const presentSeverities = SEVERITY_ORDER.filter((s) => counts[s]);
  const summary = presentSeverities.map((s) => `${counts[s]} ${s[0].toUpperCase()}${s.slice(1)}`).join(' · ');

  // Clicking jumps to the single highest-severity open pin — reuses the
  // existing selectedAnnotationId zoom-to-focus effect in useCanvasInteraction.ts,
  // so this doubles as a one-click "take me to what matters most" shortcut. Also
  // opens the panel/pins if they were hidden, since that's the whole point of
  // clicking a summary that was visible precisely because they were hidden.
  const topSeverity = presentSeverities[0];
  const jumpTarget = openForDrawing.find((a) => a.severity === topSeverity);

  return (
    <div
      onClick={() => {
        if (!showAnnotations) toggleAnnotations();
        if (jumpTarget) selectAnnotation(jumpTarget.id);
      }}
      className={`absolute top-3 right-3 z-40 flex items-center gap-1.5 font-mono text-xs font-bold cursor-pointer transition-colors select-none drop-shadow-md max-w-[calc(100%-24px)] ${theme === 'hc-light'
          ? 'text-amber-700 hover:text-amber-600'
          : 'text-amber-300 hover:text-amber-200'
        }`}
    >
      <span className="shrink-0 text-red font-bold">⚠</span>
      <span className="truncate">
        {openForDrawing.length} Open Annotation{openForDrawing.length === 1 ? '' : 's'} — {summary}
      </span>
    </div>
  );
};
