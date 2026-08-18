import React from "react";
import { Play, Sparkles, File, ArrowRightLeft, Activity, CheckCircle2, CircleDashed, RotateCw, ScanText } from "lucide-react";
import { useWorkspaceStore } from "../../stores/workspaceStore";
import { useRoomStore } from "../../stores/roomStore";
import { isZoneReviewConfirmed, isZoneReviewGrandfathered } from "../../utils/zoneGate";
import { ChecklistPanel } from "./ChecklistPanel";
import { ManualMarkingList } from "./ManualMarkingList";
import { usePhysicalComparison } from "../../hooks/usePhysicalComparison";
import { getComparisonStages, getComparisonMethodLabel } from "../../utils/comparisonStages";
import { Button } from "../ui/Button";
import { useIsManualCheckRoom } from "../../hooks/useManualCheckRoom";

interface TwoDLeftPanelProps {
  currentNav: string;
}

export const TwoDLeftPanel: React.FC<TwoDLeftPanelProps> = ({ currentNav }) => {
  const oldDrawing = useWorkspaceStore(s => s.oldDrawing);
  const newDrawing = useWorkspaceStore(s => s.newDrawing);
  const activeRoom = useRoomStore(s => s.activeRoom);
  const isManualCheckModePanel = useIsManualCheckRoom();

  const {
    runPhysicalComparisonAI,
    aiScanProgress,
    aiChecklistResults,
    aiScanError,
    resetComparison
  } = usePhysicalComparison();

  // Stage list/labels describe what the backend pipeline actually does (see
  // utils/comparisonStages.ts) rather than a fixed 4-step sequence written for a generic
  // AI call. Still looked up by comparison_method: there is only one now (ADR-006), but a
  // room created before the removal can carry an old string, and the lookup falls back.
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
    <div className="tlp-root flex flex-col w-full h-full overflow-y-auto overflow-x-hidden box-border bg-bg-sidebar relative">
      {/* This panel is a flexlayout tabset the user drags, with a 220px floor and a default
          weight of 15 against siblings weighing 50+50 -- so its real share is ~12%, and none of
          the layouts below can assume a comfortable column. Tailwind's sm:/md: breakpoints are
          useless here because they measure the window, not the panel; the container query does. */}
      <style>{`
        .tlp-root { container-type: inline-size; }
        @container (max-width: 340px) {
          .tlp-header { padding: 10px 12px; }
          .tlp-title { font-size: 11px; letter-spacing: 0.08em; }
          .tlp-idle { padding: 20px 14px; }
          .tlp-idle-stack { gap: 20px; }
          .tlp-idle-icons { gap: 12px; }
          .tlp-idle-heading { font-size: 1.15rem; }
          .tlp-idle-body { font-size: 12px; line-height: 1.6; }
          /* Overrides lucide's width/height presentation attributes. Two 72px sheets plus the
             arrow and their gaps exceed the panel's 220px floor on their own. */
          .tlp-doc-icon { width: 50px; height: 50px; }
          .tlp-arrow-icon { width: 22px; height: 22px; }
          .tlp-scan { padding: 16px 12px; }
          .tlp-scan-head { margin-bottom: 20px; padding-bottom: 12px; }
          .tlp-stage { padding: 10px; gap: 10px; }
          .tlp-progress { margin-top: 24px; }
          .tlp-error { margin: 10px; padding: 14px; }
        }
      `}</style>

      {/*
        A manual-check room replaces this panel outright — header, Run/Re-test controls,
        progress stages and checklist. Gating only the checklist would leave an engineer
        looking at a "Run AI Comparison" button in a room whose whole purpose is that no
        engine runs, and one accidental click would put engine findings in front of someone
        whose independence is the only reason their markings are worth collecting.
      */}
      {isManualCheckModePanel ? (
        <ManualMarkingList />
      ) : (
      <>
      {/* Premium Desktop Header */}
      <div className="tlp-header sticky top-0 z-20 flex flex-wrap items-center justify-between gap-y-1.5 gap-x-2 p-2.5 border-b border-border-color bg-bg-sidebar select-none">
        <div className="flex items-center gap-2 min-w-0 flex-1">
          <div className="relative flex items-center justify-center w-6 h-6 shrink-0 rounded-sm bg-accent-cyan/10 border border-accent-cyan/20">
            <Sparkles size={14} className="text-accent-cyan" />
          </div>
          <span className="tlp-title text-xs font-bold tracking-wider text-text-primary uppercase truncate">
            AI Comparison
          </span>
        </div>

        {/* Re-test Action Buttons */}
        <div className="flex items-center gap-1 shrink-0">
          <Button
            variant="ghost"
            size="sm"
            disabled={isScanning}
            className="h-6 px-2 text-[11px] font-semibold text-accent-cyan border border-accent-cyan/30 hover:bg-accent-cyan/10 hover:border-accent-cyan/60 disabled:opacity-50 disabled:pointer-events-none gap-1 rounded-sm transition-all"
            onClick={() => {
              resetComparison();
              runPhysicalComparisonAI(true);
            }}
            title="Re-run the comparison fresh (bypasses the cached result). Reuses the cached title-block OCR."
          >
            <RotateCw size={11} className={isScanning ? "animate-spin" : ""} />
            <span>Re-test</span>
          </Button>
          <Button
            variant="ghost"
            size="sm"
            disabled={isScanning}
            className="h-6 w-6 p-0 justify-center text-text-muted border border-border-color hover:text-accent-cyan hover:border-accent-cyan/60 disabled:opacity-50 disabled:pointer-events-none rounded-sm transition-all"
            onClick={() => {
              resetComparison();
              runPhysicalComparisonAI(true, true);
            }}
            title="Re-test AND re-read the title block with OCR"
            aria-label="Re-test and re-scan title-block OCR"
          >
            <ScanText size={11} className={isScanning ? "animate-pulse" : ""} />
          </Button>
        </div>
      </div>

      {/* Idle / Empty State */}
      {aiScanProgress === "idle" && (
        <div className="tlp-idle flex-grow flex flex-col items-center justify-center p-10 text-center relative min-w-0">
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-64 h-64 bg-accent-cyan/5 rounded-full blur-[80px] pointer-events-none"></div>

          <div className="tlp-idle-stack flex flex-col items-center gap-8 relative z-10 w-full min-w-0">

            {/* Icon Block */}
            <div className="relative max-w-full">
              <div className="absolute inset-0 bg-accent-cyan/10 blur-3xl rounded-full scale-125"></div>
              <div className="tlp-idle-icons relative flex items-center justify-center gap-10">
                <div className="relative flex flex-col items-center">
                  <File size={72} strokeWidth={1.5} className="tlp-doc-icon text-text-muted -rotate-6" />
                  <span className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-[14px] font-bold text-text-secondary tracking-tighter -rotate-6 mt-1.5">CAD</span>
                </div>
                <ArrowRightLeft size={32} strokeWidth={2} className="tlp-arrow-icon text-accent-cyan animate-pulse" />
                <div className="relative flex flex-col items-center">
                  <File size={72} strokeWidth={1.5} className="tlp-doc-icon text-text-muted rotate-6" />
                  <span className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-[14px] font-bold text-text-secondary tracking-tighter rotate-6 mt-1.5">CAD</span>
                </div>
              </div>
            </div>

            {/* Text Block. max-w-full, not max-w-[320px] -- that cap was wider than the panel
                itself at its default share, so it constrained nothing and the copy ran to the
                clipped edge. */}
            <div className="flex flex-col items-center gap-2 w-full min-w-0">
              <h3 className="tlp-idle-heading text-3xl font-bold text-text-primary tracking-tight text-balance">
                Ready for Comparison
              </h3>
              <p className="tlp-idle-body text-[15px] text-text-muted max-w-[320px] w-full leading-loose">
                Execute the AI Engine to analyze structural and metadata differences between the original and KMTI drawing.
              </p>
            </div>

            {/* Button */}
            <Button
              variant="primary"
              className="text-sm font-bold shadow-lg transition-transform hover:scale-105 active:scale-95 w-full max-w-[260px]"
              style={{ padding: '16px 20px', height: 'auto' }}
              onClick={() => runPhysicalComparisonAI()}
            >
              <Play size={18} className="mr-3 shrink-0" />
              START COMPARISON
            </Button>

          </div>
        </div>
      )}

      {/* Loading / Scanning State */}
      {aiScanProgress !== "idle" && aiScanProgress !== "completed" && (
        <div className="tlp-scan flex-grow flex flex-col p-8 relative min-w-0">

          <div className="tlp-scan-head flex items-start gap-3 mb-10 border-b border-border-color pb-5 min-w-0">
            <Activity size={24} className="text-accent-cyan animate-pulse shrink-0" />
            <h4 className="text-sm font-bold text-text-primary uppercase tracking-widest min-w-0">
              Analysis in Progress <span className="text-accent-cyan/70 normal-case font-semibold">&middot; {methodLabel}</span>
            </h4>
          </div>

          <div className="flex flex-col gap-5">
            {stages.map((step, idx) => {
              const isActive = aiScanProgress === step.id;
              const isPast = currentStageIndex > idx;

              return (
                <div key={step.id} className={`tlp-stage flex items-center gap-4 p-4 rounded-lg bg-bg-dark border transition-all duration-300 min-w-0 ${isActive ? 'border-accent-cyan/40 shadow-lg scale-[1.02]' : 'border-transparent'}`}>
                  <div className="flex-shrink-0">
                    {isPast ? (
                      <CheckCircle2 size={24} className="text-emerald-500" />
                    ) : isActive ? (
                      <CircleDashed size={24} className="text-accent-cyan animate-spin" />
                    ) : (
                      <div className="w-6 h-6 rounded-full border-2 border-border-color"></div>
                    )}
                  </div>
                  {/* Wraps: at the panel's floor the stage label and "Processing..." cannot share
                      a line, and the tag would otherwise be pushed past the clipped edge. */}
                  <div className="flex-grow flex flex-wrap justify-between items-center gap-x-2 gap-y-1 min-w-0">
                    <span className={`text-sm min-w-0 ${isActive ? 'text-text-primary font-bold' : isPast ? 'text-text-secondary' : 'text-text-muted'}`}>
                      {step.label}
                    </span>
                    {isActive && <span className="text-xs font-semibold text-accent-cyan animate-pulse shrink-0">Processing...</span>}
                  </div>
                </div>
              );
            })}
          </div>

          <div className="tlp-progress mt-12">
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
        <div className="tlp-error m-6 flex gap-4 items-start p-6 bg-red-500/10 border border-red-500/20 rounded-xl text-red-400 relative overflow-hidden min-w-0">
          <div className="absolute top-0 left-0 w-1.5 h-full bg-red-500"></div>
          <div className="flex-grow min-w-0 break-words">
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
            className="h-8 w-8 shrink-0 text-red-400/50 hover:text-red-400 p-0 hover:bg-red-500/10 rounded-full"
          >✕</Button>
        </div>
      )}

      {aiScanProgress === "completed" && (
        <ChecklistPanel aiChecklistResults={aiChecklistResults} />
      )}
      </>
      )}
    </div>
  );
};
