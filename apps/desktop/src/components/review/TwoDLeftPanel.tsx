import React from "react";
import { Play, Sparkles, File, ArrowRightLeft, Activity, CheckCircle2, CircleDashed } from "lucide-react";
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

  const {
    runPhysicalComparisonAI,
    aiScanProgress,
    aiChecklistResults,
    aiScanError,
    resetComparison
  } = usePhysicalComparison();

  if (!(currentNav === "workspace" && oldDrawing && newDrawing)) {
    return null;
  }

  return (
    <div className="flex flex-col w-full h-full overflow-y-auto overflow-x-hidden box-border bg-bg-sidebar relative">

      {/* Premium Header */}
      <div className="sticky top-0 z-20 flex items-center justify-between p-5 border-b border-white/5 bg-bg-sidebar/90 backdrop-blur-sm">
        <div className="flex items-center gap-3">
          <div className="relative flex items-center justify-center w-8 h-8 rounded-lg bg-accent-cyan/10 border border-accent-cyan/20">
            <Sparkles size={18} className="text-accent-cyan" />
          </div>
          <span className="text-sm font-bold tracking-widest text-zinc-100 uppercase">
            AI Comparison
          </span>
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
                  <File size={72} strokeWidth={1.5} className="text-zinc-400 -rotate-6" />
                  <span className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-[14px] font-bold text-zinc-300 tracking-tighter -rotate-6 mt-1.5">CAD</span>
                </div>
                <ArrowRightLeft size={32} strokeWidth={2} className="text-accent-cyan animate-pulse" />
                <div className="relative flex flex-col items-center">
                  <File size={72} strokeWidth={1.5} className="text-zinc-300 rotate-6" />
                  <span className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-[14px] font-bold text-zinc-200 tracking-tighter rotate-6 mt-1.5">CAD</span>
                </div>
              </div>
            </div>

            {/* Text Block */}
            <div className="flex flex-col items-center gap-2">
              <h3 className="text-3xl font-bold text-zinc-100 tracking-tight">
                Ready for Comparison
              </h3>
              <p className="text-[15px] text-zinc-400 max-w-[320px] leading-loose">
                Execute the AI Engine to analyze structural and metadata differences between the original and KMTI drawing.
              </p>
            </div>

            {/* Button */}
            <Button
              variant="primary"
              className="text-sm font-bold shadow-lg transition-transform hover:scale-105 active:scale-95"
              style={{ padding: '16px 40px', height: 'auto' }}
              onClick={runPhysicalComparisonAI}
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

          <div className="flex items-center gap-3 mb-10 border-b border-white/10 pb-5">
            <Activity size={24} className="text-accent-cyan animate-pulse" />
            <h4 className="text-sm font-bold text-zinc-100 uppercase tracking-widest">Analysis in Progress</h4>
          </div>

          <div className="flex flex-col gap-5">
            {[
              { id: "scanning_ref", label: "Scanning Original Drawing", activeSteps: ["scanning_ref", "extracting", "scanning_rev", "comparing"] },
              { id: "extracting", label: "Extracting Metadata", activeSteps: ["extracting", "scanning_rev", "comparing"] },
              { id: "scanning_rev", label: "Scanning KMTI Drawing", activeSteps: ["scanning_rev", "comparing"] },
              { id: "comparing", label: "Comparing Matches", activeSteps: ["comparing"] }
            ].map((step) => {
              const isActive = aiScanProgress === step.id;
              const isPast = step.activeSteps.includes(aiScanProgress) && !isActive;

              return (
                <div key={step.id} className={`flex items-center gap-4 p-4 rounded-lg bg-black/30 border transition-all duration-300 ${isActive ? 'border-accent-cyan/40 shadow-lg scale-[1.02]' : 'border-transparent'}`}>
                  <div className="flex-shrink-0">
                    {isPast ? (
                      <CheckCircle2 size={24} className="text-emerald-500" />
                    ) : isActive ? (
                      <CircleDashed size={24} className="text-accent-cyan animate-spin" />
                    ) : (
                      <div className="w-6 h-6 rounded-full border-2 border-white/10"></div>
                    )}
                  </div>
                  <div className="flex-grow flex justify-between items-center">
                    <span className={`text-sm ${isActive ? 'text-zinc-100 font-bold' : isPast ? 'text-zinc-400' : 'text-zinc-600'}`}>
                      {step.label}
                    </span>
                    {isActive && <span className="text-xs font-semibold text-accent-cyan animate-pulse">Processing...</span>}
                  </div>
                </div>
              );
            })}
          </div>

          <div className="mt-12">
            <div className="flex justify-between text-xs text-zinc-400 font-medium mb-3">
              <span className="uppercase tracking-widest">Overall Progress</span>
              <span>
                {aiScanProgress === "scanning_ref" ? "25%" : aiScanProgress === "extracting" ? "50%" : aiScanProgress === "scanning_rev" ? "75%" : "95%"}
              </span>
            </div>
            <div className="w-full h-2.5 bg-black/60 rounded-full overflow-hidden border border-white/5">
              <div
                className="h-full bg-accent-cyan shadow-[0_0_10px_rgba(0,229,255,0.5)]"
                style={{
                  width: aiScanProgress === "scanning_ref" ? "25%" : aiScanProgress === "extracting" ? "50%" : aiScanProgress === "scanning_rev" ? "75%" : "95%",
                  transition: "width 0.4s ease-out"
                }}
              ></div>
            </div>
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
