import React from "react";
import { Play, Sparkles, CheckCircle2 } from "lucide-react";
import { useWorkspaceStore } from "../../stores/workspaceStore";
import { useDrawingStore } from "../../stores/drawingStore";
import { useAuditStore } from "../../stores/auditStore";
import { useReviewStore } from "../../stores/reviewStore";
import { useClients } from "../../hooks/useClients";
import { useJobPolling } from "../../hooks/useJobPolling";
import { useAuditPolling } from "../../hooks/useAuditPolling";
import { Button } from "../ui/Button";
import { Skeleton } from "../ui/Skeleton";

interface TwoDRightPanelProps {
  currentNav: string;
}

export const TwoDRightPanel: React.FC<TwoDRightPanelProps> = ({ currentNav }) => {
  const newDrawing = useWorkspaceStore((s) => s.newDrawing);
  const auditStatus = useWorkspaceStore((s) => s.auditStatus);
  const complianceScore = useWorkspaceStore((s) => s.complianceScore);
  const violations = useWorkspaceStore((s) => s.violations);
  const selectedViolation = useWorkspaceStore((s) => s.selectedViolation);
  const runAudit = useWorkspaceStore((s) => s.runAudit);
  const selectViolation = useWorkspaceStore((s) => s.selectViolation);
  const selectedClient = useWorkspaceStore((s) => s.selectedClient);
  const setSelectedClient = useWorkspaceStore((s) => s.setSelectedClient);

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

  const criticalCount = violations.filter((v) => v.severity === "critical").length;
  const highCount = violations.filter((v) => v.severity === "high").length;
  const medCount = violations.filter((v) => v.severity === "medium").length;
  const lowCount = violations.filter((v) => v.severity === "low").length;

  const getViolationCardClass = (v: any, isSelected: boolean) => {
    const base = "bg-bg-dark border border-border-color rounded-xl p-3.5 cursor-pointer transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md hover:border-l-accent-cyan";
    const selectedClass = isSelected
      ? "border-accent-cyan border-l-accent-cyan shadow-[0_0_10px_rgba(37,99,235,0.18)] data-[theme=hc-dark]:shadow-[0_0_12px_rgba(0,229,255,0.2)]"
      : "border-l-transparent";
    
    let borderLeftColor = "border-l-[3px]";
    switch (v.severity.toLowerCase()) {
      case "critical": borderLeftColor += " border-l-red-500"; break;
      case "high": borderLeftColor += " border-l-orange-500"; break;
      case "medium": borderLeftColor += " border-l-yellow-500"; break;
      case "low": borderLeftColor += " border-l-blue-500"; break;
      default: borderLeftColor += " border-l-transparent";
    }
    
    return `${base} ${selectedClass} ${borderLeftColor}`;
  };

  const getSevBadgeClass = (severity: string) => {
    const base = "text-sm font-extrabold py-0.5 px-1.5 rounded uppercase";
    switch (severity.toLowerCase()) {
      case "critical": return `${base} bg-red-500/15 text-red-300 data-[theme=hc-light]:bg-red-500/10 data-[theme=hc-light]:text-red-700`;
      case "high": return `${base} bg-orange-500/15 text-orange-200 data-[theme=hc-light]:bg-orange-500/10 data-[theme=hc-light]:text-orange-700`;
      case "medium": return `${base} bg-yellow-500/15 text-yellow-200 data-[theme=hc-light]:bg-yellow-500/10 data-[theme=hc-light]:text-yellow-700`;
      case "low": return `${base} bg-blue-500/15 text-blue-200 data-[theme=hc-light]:bg-blue-500/10 data-[theme=hc-light]:text-blue-700`;
      default: return `${base} bg-zinc-500/15 text-zinc-300`;
    }
  };

  if (currentNav !== "workspace" || !isPhysicalComparisonEnabled) {
    return null;
  }

  return (
    <div className="flex flex-col w-full h-full p-4 overflow-y-auto box-border bg-bg-sidebar">
      <div className="bg-bg-card border-2 border-dashed border-border-color rounded-xl p-6 backdrop-blur-md shadow-sm mb-5">
        <h3 className="text-sm font-bold mb-4 flex items-center gap-2.5 border-l-[3px] border-accent-cyan pl-2.5 text-text-primary">
          <Sparkles size={16} style={{ color: "var(--accent-cyan)" }} />
          Stage 2 AI Compliance Auditor
        </h3>

        <div className="flex flex-col gap-2" style={{ marginTop: "12px" }}>
          <label className="text-sm font-semibold uppercase tracking-wider text-text-muted">Grounding Client Profile</label>
          <select
            className="w-full bg-transparent border border-border-color rounded-lg py-2.5 px-3.5 text-sm text-text-primary font-mono focus:outline-none focus:border-accent-cyan focus:shadow-[0_0_10px_rgba(0,229,255,0.15)] transition-all cursor-pointer"
            value={selectedClient || ""}
            onChange={(e) => setSelectedClient(e.target.value)}
          >
            <option value="" disabled>Select Target Client</option>
            {clients.map((c: any) => (
              <option key={c.id} value={c.name}>{c.name}</option>
            ))}
          </select>
        </div>

        <Button
          variant="primary"
          className="w-full mt-4 gap-2 h-12 bg-linear-to-br from-blue-600 to-blue-800 border-0"
          onClick={handleAuditTrigger}
          disabled={!newDrawing || auditStatus === "queued" || auditStatus === "auditing"}
        >
          <Play size={15} fill="currentColor" />
          <span>
            {auditStatus === "queued" || auditStatus === "auditing" ? "Running AI Auditing Pipeline..." : "Execute Compliance Audit"}
          </span>
        </Button>
      </div>

      {auditStatus === "completed" && (
        <div className="bg-bg-card border-2 border-dashed border-border-color rounded-xl p-6 backdrop-blur-md shadow-sm mb-5 flex flex-col items-center gap-3">
          <div className="w-[110px] h-[110px] rounded-full border-4 flex flex-col items-center justify-center mt-2.5" style={{ borderColor: complianceScore && complianceScore >= 80 ? "#10b981" : "#f59e0b" }}>
            <span className="text-2xl font-extrabold text-text-primary leading-none">{complianceScore}%</span>
            <span className="text-sm font-bold uppercase text-text-muted">Compliance</span>
          </div>

          <div className="grid grid-cols-4 gap-2.5 w-full mt-3.5">
            <div className="flex flex-col items-center bg-bg-dark p-2 rounded border border-border-color border-l-[3px] border-l-red-500">
              <span className="text-lg font-bold text-text-primary">{criticalCount}</span>
              <span className="text-sm text-text-muted uppercase">Critical</span>
            </div>
            <div className="flex flex-col items-center bg-bg-dark p-2 rounded border border-border-color border-l-[3px] border-l-orange-500">
              <span className="text-lg font-bold text-text-primary">{highCount}</span>
              <span className="text-sm text-text-muted uppercase">High</span>
            </div>
            <div className="flex flex-col items-center bg-bg-dark p-2 rounded border border-border-color border-l-[3px] border-l-yellow-500">
              <span className="text-lg font-bold text-text-primary">{medCount}</span>
              <span className="text-sm text-text-muted uppercase">Med</span>
            </div>
            <div className="flex flex-col items-center bg-bg-dark p-2 rounded border border-border-color border-l-[3px] border-l-blue-500">
              <span className="text-lg font-bold text-text-primary">{lowCount}</span>
              <span className="text-sm text-text-muted uppercase">Low</span>
            </div>
          </div>
        </div>
      )}

      <div className="bg-bg-card border-2 border-dashed border-border-color rounded-xl p-6 backdrop-blur-md shadow-sm flex-grow flex flex-col overflow-hidden">
        <h4 className="text-sm font-bold mb-4 flex items-center gap-2.5 border-l-[3px] border-accent-cyan pl-2.5 text-text-primary">Infractions & Grounding Explanations</h4>

        <div className="overflow-y-auto flex-grow mt-4 flex flex-col gap-3">
          {auditStatus === "idle" && (
            <div className="text-text-muted text-sm text-center py-6 flex flex-col items-center justify-center gap-3">Trigger compliance run to scan revision drawing against engineering manuals.</div>
          )}
          {auditStatus === "queued" || auditStatus === "auditing" ? (
            <div className="flex flex-col gap-4">
              <div className="flex items-center gap-3 text-text-muted text-sm py-2">
                <div className="spin-animation loader-icon w-4 h-4 border-2 border-accent-cyan border-t-transparent rounded-full"></div>
                <span>Reasoning over draft dimensions...</span>
              </div>
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="bg-bg-dark border border-border-color rounded-xl p-3.5 flex flex-col gap-3">
                  <div className="flex justify-between items-center">
                    <Skeleton className="h-5 w-16" />
                    <Skeleton className="h-4 w-12" />
                  </div>
                  <Skeleton className="h-5 w-3/4" />
                  <Skeleton className="h-4 w-full" />
                  <Skeleton className="h-4 w-5/6" />
                  <Skeleton className="h-10 w-full mt-2" />
                </div>
              ))}
            </div>
          ) : null}

          {auditStatus === "completed" && violations.length === 0 ? (
            <div className="text-sm text-center py-6 flex flex-col items-center justify-center gap-3 text-emerald-400">
              <CheckCircle2 size={36} style={{ color: "#10b981" }} />
              <span style={{ marginTop: "12px", color: "#10b981" }}>No compliance infractions found in revision drawing!</span>
            </div>
          ) : null}

          {auditStatus === "completed" && violations.map((v) => (
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
              <div className="flex justify-between items-center mb-2">
                <div className="flex items-center gap-1.5">
                  <span className={getSevBadgeClass(v.severity)}>{v.severity.toUpperCase()}</span>
                  {(v as any).entity_handle && (
                    <span
                      className="text-[10px] font-bold font-mono px-1.5 py-0.5 rounded bg-cyan-500/20 text-cyan-300 border border-cyan-500/40"
                      title={`CAD Entity Handle: ${(v as any).entity_handle}`}
                    >
                      [ID: {(v as any).entity_handle}]
                    </span>
                  )}
                </div>
                <span className="text-sm font-mono text-text-muted">{v.standard_reference || "General"}</span>
              </div>

              <h5 className="text-sm font-bold text-text-primary mb-1.5">{v.category}</h5>
              <p className="text-sm text-text-muted mb-2.5 leading-relaxed">{v.description}</p>

              <div className="bg-bg-dark border border-border-color p-2 rounded text-sm text-text-primary leading-relaxed mb-2.5">
                <strong>AI Fix Chip:</strong> {v.recommendation}
              </div>

              <div className="flex justify-between items-center text-sm">
                <span className="text-text-muted">Confidence: {(v.confidence * 100).toFixed(0)}%</span>
                <span className="text-accent-cyan hover:underline cursor-pointer">Highlight coordinates →</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

