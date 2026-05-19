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
  selectedViolationId: string | null;
  setSelectedViolation: (id: string | null) => void;
  
  // Comparison
  isComparisonMode: boolean;
  toggleComparisonMode: () => void;
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
  selectedViolationId: null,
  setSelectedViolation: (id) => set({ selectedViolationId: id }),
  
  isComparisonMode: false,
  toggleComparisonMode: () => set((state) => ({ isComparisonMode: !state.isComparisonMode }))
}));
