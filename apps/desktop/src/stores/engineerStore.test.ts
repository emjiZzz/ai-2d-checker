/**
 * The onboarding tour must wait for the engineer-identity prompt.
 *
 * Reported from the first launch of the built prototype installer: the Quick Tour opened
 * immediately, on top of the "AI CHECKER (PROTOTYPE) / TESTER NAME" prompt, before the tester had
 * entered anything. `RoomsView` mounts underneath `EngineerPromptModal` in a prototype build and
 * fired `startTour()` from a mount effect that knew nothing about the prompt.
 *
 * ⚠ **Not fixable by stacking order, which is why the rule is a render gate.** The prompt's
 * backdrop is `z-[100000]` and deliberately opaque ("Hides workspace completely for clean
 * presentation"); the tour is `z-[999999]`. Whichever wins, one modal is drawn over another. Only
 * one of them may render.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { renderHook } from "@testing-library/react";

import { useEngineerStore, useIsEngineerPromptBlocking } from "./engineerStore";

const STORAGE_KEY = "kmti_engineer_name";

beforeEach(() => {
  localStorage.removeItem(STORAGE_KEY);
  useEngineerStore.setState({ engineerName: "", isModalOpen: true });
});

afterEach(() => {
  vi.unstubAllEnvs();
  localStorage.removeItem(STORAGE_KEY);
});

const blocking = () => renderHook(() => useIsEngineerPromptBlocking()).result.current;

describe("useIsEngineerPromptBlocking — prototype build", () => {
  beforeEach(() => {
    vi.stubEnv("VITE_PROTOTYPE_MODE", "true");
  });

  it("blocks while the tester has not identified themselves", () => {
    expect(blocking()).toBe(true);
  });

  it("stops blocking once a name is submitted", () => {
    // The real transition: `setEngineerName` clears `isModalOpen`, which is what lets the
    // tour's effect re-run and start at the right moment.
    useEngineerStore.getState().setEngineerName("Raysan");

    expect(useEngineerStore.getState().isModalOpen).toBe(false);
    expect(blocking()).toBe(false);
  });

  it("stops blocking when someone with a stored name dismisses the prompt", () => {
    useEngineerStore.getState().setEngineerName("Raysan");
    useEngineerStore.getState().setIsModalOpen(true);
    expect(blocking()).toBe(true);

    useEngineerStore.getState().setIsModalOpen(false);
    expect(blocking()).toBe(false);
  });

  it("ignores a blank name rather than treating it as identification", () => {
    useEngineerStore.getState().setEngineerName("   ");

    expect(useEngineerStore.getState().engineerName).toBe("");
    expect(blocking()).toBe(true);
  });
});

describe("useIsEngineerPromptBlocking — full build", () => {
  it("never blocks, because the prompt is not rendered there at all", () => {
    /**
     * The half that is easy to get wrong. `App.tsx` renders `EngineerPromptModal` only under
     * `isPrototypeMode()`, but `isModalOpen` initialises from localStorage regardless of mode —
     * so a full-build user who has never entered a name sits at `isModalOpen === true` with no
     * modal on screen. Gating the tour on the raw flag would suppress onboarding permanently,
     * waiting on a prompt that cannot appear.
     */
    useEngineerStore.setState({ engineerName: "", isModalOpen: true });

    expect(blocking()).toBe(false);
  });
});
