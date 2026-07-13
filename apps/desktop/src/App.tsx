import { useEffect } from "react";
import { useConnectionStore } from "./stores/connectionStore";
import { useAuthStore } from "./stores/authStore";
import { useThemeStore } from "./stores/themeStore";
import { LoginPage } from "./pages/auth/LoginPage";
import { AppHeader } from "./components/AppHeader";
import { AdminDashboard } from "./pages/admin/AdminDashboard";
import { AuditWorkspace } from "./pages/workspace/AuditWorkspace";
import { useGlobalShortcuts } from "./hooks/useGlobalShortcuts";
import { useGlobalFileUpload } from "./hooks/useGlobalFileUpload";
import { QueryErrorBoundary } from "./components/ui/QueryErrorBoundary";

function App() {
  const { backendUrl, startPolling, stopPolling } = useConnectionStore();
  const { initialize: initializeTheme } = useThemeStore();
  const { isAuthenticated, isInitializing, user, initialize: initializeAuth } = useAuthStore();
  
  // Initialize global features
  useGlobalShortcuts();
  
  const {
    isDragging,
    handleDragOver,
    handleDragLeave,
    handleDrop
  } = useGlobalFileUpload();

  useEffect(() => {
    initializeTheme();
  }, [initializeTheme]);

  useEffect(() => {
    initializeAuth();
  }, [initializeAuth]);

  // Poll connection on component mount
  useEffect(() => {
    startPolling(5000);
    return () => stopPolling();
  }, [backendUrl, startPolling, stopPolling]);

  const renderContent = () => {
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
    <div 
      className={`flex flex-col h-screen w-screen overflow-hidden bg-bg-dark text-text-primary transition-colors ${
        isDragging ? "border-4 border-dashed border-accent-cyan" : ""
      }`}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      <AppHeader />
      <div className="flex-grow overflow-hidden relative flex min-h-0 min-w-0">
        {/*
          QueryErrorBoundary wraps ONLY the content area, not the whole app.
          The AppHeader and drag overlay sit outside so they survive a crash.
          "Try Again" clears TanStack Query error state + remounts the children.
        */}
        <QueryErrorBoundary>
          {renderContent()}
        </QueryErrorBoundary>
      </div>
      
      {/* Global Drag Overlay */}
      {isDragging && (
        <div className="absolute inset-0 bg-blue-500/10 backdrop-blur-sm z-50 flex items-center justify-center pointer-events-none">
          <div className="bg-bg-card p-6 rounded-xl border-2 border-accent-cyan border-dashed shadow-2xl flex flex-col items-center">
            <div className="w-16 h-16 rounded-full bg-accent-cyan/20 flex items-center justify-center mb-4 animate-bounce">
              <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-accent-cyan">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                <polyline points="17 8 12 3 7 8"></polyline>
                <line x1="12" y1="3" x2="12" y2="15"></line>
              </svg>
            </div>
            <h3 className="text-xl font-bold text-text-primary mb-1">Drop CAD file here</h3>
            <p className="text-sm text-text-muted">Supports .dwg, .dxf, .step, .iges</p>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
