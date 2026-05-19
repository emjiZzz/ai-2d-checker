import { create } from "zustand";
import { useConnectionStore } from "./connectionStore";

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
  error: string | null;

  // Actions
  login: (username: string, password: string) => Promise<boolean>;
  logout: () => void;
  initialize: () => Promise<boolean>;
  clearError: () => void;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  sessionToken: null,
  isAuthenticated: false,
  isLoading: false,
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

      // Persist session
      localStorage.setItem("ai_2d_session_token", session_token);
      localStorage.setItem("ai_2d_session_username", resUser);
      localStorage.setItem("ai_2d_session_role", role);

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

  logout: () => {
    localStorage.removeItem("ai_2d_session_token");
    localStorage.removeItem("ai_2d_session_username");
    localStorage.removeItem("ai_2d_session_role");
    set({
      user: null,
      sessionToken: null,
      isAuthenticated: false,
      error: null,
    });
  },

  initialize: async () => {
    const sessionToken = localStorage.getItem("ai_2d_session_token");
    if (!sessionToken) {
      set({ isAuthenticated: false, isLoading: false });
      return false;
    }

    set({ isLoading: true });
    const { backendUrl, apiToken } = useConnectionStore.getState();

    try {
      const headers: Record<string, string> = {
        "Accept": "application/json",
        "X-Session-Token": sessionToken,
      };
      if (apiToken) {
        headers["Authorization"] = `Bearer ${apiToken}`;
      }

      const response = await fetch(`${backendUrl}/api/v1/auth/me`, {
        headers,
      });

      const resData = await response.json();

      if (response.ok && resData.success) {
        set({
          user: resData.data,
          sessionToken,
          isAuthenticated: true,
          isLoading: false,
        });
        return true;
      } else {
        // Token has expired or is invalid
        get().logout();
        set({ isLoading: false });
        return false;
      }
    } catch (err) {
      // Offline fallback: load cached details if they exist to keep session alive local-first
      const username = localStorage.getItem("ai_2d_session_username");
      const role = localStorage.getItem("ai_2d_session_role") as "admin" | "user";
      if (username && role) {
        set({
          user: {
            id: "local",
            username,
            role,
            permissions: role === "admin" ? ["all"] : ["audit"],
            created_at: new Date().toISOString(),
          },
          sessionToken,
          isAuthenticated: true,
          isLoading: false,
        });
        return true;
      }
      set({ isLoading: false });
      return false;
    }
  },
}));
