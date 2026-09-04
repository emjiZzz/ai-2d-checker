import React, { useState, useEffect } from "react";
import {
  Database,
  AlertTriangle,
  RefreshCw,
  HardDrive,
  CheckCircle2,
  X,
  Zap,
  ShieldCheck,
  ArrowUpRight,
  Layers
} from "lucide-react";
import { StorageStats, triggerDatabaseSync, fetchDatabaseStatus } from "../../services/databaseApi";

interface ClusterUpgradeModalProps {
  isOpen: boolean;
  onClose: () => void;
  storage?: StorageStats | null;
  mode?: "cloud_primary" | "local_fallback" | "disconnected";
  onRefresh?: () => void;
}

export const ClusterUpgradeModal: React.FC<ClusterUpgradeModalProps> = ({
  isOpen,
  onClose,
  storage: initialStorage,
  mode: initialMode = "cloud_primary",
  onRefresh,
}) => {
  const [syncing, setSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState<string | null>(null);
  const [liveStorage, setLiveStorage] = useState<StorageStats | null>(initialStorage ?? null);
  const [liveMode, setLiveMode] = useState<string>(initialMode);

  const fetchLive = async () => {
    try {
      const res = await fetchDatabaseStatus();
      if (res?.connected && res?.storage) {
        setLiveStorage(res.storage);
        setLiveMode(res.mode);
      }
    } catch (e) {
      console.warn("[ClusterUpgradeModal] Failed to fetch live DB stats:", e);
    }
  };

  useEffect(() => {
    if (isOpen) {
      fetchLive();
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const currentStorage = liveStorage ?? initialStorage;
  const dataSizeMB = currentStorage?.data_size_mb ?? 0;
  const limitMB = currentStorage?.limit_mb ?? 512;
  const usagePercent = currentStorage?.usage_percent ?? Math.round((dataSizeMB / limitMB) * 100);
  const isNearLimit = usagePercent >= 60 || dataSizeMB >= 300;

  const handleOpenAtlas = async () => {
    const atlasUrl = "https://cloud.mongodb.com";
    try {
      const { openUrl } = await import("@tauri-apps/plugin-opener");
      await openUrl(atlasUrl);
    } catch {
      window.open(atlasUrl, "_blank");
    }
  };

  const handleSync = async () => {
    setSyncing(true);
    setSyncResult(null);
    try {
      const res = await triggerDatabaseSync();
      if (res?.success) {
        setSyncResult("Successfully synchronized local and cloud collections.");
        await fetchLive();
        onRefresh?.();
      } else {
        setSyncResult("Sync finished with warnings.");
      }
    } catch (err: any) {
      setSyncResult(`Sync failed: ${err.message || "Network error"}`);
    } finally {
      setSyncing(false);
    }
  };

  const getBarColor = () => {
    if (usagePercent >= 80) return "bg-rose-500 shadow-[0_0_12px_rgba(244,63,94,0.4)]";
    if (usagePercent >= 50) return "bg-amber-500 shadow-[0_0_12px_rgba(245,158,11,0.4)]";
    return "bg-accent-cyan shadow-[0_0_12px_rgba(0,229,255,0.4)]";
  };

  return (
    <div
      className="fixed inset-0 z-[999999] flex items-center justify-center p-4 bg-black/70 backdrop-blur-md animate-in fade-in duration-200"
      onClick={onClose}
    >
      <div
        className="relative w-full max-w-xl bg-bg-card border border-border-color rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border-color bg-bg-sidebar">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-amber-500/10 text-amber-400 border border-amber-500/20">
              <Database size={20} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-extrabold text-text-primary tracking-tight">
                  MongoDB Cloud Cluster Storage
                </h3>
                <span className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-full bg-accent-cyan/15 text-accent-cyan border border-accent-cyan/30">
                  Admin Notice
                </span>
              </div>
              <p className="text-xs text-text-muted mt-0.5">
                Cluster: <span className="font-mono text-text-primary font-bold">kmti-brain</span> (M0 Free Tier)
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-text-muted hover:text-text-primary hover:bg-sidebar-item-hover transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-6 overflow-y-auto space-y-6">
          {/* Storage Capacity Gauge */}
          <div className="p-4 rounded-xl bg-bg-sidebar border border-border-color space-y-3">
            <div className="flex justify-between items-baseline">
              <span className="text-xs font-bold text-text-primary flex items-center gap-2">
                <HardDrive size={15} className="text-accent-cyan" /> Free Tier Storage Usage
              </span>
              <span className="text-xs font-mono font-bold text-text-primary">
                {dataSizeMB.toFixed(2)} MB <span className="text-text-muted">/ {limitMB.toFixed(0)} MB ({usagePercent}%)</span>
              </span>
            </div>

            {/* Visual Bar */}
            <div className="w-full h-3 bg-bg-card rounded-full overflow-hidden border border-border-color p-0.5">
              <div
                className={`h-full rounded-full transition-all duration-500 ${getBarColor()}`}
                style={{ width: `${Math.min(usagePercent, 100)}%` }}
              />
            </div>

            <div className="flex justify-between text-[11px] text-text-muted">
              <span>Used: {dataSizeMB.toFixed(2)} MB</span>
              <span>Available: {Math.max(0, limitMB - dataSizeMB).toFixed(2)} MB</span>
            </div>
          </div>

          {/* Quota Warning Alert */}
          {isNearLimit ? (
            <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/30 flex gap-3 items-start">
              <AlertTriangle size={18} className="text-rose-400 shrink-0 mt-0.5" />
              <div className="text-xs text-rose-200 leading-relaxed">
                <span className="font-bold block text-rose-100 mb-1">Approaching Free Tier Limit (512 MB)</span>
                Your cluster is approaching its capacity. When full, MongoDB Atlas will reject write operations. Upgrade to a dedicated cluster to unlock auto-expanding storage.
              </div>
            </div>
          ) : (
            <div className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/20 flex gap-3 items-start">
              <Zap size={18} className="text-amber-400 shrink-0 mt-0.5" />
              <div className="text-xs text-text-muted leading-relaxed">
                <span className="font-bold text-text-primary block mb-1">Free Tier Limitations</span>
                The current <span className="font-semibold text-text-primary">M0 cluster</span> is capped at 512 MB with shared CPU. For full production performance and unlimited storage auto-scaling, MongoDB Atlas recommends upgrading to an <span className="font-semibold text-text-primary">M10 or Flex Cluster</span>.
              </div>
            </div>
          )}

          {/* Database Details Grid */}
          <div className="grid grid-cols-2 gap-3 text-xs">
            <div className="p-3 rounded-lg bg-bg-sidebar border border-border-color">
              <span className="text-text-muted text-[10px] uppercase font-bold tracking-wider block">Active Mode</span>
              <span className="font-bold text-text-primary mt-1 flex items-center gap-1.5">
                <span className={`w-2 h-2 rounded-full ${liveMode === "cloud_primary" ? "bg-emerald-400 shadow-[0_0_8px_#10b981]" : "bg-amber-400"}`} />
                {liveMode === "cloud_primary" ? "Cloud Primary (Atlas)" : "Local Fallback (Offline)"}
              </span>
            </div>

            <div className="p-3 rounded-lg bg-bg-sidebar border border-border-color">
              <span className="text-text-muted text-[10px] uppercase font-bold tracking-wider block">Local Failover</span>
              <span className="font-bold text-emerald-400 mt-1 flex items-center gap-1.5">
                <ShieldCheck size={14} /> Enabled (Zero Downtime)
              </span>
            </div>
          </div>

          {/* Upgrade Steps */}
          <div className="space-y-2">
            <h4 className="text-xs font-bold uppercase tracking-wider text-text-muted flex items-center gap-1.5">
              <Layers size={13} className="text-accent-cyan" /> How to Upgrade on Atlas:
            </h4>
            <ol className="list-decimal list-inside text-xs text-text-muted space-y-1.5 pl-1 leading-relaxed">
              <li>Open your <span className="text-text-primary font-semibold">MongoDB Atlas Dashboard</span> in your browser.</li>
              <li>Navigate to cluster <span className="text-text-primary font-mono font-semibold">kmti-brain</span>.</li>
              <li>Click the green <span className="text-text-primary font-semibold">"Upgrade"</span> button on the cluster card.</li>
              <li>Select <span className="text-text-primary font-semibold">M10 or Flex Cluster</span> (auto-scales storage to 10GB+).</li>
              <li>No code changes required — your connection string remains unchanged!</li>
            </ol>
          </div>

          {syncResult && (
            <div className="p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-xs text-emerald-400 flex items-center gap-2">
              <CheckCircle2 size={15} /> {syncResult}
            </div>
          )}
        </div>

        {/* Footer Actions */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-border-color bg-bg-sidebar">
          <button
            onClick={handleSync}
            disabled={syncing}
            className="flex items-center gap-2 px-3 py-2 rounded-xl text-xs font-bold text-text-muted hover:text-text-primary border border-border-color hover:bg-sidebar-item-hover transition-all disabled:opacity-50"
          >
            <RefreshCw size={14} className={syncing ? "animate-spin" : ""} />
            {syncing ? "Syncing..." : "Sync Local Backup"}
          </button>

          <div className="flex items-center gap-2">
            <button
              onClick={onClose}
              className="px-4 py-2 rounded-xl text-xs font-semibold text-text-muted hover:text-text-primary transition-colors"
            >
              Dismiss
            </button>
            <button
              onClick={handleOpenAtlas}
              className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-bold bg-accent-cyan text-black hover:opacity-90 transition-opacity shadow-[0_0_15px_rgba(0,229,255,0.25)] cursor-pointer"
            >
              <span>Open Atlas Dashboard</span>
              <ArrowUpRight size={14} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
