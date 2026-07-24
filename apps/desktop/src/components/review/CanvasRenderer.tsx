import React, { useEffect, useRef, useCallback, forwardRef, useImperativeHandle, useMemo } from 'react';
import { useReviewStore } from '../../stores/reviewStore';
import { useWorkspaceStore } from '../../stores/workspaceStore';
import { useThemeStore } from '../../stores/themeStore';
import { getAnnotationBadgeMap } from '../../stores/workspace/types';
import { getNormalization, parseBounds } from '../../utils/coordinateTransform';
import { renderEntities, renderViolationReticles, renderAnnotationPins } from './renderEntities';
import { DrawingCanvasRef } from './DrawingCanvas';

interface CanvasRendererProps {
  width: number;
  height: number;
  layers: any;
  drawing: any;
  isHoveringMarkerState: boolean;
  hoveredMarkerId: string | null;
  hoveredAnnotationId?: string | null;
  isNeonCAD: boolean;
  bgImage: HTMLImageElement | null;
  lightBgImage: HTMLImageElement | null;
  setRenderDiagnostics: (stats: { entityCount: number, drawCount: number, renderTimeMs: number }) => void;
  markerPositionsRef: React.MutableRefObject<Record<string, { x: number, y: number }>>;
  redrawTrigger: number;
  canvasInteractionHandlers: any;
  cursorStyle: string;
  sharedCanvasRef?: React.RefObject<HTMLCanvasElement | null>;
  isDraggingRef?: React.MutableRefObject<boolean>;
}

