/**
 * The app comes up light unless someone has chosen otherwise.
 *
 * ⚠ **In a prototype build the fallback is not a default, it is the theme.** `SettingsView` holds
 * the only control that writes `localStorage["theme"]`, and prototype mode hides the whole header
 * nav strip, so Settings cannot be reached and `setTheme` / `toggleTheme` can never be called.
 * Nothing else writes the key. So a change to the fallback is the entire user-visible behaviour
 * for every tester, on every launch — which is why it is worth a test rather than being obvious
 * from one line.
 *
 * The store reads localStorage at module-evaluation time, so each case re-imports it with
 * `vi.resetModules()`; setting the key after import would prove nothing.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

async function freshStore() {
  vi.resetModules();
  const mod = await import("./themeStore");
  return mod.useThemeStore;
}

beforeEach(() => {
  localStorage.removeItem("theme");
  document.documentElement.removeAttribute("data-theme");
  document.documentElement.classList.remove("dark", "light");
});

afterEach(() => {
  localStorage.removeItem("theme");
});

describe("the default theme", () => {
  it("is light when nothing has been stored", async () => {
    const useThemeStore = await freshStore();
    expect(useThemeStore.getState().theme).toBe("hc-light");
  });

  it("paints the document light on initialize", async () => {
    // The store holding "hc-light" is not the same as the page being light — `initialize` is what
    // puts the attribute and classes on <html>, and every themed component reads those.
    const useThemeStore = await freshStore();
    useThemeStore.getState().initialize();

    expect(document.documentElement.getAttribute("data-theme")).toBe("hc-light");
    expect(document.documentElement.classList.contains("light")).toBe(true);
    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });
});

describe("an explicit choice still wins", () => {
  it("keeps a stored dark preference", async () => {
    // What makes this a default rather than an override. Only reachable in a full build, where
    // Settings exists — but if this ever fails, the Settings picker has silently stopped
    // persisting anything.
    localStorage.setItem("theme", "hc-dark");
    const useThemeStore = await freshStore();

    expect(useThemeStore.getState().theme).toBe("hc-dark");
  });

  it("keeps a stored light preference", async () => {
    localStorage.setItem("theme", "hc-light");
    const useThemeStore = await freshStore();

    expect(useThemeStore.getState().theme).toBe("hc-light");
  });

  it("persists a toggle away from the default", async () => {
    const useThemeStore = await freshStore();
    useThemeStore.getState().toggleTheme();

    expect(useThemeStore.getState().theme).toBe("hc-dark");
    expect(localStorage.getItem("theme")).toBe("hc-dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
  });
});
