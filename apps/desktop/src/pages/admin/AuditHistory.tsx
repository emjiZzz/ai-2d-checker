import React, { useEffect, useState } from "react";
import { useAdminStore } from "../../stores/adminStore";
import { useConnectionStore } from "../../stores/connectionStore";
import {
  FileText,
  RefreshCw,
  Search,
  Trash2,
  Archive,
  RefreshCcw,
  CheckCircle2,
  AlertTriangle,
  X,
  Clock,
  Filter,
  Briefcase,
  Loader
} from "lucide-react";

// Helper utility to parse ISO datetime strings from backend reliably as UTC
const parseUtcDate = (dateStr: string | null | undefined): Date => {
  if (!dateStr) return new Date();
  const utcStr = dateStr.includes("Z") || dateStr.includes("+") ? dateStr : dateStr + "Z";
  return new Date(utcStr);
};

export const AuditHistory: React.FC = () => {
  const {
    adminAuditSessions,
    adminAuditSessionsLoading,
    error: storeError,
    fetchAdminAuditSessions,
    restoreAuditSession,
  } = useAdminStore();

  // View state: "active" vs "trashbin"
  const [viewMode, setViewMode] = useState<"active" | "trashbin">("active");

  // Filtering state
  const [searchUsername, setSearchUsername] = useState("");
  const [appliedUsername, setAppliedUsername] = useState("");

  // Toast notifications
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);

  // Drawings state for resolving file names
  const [drawings, setDrawings] = useState<any[]>([]);

  // Load data whenever view mode or applied username filter changes
  useEffect(() => {
    fetchAdminAuditSessions(viewMode === "trashbin", appliedUsername);
  }, [fetchAdminAuditSessions, viewMode, appliedUsername]);

  // Fetch drawings independently to map IDs to file names
  useEffect(() => {
    const fetchDrawings = async () => {
      const { backendUrl, apiToken } = useConnectionStore.getState();
      try {
        const headers: Record<string, string> = { "Accept": "application/json" };
        if (apiToken) headers["Authorization"] = `Bearer ${apiToken}`;

        const res = await fetch(`${backendUrl}/api/v1/drawings`, { headers });
        if (res.ok) {
          const result = await res.json();
          if (result.success && result.data) {
            setDrawings(result.data);
          }
        }
      } catch (e) {
        console.warn("Failed to fetch drawings for name resolution", e);
      }
    };
    fetchDrawings();
  }, []);

  const getDrawingName = (drawingId: string) => {
    const drawing = drawings.find((d) => d.id === drawingId);
    return drawing ? drawing.file_name : `Drawing #${drawingId.substring(0, 8)}`;
  };

  const triggerNotification = (msg: string) => {
    setSuccessMessage(msg);
    setTimeout(() => setSuccessMessage(null), 4000);
  };

  const triggerError = (msg: string) => {
    setLocalError(msg);
    setTimeout(() => setLocalError(null), 4000);
  };

  const handleApplyFilter = () => {
    setAppliedUsername(searchUsername);
  };

  const handleClearFilter = () => {
    setSearchUsername("");
    setAppliedUsername("");
  };

  const handleRestore = async (id: string, drawingId: string) => {
    const ok = await restoreAuditSession(id);
    if (ok) {
      triggerNotification(`Session for drawing ${drawingId} successfully restored.`);
      fetchAdminAuditSessions(viewMode === "trashbin", appliedUsername);
    } else {
      triggerError(storeError || "Failed to restore session.");
    }
  };

  const handleEmptyTrash = async () => {
    const ok = await useAdminStore.getState().emptyTrash();
    if (ok) {
      triggerNotification("Trashbin successfully emptied.");
      fetchAdminAuditSessions(viewMode === "trashbin", appliedUsername);
    } else {
      triggerError("Failed to empty trashbin.");
    }
  };

  // Derive counts from current data (shows count for the active filter/view)
  const totalSessions = adminAuditSessions.length;
  const completedSessions = adminAuditSessions.filter((s) => s.status === "completed").length;
  const failedSessions = adminAuditSessions.filter((s) => s.status === "failed").length;
  const queuedSessions = adminAuditSessions.filter((s) => s.status === "queued" || s.status === "processing").length;

  return (
    <div className="admin-subpage">
      {/* Dynamic Slide-Down Floating Toast Notifications */}
      {(successMessage || localError || storeError) && (
        <div className="admin-toast-container">
          {successMessage && (
            <div className="admin-toast success">
              <CheckCircle2 size={16} />
              <span>{successMessage}</span>
            </div>
          )}
          {localError && (
            <div className="admin-toast error">
              <AlertTriangle size={16} />
              <span>{localError}</span>
            </div>
          )}
        </div>
      )}

      {/* SUBPAGE HEADER */}
      <div className="subpage-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <h2 className="section-title">Audit History Archive</h2>
          <p className="section-desc">Monitor global engineering drawing compliance runs and manage session records.</p>
        </div>
        <div style={{ display: "flex", gap: "12px", alignItems: "center" }}>
          <button
            className="btn btn-secondary refresh-directory-btn"
            onClick={() => fetchAdminAuditSessions(viewMode === "trashbin", appliedUsername)}
            disabled={adminAuditSessionsLoading}
            style={{ display: "flex", alignItems: "center", gap: "8px" }}
          >
            <RefreshCw size={14} className={adminAuditSessionsLoading ? "spin-animation" : ""} />
            Sync Archive
          </button>
        </div>
      </div>

      {/* 1. VISUAL ANALYTICS METRICS STRIP (4 CARDS) */}
      <div className="admin-metrics-grid">
        <div className="card metrics-card">
          <div className="metrics-icon-wrapper blue">
            <Archive size={18} />
          </div>
          <div className="metrics-data">
            <span className="metrics-value">{totalSessions}</span>
            <span className="metrics-label">Total Sessions</span>
          </div>
        </div>

        <div className="card metrics-card">
          <div className="metrics-icon-wrapper green">
            <CheckCircle2 size={18} />
          </div>
          <div className="metrics-data">
            <span className="metrics-value">{completedSessions}</span>
            <span className="metrics-label">Completed Audits</span>
          </div>
        </div>

        <div className="card metrics-card">
          <div className="metrics-icon-wrapper purple">
            <Clock size={18} />
          </div>
          <div className="metrics-data">
            <span className="metrics-value">{queuedSessions}</span>
            <span className="metrics-label">In Progress / Queued</span>
          </div>
        </div>

        <div className="card metrics-card">
          <div className="metrics-icon-wrapper" style={{ background: "rgba(239, 68, 68, 0.1)", color: "#ef4444" }}>
            <AlertTriangle size={18} />
          </div>
          <div className="metrics-data">
            <span className="metrics-value">{failedSessions}</span>
            <span className="metrics-label">Failed Audits</span>
          </div>
        </div>
      </div>

      {/* 2. SEARCH & MULTI-FILTER CONTROL PANEL */}
      <div className="card filter-control-card">
        <div className="filter-search-group">
          {/* View Mode Toggle */}
          <div className="filter-segments-wrapper" style={{ marginRight: "auto" }}>
            <div className="filter-pill-group">
              <span className="filter-pill-label">Archive View:</span>
              <button
                className={`filter-pill-btn ${viewMode === "active" ? "active" : ""}`}
                onClick={() => setViewMode("active")}
              >
                Active Archive
              </button>
              <button
                className={`filter-pill-btn ${viewMode === "trashbin" ? "active" : ""}`}
                onClick={() => setViewMode("trashbin")}
              >
                Trashbin
              </button>
            </div>
          </div>

        </div>
      </div>

      {/* 3. DIRECTORY LISTINGS TABLE */}
      <div className="card settings-card directory-listings-card" style={{ marginTop: "24px", display: "flex", flexDirection: "column" }}>
        <div className="card-title-row" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "20px" }}>
          <h3 className="card-title" style={{ margin: 0 }}>
            <FileText size={18} style={{ color: "var(--accent-cyan)" }} />
            {viewMode === "active" ? "Active Sessions Directory" : "Deleted Sessions Trashbin"}
          </h3>
          <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
            {/* User Search Input */}
            <div className="search-input-wrapper" style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <div style={{ position: "relative", display: "flex", alignItems: "center" }}>
                <Search size={16} className="search-icon" style={{ position: "absolute", left: "10px", color: "var(--text-muted)" }} />
                <input
                  type="text"
                  placeholder="Filter by Username..."
                  className="form-input search-input"
                  style={{ paddingLeft: "34px", paddingRight: searchUsername ? "34px" : "12px", width: "220px" }}
                  value={searchUsername}
                  onChange={(e) => setSearchUsername(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") handleApplyFilter(); }}
                />
                {searchUsername && (
                  <button
                    className="clear-search-btn"
                    onClick={handleClearFilter}
                    style={{ position: "absolute", right: "10px", background: "none", border: "none", color: "var(--text-muted)", cursor: "pointer" }}
                  >
                    <X size={14} />
                  </button>
                )}
              </div>
              <button
                className="btn btn-secondary"
                onClick={handleApplyFilter}
                style={{ display: "flex", alignItems: "center", gap: "6px", padding: "6px 12px" }}
              >
                <Filter size={14} />
                Filter
              </button>
            </div>
            {viewMode === "trashbin" && adminAuditSessions.length > 0 && (
              <button
                className="btn btn-secondary"
                onClick={handleEmptyTrash}
                disabled={adminAuditSessionsLoading}
                style={{ display: "flex", alignItems: "center", gap: "8px", background: "rgba(239, 68, 68, 0.1)", color: "#ef4444", border: "1px solid rgba(239, 68, 68, 0.2)", padding: "4px 12px", fontSize: "0.8rem" }}
              >
                <Trash2 size={14} />
                Empty Trash
              </button>
            )}
          </div>
        </div>

        <div className="users-list-container" style={{ flexGrow: 1, overflowY: "auto", minHeight: "300px" }}>
          {adminAuditSessionsLoading && adminAuditSessions.length === 0 ? (
            <div className="empty-state" style={{ padding: "40px 20px", textAlign: "center", color: "var(--text-muted)" }}>
              Loading audit sessions...
            </div>
          ) : adminAuditSessions.length === 0 ? (
            <div className="empty-state" style={{ padding: "40px 20px", textAlign: "center", color: "var(--text-muted)", border: "1px dashed var(--border-color)", borderRadius: "8px" }}>
              No audit sessions found in {viewMode === "active" ? "active archive" : "trashbin"} matching criteria.
            </div>
          ) : (
            <table className="stats-table" style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr className="stats-row" style={{ background: "rgba(255, 255, 255, 0.015)", borderBottom: "1px solid rgba(255, 255, 255, 0.06)" }}>
                  <th style={{ color: "var(--text-muted)", fontSize: "0.78rem", fontWeight: "600", textTransform: "uppercase", letterSpacing: "0.5px", textAlign: "left", padding: "14px 16px", verticalAlign: "left", width: "90px" }}>ID</th>
                  <th style={{ color: "var(--text-muted)", fontSize: "0.78rem", fontWeight: "600", textTransform: "uppercase", letterSpacing: "0.5px", textAlign: "left", padding: "14px 16px", verticalAlign: "middle" }}>User</th>
                  <th style={{ color: "var(--text-muted)", fontSize: "0.78rem", fontWeight: "600", textTransform: "uppercase", letterSpacing: "0.5px", textAlign: "left", padding: "14px 16px", verticalAlign: "middle" }}>Original Drawing</th>
                  <th style={{ color: "var(--text-muted)", fontSize: "0.78rem", fontWeight: "600", textTransform: "uppercase", letterSpacing: "0.5px", textAlign: "left", padding: "14px 16px", verticalAlign: "middle" }}>KMTI Drawing</th>
                  <th style={{ color: "var(--text-muted)", fontSize: "0.78rem", fontWeight: "600", textTransform: "uppercase", letterSpacing: "0.5px", textAlign: "left", padding: "14px 16px", verticalAlign: "middle" }}>Client</th>
                  <th style={{ color: "var(--text-muted)", fontSize: "0.78rem", fontWeight: "600", textTransform: "uppercase", letterSpacing: "0.5px", textAlign: "left", padding: "14px 16px", verticalAlign: "middle" }}>Compliance Score</th>
                  <th style={{ color: "var(--text-muted)", fontSize: "0.78rem", fontWeight: "600", textTransform: "uppercase", letterSpacing: "0.5px", textAlign: "left", padding: "14px 16px", verticalAlign: "middle" }}>Session Date</th>
                  {viewMode === "trashbin" && (
                    <th style={{ color: "var(--text-muted)", fontSize: "0.78rem", fontWeight: "600", textTransform: "uppercase", letterSpacing: "0.5px", textAlign: "left", padding: "14px 16px", verticalAlign: "middle" }}>Actions</th>
                  )}
                </tr>
              </thead>
              <tbody>
                {adminAuditSessions.map((session) => {
                  const isCompleted = session.status === "completed";
                  const isFailed = session.status === "failed";
                  const score = session.compliance_score;
                  let scoreColor = "var(--text-muted)";
                  let scoreBg = "rgba(255, 255, 255, 0.03)";
                  let scoreBorder = "rgba(255, 255, 255, 0.05)";
                  if (isCompleted && score !== null) {
                    if (score >= 85) {
                      scoreColor = "#10b981";
                      scoreBg = "rgba(16, 185, 129, 0.08)";
                      scoreBorder = "rgba(16, 185, 129, 0.15)";
                    } else if (score >= 70) {
                      scoreColor = "#f59e0b";
                      scoreBg = "rgba(245, 158, 11, 0.08)";
                      scoreBorder = "rgba(245, 158, 11, 0.15)";
                    } else {
                      scoreColor = "#ef4444";
                      scoreBg = "rgba(239, 68, 68, 0.08)";
                      scoreBorder = "rgba(239, 68, 68, 0.15)";
                    }
                  }

                  return (
                    <tr
                      key={session.id}
                      className="stats-row"
                      style={{ borderBottom: "1px solid rgba(255, 255, 255, 0.04)", transition: "background-color 0.2s ease" }}
                      onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = "rgba(255, 255, 255, 0.01)"; }}
                      onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = "transparent"; }}
                    >
                      {/* ID Column */}
                      <td className="stats-label" style={{ textAlign: "left", padding: "14px 12px", verticalAlign: "left" }}>
                        <span style={{ fontSize: "0.8rem", fontWeight: 500, color: "var(--accent-cyan)", background: "rgba(0, 229, 255, 0.05)", padding: "3px 5px", borderRadius: "6px", border: "1px solid rgba(0, 229, 255, 0.15)", letterSpacing: "0.05em", fontFamily: "'JetBrains Mono', monospace" }}>
                          {(() => {
                            const name = (session.username || "Unknown").toUpperCase();
                            const prefix = name.length > 1 ? `${name[0]}${name[name.length - 1]}` : name[0];
                            const userSessions = adminAuditSessions.filter(s => s.username === session.username);
                            const absoluteIndex = userSessions.findIndex(s => s.id === session.id);
                            const numStr = String(userSessions.length - absoluteIndex).padStart(2, "0");
                            return `${prefix}${numStr}`;
                          })()}
                        </span>
                      </td>

                      {/* Username */}
                      <td className="stats-value" style={{ padding: "14px 16px", textAlign: "left", fontSize: "0.85rem", color: "var(--text-primary)", fontWeight: 600 }}>
                        {session.username || "Anonymous"}
                      </td>

                      {/* Reference File */}
                      <td className="stats-label" style={{ textAlign: "left", padding: "14px 16px", verticalAlign: "middle" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                          <FileText size={14} style={{ color: session.reference_drawing_id ? "var(--text-muted)" : "rgba(255,255,255,0.15)" }} />
                          <span style={{ color: session.reference_drawing_id ? "var(--text-primary)" : "var(--text-muted)", fontSize: "0.85rem" }}>
                            {session.reference_drawing_id ? getDrawingName(session.reference_drawing_id) : "—"}
                          </span>
                        </div>
                      </td>

                      {/* New File */}
                      <td className="stats-label" style={{ textAlign: "left", padding: "14px 16px", verticalAlign: "middle", fontWeight: "600" }}>
                        <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                            <FileText size={14} style={{ color: "var(--accent-cyan)" }} />
                            <span style={{ color: "var(--text-primary)", fontSize: "0.85rem" }}>
                              {getDrawingName(session.drawing_id)}
                            </span>
                          </div>
                          {session.remarks && (
                            <span style={{ fontSize: "0.72rem", color: "var(--accent-cyan)", display: "inline-flex", alignItems: "center", gap: "4px", background: "rgba(0, 229, 255, 0.05)", border: "1px solid rgba(0, 229, 255, 0.1)", padding: "2px 8px", borderRadius: "4px", width: "fit-content", fontWeight: "normal" }}>
                              <span style={{ width: "4px", height: "4px", borderRadius: "50%", background: "var(--accent-cyan)", display: "inline-block" }}></span>
                              {session.remarks}
                            </span>
                          )}
                        </div>
                      </td>

                      {/* Client Context */}
                      <td className="stats-value" style={{ textAlign: "left", padding: "14px 16px", color: "var(--text-primary)", verticalAlign: "middle", fontFamily: "inherit" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                          <Briefcase size={14} style={{ color: "var(--text-muted)", opacity: 0.6 }} />
                          <span style={{ fontSize: "0.85rem", color: session.client_name ? "var(--text-primary)" : "var(--text-muted)" }}>
                            {session.client_name || "Universal Standard"}
                          </span>
                        </div>
                      </td>

                      {/* Compliance Score */}
                      <td className="stats-value" style={{ textAlign: "left", padding: "14px 55px", verticalAlign: "middle", fontFamily: "inherit" }}>
                        {isCompleted ? (
                          <span style={{ display: "inline-flex", alignItems: "center", padding: "3px 8px", borderRadius: "6px", background: scoreBg, border: `1px solid ${scoreBorder}`, color: scoreColor, fontWeight: "800", fontSize: "0.82rem" }}>
                            {score !== null ? `${score.toFixed(1)}%` : "N/A"}
                          </span>
                        ) : isFailed ? (
                          <span style={{ background: "rgba(239, 68, 68, 0.08)", border: "1px solid rgba(239, 68, 68, 0.15)", color: "#ef4444", fontSize: "0.75rem", display: "inline-flex", alignItems: "center", gap: "6px", padding: "3px 8px", borderRadius: "6px" }} title={session.error_message || "Audit pipeline failed"}>
                            <AlertTriangle size={12} /> Failed
                          </span>
                        ) : (
                          <span style={{ background: "rgba(0, 229, 255, 0.05)", border: "1px solid rgba(0, 229, 255, 0.12)", color: "var(--accent-cyan)", fontSize: "0.75rem", display: "inline-flex", alignItems: "center", gap: "6px", padding: "3px 8px", borderRadius: "6px" }}>
                            <Loader size={12} className="spin-animation" /> Auditing...
                          </span>
                        )}
                      </td>

                      {/* Session Date */}
                      <td className="stats-value" style={{ textAlign: "left", padding: "14px 16px", color: "var(--text-muted)", fontSize: "0.82rem", verticalAlign: "middle", fontFamily: "'JetBrains Mono', monospace" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                          <Clock size={12} style={{ opacity: 0.6 }} />
                          <span>
                            {parseUtcDate(session.created_at).toLocaleString(undefined, {
                              month: "short", day: "numeric", hour: "2-digit", minute: "2-digit"
                            })}
                          </span>
                        </div>
                      </td>

                      {/* Actions */}
                      {viewMode === "trashbin" && (
                        <td className="stats-value" style={{ textAlign: "left", padding: "14px 16px", verticalAlign: "middle" }}>
                          <div style={{ display: "inline-flex", gap: "8px", justifyContent: "flex-start" }}>
                            <button
                              className="btn-action-round"
                              onClick={() => handleRestore(session.id, session.drawing_id)}
                              title="Restore Session"
                              style={{ background: "rgba(16, 185, 129, 0.1)", color: "#10b981", border: "1px solid rgba(16, 185, 129, 0.2)", padding: "6px", borderRadius: "6px", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", transition: "all 0.2s ease" }}
                            >
                              <RefreshCcw size={14} />
                            </button>
                          </div>
                        </td>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* STYLING BLOCK (INHERITED FROM USER MANAGEMENT) */}
      <style>{`
        .admin-subpage {
          animation: fadeIn 0.4s ease-out;
        }

        /* 1. TOAST NOTIFICATIONS styling */
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

        .admin-toast.error {
          background: rgba(24, 24, 27, 0.95);
          border-left-color: #ef4444;
          border: 1px solid rgba(239, 68, 68, 0.2);
          color: #ef4444;
        }

        /* 2. METRICS STRIP */
        .admin-metrics-grid {
          display: grid;
          grid-template-columns: repeat(4, 1fr);
          gap: 16px;
          margin-bottom: 24px;
        }

        .metrics-card.card {
          display: flex;
          align-items: center;
          gap: 16px;
          padding: 16px 20px !important;
          border: 1px solid var(--border-color);
          border-radius: 12px;
          background: var(--bg-card);
          transition: all 0.25s ease;
        }

        .metrics-card.card:hover {
          transform: translateY(-2px);
          box-shadow: 0 6px 20px rgba(0, 0, 0, 0.2);
          border-color: rgba(255, 255, 255, 0.1);
        }

        .metrics-icon-wrapper {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 42px;
          height: 42px;
          border-radius: 10px;
        }

        .metrics-icon-wrapper.blue { background: rgba(59, 130, 246, 0.1); color: #3b82f6; }
        .metrics-icon-wrapper.green { background: rgba(16, 185, 129, 0.1); color: #10b981; }
        .metrics-icon-wrapper.purple { background: rgba(168, 85, 247, 0.1); color: #a855f7; }

        .metrics-data {
          display: flex;
          flex-direction: column;
        }

        .metrics-value {
          font-size: 1.4rem;
          font-weight: 700;
          color: var(--text-primary);
          line-height: 1.1;
        }

        .metrics-label {
          font-size: 0.72rem;
          color: var(--text-muted);
          margin-top: 2px;
          text-transform: uppercase;
          letter-spacing: 0.05em;
          font-weight: 600;
        }

        /* 3. FILTER CONTROL PANEL */
        .filter-control-card {
          padding: 16px 20px;
          background: var(--bg-card);
          border: 1px solid var(--border-color);
          border-radius: 12px;
        }

        .filter-search-group {
          display: flex;
          justify-content: space-between;
          align-items: center;
          flex-wrap: wrap;
          gap: 16px;
        }

        .filter-pill-group {
          display: flex;
          align-items: center;
          gap: 6px;
          background: rgba(0, 0, 0, 0.2);
          padding: 4px;
          border-radius: 8px;
          border: 1px solid rgba(255, 255, 255, 0.05);
        }

        .filter-pill-label {
          font-size: 0.75rem;
          color: var(--text-muted);
          margin: 0 8px 0 6px;
          font-weight: 600;
        }

        .filter-pill-btn {
          background: transparent;
          border: 1px solid transparent;
          color: var(--text-muted);
          font-size: 0.8rem;
          padding: 6px 14px;
          border-radius: 6px;
          cursor: pointer;
          transition: all 0.2s ease;
          font-weight: 500;
        }

        .filter-pill-btn:hover {
          color: var(--text-primary);
          background: rgba(255, 255, 255, 0.05);
        }

        .filter-pill-btn.active {
          background: rgba(255, 255, 255, 0.1);
          color: var(--text-primary);
          border-color: rgba(255, 255, 255, 0.15);
          box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
        }

        @keyframes fadeIn {
          from { opacity: 0; transform: translateY(8px); }
          to { opacity: 1; transform: translateY(0); }
        }

        @keyframes slideInRight {
          from { transform: translateX(100%); opacity: 0; }
          to { transform: translateX(0); opacity: 1; }
        }
      `}</style>
    </div>
  );
};
