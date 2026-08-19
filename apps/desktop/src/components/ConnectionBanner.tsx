import React, { useEffect, useState } from "react";
import { WifiOff, RefreshCw, CheckCircle2 } from "lucide-react";
import { useConnectionStore } from "../stores/connectionStore";

export const ConnectionBanner: React.FC = () => {
  const { status, checkHealth } = useConnectionStore();
  const [isRetrying, setIsRetrying] = useState(false);
  const [showRestoredOverlay, setShowRestoredOverlay] = useState(false);
  const [prevStatus, setPrevStatus] = useState(status);

  useEffect(() => {
    // Detect transition from offline/failed/reconnecting/connecting -> online
    if (
      (prevStatus === "offline" ||
        prevStatus === "reconnecting" ||
        prevStatus === "failed" ||
        prevStatus === "connecting") &&
      status === "online"
    ) {
      setShowRestoredOverlay(true);
      const timer = setTimeout(() => {
        setShowRestoredOverlay(false);
      }, 2000);
      return () => clearTimeout(timer);
    }
    setPrevStatus(status);
  }, [status, prevStatus]);

  const handleRetry = async () => {
    setIsRetrying(true);
    await checkHealth();
    setIsRetrying(false);
  };

  // 1. Reconnected Success Toast (Non-blocking floating toast at bottom-right, square border)
  if (showRestoredOverlay && status === "online") {
    return (
      <div className="fixed bottom-6 right-6 z-[9999] pointer-events-none animate-in fade-in slide-in-from-bottom-2 duration-300">
        <div className="bg-bg-card/95 border border-emerald-500/30 rounded-none px-4 py-3 shadow-2xl flex items-center gap-3 backdrop-blur-md">
          <div className="w-8 h-8 rounded-none bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center">
            <CheckCircle2 size={16} className="text-emerald-500" />
          </div>
          <div>
            <h3 className="text-xs font-bold text-text-primary">Connection Restored</h3>
            <p className="text-[11px] text-text-muted">Connected to backend service</p>
          </div>
        </div>
      </div>
    );
  }

  // 2. Production Connection Offline / Reconnecting Overlay (Slight Backdrop Blur, square borders)
  // Only shown when confirmed offline/failed/invalid or reconnecting after confirmed disconnection
  if (
    status === "offline" ||
    status === "reconnecting" ||
    status === "failed" ||
    status === "invalid"
  ) {
    const isReconnecting = status === "reconnecting" || isRetrying;

    return (
      <div className="absolute inset-0 z-[9999] bg-bg-dark/50 backdrop-blur-sm flex flex-col items-center justify-center p-6 animate-in fade-in duration-300 select-none">
        <div className="bg-bg-card/95 border border-border-color rounded-none p-8 max-w-sm w-full shadow-2xl flex flex-col items-center text-center">
          
          {/* Minimal Production Icon */}
          <div className="w-14 h-14 rounded-none bg-amber-500/10 border border-amber-500/20 flex items-center justify-center mb-4">
            {isReconnecting ? (
              <RefreshCw size={24} className="text-amber-500 animate-spin" />
            ) : (
              <WifiOff size={24} className="text-amber-500" />
            )}
          </div>

          {/* Headline */}
          <h2 className="text-lg font-bold text-text-primary mb-2">
            {isReconnecting ? "Connecting to Server..." : "Connection Lost"}
          </h2>

          {/* Production Non-Tech Copy */}
          <p className="text-xs text-text-muted leading-relaxed mb-6">
            We're unable to reach the server right now. Please check your backend service or try reconnecting.
          </p>

          {/* Primary Action Button */}
          <button
            onClick={handleRetry}
            disabled={isReconnecting}
            className="w-full h-10 rounded-none bg-accent-cyan text-on-accent font-semibold text-xs hover:brightness-105 active:scale-[0.98] transition-all flex items-center justify-center gap-2 disabled:opacity-60 cursor-pointer mb-4"
          >
            <RefreshCw size={14} className={isReconnecting ? "animate-spin" : ""} />
            <span>{isReconnecting ? "Connecting..." : "Retry Connection"}</span>
          </button>

          {/* Subtle Status Indicator */}
          <div className="flex items-center gap-2 text-[11px] text-text-muted opacity-75">
            <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
            <span>Reconnecting automatically...</span>
          </div>

        </div>
      </div>
    );
  }

  return null;
};
