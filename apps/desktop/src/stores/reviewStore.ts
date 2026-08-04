import { create } from 'zustand';
import {
  DEFAULT_CUSTOM_REGIONS,
  normalizeFractions,
  zoneBoxToFractions,
  type RegionFractions,
} from '../utils/zoneFractions';

// Re-exported so existing importers keep working; the definitions live in
// utils/zoneFractions.ts alongside the maths that operates on them.
export { DEFAULT_CUSTOM_REGIONS, type RegionFractions };

interface ViewportState {
  x: number;
  y: number;
  scale: number;
}

interface ReviewState {
  // Session details
  sessionId: string | null;
  drawingId: string | null;

  // Viewport & Navigation
  viewport: ViewportState;
  setViewport: (viewport: ViewportState) => void;
  resetViewport: () => void;

  // Layer controls
  activeLayers: Record<string, boolean>;
  toggleLayer: (layerName: string) => void;
  setAllLayers: (visible: boolean) => void;

  // Overlays & Annotations
  showViolations: boolean;
  toggleViolations: () => void;
  showMarkerLabels: boolean;
  toggleMarkerLabels: () => void;
  showMinimap: boolean;
  toggleMinimap: () => void;
  showAnnotations: boolean;
  toggleAnnotations: () => void;
  showCanvasStats: boolean;
  toggleCanvasStats: () => void;
  showGrid: boolean;
  toggleGrid: () => void;
  renderMode: 'hybrid' | 'vector' | 'raster';
  setRenderMode: (mode: 'hybrid' | 'vector' | 'raster') => void;
  selectedViolationId: string | null;
  setSelectedViolation: (id: string | null) => void;

  // Comparison
  isComparisonMode: boolean;
  toggleComparisonMode: () => void;

  // Real-time hover sync coordinate (standardized space)
  hoveredCoords: { x: number; y: number } | null;
  setHoveredCoords: (coords: { x: number; y: number } | null) => void;
  isLaserSyncEnabled: boolean;
  toggleLaserSync: () => void;

  // Visual Diff Overlay Mode (Option A)
  isOverlayModeEnabled: boolean;
  toggleOverlayMode: () => void;

  // Stage 1 Physical Comparison Controls
  isPhysicalComparisonEnabled: boolean;
  togglePhysicalComparison: () => void;
  selectedComparisonRegion: string | null;
  setSelectedComparisonRegion: (region: string | null) => void;
  visibleRegions: Record<string, boolean>;
  toggleRegionVisibility: (region: string) => void;

