import React, { useState, useEffect, useRef, useMemo } from "react";
import { Maximize, Download, Map, MessageSquare, MoreVertical, Check, Activity, Grid, Move } from "lucide-react";
import { Layout, Model, TabNode, IJsonModel, Action, Actions, DockLocation } from 'flexlayout-react';
import 'flexlayout-react/style/dark.css';

import { useWorkspaceStore } from "../../stores/workspaceStore";
import {
  ZONE_KEYS,
  ZONE_SHORT_LABELS,
  ZONE_UI_COLORS,
  countFallbackZones,
  fetchZoneTemplate,
  saveZoneTemplate,
  zoneSignature,
} from "../../services/drawingsApi";
import { useReviewStore, type RegionFractions } from "../../stores/reviewStore";
import { useRoomStore } from "../../stores/roomStore";
import {
  isRoomSyncedWithDrawings,
  isZoneGateOpen,
  isZoneReviewGrandfathered,
  zonePairKey,
} from "../../utils/zoneGate";
import { useAuditStore } from "../../stores/auditStore";
import { useComplianceReportExport } from "../../hooks/useComplianceReportExport";
import { downloadRedlineDxf } from "../../services/reportsApi";
import { DrawingCanvas } from "./DrawingCanvas";
import { UploadZone } from "./UploadZone";
import { Minimap } from "./Minimap";
import { Button } from "../ui/Button";
import { TwoDLeftPanel } from "./TwoDLeftPanel";
import { TwoDRightPanel } from "./TwoDRightPanel";

/**
 * Zones whose alignment transfers to other drawings of the same sheet template.
 *
 * Measured positional spread across the 6-drawing corpus: title_upper_left 3.8pp and bom
 * 4.6pp are fixed sheet furniture; notes (37pp) moves with the drawing's contents, and iso
 * is per drawing because roughly half the sheets do not have one at all. Pinning a moving
 * zone is worse than not pinning it -- it asserts a wrong position confidently on every
 * subsequent drawing. `title` is included at 12.9pp as borderline furniture: a printed title
 * block does not wander, and its spread is believed to be residual detector error.
 *
 * `views` is templatable despite a measured 33pp spread, because that figure does not mean
 * what it looks like. It comes from `_derive_views_zone`, which takes the 5-95 percentile of
 * *content* coordinates -- so it measures where the geometry happens to sit, not where the
 * sheet's drawing area is. The area is fixed by the sheet template; the content inside it is
 * not. A pinned `views` is the drawing area, and the exclusion it used to get from being
 * derived is re-applied at the point of use via `zone_detector.views_exclusions()`.
 *
 * See docs/zone-template-alignment-implementation-plan.md.
 */
const TEMPLATABLE_ZONES = ["title_upper_left", "bom", "title", "tolerance", "views"] as const;

/**
 * localStorage key prefix for the persisted flexlayout model, per layout preset.
 *
 * Defined once because it previously was not: the read path and the default-seed write
 * used `v11` while `handleModelChange` wrote `v10`, so every layout the user rearranged
 * was saved to a key nothing ever read and silently lost on reload. Bump this when the
 * layout schema changes in a way that makes stored models unreadable.
 */
const LAYOUT_STORAGE_PREFIX = "twod-workspace-layout-v11";

