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

  // 1. Reconnected Success Screen (Production Toast Overlay)
  if (showRestoredOverlay && status === "online") {
    return (
      <div className="absolute inset-0 z-[9999] bg-bg-dark/40 backdrop-blur-sm flex flex-col items-center justify-center animate-in fade-in duration-300">
        <div className="bg-bg-card/95 border border-emerald-500/30 rounded-2xl p-6 max-w-sm w-full mx-4 shadow-2xl flex flex-col items-center text-center animate-in zoom-in-95 duration-200">
          <div className="w-12 h-12 rounded-full bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center mb-3">
            <CheckCircle2 size={24} className="text-emerald-500" />
          </div>
          <h3 className="text-base font-bold text-text-primary mb-1">Connection Restored</h3>
          <p className="text-xs text-text-muted">
            Auto-refreshing your workspace...
          </p>
        </div>
      </div>
    );
  }

  // 2. Production Connection Offline / Reconnecting Overlay (Slight Backdrop Blur)
  if (
    status === "offline" ||
    status === "reconnecting" ||
    status === "failed" ||
    status === "invalid" ||
    status === "connecting"
  ) {
    const isReconnecting = status === "reconnecting" || status === "connecting" || isRetrying;

    return (
      <div className="absolute inset-0 z-[9999] bg-bg-dark/40 backdrop-blur-sm flex flex-col items-center justify-center p-6 animate-in fade-in duration-300 select-none">
        <div className="bg-bg-card/95 border border-border-color rounded-2xl p-8 max-w-sm w-full shadow-2xl flex flex-col items-center text-center">
          
          {/* Minimal Production Icon */}
          <div className="w-14 h-14 rounded-2xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center mb-4">
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
            We're unable to reach the server right now. Please check your network connection or try reconnecting.
          </p>

          {/* Primary Action Button */}
          <button
            onClick={handleRetry}
            disabled={isReconnecting}
            className="w-full h-10 rounded-xl bg-accent-cyan text-on-accent font-semibold text-xs hover:brightness-105 active:scale-[0.98] transition-all flex items-center justify-center gap-2 disabled:opacity-60 cursor-pointer mb-4"
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
