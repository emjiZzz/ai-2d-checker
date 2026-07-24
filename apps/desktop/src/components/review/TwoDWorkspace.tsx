import React, { useState, useEffect, useRef } from "react";
import { Maximize, Download, Map } from "lucide-react";
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

// defaultLayoutJson removed as it was unused and contained syntax errors or type incompatibilities

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
        setSize({ width: entry.contentRect.width, height: entry.contentRect.height });
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
        setSize({ width: entry.contentRect.width, height: entry.contentRect.height });
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

  useEffect(() => {
    // v9: earlier versions let a tabset (most often "AI Auditor") be dragged down to a
    // near-zero-width sliver — just its bare tab-header strip, no visible label or content
    // — and that squeezed state persisted forever since it's saved verbatim to localStorage.
    // Bumping the key invalidates any such stuck layout so it regenerates fresh with the
    // minWidth guard below, which stops it from happening again.
    const savedLayout = localStorage.getItem(`twod-workspace-layout-v9-${activeLayoutPreset}`);
    if (savedLayout) {
      try {
        const parsed = JSON.parse(savedLayout);
        setModel(Model.fromJson(parsed));
        return; // Early return, layout hydrated from storage
      } catch (e) {
        console.error("Failed to parse saved layout", e);
      }
    }

    // Generate layout based on preset if no saved layout exists
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

    // Applied to every tabset below so no panel — including "AI Auditor", which only
    // appears once an audit has results — can be drag-resized down to an unusable sliver
    // (a bare tab-header strip with no visible label or content).
    const MIN_TABSET_WIDTH = 220;

    if (activeLayoutPreset === 'left') {
      layoutNode = { type: "row", weight: 100, children: [
        { type: "tabset", weight: 20, minWidth: MIN_TABSET_WIDTH, children: [{ type: "tab", name: "Comparison Results", component: "leftPanel", enableClose: true }] },
        { type: "tabset", weight: 40, minWidth: MIN_TABSET_WIDTH, children: [{ type: "tab", id: "originalCanvasTab", enableClose: true, name: oldFileName || "Original Drawing", component: "originalCanvas" }] },
        { type: "tabset", weight: 40, minWidth: MIN_TABSET_WIDTH, children: [{ type: "tab", id: "kmtiCanvasTab", enableClose: true, name: newFileName || "KMTI Drawing", component: "kmtiCanvas" }] },
        ...(hasResults ? [{ type: "tabset", weight: 20, minWidth: MIN_TABSET_WIDTH, children: [{ type: "tab", id: "rightPanelTab", name: "AI Auditor", component: "rightPanel", enableClose: true }] }] : [])
      ]};
    } else if (activeLayoutPreset === 'right') {
      layoutNode = { type: "row", weight: 100, children: [
        { type: "tabset", weight: 40, minWidth: MIN_TABSET_WIDTH, children: [{ type: "tab", id: "originalCanvasTab", enableClose: true, name: oldFileName || "Original Drawing", component: "originalCanvas" }] },
        { type: "tabset", weight: 40, minWidth: MIN_TABSET_WIDTH, children: [{ type: "tab", id: "kmtiCanvasTab", enableClose: true, name: newFileName || "KMTI Drawing", component: "kmtiCanvas" }] },
        ...(hasResults ? [{ type: "tabset", weight: 20, minWidth: MIN_TABSET_WIDTH, children: [{ type: "tab", id: "rightPanelTab", name: "AI Auditor", component: "rightPanel", enableClose: true }] }] : [])
      ]};
    } else {
      // grid default
      layoutNode = { type: "row", weight: 100, children: [
        { type: "tabset", weight: 20, minWidth: MIN_TABSET_WIDTH, children: [{ type: "tab", name: "Comparison Results", component: "leftPanel", enableClose: true }] },
        { type: "tabset", weight: 32.5, minWidth: MIN_TABSET_WIDTH, children: [{ type: "tab", id: "originalCanvasTab", enableClose: true, name: oldFileName || "Original Drawing", component: "originalCanvas" }] },
        { type: "tabset", weight: 32.5, minWidth: MIN_TABSET_WIDTH, children: [{ type: "tab", id: "kmtiCanvasTab", enableClose: true, name: newFileName || "KMTI Drawing", component: "kmtiCanvas" }] },
        ...(hasResults ? [{ type: "tabset", weight: 15, minWidth: MIN_TABSET_WIDTH, children: [{ type: "tab", id: "rightPanelTab", name: "AI Auditor", component: "rightPanel", enableClose: true }] }] : [])
      ]};
    }

    const newJson: IJsonModel = { global: globalOpts, layout: layoutNode };
    setModel(Model.fromJson(newJson));
    localStorage.setItem(`twod-workspace-layout-v9-${activeLayoutPreset}`, JSON.stringify(newJson));
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
    localStorage.setItem(`twod-workspace-layout-v9-${activeLayoutPreset}`, JSON.stringify(model.toJson()));
  };

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
            <div style={{ display: "flex", alignItems: "center" }}>
              <h3 className="text-sm font-bold flex items-center border-l-[3px] border-accent-cyan pl-2.5 text-text-primary m-0">
                Stage 1: Drawing Pair Ingestion
              </h3>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
              {newDrawing && (
                <Button variant="outline" size="sm" onClick={exportToPDF} className="h-8 text-xs border-accent-cyan/30 text-accent-cyan hover:bg-accent-cyan hover:text-zinc-950 gap-1.5" title="Export drawing pair as PDF">
                  <Download size={14} /> PDF
                </Button>
              )}
              <div className="flex items-center gap-1.5">
                <Button variant="outline" size="icon" onClick={() => setReviewViewport({ x: 0, y: 0, scale: 1 })} title="Reset Viewport">
                  <Maximize size={20} />
                </Button>
                <div className="w-px h-6 bg-border-color mx-1"></div>
                <Button variant={showMinimap ? "primary" : "outline"} size="icon" onClick={toggleMinimap} title="Toggle Interactive Minimap">
                  <Map size={20} />
                </Button>
              </div>
            </div>
          </div>
          
          <div className="flex-grow relative min-h-0 min-w-0 workspace-flexlayout-container">
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
