import React from "react";
import { Eye, EyeOff, Layers } from "lucide-react";
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

/** `1698997.98` -> `1.70e6`, so a column of volumes stays readable at a glance. */
const formatVolume = (mm3: number | null): string => {
  if (mm3 === null || !Number.isFinite(mm3)) return "—";
  if (mm3 >= 1e6) return `${(mm3 / 1e6).toFixed(2)}e6`;
  if (mm3 >= 1e3) return `${(mm3 / 1e3).toFixed(1)}e3`;
  return mm3.toFixed(0);
};

/**
 * The assembly's parts, and which of them are drawn.
 *
 * The names come from iCAD itself -- through the STEP's PRODUCT entries and out of gmsh as
 * named volumes -- so this list is the same tree the engineer sees in iCAD SX.
 *
 * Names REPEAT. Two `φ9×204` rows are two instances of one part, not a duplicate, so rows are
 * keyed and toggled by glTF node index. Matching on the name would hide both.
 *
 * Absent for a single-solid model: a list of one thing you can only hide is not a feature.
 */
export const PartsPanel: React.FC<PartsPanelProps> = ({ drawingId, parts }) => {
  const hidden = useReviewStore((s) => s.hiddenParts[drawingId]);
  const togglePart = useReviewStore((s) => s.togglePart);
  const setPartsHidden = useReviewStore((s) => s.setPartsHidden);

  if (!parts || parts.length < 2) return null;

  const hiddenSet = new Set(hidden ?? []);
  const allShown = hiddenSet.size === 0;

  return (
    <div className="absolute top-30 left-2 z-20 w-56 max-h-[65%] flex flex-col rounded-sm border border-border-color bg-bg-card/95 backdrop-blur-sm text-text-primary shadow-lg">
      <div className="flex items-center justify-between px-2.5 py-1.5 border-b border-border-color">
        <div className="flex items-center gap-1.5 text-[11px] font-semibold tracking-wide">
          <Layers size={12} />
          PARTS
          <span className="text-text-muted font-normal">({parts.length})</span>
        </div>
        <button
          type="button"
          className="text-[10px] text-text-muted hover:text-text-primary"
          onClick={() =>
            setPartsHidden(drawingId, allShown ? parts.map((p) => p.node) : [])
          }
        >
          {allShown ? "Hide all" : "Show all"}
        </button>
      </div>

      <ul className="overflow-y-auto py-1">
        {parts.map((part) => {
          const isHidden = hiddenSet.has(part.node);
          return (
            <li key={part.node}>
              <button
                type="button"
                onClick={() => togglePart(drawingId, part.node)}
                aria-pressed={!isHidden}
                title={`${part.name} — ${part.triangles.toLocaleString()} triangles, ${part.surfaces} surfaces`}
                className={[
                  "w-full flex items-center gap-2 px-2.5 py-1 text-left text-[11px] transition-colors",
                  isHidden ? "text-text-muted/50" : "text-text-primary hover:bg-bg-dark/50",
                ].join(" ")}
              >
                {isHidden ? <EyeOff size={11} /> : <Eye size={11} />}
                <span className="flex-1 truncate font-mono">{part.name}</span>
                <span className="text-text-muted text-[10px] tabular-nums">
                  {formatVolume(part.volume_mm3)}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
};
