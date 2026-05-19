import { create } from "zustand";
import { useAuthStore } from "./authStore";

interface SessionState {
  expirationTime: number | null;
  checkIntervalId: number | null;
  
  // Actions
  startExpirationMonitor: (sessionToken: string) => void;
  stopExpirationMonitor: () => void;
}

export const useSessionStore = create<SessionState>((set, get) => ({
  expirationTime: null,
  checkIntervalId: null,

  startExpirationMonitor: (sessionToken) => {
    get().stopExpirationMonitor();
    
    try {
      console.debug("Starting expiration monitor for session token prefix:", sessionToken.slice(0, 8));
      // Decode JWT expiration payload (base64 decrypt fallback or parsing)
      // Since our token is AES encrypted, we let the backend authenticate,
      // but we can schedule a lightweight check or ping to make sure the session stays valid.
      const intervalId = window.setInterval(async () => {
        const { isAuthenticated, initialize, logout } = useAuthStore.getState();
        if (isAuthenticated) {
          const isValid = await initialize();
          if (!isValid) {
            console.warn("Session expired or became invalid. Logging out.");
            logout();
          }
        }
      }, 60000); // Check once per minute

      set({ checkIntervalId: intervalId });
    } catch (e) {
      console.error("Failed to parse session monitor parameters:", e);
    }
  },

  stopExpirationMonitor: () => {
    const { checkIntervalId } = get();
    if (checkIntervalId) {
      clearInterval(checkIntervalId);
      set({ checkIntervalId: null });
    }
  }
}));
