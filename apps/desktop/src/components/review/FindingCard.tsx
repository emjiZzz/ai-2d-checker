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
    .cmp-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; min-width: 0; }
    .cmp-grid > * { min-width: 0; overflow-wrap: anywhere; }
    .cmp-grid-diff { padding: 6px 8px; }
    .cmp-grid-diff > .cmp-title { grid-column: 1 / -1; }
    .cmp-grid-diff > .cmp-h-ref, .cmp-grid-diff > .cmp-h-rev { font-size: 0.62rem; }
    .cmp-grid-diff > .cmp-v-ref, .cmp-grid-diff > .cmp-v-rev { font-size: 0.78rem; }

    @container (max-width: 260px) {
      .cmp-grid { gap: 6px; }
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
  theme: string;
}

export const ComparisonValues: React.FC<ComparisonValuesProps> = ({
  title,
  original,
  revision,
  struck = false,
  matched = false,
  theme,
}) => {
  const isLight = theme === "hc-light";
  const cleanedOrig = cleanCadText(original) || "-";
  const cleanedRev = cleanCadText(revision) || "-";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "6px", width: "100%" }}>
      {title && (
        <div
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

      {/* Side-by-side comparison strip (integrated, no heavy double-box) */}
      <div
        className="cmp-grid"
        style={{
          background: isLight ? "rgba(241, 245, 249, 0.75)" : "var(--sidebar-item-hover)",
          borderRadius: "5px",
          padding: "7px 9px",
          border: "1px solid var(--border-color)",
        }}
      >
        <div style={{ display: "flex", flexDirection: "column", gap: "2px", minWidth: 0 }}>
          <span
            style={{
              fontSize: "0.6rem",
              fontWeight: 700,
              color: "var(--text-secondary)",
              letterSpacing: "0.06em",
              textTransform: "uppercase",
            }}
          >
            Original
          </span>
          <span
            style={{
              fontSize: "0.78rem",
              fontFamily: "'JetBrains Mono', monospace",
              color: struck ? (isLight ? "#991b1b" : "#f87171") : "var(--text-secondary)",
              textDecoration: struck ? "line-through" : "none",
              wordBreak: "break-word",
              lineHeight: 1.35,
            }}
          >
            {cleanedOrig}
          </span>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: "2px", minWidth: 0 }}>
          <span
            style={{
              fontSize: "0.6rem",
              fontWeight: 700,
              color: matched ? (isLight ? "#047857" : "#10b981") : "var(--accent-cyan)",
              letterSpacing: "0.06em",
              textTransform: "uppercase",
            }}
          >
            Revision
          </span>
          <span
            style={{
              fontSize: "0.78rem",
              fontFamily: "'JetBrains Mono', monospace",
              fontWeight: 600,
              color: matched ? (isLight ? "#047857" : "#10b981") : "var(--text-primary)",
              wordBreak: "break-word",
              lineHeight: 1.35,
            }}
          >
            {cleanedRev}
          </span>
        </div>
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
          gap: "4px",
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
        <span
          style={{
            width: "5px",
            height: "5px",
            borderRadius: "50%",
            background: statusColor,
            flexShrink: 0,
          }}
        />
        {statusLabel}
      </span>
    </div>

    {children}
  </div>
);