/** Width of the Comparison Results tabset, matching what the layout seed used to apply. */
const LEFT_TABSET_WEIGHT = 15;
const LEFT_TABSET_MIN_WIDTH = 220;

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
  const annotations = useWorkspaceStore(s => s.annotations);
  const hasOpenAnnotations = useMemo(() => annotations.some((a) => a.status !== "resolved"), [annotations]);

  const setReviewViewport = useReviewStore(s => s.setViewport);
  const showMinimap = useReviewStore(s => s.showMinimap);
  const toggleMinimap = useReviewStore(s => s.toggleMinimap);
  const showAnnotations = useReviewStore(s => s.showAnnotations);
  const toggleAnnotations = useReviewStore(s => s.toggleAnnotations);
  const showCanvasStats = useReviewStore(s => s.showCanvasStats);
  const toggleCanvasStats = useReviewStore(s => s.toggleCanvasStats);
  const showGrid = useReviewStore(s => s.showGrid);
  const toggleGrid = useReviewStore(s => s.toggleGrid);
  const renderMode = useReviewStore(s => s.renderMode);
  const setRenderMode = useReviewStore(s => s.setRenderMode);

  // Zone bbox debug overlay. Lives on workspaceStore rather than reviewStore (where the
  // other view toggles are) because the cached boxes are keyed by drawing id and belong
  // with the drawings — see docs/zone-bbox-overlay-implementation-plan.md.
  const fetchZoneRegions = useWorkspaceStore(s => s.fetchZoneRegions);
  const zoneRegions = useWorkspaceStore(s => s.zoneRegions);
  const oldDrawingForZones = useWorkspaceStore(s => s.oldDrawing);
  const newDrawingForZones = useWorkspaceStore(s => s.newDrawing);

  const isRoiEditModeEnabled = useReviewStore(s => s.isRoiEditModeEnabled);
  const setRoiEditMode = useReviewStore(s => s.setRoiEditMode);
  const activeRoom = useRoomStore(s => s.activeRoom);
  const updateRoom = useRoomStore(s => s.updateRoom);
  const selectedComparisonRegion = useReviewStore(s => s.selectedComparisonRegion);
  const setSelectedComparisonRegion = useReviewStore(s => s.setSelectedComparisonRegion);
  const seedCustomRegionsFromDetected = useReviewStore(s => s.seedCustomRegionsFromDetected);
  const resetCustomRegions = useReviewStore(s => s.resetCustomRegions);

  // Returns a promise so callers that need the fetched zones (seeding the editor) can
  // await them instead of reading an empty store.
  const ensureZonesFetched = async () => {
    // Fetched lazily on first activation, never on drawing load: zone detection
    // flood-fills over every entity, and the overlay is off by default.
    await Promise.all([
      oldDrawingForZones ? fetchZoneRegions(oldDrawingForZones.id) : Promise.resolve(),
      newDrawingForZones ? fetchZoneRegions(newDrawingForZones.id) : Promise.resolve(),
    ]);
  };

  const [templateSaveState, setTemplateSaveState] = useState<
    { status: "idle" | "saving" | "saved" | "error"; message?: string }
  >({ status: "idle" });

  /**
   * Persists the aligned zones to the sheet template.
   *
   * Only TEMPLATABLE_ZONES are sent. `notes` moves with the drawing's content and `iso` is
   * absent entirely on roughly half the sheets, so pinning either would assert a wrong
   * position with full confidence on every other drawing of this template. They stay
   * detected per drawing. See docs/zone-template-alignment-implementation-plan.md,
   * "the two classes".
   */
  const saveZonesAsTemplate = async () => {
    const src = oldDrawingForZones ?? newDrawingForZones;
    const bounds = src?.metadata?.render_bounds;
    const signature = zoneSignature(bounds);
    if (!signature) {
      setTemplateSaveState({ status: "error", message: "This drawing has no render bounds." });
      return;
    }

    // Furniture only, and taken from the REFERENCE pane. Template zones are printed sheet
    // furniture and identical on both sides by definition; the per-side boxes exist for the
    // content zones, which are never templated.
    const regions = useReviewStore.getState().getRegionsFor(src?.id);
    const zones: Record<string, { xMin: number; xMax: number; yMin: number; yMax: number }> = {};
    for (const key of TEMPLATABLE_ZONES) {
      if (regions[key]) zones[key] = regions[key];
    }

    setTemplateSaveState({ status: "saving" });
    try {
      await saveZoneTemplate(signature, { zones, name: signature });
      setTemplateSaveState({
        status: "saved",
        message: `Saved ${Object.keys(zones).length} zone(s) to ${signature}`,
      });
    } catch (err) {
      setTemplateSaveState({
        status: "error",
        message: err instanceof Error ? err.message : String(err),
      });
    }
  };

  // Fallback count for the reference pane; both sheets are the same template, so one
  // number is enough context for what the dashed borders mean.
  const zoneFallbackCount = useMemo(() => {
    const src = oldDrawing ?? newDrawing;
    return src ? countFallbackZones(zoneRegions[src.id]) : 0;
  }, [oldDrawing, newDrawing, zoneRegions]);

  /**
   * Enters zone-alignment mode and seeds both panes. Idempotent, because the gate's
   * auto-open effect can fire while the mode is already on — a plain toggle would close it.
   */
  const openZoneEditing = async () => {
    if (useReviewStore.getState().isRoiEditModeEnabled) return;
    setRoiEditMode(true);

    // MUST await. This previously fired the fetch and then read `zoneRegionsMap` from the
    // React closure on the next line, where it is still empty on first activation — so
    // seeding silently never ran and the editor showed DEFAULT_CUSTOM_REGIONS while the
    // read-only overlay showed the real detected boxes. The two modes disagreeing on screen
    // was that race, not a coordinate-space bug.
    await ensureZonesFetched();

    // Read through getState() rather than the closure: the values captured when this
    // handler was created are stale by definition after the await.
    // Seed BOTH panes independently. The reference and revision differ in content extent —
    // notes that are a single sentence on one sheet and an ordered list on the other — so
    // each side starts from its own detected boxes rather than sharing one set.
    const zoneState = useWorkspaceStore.getState().zoneRegions;

    // Load the hand-aligned template for this sheet BEFORE seeding, so pinned zones can be
    // layered on top of detection. Without this the editor was write-only: `saveZoneTemplate`
    // persisted the alignment and the backend honoured it during comparison, but the editor
    // re-seeded from the detector every time it opened, so the user's own boxes appeared to
    // have been thrown away and the editor disagreed with what the audit actually ran on.
    //
    // Per drawing, because each side has its own render_bounds and therefore its own
    // signature — normally identical (same sheet template) but not guaranteed.
    const templates: Record<string, Record<string, RegionFractions> | null> = {};
    await Promise.all(
      [oldDrawingForZones, newDrawingForZones].map(async (d) => {
        if (!d) return;
        const signature = zoneSignature(d.metadata?.render_bounds);
        if (!signature) return;
        try {
          const tpl = await fetchZoneTemplate(signature);
          if (tpl?.zones) templates[d.id] = tpl.zones as Record<string, RegionFractions>;
        } catch {
          // A template that cannot be loaded must not block alignment — fall through to
          // detection, which is exactly what the user had before any template existed.
        }
      }),
    );

    for (const d of [oldDrawingForZones, newDrawingForZones]) {
      if (!d) continue;
      const detected = zoneState[d.id];
      const bounds = d.metadata?.render_bounds;
      if (detected && Array.isArray(bounds) && bounds.length === 4) {
        seedCustomRegionsFromDetected(
          detected as any,
          bounds as [number, number, number, number],
          d.id,
          templates[d.id],
        );
      }
    }

    const pinnedCount = Object.values(templates).reduce(
      (n, z) => n + Object.keys(z || {}).length, 0,
    );
    if (pinnedCount > 0) {
      setTemplateSaveState({
        status: "saved",
        message: `Loaded ${Object.keys(templates[oldDrawingForZones?.id ?? ""] ?? templates[newDrawingForZones?.id ?? ""] ?? {}).length} pinned zone(s) from template`,
      });
    }
    // Only one zone is draggable at a time (the hit-test keys off this), so default to a
    // selection instead of leaving edit mode inert with nothing grabbable.
    if (!useReviewStore.getState().selectedComparisonRegion) setSelectedComparisonRegion('title');
  };

  /** The ⋮ menu handler: still a toggle, so the user can leave and re-enter at will. */
  const toggleZoneEditing = async () => {
    if (isRoiEditModeEnabled) {
      setRoiEditMode(false);
      return;
    }
    await openZoneEditing();
  };

  // ─── Zone review gate ───────────────────────────────────────────────────────
  // The Comparison Results panel stays hidden until the user has confirmed the zone boxes
  // for this drawing pair. See utils/zoneGate.ts for the rule and why it is pure.

  const pairKey = zonePairKey(oldDrawing?.id, newDrawing?.id);
  const roomSynced = isRoomSyncedWithDrawings(activeRoom, oldDrawing?.id, newDrawing?.id);

  // Optimistic: the panel appears the moment Done is clicked, not after the PATCH lands,
  // and survives a failed write for the rest of the session.
  const [locallyConfirmedPair, setLocallyConfirmedPair] = useState<string | null>(null);

  // Grandfathering is SNAPSHOTTED per room open, never derived live. AuditWorkspace's
  // reverse-sync nulls `physical_comparison_results` whenever the scan returns to idle —
  // which is exactly what Re-test does — so a live reading would delete the Comparison
  // Results panel out from under a user mid-retest.
  const grandfatheredRef = useRef(false);
  const grandfatherRoomIdRef = useRef<string | null>(null);
  if (activeRoom && grandfatherRoomIdRef.current !== activeRoom.id) {
    grandfatherRoomIdRef.current = activeRoom.id;
    grandfatheredRef.current = isZoneReviewGrandfathered(activeRoom);
  }

  const zonesGateOpen = isZoneGateOpen({
    oldDrawingId: oldDrawing?.id,
    newDrawingId: newDrawing?.id,
    room: activeRoom,
    grandfathered: grandfatheredRef.current,
    locallyConfirmedPair,
  });

  // Reset per-room UI state. `isRoiEditModeEnabled` lives in reviewStore and is global and
  // ephemeral — without this, edit mode bleeds from an unconfirmed room into a confirmed one
  // and the amber toolbar renders over a room that is already past the gate.
  const autoOpenedForRef = useRef<string | null>(null);
  useEffect(() => {
    setRoiEditMode(false);
    autoOpenedForRef.current = null;
    setLocallyConfirmedPair(null);
  }, [activeRoom?.id, setRoiEditMode]);

  // Auto-open the editor when the gate is closed. `roomSynced` defeats an ordering race in
  // openRoom, which pushes drawings into the workspace well before it sets activeRoom: in
  // that window both drawings are present while activeRoom is still the previous room, and
  // this would flash the editor open over a room that is already confirmed.
  useEffect(() => {
    if (!hasHydrated || !roomSynced || !activeRoom || !pairKey) return;
    if (zonesGateOpen) return;
    const key = `${activeRoom.id}|${pairKey}`;
    if (autoOpenedForRef.current === key) return; // don't fight a manual close
    autoOpenedForRef.current = key;
    void openZoneEditing();
  }, [hasHydrated, roomSynced, zonesGateOpen, activeRoom?.id, pairKey]);

  const confirmZoneReview = async () => {
    if (!activeRoom || !pairKey) return;
    setLocallyConfirmedPair(pairKey);
    setRoiEditMode(false);
    await updateRoom(activeRoom.id, { zones_confirmed_for: pairKey });
  };

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

  const activeSession = useAuditStore(s => s.activeSession);
  const [isExportingRedline, setIsExportingRedline] = useState(false);
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
    const savedLayout = localStorage.getItem(`${LAYOUT_STORAGE_PREFIX}-${activeLayoutPreset}`);
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

    const MIN_TABSET_WIDTH = 220;


    // NOTE: the seed deliberately does not create `leftPanelTab`. The zone-review gate
    // effect below owns that tab exclusively — seeding it here and deleting it one frame
    // later flashes the gated panel on screen for every fresh user, and having two sources
    // of truth for one tab is what made the previous show/hide behaviour hard to reason
    // about. LEFT_TABSET_WEIGHT is re-applied when the effect adds the tab.

    if (activeLayoutPreset === 'left') {
      layoutNode = {
        type: "row",
        weight: 100,
        children: [
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
          { type: "tabset", weight: 50, minWidth: MIN_TABSET_WIDTH, children: [{ type: "tab", id: "originalCanvasTab", enableClose: true, name: oldFileName || "Original Drawing", component: "originalCanvas" }] },
          { type: "tabset", weight: 50, minWidth: MIN_TABSET_WIDTH, children: [{ type: "tab", id: "kmtiCanvasTab", enableClose: true, name: newFileName || "KMTI Drawing", component: "kmtiCanvas" }] },
          ...(hasResults ? [{ type: "tabset", weight: 15, minWidth: MIN_TABSET_WIDTH, children: [{ type: "tab", id: "rightPanelTab", name: "AI Auditor", component: "rightPanel", enableClose: true }] }] : [])
        ]
      };
    }

    const newJson: IJsonModel = { global: globalOpts, layout: layoutNode };
    setModel(Model.fromJson(newJson));
    localStorage.setItem(`${LAYOUT_STORAGE_PREFIX}-${activeLayoutPreset}`, JSON.stringify(newJson));
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
    // v11, matching the key this component reads on mount and writes when seeding a
    // default layout. This wrote v10 — a key nothing ever read back — so every layout
    // the user rearranged was saved and then silently discarded on reload.
    localStorage.setItem(`${LAYOUT_STORAGE_PREFIX}-${activeLayoutPreset}`, JSON.stringify(model.toJson()));
  };

  // Show/hide the Comparison Results panel. Gated on the zone review, not merely on both
  // drawings being present — see utils/zoneGate.ts.
  //
  // Deliberately has NO isInitialModelLoadRef guard, unlike the AI Auditor effect below.
  // That guard exists there so a newly arrived score doesn't fight the seeded layout; here
  // the delete branch running on first mount is precisely the mechanism that removes a
  // leftPanelTab persisted into the saved layout by an earlier session. Adding a guard here
  // would let a stale layout leak the panel past the gate.
  useEffect(() => {
    if (!model) return;

    const leftNode = model.getNodeById("leftPanelTab");
    const bothUploaded = zonesGateOpen;

    if (!bothUploaded && leftNode) {
      model.doAction(Actions.deleteTab("leftPanelTab"));
    } else if (bothUploaded && !leftNode) {
      const added = model.doAction(Actions.addNode(
        { type: "tab", id: "leftPanelTab", name: "Comparison Results", component: "leftPanel", enableClose: true },
        model.getRootRow().getId(),
        DockLocation.LEFT,
        -1
      ));
      // addNode gives the new tabset flexlayout's default weight, which is far wider than
      // the 15 the seed used to apply. Now that this is the only path that creates the tab,
      // that difference would be everyone's panel width, not an edge case.
      const parent = (added as any)?.getParent?.();
      if (parent) {
        model.doAction(Actions.updateNodeAttributes(parent.getId(), {
          weight: LEFT_TABSET_WEIGHT,
          minWidth: LEFT_TABSET_MIN_WIDTH,
        }));
      }
    }
  }, [zonesGateOpen, model]);

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
            <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
              {newDrawing && (
                <Button variant="outline" size="sm" onClick={exportToPDF} className="h-8 text-xs border-accent-cyan/30 text-accent-cyan hover:bg-accent-cyan hover:text-zinc-950 gap-1.5" title="Export drawing pair as PDF">
                  <Download size={14} /> PDF
                </Button>
              )}
              {activeSession?.id && (
                <Button 
                  variant="outline" 
                  size="sm" 
                  onClick={async () => {
                    try {
                      setIsExportingRedline(true);
                      await downloadRedlineDxf(activeSession.id, `redline_${newDrawing?.file_name || activeSession.id}.dxf`);
                    } catch (err: any) {
                      alert(`Redline DXF Export: ${err.message}`);
                    } finally {
                      setIsExportingRedline(false);
                    }
                  }} 
                  disabled={isExportingRedline}
                  className="h-8 text-xs border-red-500/40 text-red-400 hover:bg-red-500 hover:text-white gap-1.5" 
                  title="Export CAD Redline layer as a DXF file"
                >
                  {isExportingRedline ? (
                    <div className="w-3 h-3 border-2 border-red-400 border-t-transparent rounded-full animate-spin" />
                  ) : (
                    <Download size={14} />
                  )}
                  <span>Redline DXF</span>
                </Button>
              )}
              <div className="flex items-center gap-1.5">
                <Button 
                  variant="outline" 
                  size="icon" 
                  onClick={toggleAnnotations} 
                  title="Toggle Reviewer Annotations"
                  className={`relative focus:outline-none focus-visible:outline-none focus-visible:ring-0 ${
                    showAnnotations 
                      ? "border-accent-cyan/50 text-accent-cyan bg-accent-cyan/10" 
                      : "text-text-muted hover:text-text-primary"
                  }`}
                >
                  <MessageSquare size={18} />
                  {hasOpenAnnotations && (
                    <span className="absolute top-1 right-1 w-2 h-2 rounded-full bg-accent-amber animate-pulse" />
                  )}
                </Button>

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

                      <button
                        onClick={() => { toggleZoneEditing(); setIsViewMenuOpen(false); }}
                        className={`flex items-center justify-between w-full px-3 py-2 text-xs font-semibold rounded-lg transition-colors cursor-pointer ${
                          isRoiEditModeEnabled
                            ? "bg-amber-500/10 text-amber-400 border border-amber-500/20"
                            : "text-text-primary hover:bg-sidebar-item-hover"
                        }`}
                        title="Drag and resize the zone boxes to align them to this sheet"
                      >
                        <div className="flex items-center gap-2">
                          <Move size={16} />
                          <span>{isRoiEditModeEnabled ? "Stop Editing Zones" : "Edit Zone Boxes"}</span>
                        </div>
                        {isRoiEditModeEnabled && <Check size={14} className="text-amber-400" />}
                      </button>

                      <div className="h-px bg-border-color my-0.5"></div>
                      <div className="px-3 py-1 text-[10px] font-bold uppercase tracking-wider text-text-muted">Canvas Engine Mode</div>
                      <div className="flex items-center gap-1 px-1.5 py-1 bg-bg-dark rounded-lg border border-border-color">
                        {(['hybrid', 'vector', 'raster'] as const).map((mode) => (
                          <button
                            key={mode}
                            onClick={() => { setRenderMode(mode); setIsViewMenuOpen(false); }}
                            className={`flex-1 py-1 text-[10px] font-bold capitalize rounded transition-colors cursor-pointer ${
                              renderMode === mode
                                ? "bg-accent-cyan text-zinc-950 shadow-xs"
                                : "text-text-muted hover:text-text-primary"
                            }`}
                          >
                            {mode}
                          </button>
                        ))}
                      </div>

                      <div className="h-px bg-border-color my-0.5"></div>

                      <button
                        onClick={() => { setReviewViewport({ x: 0, y: 0, scale: 1 }); setIsViewMenuOpen(false); }}
                        className="flex items-center gap-2 w-full px-3 py-2 text-xs font-semibold text-text-primary hover:bg-sidebar-item-hover rounded-lg transition-colors cursor-pointer"
                      >
                        <Maximize size={16} />
                        <span>Reset Viewport</span>
                      </button>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>

          {isRoiEditModeEnabled && (
            <div className="flex items-center gap-2 px-4 py-2 bg-amber-500/5 border-b border-amber-500/20 flex-wrap">
              <span className="text-[10px] font-bold uppercase tracking-wider text-amber-400">
                Aligning zone
              </span>
              {ZONE_KEYS.map((key) => (
                <button
                  key={key}
                  onClick={() => setSelectedComparisonRegion(key)}
                  className={`px-2 py-1 text-[10px] font-bold uppercase rounded border transition-colors cursor-pointer ${
                    selectedComparisonRegion === key
                      ? "text-zinc-950 border-transparent"
                      : "text-text-muted border-border-color hover:text-text-primary"
                  }`}
                  style={
                    selectedComparisonRegion === key
                      ? { background: ZONE_UI_COLORS[key] }
                      : undefined
                  }
                >
                  {ZONE_SHORT_LABELS[key] ?? key}
                  {!(TEMPLATABLE_ZONES as readonly string[]).includes(key) && (
                    <span
                      className="ml-1 opacity-60"
                      title="Moves between drawings — aligned per drawing only, not saved to the template"
                    >
                      *
                    </span>
                  )}
                </button>
              ))}
              {/* Only the selected zone has drag handles — the underlying hit-test tracks a
                  single region — so the picker is how you reach the other six. */}
              <span className="text-[10px] text-text-muted ml-1">
                drag inside to move · corners to resize
              </span>
              {/* Dashed boxes with a '?' are zones the detector guessed from the percentage
                  grid rather than anchoring on real content. Counting them here saves
                  squinting at seven badges to work out how much is guesswork. */}
              {zoneFallbackCount > 0 && (
                <span className="text-[10px] font-semibold text-amber-400/80">
                  {zoneFallbackCount} of {ZONE_KEYS.length} dashed = detector guess
                </span>
              )}

              <div className="ml-auto flex items-center gap-2">
                {templateSaveState.message && (
                  <span
                    className={`text-[10px] font-semibold ${
                      templateSaveState.status === "error" ? "text-rose-400" : "text-emerald-400"
                    }`}
                  >
                    {templateSaveState.message}
                  </span>
                )}
                {/* Primary action of this mode: the gate stays shut until it is clicked. */}
                <button
                  onClick={confirmZoneReview}
                  disabled={templateSaveState.status === "saving" || !pairKey}
                  className="px-3 py-1 text-[10px] font-bold uppercase rounded bg-accent-cyan text-zinc-950 hover:brightness-110 transition-all cursor-pointer disabled:opacity-50"
                  title="Confirm these zone boxes and continue to the comparison"
                >
                  Done
                </button>
                <button
                  onClick={saveZonesAsTemplate}
                  disabled={templateSaveState.status === "saving"}
                  className="px-2 py-1 text-[10px] font-bold uppercase rounded border border-emerald-500/40 bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 transition-colors cursor-pointer disabled:opacity-50"
                  title="Save the sheet-furniture zones to this sheet template so other drawings of the same layout reuse them"
                >
                  {templateSaveState.status === "saving" ? "Saving…" : "Save to template"}
                </button>
                <button
                  onClick={() => {
                    if (oldDrawingForZones) resetCustomRegions(oldDrawingForZones.id);
                    if (newDrawingForZones) resetCustomRegions(newDrawingForZones.id);
                  }}
                  className="px-2 py-1 text-[10px] font-bold uppercase rounded border border-border-color text-text-muted hover:text-text-primary transition-colors cursor-pointer"
                  title="Discard this drawing's local alignment and return to the defaults"
                >
                  Reset
                </button>
              </div>
            </div>
          )}

          <div className="flex-grow h-full relative">
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
