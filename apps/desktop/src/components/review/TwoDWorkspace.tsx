import React, { useState, useEffect, useRef } from "react";
import { Maximize, Download, Map, MoreVertical, Check, Activity, Grid } from "lucide-react";
import { Layout, Model, TabNode, IJsonModel, Action, Actions, DockLocation } from 'flexlayout-react';
import 'flexlayout-react/style/dark.css';

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

const OriginalDrawingPanel = ({ canvasRef, currentNav }: { canvasRef: React.RefObject<any>, currentNav: string }) => {
  const drawing = useWorkspaceStore(s => s.oldDrawing);
  const layers = useWorkspaceStore(s => s.oldLayers);
  const uploadState = useWorkspaceStore(s => s.oldUploadState);
  const progress = useWorkspaceStore(s => s.oldUploadProgress);
  const fileName = useWorkspaceStore(s => s.oldFileName);
  const fileSize = useWorkspaceStore(s => s.oldFileSize);
  const error = useWorkspaceStore(s => s.oldError);
  const uploadDrawingFile = useWorkspaceStore(s => s.uploadDrawingFile);
  const clearUpload = useWorkspaceStore(s => s.clearUpload);

  const containerRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 480, height: 400 });

  useEffect(() => {
    const resizeObserver = new ResizeObserver((entries) => {
      for (let entry of entries) {
        const newW = entry.contentRect.width;
        const newH = entry.contentRect.height;
        setSize((prev) => {
          if (Math.abs(prev.width - newW) > 2 || Math.abs(prev.height - newH) > 2) {
            return { width: newW, height: newH };
          }
          return prev;
        });
      }
    });
    if (containerRef.current) resizeObserver.observe(containerRef.current);
    return () => resizeObserver.disconnect();
  }, []);

  return (
    <div className="flex flex-col h-full overflow-hidden relative bg-bg-dark w-full">
      <div className="flex-grow min-h-0 min-w-0 relative flex items-center justify-center overflow-hidden" ref={containerRef}>
        {drawing ? (
          <div style={{ position: "absolute", top: 0, left: 0, width: "100%", height: "100%", overflow: "hidden" }}>
            <DrawingCanvas
              ref={canvasRef}
              layers={layers}
              width={size.width}
              height={size.height}
              drawing={drawing}
            />
            <Minimap 
              drawing={drawing} 
              canvasWidth={size.width} 
              canvasHeight={size.height} 
            />
          </div>
        ) : (
          <UploadZone
            side="old"
            uploadState={uploadState}
            progress={progress}
            fileName={fileName}
            fileSize={fileSize}
            error={error}
            activeDrawing={drawing}
            uploadDrawingFile={uploadDrawingFile}
            clearUpload={clearUpload}
            currentNav={currentNav}
          />
        )}
      </div>
    </div>
  );
};

const KMTIDrawingPanel = ({ canvasRef, currentNav }: { canvasRef: React.RefObject<any>, currentNav: string }) => {
  const drawing = useWorkspaceStore(s => s.newDrawing);
  const layers = useWorkspaceStore(s => s.newLayers);
  const uploadState = useWorkspaceStore(s => s.newUploadState);
  const progress = useWorkspaceStore(s => s.newUploadProgress);
  const fileName = useWorkspaceStore(s => s.newFileName);
  const fileSize = useWorkspaceStore(s => s.newFileSize);
  const error = useWorkspaceStore(s => s.newError);
  const uploadDrawingFile = useWorkspaceStore(s => s.uploadDrawingFile);
  const clearUpload = useWorkspaceStore(s => s.clearUpload);

  const containerRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 480, height: 400 });

  useEffect(() => {
    const resizeObserver = new ResizeObserver((entries) => {
      for (let entry of entries) {
        const newW = entry.contentRect.width;
        const newH = entry.contentRect.height;
        setSize((prev) => {
          if (Math.abs(prev.width - newW) > 2 || Math.abs(prev.height - newH) > 2) {
            return { width: newW, height: newH };
          }
          return prev;
        });
      }
    });
    if (containerRef.current) resizeObserver.observe(containerRef.current);
    return () => resizeObserver.disconnect();
  }, []);

  return (
    <div className="flex flex-col h-full overflow-hidden relative bg-bg-dark w-full">
      <div className="flex-grow min-h-0 min-w-0 relative flex items-center justify-center overflow-hidden" ref={containerRef}>
        {drawing ? (
          <div style={{ position: "absolute", top: 0, left: 0, width: "100%", height: "100%", overflow: "hidden" }}>
            <DrawingCanvas
              ref={canvasRef}
              layers={layers}
              width={size.width}
              height={size.height}
              drawing={drawing}
            />
            <Minimap 
              drawing={drawing} 
              canvasWidth={size.width} 
              canvasHeight={size.height} 
            />
          </div>
        ) : (
          <UploadZone
            side="new"
            uploadState={uploadState}
            progress={progress}
            fileName={fileName}
            fileSize={fileSize}
            error={error}
            activeDrawing={drawing}
            uploadDrawingFile={uploadDrawingFile}
            clearUpload={clearUpload}
            currentNav={currentNav}
          />
        )}
      </div>
    </div>
  );
};

