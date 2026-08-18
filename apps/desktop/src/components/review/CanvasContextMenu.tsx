import React from 'react';
import { Eye, EyeOff, RotateCcw, Pin, Filter, Plus, ChevronRight } from 'lucide-react';
import { useReviewStore } from '../../stores/reviewStore';
import { useWorkspaceStore } from '../../stores/workspaceStore';
import { AnnotationSeverity, type StampTool } from '../../stores/workspace/types';
import { useIsManualCheckRoom } from '../../hooks/useManualCheckRoom';
import { TOOL_SIDE } from '../../stores/workspace/slices/createManualCheckSlice';

interface CanvasContextMenuProps {
  x: number;
  y: number;
  wx: number;
  wy: number;
  drawingId?: string;
  canvasWidth?: number;
  canvasHeight?: number;
  theme: string;
  onOpenAnnotationModal: (severity: AnnotationSeverity) => void;
  onClose: () => void;
  setRedrawTrigger: React.Dispatch<React.SetStateAction<number>>;
}

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

  // Manual engineer check. In such a room this menu is the ONLY way to put a mark on the
  // drawing — there is no toolbar and no left-click gesture, so there is never a moment when
  // two ways of marking are both live and mean different things.
  const isManualCheckRoom = useIsManualCheckRoom();
  const selectedEntities = useWorkspaceStore((s) => s.selectedEntities);
  // The selection is one entity today, so this is it. Written as an anchor rather than
  // `selectedEntities[0]!` because the list is what the store holds, and a marking is recorded
  // against exactly one entity either way.
  const picked = selectedEntities[0] ?? null;
  const pendingPairRef = useWorkspaceStore((s) => s.pendingPairRef);
  const setPendingPairRef = useWorkspaceStore((s) => s.setPendingPairRef);
  const openStamp = useWorkspaceStore((s) => s.openStamp);

  const MANUAL_TOOLS: { tool: StampTool; label: string; color: string }[] = [
    { tool: 'matched', label: 'Matched', color: '#10b981' },
    { tool: 'added', label: 'Added', color: '#3b82f6' },
    { tool: 'removed', label: 'Removed', color: '#ef4444' },
    { tool: 'not_a_finding', label: 'Not a finding', color: '#a1a1aa' },
  ];

  // Context-aware positioning: detect right & bottom boundaries so submenus fly out cleanly without clipping
  const isNearRightEdge = canvasWidth ? (x + 160 + 145 > canvasWidth || x > canvasWidth - 180) : false;
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
      <div className={`px-2.5 py-1 text-[10px] font-mono text-cyan-400 border-b flex items-center justify-between ${theme === 'hc-light' ? 'border-zinc-200 bg-zinc-50 text-cyan-700' : 'border-white/10 bg-black/40'}`}>
        <span>CAD World</span>
        <span className="font-bold">({wx.toFixed(1)}, {wy.toFixed(1)})</span>
      </div>
      {/* 1. Direct Annotation Pin Creation -> Opens Modal */}
      <div
        className={`flex items-center justify-between px-2.5 py-1 text-xs font-medium cursor-pointer transition-colors rounded-none ${theme === 'hc-light'
          ? 'hover:bg-cyan-600/10 hover:text-cyan-700'
          : 'hover:bg-cyan-500/15 hover:text-cyan-400'
          }`}
        onClick={() => {
          if (!drawingId) return;
          onOpenAnnotationModal('info');
        }}
      >
        <div className="flex items-center gap-1.5">
          <Pin size={13} />
          <span>Add Annotation Pin</span>
        </div>
      </div>

      {/* 2. Show/Hide Labels */}
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

      {/* 3. Undo Delete */}
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
          {[
            { label: 'MISMATCHED', key: 'MISMATCHED', color: '#ef4444' },
            { label: 'CHANGED', key: 'CHANGED', color: '#f97316' },
            { label: 'ADDED', key: 'ADDED', color: '#3b82f6' },
            { label: 'MATCHED', key: 'MATCHED', color: '#10b981' },
            { label: 'CONFLICT', key: 'CONFLICT', color: '#a855f7' },
          ].map((item) => {
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
        Manual engineer check — this replaces the Add Marker submenu below rather than sitting
        beside it. The two produce different things (a ground-truth record vs an ephemeral
        client-side pin) and offering both at once is how a checker records an hour of work into
        the wrong place.

        Since 2026-08-18 this section is opened by a LEFT-click on an entity, not a right-click.
        A right-click still opens the menu — it is the only surface that can cancel a pairing in
        flight — but resolves no entity, so it falls to the hint above. One gesture records a
        finding; see `useEntityPicking`.
      */}
      {isManualCheckRoom && (
        <>
          {!picked ? (
            <div className="px-2.5 py-1.5 text-[0.68rem] leading-snug opacity-60">
              Left-click an entity, or drag a box over several, then right-click here.
            </div>
          ) : (
            <>
              <div
                className={`px-2.5 py-1 text-[0.62rem] font-mono truncate border-b ${theme === 'hc-light' ? 'border-zinc-200 text-zinc-500' : 'border-white/10 text-zinc-500'}`}
                title={picked.text || picked.entityType}
              >
                {picked.side === 'ref' ? 'REFERENCE' : 'REVISION'} ·{' '}
                {selectedEntities.length > 1
                  ? `${selectedEntities.length} entities selected`
                  : picked.text || picked.entityType}
              </div>

              {MANUAL_TOOLS.filter(
                (t) =>
                  TOOL_SIDE[t.tool] === picked.side ||
                  // "I looked at this and it is deliberately not a finding" is an attribution
                  // about one entity, not a claim about a side — the engine can over-report on
                  // either sheet, and on the reference this was previously unrecordable.
                  t.tool === 'not_a_finding',
              ).map((opt) => (
                <div
                  key={opt.tool}
                  className={`flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium cursor-pointer transition-colors ${theme === 'hc-light'
                    ? 'hover:bg-cyan-600/10 hover:text-cyan-700'
                    : 'hover:bg-cyan-500/15 hover:text-cyan-400'
                    }`}
                  onClick={() => {
                    openStamp({
                      tool: opt.tool,
                      ref: picked.side === 'ref' ? picked : null,
                      rev: picked.side === 'rev' ? picked : null,
                    });
                    onClose();
                  }}
                >
                  <div className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: opt.color }} />
                  <span className="text-[0.72rem]">{opt.label}</span>
                </div>
              ))}

              {/* CHANGED is two clicks because it is two entities, and each must contribute its
                  OWN coordinate. The old marker collapsed both sides onto one point, which is
                  meaningless the moment a revision is re-traced. */}
              {picked.side === 'ref' && (
                <div
                  className={`flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium cursor-pointer transition-colors ${theme === 'hc-light'
                    ? 'hover:bg-cyan-600/10 hover:text-cyan-700'
                    : 'hover:bg-cyan-500/15 hover:text-cyan-400'
                    }`}
                  onClick={() => {
                    setPendingPairRef(picked);
                    onClose();
                  }}
                >
                  <div className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: '#f97316' }} />
                  <span className="text-[0.72rem]">Changed — pick counterpart…</span>
                </div>
              )}

              {picked.side === 'rev' && pendingPairRef && (
                <div
                  className={`flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium cursor-pointer transition-colors ${theme === 'hc-light'
                    ? 'hover:bg-orange-600/10 hover:text-orange-700'
                    : 'hover:bg-orange-500/15 hover:text-orange-400'
                    }`}
                  onClick={() => {
                    openStamp({ tool: 'changed', ref: pendingPairRef, rev: picked });
                    onClose();
                  }}
                >
                  <div className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: '#f97316' }} />
                  <span className="text-[0.72rem] truncate">
                    Changed from “{pendingPairRef.text || pendingPairRef.entityType}”
                  </span>
                </div>
              )}
            </>
          )}

          {/* A pairing in flight is cancellable from here, because it is the only surface that
              can show it — without this the first half of a pair is invisible state. */}
          {pendingPairRef && (
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
        </>
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
          {[
            { label: 'MATCHED', type: 'ai_green', isResolved: true, status: 'MATCHED', color: '#10b981' },
            { label: 'MISMATCHED', type: 'ai_red', isResolved: false, status: 'MISMATCHED', color: '#ef4444' },
            { label: 'CHANGED', type: 'ai_orange', isResolved: false, status: 'CHANGED', color: '#f97316' },
            { label: 'ADDED', type: 'checker_blue', isResolved: false, status: 'ADDED', color: '#3b82f6' },
          ].map((opt) => (
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
