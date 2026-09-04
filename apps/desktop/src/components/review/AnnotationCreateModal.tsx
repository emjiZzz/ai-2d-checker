import React, { useState } from 'react';
import { X } from 'lucide-react';
import { useWorkspaceStore } from '../../stores/workspaceStore';
import { useReviewStore } from '../../stores/reviewStore';
import { AnnotationSeverity } from '../../stores/workspace/types';

interface AnnotationCreateModalProps {
  x: number;
  y: number;
  wx: number;
  wy: number;
  severity?: AnnotationSeverity;
  drawingId?: string;
  canvasWidth: number;
  canvasHeight: number;
  theme: string;
  onClose: () => void;
  setRedrawTrigger: React.Dispatch<React.SetStateAction<number>>;
}

export const AnnotationCreateModal: React.FC<AnnotationCreateModalProps> = ({
  x,
  y,
  wx,
  wy,
  drawingId,
  canvasWidth,
  canvasHeight,
  theme,
  onClose,
  setRedrawTrigger,
}) => {
  const [content, setContent] = useState('');
  const createAnnotationAt = useWorkspaceStore((s) => s.createAnnotationAt);
  const showAnnotations = useReviewStore((s) => s.showAnnotations);
  const toggleAnnotations = useReviewStore((s) => s.toggleAnnotations);

  const handleSubmit = async () => {
    if (!drawingId || !content.trim()) return;
    await createAnnotationAt([wx, wy], content.trim(), drawingId);
    if (!showAnnotations) toggleAnnotations();
    setRedrawTrigger((prev) => prev + 1);
    onClose();
  };

  return (
    <div
      className={`absolute z-[10005] p-3 w-72 rounded-none border backdrop-blur-md shadow-2xl select-none ${theme === 'hc-light'
          ? 'bg-white border-zinc-300 text-zinc-900 shadow-zinc-400/30'
          : 'bg-zinc-950/98 border-white/15 text-zinc-100 shadow-black/80'
        }`}
      style={{
        left: Math.min(Math.max(10, x), canvasWidth - 300),
        top: Math.min(Math.max(10, y), canvasHeight - 200),
      }}
      onMouseDown={(e) => e.stopPropagation()}
      onClick={(e) => e.stopPropagation()}
    >
      <div className="flex items-center justify-between mb-2">
        <label className="text-[10px] font-bold text-zinc-400 uppercase tracking-wider block">
          Add Annotation Note
        </label>
        <button
          type="button"
          className="text-zinc-400 hover:text-white transition-colors cursor-pointer p-0.5"
          onClick={onClose}
        >
          <X size={14} />
        </button>
      </div>

      {/* Note textarea */}
      <textarea
        autoFocus
        className={`w-full text-xs p-2 rounded-none border outline-none resize-none mb-2.5 ${theme === 'hc-light'
            ? 'bg-zinc-50 border-zinc-300 text-zinc-900 focus:border-cyan-600'
            : 'bg-zinc-900/90 border-white/10 text-zinc-100 focus:border-cyan-400'
          }`}
        rows={3}
        placeholder="Add engineering review note..."
        value={content}
        onChange={(e) => setContent(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
            e.preventDefault();
            handleSubmit();
          }
        }}
      />

      {/* Actions */}
      <div className="flex gap-1.5">
        <button
          type="button"
          className={`flex-1 font-bold py-1.5 px-3 rounded-none text-xs transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed ${theme === 'hc-light'
              ? 'bg-cyan-600 hover:bg-cyan-700 text-white'
              : 'bg-cyan-500 hover:bg-cyan-400 text-zinc-950'
            }`}
          disabled={!drawingId || !content.trim()}
          onClick={handleSubmit}
        >
          Add
        </button>
        <button
          type="button"
          className={`px-3 font-medium py-1.5 rounded-none text-xs transition-colors cursor-pointer ${theme === 'hc-light'
              ? 'bg-zinc-200 hover:bg-zinc-300 text-zinc-700'
              : 'bg-zinc-800 hover:bg-zinc-700 text-zinc-300'
            }`}
          onClick={onClose}
        >
          Cancel
        </button>
      </div>
    </div>
  );
};
