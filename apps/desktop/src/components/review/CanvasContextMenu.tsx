import React from 'react';
import { Eye, EyeOff, RotateCcw, Pin, Filter, Plus, ChevronRight, PenTool, Trash2, Undo2, Redo2 } from 'lucide-react';
import { useReviewStore } from '../../stores/reviewStore';
import { useWorkspaceStore } from '../../stores/workspaceStore';
import { useHistoryStore } from '../../stores/historyStore';
import { performUndo, performRedo } from '../../hooks/useUndoRedo';
import { AnnotationSeverity } from '../../stores/workspace/types';
import { useIsManualCheckRoom } from '../../hooks/useManualCheckRoom';
import { MARKER_STYLES, type MarkerType } from './markerStyles';

interface CanvasContextMenuProps {
  x: number;
  y: number;
  wx: number;
  wy: number;
  drawingId?: string;
  canvasWidth?: number;
  canvasHeight?: number;
  theme: string;
  onOpenAnnotationModal: (severity?: AnnotationSeverity) => void;
  onClose: () => void;
  setRedrawTrigger: React.Dispatch<React.SetStateAction<number>>;
}

/** Every marker type a sheet can show, in the order they appear on the canvas legend. */
const FILTERABLE_MARKERS: MarkerType[] = [
  'MISMATCHED',
  'CHANGED',
  'ADDED',
  'MATCHED',
  'CONFLICT',
  'REMOVED',
];

