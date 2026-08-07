import { useState, useEffect, useCallback, RefObject, useRef, useMemo } from 'react';
import { useReviewStore } from '../../stores/reviewStore';
import {
  DEFAULT_CUSTOM_REGIONS,
  insertPointOnEdge,
  isPolygonZone,
  movePointTo,
  removePointAt,
  shapePointsToScreen,
  translateShape,
} from '../../utils/zoneFractions';
import { useWorkspaceStore } from '../../stores/workspaceStore';
import { recordHistory } from '../../stores/historyStore';
import type { RegionFractions } from '../../utils/zoneFractions';
import { getNormalization, screenToWorld, screenToWorldUnflipped, screenDeltaToWorldDelta, parseBounds, clampViewport as clampViewportShared } from '../../utils/coordinateTransform';
import { hitTestMarker, getRoiDragPercentages } from './canvasInteraction';

interface UseCanvasInteractionProps {
  canvasRef: RefObject<HTMLCanvasElement | null>;
  width: number;
  height: number;
  drawing: any;
  oldDrawing: any;
  setRedrawTrigger: React.Dispatch<React.SetStateAction<number>>;
  markerPositionsRef: React.MutableRefObject<Record<string, { x: number, y: number }>>;
}

type ScreenPoint = { x: number; y: number };

/**
 * Index of the edge within `tolerance` px of (mx, my), or null.
 *
 * Edge *i* runs from vertex i to vertex i+1, wrapping — the same numbering
 * `insertPointOnEdge` uses, so the ghost node the hint draws and the node the click creates
 * are always the same point.
 *
 * Distance is to the SEGMENT, not to the infinite line: near a corner the perpendicular
 * distance to a line stays small far outside the shape, which would light up an edge hint
 * while the cursor sits well off the zone.
 */
function nearestEdgeWithin(
  points: ScreenPoint[],
  mx: number,
  my: number,
  tolerance: number,
): number | null {
  let best: number | null = null;
  let bestDist = tolerance;
  for (let i = 0; i < points.length; i += 1) {
    const a = points[i];
    const b = points[(i + 1) % points.length];
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const lenSq = dx * dx + dy * dy;
    // A zero-length edge has no direction to project onto; skip rather than divide by zero.
    if (lenSq === 0) continue;
    const t = Math.max(0, Math.min(1, ((mx - a.x) * dx + (my - a.y) * dy) / lenSq));
    const dist = Math.hypot(mx - (a.x + t * dx), my - (a.y + t * dy));
    if (dist < bestDist) {
      bestDist = dist;
      best = i;
    }
  }
  return best;
}

/** Winding test in SCREEN space, so the body-drag target matches the drawn outline. */
function pointInScreenShape(points: ScreenPoint[], mx: number, my: number): boolean {
  let inside = false;
  for (let i = 0, j = points.length - 1; i < points.length; j = i, i += 1) {
    const a = points[i];
    const b = points[j];
    if (a.y > my !== b.y > my && mx < ((b.x - a.x) * (my - a.y)) / (b.y - a.y) + a.x) {
      inside = !inside;
    }
  }
  return inside;
}

