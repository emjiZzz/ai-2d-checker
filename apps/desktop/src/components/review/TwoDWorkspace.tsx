import React, { useState, useEffect, useRef, useMemo } from "react";
import { Maximize, Download, MoreVertical, Check, Move, LayoutTemplate, Crosshair } from "lucide-react";
import { Layout, Model, TabNode, IJsonModel, Action, Actions, DockLocation } from 'flexlayout-react';
import 'flexlayout-react/style/dark.css';

import { useWorkspaceStore } from "../../stores/workspaceStore";
import {
  ZONE_KEYS,
  ZONE_SHORT_LABELS,
  ZONE_UI_COLORS,
  countFallbackZones,
  fetchZoneTemplate,
  fetchDefaultZoneTemplate,
  saveZoneTemplate,
  zoneSignature,
  type ZoneTemplateFractions,
} from "../../services/drawingsApi";
import { mergeSidesForTemplate, zonesToTemplatePayload } from "../../utils/zoneFractions";
import { useReviewStore, type RegionFractions } from "../../stores/reviewStore";
import { recordHistoryGroup, type HistoryEntry } from "../../stores/historyStore";
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
import { Button } from "../ui/Button";
import { TwoDLeftPanel } from "./TwoDLeftPanel";
import { TwoDRightPanel } from "./TwoDRightPanel";
import { SavedTemplatesModal } from "./SavedTemplatesModal";

/**
 * Zones whose position is fixed by the printed sheet template, so an alignment made on one
 * drawing transfers to every other drawing of that layout.
 *
 * NOTE: this is no longer a filter on what gets saved. Every zone the user has aligned is
 * written to the template; the list survives only to mark the ones where pinning carries a
 * caveat, because that caveat is measured and worth surfacing rather than deleting.
 *
 * Measured positional spread across the 6-drawing corpus: title_upper_left 3.8pp and bom
 * 4.6pp are fixed sheet furniture. `title` is included at 12.9pp as borderline furniture: a
 * printed title block does not wander, and its spread is believed to be residual detector
 * error. `notes` (37pp) genuinely moves with the drawing's contents, and `iso` is absent
 * altogether on roughly half the sheets -- pinning either fixes ONE position for every sheet
 * of the template, which is right when the layout really is shared and wrong when it is not.
 *
 * `views` is here despite a measured 33pp spread, because that figure does not mean what it
 * looks like. It comes from `_derive_views_zone`, which takes the 5-95 percentile of
 * *content* coordinates -- so it measures where the geometry happens to sit, not where the
 * sheet's drawing area is. The area is fixed by the sheet template; the content inside it is
 * not. A pinned `views` is the drawing area, and the exclusion it used to get from being
 * derived is re-applied at the point of use via `zone_detector.views_exclusions()`.
 *
 * See docs/zone-template-alignment-implementation-plan.md.
 */
const STABLE_ZONES = ["title_upper_left", "bom", "title", "tolerance", "views"] as const;

/**
 * localStorage key prefix for the persisted flexlayout model, per layout preset.
 *
 * Defined once because it previously was not: the read path and the default-seed write
 * used `v11` while `handleModelChange` wrote `v10`, so every layout the user rearranged
 * was saved to a key nothing ever read and silently lost on reload. Bump this when the
 * layout schema changes in a way that makes stored models unreadable.
 */
