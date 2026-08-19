import React from "react";
import { ChevronDown, ChevronRight, Eye, EyeOff } from "lucide-react";

/**
 * The collapsible category card both review panels are built from.
 *
 * ## Why it is shared rather than copied
 *
 * `ChecklistPanel` (engine findings) and `ManualMarkingList` (what an engineer recorded) answer
 * different questions and must NOT share their bodies — the checklist's rows carry
 * `CorrectionControls`, which writes to `audit_feedback`, the learned model's corpus. A manual
 * marking is ground truth, not a correction of an engine finding, and routing one through that
 * path would file it as the wrong kind of statement entirely.
 *
 * The *chrome* is a different matter. A card, an uppercase category label, a status pill, a
 * chevron and an eye toggle are presentation, and they were written twice — which is why the two
 * panels looked like two products. This is lifted verbatim from `ChecklistPanel` so the swap
 * there is inert; the manual list adopts it and stops being the odd one out.
 *
 * The eye toggle is optional because only one caller has something to hide: the checklist can
 * mute a category's markers on the canvas, and a manual marking has no such concept — it is
 * either recorded or retracted.
 */
export interface ChecklistSectionProps {
  /** Category name, rendered uppercase. */
  label: string;
  /** Pill text — a status, or a count. Omit for no pill. */
  statusLabel?: string;
  /** Pill colour; the background is the same colour at 8% opacity. */
  statusColor?: string;
  /** Show the check glyph inside the pill. */
  statusIsMatched?: boolean;
  expanded: boolean;
  onToggle: () => void;
  /** Canvas visibility for this category's markers. Omitted where nothing can be hidden. */
  eye?: { hidden: boolean; enabled: boolean; onToggle: () => void };
  children: React.ReactNode;
}

export const ChecklistSection: React.FC<ChecklistSectionProps> = ({
  label,
  statusLabel,
  statusColor = "var(--text-muted)",
  statusIsMatched = false,
  expanded,
  onToggle,
  eye,
  children,
}) => (
  <div
    style={{
      background: "var(--bg-card)",
      border: "1px solid var(--border-color)",
      // Square. The rounded card was the panel's only soft edge against a workspace of
      // rectangular sheets, title blocks and tables (owner's call, 2026-08-18).
      borderRadius: 0,
      overflow: "hidden",
      boxShadow: "0 2px 8px rgba(24,24,27,0.06)",
      // ⚠ Load-bearing in a scrolling column, not cosmetic. A flex item defaults to
      // `flex-shrink: 1`, so inside a height-constrained `flex-direction: column` scroller each
      // section is SQUEEZED to fit rather than overflowing — and `overflow: hidden` above turns
      // that squeeze into a clip, so a category with ten cards renders two and a half and the
      // rest are simply gone. The scrollbar looks right, the content is not there.
      flexShrink: 0,
    }}
  >
    <div
      onClick={onToggle}
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        padding: "12px 14px",
        cursor: "pointer",
        userSelect: "none",
        flexWrap: "wrap",
        gap: "8px",
        minWidth: 0,
        background: expanded ? "var(--sidebar-item-hover)" : "transparent",
        borderBottom: expanded ? "1px solid var(--border-color)" : "none",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "8px", minWidth: 0, flex: "1 1 auto" }}>
        {eye && (
          <div
            onClick={(e) => {
              // Without this the click also reaches the header and collapses the very section
              // the user was trying to mute.
              e.stopPropagation();
              if (eye.enabled) eye.onToggle();
            }}
            style={{
              cursor: eye.enabled ? "pointer" : "default",
              color: eye.enabled
                ? eye.hidden
                  ? "var(--text-muted)"
                  : "var(--accent-cyan)"
                : "var(--border-color)",
              display: "flex",
              alignItems: "center",
              flexShrink: 0,
            }}
          >
            {eye.hidden ? <EyeOff size={16} /> : <Eye size={16} />}
          </div>
        )}
        <span
          style={{
            fontSize: "0.92rem",
            fontWeight: 500,
            color: "var(--text-primary)",
            letterSpacing: "0.03em",
            textTransform: "uppercase",
            minWidth: 0,
          }}
        >
          {label}
        </span>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: "10px", flexShrink: 0 }}>
        {statusLabel && (
          <span
            style={{
              display: "flex",
              alignItems: "center",
              gap: "5px",
              fontSize: "0.72rem",
              fontWeight: 700,
              padding: "4px 11px",
              borderRadius: "999px",
              color: statusColor,
              background: `${statusColor}14`,
              letterSpacing: "0.04em",
              textTransform: "uppercase",
            }}
          >
            {statusIsMatched && (
              <svg
                width="11"
                height="11"
                viewBox="0 0 12 12"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <polyline points="1.5 6.5 4.5 9.5 10.5 2.5" />
              </svg>
            )}
            {statusLabel}
          </span>
        )}
        {expanded ? (
          <ChevronDown size={14} color="var(--text-muted)" />
        ) : (
          <ChevronRight size={14} color="var(--text-muted)" />
        )}
      </div>
    </div>

    {expanded && (
      <div
        style={{
          padding: "14px 16px",
          background: "var(--bg-dark)",
          display: "flex",
          flexDirection: "column",
          gap: "14px",
          minWidth: 0,
          containerType: "inline-size",
        }}
      >
        {children}
      </div>
    )}
  </div>
);