export function useCanvasInteraction({
  canvasRef,
  width,
  height,
  drawing,
  oldDrawing,
  setRedrawTrigger,
  markerPositionsRef
}: UseCanvasInteractionProps) {
  const setViewport = useReviewStore(s => s.setViewport);
  const showViolations = useReviewStore(s => s.showViolations);
  const isRoiEditModeEnabled = useReviewStore(s => s.isRoiEditModeEnabled);
  const selectedComparisonRegion = useReviewStore(s => s.selectedComparisonRegion);
  // This hook runs once per canvas pane, and `drawing` is that pane's own drawing — so the
  // pane edits its own zone boxes. Reference and revision differ in content extent (notes
  // as one sentence vs an ordered list), which a shared set could not express.
  const allCustomRegions = useReviewStore(s => s.customRegions);
  const customRegions = (drawing?.id && allCustomRegions[drawing.id]) || DEFAULT_CUSTOM_REGIONS;
  const updateCustomRegion = useReviewStore(s => s.updateCustomRegion);

  const selectedViolation = useWorkspaceStore((s) => s.selectedViolation);
  const selectViolation = useWorkspaceStore((s) => s.selectViolation);
  const violations = useWorkspaceStore((s) => s.violations);

  const isPlacingAnnotation = useWorkspaceStore((s) => s.isPlacingAnnotation);
  const createAnnotationAt = useWorkspaceStore((s) => s.createAnnotationAt);
  const showAnnotations = useReviewStore((s) => s.showAnnotations);
  const selectedAnnotationId = useWorkspaceStore((s) => s.selectedAnnotationId);
  // Removed subscription to prevent re-renders, we use .getState() instead
  // const hiddenViolationIds = useWorkspaceStore(s => s.hiddenViolationIds);
  const setViolations = useWorkspaceStore((s) => s.setViolations);

  const [isDragging, setIsDragging] = useState(false);
  const isDraggingRef = useRef(false);
  const dragDebounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mouseDownRawPosRef = useRef({ x: 0, y: 0 });
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const [isSpacePressed, setIsSpacePressed] = useState(false);

  // Draggable Markers State
  const [dragMarkerId, setDragMarkerId] = useState<string | null>(null);
  const [hoveredMarkerId, setHoveredMarkerId] = useState<string | null>(null);
  const [hoveredAnnotationId, setHoveredAnnotationId] = useState<string | null>(null);
  const [dragMarkerStartPos, setDragMarkerStartPos] = useState<[number, number] | null | undefined>(null);
  const [dragMarkerMouseStart, setDragMarkerMouseStart] = useState<{ x: number, y: number }>({ x: 0, y: 0 });
  const [hasDragMarkerMoved, setHasDragMarkerMoved] = useState(false);
  const [dragMarkerOriginalCoords, setDragMarkerOriginalCoords] = useState<{ coordinates?: [number, number], ref_coordinates?: [number, number] } | null>(null);

  // Draggable Annotation Pin State — same threshold-based lifecycle as marker
  // drag above: mousedown arms a candidate, mousemove tracks the cursor only
  // past a 3px threshold (so a plain click doesn't nudge the pin), mouseup
  // either selects (no movement) or persists the new position.
  const [dragAnnotationId, setDragAnnotationId] = useState<string | null>(null);
  const [dragAnnotationStartPos, setDragAnnotationStartPos] = useState<[number, number] | null>(null);
  const [dragAnnotationMouseStart, setDragAnnotationMouseStart] = useState<{ x: number, y: number }>({ x: 0, y: 0 });
  const [hasDragAnnotationMoved, setHasDragAnnotationMoved] = useState(false);

  // Custom Context Menu State
  const [contextMenu, setContextMenu] = useState<{
    visible: boolean;
    x: number;
    y: number;
    wx: number; // CAD world coordinates
    wy: number;
  } | null>(null);
  
  const [preventNextContextMenu, setPreventNextContextMenu] = useState(false);
  const [isHoveringMarkerState, setIsHoveringMarkerState] = useState(false);

  // ROI Interactive Drag handles local states.
  //
  // `handleId` is a corner for a rectangular zone, `node:<i>` for a vertex of a reshaped one,
  // or `center` for the whole-zone drag. `edge:<i>` never becomes an ACTIVE handle — clicking
  // an edge inserts a node and immediately hands the drag to that new `node:<i>`, so the
  // gesture is add-and-place in one motion rather than add-then-find-it.
  const [activeDragHandle, setActiveDragHandle] = useState<{
    regionKey: string;
    handleId: string;
  } | null>(null);
  
  const [hoveredHandleInfo, setHoveredHandleInfo] = useState<{
    regionKey: string;
    handleId: string;
    cursor: string;
  } | null>(null);

  /**
   * The zone's geometry as it was when the current drag gesture STARTED.
   *
   * Undo has to coalesce here. The drag handler writes to the store on every mousemove frame,
   * so recording per write would turn one nudge of a corner into a couple of hundred undo
   * steps and make Ctrl+Z appear broken — you would hold it down and watch the box creep.
   * One gesture (mousedown → mouseup) is one entry.
   *
   * A ref, not state: it is written during mousedown and read during mouseup within the same
   * gesture, and a state update would not be visible to the mouseup handler that reads it.
   */
  const zoneGestureRef = useRef<{
    drawingId: string;
    zoneKey: string;
    before: RegionFractions | null;
  } | null>(null);

  /**
   * Closes an in-flight zone gesture, recording it only if the geometry actually changed.
   *
   * The equality check matters: clicking a handle without moving it, or clicking inside a zone
   * to select it, both run through the drag lifecycle and would otherwise push a no-op entry
   * that makes the user press Ctrl+Z twice to undo one real edit.
   */
  const commitZoneGesture = useCallback(() => {
    const gesture = zoneGestureRef.current;
    zoneGestureRef.current = null;
    if (!gesture) return;

    const after = useReviewStore.getState().getRegionsFor(gesture.drawingId)[gesture.zoneKey] ?? null;
    if (JSON.stringify(gesture.before) === JSON.stringify(after)) return;

    recordHistory({
      kind: 'zone/update',
      label: gesture.before === null ? 'Add zone box' : 'Edit zone box',
      drawingId: gesture.drawingId,
      zoneKey: gesture.zoneKey,
      before: gesture.before,
      after,
    });
  }, []);
  
  const [centerDragStart, setCenterDragStart] = useState<{
    pctX: number;
    pctY: number;
    originalXMin: number;
    originalXMax: number;
    originalYMin: number;
    originalYMax: number;
  } | null>(null);

  const bounds = useMemo(() => parseBounds(drawing?.metadata?.render_bounds), [drawing?.metadata?.render_bounds]);
  const norm = useMemo(() => getNormalization(bounds), [bounds]);

  const clampViewport = useCallback((v: { x: number, y: number, scale: number }) => {
    return clampViewportShared(v, bounds, width, height);
  }, [bounds, width, height]);

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

  // Zoom-to-focus selected violation coordinates
  useEffect(() => {
    if (selectedViolation && drawing) {
      // Determine if we should handle the zoom on THIS canvas.
      // We prioritize newDrawing canvas. If newDrawing is missing, fallback to oldDrawing canvas.
      const state = useWorkspaceStore.getState();
      const primaryId = state.newDrawing?.id || state.oldDrawing?.id;
      if (drawing.id !== primaryId) return;

      // Prefer new drawing coords if it's the new drawing, otherwise old coords.
      const isNew = drawing.id === state.newDrawing?.id;
      const coords = isNew 
        ? (selectedViolation.coordinates || selectedViolation.ref_coordinates)
        : (selectedViolation.ref_coordinates || selectedViolation.coordinates);

      if (coords && Array.isArray(coords) && coords.length >= 2) {
        const [vx, vy] = coords;

        // Safety Guard 1: Ignore invalid, non-finite, or [0, 0] unanchored coordinates
        if (!Number.isFinite(vx) || !Number.isFinite(vy) || (vx === 0 && vy === 0)) {
          return;
        }

        // Safety Guard 2: Verify coordinates are within rendering bounds area (+20% margin)
        if (bounds) {
          const marginX = (bounds.xmax - bounds.xmin) * 0.2;
          const marginY = (bounds.ymax - bounds.ymin) * 0.2;
          if (vx < bounds.xmin - marginX || vx > bounds.xmax + marginX || vy < bounds.ymin - marginY || vy > bounds.ymax + marginY) {
            console.warn("[Smart Navigation] Skipping camera auto-focus for out-of-bounds coordinates:", coords);
            return;
          }
        }

        const stdX = (vx - norm.xmin) * norm.normScale;
        const vy_inverted = norm.hasBounds ? (norm.ymax + norm.ymin - vy) : vy;
        const stdY = (vy_inverted - norm.ymin) * norm.normScale;

        let targetScale = 2.2;
        if (bounds && norm.normScale) {
          const drawingDim = Math.max(bounds.xmax - bounds.xmin, bounds.ymax - bounds.ymin);
          if (drawingDim > 0) {
            targetScale = Math.min(6.0, Math.max(1.5, (width * 0.45) / (drawingDim * norm.normScale)));
          }
        }
        const targetX = width / 2 - stdX * targetScale;
        const targetY = height / 2 - stdY * targetScale;

        setViewport(clampViewport({ x: targetX, y: targetY, scale: targetScale }));
      }
    }
  }, [selectedViolation, drawing, width, height, setViewport, clampViewport]);

  // Zoom-to-focus selected annotation pin. Parallel to the violation effect
  // above — annotation coordinates are stored in the same CAD (Y-up) space, so
  // the transform math is identical; kept separate rather than abstracted because
  // the violation effect carries violation-specific old/new-side and bounds guards.
  useEffect(() => {
    if (!selectedAnnotationId || !drawing) return;

    const state = useWorkspaceStore.getState();
    const ann = Array.isArray(state.annotations) ? state.annotations.find(a => a.id === selectedAnnotationId) : null;
    // Only the canvas that owns this pin should recenter — its coordinates are
    // in that drawing's CAD space and would land somewhere arbitrary elsewhere.
    if (!ann || ann.drawing_id !== drawing.id) return;

    const coords = ann.coordinates;
    if (!coords || !Array.isArray(coords) || coords.length < 2) return;

    const [ax, ay] = coords;
    if (!Number.isFinite(ax) || !Number.isFinite(ay)) return;

    const stdX = (ax - norm.xmin) * norm.normScale;
    const ay_inverted = norm.hasBounds ? (norm.ymax + norm.ymin - ay) : ay;
    const stdY = (ay_inverted - norm.ymin) * norm.normScale;

    let targetScale = 2.2;
    if (bounds && norm.normScale) {
      const drawingDim = Math.max(bounds.xmax - bounds.xmin, bounds.ymax - bounds.ymin);
      if (drawingDim > 0) {
        targetScale = Math.min(6.0, Math.max(1.5, (width * 0.45) / (drawingDim * norm.normScale)));
      }
    }
    // Offset camera target so that both the popover callout card and pin reticle are comfortably centered
    const popoverOffsetX = 80;
    const popoverOffsetY = -50;

    const targetX = width / 2 - stdX * targetScale - popoverOffsetX;
    const targetY = height / 2 - stdY * targetScale - popoverOffsetY;

    setViewport(clampViewport({ x: targetX, y: targetY, scale: targetScale }));
  }, [selectedAnnotationId, drawing, width, height, setViewport, clampViewport]);

  // Keyboard shortcut actions
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const active = document.activeElement as HTMLElement | null;
      if (active && (active.tagName === 'INPUT' || active.tagName === 'TEXTAREA' || active.isContentEditable)) {
        return;
      }

      // NOTE: Ctrl+Z / Ctrl+Y are NOT handled here. This hook runs once per canvas pane and
      // the workspace renders two, so a window-level binding here fired twice per press and
      // undid two actions. Undo lives in hooks/useUndoRedo.ts, mounted once by App.
      const key = e.key.toLowerCase();
      if (key === 'escape') {
        e.preventDefault();
        selectViolation(null);
        useWorkspaceStore.getState().selectAnnotation(null);
      } else if (key === 'f') {
        e.preventDefault();
        if (selectedViolation && selectedViolation.coordinates && drawing) {
          const [vx, vy] = selectedViolation.coordinates;
          const norm = getNormalization(parseBounds(drawing?.metadata?.render_bounds));
          const stdX = (vx - norm.xmin) * norm.normScale;
          const vy_inverted = norm.hasBounds ? (norm.ymax + norm.ymin - vy) : vy;
          const stdY = (vy_inverted - norm.ymin) * norm.normScale;

          const targetScale = 2.2;
          const targetX = width / 2 - stdX * targetScale;
          const targetY = height / 2 - stdY * targetScale;
          setViewport(clampViewport({ x: targetX, y: targetY, scale: targetScale }));
        }
      } else if (key === 'delete' || key === 'backspace') {
        if (selectedViolation) {
          e.preventDefault();
          const currentViolations = useWorkspaceStore.getState().violations;
          // Record BEFORE removing, and push onto the deleted stack, so this deletion is
          // reachable by both Ctrl+Z and the context menu's "Undo Delete". Previously it did
          // neither, making keyboard-deleted markers the one unrecoverable action in the
          // workspace — alt-click delete had always been undoable.
          useWorkspaceStore.getState().pushDeletedViolation(selectedViolation);
          recordHistory({
            kind: 'violation/delete',
            label: 'Delete marker',
            violationId: selectedViolation.id,
            violation: selectedViolation,
          });
          setViolations(currentViolations.filter(v => v.id !== selectedViolation.id));
          selectViolation(null);
        }
      } else if (e.ctrlKey && (e.key === '=' || e.key === '+')) {
        e.preventDefault();
        const currentViewport = useReviewStore.getState().viewport;
        setViewport(clampViewport({ ...currentViewport, scale: Math.min(25, currentViewport.scale * 1.25) }));
      } else if (e.ctrlKey && e.key === '-') {
        e.preventDefault();
        const currentViewport = useReviewStore.getState().viewport;
        setViewport(clampViewport({ ...currentViewport, scale: Math.max(0.81, currentViewport.scale / 1.25) }));
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [selectedViolation, drawing, width, height, setViewport, selectViolation, clampViewport]);

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    const currentViewport = useReviewStore.getState().viewport;
    mouseDownRawPosRef.current = { x: e.clientX, y: e.clientY };

    // Restrict panning strictly to primary left mouse button (e.button === 0) or space key pan shortcut
    if (e.button !== 0 && !isSpacePressed) {
      return;
    }

    if (isSpacePressed) {
      setIsDragging(true);
      isDraggingRef.current = true;
      if (dragDebounceTimerRef.current) {
        clearTimeout(dragDebounceTimerRef.current);
        dragDebounceTimerRef.current = null;
      }
      setDragStart({ x: e.clientX - currentViewport.x, y: e.clientY - currentViewport.y });
      e.preventDefault();
      return;
    }
    if (e.button === 0) {
      const rect = canvasRef.current?.getBoundingClientRect();

      // Annotation placement mode: a left-click drops a pin at the clicked
      // point, attached to THIS canvas's drawing. Either pane can be pinned —
      // a pin's coordinates only mean anything in its own drawing's CAD space,
      // so the drawing that was clicked is the one it belongs to. (This was
      // previously restricted to the primary pane, which made the reference
      // canvas a silent dead zone and mis-attributed every pin to the new drawing.)
      if (isPlacingAnnotation && rect && drawing?.id) {
        const mx = e.clientX - rect.left;
        const my = e.clientY - rect.top;
        const world = screenToWorld(mx, my, norm, currentViewport);
        const content = useWorkspaceStore.getState().pendingAnnotationText || "";
        createAnnotationAt([world.x, world.y], content, drawing.id);
        e.preventDefault();
        return;
      }

      if (rect) {
        const mx = e.clientX - rect.left;
        const my = e.clientY - rect.top;

        const hiddenViolationIds = useWorkspaceStore.getState().hiddenViolationIds;
        const visibleViolations = violations.filter(v => !hiddenViolationIds[v.id]);

        const clickedViolationId = hitTestMarker({
          mx,
          my,
          violations: visibleViolations,
          drawing,
          oldDrawing,
          showViolations,
          viewport: currentViewport,
          markerPositions: markerPositionsRef.current
        });

        if (clickedViolationId) {
          const markerItem = visibleViolations.find(v => v.id === clickedViolationId);
          if (markerItem) {
            const isOldDrawing = oldDrawing && drawing?.id === oldDrawing.id;
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

        // Annotation pin hit-test. Positions are stored under "ann:<id>" keys by
        // renderAnnotationPins, in the same canvas-pixel space. Arms a drag
        // candidate rather than selecting immediately — mirrors the marker
        // drag flow so a plain click still selects (handled in mouseup when
        // the 3px move threshold isn't crossed) while a press-and-drag moves
        // the pin.
        // Annotation pin hit-test (always active on canvas regardless of side panel visibility)
        const positions = markerPositionsRef.current;
        const hitRadius = 10;
        const ownPins = useWorkspaceStore.getState().annotations.filter(a => a.drawing_id === drawing?.id);
        for (const ann of ownPins) {
          const p = positions[`ann:${ann.id}`];
          if (p && Math.hypot(p.x - mx, p.y - my) <= hitRadius) {
            setDragAnnotationId(ann.id);
            setDragAnnotationStartPos(ann.coordinates ? [...ann.coordinates] : [0, 0]);
            setDragAnnotationMouseStart({ x: e.clientX, y: e.clientY });
            setHasDragAnnotationMoved(false);
            return;
          }
        }
      }

      if (isRoiEditModeEnabled && hoveredHandleInfo) {
        const { regionKey, handleId } = hoveredHandleInfo;
        const current = customRegions[regionKey];

        // ALT+click a node removes it — the inverse of clicking an edge. Bounded at three
        // vertices by `removePointAt`, because two points enclose nothing and a zone that
        // contains nothing reports nothing, silently.
        if (e.altKey && handleId.startsWith('node:') && current && drawing?.id) {
          const removed = removePointAt(current, Number(handleId.slice('node:'.length)));
          updateCustomRegion(drawing.id, regionKey, removed);
          // Recorded immediately rather than through the gesture ref: this is a complete
          // edit on mousedown with no drag to follow, so there is no mouseup to commit it.
          recordHistory({
            kind: 'zone/update',
            label: 'Remove zone node',
            drawingId: drawing.id,
            zoneKey: regionKey,
            before: current,
            after: removed,
          });
          setRedrawTrigger(prev => prev + 1);
          return;
        }

        // Click an edge to insert a node at that point, then drag it straight away: the new
        // vertex becomes the active handle, so adding and placing are one gesture. On a
        // rectangle this is also the moment the zone stops being one.
        if (handleId.startsWith('edge:') && current && drawing?.id) {
          const edgeIndex = Number(handleId.slice('edge:'.length));
          // Snapshot BEFORE the insert, and let mouseup commit it — so inserting a node and
          // dragging it into place is a single undo step, matching the single gesture the
          // user performed.
          zoneGestureRef.current = { drawingId: drawing.id, zoneKey: regionKey, before: current };
          updateCustomRegion(drawing.id, regionKey, insertPointOnEdge(current, edgeIndex));
          setActiveDragHandle({ regionKey, handleId: `node:${edgeIndex + 1}` });
          setIsDragging(true);
          setRedrawTrigger(prev => prev + 1);
          return;
        }

        if (drawing?.id) {
          zoneGestureRef.current = {
            drawingId: drawing.id,
            zoneKey: regionKey,
            before: current ?? null,
          };
        }

        setActiveDragHandle({ regionKey, handleId });

        if (hoveredHandleInfo.handleId === 'center') {
          const rect = canvasRef.current?.getBoundingClientRect();
          if (rect && drawing?.metadata?.render_bounds) {
            const mx = e.clientX - rect.left;
            const my = e.clientY - rect.top;

            const dragPercentages = getRoiDragPercentages({ mx, my, drawing, viewport: currentViewport });
            const current = customRegions[hoveredHandleInfo.regionKey];
            if (dragPercentages && current) {
              setCenterDragStart({
                pctX: dragPercentages.pctX,
                pctY: dragPercentages.pctY,
                originalXMin: current.xMin,
                originalXMax: current.xMax,
                originalYMin: current.yMin,
                originalYMax: current.yMax
              });
            }
          }
        }
        // When entering handle mode, treat as dragging
        setIsDragging(true);
        isDraggingRef.current = true;
        if (dragDebounceTimerRef.current) {
          clearTimeout(dragDebounceTimerRef.current);
          dragDebounceTimerRef.current = null;
        }
        setDragStart({ x: e.clientX - currentViewport.x, y: e.clientY - currentViewport.y });
      } else {
        setIsDragging(true);
        isDraggingRef.current = true;
        setDragStart({ x: e.clientX - currentViewport.x, y: e.clientY - currentViewport.y });
      }
    }
  }, [isSpacePressed, violations, drawing, oldDrawing, showViolations, markerPositionsRef, isRoiEditModeEnabled, hoveredHandleInfo, customRegions, canvasRef, isPlacingAnnotation, createAnnotationAt, showAnnotations]);

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;

    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    const currentViewport = useReviewStore.getState().viewport;

    // ── Marker drag ────────────────────────────────────────────────────────────
    if (dragMarkerId && dragMarkerStartPos) {
      // A drag is a delta, not a point: the Y-flip is affine and does not distribute
      // over a subtraction, so screenDeltaToWorldDelta handles the sign inversion.
      const { dx: deltaX, dy: adjustedDeltaY } = screenDeltaToWorldDelta(
        e.clientX - dragMarkerMouseStart.x,
        e.clientY - dragMarkerMouseStart.y,
        norm,
        currentViewport,
      );

      const newX = dragMarkerStartPos[0] + deltaX;
      const newY = dragMarkerStartPos[1] + adjustedDeltaY;

      if (Math.hypot(e.clientX - dragMarkerMouseStart.x, e.clientY - dragMarkerMouseStart.y) > 3) {
        setHasDragMarkerMoved(true);
      }

      const isOldDrawing = oldDrawing && drawing?.id === oldDrawing.id;
      const currentViolations = useWorkspaceStore.getState().violations;
      setViolations(currentViolations.map(v => {
        if (v.id === dragMarkerId) {
          return isOldDrawing
            ? { ...v, ref_coordinates: [newX, newY] as [number, number] }
            : { ...v, coordinates: [newX, newY] as [number, number] };
        }
        return v;
      }));
      return;
    }

    // ── Annotation pin drag ───────────────────────────────────────────────────
    // Same delta/Y-flip math as marker drag above (identical coordinate space).
    // Position updates go through moveAnnotationLocal (no network call per
    // frame) — the final position is persisted once in mouseup.
    if (dragAnnotationId && dragAnnotationStartPos) {
      const { dx: deltaX, dy: adjustedDeltaY } = screenDeltaToWorldDelta(
        e.clientX - dragAnnotationMouseStart.x,
        e.clientY - dragAnnotationMouseStart.y,
        norm,
        currentViewport,
      );

      const newX = dragAnnotationStartPos[0] + deltaX;
      const newY = dragAnnotationStartPos[1] + adjustedDeltaY;

      if (Math.hypot(e.clientX - dragAnnotationMouseStart.x, e.clientY - dragAnnotationMouseStart.y) > 3) {
        setHasDragAnnotationMoved(true);
      }

      useWorkspaceStore.getState().moveAnnotationLocal(dragAnnotationId, [newX, newY]);
      return;
    }

    // ── FAST PATH: Simple viewport pan ────────────────────────────────────────
    // Skip ALL expensive work: hit-tests, getNormalization(), state setters.
    // This is the most-frequently-hit code path (every mouse pixel while panning).
    if (isDragging && !activeDragHandle) {
      setViewport(clampViewport({ ...currentViewport, x: e.clientX - dragStart.x, y: e.clientY - dragStart.y }));
      return;
    }

    // ── Shared computation (only reached when NOT panning) ────────────────────
    const effectiveScale = currentViewport.scale * norm.normScale;

    // ── Marker hover hit-test ─────────────────────────────────────────────────
    let isHoveringMarker = false;
    let hoveredMId: string | null = null;
    if (showViolations) {
      const hiddenViolationIds = useWorkspaceStore.getState().hiddenViolationIds;
      const visibleViolations = violations.filter(v => !hiddenViolationIds[v.id]);

      const clickedViolationId = hitTestMarker({
        mx,
        my,
        violations: visibleViolations,
        drawing,
        oldDrawing,
        showViolations,
        viewport: currentViewport,
        markerPositions: markerPositionsRef.current
      });
      if (clickedViolationId) {
        isHoveringMarker = true;
        hoveredMId = clickedViolationId;
      }
    }

    // ── Annotation pin hover hit-test ─────────────────────────────────────────
    let hoveredAnnId: string | null = null;
    if (drawing?.id) {
      const ownPins = useWorkspaceStore.getState().annotations.filter(a => a.drawing_id === drawing.id);
      const positions = markerPositionsRef.current;
      const hitRadius = 10;
      for (const ann of ownPins) {
        const p = positions[`ann:${ann.id}`];
        if (p && Math.hypot(p.x - mx, p.y - my) <= hitRadius) {
          hoveredAnnId = ann.id;
          isHoveringMarker = true;
          break;
        }
      }
    }

    setHoveredAnnotationId(hoveredAnnId);
    setIsHoveringMarkerState(isHoveringMarker);
    setHoveredMarkerId(hoveredMId);

    // ── ROI Drag Handle hover ─────────────────────────────────────────────────
    if (isRoiEditModeEnabled && selectedComparisonRegion && drawing?.metadata?.render_bounds) {
      const [rxMin, ryMin, rxMax, ryMax] = drawing.metadata.render_bounds;
      const w = rxMax - rxMin;
      const h = ryMax - ryMin;
      const regionKey = selectedComparisonRegion;
      const customReg = customRegions[regionKey];

      if (customReg) {
        const screenXMin = (rxMin + w * customReg.xMin - norm.xmin) * effectiveScale + currentViewport.x;
        const screenXMax = (rxMin + w * customReg.xMax - norm.xmin) * effectiveScale + currentViewport.x;
        const screenYMin = (ryMin + h * customReg.yMin - norm.ymin) * effectiveScale + currentViewport.y;
        const screenYMax = (ryMin + h * customReg.yMax - norm.ymin) * effectiveScale + currentViewport.y;

        const isPolygon = isPolygonZone(customReg);
        const pts = shapePointsToScreen(customReg, drawing.metadata.render_bounds, norm, currentViewport);

        // A RECTANGLE keeps its four corner handles and its rectangular resize. A RESHAPED
        // zone's handles are its vertices: once an outline exists there is no opposite edge
        // to hold, so "resize the box" has no meaning.
        const handles = isPolygon
          ? pts.map((p, i) => ({ id: `node:${i}`, x: p.x, y: p.y, cursor: 'move' }))
          : [
              { id: 'top-left', x: screenXMin, y: screenYMin, cursor: 'nwse-resize' },
              { id: 'top-right', x: screenXMax, y: screenYMin, cursor: 'nesw-resize' },
              { id: 'bottom-left', x: screenXMin, y: screenYMax, cursor: 'nesw-resize' },
              { id: 'bottom-right', x: screenXMax, y: screenYMax, cursor: 'nwse-resize' },
            ];

        const hovered = handles.find(hd => Math.hypot(mx - hd.x, my - hd.y) <= 12);
        if (hovered) {
          setHoveredHandleInfo({ regionKey, handleId: hovered.id, cursor: hovered.cursor });
        } else {
          // Edge hover — the "add a node here" affordance. Checked AFTER the vertex handles
          // so a corner never loses to the two edges meeting at it, and with a tighter
          // tolerance (8px vs 12px) so grabbing an existing node stays easier than minting a
          // new one. `copy` is the cursor because the click adds something rather than moving
          // what is there.
          const edge = nearestEdgeWithin(pts, mx, my, 8);
          if (edge !== null) {
            setHoveredHandleInfo({ regionKey, handleId: `edge:${edge}`, cursor: 'copy' });
          } else if (pointInScreenShape(pts, mx, my)) {
            setHoveredHandleInfo({ regionKey, handleId: 'center', cursor: 'move' });
          } else {
            setHoveredHandleInfo(null);
          }
        }
      }
    } else {
      if (hoveredHandleInfo) setHoveredHandleInfo(null);
    }

    // ── ROI Drag Handle move ──────────────────────────────────────────────────
    if (activeDragHandle && drawing?.metadata?.render_bounds && customRegions) {
      const [rxMin, ryMin, rxMax, ryMax] = drawing.metadata.render_bounds;
      const w = rxMax - rxMin;
      const h = ryMax - ryMin;

      // Unflipped on purpose — ROI regions live in percentage space against
      // render_bounds, where Y is not inverted.
      const { x: worldX, y: worldY } = screenToWorldUnflipped(
        e.clientX - rect.left,
        e.clientY - rect.top,
        norm,
        currentViewport,
      );

      const pctX = Math.max(0.0, Math.min(1.0, (worldX - rxMin) / w));
      const pctY = Math.max(0.0, Math.min(1.0, (worldY - ryMin) / h));

      const currentBounds = { ...customRegions[activeDragHandle.regionKey] };

      // Dragging a VERTEX of a reshaped zone. Handled before the rectangle branches because
      // those all write xMin/xMax/yMin/yMax, which on a polygon are the DERIVED bounds — the
      // write would be recomputed away by `normalizeFractions` and the node would snap back.
      if (activeDragHandle.handleId.startsWith('node:')) {
        const index = Number(activeDragHandle.handleId.slice('node:'.length));
        updateCustomRegion(
          drawing.id,
          activeDragHandle.regionKey,
          movePointTo(currentBounds, index, { x: pctX, y: pctY }),
        );
        setRedrawTrigger(prev => prev + 1);
        return;
      }

      // Whole-zone drag of a reshaped zone: every vertex moves together. The rectangle path
      // below cannot express this — it slides four edges, and a polygon has no four edges.
      if (activeDragHandle.handleId === 'center' && centerDragStart && isPolygonZone(currentBounds)) {
        updateCustomRegion(
          drawing.id,
          activeDragHandle.regionKey,
          translateShape(
            currentBounds,
            pctX - centerDragStart.pctX,
            pctY - centerDragStart.pctY,
          ),
        );
        setCenterDragStart({ ...centerDragStart, pctX, pctY });
        setRedrawTrigger(prev => prev + 1);
        return;
      }

      if (activeDragHandle.handleId === 'center' && centerDragStart) {
        const deltaPctX = pctX - centerDragStart.pctX;
        const deltaPctY = pctY - centerDragStart.pctY;

        const boxW = centerDragStart.originalXMax - centerDragStart.originalXMin;
        const boxH = centerDragStart.originalYMax - centerDragStart.originalYMin;

        let newXMin = centerDragStart.originalXMin + deltaPctX;
        let newXMax = centerDragStart.originalXMax + deltaPctX;
        let newYMin = centerDragStart.originalYMin + deltaPctY;
        let newYMax = centerDragStart.originalYMax + deltaPctY;

        if (newXMin < 0) { newXMin = 0; newXMax = boxW; }
        else if (newXMax > 1) { newXMax = 1; newXMin = 1 - boxW; }
        if (newYMin < 0) { newYMin = 0; newYMax = boxH; }
        else if (newYMax > 1) { newYMax = 1; newYMin = 1 - boxH; }

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

      updateCustomRegion(drawing.id, activeDragHandle.regionKey, currentBounds);
      setRedrawTrigger(prev => prev + 1);
    }
  }, [isDragging, activeDragHandle, allCustomRegions, updateCustomRegion, setRedrawTrigger, canvasRef, drawing, oldDrawing, dragMarkerId, dragMarkerStartPos, dragMarkerMouseStart, showViolations, violations, markerPositionsRef, isRoiEditModeEnabled, selectedComparisonRegion, centerDragStart, dragStart, setViewport, hoveredHandleInfo, clampViewport, norm, dragAnnotationId, dragAnnotationStartPos, dragAnnotationMouseStart]);


  const handleMouseUp = useCallback((e: React.MouseEvent) => {
    setIsDragging(false);
    
    // Debounce the physical drag end so violation rendering doesn't cause a micro-stutter on release
    if (dragDebounceTimerRef.current) clearTimeout(dragDebounceTimerRef.current);
    dragDebounceTimerRef.current = setTimeout(() => {
      isDraggingRef.current = false;
      setRedrawTrigger(prev => prev + 1); // Ensure reticles pop back in
    }, 50);
    setActiveDragHandle(null);
    setCenterDragStart(null);
    // Close the zone gesture opened in mousedown. No-ops when the press was a pan or a plain
    // click, since nothing was snapshotted and the geometry is unchanged either way.
    commitZoneGesture();

    // If we didn't click on a marker, and we didn't drag/pan significantly, it's a "click outside" -> deselect
    if (!dragMarkerId && selectedViolation) {
      const dx = e.clientX - mouseDownRawPosRef.current.x;
      const dy = e.clientY - mouseDownRawPosRef.current.y;
      if (Math.abs(dx) < 5 && Math.abs(dy) < 5) {
        selectViolation(null);
      }
    }

    // Same "click outside" dismissal for the selected annotation pin — previously
    // only violations had this; annotations had no deselect path at all (not from
    // the canvas, the list, or Escape — all three are now fixed together).
    if (!dragAnnotationId && selectedAnnotationId) {
      const dx = e.clientX - mouseDownRawPosRef.current.x;
      const dy = e.clientY - mouseDownRawPosRef.current.y;
      if (Math.abs(dx) < 5 && Math.abs(dy) < 5) {
        useWorkspaceStore.getState().selectAnnotation(null);
      }
    }

    if (dragMarkerId) {
      if (!hasDragMarkerMoved) {
        const currentViolations = useWorkspaceStore.getState().violations;
        const markerToDelete = currentViolations.find(v => v.id === dragMarkerId);
        if (markerToDelete) {
          if (e.altKey) {
            useWorkspaceStore.getState().pushDeletedViolation(markerToDelete);
            recordHistory({
              kind: 'violation/delete',
              label: 'Delete marker',
              violationId: markerToDelete.id,
              violation: markerToDelete,
            });
            setViolations(currentViolations.filter(v => v.id !== dragMarkerId));
            if (selectedViolation?.id === dragMarkerId) {
              selectViolation(null);
            }
          } else {
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
            recordHistory({
              kind: 'violation/move',
              label: 'Move marker',
              violationId: dragMarkerId,
              before: {
                coordinates: dragMarkerOriginalCoords.coordinates,
                refCoordinates: dragMarkerOriginalCoords.ref_coordinates,
              },
              after: {
                coordinates: markerItem.coordinates,
                refCoordinates: markerItem.ref_coordinates,
              },
            });
          }
        }
      }
      setDragMarkerId(null);
      setDragMarkerStartPos(null);
      setDragMarkerOriginalCoords(null);
    }

    // ── Annotation pin drag finalize ────────────────────────────────────────
    // No movement past the 3px threshold → treat as a plain click and select.
    // Movement past it → persist the position dragged in mousemove (which was
    // only ever applied locally via moveAnnotationLocal, never sent over the
    // wire) via a single PATCH here.
    if (dragAnnotationId) {
      if (!hasDragAnnotationMoved) {
        useWorkspaceStore.getState().selectAnnotation(dragAnnotationId);
        if (!useReviewStore.getState().showAnnotations) {
          useReviewStore.getState().toggleAnnotations();
        }
      } else {
        const ann = useWorkspaceStore.getState().annotations.find(a => a.id === dragAnnotationId);
        if (ann?.coordinates) {
          useWorkspaceStore.getState().updateAnnotationDetails(dragAnnotationId, { coordinates: ann.coordinates });
        }
      }
      setDragAnnotationId(null);
      setDragAnnotationStartPos(null);
    }
  }, [dragMarkerId, hasDragMarkerMoved, dragMarkerOriginalCoords, selectedViolation, selectViolation, dragAnnotationId, hasDragAnnotationMoved, selectedAnnotationId, commitZoneGesture]);

  const handleMouseLeave = useCallback(() => {
    setIsDragging(false);
    if (dragDebounceTimerRef.current) clearTimeout(dragDebounceTimerRef.current);
    dragDebounceTimerRef.current = setTimeout(() => {
      isDraggingRef.current = false;
      setRedrawTrigger(prev => prev + 1);
    }, 50);
    setActiveDragHandle(null);
    setCenterDragStart(null);
    // The cursor leaving the canvas ends the drag, and the moves made up to that point are
    // already in the store — so the gesture must be recorded here too. Without this, dragging
    // a zone off the edge of the pane left an edit that Ctrl+Z could not reach.
    commitZoneGesture();
    setHoveredHandleInfo(null);
    setIsHoveringMarkerState(false);
    setDragMarkerId(null);
    setDragMarkerStartPos(null);
    setHoveredMarkerId(null);
    setHoveredAnnotationId(null);
    // Cursor left the canvas mid-drag — drop the candidate rather than leave
    // it armed (would otherwise resume dragging on the NEXT mousemove inside
    // the canvas, jumping the pin to wherever the cursor re-entered).
    setDragAnnotationId(null);
    setDragAnnotationStartPos(null);
  }, [commitZoneGesture]);

  const handleContextMenu = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    if (preventNextContextMenu) {
      setPreventNextContextMenu(false);
      return;
    }
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;

    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;

    const currentViewport = useReviewStore.getState().viewport;
    const effectiveScale = currentViewport.scale * norm.normScale;
    const wx = norm.xmin + (mx - currentViewport.x) / effectiveScale;
    const worldPos = screenToWorld(mx, my, norm, currentViewport);
    const wy = worldPos.y;

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
  }, [preventNextContextMenu, canvasRef, drawing, width, height, norm]);

  const handleWheel = useCallback((e: React.WheelEvent<HTMLCanvasElement>) => {
    e.preventDefault();
    
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;
    
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    
    const currentViewport = useReviewStore.getState().viewport;
    const zoomFactor = 1.15;
    const scaleFactor = e.deltaY < 0 ? zoomFactor : 1 / zoomFactor;
    
    const newScale = Math.min(25, Math.max(0.81, currentViewport.scale * scaleFactor));
    
    const newX = mx - (mx - currentViewport.x) * (newScale / currentViewport.scale);
    const newY = my - (my - currentViewport.y) * (newScale / currentViewport.scale);
    
    setViewport(clampViewport({ x: newX, y: newY, scale: newScale }));
  }, [canvasRef, setViewport, clampViewport]);

  const getCursorStyle = () => {
    if (isPlacingAnnotation) return 'crosshair';
    if (isSpacePressed) return isDragging ? 'grabbing' : 'grab';
    if (activeDragHandle) {
      // A vertex or whole-zone drag is a move, not a resize — the diagonal resize cursors
      // only mean something for a rectangle's corners.
      if (activeDragHandle.handleId.startsWith('node:') || activeDragHandle.handleId === 'center') {
        return 'move';
      }
      return (activeDragHandle.handleId === 'top-left' || activeDragHandle.handleId === 'bottom-right') ? 'nwse-resize' : 'nesw-resize';
    }
    if (hoveredHandleInfo) return hoveredHandleInfo.cursor;
    if (dragAnnotationId) return 'grabbing';
    if (isHoveringMarkerState || !!hoveredAnnotationId) return 'pointer';
    if (isDragging) return 'grabbing';
    return 'grab';
  };

  // Stable handlers object so a React.memo'd CanvasRenderer isn't re-rendered
  // just because this object was re-created. The individual handlers are
  // already useCallback'd, so this only changes identity when one of them does.
  const handlers = useMemo(() => ({
    onMouseDown: handleMouseDown,
    onMouseMove: handleMouseMove,
    onMouseUp: handleMouseUp,
    onMouseLeave: handleMouseLeave,
    onContextMenu: handleContextMenu,
    onWheel: handleWheel,
  }), [handleMouseDown, handleMouseMove, handleMouseUp, handleMouseLeave, handleContextMenu, handleWheel]);

  return {
    handlers,
    state: {
      isDraggingRef,
      contextMenu,
      setContextMenu,
      isHoveringMarkerState,
      hoveredMarkerId,
      hoveredAnnotationId,
      cursorStyle: getCursorStyle(),
      // Exposed so the zone editor can highlight the handle actually under the cursor.
      // Prefer the one being dragged: once a drag starts the pointer can travel off the
      // handle, and dropping the highlight mid-drag makes it look like the grab was lost.
      hoveredHandleId: activeDragHandle?.handleId ?? hoveredHandleInfo?.handleId ?? null,
    }
  };
}
