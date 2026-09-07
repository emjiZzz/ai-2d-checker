import React, { useState, useEffect, useRef } from "react";
import { ChevronLeft, ChevronRight, Sparkles, Play, CheckCircle2, RotateCcw, AlertTriangle } from "lucide-react";
import { useThreeDStore } from "../../stores/threeDStore";
import { useDrawingStore } from "../../stores/drawingStore";
import { useAuditStore } from "../../stores/auditStore";
import { useClients } from "../../hooks/useClients";
import { useJobPolling } from "../../hooks/useJobPolling";
import { useAuditPolling } from "../../hooks/useAuditPolling";
import { ThreeDViewer } from "./ThreeDViewer";
import { UploadZone } from "./UploadZone";
import { Skeleton } from "../ui/Skeleton";
import { Select } from "../ui/Select";

interface ThreeDWorkspaceProps {
  currentNav: string;
}

export const ThreeDWorkspace: React.FC<ThreeDWorkspaceProps> = ({ currentNav }) => {
  const {
    activeDrawing,
    uploadState,
    uploadProgress,
    fileName,
    fileSize,
    errorMessage,
    uploadDrawingFile,
    clearUpload,
    selectedClient,
    setSelectedClient,
    auditStatus,
    complianceScore,
    violations,
    selectedViolation,
    selectViolation,
    runAudit,
    _setDrawing,
    _setUploadStatus,
  } = useThreeDStore();

  const { clients } = useClients();
  const { activeJob } = useDrawingStore();
  const { activeSession } = useAuditStore();

  // Attach TanStack Query background pollers. They automatically sleep if no active job/session.
  useJobPolling(activeJob?.id || null);
  useAuditPolling(activeSession?.id || null);

  const [isRightPanelCollapsed, setIsRightPanelCollapsed] = useState(false);
  const [rightSidebarWidth, setRightSidebarWidth] = useState(400);
  const [isResizingRight, setIsResizingRight] = useState(false);

  const containerRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 480, height: 500 });

  useEffect(() => {
    const resizeObserver = new ResizeObserver((entries) => {
      for (let entry of entries) {
        if (entry.target === containerRef.current) {
          setSize({ width: entry.contentRect.width, height: entry.contentRect.height });
        }
      }
    });

    if (containerRef.current) {
      resizeObserver.observe(containerRef.current);
    }
    return () => resizeObserver.disconnect();
  }, [activeDrawing]);

  // Resize Right panel
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (isResizingRight) {
        const newWidth = Math.max(250, Math.min(600, window.innerWidth - e.clientX));
        setRightSidebarWidth(newWidth);
      }
    };
    const handleMouseUp = () => {
      setIsResizingRight(false);
    };
    if (isResizingRight) {
      window.addEventListener("mousemove", handleMouseMove);
      window.addEventListener("mouseup", handleMouseUp);
    }
    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
  }, [isResizingRight]);

  const handleAuditTrigger = async () => {
    if (!activeDrawing || !selectedClient) return;
    await runAudit(selectedClient);
  };

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
    const base = "text-[11px] font-extrabold py-0.5 px-1.5 rounded uppercase";
    switch (severity.toLowerCase()) {
      case "critical": return `${base} bg-red-500/15 text-red-300 data-[theme=hc-light]:bg-red-500/10 data-[theme=hc-light]:text-red-700`;
      case "high": return `${base} bg-orange-500/15 text-orange-200 data-[theme=hc-light]:bg-orange-500/10 data-[theme=hc-light]:text-orange-700`;
      case "medium": return `${base} bg-yellow-500/15 text-yellow-200 data-[theme=hc-light]:bg-yellow-500/10 data-[theme=hc-light]:text-yellow-700`;
      case "low": return `${base} bg-blue-500/15 text-blue-200 data-[theme=hc-light]:bg-blue-500/10 data-[theme=hc-light]:text-blue-700`;
      default: return `${base} bg-zinc-500/15 text-zinc-300`;
    }
  };

  const criticalCount = violations.filter((v) => v.severity === "critical").length;
  const highCount = violations.filter((v) => v.severity === "high").length;
  const medCount = violations.filter((v) => v.severity === "medium").length;
  const lowCount = violations.filter((v) => v.severity === "low").length;

  return (
    <div className="flex flex-grow h-full overflow-hidden min-w-0">
      <main className="flex-grow h-full min-h-0 min-w-0 flex flex-col p-2.5 overflow-hidden border-r border-border-color box-border" style={{ display: "flex", flexDirection: "column", position: "relative" }}>
        <div className="bg-bg-card border border-border-color rounded-sm p-2 shadow-xs mb-2 z-10">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", width: "100%", gap: "12px", flexWrap: "wrap" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
              <h3 className="text-xs font-bold tracking-tight flex items-center border-l-[3px] border-accent-cyan pl-2 text-text-primary uppercase m-0">
                Stage 1: 3D Model Checking Ingestion
              </h3>
              
              {activeDrawing && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-sm bg-purple-500/15 border border-purple-500/30 text-purple-400 text-[11px] font-mono">
                  ACTIVE 3D: {activeDrawing.file_name}
                </span>
              )}
            </div>
          </div>
        </div>

        <div className="flex-grow bg-bg-sidebar border border-border-color rounded-sm flex flex-col overflow-hidden min-h-[450px] relative">
          <div style={{ position: "absolute", top: 0, left: 0, width: "100%", height: "100%", zIndex: 1 }} ref={containerRef}>
            <ThreeDViewer
              drawing={activeDrawing}
              width={size.width}
              height={size.height}
            />
          </div>

          {(!activeDrawing || !["step", "stp", "iges", "igs", "icd", "sldprt", "sldasm"].includes(activeDrawing?.format?.toLowerCase() || "")) && (
            <div className="absolute inset-0 z-10 flex flex-col items-center justify-center bg-bg-dark/80 backdrop-blur-md">
              <div className="w-[400px] bg-bg-card p-5 rounded-sm border border-border-color shadow-xl">
                <h2 className="text-center text-text-primary text-lg font-bold tracking-tight mb-1">3D Model Ingestion</h2>
                <p className="text-center text-text-muted text-xs mb-4 leading-relaxed">Upload your 3D model file to begin compliance checking</p>
                <UploadZone
                  side="new"
                  uploadState={uploadState}
                  progress={uploadProgress}
                  fileName={fileName}
                  fileSize={fileSize}
                  error={errorMessage}
                  activeDrawing={activeDrawing}
                  uploadDrawingFile={uploadDrawingFile}
                  clearUpload={clearUpload}
                  currentNav={currentNav}
                />
                
                <div style={{ marginTop: "16px", display: "flex", justifyContent: "center" }}>
                  <button
                    onClick={() => {
                      _setDrawing({
                        id: "demo_step_3d",
                        file_name: "bracket_v2_machined.step",
                        format: "step",
                        file_path: "uploads/demo_step_3d.step",
                        entity_counts: { FACE: 42, SOLID: 1 },
                        metadata: { face_count: 42, volume_mm3: 27100, surface_area_mm2: 6500, bounds_min: [-40, -40, -40], bounds_max: [40, 40, 40] },
                        created_at: new Date().toISOString()
                      });
                      _setUploadStatus("completed", 100);
                    }}
                    className="flex items-center justify-center gap-1.5 py-1.5 px-3 text-xs font-bold rounded-sm cursor-pointer transition-all bg-purple-500/10 border border-dashed border-purple-500/40 text-purple-400 hover:bg-purple-500/20 w-full"
                  >
                    <RotateCcw size={12} />
                    Load 3D STEP Demo
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      </main>

      <aside
        className={`stage2-right-panel ${isRightPanelCollapsed ? "collapsed" : ""}`}
        style={{
          width: isRightPanelCollapsed ? "40px" : `${rightSidebarWidth}px`,
          minWidth: isRightPanelCollapsed ? "40px" : `${rightSidebarWidth}px`,
          position: "relative",
          display: "flex",
          flexDirection: "column",
          transition: isResizingRight ? "none" : "width 300ms cubic-bezier(0.4, 0, 0.2, 1)"
        }}
      >
        {/* Kept inside the panel's own box (no negative offset) so it can never be
            clipped by the overflow-hidden ancestors of the workspace layout — a
            collapsed panel that shrank all the way to 0px used to strand this
            button off-screen with no way to reopen the panel. */}
        <button
          className="absolute left-1 top-4 z-50 w-8 h-8 rounded-lg bg-bg-card border border-border-color shadow-md flex items-center justify-center text-text-muted hover:text-accent-cyan hover:border-accent-cyan transition-colors cursor-pointer"
          onClick={() => setIsRightPanelCollapsed(!isRightPanelCollapsed)}
          title={isRightPanelCollapsed ? "Expand AI Explanations" : "Collapse AI Explanations"}
        >
          {isRightPanelCollapsed ? <ChevronLeft size={16} /> : <ChevronRight size={16} />}
        </button>

        {!isRightPanelCollapsed && (
          <div
            className="absolute left-0 top-0 bottom-0 w-1 cursor-ew-resize hover:bg-accent-cyan/40 transition-colors z-50"
            onMouseDown={(e) => {
              e.preventDefault();
              setIsResizingRight(true);
            }}
          />
        )}

        {!isRightPanelCollapsed && (
        <div className="panel-content-wrapper" style={{ display: "flex", flexDirection: "column", height: "100%", overflowY: "auto", padding: "16px" }}>
          <div className="bg-bg-card border border-border-color rounded-xl p-6 backdrop-blur-md shadow-sm mb-5">
            <h3 className="text-base font-extrabold tracking-tight mb-4 flex items-center gap-3 text-text-primary">
              <span className="w-8 h-8 rounded-lg bg-linear-to-br from-indigo-500 to-purple-600 flex items-center justify-center shrink-0 shadow-sm">
                <Sparkles size={15} className="text-white" />
              </span>
              Stage 2 AI 3D Compliance Auditor
            </h3>

            <div className="flex flex-col gap-2" style={{ marginTop: "12px" }}>
              <label className="text-[10px] font-semibold uppercase tracking-wider text-text-muted">Grounding Client Profile</label>
              <Select
                value={selectedClient || ""}
                onChange={setSelectedClient}
                placeholder="Select Target Client"
                options={clients.map((c: any) => ({ value: c.name, label: c.name }))}
              />
            </div>

            <button
              className="inline-flex items-center justify-center gap-2 py-3 px-6 rounded-xl font-bold text-sm cursor-pointer transition-all bg-linear-to-br from-indigo-500 to-purple-600 text-white shadow-md hover:-translate-y-0.5 hover:shadow-lg hover:brightness-105 border border-transparent disabled:opacity-50 disabled:pointer-events-none w-full mt-4 justify-center whitespace-nowrap"
              onClick={handleAuditTrigger}
              disabled={!activeDrawing || auditStatus === "queued" || auditStatus === "auditing"}
            >
              <Play size={15} fill="currentColor" />
              <span>
                {auditStatus === "queued" || auditStatus === "auditing" ? "Analyzing 3D Topology..." : "Execute 3D Compliance Audit"}
              </span>
            </button>
          </div>

          {auditStatus === "completed" && (
            <div className="bg-bg-card border border-border-color rounded-xl p-6 backdrop-blur-md shadow-sm mb-5 flex flex-col items-center gap-3">
              <div className="w-[110px] h-[110px] rounded-full border-4 flex flex-col items-center justify-center mt-2.5" style={{ borderColor: complianceScore && complianceScore >= 80 ? "#10b981" : "#f59e0b" }}>
                <span className="text-2xl font-extrabold text-text-primary leading-none">{complianceScore}%</span>
                <span className="text-[10px] font-bold uppercase text-text-muted">Compliance</span>
              </div>

              <div className="grid grid-cols-4 gap-2.5 w-full mt-3.5">
                <div className="flex flex-col items-center bg-bg-dark p-2 rounded border border-border-color border-l-[3px] border-l-red-500">
                  <span className="text-lg font-bold text-text-primary">{criticalCount}</span>
                  <span className="text-[11px] text-text-muted uppercase">Critical</span>
                </div>
                <div className="flex flex-col items-center bg-bg-dark p-2 rounded border border-border-color border-l-[3px] border-l-orange-500">
                  <span className="text-lg font-bold text-text-primary">{highCount}</span>
                  <span className="text-[11px] text-text-muted uppercase">High</span>
                </div>
                <div className="flex flex-col items-center bg-bg-dark p-2 rounded border border-border-color border-l-[3px] border-l-yellow-500">
                  <span className="text-lg font-bold text-text-primary">{medCount}</span>
                  <span className="text-[11px] text-text-muted uppercase">Med</span>
                </div>
                <div className="flex flex-col items-center bg-bg-dark p-2 rounded border border-border-color border-l-[3px] border-l-blue-500">
                  <span className="text-lg font-bold text-text-primary">{lowCount}</span>
                  <span className="text-[11px] text-text-muted uppercase">Low</span>
                </div>
              </div>
            </div>
          )}

          <div className="bg-bg-card border border-border-color rounded-xl p-6 backdrop-blur-md shadow-sm flex-grow flex flex-col overflow-hidden">
            <h4 className="text-base font-extrabold tracking-tight mb-4 flex items-center gap-2.5 border-l-[3px] border-accent-cyan pl-2.5 text-text-primary">AI Geometrical Infractions & peer checking</h4>
            
            <div className="overflow-y-auto flex-grow mt-4 flex flex-col gap-3">
              {auditStatus === "idle" && (
                <div className="text-text-muted text-sm text-center py-6 flex flex-col items-center justify-center gap-3 px-2">
                  <span className="w-10 h-10 rounded-full bg-amber-500/10 border border-amber-500/20 flex items-center justify-center shrink-0">
                    <AlertTriangle size={18} className="text-amber-500" />
                  </span>
                  <span className="leading-relaxed">Trigger 3D compliance run to check mechanical alignment against manufacturing standards.</span>
                  <span className="inline-flex items-center gap-1 text-accent-cyan font-semibold hover:underline cursor-pointer">
                    Learn more <ChevronRight size={13} />
                  </span>
                </div>
              )}
              
              {auditStatus === "queued" || auditStatus === "auditing" ? (
                <div className="flex flex-col gap-4">
                  <div className="flex items-center gap-3 text-text-muted text-xs py-2">
                    <div className="spin-animation loader-icon w-4 h-4 border-2 border-accent-cyan border-t-transparent rounded-full"></div>
                    <span>Evaluating counterbore & step tolerances...</span>
                  </div>
                  {Array.from({ length: 4 }).map((_, i) => (
                    <div key={i} className="bg-bg-dark border border-border-color rounded-xl p-3.5 flex flex-col gap-3">
                      <div className="flex justify-between items-center">
                        <Skeleton className="h-4 w-16" />
                        <Skeleton className="h-3 w-12" />
                      </div>
                      <Skeleton className="h-4 w-3/4" />
                      <Skeleton className="h-3 w-full" />
                      <Skeleton className="h-3 w-5/6" />
                      <Skeleton className="h-8 w-full mt-2" />
                    </div>
                  ))}
                </div>
              ) : null}

              {auditStatus === "completed" && violations.length === 0 ? (
                <div className="text-xs text-center py-6 flex flex-col items-center justify-center gap-3 text-emerald-400">
                  <CheckCircle2 size={36} style={{ color: "#10b981" }} />
                  <span style={{ marginTop: "12px", color: "#10b981" }}>No compliance infractions found in 3D model!</span>
                </div>
              ) : null}

              {auditStatus === "completed" && violations.map((v) => (
                <div
                  key={v.id}
                  role="button"
                  tabIndex={0}
                  aria-label={`Select ${v.severity} violation: ${v.category}`}
                  className={getViolationCardClass(v, selectedViolation === v.id)}
                  onClick={() => selectViolation(v.id)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      selectViolation(v.id);
                    }
                  }}
                >
                  <div className="flex justify-between items-center mb-2">
                    <span className={getSevBadgeClass(v.severity)}>{v.severity.toUpperCase()}</span>
                    <span className="text-[10px] font-mono text-text-muted">{v.standard_reference || "General"}</span>
                  </div>

                  <h5 className="text-xs font-bold text-text-primary mb-1.5">{v.category}</h5>
                  <p className="text-[11px] text-text-muted mb-2.5 leading-relaxed">{v.description}</p>

                  <div className="bg-bg-dark border border-border-color p-2 rounded text-[11px] text-text-primary leading-relaxed mb-2.5">
                    <strong>AI Fix Chip:</strong> {v.recommendation}
                  </div>

                  <div className="flex justify-between items-center text-[10px]">
                    <span className="text-text-muted">Confidence: {(v.confidence * 100).toFixed(0)}%</span>
                    <span className="text-accent-cyan hover:underline cursor-pointer">Highlight coordinates →</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
        )}
      </aside>
    </div>
  );
};
