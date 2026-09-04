import React, { useEffect, useRef, useState, useCallback, forwardRef, useImperativeHandle, useMemo } from 'react';
import { useReviewStore } from '../../stores/reviewStore';
import { DEFAULT_CUSTOM_REGIONS } from '../../utils/zoneFractions';
import { useWorkspaceStore } from '../../stores/workspaceStore';
import { useThemeStore } from '../../stores/themeStore';
import { getAnnotationBadgeMap } from '../../stores/workspace/types';
import { getNormalization, parseBounds } from '../../utils/coordinateTransform';
import { renderEntities, renderViolationReticles, renderAnnotationPins, renderZoneEditor, renderViewOrigins, renderSelectionHighlight, renderPenStrokes } from './renderEntities';
import { entitiesFromLayers, viewDatumsFromTransform } from './viewDatums';
import { DrawingCanvasRef } from './DrawingCanvas';
import { EntityHitIndex } from './entityPicking';
import { renderManualMarkings } from './renderManualMarkings';
import { useIsManualCheckRoom } from "../../hooks/useManualCheckRoom";
import { markingsToMarkers } from './markerStyles';
import {
  computeExportFit,
  cropIsWorthwhile,
  findInkBounds,
  fitSpaceFromPixels,
  resolutionMultiplierFor,
  type FitRect,
} from './exportFit';

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
  /** Manual-check picking index. Undefined outside manual mode, where it costs nothing. */
  entityHitIndex?: EntityHitIndex;
  redrawTrigger: number;
  canvasInteractionHandlers: any;
  cursorStyle: string;
  sharedCanvasRef?: React.RefObject<HTMLCanvasElement | null>;
  isDraggingRef?: React.MutableRefObject<boolean>;
  /** Handle under the cursor (or being dragged) in zone-edit mode, for highlighting. */
  hoveredHandleId?: string | null;
  currentStrokeRef?: React.MutableRefObject<{ points: [number, number][]; color: string; width: number } | null>;
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
  entityHitIndex,
  redrawTrigger,
  canvasInteractionHandlers,
  cursorStyle,
  sharedCanvasRef,
  isDraggingRef,
  hoveredHandleId,
  currentStrokeRef,
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
  const showViolationsPref = useReviewStore(s => s.showViolations);
  const isManualCheckMode = useIsManualCheckRoom();
  const manualMarkings = useWorkspaceStore((s) => s.markings);
  const hoveredEntityId = useWorkspaceStore((s) => s.hoveredEntityId);
  // Selection is part of the canvas's mouse scheme in EVERY room, not a manual-check feature,
  // so this is read outside the manual gate below.
  const selectedEntities = useWorkspaceStore((s) => s.selectedEntities);
  const pendingPairRef = useWorkspaceStore((s) => s.pendingPairRef);
  const hoverLocator = useWorkspaceStore((s) => s.hoverLocator);
  const selectionLocator = useWorkspaceStore((s) => s.selectionLocator);
  // Manual check mode shows no engine output. Not decoration: a checker who can see what the
  // engine concluded is no longer an independent observer, and independence is the only reason
  // these markings are worth more than the corrections we already collect. The user's own
  // `showViolations` preference is read but not written, so leaving the mode restores it.
  const showViolations = showViolationsPref && !isManualCheckMode;
  const showMarkerLabels = useReviewStore(s => s.showMarkerLabels);
  const visibleMarkerTypes = useReviewStore(s => s.visibleMarkerTypes);
  const showViewOrigins = useReviewStore(s => s.showViewOrigins);

  const selectedViolation = useWorkspaceStore((s) => s.selectedViolation);
  const violations = useWorkspaceStore((s) => s.violations);
  const hiddenViolationIds = useWorkspaceStore((s) => s.hiddenViolationIds);
  const oldDrawing = useWorkspaceStore((s) => s.oldDrawing);
  const annotations = useWorkspaceStore((s) => s.annotations);
  const selectedAnnotationId = useWorkspaceStore((s) => s.selectedAnnotationId);
  const penStrokes = useWorkspaceStore((s) => s.penStrokes);
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

  const renderContent = useCallback((ctx: CanvasRenderingContext2D, isExport: boolean, renderWidth: number = width, renderHeight: number = height, fitOverride: FitRect | null = null) => {
    // Read viewport from ref — decoupled from React closure, stays fresh during pan without causing re-renders
    const viewport = viewportRef.current;
    const norm = getNormalization(parseBounds(drawing?.metadata?.render_bounds));
    const normalizationScale = norm.normScale;
    const normXMin = norm.xmin;
    const normYMin = norm.ymin;

    const effectiveScale = viewport.scale * normalizationScale;
    const resolutionMultiplier = resolutionMultiplierFor(isExport, renderWidth, width);

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

    // `fitOverride` is how the two-pass export crops to the ink: pass one fits `render_bounds`
    // and measures what was actually painted, pass two comes back through here with that
    // rectangle. Absent, this is the historical behaviour.
    const exportRect: FitRect | null =
      fitOverride ??
      (isExport && drawing?.metadata?.render_bounds
        ? (drawing.metadata.render_bounds.slice(0, 4) as FitRect)
        : null);

    if (isExport && exportRect && exportRect[2] - exportRect[0] > 0 && exportRect[3] - exportRect[1] > 0) {
      const fit = computeExportFit(exportRect, renderWidth, renderHeight);
      scale = fit.scale;
      transX = fit.transX;
      transY = fit.transY;
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
      entityHitIndex,
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

    // The selection, above the geometry and below everything else. `renderEntities` has just
    // rebuilt the pick index this reads, so the outlines are this frame's hitboxes rather than
    // the previous frame's. Filtered to THIS canvas's drawing: a selection carries the id of
    // the sheet it was made on, and the two panes share this component.
    renderSelectionHighlight({
      frame: frameData,
      entityIds: drawing?.id
        ? selectedEntities
            .filter((p) => p.drawingId === String(drawing.id))
            .map((p) => p.entityId)
        : [],
    });

    // What the engineer has recorded, drawn through the SAME renderer as engine findings —
    // same bullet, same detail card, same Show Labels toggle, same colour per status. They were
    // two visual languages for one idea until 2026-08-18, disagreeing about what colour
    // `MATCHED` is.
    //
    // Called separately rather than concatenated into `visibleViolations` because
    // `showViolations` is forced FALSE in a manual room — a checker who can see the engine's
    // conclusions is no longer an independent observer. The gate is about the engine's output,
    // not about the renderer, so the engineer's own markings pass `showViolations: true`.
    if (isManualCheckMode) {
      renderViolationReticles({
        frame: frameData,
        violations: markingsToMarkers(manualMarkings),
        showViolations: true,
        showMarkerLabels,
        hoveredMarkerId,
        selectedViolation,
        drawing,
        oldDrawing,
        visibleMarkerTypes,
      });
    }

    // What the engineer has recorded, drawn back onto the sheet. Above the geometry because it
    // is an overlay, and only in a manual-check room — an AI room has no markings and the call
    // would be a no-op with a per-frame cost.
    if (isManualCheckMode) {
      renderManualMarkings({
        frame: frameData,
        // Which sheet this canvas shows. A CHANGED marking holds a different coordinate per
        // side, so the wrong answer here puts every paired badge on the wrong drawing.
        side: oldDrawing && drawing?.id === oldDrawing.id ? 'ref' : 'rev',
        hoveredEntityId,
        entityHitIndex,
        pendingPairRef,
        hoverLocator,
        // Passed straight through. It was briefly gated on the selection belonging to a drawing
        // THIS pane knows about, which silently broke the feature in one direction: both panes
        // read `oldDrawing` from the store, so the reference pane only ever knows the reference's
        // id and rejected every revision-side selection — killing the outline on exactly the
        // sheet the engineer turns to after clicking. Staleness across a drawing switch is
        // handled where it is knowable, by `TwoDWorkspace` clearing the selection when the pair
        // changes; a renderer cannot tell a stale id from one belonging to the other pane.
        selectionLocator,
        // This canvas's own zones — `zoneRegions` is keyed by drawing, and confining a match
        // to the same zone is what stops a BOM value matching the same value in a view.
        zones: drawing?.id ? zoneRegions[drawing.id] : null,
      });
    }

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

    // Freehand pen strokes drawn on this sheet
    renderPenStrokes({
      frame: frameData,
      strokes: Array.isArray(penStrokes) ? penStrokes : [],
      currentStroke: currentStrokeRef?.current,
      drawingId: drawing?.id ? String(drawing.id) : undefined,
    });

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
  }, [layers, width, height, activeLayers, showViolations, isManualCheckMode, manualMarkings, hoveredEntityId, selectedEntities, pendingPairRef, hoverLocator, selectionLocator, showMarkerLabels, violations, hiddenViolationIds, selectedViolation, drawing, isNeonCAD, theme, oldDrawing, hoveredMarkerId, hoveredAnnotationId, visibleMarkerTypes, markerPositionsRef, entityHitIndex, showAnnotations, annotations, selectedAnnotationId, annotationBadgeMap, showViewOrigins, zoneRegions, isRoiEditModeEnabled, allCustomRegions, allPinnedZoneKeys, selectedComparisonRegion, hoveredHandleId, penStrokes, currentStrokeRef]);


  /**
   * Expose the canvas to the interaction layer, and the sheet itself to the PDF report.
   *
   * The dependency is `renderContent` and nothing else, and it must stay that way. This
   * hand-listed fourteen of `renderContent`'s thirty-odd inputs — omitting `layers`,
   * `manualMarkings`, `annotations`, `width` and `height` among others — so the handle captured
   * whichever `renderContent` existed the last time one of those fourteen moved. Layers arrive
   * after the drawing they belong to, which put an EMPTY-layer closure in the exported handle:
   * the report's drawing pages rendered their white background and no geometry. A marking made
   * after the last captured change was likewise absent, which is the same defect wearing the
   * costume the engineer would notice — checkmarks missing from their own report.
   *
   * Declared below `renderContent` rather than above it because naming it in a dependency array
   * evaluates it during render, and a `const` referenced before its own declaration is a TDZ
   * ReferenceError, not a stale value.
   */
  useImperativeHandle(ref, () => ({
    exportImage: (exportWidth?: number, exportHeight?: number) => {
      const canvas = document.createElement('canvas');
      const targetW = exportWidth || 3396;
      const targetH = exportHeight || 2352;
      canvas.width = targetW;
      canvas.height = targetH;
      const ctx = canvas.getContext('2d');
      if (!ctx) return '';
      ctx.imageSmoothingEnabled = true;
      ctx.imageSmoothingQuality = 'high';

      // Pass one: the historical `render_bounds` fit, which is what tells us where the ink is.
      renderContent(ctx, true, targetW, targetH);

      // Pass two: the same render, cropped to what pass one actually painted.
      //
      // At full resolution, not on a small probe. A cheaper low-res first pass would be tempting
      // and wrong: `renderEntities` culls text below one pixel high, so a probe answers the
      // question for a DIFFERENT set of entities than the final render draws — and the labels it
      // drops are the small ones at the edges of the sheet, which are exactly the ones a crop
      // must not cut off.
      const rect = drawing?.metadata?.render_bounds?.slice(0, 4) as FitRect | undefined;
      if (rect && rect[2] - rect[0] > 0 && rect[3] - rect[1] > 0) {
        const firstFit = computeExportFit(rect, targetW, targetH);
        const ink = findInkBounds(ctx, targetW, targetH);
        if (ink && cropIsWorthwhile(ink, targetW, targetH, firstFit.padding)) {
          const topLeft = fitSpaceFromPixels(firstFit, ink[0], ink[1]);
          const bottomRight = fitSpaceFromPixels(firstFit, ink[2], ink[3]);
          ctx.setTransform(1, 0, 0, 1, 0, 0);
          renderContent(ctx, true, targetW, targetH, [
            topLeft.x,
            topLeft.y,
            bottomRight.x,
            bottomRight.y,
          ]);
        }
      }

      return canvas.toDataURL('image/png');
    },
    getCanvasElement: () => canvasRef.current
  }), [renderContent, drawing]);

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
