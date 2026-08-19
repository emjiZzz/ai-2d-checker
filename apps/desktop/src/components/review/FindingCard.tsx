import React from "react";
import { cleanCadText } from "./renderEntities";

/**
 * The finding card, shared by the engine's checklist and the manual-check panel.
 *
 * ## Why this is shared and the bodies are not
 *
 * Both panels answer "what was found, and what do the two sheets say". That question has one
 * right presentation — a card, a status chip, and the two values side by side under ORIGINAL and
 * REVISION — and it was implemented once for the engine and then approximated for manual
 * markings, which is why the two panels looked like two products.
 *
 * What stays separate is what each panel DOES with a row. The checklist's actions write to
 * `audit_feedback`, the learned model's corpus, because dismissing or correcting an engine
 * finding is a statement about the engine. A manual marking is ground truth and its only action
 * is retraction. So the actions are a slot, not a fixed part of the card.
 *
 * ## The two columns never stack
 *
 * Stacking would fit a narrow panel more comfortably and would destroy what the grid is for:
 * you cannot compare two values that are not beside each other. The container query buys back
 * horizontal room instead — tighter padding, gap and type — so a squeezed panel yields a smaller
 * pair rather than two slivers.
 */

/**
 * The grid's stylesheet. Render ONCE per panel, never per card.
 *
 * Layout and type scale live here rather than inline because inline styles outrank stylesheet
 * rules — a container query could never override a value declared on the element. Only
 * status-dependent styling stays inline.
 *
 * ⚠ The query container is the CARD (`container-type: inline-size` on `FindingCard`), not the
 * viewport. This panel is a flexlayout tabset whose width the user drags, so a viewport media
 * query would be measuring an unrelated box: at the 220px floor a card has ~138px of content.
 */
export const ComparisonGridStyles: React.FC = () => (
  <style>{`
    .cmp-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; min-width: 0; }
    .cmp-grid > * { min-width: 0; overflow-wrap: anywhere; }
    .cmp-grid-diff { text-align: center; padding: 12px; }
    .cmp-grid-diff > .cmp-title { grid-column: 1 / -1; }
    .cmp-grid-diff > .cmp-h-ref, .cmp-grid-diff > .cmp-h-rev { font-size: 0.62rem; }
    .cmp-grid-diff > .cmp-v-ref, .cmp-grid-diff > .cmp-v-rev { font-size: 0.8rem; }

    @container (max-width: 260px) {
      .cmp-grid { gap: 6px; }
      .cmp-grid-diff { padding: 8px; }
      .cmp-grid-diff > .cmp-h-ref, .cmp-grid-diff > .cmp-h-rev { font-size: 0.55rem; letter-spacing: 0.02em; }
      .cmp-grid-diff > .cmp-v-ref, .cmp-grid-diff > .cmp-v-rev { font-size: 0.72rem; }
    }
  `}</style>
);

export interface ComparisonValuesProps {
  /** Heading inside the box — the field name for a checklist row, the value for a marking. */
  title: string;
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
}) => (
  <div
    className="cmp-grid cmp-grid-diff"
    style={{
      background: theme === "hc-light" ? "#f1f5f9" : "var(--sidebar-item-hover)",
      border: "1px solid var(--border-color)",
      borderRadius: "2px",
    }}
  >
    <div
      className="cmp-title"
      style={{
        fontSize: "0.8rem",
        fontWeight: 700,
        color: "var(--text-primary)",
        borderBottom: "1px solid var(--border-color)",
        paddingBottom: "8px",
        marginBottom: "2px",
        textTransform: "uppercase",
        textAlign: "left",
        letterSpacing: "0.02em",
      }}
    >
      {cleanCadText(title)}
    </div>

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
        color: "var(--accent-cyan)",
        letterSpacing: "0.06em",
        textTransform: "uppercase",
      }}
    >
      Revision
    </div>

    {/* `-` rather than an empty cell: a blank reads as a rendering fault, where a dash reads as
        "this sheet has nothing here", which for an ADDED or a REMOVED is the finding itself. */}
    <div
      className="cmp-v-ref"
      style={{
        color: "var(--text-secondary)",
        fontFamily: "'JetBrains Mono', monospace",
        textDecoration: struck ? "line-through" : "none",
        wordBreak: "break-word",
      }}
    >
      {cleanCadText(original) || "-"}
    </div>
    <div
      className="cmp-v-rev"
      style={{
        color: matched ? (theme === "hc-light" ? "#047857" : "#10b981") : "var(--text-primary)",
        fontFamily: "'JetBrains Mono', monospace",
        fontWeight: 600,
        wordBreak: "break-word",
      }}
    >
      {cleanCadText(revision) || "-"}
    </div>
  </div>
);

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
      borderRadius: 0,
      padding: "14px",
      display: "flex",
      flexDirection: "column",
      gap: "10px",
      cursor: onClick ? "pointer" : "default",
      opacity: dimmed ? 0.4 : 1,
      boxShadow: selected ? "0 6px 20px rgba(37,99,235,0.15)" : "0 1px 4px rgba(0,0,0,0.05)",
      transition: "all 0.2s ease",
      // Same reason as `ChecklistSection`: these are flex items in a column, and a card that
      // shrinks crops its own comparison grid — the two values it exists to show.
      flexShrink: 0,
      // The card is the query container for `.cmp-grid` inside it. See `ComparisonGridStyles`.
      minWidth: 0,
      containerType: "inline-size",
    }}
  >
    {/* Both this row and the cluster inside it must wrap: at the panel's minimum width the
        actions and the status pill do not fit on one line, and the panel root is
        overflow-x:hidden, so anything that overflows is silently clipped rather than scrollable. */}
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        flexWrap: "wrap",
        gap: "8px",
        minWidth: 0,
      }}
    >
      <div
        style={{
          display: "flex",
          gap: "10px",
          rowGap: "6px",
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
          gap: "5px",
          fontSize: "0.62rem",
          fontWeight: 700,
          padding: "2px 6px",
          borderRadius: "2px",
          color: statusColor,
          background: statusBg ?? `${statusColor}1f`,
          textTransform: "uppercase",
          letterSpacing: "0.04em",
        }}
      >
        <span
          style={{
            width: "4px",
            height: "4px",
            borderRadius: "1px",
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
