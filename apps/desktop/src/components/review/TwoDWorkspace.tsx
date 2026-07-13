import React, { useState, useEffect, useRef } from "react";
import {
  ZoomIn,
  ZoomOut,
  Maximize,
  Trash2,
  Download,
  Map
} from "lucide-react";
import { useWorkspaceStore } from "../../stores/workspaceStore";
import { useReviewStore } from "../../stores/reviewStore";
import { useComplianceReportExport } from "../../hooks/useComplianceReportExport";
import { DrawingCanvas } from "./DrawingCanvas";
import { UploadZone } from "./UploadZone";
import { Minimap } from "./Minimap";
import { Button } from "../ui/Button";
import { TwoDLeftPanel } from "./TwoDLeftPanel";
import { TwoDRightPanel } from "./TwoDRightPanel";

interface TwoDWorkspaceProps {
  currentNav: string;
}

export const TwoDWorkspace: React.FC<TwoDWorkspaceProps> = ({ currentNav }) => {
  const oldDrawing = useWorkspaceStore(s => s.oldDrawing);
  const newDrawing = useWorkspaceStore(s => s.newDrawing);
  const oldLayers = useWorkspaceStore(s => s.oldLayers);
  const newLayers = useWorkspaceStore(s => s.newLayers);
  const complianceScore = useWorkspaceStore(s => s.complianceScore);
  const violations = useWorkspaceStore(s => s.violations);
  const oldUploadState = useWorkspaceStore(s => s.oldUploadState);
  const newUploadState = useWorkspaceStore(s => s.newUploadState);
  const oldUploadProgress = useWorkspaceStore(s => s.oldUploadProgress);
  const newUploadProgress = useWorkspaceStore(s => s.newUploadProgress);
  const oldFileName = useWorkspaceStore(s => s.oldFileName);
  const newFileName = useWorkspaceStore(s => s.newFileName);
  const oldFileSize = useWorkspaceStore(s => s.oldFileSize);
  const newFileSize = useWorkspaceStore(s => s.newFileSize);
  const oldError = useWorkspaceStore(s => s.oldError);
  const newError = useWorkspaceStore(s => s.newError);
  const compatibilityStatus = useWorkspaceStore(s => s.compatibilityStatus);
  const uploadDrawingFile = useWorkspaceStore(s => s.uploadDrawingFile);
  const clearUpload = useWorkspaceStore(s => s.clearUpload);
  const hasHydrated = useWorkspaceStore(s => s.hasHydrated);

  const viewportScaleRef = useRef(useReviewStore.getState().viewport.scale);
  const sliderRef = useRef<HTMLInputElement>(null);
  const setReviewViewport = useReviewStore(s => s.setViewport);
  const showMinimap = useReviewStore(s => s.showMinimap);
  const toggleMinimap = useReviewStore(s => s.toggleMinimap);

  // Keep slider value current without React re-renders
  useEffect(() => {
    const unsub = useReviewStore.subscribe((state) => {
      const scale = state.viewport.scale;
      if (scale !== viewportScaleRef.current) {
        viewportScaleRef.current = scale;
        if (sliderRef.current) sliderRef.current.value = String(scale);
      }
    });
    return unsub;
  }, []);

  const containerRefOld = useRef<HTMLDivElement>(null);
  const containerRefNew = useRef<HTMLDivElement>(null);
  const drawingCanvasRefOld = useRef<any>(null);
  const drawingCanvasRefNew = useRef<any>(null);
  const [oldSize, setOldSize] = useState({ width: 480, height: 400 });
  const [newSize, setNewSize] = useState({ width: 480, height: 400 });

  // Update sizes when containers resize
  useEffect(() => {
    const resizeObserver = new ResizeObserver((entries) => {
      for (let entry of entries) {
        if (entry.target === containerRefOld.current) {
          setOldSize({ width: entry.contentRect.width, height: entry.contentRect.height });
        }
        if (entry.target === containerRefNew.current) {
          setNewSize({ width: entry.contentRect.width, height: entry.contentRect.height });
        }
      }
    });

    if (containerRefOld.current) resizeObserver.observe(containerRefOld.current);
    if (containerRefNew.current) resizeObserver.observe(containerRefNew.current);

    return () => {
      resizeObserver.disconnect();
    };
  }, [oldDrawing, newDrawing]);

  const { exportToPDF } = useComplianceReportExport({
    oldDrawing,
    newDrawing,
    violations,
    complianceScore,
    canvasRefs: { old: drawingCanvasRefOld, new: drawingCanvasRefNew }
  });

  const getCompatibilityBadgeClass = (status: string) => {
    const base = "flex items-center gap-1.5 py-1 px-2.5 rounded-full text-sm font-extrabold tracking-wider uppercase bg-bg-dark border transition-all duration-300";
    switch (status.toLowerCase()) {
      case "idle": return `${base} text-zinc-400 border-zinc-700`;
      case "compatible": return `${base} text-emerald-400 bg-emerald-500/8 border-emerald-500/25 shadow-[0_0_10px_rgba(16,185,129,0.1)]`;
      case "mismatch": return `${base} text-orange-400 bg-orange-500/8 border-orange-500/25 animate-pulse`;
      case "unsupported": return `${base} text-red-400 bg-red-500/8 border-red-500/25`;
      default: return `${base} text-zinc-400 border-border-color`;
    }
  };

  const getCompatibilityDotClass = (status: string) => {
    const base = "w-1.5 h-1.5 rounded-full";
    switch (status.toLowerCase()) {
      case "idle": return `${base} bg-zinc-500`;
      case "compatible": return `${base} bg-emerald-500`;
      case "mismatch": return `${base} bg-orange-500`;
      case "unsupported": return `${base} bg-red-500`;
      default: return `${base} bg-zinc-500`;
    }
  };

  if (!hasHydrated) {
    return (
      <div className="flex items-center justify-center h-full w-full bg-bg-dark text-text-muted">
        <div className="flex flex-col items-center gap-3">
          <div className="spin-animation w-8 h-8 border-2 border-accent-cyan border-t-transparent rounded-full"></div>
          <span>Loading workspace state...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-grow h-full overflow-hidden min-w-0">
      <TwoDLeftPanel currentNav={currentNav} />

      {currentNav === "workspace" && (
        <div className="flex flex-grow h-full overflow-hidden min-w-0">
          <main className="flex-grow h-full min-h-0 min-w-0 flex flex-col p-5 overflow-hidden border-r border-border-color box-border">
            <div className="flex-grow bg-bg-sidebar border border-border-color rounded-xl flex flex-col overflow-hidden min-h-0 min-w-0 shadow-sm data-[theme=hc-dark]:shadow-md">
              <div className="flex items-center justify-between bg-bg-dark border-b border-border-color py-2 px-4 gap-3 shrink-0 w-full">
                <div style={{ display: "flex", alignItems: "center" }}>
                  <h3 className="text-sm font-bold flex items-center border-l-[3px] border-accent-cyan pl-2.5 text-text-primary m-0">
                    Stage 1: Drawing Pair Ingestion
                  </h3>
                </div>

                <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
                  <div className={getCompatibilityBadgeClass(compatibilityStatus)}>
                    <span className={getCompatibilityDotClass(compatibilityStatus)}></span>
                    <span>
                      {compatibilityStatus === "Idle" && "Awaiting Pair Ingestion"}
                      {compatibilityStatus === "Compatible" && `COMPATIBLE: ${oldDrawing?.file_name.split(".").pop()?.toUpperCase()} ↁE${newDrawing?.file_name.split(".").pop()?.toUpperCase()}`}
                      {compatibilityStatus === "Mismatch" && "FORMAT MISMATCH"}
                      {compatibilityStatus === "Unsupported" && "UNSUPPORTED EXTENSION"}
                    </span>
                  </div>

                  <div className="flex items-center gap-1.5">
                    <Button
                      variant="outline"
                      size="icon"
                      onClick={() => {
                        const vp = useReviewStore.getState().viewport;
                        setReviewViewport({ ...vp, scale: Math.min(25, vp.scale * 1.25) });
                      }}
                      title="Zoom In"
                    >
                      <ZoomIn size={20} />
                    </Button>
                    <input
                      ref={sliderRef}
                      type="range"
                      min="0.1"
                      max="25"
                      step="0.1"
                      defaultValue={String(viewportScaleRef.current)}
                      onChange={(e) => {
                        const vp = useReviewStore.getState().viewport;
                        setReviewViewport({ ...vp, scale: parseFloat(e.target.value) });
                      }}
                      className="w-24 accent-accent-cyan cursor-pointer mx-2"
                      title="Mouse Zoom Control"
                    />
                    <Button
                      variant="outline"
                      size="icon"
                      onClick={() => {
                        const vp = useReviewStore.getState().viewport;
                        setReviewViewport({ ...vp, scale: Math.max(0.1, vp.scale / 1.25) });
                      }}
                      title="Zoom Out"
                    >
                      <ZoomOut size={20} />
                    </Button>
                    <Button
                      variant="outline"
                      size="icon"
                      onClick={() => setReviewViewport({ x: 0, y: 0, scale: 1 })}
                      title="Reset Viewport"
                    >
                      <Maximize size={20} />
                    </Button>
                    <div className="w-px h-6 bg-border-color mx-1"></div>
                    <Button
                      variant={showMinimap ? "primary" : "outline"}
                      size="icon"
                      onClick={toggleMinimap}
                      title="Toggle Interactive Minimap"
                    >
                      <Map size={20} />
                    </Button>
                  </div>
                </div>
              </div>

              <div className="flex-grow min-h-0 min-w-0 flex overflow-hidden">
                {/* 1. LEFT CANVAS - REFERENCE DRAWING */}
                <div className="flex-1 flex flex-col border-r border-border-color h-full overflow-hidden relative">
                  <div className="flex justify-between items-center bg-bg-dark border-b border-border-color py-1.5 px-3 shrink-0">
                    <div className="text-sm font-bold text-text-primary uppercase tracking-wider">Original Drawing</div>
                    {oldDrawing && (
                      <div className="flex items-center gap-1.5 py-0.5 px-2.5 rounded bg-bg-dark border border-border-color text-sm text-text-primary transition-all duration-200 border-l-[3px] border-l-accent-cyan">
                        <span className="font-medium max-w-[180px] overflow-hidden text-ellipsis whitespace-nowrap" title={oldDrawing.file_name}>
                          {oldDrawing.file_name}
                        </span>
                        <Button variant="ghost" size="icon" className="h-5 w-5 text-zinc-500 hover:text-red-500" onClick={() => clearUpload("old")} title="Remove reference drawing">
                          <Trash2 size={10} />
                        </Button>
                      </div>
                    )}
                  </div>
                  <div className="flex-grow min-h-0 min-w-0 bg-bg-dark relative flex items-center justify-center overflow-hidden" ref={containerRefOld}>
                    {oldDrawing ? (
                      <div style={{ position: "absolute", top: 0, left: 0, width: "100%", height: "100%", overflow: "hidden" }}>
                        <DrawingCanvas
                          ref={drawingCanvasRefOld}
                          layers={oldLayers}
                          width={oldSize.width}
                          height={oldSize.height}
                          drawing={oldDrawing}
                        />
                        <Minimap 
                          drawing={oldDrawing} 
                          canvasWidth={oldSize.width} 
                          canvasHeight={oldSize.height} 
                        />
                      </div>
                    ) : (
                      <UploadZone
                        side="old"
                        uploadState={oldUploadState}
                        progress={oldUploadProgress}
                        fileName={oldFileName}
                        fileSize={oldFileSize}
                        error={oldError}
                        activeDrawing={oldDrawing}
                        uploadDrawingFile={uploadDrawingFile}
                        clearUpload={clearUpload}
                        currentNav={currentNav}
                      />
                    )}
                  </div>
                </div>

                {/* 2. RIGHT CANVAS - REVISION DRAWING */}
                <div className="flex-1 flex flex-col h-full overflow-hidden relative">
                  <div className="flex justify-between items-center bg-bg-dark border-b border-border-color py-1.5 px-3 shrink-0">
                    <div className="text-sm font-bold text-text-primary uppercase tracking-wider">KMTI Drawing</div>
                    {newDrawing && (
                      <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                        <div className="flex items-center gap-1.5 py-0.5 px-2.5 rounded bg-bg-dark border border-border-color text-sm text-text-primary transition-all duration-200 border-l-[3px] border-l-purple-500">
                          <span className="font-medium max-w-[180px] overflow-hidden text-ellipsis whitespace-nowrap" title={newDrawing.file_name}>
                            {newDrawing.file_name}
                          </span>
                          <Button variant="ghost" size="icon" className="h-5 w-5 text-zinc-500 hover:text-red-500" onClick={() => clearUpload("new")} title="Remove revision drawing">
                            <Trash2 size={10} />
                          </Button>
                        </div>
                        <Button
                          variant="outline"
                          size="sm"
                          className="h-7 text-xs border-accent-cyan/30 text-accent-cyan hover:bg-accent-cyan hover:text-zinc-950 gap-1.5"
                          onClick={exportToPDF}
                          title="Export drawing pair as PDF"
                        >
                          <Download size={12} />
                          <span>PDF</span>
                        </Button>
                      </div>
                    )}
                  </div>
                  <div className="flex-grow min-h-0 min-w-0 bg-bg-dark relative flex items-center justify-center overflow-hidden" ref={containerRefNew}>
                    {newDrawing ? (
                      <div style={{ position: "absolute", top: 0, left: 0, width: "100%", height: "100%", overflow: "hidden" }}>
                        <DrawingCanvas
                          ref={drawingCanvasRefNew}
                          layers={newLayers}
                          width={newSize.width}
                          height={newSize.height}
                          drawing={newDrawing}
                        />
                        <Minimap 
                          drawing={newDrawing} 
                          canvasWidth={newSize.width} 
                          canvasHeight={newSize.height} 
                        />
                      </div>
                    ) : (
                      <UploadZone
                        side="new"
                        uploadState={newUploadState}
                        progress={newUploadProgress}
                        fileName={newFileName}
                        fileSize={newFileSize}
                        error={newError}
                        activeDrawing={newDrawing}
                        uploadDrawingFile={uploadDrawingFile}
                        clearUpload={clearUpload}
                        currentNav={currentNav}
                      />
                    )}
                  </div>
                </div>
              </div>
            </div>
          </main>

          <TwoDRightPanel currentNav={currentNav} />
        </div>
      )}
    </div>
  );
};
