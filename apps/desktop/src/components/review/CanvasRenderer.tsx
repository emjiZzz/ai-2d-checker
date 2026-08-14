import React, { useEffect, useRef, useState, useCallback, forwardRef, useImperativeHandle, useMemo } from 'react';
import { useReviewStore } from '../../stores/reviewStore';
import { DEFAULT_CUSTOM_REGIONS } from '../../utils/zoneFractions';
import { useWorkspaceStore } from '../../stores/workspaceStore';
import { useThemeStore } from '../../stores/themeStore';
import { getAnnotationBadgeMap } from '../../stores/workspace/types';
import { getNormalization, parseBounds } from '../../utils/coordinateTransform';
import { renderEntities, renderViolationReticles, renderAnnotationPins, renderZoneEditor, renderViewOrigins } from './renderEntities';
import { entitiesFromLayers, viewDatumsFromTransform } from './viewDatums';
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
  markerPositionsRef: React.MutableRefObject<Record<string, { x: number, y: number }>>;
  redrawTrigger: number;
  canvasInteractionHandlers: any;
  cursorStyle: string;
  sharedCanvasRef?: React.RefObject<HTMLCanvasElement | null>;
  isDraggingRef?: React.MutableRefObject<boolean>;
  /** Handle under the cursor (or being dragged) in zone-edit mode, for highlighting. */
  hoveredHandleId?: string | null;
}

