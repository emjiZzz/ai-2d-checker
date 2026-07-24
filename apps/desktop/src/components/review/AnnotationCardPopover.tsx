import React, { useState } from 'react';
import { X, Edit2, Check, Trash2, Save } from 'lucide-react';
import { useWorkspaceStore } from '../../stores/workspaceStore';
import { AnnotationItem, AnnotationSeverity, SEVERITY_PEN_MAP } from '../../stores/workspace/types';

interface AnnotationCardPopoverProps {
  annotation: AnnotationItem;
  badgeNumber?: string;
  x: number;
  y: number;
  canvasWidth: number;
  canvasHeight: number;
  theme: string;
  onClose: () => void;
  setRedrawTrigger: React.Dispatch<React.SetStateAction<number>>;
}

const SEVERITY_BADGES: Record<AnnotationSeverity, { label: string; bg: string; text: string; border: string }> = {
  info: { label: 'INFO', bg: 'bg-cyan-500/20', text: 'text-cyan-400', border: 'border-cyan-500' },
  low: { label: 'LOW', bg: 'bg-blue-500/20', text: 'text-blue-400', border: 'border-blue-500' },
  medium: { label: 'MED', bg: 'bg-yellow-500/20', text: 'text-yellow-400', border: 'border-yellow-500' },
  high: { label: 'HIGH', bg: 'bg-orange-500/20', text: 'text-orange-400', border: 'border-orange-500' },
  critical: { label: 'CRIT', bg: 'bg-red-500/20', text: 'text-red-400', border: 'border-red-500' },
};

const SEVERITY_COLORS: Record<AnnotationSeverity, string> = {
  info: '#06b6d4',     // cyan-500
  low: '#3b82f6',      // blue-500
  medium: '#eab308',   // yellow-500
  high: '#f97316',     // orange-500
  critical: '#ef4444', // red-500
};

