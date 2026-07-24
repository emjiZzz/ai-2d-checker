import { create } from "zustand";
import { useConnectionStore } from "./connectionStore";

// Guarded dynamic import, matching the pattern connectionStore.ts's
// fetchApiToken already uses — this frontend can also run under plain
// `vite dev` without the Tauri shell, where @tauri-apps/api/core's invoke
// has nothing to talk to. Returns null instead of throwing in that case.
async function tauriInvoke<T>(cmd: string, args?: Record<string, unknown>): Promise<T | null> {
  if (typeof window === "undefined" || !(window as any).__TAURI_INTERNALS__) {
    return null;
  }
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<T>(cmd, args);
}

export interface UserAccount {
  id: string;
  username: string;
  role: "admin" | "user";
  permissions: string[];
  created_at: string;
}

interface AuthState {
  user: UserAccount | null;
  sessionToken: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  // True only during the initial session restore on app launch. Distinct from
  // isLoading (which covers the login form's submit spinner) so App.tsx can
  // gate its first render without touching LoginPage's existing behavior.
  isInitializing: boolean;
  error: string | null;

  // Actions
  login: (username: string, password: string) => Promise<boolean>;
  logout: () => Promise<void>;
  initialize: () => Promise<boolean>;
  clearError: () => void;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  sessionToken: null,
  isAuthenticated: false,
  isLoading: false,
  isInitializing: true,
  error: null,

  clearError: () => set({ error: null }),

  login: async (username, password) => {
    set({ isLoading: true, error: null });
    const { backendUrl, apiToken } = useConnectionStore.getState();

    try {
      const headers: Record<string, string> = {
        "Content-Type": "application/json",
        "Accept": "application/json",
      };
      if (apiToken) {
        headers["Authorization"] = `Bearer ${apiToken}`;
      }

      const response = await fetch(`${backendUrl}/api/v1/auth/login`, {
        method: "POST",
        headers,
        body: JSON.stringify({ username, password }),
      });

      const resData = await response.json();

      if (!response.ok || !resData.success) {
        const errorMsg = resData.error?.message || "Invalid credentials or account disabled.";
        set({ error: errorMsg, isLoading: false });
        return false;
      }

      const { session_token, username: resUser, role } = resData.data;

      // Persist session via Tauri's AES-256-GCM-encrypted secure storage
      // (Phase 10, frontend remediation plan) instead of plaintext localStorage.
      try {
        await tauriInvoke("save_session", { token: session_token, username: resUser, role });
      } catch (persistErr: any) {
        // Non-fatal: session still works for this run, it just won't survive
        // a restart. Surface it in the console rather than blocking login.
        console.warn("Failed to persist session to secure storage:", persistErr);
      }

      // Verify and fetch complete profile
      const profileHeaders: Record<string, string> = {
        "Accept": "application/json",
        "X-Session-Token": session_token,
      };
      if (apiToken) {
        profileHeaders["Authorization"] = `Bearer ${apiToken}`;
      }

      const profileResponse = await fetch(`${backendUrl}/api/v1/auth/me`, {
        headers: profileHeaders,
      });

      const profileData = await profileResponse.json();

      if (profileResponse.ok && profileData.success) {
        const profile = profileData.data;
        set({
          user: profile,
          sessionToken: session_token,
          isAuthenticated: true,
          isLoading: false,
          error: null,
        });
        return true;
      } else {
        set({
          user: {
            id: "local",
            username: resUser,
            role: role as "admin" | "user",
            permissions: role === "admin" ? ["all"] : ["audit"],
            created_at: new Date().toISOString(),
          },
          sessionToken: session_token,
          isAuthenticated: true,
          isLoading: false,
          error: null,
        });
        return true;
      }
    } catch (err: any) {
      set({
        error: "Failed to connect to authentication server. Check local backend.",
        isLoading: false,
      });
      return false;
    }
  },

  logout: async () => {
    // Revoke the session server-side (best-effort) before wiping local state,
    // so the token can't still be replayed against the API after this device
    // says "logged out" — see services/backend/api/routers/auth.py::logout_user.
    // Non-fatal on failure: an unreachable/offline backend must not block the
    // user from logging out locally.
    const { sessionToken } = get();
    if (sessionToken) {
      try {
        const { backendUrl, apiToken } = useConnectionStore.getState();
        const headers: Record<string, string> = { "X-Session-Token": sessionToken };
        if (apiToken) {
          headers["Authorization"] = `Bearer ${apiToken}`;
        }
        await fetch(`${backendUrl}/api/v1/auth/logout`, { method: "POST", headers });
      } catch (err) {
        console.warn("Failed to revoke session server-side:", err);
      }
    }

    try {
      await tauriInvoke("clear_session");
    } catch (err) {
      console.warn("Failed to clear persisted session:", err);
    }

    set({
      user: null,
      sessionToken: null,
      isAuthenticated: false,
      error: null,
    });

    // Hard reload the frontend to cleanly wipe all Zustand store memory (workspace, audit, admin)
    // preventing data leaks between user accounts.
    setTimeout(() => {
      window.location.reload();
    }, 50);
  },

  initialize: async () => {
    let session: { token: string; username: string; role: string } | null = null;
    try {
      session = await tauriInvoke("load_session");
    } catch (err) {
      console.warn("Failed to load persisted session:", err);
    }

    if (!session) {
      set({ isAuthenticated: false, isLoading: false, isInitializing: false });
      return false;
    }

    const sessionToken = session.token;
    set({ isLoading: true });
    const { backendUrl, apiToken } = useConnectionStore.getState();

    const headers: Record<string, string> = {
      "Accept": "application/json",
      "X-Session-Token": sessionToken,
    };
    if (apiToken) {
      headers["Authorization"] = `Bearer ${apiToken}`;
    }

    let response;
    try {
      response = await fetch(`${backendUrl}/api/v1/auth/me`, {
        headers,
      });
    } catch (err) {
      // Offline fallback: load cached details only on actual network/connection failure.
      // Intentional UI-only trust decision — this only affects what role-gated UI renders
      // while offline. It does NOT bypass auth: every protected backend request still goes
      // through get_current_user's server-side session-token verification, which will reject
      // this cached role if it doesn't match a real, valid session. Not a security bug.
      const { username, role } = session;
      if (username && role) {
        set({
          user: {
            id: "local",
            username,
            role: role as "admin" | "user",
            permissions: role === "admin" ? ["all"] : ["audit"],
            created_at: new Date().toISOString(),
          },
          sessionToken,
          isAuthenticated: true,
          isLoading: false,
          isInitializing: false,
        });
        return true;
      }
      set({ isLoading: false, isInitializing: false });
      return false;
    }

    try {
      const resData = await response.json();
      if (response.ok && resData.success) {
        set({
          user: resData.data,
          sessionToken,
          isAuthenticated: true,
          isLoading: false,
          isInitializing: false,
        });
        return true;
      } else {
        // Token has expired or is invalid
        await get().logout();
        set({ isLoading: false, isInitializing: false });
        return false;
      }
    } catch (parseErr) {
      // Treat server JSON syntax/parsing errors as invalid sessions and log out
      await get().logout();
      set({ isLoading: false, isInitializing: false });
      return false;
    }
  },
}));
