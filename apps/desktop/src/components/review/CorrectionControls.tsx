import React, { useState } from "react";
import { Check, AlertTriangle, Tag, Pencil, X, Brain } from "lucide-react";
import {
  submitAuditFeedbackPayload,
  type AuditFeedbackPayload,
  type HumanCorrectedStatus,
} from "../../services/auditsApi";

/**
 * Per-finding human correction controls for the checklist diff-row card.
 *
 * Extends the pre-existing Dismiss/Undo flow with the richer corrections the learned model
 * trains on: flip a verdict (CHANGED↔MATCHED), confirm a real change, reclassify a finding's
 * category, or correct a mis-read value. Every action sends the matching human_corrected_status
 * plus a fixed-shape finding_snapshot (features the backend trainer needs), built from the
 * matched canvas marking when available so it carries a stable entity handle and real coords.
 */

interface DiffRow {
  field?: string;
  original?: string;
  kmti?: string;
  status?: string;
}

interface CorrectionControlsProps {
  rowId: string;
  categoryKey: string;
  statusText: string;
  row: DiffRow;
  matchingViolation: any | null;
  sessionId: string;
  drawingId: string;
  clientName?: string | null;
  onCorrected?: (status: HumanCorrectedStatus) => void;
}

const CATEGORY_OPTIONS: [string, string][] = [
  ["drawing_views", "Drawing Views"],
  ["notes_section", "Notes"],
  ["bill_of_materials", "BOM"],
  ["title_block", "Title Block"],
  ["isometric_view", "Isometric View"],
  ["other_engineering_references", "Other References"],
];

