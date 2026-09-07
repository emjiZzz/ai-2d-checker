import { describe, it, expect, beforeEach, vi } from "vitest";

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import { DEFAULT_REMOTE_API_TOKEN, useConnectionStore } from "./connectionStore";
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

/**
 * No credential may be a string literal in this file.
 *
 * `PROD_CLOUD_TOKEN = "kmti-cloud-token-2026-secret"` lived here and was the real bearer token for
 * the live cloud backend, so it was in the repository and in every installer built from it.
 * Anyone holding either had full read and write on every drawing and marking, and rotating it
 * meant a code change and a reissued installer.
 *
 * This asserts on the source text rather than on behaviour, like `features.test.ts`, because a
 * baked credential and an injected one behave identically -- that is exactly why the literal
 * survived as long as it did.
 */
describe("the remote API token", () => {
  const SOURCE = readFileSync(
    join(dirname(fileURLToPath(import.meta.url)), "connectionStore.ts"),
    "utf8",
  );

  it("is never a string literal assigned to a credential-shaped constant", () => {
    const assignments = [
      ...SOURCE.matchAll(/(?:export\s+)?const\s+(\w*(?:TOKEN|SECRET|KEY|PASSWORD|CREDENTIAL)\w*)\s*=\s*(["'`])([^"'`]*)\2/gi),
    ]
      .filter(([, , , value]) => value.trim() !== "")
      // A `*_STORAGE_KEY` is the NAME of a localStorage slot, not a secret. Its value is meant to
      // be a stable literal -- changing it orphans what every installed build already stored.
      .filter(([, name]) => !/STORAGE_KEY$/.test(name));

    expect(
      assignments.map(([, name, , value]) => `${name} = ${JSON.stringify(value)}`),
    ).toEqual([]);
  });

  it("carries no literal that looks like a shared secret", () => {
    const suspicious = [...SOURCE.matchAll(/["'`]([^"'`\s]*(?:secret|passwd|password)[^"'`\s]*)["'`]/gi)]
      .map((m) => m[1])
      // A storage key or an env var name may legitimately contain the word.
      .filter((v) => !/^[A-Z_]+$/.test(v));

    expect(suspicious).toEqual([]);
  });

  it("is empty when the build environment did not set one", () => {
    // vitest runs with VITE_REMOTE_API_TOKEN unset, which is exactly an unconfigured build. Under
    // those same conditions this used to resolve to the baked literal, so the assertion is the
    // difference. Read from the module binding rather than re-importing under a stubbed env: the
    // constant is evaluated once at module load, so a later stub could not change it and a test
    // that appeared to prove otherwise would be proving nothing.
    expect(import.meta.env.VITE_REMOTE_API_TOKEN ?? "").toBe("");
    expect(DEFAULT_REMOTE_API_TOKEN).toBe("");
  });
});
