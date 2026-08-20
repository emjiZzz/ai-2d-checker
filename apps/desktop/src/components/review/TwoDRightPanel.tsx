import React, { useState } from "react";
import { Play, Sparkles, CheckCircle2, ShieldCheck, Bot, Filter, MessageSquareCode, Ruler, Layers, FileText } from "lucide-react";
import { useWorkspaceStore } from "../../stores/workspaceStore";
import { useDrawingStore } from "../../stores/drawingStore";
import { useAuditStore } from "../../stores/auditStore";
import { useReviewStore } from "../../stores/reviewStore";
import { useClients } from "../../hooks/useClients";
import { useJobPolling } from "../../hooks/useJobPolling";
import { useAuditPolling } from "../../hooks/useAuditPolling";
import { Button } from "../ui/Button";
import { Skeleton } from "../ui/Skeleton";
import { cleanCadText } from "./renderEntities";
import { StaleExtractionBadge } from "./StaleExtractionBadge";
import { CopilotPanel } from "../copilot/CopilotPanel";
import { useCopilotStore } from "../../stores/copilotStore";
import { sendCopilotMessage } from "../../services/copilotService";
import { isPrototypeMode } from "../../config/features";

interface TwoDRightPanelProps {
  currentNav: string;
}

export const TwoDRightPanel: React.FC<TwoDRightPanelProps> = ({ currentNav }) => {
  const [panelMode, setPanelMode] = useState<"auditor" | "copilot">("auditor");
  const [severityFilter, setSeverityFilter] = useState<string>("all");

  const newDrawing = useWorkspaceStore((s) => s.newDrawing);
  const oldDrawing = useWorkspaceStore((s) => s.oldDrawing);
  const auditStatus = useWorkspaceStore((s) => s.auditStatus);
  const complianceScore = useWorkspaceStore((s) => s.complianceScore);
  const violations = useWorkspaceStore((s) => s.violations);
  const selectedViolation = useWorkspaceStore((s) => s.selectedViolation);
  const runAudit = useWorkspaceStore((s) => s.runAudit);
  const selectViolation = useWorkspaceStore((s) => s.selectViolation);
  const selectedClient = useWorkspaceStore((s) => s.selectedClient);
  const setSelectedClient = useWorkspaceStore((s) => s.setSelectedClient);
  const aiScanProgress = useWorkspaceStore((s) => s.aiScanProgress);

  const { clients } = useClients();
  const { activeJob } = useDrawingStore();
  const { activeSession } = useAuditStore();

  useJobPolling(activeJob?.id || null);
  useAuditPolling(activeSession?.id || null);

  const isPhysicalComparisonEnabled = useReviewStore((s) => s.isPhysicalComparisonEnabled);

  const handleAuditTrigger = async () => {
    if (!newDrawing || !selectedClient) return;
    await runAudit(selectedClient);
  };

  const handleAskCopilotAboutViolation = (v: any) => {
    selectViolation(v);
    setPanelMode("copilot");
    const desc = v.description || v.category;
    useCopilotStore.getState().addMessage({
      id: `user_${Date.now()}`,
      role: "user",
      content: `Explain this compliance violation and how to fix it in CAD: "${desc}" (Standard reference: ${v.standard_reference || "General"})`,
      isStreaming: false,
      citations: [],
    });
    sendCopilotMessage(`Explain this compliance violation and how to fix it in CAD: "${desc}" (Standard reference: ${v.standard_reference || "General"})`);
  };

  // Only actual Stage 2 Standards & Rules Infractions should be shown in this panel
  const infractionList = violations.filter((v: any) => {
    // Stage 1 comparison findings belong exclusively to the left Comparison Checklist
    if (v.source === "physical_comparison" || (v.id && String(v.id).startsWith("phys_chk_"))) {
      return false;
    }
    const stat = (v.status || "").toUpperCase();
    const desc = (v.description || v.details || "").toLowerCase();
    if (stat === "MATCHED" || desc.includes("verified and matches reference") || desc.includes("matches reference")) {
      return false;
    }
    return true;
  });

  const criticalCount = infractionList.filter((v) => v.severity === "critical").length;
  const highCount = infractionList.filter((v) => v.severity === "high").length;
  const medCount = infractionList.filter((v) => v.severity === "medium").length;
  const lowCount = infractionList.filter((v) => v.severity === "low").length;

  const filteredViolations = infractionList.filter((v) => {
    if (severityFilter === "all") return true;
    return v.severity.toLowerCase() === severityFilter.toLowerCase();
  });

  const isAuditing = auditStatus === "queued" || auditStatus === "auditing";
  const isStandardsAuditCompleted = auditStatus === "completed" && !!selectedClient && complianceScore !== null;

  const getViolationCardClass = (v: any, isSelected: boolean) => {
    const base = "bg-bg-card border border-border-color rounded-sm p-3 cursor-pointer transition-all duration-150 hover:border-l-accent-cyan";
    const selectedClass = isSelected
      ? "border-accent-cyan border-l-accent-cyan shadow-xs"
      : "border-l-transparent";

    let borderLeftColor = "border-l-[3px]";
    switch (v.severity?.toLowerCase()) {
      case "critical": borderLeftColor += " border-l-red-500"; break;
      case "high": borderLeftColor += " border-l-orange-500"; break;
      case "medium": borderLeftColor += " border-l-yellow-500"; break;
      case "low": borderLeftColor += " border-l-blue-500"; break;
      default: borderLeftColor += " border-l-transparent";
    }

    return `${base} ${selectedClass} ${borderLeftColor}`;
  };

  const getSevBadgeClass = (severity: string) => {
    const base = "text-[11px] font-extrabold py-0.5 px-2 rounded uppercase tracking-wider";
    switch (severity?.toLowerCase()) {
      case "critical": return `${base} bg-red-500/15 text-red-300 border border-red-500/30`;
      case "high": return `${base} bg-orange-500/15 text-orange-200 border border-orange-500/30`;
      case "medium": return `${base} bg-yellow-500/15 text-yellow-200 border border-yellow-500/30`;
      case "low": return `${base} bg-blue-500/15 text-blue-200 border border-blue-500/30`;
      default: return `${base} bg-zinc-500/15 text-zinc-300`;
    }
  };

  // Render gate: allow if in workspace and comparison is active/completed or audit results exist
  const isAvailable = isPhysicalComparisonEnabled || aiScanProgress === "completed" || isStandardsAuditCompleted;
  if (currentNav !== "workspace" || !isAvailable) {
    return null;
  }

  return (
    <div className="flex flex-col w-full h-full p-3 overflow-hidden box-border bg-bg-sidebar">
      {/* Top Mode Navigation Switcher */}
      {!isPrototypeMode() && (
        <div className="flex items-center gap-1.5 p-1 bg-bg-dark border border-border-color rounded-lg mb-3 shrink-0">
          <button
            onClick={() => setPanelMode("auditor")}
            className={`flex-1 flex items-center justify-center gap-1.5 py-1.5 px-3 rounded-md text-xs font-semibold cursor-pointer transition-all ${
              panelMode === "auditor"
                ? "bg-accent-cyan/15 border border-accent-cyan/30 text-accent-cyan shadow-xs"
                : "text-text-muted hover:text-text-primary hover:bg-sidebar-item-hover border border-transparent"
            }`}
          >
            <ShieldCheck size={14} />
            <span>Stage 2 Auditor</span>
          </button>

          <button
            onClick={() => setPanelMode("copilot")}
            className={`flex-1 flex items-center justify-center gap-1.5 py-1.5 px-3 rounded-md text-xs font-semibold cursor-pointer transition-all ${
              panelMode === "copilot"
                ? "bg-accent-cyan/15 border border-accent-cyan/30 text-accent-cyan shadow-xs"
                : "text-text-muted hover:text-text-primary hover:bg-sidebar-item-hover border border-transparent"
            }`}
          >
            <Bot size={14} />
            <span>AI Copilot</span>
          </button>
        </div>
      )}

      {/* Mode 1: Stage 2 Compliance Auditor */}
      {panelMode === "auditor" && (
        <div className="flex flex-col w-full h-full overflow-y-auto min-h-0">
          {/*
            Above the audit trigger on purpose: an audit run against a sheet that is drawing
            its own geometry wrong is measuring the extraction, not the drawing. Both render
            nothing when the drawing is current, so a healthy database shows no chrome here.
          */}
          <StaleExtractionBadge drawing={oldDrawing} label="Reference" />
          <StaleExtractionBadge drawing={newDrawing} label="Revision" />

          {/* Grounding & Trigger Box */}
          <div className="bg-bg-card border border-border-color rounded-xl p-4 backdrop-blur-md shadow-xs mb-3 shrink-0">
            <h3 className="text-xs font-bold mb-3 flex items-center gap-2 border-l-[3px] border-accent-cyan pl-2 text-text-primary uppercase tracking-wide">
              <Sparkles size={14} className="text-accent-cyan" />
              Stage 2 Standards Auditor
            </h3>

            <div className="flex flex-col gap-1.5">
              <label className="text-[11px] font-semibold uppercase tracking-wider text-text-muted">Grounding Client Profile</label>
              <select
                className="w-full bg-bg-dark border border-border-color rounded-lg py-2 px-3 text-xs text-text-primary font-mono focus:outline-none focus:border-accent-cyan transition-all cursor-pointer"
                value={selectedClient || ""}
                onChange={(e) => setSelectedClient(e.target.value)}
              >
                <option value="" disabled>Select Target Client Profile</option>
                {clients.map((c: any) => (
                  <option key={c.id} value={c.name}>{c.name}</option>
                ))}
              </select>
            </div>

            <Button
              variant="primary"
              className="w-full mt-3 gap-2 h-10 bg-linear-to-br from-blue-600 to-blue-800 border-0 text-xs font-bold"
              onClick={handleAuditTrigger}
              disabled={!newDrawing || !selectedClient || isAuditing}
            >
              <Play size={14} fill="currentColor" />
              <span>
                {isAuditing ? "Auditing Client Standards..." : "Execute Compliance Audit"}
              </span>
            </Button>
          </div>

          {/* Readiness Card (Before Audit Run) */}
          {!isStandardsAuditCompleted && !isAuditing && (
            <div className="bg-bg-card border border-border-color rounded-xl p-4 backdrop-blur-md shadow-xs flex flex-col gap-3 shrink-0">
              <div className="flex items-center gap-2 text-text-primary text-xs font-bold">
                <ShieldCheck size={16} className="text-accent-cyan" />
                <span>Standards & Compliance Verification</span>
              </div>
              <p className="text-[11px] text-text-muted leading-relaxed m-0">
                Evaluates the CAD drawing against Japanese Industrial Standards (JIS) and company-specific manufacturing guidelines.
              </p>

              <div className="flex flex-col gap-2 mt-1">
                <div className="flex items-center gap-2.5 p-2 rounded-lg bg-bg-dark border border-border-color/60 text-xs">
                  <Ruler size={14} className="text-accent-cyan shrink-0" />
                  <div className="flex flex-col">
                    <span className="text-[11px] font-semibold text-text-primary">Tolerances & Limits</span>
                    <span className="text-[10px] text-text-muted">ISO 2768-m, machining fits, and general tolerances</span>
                  </div>
                </div>

                <div className="flex items-center gap-2.5 p-2 rounded-lg bg-bg-dark border border-border-color/60 text-xs">
                  <Layers size={14} className="text-accent-cyan shrink-0" />
                  <div className="flex flex-col">
                    <span className="text-[11px] font-semibold text-text-primary">Layer & Line Conventions</span>
                    <span className="text-[10px] text-text-muted">JIS line types, lineweights, and layer taxonomy</span>
                  </div>
                </div>

                <div className="flex items-center gap-2.5 p-2 rounded-lg bg-bg-dark border border-border-color/60 text-xs">
                  <FileText size={14} className="text-accent-cyan shrink-0" />
                  <div className="flex flex-col">
                    <span className="text-[11px] font-semibold text-text-primary">Client Profile Rules</span>
                    <span className="text-[10px] text-text-muted">Company title blocks, BOM format, and notes rules</span>
                  </div>
                </div>
              </div>

              <div className="text-[10px] text-text-muted text-center pt-2 border-t border-border-color/40">
                Select a profile above and click <span className="text-accent-cyan font-semibold">Execute Compliance Audit</span> to begin.
              </div>
            </div>
          )}

          {/* Audit in Progress State */}
          {isAuditing && (
            <div className="bg-bg-card border border-border-color rounded-xl p-4 backdrop-blur-md shadow-xs flex flex-col gap-3">
              <div className="flex items-center gap-2 text-text-muted text-xs">
                <div className="spin-animation w-3.5 h-3.5 border-2 border-accent-cyan border-t-transparent rounded-full"></div>
                <span>Auditing CAD drawings against standard guidelines...</span>
              </div>
              {Array.from({ length: 3 }).map((_, i) => (
                <div key={i} className="bg-bg-dark border border-border-color rounded-lg p-3 flex flex-col gap-2">
                  <div className="flex justify-between items-center">
                    <Skeleton className="h-4 w-16" />
                    <Skeleton className="h-3 w-12" />
                  </div>
                  <Skeleton className="h-4 w-3/4" />
                  <Skeleton className="h-3 w-full" />
                </div>
              ))}
            </div>
          )}

          {/* Compliance Score Gauge & Breakdown (After Audit Completes) */}
          {isStandardsAuditCompleted && (
            <div className="bg-bg-card border border-border-color rounded-xl p-4 backdrop-blur-md shadow-xs mb-3 flex flex-col items-center gap-2.5 shrink-0">
              <div
                className="w-20 h-20 rounded-full border-4 flex flex-col items-center justify-center mt-1"
                style={{ borderColor: complianceScore && complianceScore >= 80 ? "#10b981" : "#f59e0b" }}
              >
                <span className="text-xl font-extrabold text-text-primary leading-none">{complianceScore ?? 0}%</span>
                <span className="text-[10px] font-bold uppercase text-text-muted mt-0.5">Score</span>
              </div>

              <div className="grid grid-cols-4 gap-1.5 w-full mt-2">
                <div className="flex flex-col items-center bg-bg-dark py-1.5 px-1 rounded border border-border-color border-l-[3px] border-l-red-500">
                  <span className="text-base font-bold text-text-primary leading-tight">{criticalCount}</span>
                  <span className="text-[10px] text-text-muted uppercase">Crit</span>
                </div>
                <div className="flex flex-col items-center bg-bg-dark py-1.5 px-1 rounded border border-border-color border-l-[3px] border-l-orange-500">
                  <span className="text-base font-bold text-text-primary leading-tight">{highCount}</span>
                  <span className="text-[10px] text-text-muted uppercase">High</span>
                </div>
                <div className="flex flex-col items-center bg-bg-dark py-1.5 px-1 rounded border border-border-color border-l-[3px] border-l-yellow-500">
                  <span className="text-base font-bold text-text-primary leading-tight">{medCount}</span>
                  <span className="text-[10px] text-text-muted uppercase">Med</span>
                </div>
                <div className="flex flex-col items-center bg-bg-dark py-1.5 px-1 rounded border border-border-color border-l-[3px] border-l-blue-500">
                  <span className="text-base font-bold text-text-primary leading-tight">{lowCount}</span>
                  <span className="text-[10px] text-text-muted uppercase">Low</span>
                </div>
              </div>
            </div>
          )}

          {/* 100% Compliant Celebratory State */}
          {isStandardsAuditCompleted && infractionList.length === 0 && (
            <div className="bg-bg-card border border-border-color rounded-xl p-6 backdrop-blur-md shadow-xs flex flex-col items-center justify-center text-center gap-2.5 flex-grow">
              <CheckCircle2 size={36} className="text-emerald-400" />
              <h4 className="text-sm font-bold text-text-primary m-0">100% Standards Compliant</h4>
              <p className="text-xs text-text-muted m-0 leading-relaxed max-w-xs">
                No CAD engineering rule violations detected for client <span className="text-accent-cyan font-semibold">{selectedClient || "profile"}</span>.
              </p>
            </div>
          )}

          {/* Infractions Feed & Filters (Only if infractions exist) */}
          {isStandardsAuditCompleted && infractionList.length > 0 && (
            <div className="bg-bg-card border border-border-color rounded-xl p-4 backdrop-blur-md shadow-xs flex-grow flex flex-col min-h-0 overflow-hidden">
              <div className="flex items-center justify-between gap-2 mb-2 pb-2 border-b border-border-color shrink-0">
                <h4 className="text-xs font-bold flex items-center gap-1.5 text-text-primary m-0 uppercase tracking-wide">
                  <span>Infractions</span>
                  <span className="text-text-muted font-normal">({filteredViolations.length})</span>
                </h4>

                {/* Severity Filter Chips */}
                <div className="flex items-center gap-1">
                  <Filter size={11} className="text-text-muted" />
                  {(["all", "critical", "high", "medium", "low"] as const).map((sev) => (
                    <button
                      key={sev}
                      onClick={() => setSeverityFilter(sev)}
                      className={`px-1.5 py-0.5 text-[10px] font-bold rounded uppercase transition-colors cursor-pointer ${
                        severityFilter === sev
                          ? "bg-accent-cyan text-zinc-950"
                          : "text-text-muted bg-bg-dark border border-border-color hover:text-text-primary"
                      }`}
                    >
                      {sev === "all" ? "All" : sev[0].toUpperCase()}
                    </button>
                  ))}
                </div>
              </div>

              <div className="overflow-y-auto flex-grow flex flex-col gap-2.5 pr-0.5">
                {filteredViolations.length === 0 && (
                  <div className="text-xs text-center py-8 flex flex-col items-center justify-center gap-2 text-emerald-400">
                    <CheckCircle2 size={24} className="text-emerald-400" />
                    <span className="font-semibold">No infractions found matching {severityFilter} filter.</span>
                  </div>
                )}

                {filteredViolations.map((v) => (
                  <div
                    key={v.id}
                    role="button"
                    tabIndex={0}
                    aria-label={`Select ${v.severity} violation: ${v.category}`}
                    className={getViolationCardClass(v, selectedViolation?.id === v.id)}
                    onClick={() => selectViolation(v)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        selectViolation(v);
                      }
                    }}
                  >
                    <div className="flex justify-between items-center mb-1.5">
                      <div className="flex items-center gap-1.5">
                        <span className={getSevBadgeClass(v.severity)}>{v.severity.toUpperCase()}</span>
                        {(v as any).entity_handle && (
                          <span
                            className="text-[10px] font-mono font-bold px-1 py-0.5 rounded bg-cyan-500/10 text-accent-cyan border border-cyan-500/30"
                            title={`CAD Entity Handle: ${(v as any).entity_handle}`}
                          >
                            {(v as any).entity_handle}
                          </span>
                        )}
                      </div>
                      <span className="text-[10px] font-mono text-text-muted truncate max-w-[120px]">
                        {v.standard_reference || "General"}
                      </span>
                    </div>

                    <h5 className="text-xs font-bold text-text-primary mb-1">{cleanCadText(v.category)}</h5>
                    <p className="text-[11px] text-text-muted mb-2 leading-relaxed">{cleanCadText(v.description)}</p>

                    {v.recommendation && (
                      <div className="bg-bg-dark border border-border-color p-2 rounded text-[11px] text-text-primary leading-relaxed mb-2">
                        <strong className="text-accent-cyan">Fix:</strong> {cleanCadText(v.recommendation)}
                      </div>
                    )}

                    <div className="flex items-center justify-between pt-1 border-t border-border-color/60 text-[10px]">
                      <span className="text-text-muted">
                        Confidence: {(v.confidence * 100).toFixed(0)}%
                      </span>
                      {!isPrototypeMode() && (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleAskCopilotAboutViolation(v);
                          }}
                          className="flex items-center gap-1 text-accent-cyan hover:underline font-semibold cursor-pointer bg-accent-cyan/10 hover:bg-accent-cyan/20 px-2 py-0.5 rounded border border-accent-cyan/30 transition-all"
                          title="Ask Engineering Copilot about this violation"
                        >
                          <MessageSquareCode size={11} />
                          <span>Ask Copilot →</span>
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Mode 2: Engineering Copilot */}
      {panelMode === "copilot" && (
        <div className="flex flex-col w-full h-full overflow-hidden min-h-0">
          <CopilotPanel />
        </div>
      )}
    </div>
  );
};




