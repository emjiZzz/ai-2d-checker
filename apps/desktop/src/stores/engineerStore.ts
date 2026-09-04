import { create } from "zustand";

import { isPrototypeMode } from "../config/features";

interface EngineerState {
  engineerName: string;
  isModalOpen: boolean;
  setEngineerName: (name: string) => void;
  setIsModalOpen: (open: boolean) => void;
  initialize: () => void;
}

const STORAGE_KEY = "kmti_engineer_name";

export const useEngineerStore = create<EngineerState>((set) => ({
  engineerName: localStorage.getItem(STORAGE_KEY) || "",
  isModalOpen: !localStorage.getItem(STORAGE_KEY),

  setEngineerName: (name: string) => {
    const trimmed = name.trim();
    if (trimmed) {
      localStorage.setItem(STORAGE_KEY, trimmed);
      set({ engineerName: trimmed, isModalOpen: false });
    }
  },

  setIsModalOpen: (open: boolean) => {
    set({ isModalOpen: open });
  },

  initialize: () => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      set({ engineerName: stored, isModalOpen: false });
    } else {
      set({ isModalOpen: true });
    }
  },
}));

/**
 * True while the engineer-identity prompt is covering the app and nothing behind it is usable.
 *
 * One definition, two readers — `RoomsView` (must not *start* the tour) and
 * `InteractiveTourOverlay` (must not *render* over the prompt). Written as a rule rather than
 * repeated, because the two would drift into disagreeing about when the app is ready, and the
 * symptom of that disagreement is a modal with another modal on top of it.
 *
 * **Prototype-scoped, and that is not incidental.** `App.tsx` renders `EngineerPromptModal`
 * only when `isPrototypeMode()`, while `isModalOpen` initialises to
 * `!localStorage.getItem(STORAGE_KEY)` regardless of mode. So in a full build a user who has
 * never entered a name has `isModalOpen === true` with no modal on screen — gating on the raw
 * flag there would suppress the onboarding tour permanently, for a prompt that does not exist.
 *
 * Resolved (false) means the prompt is finished with: either a name was submitted, or someone
 * with a name already stored dismissed it. Dismissing with no name closes the app instead, so
 * there is no third state to consider.
 */
export function useIsEngineerPromptBlocking(): boolean {
  const isModalOpen = useEngineerStore((s) => s.isModalOpen);
  return isPrototypeMode() && isModalOpen;
}
