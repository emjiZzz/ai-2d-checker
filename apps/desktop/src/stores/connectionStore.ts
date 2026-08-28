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
export const REMOTE_API_TOKEN_STORAGE_KEY = "ai_2d_remote_api_token";

/**
 * Predicate answering whether a backend address points to loopback.
 * Centralized so the timeout, token retrieval, and start_backend branches share one definition.
 */
export function isLoopbackBackend(url: string): boolean {
  try {
    const parsed = new URL(url);
    const host = parsed.hostname.toLowerCase();
    return host === "127.0.0.1" || host === "localhost" || host === "::1" || host === "[::1]";
  } catch {
    return false;
  }
}

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
  remoteApiToken: string | null;
  failedAttempts: number;
  /** One bundled-backend start attempt per app session; see the offline branch of checkHealth. */
  backendStartAttempted: boolean;

  // Actions
  setBackendUrl: (url: string) => void;
  setRemoteApiToken: (token: string) => void;
  checkHealth: () => Promise<boolean>;
  startPolling: (intervalMs?: number) => void;
  stopPolling: () => void;
  fetchApiToken: () => Promise<string | null>;
  /** Discard the cached token and read it again. See the 401 path in `fetchUtils`. */
  refreshApiToken: () => Promise<string | null>;
}

/**
 * The token read currently in flight, if any, so concurrent callers share one.
 *
 * Module scope rather than store state on purpose: it is a lock, not something the UI renders,
 * and putting a promise in a zustand store makes every subscriber re-render on a value none of
 * them can use.
 */
let inFlightTokenRead: Promise<string | null> | null = null;

