import React from "react";
import { Play, Sparkles, File, ArrowRightLeft, Activity, CheckCircle2, CircleDashed, RotateCw, ScanText } from "lucide-react";
import { useWorkspaceStore } from "../../stores/workspaceStore";
import { useRoomStore } from "../../stores/roomStore";
import { isZoneReviewConfirmed, isZoneReviewGrandfathered } from "../../utils/zoneGate";
import { ChecklistPanel } from "./ChecklistPanel";
import { usePhysicalComparison } from "../../hooks/usePhysicalComparison";
import { getComparisonStages, getComparisonMethodLabel } from "../../utils/comparisonStages";
import { Button } from "../ui/Button";

interface TwoDLeftPanelProps {
  currentNav: string;
}

export const TwoDLeftPanel: React.FC<TwoDLeftPanelProps> = ({ currentNav }) => {
  const oldDrawing = useWorkspaceStore(s => s.oldDrawing);
  const newDrawing = useWorkspaceStore(s => s.newDrawing);
  const activeRoom = useRoomStore(s => s.activeRoom);

  const {
    runPhysicalComparisonAI,
    aiScanProgress,
    aiChecklistResults,
    aiScanError,
    resetComparison
  } = usePhysicalComparison();

  // Stage list/labels match whichever comparison_method this Room actually runs (see
  // utils/comparisonStages.ts) — no longer a fixed 4-step sequence written for one
  // generic AI call that doesn't describe what hybrid, rag, etc. each actually do.
  const stages = getComparisonStages(activeRoom?.comparison_method);
  const methodLabel = getComparisonMethodLabel(activeRoom?.comparison_method);
  const aiScanProgressPct = useWorkspaceStore(s => s.aiScanProgressPct);
  const currentStageIndex = stages.findIndex(s => s.id === aiScanProgress);
  const progressPct = aiScanProgressPct > 0
    ? aiScanProgressPct
    : currentStageIndex >= 0
    ? Math.round(((currentStageIndex + 1) / stages.length) * 95)
    : 5;

  const isScanning = aiScanProgress !== "idle" && aiScanProgress !== "completed";

  if (!(currentNav === "workspace" && oldDrawing && newDrawing)) {
    return null;
  }

  // Defence in depth. The tab should not exist at all before the zone review is confirmed
  // (TwoDWorkspace owns that), but a layout persisted by an earlier session — or a floated
  // tab — could resurrect it. Keeping the body empty means the gate cannot be bypassed into
  // START COMPARISON even if the tab leaks.
  if (
    !isZoneReviewConfirmed(activeRoom, oldDrawing.id, newDrawing.id) &&
    !isZoneReviewGrandfathered(activeRoom)
  ) {
    return null;
  }

  return (
    <div className="flex flex-col w-full h-full overflow-y-auto overflow-x-hidden box-border bg-bg-sidebar relative">

      {/* Premium Header */}
      <div className="sticky top-0 z-20 flex items-center justify-between p-5 border-b border-border-color bg-bg-sidebar/90 backdrop-blur-sm">
        <div className="flex items-center gap-3">
          <div className="relative flex items-center justify-center w-8 h-8 rounded-lg bg-accent-cyan/10 border border-accent-cyan/20">
            <Sparkles size={18} className="text-accent-cyan" />
          </div>
          <span className="text-sm font-bold tracking-widest text-text-primary uppercase">
            AI Comparison
          </span>
        </div>

        {/* Re-test Action Buttons */}
        <div className="flex items-center gap-1.5">
          <Button
            variant="ghost"
            size="sm"
            disabled={isScanning}
            className="h-8 px-3 text-xs font-semibold text-accent-cyan border border-accent-cyan/30 hover:bg-accent-cyan/10 hover:border-accent-cyan/60 disabled:opacity-50 disabled:pointer-events-none gap-1.5 rounded-lg transition-all"
            onClick={() => {
              resetComparison();
              runPhysicalComparisonAI(true);
            }}
            title="Re-run the comparison fresh (bypasses the cached result). Reuses the cached title-block OCR."
          >
            <RotateCw size={13} className={isScanning ? "animate-spin" : ""} />
            <span>Re-test</span>
          </Button>
          {/* Deep variant: also re-reads the title-block crop with Gemini. Separate from
              Re-test because OCR is a paid per-drawing call and should not fire every time. */}
          <Button
            variant="ghost"
            size="sm"
            disabled={isScanning}
            className="h-8 w-8 p-0 justify-center text-text-muted border border-border-color hover:text-accent-cyan hover:border-accent-cyan/60 disabled:opacity-50 disabled:pointer-events-none rounded-lg transition-all"
            onClick={() => {
              resetComparison();
              runPhysicalComparisonAI(true, true);
            }}
            title="Re-test AND re-read the title block with OCR (slower — one Gemini call per drawing). Use when the title-block reading looks stale, not just the comparison."
            aria-label="Re-test and re-scan title-block OCR"
          >
            <ScanText size={13} className={isScanning ? "animate-pulse" : ""} />
          </Button>
        </div>
      </div>

      {/* Idle / Empty State */}
      {aiScanProgress === "idle" && (
        <div className="flex-grow flex flex-col items-center justify-center p-10 text-center relative">
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-64 h-64 bg-accent-cyan/5 rounded-full blur-[80px] pointer-events-none"></div>

          <div className="flex flex-col items-center gap-8 relative z-10">

            {/* Icon Block */}
            <div className="relative">
              <div className="absolute inset-0 bg-accent-cyan/10 blur-3xl rounded-full scale-125"></div>
              <div className="relative flex items-center justify-center gap-10">
                <div className="relative flex flex-col items-center">
                  <File size={72} strokeWidth={1.5} className="text-text-muted -rotate-6" />
                  <span className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-[14px] font-bold text-text-secondary tracking-tighter -rotate-6 mt-1.5">CAD</span>
                </div>
                <ArrowRightLeft size={32} strokeWidth={2} className="text-accent-cyan animate-pulse" />
                <div className="relative flex flex-col items-center">
                  <File size={72} strokeWidth={1.5} className="text-text-muted rotate-6" />
                  <span className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-[14px] font-bold text-text-secondary tracking-tighter rotate-6 mt-1.5">CAD</span>
                </div>
              </div>
            </div>

            {/* Text Block */}
            <div className="flex flex-col items-center gap-2">
              <h3 className="text-3xl font-bold text-text-primary tracking-tight">
                Ready for Comparison
              </h3>
              <p className="text-[15px] text-text-muted max-w-[320px] leading-loose">
                Execute the AI Engine to analyze structural and metadata differences between the original and KMTI drawing.
              </p>
            </div>

            {/* Button */}
            <Button
              variant="primary"
              className="text-sm font-bold shadow-lg transition-transform hover:scale-105 active:scale-95"
              style={{ padding: '16px 40px', height: 'auto' }}
              onClick={() => runPhysicalComparisonAI()}
            >
              <Play size={18} className="mr-3" />
              START COMPARISON
            </Button>

          </div>
        </div>
      )}

      {/* Loading / Scanning State */}
      {aiScanProgress !== "idle" && aiScanProgress !== "completed" && (
        <div className="flex-grow flex flex-col p-8 relative">

          <div className="flex items-center gap-3 mb-10 border-b border-border-color pb-5">
            <Activity size={24} className="text-accent-cyan animate-pulse" />
            <h4 className="text-sm font-bold text-text-primary uppercase tracking-widest">
              Analysis in Progress <span className="text-accent-cyan/70 normal-case font-semibold">&middot; {methodLabel}</span>
            </h4>
          </div>

          <div className="flex flex-col gap-5">
            {stages.map((step, idx) => {
              const isActive = aiScanProgress === step.id;
              const isPast = currentStageIndex > idx;

              return (
                <div key={step.id} className={`flex items-center gap-4 p-4 rounded-lg bg-bg-dark border transition-all duration-300 ${isActive ? 'border-accent-cyan/40 shadow-lg scale-[1.02]' : 'border-transparent'}`}>
                  <div className="flex-shrink-0">
                    {isPast ? (
                      <CheckCircle2 size={24} className="text-emerald-500" />
                    ) : isActive ? (
                      <CircleDashed size={24} className="text-accent-cyan animate-spin" />
                    ) : (
                      <div className="w-6 h-6 rounded-full border-2 border-border-color"></div>
                    )}
                  </div>
                  <div className="flex-grow flex justify-between items-center">
                    <span className={`text-sm ${isActive ? 'text-text-primary font-bold' : isPast ? 'text-text-secondary' : 'text-text-muted'}`}>
                      {step.label}
                    </span>
                    {isActive && <span className="text-xs font-semibold text-accent-cyan animate-pulse">Processing...</span>}
                  </div>
                </div>
              );
            })}
          </div>

          <div className="mt-12">
            <div className="flex justify-between text-xs text-text-muted font-medium mb-3">
              <span className="uppercase tracking-widest">Overall Progress</span>
              <span>{progressPct}%</span>
            </div>
            <div className="w-full h-2.5 bg-bg-dark rounded-full overflow-hidden border border-border-color">
              <div
                className="h-full bg-accent-cyan shadow-[0_0_10px_rgba(0,229,255,0.5)]"
                style={{
                  width: `${progressPct}%`,
                  transition: "width 0.4s ease-out"
                }}
              ></div>
            </div>
            <p className="mt-3 text-[11px] text-accent-cyan/80 font-medium leading-relaxed">
              Real-time analysis progress streamed live from the backend.
            </p>
          </div>
        </div>
      )}

      {/* Error State */}
      {aiScanError && (
        <div className="m-6 flex gap-4 items-start p-6 bg-red-500/10 border border-red-500/20 rounded-xl text-red-400 relative overflow-hidden">
          <div className="absolute top-0 left-0 w-1.5 h-full bg-red-500"></div>
          <div className="flex-grow">
            <div className="text-sm font-bold tracking-widest mb-2">
              ANALYSIS FAILED
            </div>
            <div className="text-sm text-red-400/80 leading-relaxed mb-4">
              {aiScanError}
            </div>
            <Button
              variant="outline"
              size="lg"
              onClick={() => { resetComparison(); runPhysicalComparisonAI(); }}
              className="text-red-400 border-red-500/30 bg-red-500/10 hover:bg-red-500/20 h-10 text-sm font-bold gap-2"
            >
              <span>↺</span> RETRY SCAN
            </Button>
          </div>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => resetComparison()}
            className="h-8 w-8 text-red-400/50 hover:text-red-400 p-0 hover:bg-red-500/10 rounded-full"
          >✕</Button>
        </div>
      )}

      {/* Completed State */}
      {aiScanProgress === "completed" && (
        <ChecklistPanel aiChecklistResults={aiChecklistResults} />
      )}
    </div>
  );
};
