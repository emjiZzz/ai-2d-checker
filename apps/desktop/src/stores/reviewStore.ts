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
  /**
   * The marker under the cursor, on EITHER canvas.
   *
   * Shared rather than per-canvas because one marker exists on both sheets — it is drawn at each
   * side's own coordinate — and hovering it should reveal both halves at once. That is the whole
   * value of the card while comparing: you look at one sheet and read what the other says.
   *
   * It was `useState` inside `useCanvasInteraction`, so each pane had its own copy and only the
   * pane under the cursor lit up. The other one kept drawing the same marker with no card, which
   * looked like the marker existing on one sheet only.
   */
  hoveredMarkerId: string | null;
  setHoveredMarkerId: (id: string | null) => void;
  /**
   * A matcher correction waiting for the engineer to point at the right entity.
   *
   * `mispaired_wrong_match` / `mispaired_missing_counterpart` used to submit immediately with an
   * optional free-text box for the counterpart. It was skipped 103 times out of 106, leaving a
   * corpus of rejections with no corrections — and a matcher cannot be trained on negatives,
   * because there is no target to learn toward.
   *
   * So the correction is now armed here and completed by the next entity click on either sheet,
   * reusing the picking gesture the manual-check flow already provides. The payload is carried
   * whole rather than rebuilt at completion: the finding's row, category and snapshot belong to
   * the card that was clicked, and that card may be scrolled away by the time the pick happens.
   */
  pendingCounterpart: { payload: any; label: string } | null;
  setPendingCounterpart: (p: { payload: any; label: string } | null) => void;
  showAnnotations: boolean;
  toggleAnnotations: () => void;
  showViewOrigins: boolean;
  toggleViewOrigins: () => void;
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

  // NOTE: manual engineer check is deliberately NOT a toggle here, unlike every other mode on
  // this store. It is a property of the ROOM, chosen at creation (`room_mode`) and read via
  // `useIsManualCheckRoom()`. A flag here would be a second copy that can disagree with the
  // room — and the disagreement is silent in the direction that matters, since a manual room
  // rendering engine findings destroys the independence the markings exist to provide.

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
  /**
   * Undo/redo entry point for a SINGLE zone. Writes `bounds` verbatim, or DELETES the zone
   * when `bounds` is null.
   *
   * Separate from `updateCustomRegion` because that one cannot express removal — it takes a
   * `RegionFractions` and always writes one. Undoing the zone picker's auto-seed (which
   * creates a box for a zone that had none) has to leave the key absent, not leave a
   * zero-size box behind that the picker would then treat as already placed.
   *
   * Never normalizes: the value came out of the store already normalized, and re-normalizing
   * a polygon's derived bounding box on the way back in is how a restored shape drifts.
   */
  restoreCustomRegion: (drawingId: string, key: string, bounds: RegionFractions | null) => void;
  /**
   * Undo/redo entry point for a WHOLE drawing's alignment — the inverse of `resetCustomRegions`
   * and of applying a template. `regions: null` restores the "never aligned" state, matching
   * what Reset produces, including clearing the localStorage key rather than storing `{}`
   * (an empty object is a drawing whose every zone was deleted, which is not the same thing
   * and would suppress re-seeding from the detector).
   */
  restoreDrawingRegions: (
    drawingId: string,
    regions: Record<string, RegionFractions> | null,
    pinned: string[] | null,
  ) => void;
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
  /**
   * Zone keys a human has moved, resized or reshaped, per drawing. Persisted.
   *
   * ## Why this has to exist
   *
   * `customRegions` holds two different things under one key: boxes the *detector* seeded and
   * boxes the *user* dragged. They are indistinguishable once written, and localStorage keeps
   * both. That ambiguity caused a bug in each direction:
   *
   * - Trusting localStorage meant a stale detector seed masked a pinned template zone, so
   *   a saved alignment looked reverted.
   * - The fix for that — stamping the template over everything on every editor open — meant a
   *   user's own alignment was silently destroyed, on every open and on every restart.
   *
   * Recording *who* placed a box resolves both: the template overrides a detector seed and
   * never overrides a human one.
   *
   * ## Persisted, not session-scoped
   *
   * It was session-scoped at first, on the reasoning that "Save to template" is how an edit
   * outlives a session. That was wrong in practice: a per-drawing alignment is legitimate work
   * that a user expects to survive a restart, and a template is a per-*layout* default, so the
   * more specific value should win — the same precedence the backend already uses when a
   * signature-specific template beats the global default.
   */
  userAlignedZoneKeys: Record<string, string[]>;

  // Context Menu Marker Filters
  visibleMarkerTypes: Record<string, boolean>;
  toggleMarkerTypeVisibility: (type: string) => void;

  // Layout Presets
  activeLayoutPreset: "grid" | "left" | "right";
  setActiveLayoutPreset: (preset: "grid" | "left" | "right") => void;
}

