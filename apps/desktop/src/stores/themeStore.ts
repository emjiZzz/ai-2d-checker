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
    document.documentElement.classList.toggle("dark", newTheme === "hc-dark");
    document.documentElement.classList.toggle("light", newTheme === "hc-light");
  },
  setTheme: (theme) => {
    set({ theme });
    localStorage.setItem("theme", theme);
    document.documentElement.setAttribute("data-theme", theme);
    document.documentElement.classList.toggle("dark", theme === "hc-dark");
    document.documentElement.classList.toggle("light", theme === "hc-light");
  },
  initialize: () => {
    const theme = get().theme;
    document.documentElement.setAttribute("data-theme", theme);
    document.documentElement.classList.toggle("dark", theme === "hc-dark");
    document.documentElement.classList.toggle("light", theme === "hc-light");
  }
}));
