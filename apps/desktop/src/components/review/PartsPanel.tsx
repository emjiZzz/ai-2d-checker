import React, { useState } from "react";
import { ChevronLeft, ChevronRight, Eye, EyeOff } from "lucide-react";
import { useReviewStore } from "../../stores/reviewStore";

export interface AssemblyPart {
  index: number;
  node: number;
  name: string;
  surfaces: number;
  triangles: number;
  volume_mm3: number | null;
}

interface PartsPanelProps {
  drawingId: string;
  parts: AssemblyPart[];
}

/**
 * Collapsible sidebar overlay for the assembly's parts.
 *
 * - Clicking an item row highlights that specific part in the 3D model.
 * - Clicking the eye icon hides/shows that part in the 3D model.
 * - Pinned to the overlay sidebar with a smooth collapse/expand toggle.
 */
export const PartsPanel: React.FC<PartsPanelProps> = ({ drawingId, parts }) => {
  const [isOpen, setIsOpen] = useState(true);
  const hidden = useReviewStore((s) => s.hiddenParts[drawingId]);
  const togglePart = useReviewStore((s) => s.togglePart);
  const selectedPart = useReviewStore((s) => s.selectedPart[drawingId] ?? null);
  const setSelectedPart = useReviewStore((s) => s.setSelectedPart);

  if (!parts || parts.length < 2) return null;

  const hiddenSet = new Set(hidden ?? []);

  if (!isOpen) {
    return (
      <div className="absolute top-11 right-2 z-20 select-none">
        <button
          type="button"
          onClick={() => setIsOpen(true)}
          className="flex items-center gap-1.5 px-2.5 py-1.5 rounded border border-border-color bg-bg-card/90 hover:bg-bg-card hover:border-accent-cyan/80 backdrop-blur-sm text-text-primary shadow-md text-xs font-mono font-semibold cursor-pointer transition-all group"
          title="Expand Parts Sidebar"
          aria-label="Expand Parts Sidebar"
        >
          <ChevronLeft size={13} className="text-text-muted group-hover:text-accent-cyan transition-colors" />
          <span>PARTS</span>
          <span className="text-text-muted text-[10px]">({parts.length})</span>
        </button>
      </div>
    );
  }

  return (
    <div className="absolute top-11 right-2 z-20 w-44 max-h-[calc(100%-4rem)] flex flex-col rounded border border-border-color bg-bg-card/95 backdrop-blur-md text-text-primary shadow-xl select-none transition-all">
      {/* Header */}
      <div className="flex items-center justify-between px-2.5 py-1.5 border-b border-border-color bg-bg-card/70">
        <div className="flex items-center gap-1.5 text-[11px] font-semibold tracking-wide">
          <span>PARTS</span>
          <span className="text-text-muted font-normal text-[10px]">({parts.length})</span>
        </div>
        <button
          type="button"
          onClick={() => setIsOpen(false)}
          className="p-0.5 rounded text-text-muted hover:text-text-primary hover:bg-bg-dark/50 transition-colors cursor-pointer"
          title="Collapse Parts Sidebar"
          aria-label="Collapse Parts Sidebar"
        >
          <ChevronRight size={14} />
        </button>
      </div>

      {/* Parts List */}
      <ul className="overflow-y-auto py-1 flex-1 min-h-0">
        {parts.map((part) => {
          const isHidden = hiddenSet.has(part.node);
          const isSelected = selectedPart === part.node;

          return (
            <li key={part.node} className="px-1 py-0.5">
              <div
                role="button"
                tabIndex={0}
                onClick={() => setSelectedPart(drawingId, part.node)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    setSelectedPart(drawingId, part.node);
                  }
                }}
                aria-pressed={!isHidden}
                aria-selected={isSelected}
                title={`${part.name} — ${part.triangles.toLocaleString()} triangles, ${part.surfaces} surfaces${isSelected ? " (Selected in 3D)" : ""}`}
                className={[
                  "w-full flex items-center justify-between gap-2 px-2 py-1 text-left text-[11px] rounded transition-all cursor-pointer",
                  isSelected
                    ? "bg-accent-cyan/15 text-accent-cyan font-medium border border-accent-cyan/40 shadow-xs"
                    : isHidden
                    ? "text-text-muted/40 hover:bg-bg-dark/30"
                    : "text-text-primary hover:bg-bg-dark/50 hover:text-accent-cyan",
                ].join(" ")}
              >
                {/* Part Name: clicking row highlights only this part in 3D */}
                <span className="flex-1 truncate font-mono">{part.name}</span>

                {/* Eye Icon button: click toggles visibility on/off on the right side */}
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    togglePart(drawingId, part.node);
                  }}
                  className="p-0.5 rounded hover:bg-bg-dark/60 text-text-muted hover:text-text-primary transition-colors cursor-pointer shrink-0"
                  aria-label={`Toggle visibility of ${part.name}`}
                  title={isHidden ? "Show part in 3D" : "Hide part in 3D"}
                >
                  {isHidden ? (
                    <EyeOff size={12} className="text-text-muted/50" />
                  ) : (
                    <Eye size={12} className={isSelected ? "text-accent-cyan" : "text-text-muted"} />
                  )}
                </button>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
};
