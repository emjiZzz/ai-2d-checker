import React, { useState } from "react";
import { useAdminStore } from "../../stores/adminStore";
import { Archive, RotateCcw, AlertTriangle, FileCode, CheckCircle, X, Sparkles } from "lucide-react";

export const BackupRecovery: React.FC = () => {
  const { triggerBackup, triggerRestore, isLoading } = useAdminStore();
  const [lastBackup, setLastBackup] = useState<string | null>("backup_snapshot_1779174325.zip");
  const [successToast, setSuccessToast] = useState<string | null>(null);
  
  // Custom frosted confirmation overlay state
  const [showRestoreConfirm, setShowRestoreConfirm] = useState(false);

  const handleBackup = async () => {
    const backupFile = await triggerBackup();
    if (backupFile) {
      setLastBackup(backupFile);
      setSuccessToast(`System snapshot compiled: ${backupFile}`);
      setTimeout(() => setSuccessToast(null), 4000);
    }
  };

  const handleRestoreExecute = async () => {
    setShowRestoreConfirm(false);
    const ok = await triggerRestore(lastBackup || "");
    if (ok) {
      setSuccessToast("Database restored successfully from local ZIP snapshot.");
      setTimeout(() => setSuccessToast(null), 4000);
    }
  };

  return (
    <div className="admin-subpage">
      {/* Floating Toast Notification */}
      {successToast && (
        <div className="admin-toast-container">
          <div className="admin-toast success">
            <CheckCircle size={16} />
            <span>{successToast}</span>
          </div>
        </div>
      )}

      {/* High-Fidelity Frosted Glass Restoration Confirmation Overlay */}
      {showRestoreConfirm && (
        <div className="frosted-glass-overlay">
          <div className="overlay-card card settings-card delete-warning-card">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <h4 className="card-title danger" style={{ margin: 0, borderLeft: "3px solid #ef4444", paddingLeft: "8px", fontSize: "0.9rem" }}>
                <AlertTriangle size={16} style={{ color: "#ef4444", marginRight: "6px" }} />
                Restore System State?
              </h4>
              <button className="btn-close-overlay" onClick={() => setShowRestoreConfirm(false)}>
                <X size={16} />
              </button>
            </div>

            <div className="deleted-info-box" style={{ marginTop: "16px", padding: "12px", background: "linear-gradient(135deg, rgba(239, 68, 68, 0.1) 0%, rgba(239, 68, 68, 0.02) 100%)", border: "1px solid rgba(239, 68, 68, 0.2)", borderRadius: "8px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <FileCode size={18} style={{ color: "#ef4444" }} />
                <span style={{ fontSize: "0.8rem", fontFamily: "monospace", fontWeight: 600 }}>{lastBackup}</span>
              </div>
              <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "8px", lineHeight: "1.4" }}>
                ⚠️ <strong>Destructive Rollback:</strong> Restoring this backup will overwrite all existing drawing schemas, user histories, and standards manual embeddings created since the backup epoch.
              </p>
            </div>

            <div style={{ display: "flex", gap: "12px", marginTop: "20px" }}>
              <button
                className="btn btn-secondary"
                onClick={() => setShowRestoreConfirm(false)}
                style={{ flex: 1, padding: "8px" }}
              >
                Keep Current
              </button>
              <button
                className="btn btn-danger-confirm"
                onClick={handleRestoreExecute}
                style={{ flex: 1, padding: "8px" }}
              >
                Proceed Rollback
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="subpage-header">
        <h2 className="section-title">Snapshot Backups & Restore System</h2>
        <p className="section-desc">Create secure offline ZIP packages containing active manuals, drawings, and MongoDB collections.</p>
      </div>

      <div className="admin-grid-2" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "24px", marginTop: "20px" }}>
        {/* Trigger card */}
        <div className="card settings-card" style={{ display: "flex", flexDirection: "column" }}>
          <h3 className="card-title">
            <Archive size={18} style={{ color: "var(--accent-cyan)" }} />
            Compile System Snapshot
          </h3>
          <p className="card-desc-text" style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginTop: "4px", flexGrow: 1 }}>
            Exports Beanie MongoDB collections, drawings directory, and LanceDB vector indices into local secure sandbox storage directories.
          </p>

          <div className="action-row" style={{ marginTop: "20px", display: "flex", flexDirection: "column", gap: "12px" }}>
            {lastBackup && (
              <div className="backup-manifest" style={{ display: "flex", alignItems: "center", gap: "8px", background: "rgba(0, 0, 0, 0.15)", padding: "10px 12px", borderRadius: "8px", border: "1px solid var(--border-color)", fontSize: "0.78rem", color: "var(--text-muted)", fontFamily: "monospace" }}>
                <FileCode size={14} style={{ color: "var(--accent-cyan)" }} />
                <span>Last saved: {lastBackup}</span>
              </div>
            )}
            
            <div style={{ display: "flex", justifyContent: "flex-end" }}>
              <button className="btn btn-primary" onClick={handleBackup} disabled={isLoading} style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <Sparkles size={14} />
                Compile Complete ZIP Backup
              </button>
            </div>
          </div>
        </div>

        {/* Restore Card */}
        <div className="card settings-card" style={{ display: "flex", flexDirection: "column" }}>
          <h3 className="card-title" style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <RotateCcw size={18} style={{ color: "var(--accent-cyan)" }} />
            Restore Database Registry
          </h3>
          <p className="card-desc-text" style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginTop: "4px" }}>
            Rollback active configuration state from a previously saved local workspace snapshot file.
          </p>

          <div className="alert alert-warning" style={{ margin: "15px 0", padding: "12px", borderRadius: "8px", background: "rgba(245, 158, 11, 0.08)", border: "1px solid rgba(245, 158, 11, 0.18)", color: "#f59e0b", fontSize: "0.78rem", display: "flex", gap: "10px", flexGrow: 1 }}>
            <AlertTriangle size={18} style={{ flexShrink: 0, color: "#f59e0b" }} />
            <div>
              <strong>Destructive Operation:</strong> Restoring snapshot state overwrites all existing drawing schemas, user histories, and vector embeddings created since the backup epoch.
            </div>
          </div>

          <div style={{ display: "flex", justifyContent: "flex-end", marginTop: "12px" }}>
            <button 
              className="btn btn-secondary" 
              onClick={() => setShowRestoreConfirm(true)} 
              disabled={!lastBackup || isLoading} 
              style={{ borderColor: "#ef4444", color: "#fca5a5", display: "flex", alignItems: "center", gap: "8px" }}
            >
              <RotateCcw size={14} />
              Rollback to Selected Snapshot
            </button>
          </div>
        </div>
      </div>

      <style>{`
        /* TOAST NOTIFICATIONS styling */
        .admin-toast-container {
          position: fixed;
          top: 24px;
          right: 24px;
          display: flex;
          flex-direction: column;
          gap: 10px;
          z-index: 2000;
          pointer-events: none;
        }

        .admin-toast {
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 12px 20px;
          border-radius: 8px;
          box-shadow: 0 10px 30px rgba(0, 0, 0, 0.4);
          font-size: 0.85rem;
          color: #ffffff;
          animation: slideInRight 0.3s cubic-bezier(0.16, 1, 0.3, 1);
          pointer-events: auto;
          border-left: 4px solid transparent;
        }

        .admin-toast.success {
          background: rgba(24, 24, 27, 0.95);
          border-left-color: #10b981;
          border: 1px solid rgba(16, 185, 129, 0.2);
          color: #10b981;
        }

        /* OVERLAYS & DIALOGS */
        .frosted-glass-overlay {
          position: absolute;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          background: rgba(9, 9, 11, 0.7);
          backdrop-filter: blur(8px);
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 20px;
          z-index: 100;
          border-radius: 14px;
          animation: fadeIn 0.25s ease-out;
        }

        .overlay-card {
          width: 100%;
          max-width: 380px;
          background: var(--bg-card);
          border: 1px solid var(--border-color);
          border-radius: 12px;
          padding: 20px !important;
          box-shadow: 0 20px 50px rgba(0, 0, 0, 0.6);
        }

        .btn-close-overlay {
          background: transparent;
          border: none;
          color: var(--text-muted);
          cursor: pointer;
          padding: 4px;
          border-radius: 4px;
          display: flex;
          align-items: center;
        }

        .btn-close-overlay:hover {
          color: var(--text-primary);
          background: rgba(255, 255, 255, 0.05);
        }

        /* Custom premium Danger confirm button */
        .btn-danger-confirm {
          background: linear-gradient(135deg, #ef4444 0%, #b91c1c 100%);
          border: 1px solid rgba(239, 68, 68, 0.3);
          color: #ffffff;
          font-weight: 600;
          border-radius: 8px;
          cursor: pointer;
          transition: all 0.2s ease;
          box-shadow: 0 4px 12px rgba(239, 68, 68, 0.25);
        }

        .btn-danger-confirm:hover {
          transform: translateY(-2px);
          box-shadow: 0 6px 20px rgba(239, 68, 68, 0.45);
          background: linear-gradient(135deg, #f87171 0%, #dc2626 100%);
        }

        .btn-danger-confirm:active {
          transform: translateY(0);
        }

        @keyframes slideInRight {
          from {
            transform: translateX(100%);
            opacity: 0;
          }
          to {
            transform: translateX(0);
            opacity: 1;
          }
        }
      `}</style>
    </div>
  );
};
