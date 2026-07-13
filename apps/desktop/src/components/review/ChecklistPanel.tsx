import React, { useState } from "react";
import { ChevronDown, ChevronRight, Eye, EyeOff } from "lucide-react";
import { useWorkspaceStore } from "../../stores/workspaceStore";

interface ChecklistPanelProps {
  aiChecklistResults: Record<string, any>;
}

export const ChecklistPanel: React.FC<ChecklistPanelProps> = ({ aiChecklistResults }) => {
  const [expandedChecklistPanels, setExpandedChecklistPanels] = useState<Record<string, boolean>>({
    drawing_views: true,
    notes_section: true,
    bill_of_materials: true,
    title_block: true,
    isometric_view: true,
    other_engineering_references: true
  });

  const violations = useWorkspaceStore(s => s.violations);
  const hiddenViolationIds = useWorkspaceStore(s => s.hiddenViolationIds);
  const selectedViolation = useWorkspaceStore(s => s.selectedViolation);
  const selectViolation = useWorkspaceStore(s => s.selectViolation);
  const toggleViolationVisibility = useWorkspaceStore(s => s.toggleViolationVisibility);
  const setViolationsVisibility = useWorkspaceStore(s => s.setViolationsVisibility);

  const toggleChecklistPanel = (key: string) => {
    setExpandedChecklistPanels((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const parseTabularContent = (content: string) => {
    if (!content) return [];
    const lines = content.split("\n").filter((l: string) => l.trim());
    const headerLine = lines.find((l: string) => l.includes("|"));
    const dataLines = lines.filter((l: string) => l.includes("|") && !l.match(/^-+$/) && l !== headerLine);

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

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "12px", flexGrow: 1, paddingBottom: "24px" }}>
      <div style={{
        background: "linear-gradient(135deg, rgba(30,30,40,0.5) 0%, rgba(15,15,20,0.5) 100%)",
        border: "1px solid rgba(255,255,255,0.06)",
        borderRadius: "8px",
        padding: "14px",
        boxShadow: "0 4px 20px rgba(0,0,0,0.2)",
        backdropFilter: "blur(15px)",
        display: "flex",
        flexDirection: "column",
        gap: "10px"
      }}>
        <div style={{ fontSize: "0.8rem", fontWeight: 600, color: "var(--accent-cyan)", letterSpacing: "0.05em", textTransform: "uppercase" }}>
          INSPECTION SUMMARY REPORT
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px" }}>
          {[
            { key: "drawing_views", label: "Drawing Views" },
            { key: "notes_section", label: "Notes" },
            { key: "bill_of_materials", label: "BOM" },
            { key: "title_block", label: "Title Block" },
            { key: "isometric_view", label: "Isometric View" }
          ].map(({ key, label }) => {
            const res = aiChecklistResults[key];
            if (!res) return null;
            let color = "#10b981";
            if (res.status === "CHANGED") color = "#f59e0b";
            else if (res.status === "ADDED") color = "#3b82f6";
            else if (res.status === "REMOVED" || res.status === "MISSING") color = "#ef4444";
            return (
              <div key={key} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", background: "rgba(255,255,255,0.02)", padding: "5px 8px", borderRadius: "5px", border: "1px solid rgba(255,255,255,0.04)" }}>
                <span style={{ fontSize: "0.72rem", color: "#a1a1aa", fontWeight: 400 }}>{label}</span>
                <span style={{ fontSize: "0.68rem", fontWeight: 600, color, letterSpacing: "0.02em" }}>{res.status}</span>
              </div>
            );
          })}
        </div>
        {(() => {
          const keys = ["drawing_views", "notes_section", "bill_of_materials", "title_block", "isometric_view"];
          const total = keys.filter(k => aiChecklistResults[k]).length;
          const matched = keys.filter(k => aiChecklistResults[k]?.status === "MATCHED").length;
          const pct = total > 0 ? Math.round((matched / total) * 100) : 0;
          return (
            <div style={{ marginTop: "4px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.72rem", color: "#e4e4e7", marginBottom: "5px", fontWeight: 500 }}>
                <span>Completion Parity</span>
                <span style={{ color: "var(--accent-cyan)", fontWeight: 600 }}>{pct}% MATCHED</span>
              </div>
              <div style={{ width: "100%", height: "4px", background: "rgba(255,255,255,0.08)", borderRadius: "2px", overflow: "hidden" }}>
                <div style={{ height: "100%", background: "var(--accent-cyan)", width: `${pct}%`, transition: "width 0.5s ease" }}></div>
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

        let badgeColor = "#10b981";
        if (result.status === "ADDED") badgeColor = "#3b82f6";
        else if (result.status === "CHANGED") badgeColor = "#f59e0b";
        else if (result.status === "REMOVED" || result.status === "MISSING") badgeColor = "#ef4444";

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

        // 2. Pre-calculate matching violations so the category header knows exactly which markers belong to it
        const rowToViolationMap = new Map<number, any>();
        const categoryViolationIdsSet = new Set<string>();

        diffRows.forEach((row, idx) => {
          const matchingViolation = violations.find(v => {
            const desc = v.description ? v.description.trim() : "";
            const kmtiText = (row.kmti || "").trim().toLowerCase();
            const origText = (row.original || "").trim().toLowerCase();
            const descLower = desc.toLowerCase();
            
            let matchesText = false;
            if (descLower) {
              if (kmtiText && (descLower === kmtiText || descLower.includes(kmtiText) || kmtiText.includes(descLower))) {
                matchesText = true;
              } else if (origText && (descLower === origText || descLower.includes(origText) || origText.includes(descLower))) {
                matchesText = true;
              }
            }
            if (!matchesText && row.field && descLower.includes(row.field.toLowerCase())) {
              matchesText = true;
            }

            const vCat = v.category ? v.category.toLowerCase().replace(/_/g, "") : "";
            let matchesCategory = false;
            
            if (vCat) {
              matchesCategory = vCat === pKey || vCat.includes(pKey) || pKey.includes(vCat);
              if (!matchesCategory && row.field) {
                const rField = row.field.toLowerCase().replace(/_/g, "");
                if (vCat === rField || vCat.includes(rField) || rField.includes(vCat)) {
                  matchesCategory = true;
                }
              }
            } else {
              // If AI gave no category, rely purely on text match
              matchesCategory = true;
            }
            
            return matchesText && matchesCategory;
          });

          if (matchingViolation) {
            rowToViolationMap.set(idx, matchingViolation);
            categoryViolationIdsSet.add(matchingViolation.id);
          }
        });

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
          <div
            key={key}
            style={{
              background: "rgba(22,22,26,0.7)",
              border: "1px solid rgba(255,255,255,0.06)",
              borderRadius: "8px",
              overflow: "hidden",
              boxShadow: "0 4px 12px rgba(0,0,0,0.15)"
            }}
          >
            <div
              onClick={() => toggleChecklistPanel(key)}
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                padding: "12px 14px",
                cursor: "pointer",
                userSelect: "none",
                background: isExpanded ? "rgba(255,255,255,0.02)" : "transparent",
                borderBottom: isExpanded ? "1px solid rgba(255,255,255,0.05)" : "none"
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <div 
                  onClick={(e) => {
                    e.stopPropagation();
                    if (categoryViolationIds.length > 0) {
                      setViolationsVisibility(categoryViolationIds, !allHidden);
                    }
                  }}
                  style={{
                    cursor: categoryViolationIds.length > 0 ? "pointer" : "default",
                    color: categoryViolationIds.length > 0 ? (allHidden ? "#52525b" : "var(--accent-cyan)") : "rgba(255,255,255,0.1)",
                    display: "flex",
                    alignItems: "center"
                  }}
                >
                  {allHidden ? <EyeOff size={16} /> : <Eye size={16} />}
                </div>
                <span style={{ fontSize: "0.92rem", fontWeight: 500, color: "#ffffff", letterSpacing: "0.03em", textTransform: "uppercase" }}>
                  {label}
                </span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                <span style={{
                  fontSize: "0.72rem", fontWeight: 500, padding: "3px 8px", borderRadius: "5px",
                  color: badgeColor, border: `1px solid ${badgeColor}40`, background: `${badgeColor}12`,
                  letterSpacing: "0.04em"
                }}>
                  {result.status}
                </span>
                {isExpanded ? <ChevronDown size={14} color="#a1a1aa" /> : <ChevronRight size={14} color="#a1a1aa" />}
              </div>
            </div>

            {isExpanded && (
              <div style={{ padding: "14px 16px", background: "rgba(0,0,0,0.25)", display: "flex", flexDirection: "column", gap: "14px" }}>
                {result.difference_summary && (
                  <div>
                    <div style={{ fontSize: "0.8rem", fontWeight: 500, color: "var(--accent-cyan)", marginBottom: "6px", letterSpacing: "0.05em" }}>DIFFERENCE SUMMARY</div>
                    <div style={{ fontSize: "0.85rem", color: "#e4e4e7", lineHeight: "1.5", fontWeight: 100 }}>{result.difference_summary}</div>
                  </div>
                )}

                {(result.reference_content || result.revision_content) && (() => {
                  if (isTabular) {
                    return (
                      <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                        <div style={{ fontSize: "0.8rem", fontWeight: 650, color: "var(--accent-cyan)", marginBottom: "4px", letterSpacing: "0.05em" }}>COMPARATIVE CONTENTS</div>
                        {diffRows.length === 0 ? (
                          <div style={{
                            padding: "14px",
                            textAlign: "center",
                            color: "#10b981",
                            background: "rgba(16, 185, 129, 0.06)",
                            border: "1px dashed rgba(16, 185, 129, 0.25)",
                            borderRadius: "8px",
                            fontSize: "0.78rem",
                            fontWeight: 500
                          }}>
                            ✨ Perfect Match! All fields are identical.
                          </div>
                        ) : (
                          <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                            {diffRows.map((row, idx) => {
                              let cellBadgeColor = "#ef4444";
                              let cellBadgeBg = "rgba(239, 68, 68, 0.08)";
                              let statusText = row.status || "MISMATCHED";

                              const matchingViolation = rowToViolationMap.get(idx);

                              if (matchingViolation) {
                                const pt = matchingViolation.pen_type || "";
                                if (pt === "ai_orange") {
                                  cellBadgeColor = "#f97316"; statusText = "CHANGED"; cellBadgeBg = "rgba(249, 115, 22, 0.08)";
                                } else if (pt === "checker_blue") {
                                  cellBadgeColor = "#3b82f6"; statusText = "ADDED"; cellBadgeBg = "rgba(59, 130, 246, 0.08)";
                                } else if (pt === "ai_red") {
                                  cellBadgeColor = "#ef4444"; statusText = "REMOVED"; cellBadgeBg = "rgba(239, 68, 68, 0.08)";
                                } else if (pt === "resolved_green" || pt === "ai_green") {
                                  cellBadgeColor = "#10b981"; statusText = "MATCHED"; cellBadgeBg = "rgba(16, 185, 129, 0.08)";
                                }
                              } else {
                                if (statusText.toUpperCase().includes("CHANGE")) {
                                  cellBadgeColor = "#f97316"; cellBadgeBg = "rgba(249, 115, 22, 0.08)";
                                } else if (statusText.toUpperCase().includes("ADD")) {
                                  cellBadgeColor = "#3b82f6"; cellBadgeBg = "rgba(59, 130, 246, 0.08)";
                                } else if (statusText.toUpperCase().includes("MATCH")) {
                                  cellBadgeColor = "#10b981"; cellBadgeBg = "rgba(16, 185, 129, 0.08)";
                                }
                              }

                              const rowId = `${key}-${idx}`;
                              const isSelected = !!(selectedViolation && matchingViolation && selectedViolation.id === matchingViolation.id &&
                                ((selectedViolation as any)._rowId === rowId || !(selectedViolation as any)._rowId));
                                
                              const isHidden = matchingViolation ? !!hiddenViolationIds[matchingViolation.id] : false;

                              return (
                                <div
                                  key={idx}
                                  onClick={() => {
                                    if (matchingViolation) {
                                      selectViolation({ ...matchingViolation, _rowId: rowId } as any);
                                    }
                                  }}
                                  style={{
                                    background: isSelected ? "rgba(0, 229, 255, 0.06)" : "rgba(255,255,255,0.02)",
                                    border: isSelected ? "1px solid var(--accent-cyan)" : "1px solid rgba(255,255,255,0.06)",
                                    borderRadius: "8px",
                                    padding: "12px",
                                    display: "flex",
                                    flexDirection: "column",
                                    gap: "8px",
                                    cursor: matchingViolation ? "pointer" : "default",
                                    opacity: isHidden ? 0.4 : 1,
                                    transition: "opacity 0.2s ease"
                                  }}
                                >
                                  {/* Badge Row */}
                                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                                    <div 
                                      onClick={(e) => {
                                        if (matchingViolation) {
                                          e.stopPropagation();
                                          toggleViolationVisibility(matchingViolation.id);
                                        }
                                      }}
                                      style={{
                                        cursor: matchingViolation ? "pointer" : "default",
                                        color: isHidden ? "#52525b" : "var(--accent-cyan)",
                                        display: "flex",
                                        alignItems: "center"
                                      }}
                                    >
                                      {matchingViolation && (
                                        isHidden ? <EyeOff size={14} /> : <Eye size={14} />
                                      )}
                                    </div>
                                    <span style={{
                                      fontSize: "0.62rem", fontWeight: 700, padding: "2px 6px", borderRadius: "4px",
                                      color: cellBadgeColor, background: cellBadgeBg, border: `1px solid ${cellBadgeColor}33`,
                                      textTransform: "uppercase"
                                    }}>
                                      {statusText}
                                    </span>
                                  </div>

                                  {/* Comparison Grid */}
                                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px", textAlign: "center", background: "rgba(0,0,0,0.2)", padding: "10px", borderRadius: "6px" }}>
                                    {/* Field Title */}
                                    <div style={{ gridColumn: "span 2", fontSize: "0.8rem", fontWeight: 700, color: "var(--accent-cyan)", borderBottom: "1px solid rgba(255,255,255,0.1)", paddingBottom: "6px", textTransform: "uppercase", textAlign: "left" }}>
                                      {row.field}
                                    </div>
                                    
                                    {/* Column Headers */}
                                    <div style={{ fontSize: "0.65rem", fontWeight: 700, color: "var(--text-muted)", marginTop: "4px" }}>
                                      ORIGINAL
                                    </div>
                                    <div style={{ fontSize: "0.65rem", fontWeight: 700, color: "var(--accent-cyan)", marginTop: "4px" }}>
                                      REVISION
                                    </div>
                                    
                                    {/* Values */}
                                    <div style={{
                                      fontSize: "0.75rem", color: "#94a3b8", fontFamily: "'JetBrains Mono', monospace",
                                      textDecoration: statusText.toUpperCase().includes("CHANGE") || statusText.toUpperCase().includes("REMOVE") || statusText.toUpperCase().includes("MIS") ? "line-through" : "none",
                                      wordBreak: "break-word"
                                    }}>
                                      {row.original || "-"}
                                    </div>
                                    <div style={{
                                      fontSize: "0.75rem", color: "#e2e8f0", fontFamily: "'JetBrains Mono', monospace", fontWeight: 600,
                                      wordBreak: "break-word"
                                    }}>
                                      {row.kmti || "-"}
                                    </div>
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        )}
                      </div>
                    );
                  } else {
                    return (
                      <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                        <div style={{ fontSize: "0.8rem", fontWeight: 650, color: "var(--accent-cyan)", marginBottom: "4px", letterSpacing: "0.05em" }}>COMPARATIVE CONTENTS</div>
                        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px" }}>
                          <div style={{ background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.06)", padding: "10px", borderRadius: "6px" }}>
                            <div style={{ fontSize: "0.65rem", fontWeight: 700, color: "var(--text-muted)", marginBottom: "6px" }}>Original Drawing</div>
                            <div style={{ fontSize: "0.78rem", color: "#94a3b8", whiteSpace: "pre-wrap", maxHeight: "150px", overflowY: "auto", fontFamily: "monospace" }}>
                              {result.reference_content || "-"}
                            </div>
                          </div>
                          <div style={{ background: "rgba(0,229,255,0.01)", border: "1px solid rgba(0,229,255,0.1)", padding: "10px", borderRadius: "6px" }}>
                            <div style={{ fontSize: "0.65rem", fontWeight: 700, color: "var(--accent-cyan)", marginBottom: "6px" }}>KMTI Drawing</div>
                            <div style={{ fontSize: "0.78rem", color: "#e2e8f0", whiteSpace: "pre-wrap", maxHeight: "150px", overflowY: "auto", fontFamily: "monospace" }}>
                              {result.revision_content || "-"}
                            </div>
                          </div>
                        </div>
                      </div>
                    );
                  }
                })()}

                {result.engineering_discrepancy_details && (
                  <div>
                    <div style={{ fontSize: "0.8rem", fontWeight: 600, color: "var(--accent-cyan)", marginBottom: "6px" }}>ENGINEERING DISCREPANCY DETAILS</div>
                    <div style={{
                      fontSize: "0.85rem",
                      color: result.status === "MATCHED" ? "#a7f3d0" : "#fecaca",
                      background: result.status === "MATCHED" ? "rgba(16,185,129,0.06)" : "rgba(239,68,68,0.06)",
                      borderLeft: `4px solid ${badgeColor}`,
                      padding: "8px 12px",
                      borderRadius: "0 6px 6px 0",
                      lineHeight: "1.5"
                    }}>
                      {result.engineering_discrepancy_details}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
};
