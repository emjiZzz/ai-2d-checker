import { useEffect, useRef } from "react";
import { useConnectionStore } from "./stores/connectionStore";
import { useAuthStore } from "./stores/authStore";
import { useThemeStore } from "./stores/themeStore";
import { LoginPage } from "./pages/auth/LoginPage";
import { AppHeader } from "./components/AppHeader";
import { ConnectionBanner } from "./components/ConnectionBanner";
import { AdminDashboard } from "./pages/admin/AdminDashboard";
import { AuditWorkspace } from "./pages/workspace/AuditWorkspace";
import { useGlobalShortcuts } from "./hooks/useGlobalShortcuts";
import { QueryErrorBoundary } from "./components/ui/QueryErrorBoundary";
import { setupConnectionSync } from "./services/queryClient";
import { EngineerPromptModal } from "./components/auth/EngineerPromptModal";

import { isPrototypeMode } from "./config/features";

function App() {
  const isProto = isPrototypeMode();
  const { backendUrl, status: connectionStatus, startPolling, stopPolling } = useConnectionStore();
  const { initialize: initializeTheme } = useThemeStore();
  const { isAuthenticated, isInitializing, user, initialize: initializeAuth } = useAuthStore();
  
  // Initialize global features
  useGlobalShortcuts();

  useEffect(() => {
    initializeTheme();
  }, [initializeTheme]);

  useEffect(() => {
    if (!isProto) {
      initializeAuth();
    }
  }, [initializeAuth, isProto]);

  // Maximize window on login (or immediately on startup in prototype mode)
  const prevAuthenticated = useRef<boolean | null>(null);
  useEffect(() => {
    if (isProto) {
      if (typeof window !== "undefined" && (window as any).__TAURI_INTERNALS__) {
        (async () => {
          try {
            const { getCurrentWindow } = await import("@tauri-apps/api/window");
            await getCurrentWindow().maximize();
          } catch (err) {
            console.warn("Window maximize failed in prototype mode:", err);
          }
        })();
      }
      return;
    }

    if (isInitializing) return; // wait until session restore is complete
    const justLoggedIn = !prevAuthenticated.current && isAuthenticated;
    const justLoggedOut = prevAuthenticated.current && !isAuthenticated;
    prevAuthenticated.current = isAuthenticated;

    if (typeof window === "undefined" || !(window as any).__TAURI_INTERNALS__) return;

    (async () => {
      try {
        const { getCurrentWindow } = await import("@tauri-apps/api/window");
        const win = getCurrentWindow();
        if (justLoggedIn) {
          await win.maximize();
        } else if (justLoggedOut) {
          await win.unmaximize();
        }
      } catch (err) {
        console.warn("Window resize after auth change failed:", err);
      }
    })();
  }, [isAuthenticated, isInitializing, isProto]);

  // Sync TanStack Query onlineManager with backend connection health status
  useEffect(() => {
    const unsubscribeSync = setupConnectionSync();
    return () => unsubscribeSync();
  }, []);

  // Re-verify auth session when backend connection becomes online
  useEffect(() => {
    if (!isProto && connectionStatus === "online") {
      initializeAuth();
    }
  }, [connectionStatus, initializeAuth, isProto]);

  // Poll connection on component mount
  useEffect(() => {
    startPolling();
    return () => stopPolling();
  }, [backendUrl, startPolling, stopPolling]);

  // Auto-sync offline Client PC storage files to NAS whenever NAS is reachable
  useEffect(() => {
    let unmounted = false;
    import("./services/clientStorageFallback").then(({ startBackgroundNasSync }) => {
      if (!unmounted) {
        startBackgroundNasSync(backendUrl);
      }
    });
    return () => {
      unmounted = true;
      import("./services/clientStorageFallback").then(({ stopBackgroundNasSync }) => {
        stopBackgroundNasSync();
      });
    };
  }, [backendUrl]);

  const renderContent = () => {
    // In prototype mode, skip login and render workspace directly
    if (isProto) {
      return <AuditWorkspace />;
    }

    // Session restore now reads from Tauri's encrypted secure storage (Phase 10),
    // which is inherently async — gate on isInitializing so LoginPage doesn't
    // flash before a valid persisted session has had a chance to resolve.
    if (isInitializing) {
      return (
        <div className="flex items-center justify-center w-full h-full text-text-muted">
          Restoring session...
        </div>
      );
    }
    if (!isAuthenticated) return <LoginPage />;
    if (user?.role === "admin") return <AdminDashboard />;
    if (user?.role === "user") return <AuditWorkspace />;
    
    // Fallback if role is missing or invalid
    return (
      <div className="flex items-center justify-center w-full h-full text-text-muted">
        Loading workspace...
      </div>
    );
  };

  return (
    <div className="flex flex-col h-screen w-screen overflow-hidden bg-bg-dark text-text-primary transition-colors">
      <AppHeader />
      <ConnectionBanner />
      <div className="flex-grow overflow-hidden relative flex min-h-0 min-w-0">
        {/*
          QueryErrorBoundary wraps ONLY the content area, not the whole app.
          The AppHeader sits outside so it survives a crash.
          "Try Again" clears TanStack Query error state + remounts the children.
        */}
        <QueryErrorBoundary>
          {renderContent()}
        </QueryErrorBoundary>
      </div>
      
      {/* Prototype Engineer Identity Prompt */}
      {isProto && <EngineerPromptModal />}
    </div>
  );
}

export default App;
