import React from "react";
import { cleanCadText } from "./renderEntities";

/**
 * The finding card and comparison grid, shared by the engine's checklist and the manual-check panel.
 *
 * Designed with a flat, single-card hierarchy (no nested boxes within boxes) so items
 * have maximum horizontal breathing room inside narrow flexlayout panels.
 */

export const ComparisonGridStyles: React.FC = () => (
  <style>{`
    .cmp-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 4px 8px; min-width: 0; }
    .cmp-grid > * { min-width: 0; overflow-wrap: anywhere; }
    .cmp-grid-diff { padding: 6px 8px; border-radius: 4px; }
    .cmp-grid-diff > .cmp-title { grid-column: 1 / -1; margin-bottom: 2px; }
    .cmp-grid-diff > .cmp-h-ref, .cmp-grid-diff > .cmp-h-rev { font-size: 0.62rem; }
    .cmp-grid-diff > .cmp-v-ref, .cmp-grid-diff > .cmp-v-rev { font-size: 0.78rem; }

    @container (max-width: 260px) {
      .cmp-grid { gap: 3px 6px; }
      .cmp-grid-diff { padding: 5px 6px; }
      .cmp-grid-diff > .cmp-h-ref, .cmp-grid-diff > .cmp-h-rev { font-size: 0.58rem; }
      .cmp-grid-diff > .cmp-v-ref, .cmp-grid-diff > .cmp-v-rev { font-size: 0.72rem; }
    }
  `}</style>
);

export interface ComparisonValuesProps {
  /** Heading inside the card — the field name for a checklist row, the value for a marking. */
  title?: string;
  original: string;
  revision: string;
  /** Strike the ORIGINAL: something that was there is gone or altered. */
  struck?: boolean;
  /** Colour the REVISION as agreement rather than as the current state. */
  matched?: boolean;
  /** Item is newly added: render full-width without comparison table */
  added?: boolean;
  theme: string;
}

export const ComparisonValues: React.FC<ComparisonValuesProps> = ({
  title,
  original,
  revision,
  struck = false,
  matched = false,
  added = false,
  theme,
}) => {
  const isLight = theme === "hc-light";

  // When an item is ADDED (or has no original data to compare), display as a clean, full-width block rather than a 2-column table
  if (added || (!original && revision)) {
    return (
      <div
        className="cmp-grid-diff"
        style={{
          background: isLight ? "rgba(241, 245, 249, 0.75)" : "var(--sidebar-item-hover)",
          border: "1px solid var(--border-color)",
          display: "flex",
          flexDirection: "column",
          gap: "4px",
        }}
      >
        {title && (
          <div
            className="cmp-title"
            style={{
              fontSize: "0.82rem",
              fontWeight: 700,
              color: "var(--text-primary)",
              letterSpacing: "0.01em",
              wordBreak: "break-word",
              lineHeight: 1.3,
            }}
          >
            {cleanCadText(title)}
          </div>
        )}
        <div
          style={{
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: "0.78rem",
            fontWeight: 600,
            color: "var(--text-primary)",
            wordBreak: "break-word",
            lineHeight: 1.4,
            whiteSpace: "pre-wrap",
          }}
        >
          {cleanCadText(revision) || "-"}
        </div>
      </div>
    );
  }

  return (
    <div
      className="cmp-grid cmp-grid-diff"
      style={{
        background: isLight ? "rgba(241, 245, 249, 0.75)" : "var(--sidebar-item-hover)",
        border: "1px solid var(--border-color)",
      }}
    >
      {title && (
        <div
          className="cmp-title"
          style={{
            fontSize: "0.82rem",
            fontWeight: 700,
            color: "var(--text-primary)",
            letterSpacing: "0.01em",
            wordBreak: "break-word",
            lineHeight: 1.3,
          }}
        >
          {cleanCadText(title)}
        </div>
      )}

      <div
        className="cmp-h-ref"
        style={{
          fontWeight: 700,
          color: "var(--text-secondary)",
          letterSpacing: "0.06em",
          textTransform: "uppercase",
        }}
      >
        Original
      </div>
      <div
        className="cmp-h-rev"
        style={{
          fontWeight: 700,
          color: matched ? (isLight ? "#047857" : "#10b981") : "var(--accent-cyan)",
          letterSpacing: "0.06em",
          textTransform: "uppercase",
        }}
      >
        Revision
      </div>

      <div
        className="cmp-v-ref"
        style={{
          fontFamily: "'JetBrains Mono', monospace",
          color: struck ? (isLight ? "#991b1b" : "#f87171") : "var(--text-secondary)",
          textDecoration: struck ? "line-through" : "none",
          wordBreak: "break-word",
          lineHeight: 1.35,
        }}
      >
        {cleanCadText(original) || "-"}
      </div>
      <div
        className="cmp-v-rev"
        style={{
          fontFamily: "'JetBrains Mono', monospace",
          fontWeight: 600,
          color: matched ? (isLight ? "#047857" : "#10b981") : "var(--text-primary)",
          wordBreak: "break-word",
          lineHeight: 1.35,
        }}
      >
        {cleanCadText(revision) || "-"}
      </div>
    </div>
  );
};

export interface FindingCardProps {
  /** Left of the badge row: whatever this panel lets you do to a row. */
  actions?: React.ReactNode;
  statusLabel: string;
  statusColor: string;
  statusBg?: string;
  selected?: boolean;
  /** Hidden or dismissed — still readable, visibly inactive. */
  dimmed?: boolean;
  onClick?: () => void;
  children: React.ReactNode;
}

export const FindingCard: React.FC<FindingCardProps> = ({
  actions,
  statusLabel,
  statusColor,
  statusBg,
  selected = false,
  dimmed = false,
  onClick,
  children,
}) => (
  <div
    onClick={onClick}
    style={{
      background: selected ? "rgba(37, 99, 235, 0.08)" : "var(--bg-card)",
      border: selected ? "1.5px solid var(--accent-cyan)" : "1px solid var(--border-color)",
      borderRadius: "6px",
      padding: "10px 12px",
      display: "flex",
      flexDirection: "column",
      gap: "8px",
      cursor: onClick ? "pointer" : "default",
      opacity: dimmed ? 0.4 : 1,
      boxShadow: selected ? "0 4px 14px rgba(37,99,235,0.12)" : "0 1px 3px rgba(0,0,0,0.04)",
      transition: "all 0.15s ease",
      flexShrink: 0,
      minWidth: 0,
      containerType: "inline-size",
    }}
  >
    {/* Header with actions and status badge */}
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        flexWrap: "wrap",
        gap: "6px",
        minWidth: 0,
      }}
    >
      <div
        style={{
          display: "flex",
          gap: "8px",
          alignItems: "center",
          flexWrap: "wrap",
          minWidth: 0,
        }}
      >
        {actions}
      </div>
      <span
        style={{
          display: "inline-flex",
          alignItems: "center",
          fontSize: "0.62rem",
          fontWeight: 700,
          padding: "2px 7px",
          borderRadius: "999px",
          color: statusColor,
          background: statusBg ?? `${statusColor}18`,
          textTransform: "uppercase",
          letterSpacing: "0.04em",
          flexShrink: 0,
        }}
      >
        {statusLabel}
      </span>
    </div>

    {children}
  </div>
);