export const CanvasRenderer = forwardRef<DrawingCanvasRef, CanvasRendererProps>(({
  width,
  height,
  layers,
  drawing,
  hoveredMarkerId,
  hoveredAnnotationId,
  isNeonCAD,
  bgImage,
  lightBgImage,
  setRenderDiagnostics,
  markerPositionsRef,
  redrawTrigger,
  canvasInteractionHandlers,
  cursorStyle,
  sharedCanvasRef,
  isDraggingRef
}, ref) => {
  const internalCanvasRef = useRef<HTMLCanvasElement>(null);
  // If DrawingCanvas passes its own ref (used by the interaction hook), use it;
  // otherwise fall back to an internal one so CanvasRenderer always has a ref.
  const canvasRef = (sharedCanvasRef as React.RefObject<HTMLCanvasElement>) ?? internalCanvasRef;
  const rafId = useRef<number | null>(null);
  /** Holds the latest viewport value. Updated via store subscription — avoids React re-renders on every pan pixel. */
  const viewportRef = useRef(useReviewStore.getState().viewport);
  /** Stable ref to the latest drawCanvas — used by the imperative viewport subscription below. */
  const drawCanvasFnRef = useRef<() => void>(() => { });

  // viewport intentionally NOT subscribed via React hook — managed via viewportRef + store subscription
  const activeLayers = useReviewStore(s => s.activeLayers);
  const showViolations = useReviewStore(s => s.showViolations);
  const showMarkerLabels = useReviewStore(s => s.showMarkerLabels);
  const visibleMarkerTypes = useReviewStore(s => s.visibleMarkerTypes);

  const selectedViolation = useWorkspaceStore((s) => s.selectedViolation);
  const violations = useWorkspaceStore((s) => s.violations);
  const hiddenViolationIds = useWorkspaceStore((s) => s.hiddenViolationIds);
  const oldDrawing = useWorkspaceStore((s) => s.oldDrawing);
  const annotations = useWorkspaceStore((s) => s.annotations);
  const selectedAnnotationId = useWorkspaceStore((s) => s.selectedAnnotationId);
  const showAnnotations = useReviewStore((s) => s.showAnnotations);
  const annotationBadgeMap = useMemo(() => getAnnotationBadgeMap(annotations), [annotations]);
  const theme = useThemeStore((s) => s.theme);
  const dpr = typeof window !== 'undefined' ? window.devicePixelRatio || 1 : 1;

  const visibleViolations = useMemo(() => {
    return violations.filter(v => !hiddenViolationIds[v.id]);
  }, [violations, hiddenViolationIds]);

  // Expose canvasRef for interaction layer
  useImperativeHandle(ref, () => ({
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
    },
    getCanvasElement: () => canvasRef.current
  }), [drawing, activeLayers, showViolations, showMarkerLabels, violations, hiddenViolationIds, selectedViolation, bgImage, isNeonCAD, theme, lightBgImage, oldDrawing, hoveredMarkerId, hoveredAnnotationId, visibleMarkerTypes]);

  // Subscribe to viewport changes without triggering React re-renders.
  // On every setViewport call (each mouse pixel during pan), we update the ref and schedule
  // a canvas repaint directly via RAF — completely bypassing the React render pipeline.
  useEffect(() => {
    viewportRef.current = useReviewStore.getState().viewport;
    const unsub = useReviewStore.subscribe((state) => {
      if (state.viewport !== viewportRef.current) {
        viewportRef.current = state.viewport;
        if (rafId.current) cancelAnimationFrame(rafId.current);
        rafId.current = requestAnimationFrame(() => drawCanvasFnRef.current());
      }
    });
    return unsub;
  }, []);

  const renderContent = useCallback((ctx: CanvasRenderingContext2D, isExport: boolean, renderWidth: number = width, renderHeight: number = height) => {
    // Read viewport from ref — decoupled from React closure, stays fresh during pan without causing re-renders
    const viewport = viewportRef.current;
    const norm = getNormalization(parseBounds(drawing?.metadata?.render_bounds));
    const normalizationScale = norm.normScale;
    const normXMin = norm.xmin;
    const normYMin = norm.ymin;

    const effectiveScale = viewport.scale * normalizationScale;
    const resolutionMultiplier = renderWidth / width;

    // 1. Clear infinite background
    if (isExport) {
      ctx.fillStyle = '#ffffff';
    } else {
      ctx.fillStyle = theme === 'hc-light' ? '#fafafa' : '#262b36';
    }
    ctx.fillRect(0, 0, renderWidth, renderHeight);

    // 2. Draw fine engineering grids
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

      // Batch ALL grid lines into one Path2D — avoids ~40+ individual GPU flushes per frame
      const gridPath = new Path2D();
      const kStartX = Math.floor((0 - screenOriginX) / screenSpacing);
      const kEndX = Math.ceil((renderWidth - screenOriginX) / screenSpacing);
      for (let k = kStartX; k <= kEndX; k++) {
        const sx = Math.round(screenOriginX + k * screenSpacing);
        gridPath.moveTo(sx, 0);
        gridPath.lineTo(sx, renderHeight);
      }
      const kStartY = Math.floor((0 - screenOriginY) / screenSpacing);
      const kEndY = Math.ceil((renderHeight - screenOriginY) / screenSpacing);
      for (let k = kStartY; k <= kEndY; k++) {
        const sy = Math.round(screenOriginY + k * screenSpacing);
        gridPath.moveTo(0, sy);
        gridPath.lineTo(renderWidth, sy);
      }
      ctx.stroke(gridPath);
      ctx.restore();
    }

    // 3. Setup transformations
    let scale = effectiveScale;
    let transX = viewport.x - normXMin * effectiveScale;
    let transY = viewport.y - normYMin * effectiveScale;

    if (isExport && drawing?.metadata?.render_bounds) {
      const [xmin, ymin, xmax, ymax] = drawing.metadata.render_bounds;
      const drawingW = xmax - xmin;
      const drawingH = ymax - ymin;
      if (drawingW > 0 && drawingH > 0) {
        const padding = Math.max(30, Math.round(renderWidth * 0.04));
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
    const isDragging = isDraggingRef?.current ?? false;
    const isNeonModeActive = isNeonCAD && !isDragging;

    if (isNeonModeActive && !isExport) {
      currentFilter = "contrast(1.25) brightness(1.15) saturate(1.35) hue-rotate(2deg)";
    }
    ctx.filter = currentFilter;

    // 4. Viewport bounds in world coordinates
    const minX = -transX / scale;
    const minY = -transY / scale;
    const maxX = (renderWidth - transX) / scale;
    const maxY = (renderHeight - transY) / scale;
    const currentViewportScale = scale / normalizationScale;

    const frameData = {
      ctx,
      isExport,
      renderWidth,
      renderHeight,
      width,
      height,
      norm,
      scale,
      transX,
      transY,
      minX,
      minY,
      maxX,
      maxY,
      currentViewportScale,
      resolutionMultiplier,
      viewport,
      markerPositionsRef,
      isNeonModeActive
    };

    // Call extracted modular renderers
    const stats = renderEntities({
      frame: frameData,
      layers,
      activeLayers,
      theme,
      bgImage,
      lightBgImage,
      drawing
    });

    // Only render violation reticles when not actively panning/zooming — they're static
    // during interaction and rendering them is expensive (O(violations) per frame).
    if (!isDragging) {
      renderViolationReticles({
        frame: frameData,
        violations: visibleViolations,
        showViolations,
        showMarkerLabels,
        hoveredMarkerId,
        selectedViolation,
        drawing,
        oldDrawing,
        visibleMarkerTypes
      });

      if (showAnnotations) {
        renderAnnotationPins({
          // Only this drawing's pins. Coordinates are in the owning drawing's
          // CAD space, so rendering all of them on every pane put pins at
          // meaningless positions on the opposite drawing.
          frame: frameData,
          annotations: annotations.filter((a) => a.drawing_id === drawing?.id),
          selectedAnnotationId,
          hoveredAnnotationId,
          badgeMap: annotationBadgeMap,
        });
      }
    }

    ctx.restore();



    return stats;
  }, [layers, width, height, activeLayers, showViolations, showMarkerLabels, violations, hiddenViolationIds, selectedViolation, bgImage, drawing, isNeonCAD, theme, lightBgImage, oldDrawing, hoveredMarkerId, hoveredAnnotationId, visibleMarkerTypes, markerPositionsRef, showAnnotations, annotations, selectedAnnotationId, annotationBadgeMap]);

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
  }, [renderContent, setRenderDiagnostics]);

  // Keep drawCanvasFnRef current so the viewport subscription always calls the latest version
  useEffect(() => {
    drawCanvasFnRef.current = drawCanvas;
  });

  // Schedule canvas redraws for all non-viewport invalidations (layer toggles, violations, hover, etc.).
  // Viewport-driven redraws are handled imperatively by the store subscription above.
  useEffect(() => {
    if (rafId.current) cancelAnimationFrame(rafId.current);
    rafId.current = requestAnimationFrame(() => {
      drawCanvasFnRef.current();
    });
    return () => {
      if (rafId.current) cancelAnimationFrame(rafId.current);
    };
  }, [drawCanvas, redrawTrigger]);

  // Register wheel as non-passive so e.preventDefault() actually prevents page scroll
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !canvasInteractionHandlers.onWheel) return;
    const handler = (e: WheelEvent) => {
      e.preventDefault();
      // Wrap into a synthetic-like object the hook's handler expects
      canvasInteractionHandlers.onWheel(e as any);
    };
    canvas.addEventListener('wheel', handler, { passive: false });
    return () => canvas.removeEventListener('wheel', handler);
  }, [canvasInteractionHandlers.onWheel]);

  // Spread all handlers EXCEPT onWheel (handled natively above to allow e.preventDefault)
  const { onWheel: _onWheel, ...domHandlers } = canvasInteractionHandlers;

  return (
    <canvas
      ref={canvasRef}
      width={width * dpr}
      height={height * dpr}
      {...domHandlers}
      style={{
        cursor: cursorStyle,
        display: 'block',
        width: '100%',
        height: '100%'
      }}
    />
  );
});
