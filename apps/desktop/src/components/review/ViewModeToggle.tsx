import React from "react";
import { hasThreeDMesh } from "../../config/drawingFormats";
import { useReviewStore } from "../../stores/reviewStore";
import type { DrawingItem } from "../../stores/workspace/types";

interface ViewModeToggleProps {
  side: "old" | "new";
  drawing: DrawingItem | null;
}

/**
 * Single-button 2D / 3D toggle for one pane.
 *
 * If the current view is 2D, the button displays "3D" to switch to 3D.
 * If the current view is 3D, the button displays "2D" to switch back to 2D.
 *
 * An .icd carries a drawing and a model, and iCAD SX switches between them in one workspace,
 * so this does too rather than making the engineer upload the same file into a second one.
 *
 * Per pane, not global. This view exists to hold two drawings side by side; flipping both at
 * once would take that away.
 *
 * Absent, not disabled, when the drawing has no model (pure 2D .dwg, .dxf, or sheet-only .icd).
 */
export const ViewModeToggle: React.FC<ViewModeToggleProps> = ({ side, drawing }) => {
  const mode = useReviewStore((s) => s.viewMode[side]);
  const toggleViewMode = useReviewStore((s) => s.toggleViewMode);

  if (!hasThreeDMesh(drawing)) return null;

  const targetMode = mode === "2d" ? "3d" : "2d";
  const label = targetMode.toUpperCase();

  return (
    <button
      type="button"
      onClick={() => toggleViewMode(side)}
      className="absolute top-2 right-2 z-20 flex items-center justify-center min-w-[36px] h-7 px-2.5 rounded border border-border-color bg-bg-card/90 backdrop-blur-sm text-[11px] font-bold tracking-wider text-text-primary hover:text-accent-primary hover:border-accent-primary/40 shadow-sm transition-all cursor-pointer select-none"
      title={`Switch to ${label} view (F1)`}
      aria-label={label}
    >
      {label}
    </button>
  );
};
