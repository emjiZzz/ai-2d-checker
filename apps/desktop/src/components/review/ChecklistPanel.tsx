import React, { useState } from "react";
import { ChevronDown, ChevronRight, Eye, EyeOff, XCircle, Brain, RotateCcw } from "lucide-react";
import { useWorkspaceStore } from "../../stores/workspaceStore";
import { useRoomStore } from "../../stores/roomStore";
import { submitAuditFeedbackPayload } from "../../services/auditsApi";
import { getTaxonomyWithOther, OTHER_FEATURE_KEY, DEFERRED_FEATURE_KEYS } from "../../utils/comparisonTaxonomy";
import { CorrectionControls } from "./CorrectionControls";
import { ReviewControls } from "./ReviewControls";
import { SummaryPanel } from "./SummaryPanel";
import { ChecklistSection } from "./ChecklistSection";
import { ComparisonGridStyles, ComparisonValues } from "./FindingCard";
import { markerTypeOf, markerUi } from "./markerStyles";
import { isPersistedViolationId, reviewableViolationId } from "../../utils/violationIdentity";
import { useThemeStore } from "../../stores/themeStore";

interface ChecklistPanelProps {
  aiChecklistResults: Record<string, any>;
}

const parseTabularContent = (content: string) => {
  if (!content) return [];
  const lines = content.split("\n").filter((l: string) => l.trim());
  const headerLine = lines.find((l: string) => l.includes("|"));
  const isSeparatorRow = (l: string) =>
    l.split("|").map(p => p.trim()).filter(p => p !== "").every(p => /^:?-{1,}:?$/.test(p));
  const dataLines = lines.filter((l: string) => l.includes("|") && !isSeparatorRow(l) && l !== headerLine);

  return dataLines.map((line: string) => {
    const parts = line.split("|").map((p: string) => p.trim());
    let cleanedParts = [...parts];
    if (cleanedParts[0] === "") cleanedParts.shift();
    if (cleanedParts[cleanedParts.length - 1] === "") cleanedParts.pop();

    const field = cleanedParts[0] || "";
    const original = cleanedParts[1] || "";
    const kmti = cleanedParts[2] || "";
    const rawStatus = cleanedParts[3] || "";

    const normalizeStatus = (s: string): string => {
      const u = s?.toUpperCase().trim() || "";
      if (["MISMATCHED", "MISMATCH", "DIFFER", "DIFFERENT"].includes(u)) return "CHANGED";
      return s?.trim() || "";
    };
    const status = normalizeStatus(rawStatus);
    const isMatch = status.toUpperCase().includes("MATCHED") && !status.toUpperCase().includes("MIS");

    return { field, original, kmti, status, isMatch };
  });
};