  // ROI Calibration Editor States
  isRoiEditModeEnabled: boolean;
  toggleRoiEditMode: () => void;
  /** Explicit setter. The auto-open flow needs idempotence, which a toggle cannot give. */
  setRoiEditMode: (enabled: boolean) => void;
  /**
   * Zone boxes keyed by DRAWING id, then by zone.
   *
   * Per drawing, not shared between the two panes. The reference and revision genuinely
   * differ in content extent -- notes that are one long sentence on one sheet and an ordered
   * list on the other need different boxes, and `views` was measured 23pp apart in height
   * between two sheets of the same template. A single shared box would clip one side or
   * swallow neighbouring content on the other, producing false mismatches.
   *
   * This also matches what the backend already does: orchestrator.py computes `ref_regions`
   * and `rev_regions` independently. A shared editor set contradicted the model the audit
   * actually runs on.
   */
  customRegions: Record<string, Record<string, RegionFractions>>;
  /** Regions for one drawing, falling back to defaults so callers never handle undefined. */
  getRegionsFor: (drawingId: string | null | undefined) => Record<string, RegionFractions>;
  updateCustomRegion: (drawingId: string, key: string, bounds: RegionFractions) => void;
  resetCustomRegions: (drawingId?: string | null) => void;
  loadCustomRegions: (drawingId: string | null) => void;
  /**
   * Replaces `customRegions` with the detector's own boxes, converted to fractions, so
   * alignment starts from what the pipeline actually produced instead of from the coarse
   * DEFAULT_CUSTOM_REGIONS guess. No-op when a saved alignment exists for this drawing —
   * seeding over the user's own work would be data loss.
   *
   * `templateZones` are the hand-aligned zones stored for this sheet signature, and they
   * are applied LAST, on top of detection. That mirrors the backend exactly:
   * `table_extractor.extract_dynamic_regions_async` overwrites detected boxes with the
   * template's. If the editor did not do the same it would show the user a different set of
   * zones than the comparison actually runs on.
   *
   * No Y flip: `ZoneFractions` is stored Y-DOWN precisely to match `customRegions`, so these
   * transfer directly. (Detected boxes are CAD Y-up and DO need the flip — that is what
   * `zoneBoxToFractions` is for.)
   */
  seedCustomRegionsFromDetected: (
    zones: Record<string, { xmin: number; ymin: number; xmax: number; ymax: number } | null>,
    renderBounds: readonly [number, number, number, number],
    drawingId: string | null | undefined,
    templateZones?: Record<string, RegionFractions> | null,
  ) => void;
  /** Explicitly apply a template's pinned zones to a drawing's custom regions, overwriting existing regions. */
  applyZoneTemplate: (
    drawingId: string | null | undefined,
    templateZones: Record<string, RegionFractions> | null | undefined,
    detectedZones?: Record<string, { xmin: number; ymin: number; xmax: number; ymax: number } | null> | null,
    renderBounds?: readonly [number, number, number, number] | null,
  ) => void;
  /** True once seeded or loaded from storage, so entering edit mode only seeds once. */
  hasSeededCustomRegions: boolean;
  /**
   * Zone keys that came from the hand-aligned template, per drawing.
   *
   * The overlay marks a zone dashed-and-'?' when the *detector* did not anchor it. A pinned
   * zone is never anchored by the detector — it did not come from there — so without this it
   * renders as a guess, which is precisely backwards: a human decision is the most
   * authoritative source of a zone box there is, outranking `content_aware`.
   */
  pinnedZoneKeys: Record<string, string[]>;
  getPinnedZoneKeys: (drawingId: string | null | undefined) => string[];

  // Context Menu Marker Filters
  visibleMarkerTypes: Record<string, boolean>;
  toggleMarkerTypeVisibility: (type: string) => void;

  // Layout Presets
  activeLayoutPreset: "grid" | "left" | "right";
  setActiveLayoutPreset: (preset: "grid" | "left" | "right") => void;
}