export const CanvasContextMenu: React.FC<CanvasContextMenuProps> = ({
  x,
  y,
  wx,
  wy,
  drawingId,
  canvasWidth,
  canvasHeight,
  theme,
  onOpenAnnotationModal,
  onClose,
  setRedrawTrigger,
}) => {
  const showMarkerLabels = useReviewStore((s) => s.showMarkerLabels);
  const toggleMarkerLabels = useReviewStore((s) => s.toggleMarkerLabels);

  const isPenActive = useWorkspaceStore((s) => s.isPenActive);
  const setIsPenActive = useWorkspaceStore((s) => s.setIsPenActive);
  const undoLastPenStroke = useWorkspaceStore((s) => s.undoLastPenStroke);
  const penStrokes = useWorkspaceStore((s) => s.penStrokes);
  const clearPenStrokes = useWorkspaceStore((s) => s.clearPenStrokes);
  const hasDrawingStrokes = Boolean(
    drawingId && Array.isArray(penStrokes) && penStrokes.some((s) => s.drawingId === String(drawingId))
  );

  const canUndo = useHistoryStore((s) => s.past.length > 0) || hasDrawingStrokes;
  const canRedo = useHistoryStore((s) => s.future.length > 0);

  // Manual engineer check. Marking moved to `SelectionMenu` on 2026-08-18; all this menu still
  // owns is cancelling a pairing in flight, which needs a surface that opens with nothing
  // selected. There is still exactly ONE way to write a marking — see that component.
  const isManualCheckRoom = useIsManualCheckRoom();
  const pendingPairRef = useWorkspaceStore((s) => s.pendingPairRef);
  const setPendingPairRef = useWorkspaceStore((s) => s.setPendingPairRef);

  // Context-aware positioning: detect right & bottom boundaries so submenus fly out cleanly without clipping
  // 200 is the widest flyout — the stamp categories, whose longest row is
  // "Changed — pick counterpart…". Under-estimating this is what makes a submenu open off the
  // edge of the canvas instead of flipping to the other side.
  const isNearRightEdge = canvasWidth ? (x + 160 + 200 > canvasWidth || x > canvasWidth - 180) : false;
  const isNearBottomEdge = canvasHeight ? (y + 160 > canvasHeight - 60) : false;

  const submenuXClass = isNearRightEdge ? 'right-full left-auto' : 'left-full right-auto';
  const submenuYClass = isNearBottomEdge ? 'bottom-0 top-auto' : 'top-0 bottom-auto';

  return (
    <div
      className={`absolute z-[10000] flex flex-col py-1 min-w-[160px] rounded-none border backdrop-blur-md shadow-xl select-none ${theme === 'hc-light'
        ? 'bg-white border-zinc-300 text-zinc-900 shadow-zinc-400/20'
        : 'bg-zinc-950/95 border-white/10 text-zinc-100 shadow-black/60'
        }`}
      style={{ left: x, top: y }}
      onMouseDown={(e) => e.stopPropagation()}
      onClick={(e) => e.stopPropagation()}
    >
      {/* 1. Freehand Pen Tool */}
      <div
        className={`flex items-center justify-between px-2.5 py-1.5 text-xs font-medium cursor-pointer transition-colors rounded-none ${
          isPenActive
            ? theme === 'hc-light'
              ? 'bg-red-50 text-red-600 font-semibold'
              : 'bg-red-500/20 text-red-400 font-semibold'
            : theme === 'hc-light'
              ? 'hover:bg-cyan-600/10 hover:text-cyan-700'
              : 'hover:bg-cyan-500/15 hover:text-cyan-400'
        }`}
        onClick={() => {
          setIsPenActive(!isPenActive);
          setRedrawTrigger((prev) => prev + 1);
          onClose();
        }}
      >
        <div className="flex items-center gap-1.5">
          <PenTool size={13} className={isPenActive ? 'text-red-500' : ''} />
          <span>{isPenActive ? 'Exit Pen Tool (Esc)' : 'Draw with Pen'}</span>
        </div>
      </div>

      {/* Undo Last Pen Stroke */}
      {hasDrawingStrokes && (
        <div
          className={`flex items-center justify-between px-2.5 py-1 text-xs font-medium cursor-pointer transition-colors rounded-none ${
            theme === 'hc-light'
              ? 'hover:bg-cyan-600/10 hover:text-cyan-700'
              : 'hover:bg-cyan-500/15 hover:text-cyan-400'
          }`}
          onClick={() => {
            if (drawingId) undoLastPenStroke(drawingId);
            setRedrawTrigger((prev) => prev + 1);
            onClose();
          }}
        >
          <div className="flex items-center gap-1.5">
            <Undo2 size={13} />
            <span>Undo Pen Stroke</span>
          </div>
        </div>
      )}

      {/* Clear Pen Markings */}
      {hasDrawingStrokes && (
        <div
          className={`flex items-center justify-between px-2.5 py-1 text-xs font-medium cursor-pointer transition-colors rounded-none ${
            theme === 'hc-light'
              ? 'hover:bg-red-50 text-red-600'
              : 'hover:bg-red-500/15 text-red-400'
          }`}
          onClick={() => {
            if (drawingId) clearPenStrokes(drawingId);
            setRedrawTrigger((prev) => prev + 1);
            onClose();
          }}
        >
          <div className="flex items-center gap-1.5">
            <Trash2 size={13} />
            <span>Clear Pen Markings</span>
          </div>
        </div>
      )}

      <div className={`border-b my-1 ${theme === 'hc-light' ? 'border-zinc-200' : 'border-white/10'}`} />

      {/* 2. Direct Annotation Pin Creation -> Opens Modal */}
      <div
        className={`flex items-center justify-between px-2.5 py-1 text-xs font-medium cursor-pointer transition-colors rounded-none ${theme === 'hc-light'
          ? 'hover:bg-cyan-600/10 hover:text-cyan-700'
          : 'hover:bg-cyan-500/15 hover:text-cyan-400'
          }`}
        onClick={() => {
          if (!drawingId) return;
          onOpenAnnotationModal();
        }}
      >
        <div className="flex items-center gap-1.5">
          <Pin size={13} />
          <span>Add Annotation Pin</span>
        </div>
      </div>

      {/* 3. Show/Hide Labels */}
      <div
        className={`flex items-center justify-between px-2.5 py-1 text-xs font-medium cursor-pointer transition-colors rounded-none ${theme === 'hc-light'
          ? 'hover:bg-cyan-600/10 hover:text-cyan-700'
          : 'hover:bg-cyan-500/15 hover:text-cyan-400'
          }`}
        onClick={() => {
          toggleMarkerLabels();
          onClose();
        }}
      >
        <div className="flex items-center gap-1.5">
          {showMarkerLabels ? <EyeOff size={13} /> : <Eye size={13} />}
          <span>{showMarkerLabels ? 'Hide Labels' : 'Show Labels'}</span>
        </div>
      </div>

      {/* Global Undo */}
      <div
        className={`flex items-center justify-between px-2.5 py-1 text-xs font-medium rounded-none ${
          !canUndo
            ? 'opacity-40 pointer-events-none text-zinc-500'
            : `cursor-pointer transition-colors ${
                theme === 'hc-light'
                  ? 'hover:bg-cyan-600/10 hover:text-cyan-700'
                  : 'hover:bg-cyan-500/15 hover:text-cyan-400'
              }`
        }`}
        onClick={() => {
          if (useHistoryStore.getState().past.length > 0) {
            performUndo();
          } else if (drawingId && hasDrawingStrokes) {
            undoLastPenStroke(drawingId);
          }
          setRedrawTrigger((prev) => prev + 1);
          onClose();
        }}
      >
        <div className="flex items-center gap-1.5">
          <Undo2 size={13} />
          <span>Undo</span>
        </div>
        <span className="text-[10px] text-zinc-400 font-mono ml-2">Ctrl+Z</span>
      </div>

      {/* Global Redo */}
      {canRedo && (
        <div
          className={`flex items-center justify-between px-2.5 py-1 text-xs font-medium cursor-pointer transition-colors rounded-none ${
            theme === 'hc-light'
              ? 'hover:bg-cyan-600/10 hover:text-cyan-700'
              : 'hover:bg-cyan-500/15 hover:text-cyan-400'
          }`}
          onClick={() => {
            performRedo();
            setRedrawTrigger((prev) => prev + 1);
            onClose();
          }}
        >
          <div className="flex items-center gap-1.5">
            <Redo2 size={13} />
            <span>Redo</span>
          </div>
          <span className="text-[10px] text-zinc-400 font-mono ml-2">Ctrl+Y</span>
        </div>
      )}

      {/* 4. Undo Delete */}
      <div
        className={`flex items-center justify-between px-2.5 py-1 text-xs font-medium rounded-none ${useWorkspaceStore.getState().deletedViolationsStack.length === 0
          ? 'opacity-40 pointer-events-none text-zinc-500'
          : `cursor-pointer transition-colors ${theme === 'hc-light'
            ? 'hover:bg-cyan-600/10 hover:text-cyan-700'
            : 'hover:bg-cyan-500/15 hover:text-cyan-400'
          }`
          }`}
        onClick={() => {
          useWorkspaceStore.getState().popAndRestoreViolation();
          onClose();
        }}
      >
        <div className="flex items-center gap-1.5">
          <RotateCcw size={13} />
          <span>Undo Delete</span>
        </div>
        {useWorkspaceStore.getState().deletedViolationsStack.length > 0 && (
          <span className="text-[0.62rem] bg-white/10 px-1 py-0.5 ml-1.5 font-mono">
            {useWorkspaceStore.getState().deletedViolationsStack.length}
          </span>
        )}
      </div>

      <div className={`border-b my-1 ${theme === 'hc-light' ? 'border-zinc-200' : 'border-white/10'}`} />

      {/* 4. Filter Markers Submenu */}
      <div
        className={`group/filterSubmenu relative flex items-center justify-between px-2.5 py-1 text-xs font-medium cursor-pointer transition-colors rounded-none ${theme === 'hc-light'
          ? 'hover:bg-cyan-600/10 hover:text-cyan-700'
          : 'hover:bg-cyan-500/15 hover:text-cyan-400'
          }`}
      >
        <div className="flex items-center gap-1.5">
          <Filter size={13} />
          <span>Filter Markers</span>
        </div>
        <ChevronRight size={12} className="opacity-60 ml-2" />

        {/* Filter Submenu Dropdown */}
        <div
          className={`absolute ${submenuXClass} ${submenuYClass} hidden group-hover/filterSubmenu:flex flex-col py-1 min-w-[140px] rounded-none border backdrop-blur-md shadow-xl z-[10001] ${theme === 'hc-light'
            ? 'bg-white border-zinc-300 text-zinc-900 shadow-zinc-400/20'
            : 'bg-zinc-950/98 border-white/10 text-zinc-100 shadow-black/60'
            }`}
        >
          {/* Read off the shared table, not restated. This list held a THIRD set of colours for
              the same five words — `#ef4444` here against `#ff2850` on the canvas — so the swatch
              beside a filter did not match the marker it filtered. It also lacked REMOVED, which
              a manual check produces: absent from the list is not the same as filtered out, but
              it did mean the one status an engineer records most on the reference had no way to
              be hidden. */}
          {FILTERABLE_MARKERS.map((key) => {
            const item = { label: key, key, color: MARKER_STYLES[key].color };
            const isActive = useReviewStore.getState().visibleMarkerTypes[item.key] ?? true;
            return (
              <div
                key={item.key}
                className={`flex items-center justify-between px-2.5 py-1 text-xs font-medium cursor-pointer transition-colors rounded-none ${theme === 'hc-light'
                  ? 'hover:bg-cyan-600/10 hover:text-cyan-700'
                  : 'hover:bg-cyan-500/15 hover:text-cyan-400'
                  }`}
                onClick={(e) => {
                  e.stopPropagation();
                  useReviewStore.getState().toggleMarkerTypeVisibility(item.key);
                  setRedrawTrigger((prev) => prev + 1);
                }}
                style={{ opacity: isActive ? 1 : 0.45 }}
              >
                <div className="flex items-center gap-1.5">
                  <div className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: item.color }} />
                  <span className="text-[0.72rem]">{item.label}</span>
                </div>
                {!isActive && <span className="text-[0.65rem] opacity-60">Hidden</span>}
              </div>
            );
          })}
        </div>
      </div>

      {/*
        Manual engineer check.

        Only ONE thing from that workflow lives in this menu: cancelling a pairing in flight.
        Everything else — the categories, the entity being marked — moved to `SelectionMenu` on
        2026-08-18, opened by the left-click that selects. This menu is the canvas's toolbox, and
        a marking taxonomy sitting in it made the engineer hunt for view controls among finding
        types and vice versa.

        Cancelling stays because this is the only surface that opens with NOTHING selected, which
        is exactly the state someone is in when they change their mind about a half-made pair.
        Without it the first half of a pair is unreachable state.
      */}
      {isManualCheckRoom && pendingPairRef && (
        <div
          className={`flex items-center gap-1.5 px-2.5 py-1 text-xs cursor-pointer opacity-70 hover:opacity-100 border-t ${theme === 'hc-light' ? 'border-zinc-200' : 'border-white/10'}`}
          onClick={() => {
            setPendingPairRef(null);
            onClose();
          }}
        >
          <span className="text-[0.7rem]">Cancel pairing</span>
        </div>
      )}

      {/* 5. Add Marker Submenu — AI rooms only.

          These markers are client-side and ephemeral (`custom_marker_*`, never persisted, and
          locked out of every write-back path by `isPersistedViolationId`). Useful as a scratch
          annotation next to engine output; useless as ground truth, which is why a manual-check
          room offers the section above instead. */}
      {!isManualCheckRoom && (
      <div
        className={`group/markerSubmenu relative flex items-center justify-between px-2.5 py-1 text-xs font-medium cursor-pointer transition-colors rounded-none ${theme === 'hc-light'
          ? 'hover:bg-cyan-600/10 hover:text-cyan-700'
          : 'hover:bg-cyan-500/15 hover:text-cyan-400'
          }`}
      >
        <div className="flex items-center gap-1.5">
          <Plus size={13} />
          <span>Add Marker</span>
        </div>
        <ChevronRight size={12} className="opacity-60 ml-2" />

        <div
          className={`absolute ${submenuXClass} ${submenuYClass} hidden group-hover/markerSubmenu:flex flex-col py-1 min-w-[130px] rounded-none border backdrop-blur-md shadow-xl z-[10001] ${theme === 'hc-light'
            ? 'bg-white border-zinc-300 text-zinc-900'
            : 'bg-zinc-950/98 border-white/10 text-zinc-100'
            }`}
        >
          {/* Colour from the shared table, `pen_type` kept: these markers are written into the
              violations list, which stores pen types. The label and swatch now match the badge
              the click produces — they were two shades off. */}
          {([
            { type: 'ai_green', isResolved: true, status: 'MATCHED' },
            { type: 'ai_red', isResolved: false, status: 'MISMATCHED' },
            { type: 'ai_orange', isResolved: false, status: 'CHANGED' },
            { type: 'checker_blue', isResolved: false, status: 'ADDED' },
          ] as const).map((o) => ({ ...o, label: o.status, color: MARKER_STYLES[o.status].color })).map((opt) => (
            <div
              key={opt.label}
              className={`flex items-center justify-between px-2.5 py-1 text-xs font-medium cursor-pointer transition-colors rounded-none ${theme === 'hc-light'
                ? 'hover:bg-cyan-600/10 hover:text-cyan-700'
                : 'hover:bg-cyan-500/15 hover:text-cyan-400'
                }`}
              onClick={() => {
                const newMarker: any = {
                  id: `custom_marker_${Date.now()}`,
                  severity: opt.status === 'MATCHED' ? 'low' : 'high',
                  category: 'Manual Marker',
                  description: 'Manually added marker',
                  recommendation: 'Manual verification check',
                  affected_entities: [],
                  confidence: 1.0,
                  coordinates: [wx, wy] as [number, number],
                  ref_coordinates: [wx, wy] as [number, number],
                  pen_type: opt.type,
                  is_resolved: opt.isResolved,
                  status: opt.status,
                };
                const current = useWorkspaceStore.getState().violations;
                useWorkspaceStore.getState().setViolations([...current, newMarker]);
                setRedrawTrigger((prev) => prev + 1);
                onClose();
              }}
            >
              <div className="flex items-center gap-1.5">
                <div className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: opt.color }} />
                <span className="text-[0.72rem]">{opt.label}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
      )}
    </div>
  );
};
