import React from 'react';
import { Eye, EyeOff, RotateCcw, Pin, Filter, Plus, ChevronRight } from 'lucide-react';
import { useReviewStore } from '../../stores/reviewStore';
import { useWorkspaceStore } from '../../stores/workspaceStore';
import { AnnotationSeverity } from '../../stores/workspace/types';

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

      {/* 5. Add Marker Submenu */}
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
    </div>
  );
};