export const useReviewStore = create<ReviewState>((set, get) => ({
  sessionId: null,
  drawingId: null,

  viewport: { x: 0, y: 0, scale: 1 },
  setViewport: (vp) => set({ viewport: vp }),
  resetViewport: () => set({ viewport: { x: 0, y: 0, scale: 1 } }),

  activeLayers: {},
  toggleLayer: (layerName) => set((state) => ({
    activeLayers: {
      ...state.activeLayers,
      [layerName]: !state.activeLayers[layerName]
    }
  })),
  setAllLayers: (visible) => set((state) => {
    const updated: Record<string, boolean> = {};
    for (const key of Object.keys(state.activeLayers)) {
      updated[key] = visible;
    }
    return { activeLayers: updated };
  }),

  showViolations: true,
  toggleViolations: () => set((state) => ({ showViolations: !state.showViolations })),
  showMarkerLabels: false,
  toggleMarkerLabels: () => set((state) => ({ showMarkerLabels: !state.showMarkerLabels })),
  showMinimap: true,
  toggleMinimap: () => set((state) => ({ showMinimap: !state.showMinimap })),
  showAnnotations: false,
  toggleAnnotations: () => set((state) => ({ showAnnotations: !state.showAnnotations })),
  showCanvasStats: true,
  toggleCanvasStats: () => set((state) => ({ showCanvasStats: !state.showCanvasStats })),
  showGrid: false,
  toggleGrid: () => set((state) => ({ showGrid: !state.showGrid })),
  renderMode: 'hybrid',
  setRenderMode: (mode) => set({ renderMode: mode }),
  selectedViolationId: null,
  setSelectedViolation: (id) => set({ selectedViolationId: id }),

  isComparisonMode: false,
  toggleComparisonMode: () => set((state) => ({ isComparisonMode: !state.isComparisonMode })),

  hoveredCoords: null,
  setHoveredCoords: (coords) => set({ hoveredCoords: coords }),
  isLaserSyncEnabled: true,
  toggleLaserSync: () => set((state) => ({ isLaserSyncEnabled: !state.isLaserSyncEnabled })),

  isOverlayModeEnabled: false,
  toggleOverlayMode: () => set((state) => ({ isOverlayModeEnabled: !state.isOverlayModeEnabled })),

  isPhysicalComparisonEnabled: false,
  togglePhysicalComparison: () => set((state) => ({ isPhysicalComparisonEnabled: !state.isPhysicalComparisonEnabled })),
  selectedComparisonRegion: null,
  setSelectedComparisonRegion: (region) => set({ selectedComparisonRegion: region }),
  visibleRegions: { views: true, notes: true, bom: true, title: true, iso: true },
  toggleRegionVisibility: (region) => set((state) => ({
    visibleRegions: {
      ...state.visibleRegions,
      [region]: !state.visibleRegions[region]
    }
  })),

  isRoiEditModeEnabled: false,
  toggleRoiEditMode: () => set((state) => ({ isRoiEditModeEnabled: !state.isRoiEditModeEnabled })),
  setRoiEditMode: (enabled) => set({ isRoiEditModeEnabled: enabled }),
  customRegions: {},
  pinnedZoneKeys: {},
  hasSeededCustomRegions: false,

  // Uses zustand's `get`, not useReviewStore.getState(): referencing the store from inside
  // its own initializer is a circular reference that collapses ReviewState inference to
  // `any` across every consumer of the store.
  getRegionsFor: (drawingId) => {
    return (drawingId && get().customRegions[drawingId]) || DEFAULT_CUSTOM_REGIONS;
  },

  getPinnedZoneKeys: (drawingId) => {
    return (drawingId && get().pinnedZoneKeys[drawingId]) || [];
  },

  seedCustomRegionsFromDetected: (zones, renderBounds, drawingId, templateZones) => set((state) => {
    if (!drawingId) return {};

    const pinnedKeys = Object.entries(templateZones || {})
      .filter(([, frac]) => Boolean(frac))
      .map(([key]) => key);
    const nextPinned = { ...state.pinnedZoneKeys, [drawingId]: pinnedKeys };

    const existing = state.customRegions[drawingId] || DEFAULT_CUSTOM_REGIONS;
    const seeded: Record<string, RegionFractions> = { ...existing };

    // The DETECTOR only seeds a drawing that has no alignment yet. Re-seeding over an
    // existing one would silently discard the user's own work, and `zoneBoxToFractions`
    // applies the CAD Y-up -> Y-down flip that detected boxes need.
    if (!state.customRegions[drawingId]) {
      for (const [key, box] of Object.entries(zones)) {
        if (!box) continue;
        const frac = zoneBoxToFractions(box, renderBounds);
        // null means a degenerate sheet; keep the default rather than storing NaNs.
        if (frac) seeded[key] = normalizeFractions(frac);
      }
    }

    // The TEMPLATE is applied every time, on top of everything else.
    //
    // It is an explicit, named, persisted decision covering every drawing of this sheet
    // layout, whereas `customRegions` is one drawing's scratch state — and it is restored
    // from localStorage on reload, so it exists even when the user has never touched a
    // handle. Applying the template only on a fresh seed is what made a pinned zone appear
    // to revert to a detector box: the geometry was in the database and honoured by the
    // comparison, but the editor kept redisplaying the old local seed. A pinned zone belongs
    // in its pinned place every time the editor opens; RESET is the way back to detection.
    //
    // No Y flip here: ZoneFractions is stored Y-DOWN precisely to match customRegions.
    if (templateZones && Object.keys(templateZones).length > 0) {
      for (const [key, frac] of Object.entries(templateZones)) {
        if (frac) seeded[key] = normalizeFractions(frac);
      }
    }

    const next = { ...state.customRegions, [drawingId]: seeded };
    localStorage.setItem(`custom_regions_${drawingId}`, JSON.stringify(seeded));
    return {
      customRegions: next,
      pinnedZoneKeys: nextPinned,
      hasSeededCustomRegions: true,
    };
  }),

  applyZoneTemplate: (drawingId, templateZones, detectedZones, renderBounds) => set((state) => {
    if (!drawingId) return {};

    const pinnedKeys = Object.entries(templateZones || {})
      .filter(([, frac]) => Boolean(frac))
      .map(([key]) => key);
    const nextPinned = { ...state.pinnedZoneKeys, [drawingId]: pinnedKeys };

    const seeded: Record<string, RegionFractions> = { ...DEFAULT_CUSTOM_REGIONS };
    if (detectedZones && renderBounds) {
      for (const [key, box] of Object.entries(detectedZones)) {
        if (!box) continue;
        const frac = zoneBoxToFractions(box, renderBounds);
        if (frac) seeded[key] = normalizeFractions(frac);
      }
    }
    for (const [key, frac] of Object.entries(templateZones || {})) {
      if (frac) seeded[key] = normalizeFractions(frac);
    }

    localStorage.setItem(`custom_regions_${drawingId}`, JSON.stringify(seeded));
    return {
      customRegions: { ...state.customRegions, [drawingId]: seeded },
      pinnedZoneKeys: nextPinned,
      hasSeededCustomRegions: true,
    };
  }),

  updateCustomRegion: (drawingId, key, bounds) => set((state) => {
    if (!drawingId) return {};
    const forDrawing = state.customRegions[drawingId] || { ...DEFAULT_CUSTOM_REGIONS };
    const updated = {
      ...forDrawing,
      // Clamped and de-inverted on write, so dragging a handle past the opposite edge
      // can't persist a backwards box.
      [key]: normalizeFractions(bounds),
    };
    localStorage.setItem(`custom_regions_${drawingId}`, JSON.stringify(updated));
    return { customRegions: { ...state.customRegions, [drawingId]: updated } };
  }),

  resetCustomRegions: (drawingId) => set((state) => {
    if (!drawingId) return {};
    localStorage.removeItem(`custom_regions_${drawingId}`);
    const next = { ...state.customRegions };
    delete next[drawingId];
    // Reset means "go back to what the detector found", so the pinned marks go too --
    // leaving them would label detector boxes as human-aligned.
    const nextPinned = { ...state.pinnedZoneKeys };
    delete nextPinned[drawingId];
    return { customRegions: next, pinnedZoneKeys: nextPinned, hasSeededCustomRegions: false };
  }),

  loadCustomRegions: (drawingId) => set((state) => {
    if (!drawingId) return { drawingId: null };
    const saved = localStorage.getItem(`custom_regions_${drawingId}`);
    if (!saved) return { drawingId };
    try {
      return {
        drawingId,
        customRegions: { ...state.customRegions, [drawingId]: JSON.parse(saved) },
      };
    } catch {
      // Corrupt entry: drop it rather than leaving a poisoned key that fails every load.
      localStorage.removeItem(`custom_regions_${drawingId}`);
      return { drawingId };
    }
  }),

  visibleMarkerTypes: {
    MISMATCHED: true,
    CHANGED: true,
    ADDED: true,
    MATCHED: true,
    CONFLICT: true
  },
  toggleMarkerTypeVisibility: (type) => set((state) => ({
    visibleMarkerTypes: {
      ...state.visibleMarkerTypes,
      [type]: !state.visibleMarkerTypes[type]
    }
  })),

  activeLayoutPreset: "grid",
  setActiveLayoutPreset: (preset) => set({ activeLayoutPreset: preset })
}));