// Memoized: with a stable `canvasInteractionHandlers` object (see
// useCanvasInteraction) and value-stable `cursorStyle`, a parent re-render
// caused by an unrelated DrawingCanvas state change (e.g. the throttled render
// diagnostics flush) no longer cascades into a canvas re-render.
export const CanvasRenderer = React.memo(forwardRef<DrawingCanvasRef, CanvasRendererProps>(({
  width,
  height,
  layers,
  drawing,
  hoveredMarkerId,
  hoveredAnnotationId,
  isNeonCAD,
  markerPositionsRef,
  redrawTrigger,
  canvasInteractionHandlers,
  cursorStyle,
  sharedCanvasRef,
  isDraggingRef,
  hoveredHandleId
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
  const showViewOrigins = useReviewStore(s => s.showViewOrigins);

  const selectedViolation = useWorkspaceStore((s) => s.selectedViolation);
  const violations = useWorkspaceStore((s) => s.violations);
  const hiddenViolationIds = useWorkspaceStore((s) => s.hiddenViolationIds);
  const oldDrawing = useWorkspaceStore((s) => s.oldDrawing);
  const annotations = useWorkspaceStore((s) => s.annotations);
  const selectedAnnotationId = useWorkspaceStore((s) => s.selectedAnnotationId);
  const showAnnotations = useReviewStore((s) => s.showAnnotations);
  const annotationBadgeMap = useMemo(() => getAnnotationBadgeMap(annotations), [annotations]);
  // Zone debug overlay. Read from the store rather than threaded as props: this
  // component already receives its own `drawing`, so `zoneRegions[drawing.id]` is
  // unambiguous without a side discriminator — the same way annotation pins are
  // filtered by `drawing.id` below.
  const zoneRegions = useWorkspaceStore((s) => s.zoneRegions);
  const isRoiEditModeEnabled = useReviewStore((s) => s.isRoiEditModeEnabled);
  const allCustomRegions = useReviewStore((s) => s.customRegions);
  // Which zones came from the hand-aligned template. Drives the guess marker: a pinned zone
  // is not something the detector anchored, so confidence alone would draw it as a guess.
  const allPinnedZoneKeys = useReviewStore((s) => s.pinnedZoneKeys);
  const selectedComparisonRegion = useReviewStore((s) => s.selectedComparisonRegion);
  const theme = useThemeStore((s) => s.theme);
  // devicePixelRatio, tracked live rather than read once. `drawCanvas` reads a fresh value from
  // `window` on every frame, so if this one goes stale — dragging the window to a monitor with
  // different OS scaling is the way that happens — the render transform and the backing store
  // disagree and the canvas goes blurry until some unrelated state change forces a re-render.
  // matchMedia is the only DPR-change signal browsers expose, and the query is resolution-
  // specific rather than a standing subscription, so it has to be re-armed after each fire.
  const [dpr, setDpr] = useState(() => (typeof window !== 'undefined' ? window.devicePixelRatio || 1 : 1));
  useEffect(() => {
    if (typeof window === 'undefined') return;
    let mql: MediaQueryList | null = null;
    let cancelled = false;
    const arm = () => {
      if (cancelled) return;
      const next = window.devicePixelRatio || 1;
      setDpr(next);
      mql = window.matchMedia(`(resolution: ${next}dppx)`);
      mql.addEventListener('change', arm, { once: true });
    };
    arm();
    return () => {
      cancelled = true;
      mql?.removeEventListener('change', arm);
    };
  }, []);

  // Backing store and CSS size are both derived from ONE rounded device-pixel figure, so that
  // `cssPx * dpr === backingPx` holds exactly and the bitmap maps 1:1 onto physical pixels.
  //
  // This is the difference between a crisp canvas and a blurry one, and it is easy to get
  // wrong: `width`/`height` arrive from a ResizeObserver's `contentRect`, which reports
  // FRACTIONAL sizes (a flex column happily produces 689.6px). Sizing the element with
  // `width: 100%` while the backing store was `Math.round(689.6 * dpr)` left the browser
  // rescaling a 690px bitmap into a 689.6px box — a non-integer resample applied to every
  // pixel on the canvas, which reads as a uniform softness at every zoom level and survives
  // any amount of work on the renderer itself.
  const backingW = Math.round(width * dpr);
  const backingH = Math.round(height * dpr);

  const visibleViolations = useMemo(() => {
    return violations.filter(v => !hiddenViolationIds[v.id]);
  }, [violations, hiddenViolationIds]);

  // Each view's own origin. Memoized because finding it walks every entity on the sheet looking
  // for centrelines and concentric curves, and `renderViewOrigins` runs on every pan frame. Only
  // one of these per sheet comes from the file; the rest are inferred and drawn dashed. See
  // `viewDatums.ts`.
  const viewDatums = useMemo(
    () => viewDatumsFromTransform(drawing?.metadata?.viewport_transform, entitiesFromLayers(layers)),
    [drawing, layers],
  );

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
  }), [drawing, activeLayers, showViolations, showMarkerLabels, violations, hiddenViolationIds, selectedViolation, isNeonCAD, theme, oldDrawing, hoveredMarkerId, hoveredAnnotationId, visibleMarkerTypes, showViewOrigins]);

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
      ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue('--bg-canvas').trim() || '#262b36';
    }
    ctx.fillRect(0, 0, renderWidth, renderHeight);

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

    const isDragging = isDraggingRef?.current ?? false;
    const isNeonModeActive = isNeonCAD && !isDragging;
    ctx.filter = "none";

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
      drawing
    });

    // Per-view ORIGIN markers, above the geometry so they read as an overlay. Drawn during
    // drag too: they are three tiny paths, and the point of a datum marker is that it tracks
    // the geometry while you pan.
    if (showViewOrigins) {
      renderViewOrigins({ frame: frameData, datums: viewDatums });
    }

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

      // Always render annotation pins on the canvas even when the side panel is collapsed
      renderAnnotationPins({
        // Only this drawing's pins. Coordinates are in the owning drawing's
        // CAD space, so rendering all of them on every pane put pins at
        // meaningless positions on the opposite drawing.
        frame: frameData,
        annotations: Array.isArray(annotations) ? annotations.filter((a) => a.drawing_id === drawing?.id) : [],
        selectedAnnotationId,
        hoveredAnnotationId,
        badgeMap: annotationBadgeMap,
      });
    }

    // Zone debug boxes, drawn last so they sit above geometry and pins. Indexed by
    // this pane's own drawing id for the same reason annotation pins are filtered by
    // it above: zone boxes are in the owning drawing's CAD space, so showing the
    // reference's boxes over the revision would put them at meaningless positions.
    // Rendered during drag too — unlike reticles these are cheap (7 rects) and the
    // whole point is that they track the geometry while panning.
    // Zone boxes render only in alignment mode. There is no separate read-only overlay:
    // two near-identical box sets with different meanings made it impossible to tell which
    // one a drag affected. Geometry is the editable `customRegions`; the detected payload
    // rides along only so each box can report whether the detector measured it or guessed.
    if (isRoiEditModeEnabled && drawing?.metadata?.render_bounds) {
      renderZoneEditor({
        frame: frameData,
        customRegions: (drawing?.id && allCustomRegions[drawing.id]) || DEFAULT_CUSTOM_REGIONS,
        renderBounds: drawing.metadata.render_bounds,
        selectedRegion: selectedComparisonRegion,
        hoveredHandleId: hoveredHandleId ?? null,
        detected: drawing?.id ? zoneRegions[drawing.id] : null,
        // Read from the subscribed map, not the store getter: a getter call inside this
        // effect would not re-run the render when the template finishes loading.
        pinnedKeys: (drawing?.id && allPinnedZoneKeys[drawing.id]) || [],
      });
    }

    ctx.restore();



    return stats;
  }, [layers, width, height, activeLayers, showViolations, showMarkerLabels, violations, hiddenViolationIds, selectedViolation, drawing, isNeonCAD, theme, oldDrawing, hoveredMarkerId, hoveredAnnotationId, visibleMarkerTypes, markerPositionsRef, showAnnotations, annotations, selectedAnnotationId, annotationBadgeMap, showViewOrigins, zoneRegions, isRoiEditModeEnabled, allCustomRegions, allPinnedZoneKeys, selectedComparisonRegion, hoveredHandleId]);

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

    renderContent(ctx, false);
  }, [renderContent]);

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
      width={backingW}
      height={backingH}
      {...domHandlers}
      style={{
        cursor: cursorStyle,
        display: 'block',
        // Explicit px, NOT '100%' — see the backingW/backingH note above. The parent wrapper
        // is overflow:hidden, so the sub-pixel remainder between this and the container is
        // clipped rather than scrolled.
        width: `${backingW / dpr}px`,
        height: `${backingH / dpr}px`
      }}
    />
  );
}));