export const CorrectionControls: React.FC<CorrectionControlsProps> = ({
  rowId,
  categoryKey,
  statusText,
  row,
  matchingViolation,
  sessionId,
  drawingId,
  clientName,
  onCorrected,
}) => {
  const [mode, setMode] = useState<null | "menu" | "reclassify" | "value">(null);
  const [busy, setBusy] = useState(false);
  const [corrected, setCorrected] = useState<string | null>(null);
  const [valueInput, setValueInput] = useState("");

  const isMatched = statusText.toUpperCase() === "MATCHED";

  const buildPayload = (
    human_corrected_status: HumanCorrectedStatus,
    extra?: { corrected_category?: string; corrected_value?: string; human_comment?: string }
  ): AuditFeedbackPayload => ({
    session_id: sessionId || "session_default",
    drawing_id: drawingId || "drawing_default",
    client_name: clientName ?? null,
    entity_text: row.field || row.kmti || row.original || matchingViolation?.description || "",
    entity_handle: matchingViolation?.entity_handle ?? null,
    category: categoryKey,
    original_status: statusText,
    human_corrected_status,
    human_comment: extra?.human_comment ?? null,
    coordinates: matchingViolation?.coordinates ?? null,
    corrected_category: extra?.corrected_category ?? null,
    corrected_value: extra?.corrected_value ?? null,
    // Same contract as ChecklistPanel.tsx — send the raw texts, status, category, feature and
    // coordinates; leave the three derived features null. The backend recomputes them from
    // those inputs (feature_extractor.build_feature_row) using the runtime differ's own
    // normalization, and the INFERENCE path never supplies them either, so null is what keeps
    // training and inference on one definition. Computing them here would be train/serve skew:
    // there is no SequenceMatcher or SpatialDiffer._normalize_text in TypeScript.
    // Pinned by tests/test_stage_0a_measurement_unblocking.py.
    finding_snapshot: {
      ref_text: matchingViolation?.original_value ?? row.original ?? null,
      rev_text: matchingViolation?.description ?? row.kmti ?? null,
      det_status: matchingViolation?.status ?? statusText,
      category: matchingViolation?.category ?? categoryKey,
      feature: matchingViolation?.feature ?? null,
      ref_coord: matchingViolation?.ref_coordinates ?? null,
      rev_coord: matchingViolation?.coordinates ?? null,
      text_similarity: null,
      match_distance: null,
      is_numericish: null,
    },
  });

  const submit = async (
    human_corrected_status: HumanCorrectedStatus,
    label: string,
    extra?: { corrected_category?: string; corrected_value?: string; human_comment?: string }
  ) => {
    setBusy(true);
    try {
      await submitAuditFeedbackPayload(buildPayload(human_corrected_status, extra));
      setCorrected(label);
      onCorrected?.(human_corrected_status);
    } catch (err) {
      console.warn("[CorrectionControls] Feedback submit error:", err);
    } finally {
      setBusy(false);
      setMode(null);
    }
  };

  if (corrected) {
    return (
      <span
        data-testid={`correction-done-${rowId}`}
        style={{ display: "inline-flex", alignItems: "center", gap: "4px", fontSize: "0.65rem", fontWeight: 700, color: "#10b981" }}
      >
        <Brain size={12} /> Taught: {corrected}
      </span>
    );
  }

  const btnStyle: React.CSSProperties = {
    background: "transparent",
    border: "none",
    color: "var(--text-muted)",
    cursor: "pointer",
    fontSize: "0.7rem",
    display: "inline-flex",
    alignItems: "center",
    gap: "4px",
    padding: "2px 4px",
    opacity: busy ? 0.5 : 1,
  };

  const menuItemStyle: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: "6px",
    padding: "5px 8px",
    borderRadius: "6px",
    cursor: "pointer",
    fontSize: "0.72rem",
    color: "var(--text-primary)",
    background: "transparent",
    border: "none",
    width: "100%",
    textAlign: "left",
  };

  if (mode === null) {
    return (
      <button
        data-testid={`correction-open-${rowId}`}
        onClick={(e) => {
          e.stopPropagation();
          setMode("menu");
        }}
        title="Correct this finding & teach the model"
        style={btnStyle}
        disabled={busy}
      >
        <Pencil size={12} />
        <span>Correct</span>
      </button>
    );
  }

  return (
    <div
      onClick={(e) => e.stopPropagation()}
      style={{
        position: "relative",
        display: "flex",
        flexDirection: "column",
        gap: "3px",
        background: "var(--bg-sidebar)",
        border: "1px solid var(--border-color)",
        borderRadius: "8px",
        padding: "6px",
        minWidth: "190px",
        boxShadow: "0 6px 20px rgba(0,0,0,0.18)",
        zIndex: 5,
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "0 4px 2px" }}>
        <span style={{ fontSize: "0.6rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.04em", color: "var(--text-muted)" }}>
          Teach the model
        </span>
        <button onClick={() => setMode(null)} style={{ background: "transparent", border: "none", cursor: "pointer", color: "var(--text-muted)" }} aria-label="Close correction menu">
          <X size={12} />
        </button>
      </div>

      {mode === "menu" && (
        <>
          {!isMatched && (
            <button
              data-testid={`correction-matched-${rowId}`}
              style={menuItemStyle}
              onClick={() => submit("verdict_matched", "Actually matched")}
            >
              <Check size={13} color="#10b981" /> Actually MATCHED
            </button>
          )}
          <button
            data-testid={`correction-realchange-${rowId}`}
            style={menuItemStyle}
            onClick={() => submit(isMatched ? "verdict_changed" : "confirmed_change", "Real change")}
          >
            <AlertTriangle size={13} color="#f97316" /> {isMatched ? "Actually a change" : "Confirm real change"}
          </button>
          <button style={menuItemStyle} onClick={() => setMode("reclassify")}>
            <Tag size={13} color="#3b82f6" /> Reclassify category
          </button>
          <button style={menuItemStyle} onClick={() => { setValueInput(row.kmti || ""); setMode("value"); }}>
            <Pencil size={13} color="#a855f7" /> Fix value / note
          </button>
        </>
      )}

      {mode === "reclassify" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "4px", padding: "2px 4px" }}>
          <span style={{ fontSize: "0.65rem", color: "var(--text-muted)" }}>Move this finding to:</span>
          <select
            data-testid={`correction-category-select-${rowId}`}
            defaultValue=""
            onChange={(e) => {
              const val = e.target.value;
              if (val) submit("category_override", `→ ${val}`, { corrected_category: val });
            }}
            style={{
              background: "var(--bg-card)",
              border: "1px solid var(--border-color)",
              borderRadius: "6px",
              padding: "5px",
              fontSize: "0.72rem",
              color: "var(--text-primary)",
            }}
          >
            <option value="" disabled>Choose category…</option>
            {CATEGORY_OPTIONS.filter(([k]) => k !== categoryKey).map(([k, label]) => (
              <option key={k} value={k}>{label}</option>
            ))}
          </select>
        </div>
      )}

      {mode === "value" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "4px", padding: "2px 4px" }}>
          <span style={{ fontSize: "0.65rem", color: "var(--text-muted)" }}>Corrected value:</span>
          <input
            data-testid={`correction-value-input-${rowId}`}
            value={valueInput}
            onChange={(e) => setValueInput(e.target.value)}
            style={{
              background: "var(--bg-card)",
              border: "1px solid var(--border-color)",
              borderRadius: "6px",
              padding: "5px",
              fontSize: "0.72rem",
              color: "var(--text-primary)",
              fontFamily: "'JetBrains Mono', monospace",
            }}
            placeholder="e.g. ø25"
          />
          <button
            data-testid={`correction-value-save-${rowId}`}
            disabled={busy || !valueInput.trim()}
            onClick={() => submit("value_correction", "Value fixed", { corrected_value: valueInput.trim() })}
            style={{
              background: "var(--accent-cyan)",
              color: "#04121a",
              border: "none",
              borderRadius: "6px",
              padding: "5px",
              fontSize: "0.7rem",
              fontWeight: 700,
              cursor: valueInput.trim() ? "pointer" : "default",
              opacity: valueInput.trim() ? 1 : 0.5,
            }}
          >
            Save correction
          </button>
        </div>
      )}
    </div>
  );
};
