import React, { useState } from "react";
import { Check, AlertTriangle, Tag, Pencil, X, Brain, Unlink } from "lucide-react";
import {
  submitAuditFeedbackPayload,
  type AuditFeedbackPayload,
  type HumanCorrectedStatus,
} from "../../services/auditsApi";

/**
 * Per-finding human correction controls for the checklist diff-row card.
 *
 * Every action sends a `human_corrected_status` plus a fixed-shape `finding_snapshot` (the
 * features the backend trainer needs), built from the matched canvas marking when available so
 * it carries a stable entity handle and real coordinates.
 *
 * ## The wording is the checker's, not the model's
 *
 * The menu used to read "Actually a change" / "Confirm real change" — the same question, worded
 * two ways depending on what the engine had concluded (`isMatched ? … : …`). That made the
 * reviewer decode the engine's verdict before they could describe what they saw.
 *
 * Each button now states an observation about the *drawings*. The engine-facing verb is chosen
 * underneath: "Real change" sends `verdict_changed` on a MATCHED row and `confirmed_change`
 * otherwise, and both mean label 1 to the trainer. Seven verbs still exist on the wire; the
 * reviewer sees four questions.
 *
 * ## "Badly paired" is a new kind of statement
 *
 * The other options all assume the engine compared the right two entities and only got its
 * conclusion wrong. A finding like "NONE → 260" is usually neither a real change nor a false
 * alarm — it is one half of a pair the matcher failed to make. That is a statement about the
 * *matcher*, which nothing here could express before, and which is training data for the
 * Stage 3 learned matcher. It is captured, never mapped to a verdict — see
 * `trainer.MATCHER_FEEDBACK` for why either mapping would teach the model something false.
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
  const [mode, setMode] = useState<null | "menu" | "reclassify" | "value" | "paired">(null);
  const [busy, setBusy] = useState(false);
  const [corrected, setCorrected] = useState<string | null>(null);
  const [valueInput, setValueInput] = useState("");
  const [noteInput, setNoteInput] = useState("");

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
          {/* Same question in both directions — "is this a real change?" — so it reads the
              same way regardless of what the engine concluded. Only the wire verb differs. */}
          <button
            data-testid={`correction-realchange-${rowId}`}
            style={menuItemStyle}
            onClick={() => submit(isMatched ? "verdict_changed" : "confirmed_change", "Real change")}
          >
            <AlertTriangle size={13} color="#f97316" /> This is a real change
          </button>
          {!isMatched && (
            <button
              data-testid={`correction-matched-${rowId}`}
              style={menuItemStyle}
              onClick={() => submit("verdict_matched", "Not a change")}
            >
              <Check size={13} color="#10b981" /> Not a change — these match
            </button>
          )}
          <button data-testid={`correction-paired-open-${rowId}`} style={menuItemStyle} onClick={() => setMode("paired")}>
            <Unlink size={13} color="#eab308" /> Wrongly paired
          </button>
          <button style={menuItemStyle} onClick={() => setMode("reclassify")}>
            <Tag size={13} color="#3b82f6" /> Wrong section
          </button>
          <button style={menuItemStyle} onClick={() => { setValueInput(row.kmti || ""); setMode("value"); }}>
            <Pencil size={13} color="#a855f7" /> Wrong value
          </button>
        </>
      )}

      {mode === "paired" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "4px", padding: "2px 4px" }}>
          <span style={{ fontSize: "0.65rem", color: "var(--text-muted)" }}>What did the engine get wrong?</span>
          <button
            data-testid={`correction-paired-missing-${rowId}`}
            style={menuItemStyle}
            onClick={() => submit("mispaired_missing_counterpart", "Has a match", { human_comment: noteInput.trim() || undefined })}
          >
            <Unlink size={13} color="#eab308" /> It does have a match on the other drawing
          </button>
          <button
            data-testid={`correction-paired-wrong-${rowId}`}
            style={menuItemStyle}
            onClick={() => submit("mispaired_wrong_match", "Wrong pair", { human_comment: noteInput.trim() || undefined })}
          >
            <X size={13} color="#ef4444" /> These two are not the same thing
          </button>
          <input
            data-testid={`correction-paired-note-${rowId}`}
            value={noteInput}
            onChange={(e) => setNoteInput(e.target.value)}
            placeholder="Optional: which one should it pair with?"
            style={{
              background: "var(--bg-card)",
              border: "1px solid var(--border-color)",
              borderRadius: "6px",
              padding: "5px",
              fontSize: "0.7rem",
              color: "var(--text-primary)",
            }}
          />
        </div>
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
