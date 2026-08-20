import { create } from "zustand";

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