/**
 * Where a drawing's human-aligned zone keys live on disk.
 *
 * A sibling of `custom_regions_<id>` rather than a field inside it, so the stored region
 * shape is unchanged and an install that predates this key simply reads back "nothing was
 * hand-aligned" — which is the safe direction: the template still applies, exactly as before.
 */
const alignedKeysStorageKey = (drawingId: string) => `custom_regions_aligned_${drawingId}`;

function persistAlignedKeys(drawingId: string, keys: string[] | null): void {
  if (!keys || keys.length === 0) {
    localStorage.removeItem(alignedKeysStorageKey(drawingId));
    return;
  }
  localStorage.setItem(alignedKeysStorageKey(drawingId), JSON.stringify(keys));
}

function readAlignedKeys(drawingId: string): string[] {
  const raw = localStorage.getItem(alignedKeysStorageKey(drawingId));
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter((k) => typeof k === "string") : [];
  } catch {
    localStorage.removeItem(alignedKeysStorageKey(drawingId));
    return [];
  }
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

  pendingCounterpart: null,
  setPendingCounterpart: (p) => set({ pendingCounterpart: p }),

  hoveredMarkerId: null,
  setHoveredMarkerId: (id) => {
    // Guarded: this is written from a mousemove handler, and an unconditional set would
    // re-render BOTH canvases on every pointer pixel now that the value is shared.
    if (get().hoveredMarkerId === id) return;
    set({ hoveredMarkerId: id });
  },
  showAnnotations: false,
  toggleAnnotations: () => set((state) => ({ showAnnotations: !state.showAnnotations })),
  // One marker per view, at that view's own origin. Off by default: it is a reference overlay,
  // not part of the sheet, and a drawing with no paper-space viewports (the DWG-exported
  // reference sheets) has none to show at all.
  //
  // Until 2026-08-12 this drew the viewport's WINDOW CENTRE and called it the origin — 22.2 and
  // 11.8 units out on two of M745221N01_FSRS2's three views. The datums are now computed in
  // `viewDatums.ts`, and the inferred ones are drawn dashed. See renderViewOrigins.
  showViewOrigins: false,
  toggleViewOrigins: () => set((state) => ({ showViewOrigins: !state.showViewOrigins })),
  // There is no `renderMode` any more — the canvas draws vectors, always. The raster PNG was
  // removed from the display path entirely; the backend still generates it, but only as the
  // source of `render_bounds` and as an input to title-block OCR and the PDF report.
  // See docs/vault/07 - .../ADR-011 Vector as the Only Render Path.
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
  userAlignedZoneKeys: {},
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
    //
    // EXCEPT for a zone the user has aligned in this session. Stamping over one of those
    // silently discarded hand alignment every time the editor was re-opened, and it was
    // worst on a *reshaped* zone: the template carries a rectangle, so the user's outline was
    // replaced by its own bounding box and the nodes they had placed simply disappeared.
    // Restoring from `localStorage` is what the stamp is meant to override; a live edit is
    // not. See `userAlignedZoneKeys`.
    const aligned = new Set(state.userAlignedZoneKeys[drawingId] || []);
    if (templateZones && Object.keys(templateZones).length > 0) {
      for (const [key, frac] of Object.entries(templateZones)) {
        if (frac && !aligned.has(key)) seeded[key] = normalizeFractions(frac);
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
    // Applying a template is an explicit, deliberate "use these boxes everywhere" decision,
    // so it clears the edit record: those boxes ARE the template now, and the next open
    // should stamp them rather than treat them as untouchable local work.
    const nextAligned = { ...state.userAlignedZoneKeys };
    delete nextAligned[drawingId];
    persistAlignedKeys(drawingId, null);
    return {
      customRegions: { ...state.customRegions, [drawingId]: seeded },
      pinnedZoneKeys: nextPinned,
      userAlignedZoneKeys: nextAligned,
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
    // This is the *user's* write path — seeding writes through `set` directly, never here —
    // so it is the right place to record that a zone must not be re-stamped from the
    // template. Persisted alongside the regions so it survives a restart; see
    // `userAlignedZoneKeys`.
    const touched = state.userAlignedZoneKeys[drawingId] || [];
    if (touched.includes(key)) {
      return { customRegions: { ...state.customRegions, [drawingId]: updated } };
    }
    const nextTouched = [...touched, key];
    persistAlignedKeys(drawingId, nextTouched);
    return {
      customRegions: { ...state.customRegions, [drawingId]: updated },
      userAlignedZoneKeys: { ...state.userAlignedZoneKeys, [drawingId]: nextTouched },
    };
  }),

  // Undo/redo of a single zone. Like `restoreDrawingRegions`, the restored box is the user's
  // own work and keeps its immunity to template re-stamping; a redo that reinstates a reshape
  // must not leave it flattenable on the next editor open. The one exception is a restore that
  // removes the box entirely — see the `bounds === null` branch.
  restoreCustomRegion: (drawingId, key, bounds) => set((state) => {
    if (!drawingId) return {};
    const forDrawing = state.customRegions[drawingId] || { ...DEFAULT_CUSTOM_REGIONS };
    const updated = { ...forDrawing };
    if (bounds === null) {
      delete updated[key];
    } else {
      updated[key] = bounds;
    }
    localStorage.setItem(`custom_regions_${drawingId}`, JSON.stringify(updated));

    const touched = state.userAlignedZoneKeys[drawingId] || [];

    // `bounds === null` is undoing the CREATION of a box, so the alignment record goes with
    // it — same rule as `regions === null` in `restoreDrawingRegions`. Keeping the mark left
    // the zone in the worst of both states: no box, and immune to the template that had one,
    // so the next editor open produced an empty zone the template should have filled.
    if (bounds === null) {
      if (!touched.includes(key)) {
        return { customRegions: { ...state.customRegions, [drawingId]: updated } };
      }
      const nextTouched = touched.filter((k) => k !== key);
      persistAlignedKeys(drawingId, nextTouched);
      return {
        customRegions: { ...state.customRegions, [drawingId]: updated },
        userAlignedZoneKeys: { ...state.userAlignedZoneKeys, [drawingId]: nextTouched },
      };
    }

    if (touched.includes(key)) {
      return { customRegions: { ...state.customRegions, [drawingId]: updated } };
    }
    const nextTouched = [...touched, key];
    persistAlignedKeys(drawingId, nextTouched);
    return {
      customRegions: { ...state.customRegions, [drawingId]: updated },
      userAlignedZoneKeys: { ...state.userAlignedZoneKeys, [drawingId]: nextTouched },
    };
  }),

  restoreDrawingRegions: (drawingId, regions, pinned) => set((state) => {
    if (!drawingId) return {};
    const nextRegions = { ...state.customRegions };
    const nextPinned = { ...state.pinnedZoneKeys };

    if (regions === null) {
      delete nextRegions[drawingId];
      localStorage.removeItem(`custom_regions_${drawingId}`);
    } else {
      nextRegions[drawingId] = regions;
      localStorage.setItem(`custom_regions_${drawingId}`, JSON.stringify(regions));
    }

    if (pinned === null) {
      delete nextPinned[drawingId];
    } else {
      nextPinned[drawingId] = pinned;
    }

    // The restored boxes are the user's own work, so they must carry the same immunity to
    // template re-stamping that making them by hand would have. Without this, undoing a Reset
    // brought the alignment back and then the next editor open flattened it again — the boxes
    // returned, their protection did not. `regions === null` is the "never aligned" state, so
    // the record goes with them.
    const nextAligned = { ...state.userAlignedZoneKeys };
    if (regions === null) {
      delete nextAligned[drawingId];
      persistAlignedKeys(drawingId, null);
    } else {
      nextAligned[drawingId] = Object.keys(regions);
      persistAlignedKeys(drawingId, nextAligned[drawingId]);
    }

    return {
      customRegions: nextRegions,
      pinnedZoneKeys: nextPinned,
      userAlignedZoneKeys: nextAligned,
      // Mirrors resetCustomRegions: with no regions there is nothing seeded, so the editor is
      // free to re-seed from the detector next time it opens.
      hasSeededCustomRegions: regions !== null,
    };
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
    // Reset is an explicit "discard my alignment", so the protection against re-stamping
    // goes with it -- otherwise the zones the user had touched would be the only ones the
    // template could never reach again, which is the opposite of what Reset means.
    const nextAligned = { ...state.userAlignedZoneKeys };
    delete nextAligned[drawingId];
    persistAlignedKeys(drawingId, null);
    return {
      customRegions: next,
      pinnedZoneKeys: nextPinned,
      userAlignedZoneKeys: nextAligned,
      hasSeededCustomRegions: false,
    };
  }),

  loadCustomRegions: (drawingId) => set((state) => {
    if (!drawingId) return { drawingId: null };
    const saved = localStorage.getItem(`custom_regions_${drawingId}`);
    if (!saved) return { drawingId };
    try {
      // The aligned-key record is restored with the regions, and this is the whole reason it
      // is persisted: without it a restart made every hand-aligned box look like a detector
      // seed again, so the template stamped over it and the user's work "went back to
      // default". See `userAlignedZoneKeys`.
      return {
        drawingId,
        customRegions: { ...state.customRegions, [drawingId]: JSON.parse(saved) },
        userAlignedZoneKeys: {
          ...state.userAlignedZoneKeys,
          [drawingId]: readAlignedKeys(drawingId),
        },
      };
    } catch {
      // Corrupt entry: drop it rather than leaving a poisoned key that fails every load.
      localStorage.removeItem(`custom_regions_${drawingId}`);
      persistAlignedKeys(drawingId, null);
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
