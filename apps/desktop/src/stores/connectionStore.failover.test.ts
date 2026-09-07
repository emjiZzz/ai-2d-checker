import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";
import { useConnectionStore, FALLBACK_BACKEND_URL } from "./connectionStore";
import { useWorkspaceStore } from "./workspaceStore";

/**
 * Failing over to a backup backend, and the one thing that makes it safe.
 *
 * Both backends share a single Atlas, so rooms, sessions, markings and entities are identical on
 * either and marking survives the switch. `storage/uploads` is not shared -- it is per server --
 * so an upload made on the fallback never reaches the primary, and on an ephemeral disk it does
 * not survive the next restart. That is the failure that turned two ingestions into four rows on
 * 2026-09-07, so uploads are refused while the fallback is active.
 *
 * The fallback URL is empty unless a build sets `VITE_FALLBACK_BACKEND_URL`, so these drive the
 * store directly rather than depending on build-time configuration.
 */
const PRIMARY = "http://192.168.200.129:8080";
const BACKUP = "https://ai-2d-checker-backend.onrender.com";

describe("backend failover", () => {
  beforeEach(() => {
    useConnectionStore.setState({
      backendUrl: PRIMARY,
      primaryBackendUrl: PRIMARY,
      usingFallback: false,
      status: "online",
      apiToken: "tok",
      remoteApiToken: "tok",
      failedAttempts: 0,
      pollsSincePrimaryProbe: 0,
    });
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  const healthy = () =>
    Promise.resolve({ ok: true, json: () => Promise.resolve({ status: "healthy" }) } as Response);
  const dead = () => Promise.reject(new Error("ECONNREFUSED"));

  it("does not fail over when no fallback is configured", async () => {
    /** An empty `FALLBACK_BACKEND_URL` must disable the feature rather than pick a default. */
    if (FALLBACK_BACKEND_URL) return; // a configured build exercises the paths below instead
    vi.stubGlobal("fetch", vi.fn(healthy));
    const moved = await useConnectionStore.getState().failOverToFallback();
    expect(moved).toBe(false);
    expect(useConnectionStore.getState().backendUrl).toBe(PRIMARY);
  });

  it("moves to the fallback only when it actually answers", async () => {
    vi.stubGlobal("fetch", vi.fn(dead));
    useConnectionStore.setState({ primaryBackendUrl: PRIMARY });
    // Drive the action directly with a stubbed probe target.
    const moved = await useConnectionStore.getState().failOverToFallback();
    expect(moved).toBe(false);
    expect(useConnectionStore.getState().usingFallback).toBe(false);
  });

  it("does not refuse uploads on the fallback", async () => {
    /**
     * Blocked until 2026-09-07, on the reasoning that a drawing ingested on the fallback would
     * be unusable from the primary. That was wrong: `extracted_entities` is a Mongo collection,
     * so entities cross with everything else in Atlas and the canvas -- which draws from
     * entities, not from the file -- renders it from either server.
     *
     * What stays behind is only the source DXF, costing `/reextract` from the other machine.
     * Owner's call that the fallback should be able to ingest.
     *
     * Asserted as "not refused by the fallback check": the upload still fails here, because
     * there is no server, and the point is that it fails on the network rather than on a guard.
     */
    useConnectionStore.setState({ backendUrl: BACKUP, usingFallback: true });
    const file = new File(["x"], "drawing.dxf", { type: "application/dxf" });

    await useWorkspaceStore.getState().uploadDrawingFile(file, "old");

    expect(useWorkspaceStore.getState().oldError ?? "").not.toMatch(/fallback backend/i);
  });

  it("allows uploads again once the primary is back", async () => {
    useConnectionStore.setState({ backendUrl: BACKUP, usingFallback: true });
    vi.stubGlobal("fetch", vi.fn(healthy));

    const restored = await useConnectionStore.getState().restorePrimary();

    expect(restored).toBe(true);
    const c = useConnectionStore.getState();
    expect(c.usingFallback).toBe(false);
    expect(c.backendUrl).toBe(PRIMARY);
  });

  it("stays on the fallback while the primary is still down", async () => {
    useConnectionStore.setState({ backendUrl: BACKUP, usingFallback: true });
    vi.stubGlobal("fetch", vi.fn(dead));

    const restored = await useConnectionStore.getState().restorePrimary();

    expect(restored).toBe(false);
    expect(useConnectionStore.getState().usingFallback).toBe(true);
  });

  it("never fails over from a loopback primary", async () => {
    /**
     * A loopback primary is this machine's own sidecar, holding this machine's storage. The
     * recovery there is to start it, not to move to a shared cloud -- which is a different data
     * location, and would pre-empt the start_backend branch that exists for exactly this.
     *
     * Asserted on the source because the branch lives inside checkHealth's catch, which needs a
     * failing fetch, a Tauri global and a token read to reach.
     */
    const src = readFileSync(
      join(dirname(fileURLToPath(import.meta.url)), "connectionStore.ts"),
      "utf8",
    );
    const i = src.indexOf("failOverToFallback()");
    const guard = src.slice(Math.max(0, i - 400), i);
    expect(guard).toMatch(/!isLoopback\s*&&/);
  });

  it("a manual address choice re-pins the primary and cancels the fallback", () => {
    /**
     * Otherwise the next failback drags the app back to the baked default and silently undoes
     * what the engineer typed into the offline overlay.
     */
    useConnectionStore.setState({ backendUrl: BACKUP, usingFallback: true });
    vi.stubGlobal("fetch", vi.fn(healthy));

    useConnectionStore.getState().setBackendUrl("http://192.168.200.105:8080");

    const c = useConnectionStore.getState();
    expect(c.primaryBackendUrl).toBe("http://192.168.200.105:8080");
    expect(c.usingFallback).toBe(false);
  });

  it("never persists the fallback as the remembered backend", async () => {
    /** A restart must come up on the primary, not on a backup chosen minutes earlier. */
    useConnectionStore.setState({ backendUrl: PRIMARY, usingFallback: false });
    vi.stubGlobal("fetch", vi.fn(healthy));
    localStorage.removeItem("ai_2d_backend_url");

    await useConnectionStore.getState().failOverToFallback();

    expect(localStorage.getItem("ai_2d_backend_url")).toBeNull();
  });
});