export const TwoDWorkspace: React.FC<TwoDWorkspaceProps> = ({ currentNav }) => {
  const oldDrawing = useWorkspaceStore(s => s.oldDrawing);
  const newDrawing = useWorkspaceStore(s => s.newDrawing);
  const complianceScore = useWorkspaceStore(s => s.complianceScore);
  const violations = useWorkspaceStore(s => s.violations);
  const hasHydrated = useWorkspaceStore(s => s.hasHydrated);
  const setReviewViewport = useReviewStore(s => s.setViewport);
  const showMinimap = useReviewStore(s => s.showMinimap);
  const toggleMinimap = useReviewStore(s => s.toggleMinimap);
  const showCanvasStats = useReviewStore(s => s.showCanvasStats);
  const toggleCanvasStats = useReviewStore(s => s.toggleCanvasStats);
  const showGrid = useReviewStore(s => s.showGrid);
  const toggleGrid = useReviewStore(s => s.toggleGrid);

  const drawingCanvasRefOld = useRef<any>(null);
  const drawingCanvasRefNew = useRef<any>(null);

  const { exportToPDF } = useComplianceReportExport({
    oldDrawing,
    newDrawing,
    violations,
    complianceScore,
    canvasRefs: { old: drawingCanvasRefOld, new: drawingCanvasRefNew }
  });

  const activeLayoutPreset = useReviewStore(s => s.activeLayoutPreset);

  const [model, setModel] = useState<Model | null>(null);
  const [isViewMenuOpen, setIsViewMenuOpen] = useState(false);
  const viewMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (viewMenuRef.current && !viewMenuRef.current.contains(event.target as Node)) {
        setIsViewMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  useEffect(() => {
    // v11: Bumping layout version to set Comparison Results panel width to 15%
    const savedLayout = localStorage.getItem(`twod-workspace-layout-v11-${activeLayoutPreset}`);
    if (savedLayout) {
      try {
        const parsed = JSON.parse(savedLayout);
        setModel(Model.fromJson(parsed));
        return;
      } catch (e) {
        console.error("Failed to parse saved layout", e);
      }
    }

    const globalOpts = {
      tabEnableClose: true,
      tabSetHeaderHeight: 32,
      tabSetTabStripHeight: 32,
      enableEdgeDock: true,
      marginInsets: { top: 0, right: 0, bottom: 0, left: 0 },
      splitterSize: 6,
      tabEnableFloat: true,
      tabEnablePopout: true
    };

    let layoutNode: any;

    const oldFileName = useWorkspaceStore.getState().oldDrawing?.file_name;
    const newFileName = useWorkspaceStore.getState().newDrawing?.file_name;
    const hasResults = complianceScore !== null;
    const bothUploaded = Boolean(useWorkspaceStore.getState().oldDrawing && useWorkspaceStore.getState().newDrawing);

    const MIN_TABSET_WIDTH = 220;

    const leftTabset = {
      type: "tabset",
      weight: 15,
      minWidth: MIN_TABSET_WIDTH,
      children: [{ type: "tab", id: "leftPanelTab", name: "Comparison Results", component: "leftPanel", enableClose: true }]
    };

    if (activeLayoutPreset === 'left') {
      layoutNode = {
        type: "row",
        weight: 100,
        children: [
          ...(bothUploaded ? [leftTabset] : []),
          { type: "tabset", weight: 42.5, minWidth: MIN_TABSET_WIDTH, children: [{ type: "tab", id: "originalCanvasTab", enableClose: true, name: oldFileName || "Original Drawing", component: "originalCanvas" }] },
          { type: "tabset", weight: 42.5, minWidth: MIN_TABSET_WIDTH, children: [{ type: "tab", id: "kmtiCanvasTab", enableClose: true, name: newFileName || "KMTI Drawing", component: "kmtiCanvas" }] },
          ...(hasResults ? [{ type: "tabset", weight: 20, minWidth: MIN_TABSET_WIDTH, children: [{ type: "tab", id: "rightPanelTab", name: "AI Auditor", component: "rightPanel", enableClose: true }] }] : [])
        ]
      };
    } else if (activeLayoutPreset === 'right') {
      layoutNode = {
        type: "row",
        weight: 100,
        children: [
          { type: "tabset", weight: 40, minWidth: MIN_TABSET_WIDTH, children: [{ type: "tab", id: "originalCanvasTab", enableClose: true, name: oldFileName || "Original Drawing", component: "originalCanvas" }] },
          { type: "tabset", weight: 40, minWidth: MIN_TABSET_WIDTH, children: [{ type: "tab", id: "kmtiCanvasTab", enableClose: true, name: newFileName || "KMTI Drawing", component: "kmtiCanvas" }] },
          ...(hasResults ? [{ type: "tabset", weight: 20, minWidth: MIN_TABSET_WIDTH, children: [{ type: "tab", id: "rightPanelTab", name: "AI Auditor", component: "rightPanel", enableClose: true }] }] : [])
        ]
      };
    } else {
      // grid default
      layoutNode = {
        type: "row",
        weight: 100,
        children: [
          ...(bothUploaded ? [leftTabset] : []),
          { type: "tabset", weight: bothUploaded ? 42.5 : 50, minWidth: MIN_TABSET_WIDTH, children: [{ type: "tab", id: "originalCanvasTab", enableClose: true, name: oldFileName || "Original Drawing", component: "originalCanvas" }] },
          { type: "tabset", weight: bothUploaded ? 42.5 : 50, minWidth: MIN_TABSET_WIDTH, children: [{ type: "tab", id: "kmtiCanvasTab", enableClose: true, name: newFileName || "KMTI Drawing", component: "kmtiCanvas" }] },
          ...(hasResults ? [{ type: "tabset", weight: 15, minWidth: MIN_TABSET_WIDTH, children: [{ type: "tab", id: "rightPanelTab", name: "AI Auditor", component: "rightPanel", enableClose: true }] }] : [])
        ]
      };
    }

    const newJson: IJsonModel = { global: globalOpts, layout: layoutNode };
    setModel(Model.fromJson(newJson));
    localStorage.setItem(`twod-workspace-layout-v11-${activeLayoutPreset}`, JSON.stringify(newJson));
  }, [activeLayoutPreset]);

  // Rename tabs when filenames change
  const oldFileNameStr = useWorkspaceStore(s => s.oldDrawing?.file_name);
  const newFileNameStr = useWorkspaceStore(s => s.newDrawing?.file_name);
  useEffect(() => {
    if (!model) return;
    const oldNode = model.getNodeById("originalCanvasTab");
    if (oldNode) {
      model.doAction(Actions.renameTab("originalCanvasTab", oldFileNameStr || "Original Drawing"));
    }
    const newNode = model.getNodeById("kmtiCanvasTab");
    if (newNode) {
      model.doAction(Actions.renameTab("kmtiCanvasTab", newFileNameStr || "KMTI Drawing"));
    }
  }, [model, oldFileNameStr, newFileNameStr]);

  const handleModelChange = (model: Model, _action: Action) => {
    localStorage.setItem(`twod-workspace-layout-v10-${activeLayoutPreset}`, JSON.stringify(model.toJson()));
  };

  // Dynamic show/hide for Comparison Results panel based on whether BOTH drawings are uploaded/ingested
  useEffect(() => {
    if (!model) return;

    const leftNode = model.getNodeById("leftPanelTab");
    const bothUploaded = Boolean(oldDrawing && newDrawing);

    if (!bothUploaded && leftNode) {
      model.doAction(Actions.deleteTab("leftPanelTab"));
    } else if (bothUploaded && !leftNode) {
      model.doAction(Actions.addNode(
        { type: "tab", id: "leftPanelTab", name: "Comparison Results", component: "leftPanel", enableClose: true },
        model.getRootRow().getId(),
        DockLocation.LEFT,
        -1
      ));
    }
  }, [oldDrawing, newDrawing, model]);

  // Dynamic show/hide for AI Auditor right panel based on complianceScore results
  const prevScoreRef = useRef(complianceScore);
  const isInitialModelLoadRef = useRef(true);

  useEffect(() => {
    if (!model) return;
    
    const node = model.getNodeById("rightPanelTab");
    const hasResults = complianceScore !== null;

    if (isInitialModelLoadRef.current) {
       isInitialModelLoadRef.current = false;
       if (!hasResults && node) {
          model.doAction(Actions.deleteTab("rightPanelTab"));
       }
    } else {
       const wasNull = prevScoreRef.current === null;
       const isNull = !hasResults;
       if (wasNull && !isNull && !node) {
          model.doAction(Actions.addNode({ type: "tab", id: "rightPanelTab", name: "AI Auditor", component: "rightPanel", enableClose: true }, model.getRootRow().getId(), DockLocation.RIGHT, -1));
       } else if (!wasNull && isNull && node) {
          model.doAction(Actions.deleteTab("rightPanelTab"));
       }
    }
    prevScoreRef.current = complianceScore;
  }, [complianceScore, model]);

  const handleAction = (action: Action) => {
    if (action.type === Actions.DELETE_TAB) {
      const node = model?.getNodeById(action.data.node) as TabNode | undefined;
      if (node) {
        const component = node.getComponent();
        if (component === "originalCanvas") {
          useWorkspaceStore.getState().clearUpload("old");
          return undefined; // prevent deletion
        }
        if (component === "kmtiCanvas") {
          useWorkspaceStore.getState().clearUpload("new");
          return undefined;
        }
      }
    }
    return action;
  };

  const factory = (node: TabNode) => {
    const component = node.getComponent();
    if (component === "leftPanel") {
      return <TwoDLeftPanel currentNav={currentNav} />;
    }
    if (component === "rightPanel") {
      return <TwoDRightPanel currentNav={currentNav} />;
    }
    if (component === "originalCanvas") {
      return <OriginalDrawingPanel canvasRef={drawingCanvasRefOld} currentNav={currentNav} />;
    }
    if (component === "kmtiCanvas") {
      return <KMTIDrawingPanel canvasRef={drawingCanvasRefNew} currentNav={currentNav} />;
    }
  };

  if (!hasHydrated || !model) {
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
    <div className="flex flex-grow h-full overflow-hidden min-w-0 bg-bg-dark">
      {currentNav === "workspace" && (
        <div className="flex flex-grow h-full overflow-hidden min-w-0 flex-col">
          <div className="flex items-center justify-between bg-bg-dark border-b border-border-color py-2 px-4 gap-3 shrink-0 w-full z-10 shadow-sm data-[theme=hc-dark]:shadow-md">
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold text-text-primary">2D Review Workspace</span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <Button 
                variant="outline" 
                size="icon" 
                onClick={() => setReviewViewport({ x: 0, y: 0, scale: 1 })} 
                className="focus:outline-none focus-visible:outline-none focus-visible:ring-0 text-text-muted hover:text-text-primary" 
                title="Reset Viewport"
              >
                <Maximize size={18} />
              </Button>
              {newDrawing && (
                <Button variant="outline" size="sm" onClick={exportToPDF} className="h-8 text-xs border-accent-cyan/30 text-accent-cyan hover:bg-accent-cyan hover:text-zinc-950 gap-1.5" title="Export drawing pair as PDF">
                  <Download size={14} /> PDF
                </Button>
              )}
              <div className="flex items-center gap-1.5">
                {/* 3-Dots View Controls Menu */}
                <div ref={viewMenuRef} className="relative">
                  <Button 
                    variant="outline" 
                    size="icon" 
                    onClick={() => setIsViewMenuOpen(!isViewMenuOpen)} 
                    title="More Options"
                    className={`focus:outline-none focus-visible:outline-none focus-visible:ring-0 ${
                      showMinimap || isViewMenuOpen 
                        ? "border-accent-cyan/50 text-accent-cyan bg-accent-cyan/10" 
                        : "text-text-muted hover:text-text-primary"
                    }`}
                  >
                    <MoreVertical size={18} />
                  </Button>

                  {isViewMenuOpen && (
                    <div className="absolute right-0 top-full mt-2 w-60 glass-panel rounded-xl shadow-2xl p-1.5 z-50 flex flex-col gap-1 border border-border-color bg-bg-card animate-fade-in">
                      <button
                        onClick={() => { toggleMinimap(); setIsViewMenuOpen(false); }}
                        className={`flex items-center justify-between w-full px-3 py-2 text-xs font-semibold rounded-lg transition-colors cursor-pointer ${
                          showMinimap 
                            ? "bg-accent-cyan/10 text-accent-cyan border border-accent-cyan/20" 
                            : "text-text-primary hover:bg-sidebar-item-hover"
                        }`}
                      >
                        <div className="flex items-center gap-2">
                          <Map size={16} />
                          <span>{showMinimap ? "Hide Interactive Minimap" : "Show Interactive Minimap"}</span>
                        </div>
                        {showMinimap && <Check size={14} className="text-accent-cyan" />}
                      </button>

                      <button
                        onClick={() => { toggleCanvasStats(); setIsViewMenuOpen(false); }}
                        className={`flex items-center justify-between w-full px-3 py-2 text-xs font-semibold rounded-lg transition-colors cursor-pointer ${
                          showCanvasStats 
                            ? "bg-accent-cyan/10 text-accent-cyan border border-accent-cyan/20" 
                            : "text-text-primary hover:bg-sidebar-item-hover"
                        }`}
                      >
                        <div className="flex items-center gap-2">
                          <Activity size={16} />
                          <span>{showCanvasStats ? "Hide Canvas Stats" : "Show Canvas Stats"}</span>
                        </div>
                        {showCanvasStats && <Check size={14} className="text-accent-cyan" />}
                      </button>

                      <button
                        onClick={() => { toggleGrid(); setIsViewMenuOpen(false); }}
                        className={`flex items-center justify-between w-full px-3 py-2 text-xs font-semibold rounded-lg transition-colors cursor-pointer ${
                          showGrid 
                            ? "bg-accent-cyan/10 text-accent-cyan border border-accent-cyan/20" 
                            : "text-text-primary hover:bg-sidebar-item-hover"
                        }`}
                      >
                        <div className="flex items-center gap-2">
                          <Grid size={16} />
                          <span>{showGrid ? "Hide Canvas Grid" : "Show Canvas Grid"}</span>
                        </div>
                        {showGrid && <Check size={14} className="text-accent-cyan" />}
                      </button>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>

          <div className="flex-grow h-full relative workspace-flexlayout-container">
            <Layout
              model={model}
              factory={factory}
              onModelChange={handleModelChange}
              onAction={handleAction}
            />
          </div>
        </div>
      )}
    </div>
  );
};
