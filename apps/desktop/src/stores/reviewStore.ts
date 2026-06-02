import { create } from 'zustand';

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
  customRegions: Record<string, { xMin: number; xMax: number; yMin: number; yMax: number }>;
  updateCustomRegion: (key: string, bounds: { xMin: number; xMax: number; yMin: number; yMax: number }) => void;
  resetCustomRegions: () => void;
  loadCustomRegions: (drawingId: string | null) => void;

  // Context Menu Marker Filters
  visibleMarkerTypes: Record<string, boolean>;
  toggleMarkerTypeVisibility: (type: string) => void;
}

export const useReviewStore = create<ReviewState>((set) => ({
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
  showMarkerLabels: true,
  toggleMarkerLabels: () => set((state) => ({ showMarkerLabels: !state.showMarkerLabels })),
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
  customRegions: {
    views: { xMin: 0.05, xMax: 0.65, yMin: 0.15, yMax: 0.85 },
    notes: { xMin: 0.05, xMax: 0.35, yMin: 0.20, yMax: 0.60 },
    bom: { xMin: 0.65, xMax: 0.98, yMin: 0.05, yMax: 0.42 },
    title: { xMin: 0.40, xMax: 0.98, yMin: 0.75, yMax: 0.98 },
    iso: { xMin: 0.65, xMax: 0.98, yMin: 0.45, yMax: 0.72 }
  },
  updateCustomRegion: (key, bounds) => set((state) => {
    const updated = {
      ...state.customRegions,
      [key]: bounds
    };
    if (state.drawingId) {
      localStorage.setItem(`custom_regions_${state.drawingId}`, JSON.stringify(updated));
    }
    return { customRegions: updated };
  }),
  resetCustomRegions: () => set((state) => {
    if (state.drawingId) {
      localStorage.removeItem(`custom_regions_${state.drawingId}`);
    }
    return {
      customRegions: {
        views: { xMin: 0.05, xMax: 0.65, yMin: 0.15, yMax: 0.85 },
        notes: { xMin: 0.05, xMax: 0.35, yMin: 0.20, yMax: 0.60 },
        bom: { xMin: 0.65, xMax: 0.98, yMin: 0.05, yMax: 0.42 },
        title: { xMin: 0.40, xMax: 0.98, yMin: 0.75, yMax: 0.98 },
        iso: { xMin: 0.65, xMax: 0.98, yMin: 0.45, yMax: 0.72 }
      }
    };
  }),
  loadCustomRegions: (drawingId) => {
    if (!drawingId) {
      set({
        drawingId: null,
        customRegions: {
          views: { xMin: 0.05, xMax: 0.65, yMin: 0.15, yMax: 0.85 },
          notes: { xMin: 0.05, xMax: 0.35, yMin: 0.20, yMax: 0.60 },
          bom: { xMin: 0.65, xMax: 0.98, yMin: 0.05, yMax: 0.42 },
          title: { xMin: 0.40, xMax: 0.98, yMin: 0.75, yMax: 0.98 },
          iso: { xMin: 0.65, xMax: 0.98, yMin: 0.45, yMax: 0.72 }
        }
      });
      return;
    }
    const saved = localStorage.getItem(`custom_regions_${drawingId}`);
    if (saved) {
      try {
        set({ drawingId, customRegions: JSON.parse(saved) });
      } catch (e) {
        set({
          drawingId,
          customRegions: {
            views: { xMin: 0.05, xMax: 0.65, yMin: 0.15, yMax: 0.85 },
            notes: { xMin: 0.05, xMax: 0.35, yMin: 0.20, yMax: 0.60 },
            bom: { xMin: 0.65, xMax: 0.98, yMin: 0.05, yMax: 0.42 },
            title: { xMin: 0.40, xMax: 0.98, yMin: 0.75, yMax: 0.98 },
            iso: { xMin: 0.65, xMax: 0.98, yMin: 0.45, yMax: 0.72 }
          }
        });
      }
    } else {
      set({
        drawingId,
        customRegions: {
          views: { xMin: 0.05, xMax: 0.65, yMin: 0.15, yMax: 0.85 },
          notes: { xMin: 0.05, xMax: 0.35, yMin: 0.20, yMax: 0.60 },
          bom: { xMin: 0.65, xMax: 0.98, yMin: 0.05, yMax: 0.42 },
          title: { xMin: 0.40, xMax: 0.98, yMin: 0.75, yMax: 0.98 },
          iso: { xMin: 0.65, xMax: 0.98, yMin: 0.45, yMax: 0.72 }
        }
      });
    }
  },

  visibleMarkerTypes: {
    MISMATCHED: true,
    CHANGED: true,
    ADDED: true,
    MATCHED: false
  },
  toggleMarkerTypeVisibility: (type) => set((state) => ({
    visibleMarkerTypes: {
      ...state.visibleMarkerTypes,
      [type]: !state.visibleMarkerTypes[type]
    }
  }))
}));
