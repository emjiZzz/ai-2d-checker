import { create } from "zustand";

export interface TourStepInfo {
  stepIndex: number;
  badge: string;
  title: string;
  targetSelector: string;
  description: string;
  tips: string;
  position: "bottom" | "top" | "left" | "right" | "center";
}

export const TOUR_STEPS: TourStepInfo[] = [
  {
    stepIndex: 0,
    badge: "STEP 1 OF 6 • WORKSPACES",
    title: "1. Workspaces Hub",
    targetSelector: '[data-tour="rooms-gallery"]',
    description: "Workspaces organize your CAD drawing revisions. Cards display real vector linework previews for instant visual identification.",
    tips: "Click 'Enter Tutorial Room' to automatically create and open a new 'Tutorial Room' to begin onboarding.",
    position: "bottom",
  },
  {
    stepIndex: 1,
    badge: "STEP 2 OF 6 • REFERENCE DRAWING",
    title: "2. Upload Reference Drawing (Original DXF)",
    targetSelector: '[data-tour="upload-reference"]',
    description: "Upload the base or previous drawing in this Reference pane to serve as your comparison baseline.",
    tips: "Click 'browse' or drag & drop your original DXF file into the highlighted Reference dropzone.",
    position: "bottom",
  },
  {
    stepIndex: 2,
    badge: "STEP 3 OF 6 • REVISION DRAWING",
    title: "3. Upload Revision Drawing (New DXF)",
    targetSelector: '[data-tour="upload-revision"]',
    description: "Upload the updated revision CAD drawing here in the Revision pane to check against the baseline.",
    tips: "Click 'browse' or drag & drop your updated DXF file into the highlighted Revision dropzone.",
    position: "bottom",
  },
  {
    stepIndex: 3,
    badge: "STEP 4 OF 6 • CLASSIFY ENTITIES",
    title: "4. Left-Click: Assign Entity Status",
    targetSelector: '[data-tour="cad-canvas"]',
    description: "Left-click directly on any dimension, text line, or geometry in the drawings to open the status popup.",
    tips: "Assign MATCHED (identical), REMOVED (deleted in revision), ADDED (new in revision), or CHANGED (modified size/tolerance).",
    position: "top",
  },
  {
    stepIndex: 4,
    badge: "STEP 5 OF 6 • ANNOTATIONS",
    title: "5. Right-Click: Add Annotations",
    targetSelector: '[data-tour="cad-canvas"]',
    description: "Right-click anywhere on the drawing canvas to add custom annotations, defect flags, or reviewer notes.",
    tips: "Use right-click actions to highlight subtle discrepancies or document inspection comments.",
    position: "top",
  },
  {
    stepIndex: 5,
    badge: "STEP 6 OF 6 • Checklist Panel",
    title: "6. Checklist",
    targetSelector: '[data-tour="marking-tools"]',
    description: "All classified entities, physical differences, and ground truth findings are listed here in real-time.",
    tips: "Click any item in the list to automatically jump and center on its location in the drawing canvas.",
    position: "right",
  },
];

interface OnboardingState {
  isTourActive: boolean;
  currentStep: number;
  startTour: () => void;
  nextStep: () => void;
  prevStep: () => void;
  goToStep: (step: number) => void;
  endTour: () => void;
}

export const useOnboardingStore = create<OnboardingState>((set, get) => ({
  isTourActive: false,
  currentStep: 0,

  startTour: () => {
    set({ isTourActive: true, currentStep: 0 });
  },

  nextStep: () => {
    const { currentStep } = get();
    if (currentStep < TOUR_STEPS.length - 1) {
      set({ currentStep: currentStep + 1 });
    } else {
      get().endTour();
    }
  },

  prevStep: () => {
    const { currentStep } = get();
    if (currentStep > 0) {
      set({ currentStep: currentStep - 1 });
    }
  },

  goToStep: (step: number) => {
    if (step >= 0 && step < TOUR_STEPS.length) {
      set({ currentStep: step });
    }
  },

  endTour: () => {
    localStorage.setItem("has_seen_interactive_tour", "true");
    set({ isTourActive: false, currentStep: 0 });
  },
}));
