import React from "react";
import { ChevronDown, ChevronRight, Eye, EyeOff } from "lucide-react";

/**
 * The collapsible category header both review panels are built from.
 *
 * Designed as a clean accordion divider (no heavy double-box wrapping)
 * to eliminate nested box clutter in narrow flexlayout sidebars.
 */
export interface ChecklistSectionProps {
  /** Category name, rendered uppercase. */
  label: string;
  /** Optional category icon. */
  icon?: React.ReactNode;
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
  icon,
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
      flexShrink: 0,
      display: "flex",
      flexDirection: "column",
      gap: "6px",
    }}
  >
    {/* Clean Category Header Bar */}
    <div
      onClick={onToggle}
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        padding: "8px 10px",
        cursor: "pointer",
        userSelect: "none",
        flexWrap: "nowrap",
        gap: "6px",
        minWidth: 0,
        background: expanded ? "var(--sidebar-item-hover)" : "var(--bg-card)",
        border: "1px solid var(--border-color)",
        borderRadius: "6px",
        transition: "all 0.15s ease",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "8px", minWidth: 0, flex: "1 1 auto", overflow: "hidden" }}>
        {icon && <span style={{ display: "inline-flex", alignItems: "center", flexShrink: 0 }}>{icon}</span>}
        {eye && (
          <div
            onClick={(e) => {
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
            {eye.hidden ? <EyeOff size={14} /> : <Eye size={14} />}
          </div>
        )}
        <span
          style={{
            fontSize: "0.78rem",
            fontWeight: 700,
            color: "var(--text-primary)",
            letterSpacing: "0.04em",
            textTransform: "uppercase",
            minWidth: 0,
          }}
        >
          {label}
        </span>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: "6px", flexShrink: 0 }}>
        {statusLabel && (
          <span
            style={{
              display: "flex",
              alignItems: "center",
              gap: "4px",
              fontSize: "0.65rem",
              fontWeight: 700,
              padding: "2px 7px",
              borderRadius: "999px",
              color: statusColor,
              background: `${statusColor}18`,
              letterSpacing: "0.03em",
              textTransform: "uppercase",
            }}
          >
            {statusIsMatched && (
              <svg
                width="10"
                height="10"
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
          <ChevronDown size={13} color="var(--text-muted)" />
        ) : (
          <ChevronRight size={13} color="var(--text-muted)" />
        )}
      </div>
    </div>

    {/* Direct Child Cards (no heavy enclosing box) */}
    {expanded && (
      <div
        style={{
          padding: "2px 0 4px",
          display: "flex",
          flexDirection: "column",
          gap: "6px",
          minWidth: 0,
          containerType: "inline-size",
        }}
      >
        {children}
      </div>
    )}
  </div>
);