const LAYOUT_STORAGE_PREFIX = "twod-workspace-layout-v16";

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
        // Rounded to whole CSS pixels and compared exactly, rather than through a tolerance.
        // `contentRect` reports FRACTIONAL sizes, and the old ±2px deadband additionally let
        // this value sit up to 2px away from the container's true size. Both put the canvas
        // backing store out of step with its CSS box, which makes the browser rescale the whole
        // bitmap. CanvasRenderer now pins its own CSS size to its backing store so it can no
        // longer be stretched; integers here keep it flush with the container as well as crisp.
        // No thrash risk: the canvas is absolutely positioned inside a 100%-sized wrapper, so
        // its size never feeds back into the element being observed.
        const newW = Math.round(entry.contentRect.width);
        const newH = Math.round(entry.contentRect.height);
        setSize((prev) => (prev.width !== newW || prev.height !== newH ? { width: newW, height: newH } : prev));
      }
    });
    if (containerRef.current) resizeObserver.observe(containerRef.current);
    return () => resizeObserver.disconnect();
  }, []);

  return (
    <div className="flex flex-col h-full overflow-hidden relative bg-bg-dark w-full">
      <div
        className="flex-grow min-h-0 min-w-0 relative flex items-center justify-center overflow-hidden"
        ref={containerRef}
      >
        {drawing ? (
          <div style={{ position: "absolute", top: 0, left: 0, width: "100%", height: "100%", overflow: "hidden" }}>
            <DrawingCanvas
              ref={canvasRef}
              layers={layers}
              width={size.width}
              height={size.height}
              drawing={drawing}
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
        // Rounded to whole CSS pixels and compared exactly, rather than through a tolerance.
        // `contentRect` reports FRACTIONAL sizes, and the old ±2px deadband additionally let
        // this value sit up to 2px away from the container's true size. Both put the canvas
        // backing store out of step with its CSS box, which makes the browser rescale the whole
        // bitmap. CanvasRenderer now pins its own CSS size to its backing store so it can no
        // longer be stretched; integers here keep it flush with the container as well as crisp.
        // No thrash risk: the canvas is absolutely positioned inside a 100%-sized wrapper, so
        // its size never feeds back into the element being observed.
        const newW = Math.round(entry.contentRect.width);
        const newH = Math.round(entry.contentRect.height);
        setSize((prev) => (prev.width !== newW || prev.height !== newH ? { width: newW, height: newH } : prev));
      }
    });
    if (containerRef.current) resizeObserver.observe(containerRef.current);
    return () => resizeObserver.disconnect();
  }, []);

  return (
    <div className="flex flex-col h-full overflow-hidden relative bg-bg-dark w-full">
      <div
        className="flex-grow min-h-0 min-w-0 relative flex items-center justify-center overflow-hidden"
        ref={containerRef}
      >
        {drawing ? (
          <div style={{ position: "absolute", top: 0, left: 0, width: "100%", height: "100%", overflow: "hidden" }}>
            <DrawingCanvas
              ref={canvasRef}
              layers={layers}
              width={size.width}
              height={size.height}
              drawing={drawing}
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
  const aiScanProgress = useWorkspaceStore(s => s.aiScanProgress);
  const isPhysicalComparisonEnabled = useReviewStore(s => s.isPhysicalComparisonEnabled);
  const isRightPanelVisible = complianceScore !== null || aiScanProgress === "completed" || isPhysicalComparisonEnabled;
  const hasHydrated = useWorkspaceStore(s => s.hasHydrated);
  const setReviewViewport = useReviewStore(s => s.setViewport);
  const showViewOrigins = useReviewStore(s => s.showViewOrigins);
  const toggleViewOrigins = useReviewStore(s => s.toggleViewOrigins);

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
   * EVERY aligned zone is sent, including `notes` and `iso`. An earlier design filtered to
   * the furniture only, on the measurement that those two move between drawings; that is
   * still true (see STABLE_ZONES) but the trade was made the other way -- a zone the user
   * has deliberately placed should stay where they put it, and `RESET` is the way back to
   * detection. The zone picker still marks the moving ones so the caveat is visible.
   *
   * The two panes are merged by `mergeSidesForTemplate`: the REVISION's boxes win on any zone
   * aligned differently on the two sides, EXCEPT one the user aligned on the reference and not
   * on the revision. That exception is the fix for a silent no-op — a plain
   * `{...oldReg, ...newReg}` reads as a merge but is not one, because `getRegionsFor` returns a
   * drawing's complete zone set rather than only its edits, so every key was always present on
   * both sides and the revision won unconditionally. Editing on the reference pane and saving
   * therefore did nothing and visibly snapped back. See that function's docstring.
   *
   * The revision-wins default still matters for `notes`, which can be laid out in two columns
   * on one sheet and one on the other: absent a user preference the template carries the
   * revision's shape and imposes it on both.
   */
  const saveZonesAsTemplate = async () => {
    const src = oldDrawingForZones ?? newDrawingForZones;
    const bounds = src?.metadata?.render_bounds;
    const signature = zoneSignature(bounds);
    if (!signature) {
      setTemplateSaveState({ status: "error", message: "This drawing has no render bounds." });
      return;
    }

    const reviewState = useReviewStore.getState();
    const oldReg = oldDrawingForZones ? reviewState.getRegionsFor(oldDrawingForZones.id) : {};
    const newReg = newDrawingForZones ? reviewState.getRegionsFor(newDrawingForZones.id) : {};
    const regions = mergeSidesForTemplate(
      oldReg,
      newReg,
      oldDrawingForZones ? reviewState.userAlignedZoneKeys[oldDrawingForZones.id] ?? [] : [],
      newDrawingForZones ? reviewState.userAlignedZoneKeys[newDrawingForZones.id] ?? [] : [],
    );
    // Pure and tested in zoneFractions.test.ts. It carries the reshaped outline through —
    // this used to be an inline four-field literal that silently flattened every hand-drawn
    // polygon to its bounding box, and `applyZoneTemplate` below then wrote that flattened
    // version straight back over the live regions, so a reshape vanished on screen at the
    // moment of saving it.
    const zones = zonesToTemplatePayload(regions) as Record<string, ZoneTemplateFractions>;

    setTemplateSaveState({ status: "saving" });
    try {
      await saveZoneTemplate(signature, { zones, name: signature });

      const applyZoneTemplate = useReviewStore.getState().applyZoneTemplate;
      const entries: HistoryEntry[] = [];
      for (const d of [oldDrawing, newDrawing]) {
        if (!d) continue;
        const detected = zoneRegions[d.id];
        const bounds = d.metadata?.render_bounds;
        const before = useReviewStore.getState().customRegions[d.id] ?? null;
        const pinnedBefore = useReviewStore.getState().pinnedZoneKeys[d.id] ?? null;
        applyZoneTemplate(
          d.id,
          zones as any,
          detected as any,
          bounds as [number, number, number, number]
        );
        // Applying the template rewrites every zone on both panes from the merged set, which
        // can move zones the user never touched on this sheet. Undoable for the same reason
        // Reset is — though note this only walks back the LOCAL boxes; the template itself
        // stays saved on the server, since that is a deliberate cross-drawing decision and
        // not something a keystroke should silently retract.
        const after = useReviewStore.getState().customRegions[d.id] ?? null;
        entries.push({
          kind: 'zone/bulk',
          label: 'Apply sheet template',
          drawingId: d.id,
          before,
          after,
          pinnedBefore,
          pinnedAfter: useReviewStore.getState().pinnedZoneKeys[d.id] ?? null,
        });
      }
      // One click, one Ctrl+Z — the two entries are the two panes, not two user actions.
      recordHistoryGroup(entries);

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
          let tpl = await fetchZoneTemplate(signature);
          // No template for this sheet's own signature — fall back to the global default so the
          // editor shows the same zones the audit resolves to on an unmatched sheet. Mirrors
          // zone_template_resolver.resolve_zone_overrides exactly: a signature-specific template
          // wins; the default only fills the gap when none exists.
          if (!tpl) {
            tpl = await fetchDefaultZoneTemplate();
          }
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

  /**
   * Select a zone for alignment, and if it has no box yet, give it one so it is immediately
   * draggable. Optional zones like `shim` are in neither DEFAULT_CUSTOM_REGIONS nor the saved
   * template, so on a sheet where detection did not seed a box (or the template predates the
   * zone) the picker chip pointed at nothing — the user saw the chip but no box to place.
   * Seed a centred default per pane so the chip always yields something to drag onto the
   * content (e.g. the シム表 table). A zone that already has a box (detected or aligned) keeps
   * it untouched.
   */
  const selectZone = (key: string) => {
    setSelectedComparisonRegion(key);
    const store = useReviewStore.getState();
    const entries: HistoryEntry[] = [];
    for (const d of [oldDrawingForZones, newDrawingForZones]) {
      if (!d?.id) continue;
      const existing = store.getRegionsFor(d.id)?.[key];
      if (!existing) {
        const seeded = { xMin: 0.40, xMax: 0.60, yMin: 0.42, yMax: 0.68 };
        store.updateCustomRegion(d.id, key, seeded);
        // `before: null` — the zone had no box at all, so undo must REMOVE the key rather
        // than leave a zero-size one behind, which this chip would then read as "placed"
        // and never re-seed.
        entries.push({
          kind: 'zone/update',
          label: 'Add zone box',
          drawingId: d.id,
          zoneKey: key,
          before: null,
          after: seeded,
        });
      }
    }
    // Grouped: the chip seeds a box on each pane, and taking that back is one keystroke.
    recordHistoryGroup(entries);
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
  const [isTemplatesModalOpen, setIsTemplatesModalOpen] = useState(false);
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
    // Purge layouts saved under a superseded LAYOUT_STORAGE_PREFIX version.
    Object.keys(localStorage).forEach((k) => {
      if (k.startsWith("twod-workspace-layout-") && !k.startsWith(LAYOUT_STORAGE_PREFIX)) {
        localStorage.removeItem(k);
      }
    });

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
      // No splitterSize/splitterExtra here: flexlayout-react 0.9 ignores both and
      // derives the size from CSS. See --splitter-size in index.css.
      tabEnableFloat: true,
      tabEnablePopout: true
    };

    let layoutNode: any;

    const oldFileName = useWorkspaceStore.getState().oldDrawing?.file_name;
    const newFileName = useWorkspaceStore.getState().newDrawing?.file_name;
    const hasResults = complianceScore !== null || useWorkspaceStore.getState().aiScanProgress === "completed" || useReviewStore.getState().isPhysicalComparisonEnabled;

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
          ...(hasResults ? [{ type: "tabset", weight: 20, minWidth: MIN_TABSET_WIDTH, children: [{ type: "tab", id: "rightPanelTab", name: "AI Auditor & Copilot", component: "rightPanel", enableClose: true }] }] : [])
        ]
      };
    } else if (activeLayoutPreset === 'right') {
      layoutNode = {
        type: "row",
        weight: 100,
        children: [
          { type: "tabset", weight: 40, minWidth: MIN_TABSET_WIDTH, children: [{ type: "tab", id: "originalCanvasTab", enableClose: true, name: oldFileName || "Original Drawing", component: "originalCanvas" }] },
          { type: "tabset", weight: 40, minWidth: MIN_TABSET_WIDTH, children: [{ type: "tab", id: "kmtiCanvasTab", enableClose: true, name: newFileName || "KMTI Drawing", component: "kmtiCanvas" }] },
          ...(hasResults ? [{ type: "tabset", weight: 20, minWidth: MIN_TABSET_WIDTH, children: [{ type: "tab", id: "rightPanelTab", name: "AI Auditor & Copilot", component: "rightPanel", enableClose: true }] }] : [])
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
          ...(hasResults ? [{ type: "tabset", weight: 15, minWidth: MIN_TABSET_WIDTH, children: [{ type: "tab", id: "rightPanelTab", name: "AI Auditor & Copilot", component: "rightPanel", enableClose: true }] }] : [])
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

  // Dynamic show/hide for AI Auditor & Copilot right panel based on comparison/audit results
  const prevRightVisibleRef = useRef(isRightPanelVisible);
  const isInitialRightLoadRef = useRef(true);

  useEffect(() => {
    if (!model) return;

    const node = model.getNodeById("rightPanelTab");
    const isVisible = isRightPanelVisible;

    if (isInitialRightLoadRef.current) {
      isInitialRightLoadRef.current = false;
      if (!isVisible && node) {
        model.doAction(Actions.deleteTab("rightPanelTab"));
      } else if (isVisible && !node) {
        model.doAction(Actions.addNode({ type: "tab", id: "rightPanelTab", name: "AI Auditor & Copilot", component: "rightPanel", enableClose: true }, model.getRootRow().getId(), DockLocation.RIGHT, -1));
      }
    } else {
      const wasVisible = prevRightVisibleRef.current;
      if (!wasVisible && isVisible && !node) {
        model.doAction(Actions.addNode({ type: "tab", id: "rightPanelTab", name: "AI Auditor & Copilot", component: "rightPanel", enableClose: true }, model.getRootRow().getId(), DockLocation.RIGHT, -1));
      } else if (wasVisible && !isVisible && node) {
        model.doAction(Actions.deleteTab("rightPanelTab"));
      }
    }
    prevRightVisibleRef.current = isVisible;
  }, [isRightPanelVisible, model]);

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
          <div className="flex items-center justify-between bg-bg-topbar border-b border-border-color py-1 px-3 h-8 shrink-0 w-full z-10 select-none">
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold text-text-primary uppercase tracking-wide">2D Review Workspace</span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
              <Button
                variant="outline"
                size="icon"
                onClick={() => setReviewViewport({ x: 0, y: 0, scale: 1 })}
                className="h-6 w-6 rounded-sm focus:outline-none focus-visible:outline-none focus-visible:ring-0 text-text-muted hover:text-text-primary"
                title="Reset Viewport"
              >
                <Maximize size={14} />
              </Button>
              {newDrawing && (
                <Button variant="outline" size="sm" onClick={exportToPDF} className="h-6 px-2 text-[11px] rounded-sm border-accent-cyan/30 text-accent-cyan hover:bg-accent-cyan hover:text-zinc-950 gap-1" title="Export drawing pair as PDF">
                  <Download size={12} /> PDF
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
                  className="h-6 px-2 text-[11px] rounded-sm border-red-500/40 text-red-400 hover:bg-red-500 hover:text-white gap-1"
                  title="Export CAD Redline layer as a DXF file"
                >
                  {isExportingRedline ? (
                    <div className="w-2.5 h-2.5 border-2 border-red-400 border-t-transparent rounded-full animate-spin" />
                  ) : (
                    <Download size={12} />
                  )}
                  <span>Redline DXF</span>
                </Button>
              )}
              <Button
                variant="outline"
                size="sm"
                onClick={() => setIsTemplatesModalOpen(true)}
                className="h-6 px-2 text-[11px] rounded-sm border-amber-500/40 text-amber-500 hover:bg-amber-500/20 gap-1"
                title="Manage Saved Sheet Templates"
              >
                <LayoutTemplate size={12} />
                <span>Templates</span>
              </Button>
              <div className="flex items-center gap-1">
                {/* 3-Dots View Controls Menu */}
                <div ref={viewMenuRef} className="relative">
                  <Button
                    variant="outline"
                    size="icon"
                    onClick={() => setIsViewMenuOpen(!isViewMenuOpen)}
                    title="More Options"
                    className={`h-6 w-6 rounded-sm focus:outline-none focus-visible:outline-none focus-visible:ring-0 transition-colors ${isViewMenuOpen
                        ? "border-accent-cyan/50 text-accent-cyan bg-accent-cyan/10"
                        : "text-text-muted hover:text-text-primary border-transparent hover:bg-sidebar-item-hover"
                      }`}
                  >
                    <MoreVertical size={14} />
                  </Button>

                  {isViewMenuOpen && (
                    <div className="absolute right-0 top-full mt-2 w-60 glass-panel rounded-xl shadow-2xl p-1.5 z-50 flex flex-col gap-1 border border-border-color bg-bg-card animate-fade-in">

                      {/* One marker per view, at that view's own ORIGIN — computed by
                          `viewDatums.ts`, not read off the viewport window (which is what this
                          drew until 2026-08-12, 22.2 units from the front view's real datum).
                          Solid = stated by the file; dashed = inferred from the view's own
                          centrelines or concentric geometry, because the DXF carries only one
                          origin per sheet. Only appears on sheets that HAVE viewports: a
                          drawing exported DWG->DXF keeps everything in model space. */}
                      <button
                        onClick={() => { toggleViewOrigins(); setIsViewMenuOpen(false); }}
                        className={`flex items-center justify-between w-full px-3 py-2 text-xs font-semibold rounded-lg transition-colors cursor-pointer ${showViewOrigins
                            ? "bg-accent-cyan/10 text-accent-cyan border border-accent-cyan/20"
                            : "text-text-primary hover:bg-sidebar-item-hover"
                          }`}
                        title="Each view's own origin, as iCAD SX shows it. SOLID = stated by the DXF (its UCS origin projected) — only one view per sheet gets that. DASHED = inferred from the view's own centrelines or concentric geometry, because the export drops per-view origins. A view with neither is left unmarked rather than guessed."
                      >
                        <div className="flex items-center gap-2">
                          <Crosshair size={16} />
                          <span>{showViewOrigins ? "Hide View Origins" : "Show View Origins"}</span>
                        </div>
                        {showViewOrigins && <Check size={14} className="text-accent-cyan" />}
                      </button>

                      <button
                        onClick={() => { toggleZoneEditing(); setIsViewMenuOpen(false); }}
                        className={`flex items-center justify-between w-full px-3 py-2 text-xs font-semibold rounded-lg transition-colors cursor-pointer ${isRoiEditModeEnabled
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
                  onClick={() => selectZone(key)}
                  className={`px-2 py-1 text-[10px] font-bold uppercase rounded border transition-colors cursor-pointer ${selectedComparisonRegion === key
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
                  {!(STABLE_ZONES as readonly string[]).includes(key) && (
                    <span
                      className="ml-1 opacity-60"
                      title="Content moves between drawings — saving this to the template fixes one position for every sheet of this layout"
                    >
                      *
                    </span>
                  )}
                </button>
              ))}
              {/* Only the selected zone has drag handles — the underlying hit-test tracks a
                  single region — so the picker is how you reach the other six. */}
              <span className="text-[10px] text-text-muted ml-1">
                drag inside to move · corners to resize · click an edge to add a node ·
                alt-click a node to remove
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
                    className={`text-[10px] font-semibold ${templateSaveState.status === "error" ? "text-rose-400" : "text-emerald-400"
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
                    // Reset deletes the drawing's alignment AND its localStorage entry, so it
                    // is the one action here that can throw away a long session of hand
                    // placement. Snapshot each pane before it runs, then record the pair as
                    // ONE action: Reset is a single click and a single Ctrl+Z has to take all
                    // of it back. Undoing one pane at a time left the two sides disagreeing,
                    // which looks like undo failing rather than undo half-finishing.
                    const entries: HistoryEntry[] = [];
                    for (const d of [oldDrawingForZones, newDrawingForZones]) {
                      if (!d?.id) continue;
                      const store = useReviewStore.getState();
                      entries.push({
                        kind: 'zone/bulk',
                        label: 'Reset zone alignment',
                        drawingId: d.id,
                        before: store.customRegions[d.id] ?? null,
                        after: null,
                        pinnedBefore: store.pinnedZoneKeys[d.id] ?? null,
                        pinnedAfter: null,
                      });
                      resetCustomRegions(d.id);
                    }
                    recordHistoryGroup(entries);
                  }}
                  className="px-2 py-1 text-[10px] font-bold uppercase rounded border border-border-color text-text-muted hover:text-text-primary transition-colors cursor-pointer"
                  title="Discard this drawing's local alignment and return to the defaults"
                >
                  Reset
                </button>
              </div>
            </div>
          )}

          <div className="flex-grow h-full relative workspace-flexlayout-container">
            <Layout
              model={model}
              factory={factory}
              onModelChange={handleModelChange}
              onAction={handleAction}
            />
          </div>

          <SavedTemplatesModal
            isOpen={isTemplatesModalOpen}
            onClose={() => setIsTemplatesModalOpen(false)}
          />
        </div>
      )}
    </div>
  );
};
