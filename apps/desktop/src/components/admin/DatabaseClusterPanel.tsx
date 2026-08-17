import React, { useState, useEffect } from "react";
import {
  Database,
  HardDrive,
  RefreshCw,
  Zap,
  ShieldCheck,
  CheckCircle2
} from "lucide-react";
import { fetchDatabaseStatus, triggerDatabaseSync, DatabaseStatusResponse } from "../../services/databaseApi";
import { ClusterUpgradeModal } from "./ClusterUpgradeModal";

export const DatabaseClusterPanel: React.FC = () => {
  const [status, setStatus] = useState<DatabaseStatusResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [isUpgradeModalOpen, setIsUpgradeModalOpen] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const loadStatus = async () => {
    setLoading(true);
    try {
      const res = await fetchDatabaseStatus();
      setStatus(res);
    } catch (e: any) {
      console.warn("Failed to load database cluster status:", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadStatus();
  }, []);

  const handleSync = async () => {
    setSyncing(true);
    setNotice(null);
    try {
      const res = await triggerDatabaseSync();
      if (res?.success) {
        setNotice("Database synchronization complete!");
        loadStatus();
      } else {
        setNotice("Sync completed with warnings.");
      }
    } catch (e: any) {
      setNotice(`Sync failed: ${e.message}`);
    } finally {
      setSyncing(false);
    }
  };

  if (!status) return null;

  const storage = status.storage;
  const dataSizeMB = storage.data_size_mb;
  const limitMB = storage.limit_mb ?? 512;
  const usagePercent = storage.usage_percent ?? Math.round((dataSizeMB / limitMB) * 100);

  const getBarColor = () => {
    if (usagePercent >= 80) return "bg-rose-500 shadow-[0_0_12px_rgba(244,63,94,0.4)]";
    if (usagePercent >= 50) return "bg-amber-500 shadow-[0_0_12px_rgba(245,158,11,0.4)]";
    return "bg-accent-cyan shadow-[0_0_12px_rgba(0,229,255,0.4)]";
  };

  return (
    <div className="bg-bg-card border border-border-color rounded-xl p-6 shadow-sm">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-xl bg-amber-500/10 text-amber-400 border border-amber-500/20">
            <Database size={20} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-bold text-text-primary m-0">
                Cloud Database & Cluster Capacity
              </h3>
              <span className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-full bg-accent-cyan/15 text-accent-cyan border border-accent-cyan/30">
                Admin View
              </span>
            </div>
            <p className="text-xs text-text-muted mt-0.5">
              Cluster: <span className="font-mono text-text-primary font-bold">kmti-brain</span> ({storage.tier_name})
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={loadStatus}
            disabled={loading}
            className="p-2 rounded-lg text-text-muted hover:text-text-primary border border-border-color hover:bg-sidebar-item-hover transition-colors"
            title="Refresh database statistics"
          >
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          </button>

          <button
            onClick={() => setIsUpgradeModalOpen(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold bg-amber-500/15 border border-amber-500/30 text-amber-300 hover:bg-amber-500/25 transition-all"
          >
            <Zap size={13} className="text-amber-400" />
            <span>Upgrade Advisory</span>
          </button>
        </div>
      </div>

      {/* Storage Gauge */}
      <div className="p-4 rounded-xl bg-bg-sidebar border border-border-color space-y-3 mb-4">
        <div className="flex justify-between items-baseline">
          <span className="text-xs font-semibold text-text-primary flex items-center gap-1.5">
            <HardDrive size={14} className="text-accent-cyan" /> Storage Usage
          </span>
          <span className="text-xs font-mono font-bold text-text-primary">
            {dataSizeMB.toFixed(2)} MB / {limitMB.toFixed(0)} MB ({usagePercent}%)
          </span>
        </div>

        <div className="w-full h-2.5 bg-bg-card rounded-full overflow-hidden border border-border-color p-0.5">
          <div
            className={`h-full rounded-full transition-all duration-500 ${getBarColor()}`}
            style={{ width: `${Math.min(usagePercent, 100)}%` }}
          />
        </div>

        <div className="flex justify-between text-[11px] text-text-muted">
          <span>Total Entities & Violations: {storage.objects_count.toLocaleString()}</span>
          <span>Failover: {status.is_fallback ? "Running on Local Fallback" : "Cloud Primary Active (Auto-Sync ON)"}</span>
        </div>
      </div>

      {/* Info & Sync Action */}
      <div className="flex items-center justify-between pt-2 border-t border-border-color">
        <span className="text-xs text-text-muted flex items-center gap-1.5">
          <ShieldCheck size={14} className="text-emerald-400" />
          Automatic local MongoDB fallback and background synchronization are enabled.
        </span>

        <button
          onClick={handleSync}
          disabled={syncing}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold text-text-muted hover:text-text-primary border border-border-color hover:bg-sidebar-item-hover transition-all disabled:opacity-50"
        >
          <RefreshCw size={13} className={syncing ? "animate-spin" : ""} />
          {syncing ? "Syncing..." : "Sync to Local Backup"}
        </button>
      </div>

      {notice && (
        <div className="mt-3 p-2.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-xs text-emerald-400 flex items-center gap-2">
          <CheckCircle2 size={14} /> {notice}
        </div>
      )}

      {/* Upgrade Modal */}
      <ClusterUpgradeModal
        isOpen={isUpgradeModalOpen}
        onClose={() => setIsUpgradeModalOpen(false)}
        storage={storage}
        mode={status.mode}
        onRefresh={loadStatus}
      />
    </div>
  );
};
