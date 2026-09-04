import { describe, it, expect, beforeEach, vi } from "vitest";

import { useConnectionStore } from "./connectionStore";
import { buildHeaders, parseOrThrow } from "../services/fetchUtils";

const TOKEN_KEY = "ai_2d_api_token";

/**
 * The token cache must never be empty while the app is running.
 *
 * On 2026-08-28 an installed build showed two different errors for one cause. First
 * *"Access Denied: Invalid security API Token"* (a stale token file), and then, once the 401
 * self-heal had nulled the cache, *"Access Denied: Missing Authorization Header"* — because the
 * synchronous `buildHeaders()` omits the header rather than waiting for a token. The second error
 * names a different subsystem and sent the investigation sideways.
 */
describe("the API token cache", () => {
  beforeEach(() => {
    localStorage.clear();
    useConnectionStore.setState({ apiToken: null });
    vi.restoreAllMocks();
  });

  it("omits the Authorization header entirely when there is no token", () => {
    // Not the desired behaviour — the reason a null cache is dangerous. Pinned so the fix below
    // cannot be quietly reverted on the grounds that "buildHeaders handles it".
    useConnectionStore.setState({ apiToken: null });
    expect(buildHeaders()).not.toHaveProperty("Authorization");

    useConnectionStore.setState({ apiToken: "a-token" });
    expect(buildHeaders()).toHaveProperty("Authorization", "Bearer a-token");
  });

  it("keeps the rejected token in place on a 401 rather than punching a hole", async () => {
    localStorage.setItem(TOKEN_KEY, "the-current-token");
    useConnectionStore.setState({ apiToken: "the-stale-token" });

    const rejected = new Response(JSON.stringify({ detail: "Access Denied: Invalid security API Token." }), {
      status: 401,
      headers: { "Content-Type": "application/json" },
    });

    await expect(parseOrThrow(rejected)).rejects.toThrow("Invalid security API Token");

    // The moment that matters: a request issued right now must still carry a credential.
    expect(useConnectionStore.getState().apiToken).not.toBeNull();
    expect(buildHeaders()).toHaveProperty("Authorization");

    // And the re-read replaces it, so the next attempt carries the current one.
    await vi.waitFor(() => {
      expect(useConnectionStore.getState().apiToken).toBe("the-current-token");
    });
  });

  it("coalesces concurrent reads into one", async () => {
    // Every 401 asks for a refresh and a failing screen issues several requests at once.
    localStorage.setItem(TOKEN_KEY, "the-current-token");
    const getItem = vi.spyOn(Storage.prototype, "getItem");

    const results = await Promise.all([
      useConnectionStore.getState().fetchApiToken(),
      useConnectionStore.getState().fetchApiToken(),
      useConnectionStore.getState().fetchApiToken(),
    ]);

    expect(results).toEqual(["the-current-token", "the-current-token", "the-current-token"]);
    expect(getItem.mock.calls.filter(([key]) => key === TOKEN_KEY)).toHaveLength(1);
  });

  it("reads again on the next call once the in-flight read has settled", async () => {
    // The lock must clear, or a token that changes later can never be picked up.
    localStorage.setItem(TOKEN_KEY, "first");
    expect(await useConnectionStore.getState().fetchApiToken()).toBe("first");

    localStorage.setItem(TOKEN_KEY, "second");
    expect(await useConnectionStore.getState().refreshApiToken()).toBe("second");
  });
});