export const useConnectionStore = create<ConnectionState>((set, get) => ({
  backendUrl: localStorage.getItem(BACKEND_URL_STORAGE_KEY) || DEFAULT_BACKEND_URL,
  status: "connecting",
  version: null,
  lastChecked: null,
  error: null,
  pollingIntervalId: null,
  apiToken: (typeof window !== "undefined" && !(window as any).__TAURI_INTERNALS__)
    ? (localStorage.getItem(REMOTE_API_TOKEN_STORAGE_KEY) || localStorage.getItem("ai_2d_api_token"))
    : null,
  remoteApiToken: typeof window !== "undefined" ? localStorage.getItem(REMOTE_API_TOKEN_STORAGE_KEY) : null,
  failedAttempts: 0,
  backendStartAttempted: false,
  setBackendUrl: (url: string) => {
    // Sanitize trailing slash
    const sanitizedUrl = url.endsWith("/") ? url.slice(0, -1) : url;
    localStorage.setItem(BACKEND_URL_STORAGE_KEY, sanitizedUrl);
    set({ backendUrl: sanitizedUrl, status: "connecting", error: null, failedAttempts: 0 });
    get().checkHealth();
  },
  setRemoteApiToken: (token: string) => {
    const trimmed = token.trim();
    if (trimmed) {
      localStorage.setItem(REMOTE_API_TOKEN_STORAGE_KEY, trimmed);
      set({ remoteApiToken: trimmed, apiToken: trimmed });
    } else {
      localStorage.removeItem(REMOTE_API_TOKEN_STORAGE_KEY);
      set({ remoteApiToken: null, apiToken: null });
    }
    get().checkHealth();
  },

  /**
   * Force a re-read of the API token, replacing the cached one in place.
   *
   * The token is cached for the life of the app once fetched, which is right until it changes
   * underneath us -- a backend restart against different storage, a reinstall, or two backends
   * publishing to the same per-user path. Then every request 401s and the ONLY cure is restarting
   * the app, with an error that says "Invalid security API Token" and nothing about why.
   *
   * Observed exactly that: the packaged sidecar and a development backend both publish to
   * `%LOCALAPPDATA%/kmti-2d-checker/secure/.api-token`, so whichever started last owned it, and an
   * app opened before that point held a token the running backend had never issued.
   *
   * 🔴 **This used to `set({ apiToken: null })` first, and that null was itself a bug.** The
   * synchronous `buildHeaders()` -- 71 call sites, `createRoom` among them -- omits the
   * `Authorization` header entirely when the token is null rather than waiting for one. So between
   * the clear and the next successful read, requests went out UNAUTHENTICATED, and the backend
   * answered *"Access Denied: Missing Authorization Header"*: a different error, pointing at a
   * different subsystem, for the same underlying problem. Seen on the installed 0.1.8 build on
   * 2026-08-28, immediately after the stale-token defect it masked.
   *
   * Replacing in place is strictly better: the worst case is one more request carrying the token
   * we already know is wrong, which fails the way it already failed, while the read that fixes it
   * is in flight. A hole in the credential is not a safer state than a stale credential.
   */
  refreshApiToken: async () => {
    return await get().fetchApiToken();
  },

  fetchApiToken: async () => {
    // Coalesce concurrent reads. Every 401 asks for a refresh and a failing screen issues several
    // requests at once, so without this one rejected token becomes a burst of identical reads of
    // the same file -- and, worse, several in-flight writes racing to set the same state.
    if (inFlightTokenRead) return inFlightTokenRead;
    inFlightTokenRead = (async () => {
      const { backendUrl, remoteApiToken } = get();

      // Remote backend: if not loopback and a remote token is set, return it directly
      // and never touch local Tauri get_api_token.
      if (!isLoopbackBackend(backendUrl)) {
        if (remoteApiToken) {
          set({ apiToken: remoteApiToken });
          return remoteApiToken;
        }
        if (typeof window !== "undefined") {
          const stored = localStorage.getItem(REMOTE_API_TOKEN_STORAGE_KEY) || localStorage.getItem("ai_2d_api_token");
          if (stored) {
            set({ apiToken: stored, remoteApiToken: stored });
            return stored;
          }
        }
        return null;
      }

      // Loopback backend via Tauri
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
    })();

    try {
      return await inFlightTokenRead;
    } finally {
      inFlightTokenRead = null;
    }
  },

  checkHealth: async () => {
    const { backendUrl, status, apiToken, failedAttempts } = get();
    const isLoopback = isLoopbackBackend(backendUrl);

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

    // Dynamic timeout: 8s for local loopback headroom, 45s for remote backend (e.g. Render spin-up)
    const timeoutMs = isLoopback ? 8000 : 45000;

    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

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
        ? `Connection timeout (${timeoutMs / 1000}s). Backend service unresponsive.`
        : isLoopback
          ? "Failed to connect to local standalone backend."
          : `Failed to connect to remote backend at ${backendUrl}.`;

      set({
        status: "offline",
        error: errorMsg,
        lastChecked: Date.now(),
        failedAttempts: nextFailed,
      });

      /*
        Confirmed offline -- try to start the bundled local backend ONLY if loopback.
        Remote backend failures must never spawn a local server on 8080.
      */
      if (isLoopback && !get().backendStartAttempted && typeof window !== "undefined" && (window as any).__TAURI_INTERNALS__) {
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

  startPolling: (intervalMs?: number) => {
    // Clear any existing poll first
    get().stopPolling();

    // Trigger initial check immediately
    get().checkHealth();

    const scheduleNext = () => {
      const { status, backendUrl } = get();
      const isLoopback = isLoopbackBackend(backendUrl);

      // Adaptive intervals:
      // Online: 20s for remote backend, 10s for local loopback
      // Disconnected/reconnecting: 5s for rapid recovery detection
      const nextDelay = intervalMs ?? (
        status === "online" ? (isLoopback ? 10000 : 20000) : 5000
      );

      const timeoutId = window.setTimeout(async () => {
        await get().checkHealth();
        scheduleNext();
      }, nextDelay);

      set({ pollingIntervalId: timeoutId });
    };

    scheduleNext();
  },

  stopPolling: () => {
    const { pollingIntervalId } = get();
    if (pollingIntervalId) {
      clearTimeout(pollingIntervalId);
      set({ pollingIntervalId: null });
    }
  },
}));
