import { create } from "zustand";

/**
 * Where the app looks for the backend before anyone changes it.
 *
 * ⚠ **This must be permitted by the `connect-src` in `src-tauri/tauri.conf.json`.** The CSP is
 * enforced by the webview, so a default the CSP does not allow fails *before the request leaves
 * the app* — no network error, no backend log, nothing to debug against. The two used to be
 * separate literals that happened to agree, and `connectionStore.csp.test.ts` now pins that they
 * still do.
 *
 * ⚠ **The port is not fixed.** `.env` documents `SIDECAR_PORT=0` for dynamic allocation, and
 * `services/backend/config.py` honours it, so the running backend legitimately answers on a port
 * nothing can predict at build time. That is why the CSP allows `http://127.0.0.1:*` rather than
 * pinning 8080 — pinning would make the documented dynamic-port mode permanently unreachable, and
 * would make the offline overlay's address field unable to fix the very mismatch it exists for.
 */
export const DEFAULT_BACKEND_URL = "http://127.0.0.1:8080";

/** Where a user-chosen backend address is remembered. */
export const BACKEND_URL_STORAGE_KEY = "ai_2d_backend_url";

export type ConnectionStatus =
  | "online"
  | "offline"
  | "connecting"
  | "reconnecting"
  | "failed"
  | "invalid";

interface ConnectionState {
  backendUrl: string;
  status: ConnectionStatus;
  version: string | null;
  lastChecked: number | null;
  error: string | null;
  pollingIntervalId: number | null;
  apiToken: string | null;
  failedAttempts: number;
  /** One bundled-backend start attempt per app session; see the offline branch of checkHealth. */
  backendStartAttempted: boolean;

  // Actions
  setBackendUrl: (url: string) => void;
  checkHealth: () => Promise<boolean>;
  startPolling: (intervalMs?: number) => void;
  stopPolling: () => void;
  fetchApiToken: () => Promise<string | null>;
  /** Discard the cached token and read it again. See the 401 path in `fetchUtils`. */
  refreshApiToken: () => Promise<string | null>;
}

