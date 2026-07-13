import React from "react";
import { AlertTriangle, RefreshCw, Trash2 } from "lucide-react";
import { FallbackProps } from "react-error-boundary";

export const GlobalErrorFallback: React.FC<FallbackProps> = ({ error, resetErrorBoundary }) => {
  const handleHardReset = () => {
    // Clear potentially corrupted client-side state
    localStorage.clear();
    sessionStorage.clear();
    // Use location.replace to force a clean navigation without keeping the broken state in history
    window.location.replace("/");
  };

  return (
    <div className="fixed inset-0 flex items-center justify-center bg-bg-dark text-text-primary p-6 z-[9999]">
      <div className="max-w-md w-full bg-bg-sidebar border border-border-color rounded-xl p-8 flex flex-col items-center text-center shadow-2xl">
        <div className="w-16 h-16 rounded-full bg-red-500/10 flex items-center justify-center mb-6 border border-red-500/20">
          <AlertTriangle className="text-red-400" size={32} />
        </div>
        
        <h1 className="text-2xl font-bold text-text-primary mb-2">Something went wrong</h1>
        <p className="text-text-muted mb-6 text-sm">
          A critical rendering error occurred. The application state might be unstable.
        </p>

        <div className="w-full bg-bg-dark border border-border-color rounded-lg p-4 mb-8 text-left overflow-auto max-h-48">
          <p className="font-mono text-xs text-red-300 break-words">
            {(error as Error).message || "Unknown error"}
          </p>
        </div>

        <div className="flex flex-col w-full gap-3">
          <button 
            onClick={resetErrorBoundary}
            className="w-full btn btn-primary flex items-center justify-center gap-2 py-3"
          >
            <RefreshCw size={16} />
            Try to Recover
          </button>
          
          <button 
            onClick={handleHardReset}
            className="w-full btn btn-secondary flex items-center justify-center gap-2 py-3 hover:bg-red-500/10 hover:text-red-400 hover:border-red-500/30 transition-colors"
          >
            <Trash2 size={16} />
            Clear Data and Hard Reset
          </button>
        </div>
      </div>
    </div>
  );
};
