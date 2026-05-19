import { create } from "zustand";

interface ThemeState {
  theme: "hc-dark" | "hc-light";
  toggleTheme: () => void;
  setTheme: (theme: "hc-dark" | "hc-light") => void;
  initialize: () => void;
}

export const useThemeStore = create<ThemeState>((set, get) => ({
  theme: (localStorage.getItem("theme") as "hc-dark" | "hc-light") || "hc-dark",
  toggleTheme: () => {
    const newTheme = get().theme === "hc-dark" ? "hc-light" : "hc-dark";
    set({ theme: newTheme });
    localStorage.setItem("theme", newTheme);
    document.documentElement.setAttribute("data-theme", newTheme);
  },
  setTheme: (theme) => {
    set({ theme });
    localStorage.setItem("theme", theme);
    document.documentElement.setAttribute("data-theme", theme);
  },
  initialize: () => {
    const theme = get().theme;
    document.documentElement.setAttribute("data-theme", theme);
  }
}));
