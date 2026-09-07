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

  it("refuses uploads while on the fallback, and says why", async () => {
    useConnectionStore.setState({ backendUrl: BACKUP, usingFallback: true });
    const file = new File(["x"], "drawing.dxf", { type: "application/dxf" });

    const ok = await useWorkspaceStore.getState().uploadDrawingFile(file, "old");

    expect(ok).toBe(false);
    const s = useWorkspaceStore.getState();
    expect(s.oldUploadState).toBe("failed");
    expect(s.oldError).toMatch(/fallback backend/i);
    // No drawing id, so the panel offers no retry: there is nothing on the server to re-extract.
    expect(s.oldFailedDrawingId).toBeNull();
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