export const AnnotationCardPopover: React.FC<AnnotationCardPopoverProps> = ({
  annotation,
  badgeNumber,
  x,
  y,
  canvasWidth,
  canvasHeight,
  theme,
  onClose,
  setRedrawTrigger,
}) => {
  const [isEditing, setIsEditing] = useState(false);
  const [editContent, setEditContent] = useState(annotation.content);
  const [editSeverity, setEditSeverity] = useState<AnnotationSeverity>(annotation.severity);

  const updateAnnotationDetails = useWorkspaceStore((s) => s.updateAnnotationDetails);
  const updateAnnotationStatus = useWorkspaceStore((s) => s.updateAnnotationStatus);
  const deleteAnnotationById = useWorkspaceStore((s) => s.deleteAnnotationById);

  const dateStr = annotation.created_at
    ? new Date(annotation.created_at).toLocaleDateString()
    : new Date().toLocaleDateString();

  const severityColor = SEVERITY_COLORS[annotation.severity] || '#06b6d4';

  const handleSaveEdit = async () => {
    if (!editContent.trim()) return;
    const penType = SEVERITY_PEN_MAP[editSeverity] || 'checker_blue';
    await updateAnnotationDetails(annotation.id, {
      content: editContent.trim(),
      severity: editSeverity,
      pen_type: penType,
    });
    setIsEditing(false);
    setRedrawTrigger((prev) => prev + 1);
  };

  const handleToggleStatus = async (e: React.MouseEvent) => {
    e.stopPropagation();
    const newStatus = annotation.status === 'resolved' ? 'open' : 'resolved';
    await updateAnnotationStatus(annotation.id, newStatus);
    setRedrawTrigger((prev) => prev + 1);
  };

  const handleDelete = async (e: React.MouseEvent) => {
    e.stopPropagation();
    await deleteAnnotationById(annotation.id);
    setRedrawTrigger((prev) => prev + 1);
    onClose();
  };

  // ── Standard CAD Dog-Leg Leader Line Geometry Math ─────────────────────────
  const popoverWidth = 280;
  const popoverHeight = isEditing ? 250 : 140;
  const diagLen = 50;  // Long 45-degree diagonal extension length
  const horizLen = 45; // Long horizontal landing line extension length

  // Determine East (NE 45°) vs West (NW 45°) direction based on right boundary
  const isWest = x + diagLen + horizLen + popoverWidth > canvasWidth - 10;

  const kneeX = isWest ? x - diagLen : x + diagLen;
  const kneeY = y - diagLen; // Elevates knee 50px higher than pin

  const landingEndX = isWest ? kneeX - horizLen : kneeX + horizLen;
  const popoverX = isWest ? landingEndX - popoverWidth : landingEndX;
  let popoverY = kneeY - 25; // Positions popover card higher and above pin

  // Viewport boundary clamps
  if (popoverX < 10) {
    popoverY = kneeY - 25;
  }
  if (popoverY + popoverHeight > canvasHeight - 10) {
    popoverY = canvasHeight - popoverHeight - 10;
  }
  if (popoverY < 10) {
    popoverY = 10;
  }

  // Arrowhead pointing at pin reticle with 18px clearance offset
  const angle = Math.atan2(y - kneeY, x - kneeX);
  const pinOffset = 18; // Clean clearance space away from pin reticle center
  const tipX = x - pinOffset * Math.cos(angle);
  const tipY = y - pinOffset * Math.sin(angle);
  const headLen = 8;

  const arrowP1X = tipX - headLen * Math.cos(angle - Math.PI / 6);
  const arrowP1Y = tipY - headLen * Math.sin(angle - Math.PI / 6);
  const arrowP2X = tipX - headLen * Math.cos(angle + Math.PI / 6);
  const arrowP2Y = tipY - headLen * Math.sin(angle + Math.PI / 6);

  const cardAttachX = isWest ? popoverX + popoverWidth : popoverX;

  return (
    <>
      {/* CAD Standard Leader Line SVG Overlay (Long 45° Diagonal Knee + Long Horizontal Landing) */}
      <svg
        className="absolute inset-0 w-full h-full pointer-events-none z-[10001]"
        style={{ width: canvasWidth, height: canvasHeight }}
      >
        <path
          d={`M ${cardAttachX} ${kneeY} L ${kneeX} ${kneeY} L ${tipX} ${tipY}`}
          stroke={severityColor}
          strokeWidth="1.5"
          fill="none"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <polygon
          points={`${tipX},${tipY} ${arrowP1X},${arrowP1Y} ${arrowP2X},${arrowP2Y}`}
          fill={severityColor}
        />
      </svg>

      {/* Popover Callout Card */}
      <div
        className={`absolute z-[10002] p-3 w-72 rounded-none backdrop-blur-md shadow-2xl select-none ${
          theme === 'hc-light'
            ? 'bg-white text-zinc-900 shadow-zinc-400/30'
            : 'bg-zinc-950/98 text-zinc-100 shadow-black/80'
        }`}
        style={{
          left: popoverX,
          top: popoverY,
          border: `1px solid ${severityColor}`,
        }}
        onMouseDown={(e) => e.stopPropagation()}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Name & Date Header */}
        <div className="flex items-center justify-between pb-1.5 border-b border-white/10 text-xs font-mono">
          <div className="flex items-center gap-1.5 truncate">
            {badgeNumber && (
              <span className="text-[10px] font-bold font-mono px-1 py-0.2 rounded-none bg-blue-500/20 text-blue-400 border border-blue-500/40 shrink-0">
                {badgeNumber}
              </span>
            )}
            <span className={`font-semibold truncate ${theme === 'hc-light' ? 'text-zinc-900' : 'text-zinc-100'}`}>
              {annotation.author_id}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[10px] text-zinc-400 font-mono">{dateStr}</span>
            <button
              type="button"
              className="text-zinc-400 hover:text-white transition-colors cursor-pointer p-0.5"
              onClick={onClose}
              title="Close"
            >
              <X size={13} />
            </button>
          </div>
        </div>

        {/* Message Content Body */}
        {isEditing ? (
          <div className="py-2">
            {/* Severity selector grid for editing */}
            <div className="grid grid-cols-5 gap-1 mb-2">
              {(['info', 'low', 'medium', 'high', 'critical'] as AnnotationSeverity[]).map((sev) => {
                const info = SEVERITY_BADGES[sev];
                const isSelected = editSeverity === sev;
                return (
                  <button
                    key={sev}
                    type="button"
                    className={`py-0.5 text-[9px] font-bold rounded-none border transition-colors cursor-pointer ${
                      isSelected
                        ? `${info.bg} ${info.text} ${info.border} ring-1 ring-cyan-400`
                        : theme === 'hc-light'
                        ? 'bg-zinc-100 text-zinc-600 border-zinc-200'
                        : 'bg-zinc-900 text-zinc-400 border-white/10'
                    }`}
                    onClick={() => setEditSeverity(sev)}
                  >
                    {info.label}
                  </button>
                );
              })}
            </div>

            <textarea
              autoFocus
              className={`w-full text-xs p-1.5 rounded-none border outline-none resize-none mb-2 ${
                theme === 'hc-light'
                  ? 'bg-zinc-50 border-zinc-300 text-zinc-900 focus:border-cyan-600'
                  : 'bg-zinc-900/90 border-white/10 text-zinc-100 focus:border-cyan-400'
              }`}
              rows={3}
              value={editContent}
              onChange={(e) => setEditContent(e.target.value)}
            />

            <div className="flex justify-end gap-1.5">
              <button
                type="button"
                className="flex items-center gap-1 text-xs font-bold py-1 px-2.5 rounded-none bg-cyan-500 hover:bg-cyan-400 text-zinc-950 transition-colors cursor-pointer"
                onClick={handleSaveEdit}
              >
                <Save size={12} />
                <span>Save</span>
              </button>
              <button
                type="button"
                className="text-xs font-medium py-1 px-2.5 rounded-none bg-zinc-800 hover:bg-zinc-700 text-zinc-300 transition-colors cursor-pointer"
                onClick={() => setIsEditing(false)}
              >
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <div
            className={`text-xs py-2 leading-relaxed ${
              annotation.status === 'resolved'
                ? 'line-through text-zinc-400 opacity-60'
                : theme === 'hc-light'
                ? 'text-zinc-800'
                : 'text-zinc-200'
            }`}
          >
            {annotation.content}
          </div>
        )}

        {/* Footer: Author on bottom-left, Icon-Only Action Buttons on bottom-right */}
        {!isEditing && (
          <div className="flex items-center justify-between pt-1.5 border-t border-white/10 text-[10px] text-zinc-400">
            <span>By {annotation.author_id}</span>
            <div className="flex items-center gap-2.5">
              <button
                type="button"
                className="hover:text-cyan-400 transition-colors cursor-pointer p-0.5"
                title="Edit note & severity"
                onClick={() => setIsEditing(true)}
              >
                <Edit2 size={13} />
              </button>
              <button
                type="button"
                className={`transition-colors cursor-pointer p-0.5 ${
                  annotation.status === 'resolved' ? 'text-green-400' : 'hover:text-green-400'
                }`}
                title={annotation.status === 'resolved' ? 'Reopen note' : 'Mark resolved'}
                onClick={handleToggleStatus}
              >
                <Check size={13} />
              </button>
              <button
                type="button"
                className="hover:text-red-400 transition-colors cursor-pointer p-0.5"
                title="Delete annotation"
                onClick={handleDelete}
              >
                <Trash2 size={13} />
              </button>
            </div>
          </div>
        )}
      </div>
    </>
  );
};