export const ChecklistPanel: React.FC<ChecklistPanelProps> = ({ aiChecklistResults }) => {
  const [expandedChecklistPanels, setExpandedChecklistPanels] = useState<Record<string, boolean>>({
    drawing_views: true,
    notes_section: true,
    bill_of_materials: true,
    title_block: true,
    isometric_view: true,
    other_engineering_references: true
  });

  const [expandedFeaturePanels, setExpandedFeaturePanels] = useState<Record<string, boolean>>({});
  const toggleFeaturePanel = (panelKey: string, defaultState: boolean) => {
    setExpandedFeaturePanels((prev) => ({ ...prev, [panelKey]: !(panelKey in prev ? prev[panelKey] : defaultState) }));
  };

  const activeRoom = useRoomStore((s) => s.activeRoom);
  const newDrawing = useWorkspaceStore((s) => s.newDrawing);
  const theme = useThemeStore((s) => s.theme);
  const [dismissedRowIds, setDismissedRowIds] = useState<Record<string, boolean>>({});

  const violations = useWorkspaceStore((s) => s.violations);
  const hiddenViolationIds = useWorkspaceStore((s) => s.hiddenViolationIds);
  const selectedViolation = useWorkspaceStore((s) => s.selectedViolation);
  const selectViolation = useWorkspaceStore((s) => s.selectViolation);
  const toggleViolationVisibility = useWorkspaceStore((s) => s.toggleViolationVisibility);
  const setViolationsVisibility = useWorkspaceStore((s) => s.setViolationsVisibility);
  const applyViolationReview = useWorkspaceStore((s) => s.applyViolationReview);
  const activeSessionId = useWorkspaceStore((s) => s.activeSessionId);

  const toggleChecklistPanel = (key: string) => {
    setExpandedChecklistPanels((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  // Renders one finding's card body — unchanged from the pre-Phase-6 flat-list layout
  // (docs/checklist-taxonomy-grouping-implementation-plan.md, Context: only the
  // grouping wrapper around this is new). Extracted to a function so both the
  // feature-grouped list below and (if ever needed) any other caller can reuse the
  // exact same JSX instead of duplicating it.
  const renderDiffRowCard = (row: any, matchingViolation: any, rowId: string, categoryKey: string = "drawing_views") => {
    if (!row) return null;
    const isLight = theme === 'hc-light';
    const statusUp = (row.status || "").toUpperCase();

    // Status first, colour second. The two used to be decided together in one ternary chain per
    // branch, which is how the same finding ended up a different orange in its card and in its
    // summary chip — and why a MATCHED pill never matched its own canvas marker.
    let statusText = row.status || "MATCHED";
    if (statusUp.includes("CHANGE") || statusUp.includes("MIS")) statusText = "CHANGED";
    else if (statusUp.includes("ADD")) statusText = "ADDED";
    else if (statusUp.includes("REMOV") || statusUp.includes("MISS")) statusText = "REMOVED";

    // A matched marker overrides the parsed table: the engine's own verdict beats the LLM's
    // rendering of it. Resolved by the shared reader now that `ai_red` means the same thing on
    // both sides — this panel had it right and the canvas had it wrong.
    if (matchingViolation) {
      statusText = markerTypeOf(matchingViolation) ?? statusText;
    }

    const { color: cellBadgeColor, background: cellBadgeBg } = markerUi(statusText, isLight);

    // Feature snapshot attached to every correction so the backend model can rebuild this
    // finding's training features. text_similarity/match_distance/is_numericish are recomputed
    // server-side from the texts/coords with the runtime differ's own normalization, so null
    // here is fine — we only need the raw texts, status, category, feature and coordinates.
    const findingSnapshot = {
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
    };

    // The id to review with, or null when this row has no `AuditViolation` behind it. A MATCHED
    // row never does — the backend persists only non-MATCHED findings — and neither does a
    // marker whose join to the persisted document failed. Both cases mean "offer no verdict",
    // which is better than offering one that PATCHes a document that does not exist.
    const reviewableId =
      statusText === "MATCHED" ? null : reviewableViolationId(matchingViolation);

    const isSelected = !!(selectedViolation && matchingViolation && selectedViolation.id === matchingViolation.id &&
      ((selectedViolation as any)._rowId === rowId || !(selectedViolation as any)._rowId));
    const isHidden = matchingViolation ? !!hiddenViolationIds[matchingViolation.id] : false;

    return (
      <div
        key={rowId}
        onClick={() => {
          if (matchingViolation) {
            selectViolation({ ...matchingViolation, _rowId: rowId } as any);
          }
        }}
        style={{
          background: isSelected ? "rgba(37, 99, 235, 0.08)" : "var(--bg-card)",
          border: isSelected ? "1.5px solid var(--accent-cyan)" : "1px solid var(--border-color)",
          borderRadius: "6px",
          padding: "10px 12px",
          display: "flex",
          flexDirection: "column",
          gap: "8px",
          cursor: matchingViolation ? "pointer" : "default",
          opacity: isHidden || dismissedRowIds[rowId] ? 0.4 : 1,
          boxShadow: isSelected ? "0 4px 14px rgba(37,99,235,0.12)" : "0 1px 3px rgba(0,0,0,0.04)",
          transition: "all 0.15s ease",
          // The card is the query container for `.cmp-grid` below. This panel is a flexlayout
          // tabset whose width the user drags, so a viewport media query would be measuring the
          // wrong box entirely — at the 220px floor the card only has ~138px of content.
          minWidth: 0,
          containerType: "inline-size"
        }}
      >
        {/* Badge Row. Both this row and the cluster inside it must wrap: at the panel's minimum
            width the eye + Dismiss + Correct + status pill do not fit on one line, and the panel
            root is overflow-x-hidden, so anything that overflows is silently clipped rather than
            scrollable. */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "6px", minWidth: 0 }}>
          <div style={{ display: "flex", gap: "10px", rowGap: "6px", alignItems: "center", flexWrap: "wrap", minWidth: 0 }}>
            <div
              onClick={(e) => {
                if (matchingViolation) {
                  e.stopPropagation();
                  toggleViolationVisibility(matchingViolation.id);
                }
              }}
              style={{
                cursor: matchingViolation ? "pointer" : "default",
                color: isHidden ? "var(--text-muted)" : "var(--accent-cyan)",
                display: "flex",
                alignItems: "center"
              }}
            >
              {matchingViolation && statusText !== "MATCHED" && isPersistedViolationId(matchingViolation.id) && (
                isHidden ? <EyeOff size={14} /> : <Eye size={14} />
              )}
            </div>

            {!dismissedRowIds[rowId] ? (
              <button
                onClick={async (e) => {
                  e.stopPropagation();
                  setDismissedRowIds((prev) => ({ ...prev, [rowId]: true }));
                  if (matchingViolation) {
                    toggleViolationVisibility(matchingViolation.id);
                  }
                  try {
                    await submitAuditFeedbackPayload({
                      session_id: activeRoom?.id || "session_default",
                      drawing_id: newDrawing?.id || "drawing_default",
                      client_name: activeRoom?.client_name,
                      entity_text: row.field || row.kmti || row.original,
                      entity_handle: matchingViolation?.entity_handle,
                      category: categoryKey,
                      original_status: statusText,
                      human_corrected_status: "dismissed",
                      finding_snapshot: findingSnapshot
                    });
                  } catch (err) {
                    console.warn("[ChecklistPanel] Feedback submit error:", err);
                  }
                }}
                title="Dismiss false alarm & train AI engine"
                style={{
                  background: "transparent",
                  border: "none",
                  color: "var(--text-muted)",
                  cursor: "pointer",
                  fontSize: "0.7rem",
                  display: "flex",
                  alignItems: "center",
                  gap: "4px"
                }}
              >
                <XCircle size={13} />
                <span>Dismiss</span>
              </button>
            ) : (
              <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                <span style={{ fontSize: "0.65rem", fontWeight: 700, color: "#10b981", display: "flex", alignItems: "center", gap: "3px" }}>
                  <Brain size={12} /> Learned
                </span>
                <button
                  onClick={async (e) => {
                    e.stopPropagation();
                    setDismissedRowIds((prev) => ({ ...prev, [rowId]: false }));
                    if (matchingViolation) {
                      toggleViolationVisibility(matchingViolation.id);
                    }
                    try {
                      await submitAuditFeedbackPayload({
                        session_id: activeRoom?.id || "session_default",
                        drawing_id: newDrawing?.id || "drawing_default",
                        client_name: activeRoom?.client_name,
                        entity_text: row.field || row.kmti || row.original,
                        entity_handle: matchingViolation?.entity_handle,
                        category: categoryKey,
                        original_status: statusText,
                        human_corrected_status: "confirmed_valid",
                        finding_snapshot: findingSnapshot
                      });
                    } catch (err) {
                      console.warn("[ChecklistPanel] Undo feedback submit error:", err);
                    }
                  }}
                  title="Undo dismissal & mark item as valid"
                  style={{
                    background: "transparent",
                    border: "none",
                    color: "var(--accent-cyan)",
                    cursor: "pointer",
                    fontSize: "0.65rem",
                    fontWeight: 600,
                    display: "flex",
                    alignItems: "center",
                    gap: "2px"
                  }}
                >
                  <RotateCcw size={11} />
                  <span>Undo</span>
                </button>
              </div>
            )}

            <CorrectionControls
              rowId={rowId}
              categoryKey={categoryKey}
              statusText={statusText}
              row={row}
              matchingViolation={matchingViolation}
              sessionId={activeRoom?.id || "session_default"}
              drawingId={newDrawing?.id || "drawing_default"}
              clientName={activeRoom?.client_name}
              onCorrected={(status) => {
                if (matchingViolation && (status === "verdict_matched" || status === "dismissed")) {
                  toggleViolationVisibility(matchingViolation.id);
                }
              }}
            />
          </div>
          <span style={{
            display: "inline-flex", alignItems: "center",
            fontSize: "0.62rem", fontWeight: 700, padding: "2px 6px", borderRadius: "2px",
            color: cellBadgeColor, background: cellBadgeBg,
            textTransform: "uppercase", letterSpacing: "0.04em"
          }}>
            {statusText}
          </span>
        </div>

        {/* Comparison Grid. Layout and type scale deliberately live in the .cmp-grid stylesheet
            rather than here: inline styles outrank stylesheet rules, so the container query could
            never override a value declared inline. Only status-dependent styling stays inline. */}
        <ComparisonValues
          title={row.field}
          original={row.original}
          revision={row.kmti}
          struck={
            statusText.toUpperCase().includes("CHANGE") ||
            statusText.toUpperCase().includes("REMOVE") ||
            statusText.toUpperCase().includes("MIS")
          }
          matched={statusText.toUpperCase() === "MATCHED"}
          theme={theme}
        />

        {/* Supervisor verdict, on findings only. This is the write that fills the `lessons`
            collection.

            It sits here — a direct child of the card, below the values — rather than in the
            badge row above. Two reasons: the reviewer should see the evidence before the
            verdict, and as a card child it gets a full-width line from the card's own column
            flex instead of fighting Dismiss/Correct for horizontal space.

            Gated on `reviewableId`, which is null unless this row maps to a real
            `AuditViolation`. It previously tested `matchingViolation` alone, which contradicted
            the comment sitting over it and shipped a live 500: a MATCHED row carrying a
            client-side marker offered Approve, and PATCHing
            `/audits/violations/phys_chk_restored_1_1786329084013/review` blew up server-side. */}
        {reviewableId && (
          <ReviewControls
            violationId={reviewableId}
            resolution={matchingViolation.resolution_type}
            remarks={matchingViolation.checker_remarks}
            onReviewed={({ resolution, remarks }) =>
              applyViolationReview(matchingViolation.id, resolution, remarks)
            }
          />
        )}
      </div>
    );
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "12px", flexGrow: 1, paddingBottom: "24px", minWidth: 0 }}>
      {/* Rendered once here, not inside renderDiffRowCard — that runs per finding and would
          emit one duplicate <style> element per row. */}
      <ComparisonGridStyles />
      <div style={{
        background: "linear-gradient(135deg, var(--bg-sidebar) 0%, var(--bg-card) 100%)",
        border: "1px solid var(--border-color)",
        borderRadius: 0,
        padding: "14px",
        boxShadow: "0 2px 10px rgba(24,24,27,0.06)",
        backdropFilter: "blur(15px)",
        display: "flex",
        flexDirection: "column",
        gap: "10px"
      }}>
        <div style={{ fontSize: "0.8rem", fontWeight: 600, color: "var(--accent-cyan)", letterSpacing: "0.05em", textTransform: "uppercase" }}>
          INSPECTION SUMMARY REPORT
        </div>
        {/* auto-fit rather than a hard 1fr 1fr: at the panel's minimum width two columns leave
            ~92px per chip, not enough for "Drawing Views" plus its status. */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))", gap: "8px" }}>
          {[
            { key: "drawing_views", label: "Drawing Views" },
            { key: "notes_section", label: "Notes" },
            { key: "bill_of_materials", label: "BOM" },
            { key: "title_block", label: "Title Block" },
            { key: "isometric_view", label: "Isometric View" }
          ].map(({ key, label }) => {
            const res = aiChecklistResults[key];
            if (!res) return null;
            // `MISSING` is the LLM's word for REMOVED; the table has no entry under that name.
            const { color } = markerUi(res.status === "MISSING" ? "REMOVED" : res.status, theme === 'hc-light');
            return (
              <div key={key} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", background: "var(--sidebar-item-hover)", padding: "5px 8px", borderRadius: "5px", border: "1px solid var(--border-color)" }}>
                <span style={{ fontSize: "0.72rem", color: "var(--text-muted)", fontWeight: 400 }}>{label}</span>
                <span style={{ display: "flex", alignItems: "center", gap: "4px", fontSize: "0.68rem", fontWeight: 600, color, letterSpacing: "0.02em" }}>
                  {res.status === "MATCHED" && (
                    <svg width="10" height="10" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                      <polyline points="1.5 6.5 4.5 9.5 10.5 2.5" />
                    </svg>
                  )}
                  {res.status}
                </span>
              </div>
            );
          })}
        </div>
        {(() => {
          const keys = ["drawing_views", "notes_section", "bill_of_materials", "title_block", "isometric_view"];
          let totalItems = 0;
          let matchedItems = 0;

          keys.forEach(key => {
            const res = aiChecklistResults[key];
            if (!res) return;

            const isTabular = (res.reference_content && res.reference_content.includes("|")) ||
              (res.revision_content && res.revision_content.includes("|"));

            if (isTabular) {
              const tableRows = parseTabularContent(res.reference_content || res.revision_content);
              const uniqueRowsMap = new Map();
              tableRows.forEach(row => {
                if (!uniqueRowsMap.has(row.field)) {
                  uniqueRowsMap.set(row.field, row);
                }
              });
              const diffRows = Array.from(uniqueRowsMap.values());
              diffRows.forEach(row => {
                totalItems++;
                if (row.isMatch || (row.status || "").toUpperCase() === "MATCHED") {
                  matchedItems++;
                }
              });
            } else {
              totalItems++;
              if (res.status === "MATCHED") {
                matchedItems++;
              }
            }
          });

          const pct = totalItems > 0 ? Math.round((matchedItems / totalItems) * 100) : 0;
          return (
            <div style={{ marginTop: "6px", display: "flex", flexDirection: "column", gap: "8px" }}>
              <div>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.72rem", color: "var(--text-primary)", marginBottom: "4px", fontWeight: 500 }}>
                  <span>Completion Parity</span>
                  <span style={{ color: "var(--accent-cyan)", fontWeight: 600 }}>{pct}% MATCHED</span>
                </div>
                <div style={{ width: "100%", height: "4px", background: "var(--border-color)", borderRadius: "2px", overflow: "hidden" }}>
                  <div style={{ height: "100%", background: "var(--accent-cyan)", width: `${pct}%`, transition: "width 0.5s ease" }}></div>
                </div>
              </div>
            </div>
          );
        })()}
      </div>

      {[
        { key: "drawing_views", label: "Drawing Views" },
        { key: "notes_section", label: "Notes Section" },
        { key: "bill_of_materials", label: "Bill of Materials" },
        { key: "title_block", label: "Title Block" },
        { key: "isometric_view", label: "Isometric View" },
        { key: "other_engineering_references", label: "Other Engineering References" }
      ].map(({ key, label }) => {
        const result = aiChecklistResults[key];
        if (!result) return null;

        const isExpanded = expandedChecklistPanels[key];

        const badgeColor = markerUi(
          result.status === "MISSING" ? "REMOVED" : result.status,
          theme === 'hc-light',
        ).color;

        const pKey = key.toLowerCase().replace(/_/g, "");

        // 1. Parse tabular content to get diffRows
        let diffRows: any[] = [];
        const isTabular = (result.reference_content && result.reference_content.includes("|")) ||
          (result.revision_content && result.revision_content.includes("|"));

        if (isTabular) {
          const tableRows = parseTabularContent(result.reference_content || result.revision_content);
          const uniqueRowsMap = new Map();
          tableRows.forEach(row => {
            if (!uniqueRowsMap.has(row.field)) {
              uniqueRowsMap.set(row.field, row);
            }
          });
          diffRows = Array.from(uniqueRowsMap.values());
        }

        // 2. Pre-calculate matching violations so the category header knows exactly which
        //    markers belong to it — and so clicking a card selects *that* card's marker.
        //
        //    Two rules here exist because their absence produced "click a card, the canvas
        //    jumps to a different finding":
        //
        //    a) **A violation is claimed by at most one row.** This used to be a plain
        //       `violations.find(...)` per row with no claim tracking, so several rows could
        //       resolve to the same marker — first match wins, every time — and the row that
        //       actually owned it got nothing or someone else's.
        //    b) **Exact matches are claimed before substring ones.** The predicate accepts
        //       `descLower.includes(target) || target.includes(descLower)`, so a row reading
        //       `230` matches a marker reading `1230` or `230.5`. Run greedily in row order,
        //       a loose match on an early row can steal the marker an exact match later
        //       needed. Two passes, exact first, removes that ordering dependency.
        const rowToViolationMap = new Map<number, any>();
        const categoryViolationIdsSet = new Set<string>();
        const claimedViolationIds = new Set<string>();

        const categoryAllows = (v: any, row: any) => {
          const vCat = v.category ? v.category.toLowerCase().replace(/_/g, "") : "";
          // No category from the generator — fall back to text alone, as before.
          if (!vCat) return true;
          if (vCat === pKey || vCat.includes(pKey) || pKey.includes(vCat)) return true;
          if (row.field) {
            const rField = row.field.toLowerCase().replace(/_/g, "");
            if (vCat === rField || vCat.includes(rField) || rField.includes(vCat)) return true;
          }
          return false;
        };

        const textMatches = (v: any, row: any, exactOnly: boolean) => {
          const descLower = (v.description ? v.description.trim() : "").toLowerCase();
          const kmtiText = (row.kmti || "").trim().toLowerCase();
          const origText = (row.original || "").trim().toLowerCase();

          if (descLower) {
            const isMatch = (target: string) => {
              if (!target) return false;
              // Short or punctuation-only values are ambiguous by nature; they were already
              // exact-only, and stay so in both passes.
              if (target.length <= 2 || /^[-_./\\]+$/.test(target)) return descLower === target;
              if (descLower === target) return true;
              if (exactOnly) return false;
              return descLower.includes(target) || target.includes(descLower);
            };
            if (isMatch(kmtiText) || isMatch(origText)) return true;
          }
          // Field-name fallback is inherently loose — substring pass only.
          if (!exactOnly && row.field && descLower.includes(row.field.toLowerCase())) return true;
          return false;
        };

        for (const exactOnly of [true, false]) {
          diffRows.forEach((row, idx) => {
            if (rowToViolationMap.has(idx)) return;
            const hit = violations.find(
              v => !claimedViolationIds.has(v.id) && textMatches(v, row, exactOnly) && categoryAllows(v, row)
            );
            if (hit) {
              rowToViolationMap.set(idx, hit);
              claimedViolationIds.add(hit.id);
              categoryViolationIdsSet.add(hit.id);
            }
          });
        }

        // 3. Also include any violations that explicitly claim this parent category, even if they didn't match a row
        violations.forEach(v => {
          const vCat = v.category ? v.category.toLowerCase().replace(/_/g, "") : "";
          if (vCat && (vCat === pKey || vCat.includes(pKey) || pKey.includes(vCat))) {
            categoryViolationIdsSet.add(v.id);
          }
        });

        const categoryViolationIds = Array.from(categoryViolationIdsSet);
        const allHidden = categoryViolationIds.length > 0 && categoryViolationIds.every(id => hiddenViolationIds[id]);

        return (
          <ChecklistSection
            key={key}
            label={label}
            statusLabel={result.status}
            statusColor={badgeColor}
            statusIsMatched={result.status === "MATCHED"}
            expanded={isExpanded}
            onToggle={() => toggleChecklistPanel(key)}
            eye={{
              hidden: allHidden,
              enabled: categoryViolationIds.length > 0,
              onToggle: () => setViolationsVisibility(categoryViolationIds, !allHidden),
            }}
          >
            <>


                {/* ── MATCHED: All-Clear confirmation block ── */}
                {result.status === "MATCHED" && (
                  <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
                    {/* Header badge */}
                    <div style={{
                      display: "flex",
                      alignItems: "flex-start",
                      gap: "12px",
                      padding: "14px 16px",
                      background: "rgba(16, 185, 129, 0.07)",
                      border: "1px solid rgba(16, 185, 129, 0.25)",
                      borderRadius: "10px",
                    }}>
                      <div style={{
                        flexShrink: 0,
                        width: "28px",
                        height: "28px",
                        borderRadius: "50%",
                        background: "rgba(16, 185, 129, 0.15)",
                        border: "1.5px solid rgba(16, 185, 129, 0.5)",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                      }}>
                        <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke={markerUi('MATCHED', theme === 'hc-light').color} strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                          <polyline points="2 7.5 5.5 11 12 3" />
                        </svg>
                      </div>
                      <div style={{ flex: 1 }}>
                        <div style={{ fontSize: "0.8rem", fontWeight: 600, color: markerUi('MATCHED', theme === 'hc-light').color, marginBottom: "4px", letterSpacing: "0.04em" }}>
                          ✓ VERIFIED — NO DISCREPANCIES
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                {(result.reference_content || result.revision_content) && (() => {
                  if (isTabular) {
                    // Sub-item taxonomy grouping (docs/checklist-taxonomy-grouping-
                    // implementation-plan.md, Phase 6). Grouping bucket comes from each
                    // row's matched canvas_marking's `feature` (decision 2) — the
                    // ORIGINAL/REVISION card body itself is 100% unchanged
                    // (renderDiffRowCard, extracted verbatim from the pre-Phase-6 flat
                    // list). Every taxonomy sub-item is always rendered, even with zero
                    // findings, per the scope decision confirmed with the user.
                    const featureGroups = getTaxonomyWithOther(key).map(item => {
                      const rows = diffRows
                        .map((row, idx) => ({ row, idx, violation: rowToViolationMap.get(idx) }))
                        .filter(({ violation }) => (violation?.feature || OTHER_FEATURE_KEY) === item.key);
                      return { ...item, rows };
                    });

                    return (
                      <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                        <div style={{ fontSize: "0.8rem", fontWeight: 650, color: "var(--accent-cyan)", marginBottom: "4px", letterSpacing: "0.05em" }}>COMPARATIVE CONTENTS</div>
                        <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                          {featureGroups.map(group => {
                            const panelKey = `${key}::${group.key}`;
                            const isDeferred = DEFERRED_FEATURE_KEYS.has(group.key);
                            const hasRows = group.rows.length > 0;
                            const defaultOpen = hasRows;
                            const isOpen = panelKey in expandedFeaturePanels ? expandedFeaturePanels[panelKey] : defaultOpen;

                            // Worst-status color across the bucket's rows, same severity
                            // ranking as elsewhere in this file (REMOVED/CONFLICT > CHANGED > ADDED > MATCHED).
                            // Severity ranking stays here — it is this panel's rule, not the
                            // table's — but the colour it resolves to comes from the table.
                            let worst = "MATCHED";
                            let severity = 0;
                            for (const { row, violation } of group.rows) {
                              // One reader for "what kind of finding is this", shared with the
                              // canvas and the hit test. This was a fourth private pen chain and
                              // it disagreed with them about `ai_red` until 2026-08-18.
                              const s = (violation && markerTypeOf(violation)) || (row.status || "").toUpperCase();
                              if ((s.includes("REMOV") || s === "CONFLICT") && severity < 3) { severity = 3; worst = s === "CONFLICT" ? "CONFLICT" : "REMOVED"; }
                              else if (s.includes("CHANGE") && severity < 2) { severity = 2; worst = "CHANGED"; }
                              else if (s.includes("ADD") && severity < 1) { severity = 1; worst = "ADDED"; }
                            }
                            const subBadgeColor = markerUi(worst, theme === 'hc-light').color;

                            return (
                              <div key={panelKey} style={{ border: "1px solid var(--border-color)", borderRadius: "6px", overflow: "hidden" }}>
                                <div
                                  onClick={() => hasRows && toggleFeaturePanel(panelKey, defaultOpen)}
                                  style={{
                                    display: "flex", justifyContent: "space-between", alignItems: "center",
                                    padding: "8px 10px", cursor: hasRows ? "pointer" : "default", userSelect: "none",
                                    gap: "8px", minWidth: 0,
                                    background: "var(--bg-card)"
                                  }}
                                >
                                  <span style={{ fontSize: "0.7rem", fontWeight: 600, color: "var(--text-secondary)", letterSpacing: "0.02em", minWidth: 0 }}>
                                    {group.label}
                                  </span>
                                  <div style={{ display: "flex", alignItems: "center", gap: "8px", flexShrink: 0 }}>
                                    {hasRows && (
                                      <span style={{
                                        fontSize: "0.62rem", fontWeight: 700, color: subBadgeColor,
                                        background: `${subBadgeColor}16`,
                                        borderRadius: "999px", padding: "2px 8px"
                                      }}>
                                        {group.rows.length}
                                      </span>
                                    )}
                                    {hasRows && (isOpen ? <ChevronDown size={12} color="var(--text-muted)" /> : <ChevronRight size={12} color="var(--text-muted)" />)}
                                  </div>
                                </div>
                                {/* Rows FIRST, deferred second.
                                    This was the other way round, and its own definition in
                                    `comparisonTaxonomy.ts` warned about it: "Membership here
                                    HIDES rows — a deferred key that ever carries findings drops
                                    them silently." It did. `line_name` is deferred and sits in
                                    the title block, which HAS a classifier
                                    (`classify_title_ul_feature`), so a finding it labelled would
                                    have vanished from this panel with nothing to show it ever
                                    existed.
                                    "Not yet supported" is a statement about an EMPTY bucket —
                                    "nothing was checked here, do not read this as clean". A
                                    bucket with findings in it was evidently checked by
                                    something, and the findings are the product of record. */}
                                {hasRows ? (
                                  isOpen ? (
                                    <div style={{ padding: "10px", display: "flex", flexDirection: "column", gap: "8px", background: "var(--bg-dark)" }}>
                                      {isDeferred && (
                                        <div style={{ fontSize: "0.68rem", color: "var(--text-muted)", fontStyle: "italic" }}>
                                          This sub-item has no automatic producer yet — these arrived from somewhere else.
                                        </div>
                                      )}
                                      {group.rows.map(({ row, idx, violation }) => renderDiffRowCard(row, violation, `${key}-${idx}`, key))}
                                    </div>
                                  ) : null
                                ) : isDeferred ? (
                                  <div style={{ padding: "10px 12px", fontSize: "0.7rem", color: "var(--text-muted)", fontStyle: "italic", background: "var(--bg-card)" }}>
                                    Not yet supported for automatic checking.
                                  </div>
                                ) : !hasRows ? (
                                  <div style={{ padding: "10px 12px", fontSize: "0.7rem", color: "var(--text-muted)", background: "var(--bg-card)" }}>
                                    No changes detected.
                                  </div>
                                ) : null}
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    );
                  } else {
                    return (
                      <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                        <div style={{ fontSize: "0.8rem", fontWeight: 650, color: "var(--accent-cyan)", marginBottom: "4px", letterSpacing: "0.05em" }}>COMPARATIVE CONTENTS</div>
                        <div className="cmp-grid">
                          <div style={{ background: "var(--bg-card)", border: "1px solid var(--border-color)", padding: "10px", borderRadius: "6px" }}>
                            <div style={{ fontSize: "0.65rem", fontWeight: 700, color: "var(--text-muted)", marginBottom: "6px" }}>Original Drawing</div>
                            <div style={{ fontSize: "0.78rem", color: "var(--text-muted)", whiteSpace: "pre-wrap", maxHeight: "150px", overflowY: "auto", fontFamily: "monospace" }}>
                              {result.reference_content || "-"}
                            </div>
                          </div>
                          <div style={{ background: "rgba(0,229,255,0.01)", border: "1px solid rgba(0,229,255,0.1)", padding: "10px", borderRadius: "6px" }}>
                            <div style={{ fontSize: "0.65rem", fontWeight: 700, color: "var(--accent-cyan)", marginBottom: "6px" }}>KMTI Drawing</div>
                            <div style={{ fontSize: "0.78rem", color: "var(--text-primary)", whiteSpace: "pre-wrap", maxHeight: "150px", overflowY: "auto", fontFamily: "monospace" }}>
                              {result.revision_content || "-"}
                            </div>
                          </div>
                        </div>
                      </div>
                    );
                  }
                })()}

                {result.difference_summary && (
                  <div>
                    <div style={{ fontSize: "0.8rem", fontWeight: 600, color: "var(--accent-cyan)", marginBottom: "6px", letterSpacing: "0.05em" }}>DETAILED SUMMARY REPORT</div>
                    <div style={{ fontSize: "0.85rem", color: "var(--text-primary)", lineHeight: "1.5", fontWeight: 300, background: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "6px", padding: "10px 12px" }}>{result.difference_summary}</div>
                  </div>
                )}

                {result.engineering_discrepancy_details && (
                  <div>
                    <div style={{ fontSize: "0.8rem", fontWeight: 600, color: "var(--accent-cyan)", marginBottom: "6px", letterSpacing: "0.05em" }}>PROFESSIONAL SUGGESTION</div>
                    <div style={{
                      fontSize: "0.85rem",
                      color: markerUi(result.status === "MATCHED" ? "MATCHED" : "MISMATCHED", theme === 'hc-light').color,
                      background: markerUi(result.status === "MATCHED" ? "MATCHED" : "MISMATCHED", theme === 'hc-light').background,
                      borderLeft: `4px solid ${badgeColor}`,
                      padding: "8px 12px",
                      borderRadius: "0 6px 6px 0",
                      lineHeight: "1.5"
                    }}>
                      {result.engineering_discrepancy_details}
                    </div>
                  </div>
                )}

                {categoryViolationIds.length > 0 && (
                  <div style={{ display: "flex", flexDirection: "column", gap: "6px", marginTop: "10px" }}>
                    <div style={{ fontSize: "0.75rem", fontWeight: 600, color: "var(--accent-cyan)", letterSpacing: "0.05em", textTransform: "uppercase" }}>
                      Visual Checklist Markers ({categoryViolationIds.length})
                    </div>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
                      {violations
                        .filter(v => categoryViolationIds.includes(v.id))
                        .map(v => {
                          const isSelected = selectedViolation?.id === v.id;
                          const isHidden = !!hiddenViolationIds[v.id];
                          let markerBg = "var(--sidebar-item-hover)";
                          let markerBorder = "var(--border-color)";
                          let markerText = "var(--text-primary)";

                          if (isSelected) {
                            markerBg = "rgba(0, 229, 255, 0.1)";
                            markerBorder = "var(--accent-cyan)";
                            markerText = "var(--accent-cyan)";
                          } else if (v.pen_type === "ai_red") {
                            markerBg = "rgba(239, 68, 68, 0.05)";
                            markerBorder = "rgba(239, 68, 68, 0.2)";
                          } else if (v.pen_type === "ai_orange") {
                            markerBg = "rgba(249, 115, 22, 0.05)";
                            markerBorder = "rgba(249, 115, 22, 0.2)";
                          }

                          return (
                            <div
                              key={v.id}
                              onClick={(e) => {
                                e.stopPropagation();
                                selectViolation(v);
                              }}
                              style={{
                                display: "flex",
                                alignItems: "center",
                                gap: "6px",
                                padding: "4px 8px",
                                borderRadius: "4px",
                                background: markerBg,
                                border: `1px solid ${markerBorder}`,
                                fontSize: "0.72rem",
                                color: markerText,
                                cursor: "pointer",
                                opacity: isHidden ? 0.4 : 1,
                                transition: "all 0.15s ease",
                                maxWidth: "100%",
                                overflow: "hidden",
                                textOverflow: "ellipsis",
                                whiteSpace: "nowrap"
                              }}
                              title={v.description}
                            >
                              <span style={{
                                width: "6px",
                                height: "6px",
                                borderRadius: "50%",
                                background: markerUi(markerTypeOf(v) ?? "MATCHED", theme === 'hc-light').color,
                                flexShrink: 0
                              }} />
                              <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>
                                {v.description}
                              </span>
                            </div>
                          );
                        })}
                    </div>
                  </div>
                )}
            </>
          </ChecklistSection>
        );
      })}

      {/* ADR-010: the summary renders BELOW the checklist. The findings are the product of
          record; a summary above them invites a reader to stop there. */}
      {activeSessionId && <SummaryPanel sessionId={activeSessionId} />}
    </div>
  );
};
