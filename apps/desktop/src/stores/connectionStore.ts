import { create } from "zustand";

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

  // Actions
  setBackendUrl: (url: string) => void;
  checkHealth: () => Promise<boolean>;
  startPolling: (intervalMs?: number) => void;
  stopPolling: () => void;
  fetchApiToken: () => Promise<string | null>;
}

export const useConnectionStore = create<ConnectionState>((set, get) => ({
  // Set default standalone port matching environment loader
  backendUrl: localStorage.getItem("ai_2d_backend_url") || "http://127.0.0.1:8080",
  status: "connecting",
  version: null,
  lastChecked: null,
  error: null,
  pollingIntervalId: null,
  apiToken: (typeof window !== "undefined" && !(window as any).__TAURI_INTERNALS__) ? localStorage.getItem("ai_2d_api_token") : null,
  failedAttempts: 0,
  setBackendUrl: (url: string) => {
    // Sanitize trailing slash
    const sanitizedUrl = url.endsWith("/") ? url.slice(0, -1) : url;
    localStorage.setItem("ai_2d_backend_url", sanitizedUrl);
    set({ backendUrl: sanitizedUrl, status: "connecting", error: null, failedAttempts: 0 });
    get().checkHealth();
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
