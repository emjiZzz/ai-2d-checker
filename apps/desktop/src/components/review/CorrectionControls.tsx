import { useReviewStore } from '../../stores/reviewStore';
import React, { useState } from "react";
import { Check, AlertTriangle, Tag, Pencil, X, Brain, Unlink, RotateCcw } from "lucide-react";
import {
  submitAuditFeedbackPayload,
  retractAuditFeedback,
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
  const setPendingCounterpart = useReviewStore((s) => s.setPendingCounterpart);
  const pendingCounterpart = useReviewStore((s) => s.pendingCounterpart);
  // Only THIS card's armed correction, so twenty rows do not all claim to be waiting.
  const isWaiting = pendingCounterpart?.payload?.entity_text === (row.field || row.kmti || row.original || matchingViolation?.description || "");
  const [corrected, setCorrected] = useState<string | null>(null);
  // Kept so a mis-click can be taken back. Without it the menu was one-way: the correction
  // was already persisted and had already kicked a retrain, and the card rendered a terminal
  // "Taught: …" with no route back.
  const [feedbackId, setFeedbackId] = useState<string | null>(null);
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

  /**
   * Hand the correction to the canvas and wait for a click.
   *
   * The whole payload is stored, not rebuilt at completion: the finding's row, category and
   * snapshot belong to THIS card, and the engineer will have scrolled and panned before they
   * click. Rebuilding later would attach the correction to whatever card happened to be in
   * view.
   */
  const arm = (human_corrected_status: HumanCorrectedStatus, label: string) => {
    setPendingCounterpart({ payload: buildPayload(human_corrected_status), label });
    setMode(null);
  };

  const submit = async (
    human_corrected_status: HumanCorrectedStatus,
    label: string,
    extra?: { corrected_category?: string; corrected_value?: string; human_comment?: string }
  ) => {
    setBusy(true);
    try {
      const res = await submitAuditFeedbackPayload(buildPayload(human_corrected_status, extra));
      setFeedbackId(res?.id ?? null);
      setCorrected(label);
      onCorrected?.(human_corrected_status);
    } catch (err) {
      console.warn("[CorrectionControls] Feedback submit error:", err);
    } finally {
      setBusy(false);
      setMode(null);
    }
  };

  // A correction armed from this card and waiting for a click. Without this the app looks
  // unresponsive: the menu closes, nothing is recorded yet, and the only thing that will finish
  // it is a gesture the engineer has not been told to make.
  if (isWaiting) {
    return (
      <span
        data-testid={`correction-awaiting-${rowId}`}
        style={{
          display: "inline-flex", alignItems: "center", flexWrap: "wrap", gap: "6px",
          minWidth: 0, fontSize: "0.65rem", fontWeight: 700, color: "#eab308",
        }}
      >
        <Unlink size={12} /> Click the right entity on either drawing
        <button
          onClick={(e) => {
            e.stopPropagation();
            setPendingCounterpart(null);
          }}
          style={{
            background: "transparent", border: "none", color: "var(--text-muted)",
            cursor: "pointer", fontSize: "0.65rem", fontWeight: 600,
          }}
        >
          Cancel
        </button>
      </span>
    );
  }

  if (corrected) {
    return (
      <span
        data-testid={`correction-done-${rowId}`}
        style={{ display: "inline-flex", alignItems: "center", flexWrap: "wrap", gap: "6px", minWidth: 0, fontSize: "0.65rem", fontWeight: 700, color: "#10b981" }}
      >
        <Brain size={12} /> Taught: {corrected}
        {feedbackId && (
          <button
            data-testid={`correction-undo-${rowId}`}
            disabled={busy}
            onClick={async (e) => {
              e.stopPropagation();
              setBusy(true);
              try {
                await retractAuditFeedback(feedbackId);
                setFeedbackId(null);
                setCorrected(null);
                setMode(null);
              } catch (err) {
                console.warn("[CorrectionControls] Retract error:", err);
              } finally {
                setBusy(false);
              }
            }}
            title="Take this correction back — it stops training the model"
            style={{
              background: "transparent",
              border: "none",
              color: "var(--text-muted)",
              cursor: busy ? "default" : "pointer",
              fontSize: "0.65rem",
              fontWeight: 600,
              display: "inline-flex",
              alignItems: "center",
              gap: "3px",
              padding: 0,
              opacity: busy ? 0.5 : 1,
              textDecoration: "underline",
            }}
          >
            <RotateCcw size={11} /> Undo
          </button>
        )}
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
    // flex-start, not center: these labels are full sentences and wrap to two or three lines in
    // the narrow left panel, and a centred icon then floats mid-paragraph.
    alignItems: "flex-start",
    gap: "6px",
    padding: "5px 8px",
    borderRadius: "6px",
    cursor: "pointer",
    fontSize: "0.72rem",
    lineHeight: 1.3,
    color: "var(--text-primary)",
    background: "transparent",
    border: "none",
    width: "100%",
    minWidth: 0,
    textAlign: "left",
  };

  /** Keeps a leading lucide icon from being squashed when its label wraps. */
  const menuIconStyle: React.CSSProperties = { flexShrink: 0, marginTop: "1px" };

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
        // This menu is in flow (position: relative), not floating, so a hard minWidth reserved
        // real width in the parent row. 190px did not fit the left panel at its 220px floor,
        // where a finding card has ~138px of content -- the menu simply ran off the clipped
        // edge. flex-basis 100% takes a full line of the (now wrapping) control row instead.
        flex: "1 1 100%",
        width: "100%",
        maxWidth: "100%",
        minWidth: 0,
        boxSizing: "border-box",
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
            <AlertTriangle size={13} color="#f97316" style={menuIconStyle} /> This is a real change
          </button>
          {!isMatched && (
            <button
              data-testid={`correction-matched-${rowId}`}
              style={menuItemStyle}
              onClick={() => submit("verdict_matched", "Not a change")}
            >
              <Check size={13} color="#10b981" style={menuIconStyle} /> Not a change — these match
            </button>
          )}
          <button data-testid={`correction-paired-open-${rowId}`} style={menuItemStyle} onClick={() => setMode("paired")}>
            <Unlink size={13} color="#eab308" style={menuIconStyle} /> Wrongly paired
          </button>
          <button style={menuItemStyle} onClick={() => setMode("reclassify")}>
            <Tag size={13} color="#3b82f6" style={menuIconStyle} /> Wrong section
          </button>
          <button style={menuItemStyle} onClick={() => { setValueInput(row.kmti || ""); setMode("value"); }}>
            <Pencil size={13} color="#a855f7" style={menuIconStyle} /> Wrong value
          </button>
        </>
      )}

      {mode === "paired" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "4px", padding: "2px 4px" }}>
          <span style={{ fontSize: "0.65rem", color: "var(--text-muted)" }}>What did the engine get wrong?</span>
          {/*
            Both verbs ARM a pick rather than submitting on the spot.

            They used to submit immediately, with the correct counterpart offered as an optional
            free-text box below. It was skipped 103 times out of 106 — rationally, it was
            optional and it was typing — leaving a corpus of rejections with no corrections. A
            matcher cannot be trained on those: there is no target to learn toward.

            Pointing at the entity is one click and produces a resolvable address, so the next
            correction is worth something the previous 103 are not.
          */}
          <button
            data-testid={`correction-paired-missing-${rowId}`}
            style={menuItemStyle}
            onClick={() => arm("mispaired_missing_counterpart", "Has a match")}
          >
            <Unlink size={13} color="#eab308" style={menuIconStyle} /> It does have a match — point at it
          </button>
          <button
            data-testid={`correction-paired-wrong-${rowId}`}
            style={menuItemStyle}
            onClick={() => arm("mispaired_wrong_match", "Wrong pair")}
          >
            <X size={13} color="#ef4444" style={menuIconStyle} /> Not the same thing — point at the right one
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
              // An <input> carries an intrinsic width of ~20 characters, which overflows this
              // panel unless it is explicitly allowed to shrink.
              width: "100%",
              minWidth: 0,
              boxSizing: "border-box",
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
              width: "100%",
              minWidth: 0,
              boxSizing: "border-box",
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
              width: "100%",
              minWidth: 0,
              boxSizing: "border-box",
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
