import { create } from "zustand";

interface ThemeState {
  theme: "hc-dark" | "hc-light";
  toggleTheme: () => void;
  setTheme: (theme: "hc-dark" | "hc-light") => void;
  initialize: () => void;
}

/**
 * What the app uses when nobody has chosen.
 *
 * **In a prototype build this is not a default, it is the theme.** The only control that writes
 * `localStorage["theme"]` is the picker in `SettingsView`, and prototype mode hides the entire
 * header nav strip — so Settings is unreachable, `currentNav` stays pinned to `workspace`, and
 * neither `setTheme` nor `toggleTheme` can ever be called. Nothing else writes the key, so the
 * fallback below is what every tester sees on every launch.
 *
 * Changed from `hc-dark` to `hc-light` on 2026-08-27 (owner's call) so the data-gathering build
 * comes up light for everyone.
 *
 * A full build still honours an explicit choice: someone who picks dark in Settings keeps dark,
 * which is what makes this a default rather than an override. If it ever needs to be a genuine
 * override, that is a different change — ignore the stored value here — and it would make the
 * Settings picker unable to persist anything.
 */
const DEFAULT_THEME = "hc-light" as const;

export const useThemeStore = create<ThemeState>((set, get) => ({
  theme: (localStorage.getItem("theme") as "hc-dark" | "hc-light") || DEFAULT_THEME,
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
