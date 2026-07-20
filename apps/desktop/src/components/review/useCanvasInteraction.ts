import { useState, useEffect, useCallback, RefObject, useRef } from 'react';
import { useReviewStore } from '../../stores/reviewStore';
import { useWorkspaceStore } from '../../stores/workspaceStore';
import { getNormalization, screenToWorld, parseBounds, clampViewport as clampViewportShared } from '../../utils/coordinateTransform';
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
  const customRegions = useReviewStore(s => s.customRegions);
  const updateCustomRegion = useReviewStore(s => s.updateCustomRegion);

  const selectedViolation = useWorkspaceStore((s) => s.selectedViolation);
  const selectViolation = useWorkspaceStore((s) => s.selectViolation);
  const violations = useWorkspaceStore((s) => s.violations);
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
  const [isHoveringMarkerState, setIsHoveringMarkerState] = useState(false);

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

  const clampViewport = useCallback((v: { x: number, y: number, scale: number }) => {
    const bounds = parseBounds(drawing?.metadata?.render_bounds);
    return clampViewportShared(v, bounds, width, height);
  }, [drawing?.metadata?.render_bounds, width, height]);

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

      if (coords) {
        const [vx, vy] = coords;
        const norm = getNormalization(parseBounds(drawing?.metadata?.render_bounds));
        const stdX = (vx - norm.xmin) * norm.normScale;
        const vy_inverted = norm.hasBounds ? (norm.ymax + norm.ymin - vy) : vy;
        const stdY = (vy_inverted - norm.ymin) * norm.normScale;

        const targetScale = 2.2;
        const targetX = width / 2 - stdX * targetScale;
        const targetY = height / 2 - stdY * targetScale;

        setViewport(clampViewport({ x: targetX, y: targetY, scale: targetScale }));
      }
    }
  }, [selectedViolation, drawing, width, height, setViewport, clampViewport]);

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
          const norm = getNormalization(parseBounds(drawing?.metadata?.render_bounds));
          const stdX = (vx - norm.xmin) * norm.normScale;
          const vy_inverted = norm.hasBounds ? (norm.ymax + norm.ymin - vy) : vy;
          const stdY = (vy_inverted - norm.ymin) * norm.normScale;

          const targetScale = 2.2;
          const targetX = width / 2 - stdX * targetScale;
          const targetY = height / 2 - stdY * targetScale;
          setViewport(clampViewport({ x: targetX, y: targetY, scale: targetScale }));
        }
      } else if (e.key === 'delete' || e.key === 'backspace') {
        if (selectedViolation) {
          e.preventDefault();
          const currentViolations = useWorkspaceStore.getState().violations;
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

    if (e.button === 1 || e.button === 2 || isSpacePressed) {
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
  }, [isSpacePressed, violations, drawing, oldDrawing, showViolations, markerPositionsRef, isRoiEditModeEnabled, hoveredHandleInfo, customRegions, canvasRef]);

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;

    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    const currentViewport = useReviewStore.getState().viewport;

    // ── Marker drag ────────────────────────────────────────────────────────────
    if (dragMarkerId && dragMarkerStartPos) {
      const norm = getNormalization(parseBounds(drawing?.metadata?.render_bounds));
      const effectiveScale = currentViewport.scale * norm.normScale;
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

    // ── FAST PATH: Simple viewport pan ────────────────────────────────────────
    // Skip ALL expensive work: hit-tests, getNormalization(), state setters.
    // This is the most-frequently-hit code path (every mouse pixel while panning).
    if (isDragging && !activeDragHandle) {
      setViewport(clampViewport({ ...currentViewport, x: e.clientX - dragStart.x, y: e.clientY - dragStart.y }));
      if (e.buttons === 2) setPreventNextContextMenu(true);
      return;
    }

    // ── Shared computation (only reached when NOT panning) ────────────────────
    const norm = getNormalization(parseBounds(drawing?.metadata?.render_bounds));
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

        const handles = [
          { id: 'top-left', x: screenXMin, y: screenYMin, cursor: 'nwse-resize' },
          { id: 'top-right', x: screenXMax, y: screenYMin, cursor: 'nesw-resize' },
          { id: 'bottom-left', x: screenXMin, y: screenYMax, cursor: 'nesw-resize' },
          { id: 'bottom-right', x: screenXMax, y: screenYMax, cursor: 'nwse-resize' }
        ];

        const hovered = handles.find(hd => Math.hypot(mx - hd.x, my - hd.y) <= 12);
        if (hovered) {
          setHoveredHandleInfo({ regionKey, handleId: hovered.id, cursor: hovered.cursor });
        } else {
          if (mx >= screenXMin && mx <= screenXMax && my >= screenYMin && my <= screenYMax) {
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

      const worldX = norm.xmin + ((e.clientX - rect.left) - currentViewport.x) / effectiveScale;
      const worldY = norm.ymin + ((e.clientY - rect.top) - currentViewport.y) / effectiveScale;

      const pctX = Math.max(0.0, Math.min(1.0, (worldX - rxMin) / w));
      const pctY = Math.max(0.0, Math.min(1.0, (worldY - ryMin) / h));

      const currentBounds = { ...customRegions[activeDragHandle.regionKey] };

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

      updateCustomRegion(activeDragHandle.regionKey, currentBounds);
      setRedrawTrigger(prev => prev + 1);
    }
  }, [isDragging, activeDragHandle, customRegions, updateCustomRegion, setRedrawTrigger, canvasRef, drawing, oldDrawing, dragMarkerId, dragMarkerStartPos, dragMarkerMouseStart, showViolations, violations, markerPositionsRef, isRoiEditModeEnabled, selectedComparisonRegion, centerDragStart, dragStart, setViewport, hoveredHandleInfo, clampViewport]);


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

    // If we didn't click on a marker, and we didn't drag/pan significantly, it's a "click outside" -> deselect
    if (!dragMarkerId && selectedViolation) {
      const dx = e.clientX - mouseDownRawPosRef.current.x;
      const dy = e.clientY - mouseDownRawPosRef.current.y;
      if (Math.abs(dx) < 5 && Math.abs(dy) < 5) {
        selectViolation(null);
      }
    }

    if (dragMarkerId) {
      if (!hasDragMarkerMoved) {
        const currentViolations = useWorkspaceStore.getState().violations;
        const markerToDelete = currentViolations.find(v => v.id === dragMarkerId);
        if (markerToDelete) {
          if (e.altKey) {
            useWorkspaceStore.getState().pushDeletedViolation(markerToDelete);
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
  }, [dragMarkerId, hasDragMarkerMoved, dragMarkerOriginalCoords, selectedViolation, selectViolation]);

  const handleMouseLeave = useCallback(() => {
    setIsDragging(false);
    if (dragDebounceTimerRef.current) clearTimeout(dragDebounceTimerRef.current);
    dragDebounceTimerRef.current = setTimeout(() => {
      isDraggingRef.current = false;
      setRedrawTrigger(prev => prev + 1);
    }, 50);
    setActiveDragHandle(null);
    setCenterDragStart(null);
    setHoveredHandleInfo(null);
    setIsHoveringMarkerState(false);
    setDragMarkerId(null);
    setDragMarkerStartPos(null);
    setHoveredMarkerId(null);
  }, []);

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
    const norm = getNormalization(parseBounds(drawing?.metadata?.render_bounds));
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
  }, [preventNextContextMenu, canvasRef, drawing, width, height]);

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
    if (isSpacePressed) return isDragging ? 'grabbing' : 'grab';
    if (activeDragHandle) {
      return (activeDragHandle.handleId === 'top-left' || activeDragHandle.handleId === 'bottom-right') ? 'nwse-resize' : 'nesw-resize';
    }
    if (hoveredHandleInfo) return hoveredHandleInfo.cursor;
    if (isHoveringMarkerState) return 'pointer';
    if (isDragging) return 'grabbing';
    return 'grab';
  };

  return {
    handlers: {
      onMouseDown: handleMouseDown,
      onMouseMove: handleMouseMove,
      onMouseUp: handleMouseUp,
      onMouseLeave: handleMouseLeave,
      onContextMenu: handleContextMenu,
      onWheel: handleWheel,
    },
    state: {
      isDraggingRef,
      contextMenu,
      setContextMenu,
      isHoveringMarkerState,
      hoveredMarkerId,
      cursorStyle: getCursorStyle(),
    }
  };
}