export const useConnectionStore = create<ConnectionState>((set, get) => ({
  backendUrl: localStorage.getItem(BACKEND_URL_STORAGE_KEY) || DEFAULT_BACKEND_URL,
  status: "connecting",
  version: null,
  lastChecked: null,
  error: null,
  pollingIntervalId: null,
  apiToken: (typeof window !== "undefined" && !(window as any).__TAURI_INTERNALS__) ? localStorage.getItem("ai_2d_api_token") : null,
  failedAttempts: 0,
  backendStartAttempted: false,
  setBackendUrl: (url: string) => {
    // Sanitize trailing slash
    const sanitizedUrl = url.endsWith("/") ? url.slice(0, -1) : url;
    localStorage.setItem(BACKEND_URL_STORAGE_KEY, sanitizedUrl);
    set({ backendUrl: sanitizedUrl, status: "connecting", error: null, failedAttempts: 0 });
    get().checkHealth();
  },

  /**
   * Force a re-read of the API token.
   *
   * The token is cached for the life of the app once fetched, which is right until it changes
   * underneath us -- a backend restart against different storage, a reinstall, or two backends
   * publishing to the same per-user path. Then every request 401s and the ONLY cure is restarting
   * the app, with an error that says "Invalid security API Token" and nothing about why.
   *
   * Observed exactly that: the packaged sidecar and a development backend both publish to
   * `%LOCALAPPDATA%/kmti-2d-checker/secure/.api-token`, so whichever started last owned it, and an
   * app opened before that point held a token the running backend had never issued.
   */
  refreshApiToken: async () => {
    set({ apiToken: null });
    return await get().fetchApiToken();
  },

  fetchApiToken: async () => {
    if (typeof window !== "undefined" && (window as any).__TAURI_INTERNALS__) {
      try {
        const { invoke } = await import("@tauri-apps/api/core");
        const token = await invoke<string>("get_api_token");
        set({ apiToken: token });
        return token;
      } catch (err) {
        console.warn("Failed to retrieve API Token from Tauri shell:", err);
      }
    }
    
    // Fallback for standard browser development (non-Tauri)
    if (typeof window !== "undefined") {
      const storedToken = localStorage.getItem("ai_2d_api_token");
      if (storedToken) {
        set({ apiToken: storedToken });
        return storedToken;
      } else {
        console.warn("API Token is missing. If you are developing in a standard browser (not Tauri), please manually set it: localStorage.setItem('ai_2d_api_token', '<token_from_.api-token>')");
      }
    }
    
    return null;
  },

  checkHealth: async () => {
    const { backendUrl, status, apiToken, failedAttempts } = get();

    // Auto-fetch token on mount if not retrieved yet
    let activeToken = apiToken;
    if (!activeToken) {
      activeToken = await get().fetchApiToken();
    }

    // Set status to reconnecting only if we were confirmed offline (>= 3 consecutive failures)
    if (status === "offline") {
      set({ status: "reconnecting" });
    } else if (status !== "reconnecting" && status !== "online") {
      set({ status: "connecting" });
    }

    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 8000); // 8-second timeout for local headroom

      const headers: Record<string, string> = { "Accept": "application/json" };
      if (activeToken) {
        headers["Authorization"] = `Bearer ${activeToken}`;
      }

      const response = await fetch(`${backendUrl}/health`, {
        signal: controller.signal,
        headers,
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        const nextFailed = failedAttempts + 1;
        if (nextFailed < 3 && status === "online") {
          // Grace period: ignore transient 1st or 2nd spike without dropping UI to offline
          set({ failedAttempts: nextFailed, lastChecked: Date.now() });
          return false;
        }

        set({
          status: "failed",
          error: `HTTP Error: ${response.status} - ${response.statusText}`,
          lastChecked: Date.now(),
          failedAttempts: nextFailed,
        });
        return false;
      }

      const data = await response.json();

      if (data && (data.status === "healthy" || data.status === "degraded")) {
        set({
          status: "online",
          version: data.version || "1.0.0",
          error: null,
          lastChecked: Date.now(),
          failedAttempts: 0,
        });
        return true;
      } else {
        const nextFailed = failedAttempts + 1;
        if (nextFailed < 3 && status === "online") {
          set({ failedAttempts: nextFailed, lastChecked: Date.now() });
          return false;
        }

        set({
          status: "invalid",
          error: "Invalid health payload received from backend.",
          lastChecked: Date.now(),
          failedAttempts: nextFailed,
        });
        return false;
      }
    } catch (err: any) {
      const nextFailed = failedAttempts + 1;
      if (nextFailed < 3 && status === "online") {
        // Grace period: keep current online status on isolated timeout / busy tick
        set({ failedAttempts: nextFailed, lastChecked: Date.now() });
        return false;
      }

      const errorMsg = err.name === "AbortError"
        ? "Connection timeout. Backend service unresponsive."
        : "Failed to connect to local standalone backend.";

      set({
        status: "offline",
        error: errorMsg,
        lastChecked: Date.now(),
        failedAttempts: nextFailed,
      });

      /*
        Confirmed offline -- try to start the bundled backend.

        The installer registers a logon Scheduled Task, which covers the normal case. This covers
        the rest: the task not firing, the backend having crashed, or a post-install hook that
        failed. Without it the app sits on "Connection Lost" indefinitely and the only way forward
        is an engineer opening Task Scheduler.

        ⚠ ONCE per app session, not once per poll. `checkHealth` runs every 5 seconds; retrying
        each time would spawn a process every 5 seconds against a backend that is simply slow to
        start -- and it IS slow, tens of seconds for the Atlas connection and index bootstrap. One
        attempt, then let the existing polling notice when it comes up.

        Errors are swallowed on purpose: in a dev run there is no bundled backend and the command
        says so, which is not a condition worth surfacing to a developer who started their own.
      */
      if (!get().backendStartAttempted && typeof window !== "undefined" && (window as any).__TAURI_INTERNALS__) {
        set({ backendStartAttempted: true });
        try {
          const { invoke } = await import("@tauri-apps/api/core");
          const result = await invoke<string>("start_backend");
          console.info("[connection] start_backend:", result);
        } catch (startErr) {
          console.warn("[connection] could not start the bundled backend:", startErr);
        }
      }

      return false;
    }
  },

  startPolling: (intervalMs = 5000) => {
    // Clear any existing poll first
    get().stopPolling();

    // Trigger initial check immediately
    get().checkHealth();

    const intervalId = window.setInterval(() => {
      get().checkHealth();
    }, intervalMs);

    set({ pollingIntervalId: intervalId });
  },

  stopPolling: () => {
    const { pollingIntervalId } = get();
    if (pollingIntervalId) {
      clearInterval(pollingIntervalId);
      set({ pollingIntervalId: null });
    }
  },
}));
