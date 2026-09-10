import React from "react";
import { hasThreeDMesh } from "../../config/drawingFormats";
import { useReviewStore } from "../../stores/reviewStore";
import type { DrawingItem } from "../../stores/workspace/types";

interface ViewModeToggleProps {
  side: "old" | "new";
  drawing: DrawingItem | null;
}

/**
 * 2D / 3D switch for one pane.
 *
 * An .icd carries a drawing and a model, and iCAD SX switches between them in one workspace,
 * so this does too rather than making the engineer upload the same file into a second one.
 *
 * Per pane, not global. This view exists to hold two drawings side by side; flipping both at
 * once would take that away, which is why an earlier build of this control was removed --
 * see `06 - .../Gotcha - 3D DXF Ingestion Was Built and Removed.md`.
 *
 * Absent, not disabled, when the drawing has no model. In this shop every reference drawing is
 * 2D and only the revision is an .icd carrying both, so a control that renders greyed out on
 * every reference pane is noise on the majority of panes.
 *
 * `entity_counts.mesh` is the condition rather than the extension: it says a glTF was actually
 * written for this drawing, where `.icd` only says one might have been. An .icd holding just a
 * sheet gets no toggle, which is correct -- there is nothing to switch to.
 */
export const ViewModeToggle: React.FC<ViewModeToggleProps> = ({ side, drawing }) => {
  const mode = useReviewStore((s) => s.viewMode[side]);
  const setViewMode = useReviewStore((s) => s.setViewMode);

  if (!hasThreeDMesh(drawing)) return null;

  return (
    <div
      className="absolute top-2 right-2 z-20 flex rounded-sm overflow-hidden border border-border-color bg-bg-card/90 backdrop-blur-sm"
      title="Switch between the drawing and its 3D model (F1)"
    >
      {(["2d", "3d"] as const).map((m) => {
        const active = mode === m;
        return (
          <button
            key={m}
            type="button"
            aria-pressed={active}
            onClick={() => setViewMode(side, m)}
            className={[
              "px-2.5 py-1 text-[11px] font-semibold tracking-wide transition-colors",
              active ? "bg-accent-primary text-black" : "text-text-muted hover:text-text-primary",
            ].join(" ")}
          >
            {m.toUpperCase()}
          </button>
        );
      })}
    </div>
  );
};
