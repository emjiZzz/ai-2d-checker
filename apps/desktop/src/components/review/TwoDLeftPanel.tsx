import React, { useState, useEffect } from "react";
import { Play, Sparkles, ChevronRight, ChevronLeft } from "lucide-react";
import { useWorkspaceStore } from "../../stores/workspaceStore";
import { ChecklistPanel } from "./ChecklistPanel";
import { usePhysicalComparison } from "../../hooks/usePhysicalComparison";
import { Button } from "../ui/Button";

interface TwoDLeftPanelProps {
  currentNav: string;
}

export const TwoDLeftPanel: React.FC<TwoDLeftPanelProps> = ({ currentNav }) => {
  const oldDrawing = useWorkspaceStore(s => s.oldDrawing);
  const newDrawing = useWorkspaceStore(s => s.newDrawing);

  const [isLeftPanelCollapsed, setIsLeftPanelCollapsed] = useState(false);
  const [leftSidebarWidth, setLeftSidebarWidth] = useState(400);
  const [isResizingLeft, setIsResizingLeft] = useState(false);

  const {
    runPhysicalComparisonAI,
    aiScanProgress,
    aiChecklistResults,
    aiScanError,
    resetComparison
  } = usePhysicalComparison();

  // Removed aggressive resetComparison useEffect to prevent wiping restored state

  // Resize Left
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (isResizingLeft) {
        const newWidth = Math.max(250, Math.min(600, e.clientX));
        setLeftSidebarWidth(newWidth);
      }
    };
    const handleMouseUp = () => {
      setIsResizingLeft(false);
    };
    if (isResizingLeft) {
      window.addEventListener("mousemove", handleMouseMove);
      window.addEventListener("mouseup", handleMouseUp);
    }
    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
  }, [isResizingLeft]);


  if (!(currentNav === "workspace" && oldDrawing && newDrawing)) {
    return null;
  }

  return (
    <>
      {/* 1. LEFT SIDEBAR OR INSTRUCTIONS PANEL */}
      <aside
        className={`bg-bg-sidebar flex flex-col h-full overflow-visible box-border shrink-0 relative border-r z-20 ${
          !isLeftPanelCollapsed ? "border-border-color" : "border-transparent"
        } ${isResizingLeft ? "" : "transition-all duration-300 cubic-out"}`}
        style={{
          width: isLeftPanelCollapsed ? '0px' : `${leftSidebarWidth}px`,
          minWidth: isLeftPanelCollapsed ? '0px' : `${leftSidebarWidth}px`,
        }}
      >
        <Button
          variant="ghost"
          className="absolute top-1/2 -translate-y-1/2 w-4.5 h-12 bg-zinc-900/85 backdrop-blur-sm border border-border-color border-l-0 rounded-r-lg flex items-center justify-center cursor-pointer text-text-muted z-50 transition-all duration-200 shadow-md right-[-18px] hover:right-[-24px] hover:text-accent-cyan hover:bg-blue-600/15 hover:border-accent-cyan hover:shadow-cyan-500/25 p-0"
          onClick={() => setIsLeftPanelCollapsed(!isLeftPanelCollapsed)}
          title={isLeftPanelCollapsed ? "Expand Drawings Comparison Results" : "Collapse Drawings Comparison Results"}
        >
          {isLeftPanelCollapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
        </Button>
        <div
          className="flex flex-col w-full flex-1 min-h-0 p-4 overflow-y-auto overflow-x-hidden box-border transition-opacity duration-200"
          style={{
            opacity: isLeftPanelCollapsed ? 0 : 1,
            pointerEvents: isLeftPanelCollapsed ? "none" : "auto",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "16px", paddingBottom: "12px", borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <Sparkles size={16} style={{ color: "var(--accent-cyan)", filter: "drop-shadow(0 0 4px rgba(0,229,255,0.4))" }} />
              <span style={{ fontSize: "0.85rem", fontWeight: 500, letterSpacing: "0.05em", color: "#e4e4e7" }}>
                DRAWINGS COMPARISON RESULTS
              </span>
            </div>
            {aiScanProgress === "idle" && (
              <div className="flex gap-1.5 items-center">
                <Button
                  variant="primary"
                  className="gap-2 font-bold bg-gradient-to-r from-accent-cyan to-indigo-400 text-black hover:shadow-[0_0_12px_rgba(0,229,255,0.35)]"
                  onClick={runPhysicalComparisonAI}
                >
                  <Play size={13} fill="currentColor" />
                  RUN COMPARISON
                </Button>
              </div>
            )}
          </div>

          {aiScanProgress !== "idle" && aiScanProgress !== "completed" && (
            <div style={{ display: "flex", flexDirection: "column", gap: "12px", margin: "16px 0" }}>
              <div className="loader spin-animation" style={{ alignSelf: "center", marginBottom: "8px" }}></div>
              <div style={{ display: "flex", flexDirection: "column", gap: "6px", fontSize: "0.65rem", fontWeight: 600, color: "var(--text-muted)", background: "rgba(255,255,255,0.02)", padding: "10px", borderRadius: "6px", border: "1px solid rgba(255,255,255,0.04)" }}>
                <div style={{ display: "flex", justifyContent: "space-between", color: aiScanProgress === "scanning_ref" || aiScanProgress === "extracting" || aiScanProgress === "scanning_rev" || aiScanProgress === "comparing" ? "var(--accent-cyan)" : "inherit" }}>
                  <span>1. SCAN ORIGINAL</span>
                  {aiScanProgress === "scanning_ref" && <span style={{ fontSize: "0.6rem" }}>SCANNING...</span>}
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", color: aiScanProgress === "extracting" || aiScanProgress === "scanning_rev" || aiScanProgress === "comparing" ? "var(--accent-cyan)" : "inherit" }}>
                  <span>2. EXTRACT DATA</span>
                  {aiScanProgress === "extracting" && <span style={{ fontSize: "0.6rem" }}>EXTRACTING...</span>}
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", color: aiScanProgress === "scanning_rev" || aiScanProgress === "comparing" ? "var(--accent-cyan)" : "inherit" }}>
                  <span>3. SCAN KMTI</span>
                  {aiScanProgress === "scanning_rev" && <span style={{ fontSize: "0.6rem" }}>SCANNING...</span>}
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", color: aiScanProgress === "comparing" ? "var(--accent-cyan)" : "inherit" }}>
                  <span>4. COMPARE MATCHES</span>
                  {aiScanProgress === "comparing" && <span style={{ fontSize: "0.6rem" }}>COMPARING...</span>}
                </div>
              </div>
              <div style={{ width: "100%", height: "4px", background: "rgba(255,255,255,0.1)", borderRadius: "2px", overflow: "hidden" }}>
                <div style={{
                  height: "100%",
                  background: "var(--accent-cyan)",
                  width: aiScanProgress === "scanning_ref" ? "25%" : aiScanProgress === "extracting" ? "50%" : aiScanProgress === "scanning_rev" ? "75%" : "100%",
                  transition: "width 0.5s ease"
                }}></div>
              </div>
            </div>
          )}

          {aiScanError && (
            <div style={{ display: "flex", gap: "10px", alignItems: "flex-start", padding: "12px", background: "rgba(239,68,68,0.06)", border: "1px solid rgba(239,68,68,0.2)", borderRadius: "6px", color: "#ef4444", marginBottom: "16px" }}>
              <div style={{ flexGrow: 1 }}>
                <div style={{ fontSize: "0.75rem", fontWeight: 700, letterSpacing: "0.05em", marginBottom: "4px" }}>
                  AI COMPARISON FAILED
                </div>
                <div style={{ fontSize: "0.65rem", color: "#a1a1aa", lineHeight: 1.5 }}>
                  {aiScanError}
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => { resetComparison(); runPhysicalComparisonAI(); }}
                  className="mt-2 text-amber-500 border-amber-500/40 bg-amber-500/10 hover:bg-amber-500/20"
                >
                  ↺ RETRY
                </Button>
              </div>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => resetComparison()}
                className="h-6 w-6 text-zinc-500 hover:text-zinc-100 p-0"
              >✕</Button>
            </div>
          )}

          {aiScanProgress === "completed" && (
            <ChecklistPanel aiChecklistResults={aiChecklistResults} />
          )}
        </div>
      </aside>

      <div
        className={`left-resize-divider ${isResizingLeft ? 'active' : ''}`}
        onMouseDown={(e) => {
          e.preventDefault();
          setIsResizingLeft(true);
        }}
        style={{
          width: '6px',
          cursor: 'ew-resize',
          background: isResizingLeft ? 'rgba(0, 229, 255, 0.4)' : 'rgba(255, 255, 255, 0.05)',
          borderLeft: '1px solid rgba(255, 255, 255, 0.05)',
          borderRight: '1px solid rgba(255, 255, 255, 0.05)',
          zIndex: 30,
          transition: 'background 0.2s ease',
          flexShrink: 0
        }}
      />
    </>
  );
};
