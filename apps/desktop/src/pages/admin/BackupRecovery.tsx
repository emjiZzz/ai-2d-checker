import React, { useState } from "react";
import { useAdminStore } from "../../stores/adminStore";
import { Archive, RotateCcw, AlertTriangle, FileCode, CheckCircle } from "lucide-react";

export const BackupRecovery: React.FC = () => {
  const { triggerBackup, triggerRestore, isLoading } = useAdminStore();
  const [lastBackup, setLastBackup] = useState<string | null>("backup_snapshot_1779174325.zip");
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const handleBackup = async () => {
    const backupFile = await triggerBackup();
    if (backupFile) {
      setLastBackup(backupFile);
      setSuccessMsg(`System snapshot successfully compiled: ${backupFile}`);
      setTimeout(() => setSuccessMsg(null), 4000);
    }
  };

  const handleRestore = async () => {
    if (confirm("WARNING: Rollover snapshot files will restore user registries and override current standards library manuals. Proceed?")) {
      const ok = await triggerRestore(lastBackup || "");
      if (ok) {
        setSuccessMsg("Database restored successfully from local ZIP snapshot.");
        setTimeout(() => setSuccessMsg(null), 4000);
      }
    }
  };

  return (
    <div className="admin-subpage">
      <div className="subpage-header">
        <h2 className="section-title">Snapshot Backups & Restore System</h2>
        <p className="section-desc">Create secure offline ZIP packages containing active manuals, drawings, and MongoDB collections.</p>
      </div>

      <div className="admin-grid-2" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "24px", marginTop: "20px" }}>
        {/* Trigger card */}
        <div className="card settings-card">
          <h3 className="card-title">
            <Archive size={18} style={{ color: "var(--accent-cyan)" }} />
            Compile System Snapshot
          </h3>
          <p className="card-description">
            Exports Beanie MongoDB collections, drawings directory, and Lancedb vector indices into local secure sandbox storage directories.
          </p>

          {successMsg && (
            <div className="alert alert-success" style={{ margin: "10px 0", padding: "10px", borderRadius: "6px", background: "rgba(16, 185, 129, 0.1)", border: "1px solid rgba(16, 185, 129, 0.2)", color: "#10b981", fontSize: "0.85rem", display: "flex", alignItems: "center", gap: "8px" }}>
              <CheckCircle size={16} />
              <span>{successMsg}</span>
            </div>
          )}

          <div className="action-row" style={{ marginTop: "20px", display: "flex", flexDirection: "column", gap: "12px" }}>
            <button className="btn btn-primary" onClick={handleBackup} disabled={isLoading}>
              Compile Complete ZIP Backup
            </button>
            {lastBackup && (
              <div className="backup-manifest" style={{ display: "flex", alignItems: "center", gap: "8px", background: "var(--sidebar-item-hover)", padding: "10px", borderRadius: "6px", border: "1px solid var(--border-color)", fontSize: "0.8rem", color: "var(--text-muted)", fontFamily: "monospace" }}>
                <FileCode size={14} />
                <span>Last saved: {lastBackup}</span>
              </div>
            )}
          </div>
        </div>

        {/* Restore Card */}
        <div className="card settings-card">
          <h3 className="card-title" style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <RotateCcw size={18} style={{ color: "var(--accent-cyan)" }} />
            Restore Database Registry
          </h3>
          <p className="card-description">
            Rollback active configuration state from a previously saved local workspace snapshot file.
          </p>

          <div className="alert alert-warning" style={{ margin: "15px 0", padding: "12px", borderRadius: "6px", background: "rgba(245, 158, 11, 0.1)", border: "1px solid rgba(245, 158, 11, 0.2)", color: "#f59e0b", fontSize: "0.8rem", display: "flex", gap: "10px" }}>
            <AlertTriangle size={18} style={{ flexShrink: 0 }} />
            <div>
              <strong>Destructive Operation:</strong> Restoring snapshot state overwrites all existing drawing schemas, user histories, and vector embeddings created since the backup epoch.
            </div>
          </div>

          <button className="btn btn-secondary" onClick={handleRestore} disabled={!lastBackup || isLoading} style={{ width: "100%", borderColor: "#ef4444", color: "#fca5a5" }}>
            Rollback to Selected Snapshot
          </button>
        </div>
      </div>
    </div>
  );
};
