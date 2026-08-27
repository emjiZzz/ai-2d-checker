/**
 * Tests for `useIsManualCheckRoom`.
 *
 * This hook is the single largest behavioural difference in a prototype build: it decides whether
 * the left panel is the comparison engine or the engineer's own marking list, whether the canvas
 * suppresses engine markers, and what the context menu offers. In prototype mode it is
 * unconditionally true, so **no comparison engine runs in a prototype build** — the opposite of
 * what `features.ts` used to claim.
 *
 * The store-subscription test is the one with a history: the hook used to read the flag and return
 * before calling `useRoomStore`, which is a conditional hook call. It was inert only because Vite
 * folds the flag to a build-time constant, and `eslint-plugin-react-hooks` is not installed here,
 * so nothing would have caught it if that ever changed.
 */
import { renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useIsManualCheckRoom } from "./useManualCheckRoom";
import { useRoomStore } from "../stores/roomStore";

const setRoomMode = (room_mode: string | null) => {
  useRoomStore.setState({
    activeRoom: room_mode === null ? null : ({ id: "r1", room_mode } as never),
  });
};

afterEach(() => {
  vi.unstubAllEnvs();
  setRoomMode(null);
});

describe("useIsManualCheckRoom — without the prototype flag", () => {
  it("follows the active room's mode", () => {
    setRoomMode("manual_check");
    expect(renderHook(() => useIsManualCheckRoom()).result.current).toBe(true);

    setRoomMode("ai_comparison");
    expect(renderHook(() => useIsManualCheckRoom()).result.current).toBe(false);
  });

  it("is false when no room is open", () => {
    setRoomMode(null);
    expect(renderHook(() => useIsManualCheckRoom()).result.current).toBe(false);
  });
});

describe("useIsManualCheckRoom — in a prototype build", () => {
  it("is true even for a room the backend calls an ai_comparison room", () => {
    vi.stubEnv("VITE_PROTOTYPE_MODE", "true");
    setRoomMode("ai_comparison");
    expect(renderHook(() => useIsManualCheckRoom()).result.current).toBe(true);
  });

  it("is true with no room open at all", () => {
    vi.stubEnv("VITE_PROTOTYPE_MODE", "true");
    setRoomMode(null);
    expect(renderHook(() => useIsManualCheckRoom()).result.current).toBe(true);
  });

  it("calls the same number of hooks whether or not the flag is set", () => {
    /**
     * The regression guard for the conditional hook call, and it has to be indirect: the returned
     * boolean is `true` under the old code and the new one, so no assertion on the VALUE can tell
     * them apart. What differs is the hook COUNT — the old body returned before `useRoomStore`,
     * so a prototype render used 0 hooks and a non-prototype render used 1.
     *
     * React itself is the oracle. Flip the flag between two renders of the same mounted hook and
     * a varying count raises "Rendered more hooks than during the previous render". Verified
     * non-vacuous by restoring the early return, which fails here exactly that way.
     */
    setRoomMode("ai_comparison");
    vi.stubEnv("VITE_PROTOTYPE_MODE", "true");

    const { result, rerender } = renderHook(() => useIsManualCheckRoom());
    expect(result.current).toBe(true);

    vi.stubEnv("VITE_PROTOTYPE_MODE", "false");
    rerender();

    expect(result.current).toBe(false);
  });
});
