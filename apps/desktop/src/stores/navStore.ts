import { create } from 'zustand';

export type NavTab = 'workspace' | '3d-workspace' | 'standards' | 'history' | 'settings';

interface NavState {
  currentNav: NavTab;
  setCurrentNav: (nav: NavTab) => void;
}

export const useNavStore = create<NavState>((set) => ({
  currentNav: 'workspace',
  setCurrentNav: (nav) => set({ currentNav: nav }),
}));
