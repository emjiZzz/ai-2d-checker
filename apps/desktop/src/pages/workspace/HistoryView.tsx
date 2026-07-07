/**
 * HistoryView.tsx
 *
 * Extracted from AuditWorkspace.tsx (Phase 1 refactor).
 * Previously lines 2169-2599 (IIFE body) + 3230-3322 (Edit/Delete modals) of AuditWorkspace.tsx.
 *
 * State that lived in AuditWorkspace and is now owned here:
 *   - historySearchQuery, historyStatusFilter, historyScoreFilter (filter controls)
 *   - isEditModalOpen, isDeleteModalOpen (modal open/close)
 *   - selectedSessionForEdit, selectedSessionForDelete (modal targets)
 *   - remarksText (edit textarea)
 *
 * State that still lives in AuditWorkspace and is passed as props:
 *   - sessions (from useAuditStore)
 *   - drawings (local drawing catalog)
 *   - updateSession, deleteSession (store actions)
 *   - setCurrentNav (navigation)
 *   - apiToken, backendUrl (for handleOpenSession network call)
 *   - handleOpenSession (needs to call parent to load session into workspace canvas)
 */

import React, { useState } from "react";
import {
  AlertTriangle,
  BarChart2,
  Briefcase,
  Clock,
  Database,
  Edit,
  FileText,
  Filter,
  FolderOpen,
  Loader,
  Play,
  Search,
  TrendingUp,
  Trash2,
} from "lucide-react";
import { DrawingItem } from "../../stores/workspaceStore";

// Helper utility to parse ISO datetime strings from backend reliably as UTC
const parseUtcDate = (dateStr: string | null | undefined): Date => {
  if (!dateStr) return new Date();
  const utcStr = dateStr.includes("Z") || dateStr.includes("+") ? dateStr : dateStr + "Z";
  return new Date(utcStr);
};

interface HistoryViewProps {
  sessions: any[] | null;
  drawings: DrawingItem[];
  updateSession: (id: string, remarks: string) => Promise<boolean>;
  deleteSession: (id: string) => Promise<boolean>;
  setCurrentNav: (nav: any) => void;
  handleOpenSession: (session: any) => void;
}

export const HistoryView: React.FC<HistoryViewProps> = ({
  sessions,
  drawings,
  updateSession,
  deleteSession,
  setCurrentNav,
  handleOpenSession,
}) => {
  // Filter controls — moved from AuditWorkspace
  const [historySearchQuery, setHistorySearchQuery] = useState("");
  const [historyStatusFilter, setHistoryStatusFilter] = useState<"all" | "completed" | "failed" | "auditing">("all");
  const [historyScoreFilter, setHistoryScoreFilter] = useState<"all" | "excellent" | "warning">("all");

  // Modal state — moved from AuditWorkspace
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [selectedSessionForEdit, setSelectedSessionForEdit] = useState<any>(null);
  const [selectedSessionForDelete, setSelectedSessionForDelete] = useState<any>(null);
  const [remarksText, setRemarksText] = useState("");

  const getDrawingName = (drawingId: string) => {
    const drawing = drawings.find((d: DrawingItem) => d.id === drawingId);
    return drawing ? drawing.file_name : drawingId;
  };

  const handleSaveRemarks = async () => {
    if (!selectedSessionForEdit) return;
    const success = await updateSession(selectedSessionForEdit.id, remarksText);
    if (success) {
      setIsEditModalOpen(false);
      setSelectedSessionForEdit(null);
      setRemarksText("");
    }
  };

  const handleDeleteConfirm = async () => {
    if (!selectedSessionForDelete) return;
    const success = await deleteSession(selectedSessionForDelete.id);
    if (success) {
      setIsDeleteModalOpen(false);
      setSelectedSessionForDelete(null);
    }
  };

  // Derived stats — verbatim from the original IIFE
  const completedSessionsCount = sessions ? sessions.filter(s => s.status === "completed" && s.compliance_score !== null).length : 0;
  const avgCompliance = completedSessionsCount > 0
    ? (sessions!.filter(s => s.status === "completed" && s.compliance_score !== null).reduce((sum, s) => sum + s.compliance_score!, 0) / completedSessionsCount).toFixed(1) + "%"
    : "N/A";

  const completedCount = sessions ? sessions.filter(s => s.status === "completed").length : 0;
  const failedCount = sessions ? sessions.filter(s => s.status === "failed").length : 0;
  const successRate = (completedCount + failedCount) > 0
    ? ((completedCount / (completedCount + failedCount)) * 100).toFixed(0) + "%"
    : "100%";

  const filteredSessions = (sessions || []).filter((session) => {
    const refName = session.reference_drawing_id ? getDrawingName(session.reference_drawing_id) : "";
    const newName = getDrawingName(session.drawing_id);
    const client = session.client_name || "";
    const remarks = session.remarks || "";
    const matchesSearch =
      refName.toLowerCase().includes(historySearchQuery.toLowerCase()) ||
      newName.toLowerCase().includes(historySearchQuery.toLowerCase()) ||
      client.toLowerCase().includes(historySearchQuery.toLowerCase()) ||
      remarks.toLowerCase().includes(historySearchQuery.toLowerCase());

    const matchesStatus =
      historyStatusFilter === "all" ||
      (historyStatusFilter === "completed" && session.status === "completed") ||
      (historyStatusFilter === "failed" && session.status === "failed") ||
      (historyStatusFilter === "auditing" && session.status !== "completed" && session.status !== "failed");

    const matchesScore =
      historyScoreFilter === "all" ||
      (historyScoreFilter === "excellent" && session.status === "completed" && session.compliance_score !== null && session.compliance_score >= 85) ||
      (historyScoreFilter === "warning" && session.status === "completed" && session.compliance_score !== null && session.compliance_score < 85);

    return matchesSearch && matchesStatus && matchesScore;
  });

  return (
    <>
      <main className="workspace-main-viewport padded" style={{ display: "flex", flexDirection: "column", gap: "24px" }}>
        <div className="subpage-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", flexWrap: "wrap", gap: "16px" }}>
          <div>
            <h2 className="section-title">Audit History Archive</h2>
            <p className="section-desc">View historically logged revision comparison sessions and compliance reports.</p>
          </div>
          {sessions && sessions.length > 0 && (
            <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", background: "rgba(255,255,255,0.03)", padding: "4px 10px", borderRadius: "12px", border: "1px solid rgba(255,255,255,0.05)" }}>
              Total sessions loaded: <strong style={{ color: "var(--text-primary)" }}>{sessions.length}</strong>
            </span>
          )}
        </div>

        {/* DYNAMIC STATISTICS SUMMARY DECK */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "16px" }}>
          {/* Card 1: Total Runs */}
          <div className="card" style={{ display: "flex", alignItems: "center", gap: "16px", padding: "16px 20px", background: "linear-gradient(135deg, rgba(255, 255, 255, 0.02) 0%, rgba(255, 255, 255, 0.005) 100%)", border: "1px solid rgba(255, 255, 255, 0.05)", borderRadius: "12px" }}>
            <div style={{ width: "42px", height: "42px", borderRadius: "10px", background: "rgba(59, 130, 246, 0.08)", border: "1px solid rgba(59, 130, 246, 0.15)", display: "flex", alignItems: "center", justifyContent: "center", color: "var(--accent-cyan)", boxShadow: "0 0 12px rgba(59, 130, 246, 0.05)" }}>
              <Database size={18} />
            </div>
            <div>
              <span style={{ fontSize: "0.72rem", textTransform: "uppercase", letterSpacing: "0.8px", color: "var(--text-muted)", fontWeight: "600" }}>Total Audit Runs</span>
              <h3 style={{ fontSize: "1.4rem", fontWeight: "700", marginTop: "2px", color: "var(--text-primary)", fontFamily: "'JetBrains Mono', monospace" }}>
                {sessions ? sessions.length : 0}
              </h3>
            </div>
          </div>

          {/* Card 2: Average Compliance */}
          <div className="card" style={{ display: "flex", alignItems: "center", gap: "16px", padding: "16px 20px", background: "linear-gradient(135deg, rgba(255, 255, 255, 0.02) 0%, rgba(255, 255, 255, 0.005) 100%)", border: "1px solid rgba(255, 255, 255, 0.05)", borderRadius: "12px" }}>
            <div style={{ width: "42px", height: "42px", borderRadius: "10px", background: "rgba(16, 185, 129, 0.08)", border: "1px solid rgba(16, 185, 129, 0.15)", display: "flex", alignItems: "center", justifyContent: "center", color: "#10b981", boxShadow: "0 0 12px rgba(16, 185, 129, 0.05)" }}>
              <BarChart2 size={18} />
            </div>
            <div>
              <span style={{ fontSize: "0.72rem", textTransform: "uppercase", letterSpacing: "0.8px", color: "var(--text-muted)", fontWeight: "600" }}>Avg Compliance</span>
              <h3 style={{ fontSize: "1.4rem", fontWeight: "700", marginTop: "2px", color: "#10b981", fontFamily: "'JetBrains Mono', monospace" }}>
                {avgCompliance}
              </h3>
            </div>
          </div>

          {/* Card 3: Success Rate */}
          <div className="card" style={{ display: "flex", alignItems: "center", gap: "16px", padding: "16px 20px", background: "linear-gradient(135deg, rgba(255, 255, 255, 0.02) 0%, rgba(255, 255, 255, 0.005) 100%)", border: "1px solid rgba(255, 255, 255, 0.05)", borderRadius: "12px" }}>
            <div style={{ width: "42px", height: "42px", borderRadius: "10px", background: "rgba(168, 85, 247, 0.08)", border: "1px solid rgba(168, 85, 247, 0.15)", display: "flex", alignItems: "center", justifyContent: "center", color: "#a855f7", boxShadow: "0 0 12px rgba(168, 85, 247, 0.05)" }}>
              <TrendingUp size={18} />
            </div>
            <div>
              <span style={{ fontSize: "0.72rem", textTransform: "uppercase", letterSpacing: "0.8px", color: "var(--text-muted)", fontWeight: "600" }}>Pipeline Success</span>
              <h3 style={{ fontSize: "1.4rem", fontWeight: "700", marginTop: "2px", color: "#a855f7", fontFamily: "'JetBrains Mono', monospace" }}>
                {successRate}
              </h3>
            </div>
          </div>
        </div>

        {/* INTERACTIVE CONTROLS BAR: SEARCH & MULTI-CRITERIA FILTERS */}
        <div className="card" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: "16px", padding: "14px 20px", background: "rgba(255, 255, 255, 0.01)", border: "1px solid rgba(255, 255, 255, 0.04)", borderRadius: "12px" }}>
          <div style={{ display: "flex", flex: 1, gap: "12px", alignItems: "center", minWidth: "290px" }}>
            <div style={{ position: "relative", flex: 1 }}>
              <Search size={16} style={{ position: "absolute", left: "12px", top: "50%", transform: "translateY(-50%)", color: "var(--text-muted)" }} />
              <input
                type="text"
                placeholder="Search drawing name, remarks, or client context..."
                value={historySearchQuery}
                onChange={(e) => setHistorySearchQuery(e.target.value)}
                className="form-input"
                style={{ paddingLeft: "36px", height: "38px", background: "rgba(0, 0, 0, 0.25)", border: "1px solid rgba(255, 255, 255, 0.08)", borderRadius: "8px", fontSize: "0.85rem", width: "100%", transition: "all 0.2s ease" }}
              />
            </div>
          </div>

          <div style={{ display: "flex", gap: "16px", alignItems: "center", flexWrap: "wrap" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <Filter size={13} style={{ color: "var(--text-muted)" }} />
              <span style={{ fontSize: "0.8rem", color: "var(--text-muted)", fontWeight: "500" }}>Status:</span>
              <select
                value={historyStatusFilter}
                onChange={(e) => setHistoryStatusFilter(e.target.value as any)}
                className="form-input"
                style={{ height: "38px", padding: "0 10px", background: "rgba(0,0,0,0.25)", border: "1px solid rgba(255, 255, 255, 0.08)", borderRadius: "8px", fontSize: "0.85rem", color: "var(--text-primary)", width: "140px", cursor: "pointer", outline: "none" }}
              >
                <option value="all">All Statuses</option>
                <option value="completed">Completed</option>
                <option value="failed">Failed</option>
                <option value="auditing">Active Auditing</option>
              </select>
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <span style={{ fontSize: "0.8rem", color: "var(--text-muted)", fontWeight: "500" }}>Compliance:</span>
              <select
                value={historyScoreFilter}
                onChange={(e) => setHistoryScoreFilter(e.target.value as any)}
                className="form-input"
                style={{ height: "38px", padding: "0 10px", background: "rgba(0,0,0,0.25)", border: "1px solid rgba(255, 255, 255, 0.08)", borderRadius: "8px", fontSize: "0.85rem", color: "var(--text-primary)", width: "155px", cursor: "pointer", outline: "none" }}
              >
                <option value="all">All Scores</option>
                <option value="excellent">Excellent (≥ 85%)</option>
                <option value="warning">Warning (&lt; 85%)</option>
              </select>
            </div>
          </div>
        </div>

        {/* ARCHIVE GRID / RESULTS TABLE */}
        {filteredSessions.length > 0 ? (
          <div className="card settings-card" style={{ padding: "0px", overflow: "hidden", border: "1px solid rgba(255, 255, 255, 0.06)", borderRadius: "12px", background: "var(--bg-card)" }}>
            <table className="stats-table" style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr className="stats-row" style={{ background: "rgba(255, 255, 255, 0.015)", borderBottom: "1px solid rgba(255, 255, 255, 0.06)" }}>
                  <th style={{ color: "var(--text-muted)", fontSize: "0.78rem", fontWeight: "600", textTransform: "uppercase", letterSpacing: "0.5px", textAlign: "left", padding: "14px 16px", verticalAlign: "middle", width: "90px" }}>ID</th>
                  <th style={{ color: "var(--text-muted)", fontSize: "0.78rem", fontWeight: "600", textTransform: "uppercase", letterSpacing: "0.5px", textAlign: "left", padding: "14px 16px", verticalAlign: "middle" }}>Original Drawing</th>
                  <th style={{ color: "var(--text-muted)", fontSize: "0.78rem", fontWeight: "600", textTransform: "uppercase", letterSpacing: "0.5px", textAlign: "left", padding: "14px 16px", verticalAlign: "middle" }}>KMTI Drawing</th>
                  <th style={{ color: "var(--text-muted)", fontSize: "0.78rem", fontWeight: "600", textTransform: "uppercase", letterSpacing: "0.5px", textAlign: "left", padding: "14px 16px", verticalAlign: "middle" }}>Client</th>
                  <th style={{ color: "var(--text-muted)", fontSize: "0.78rem", fontWeight: "600", textTransform: "uppercase", letterSpacing: "0.5px", textAlign: "left", padding: "14px 16px", verticalAlign: "middle" }}>Compliance Score</th>
                  <th style={{ color: "var(--text-muted)", fontSize: "0.78rem", fontWeight: "600", textTransform: "uppercase", letterSpacing: "0.5px", textAlign: "left", padding: "14px 16px", verticalAlign: "middle" }}>Session Date</th>
                  <th style={{ color: "var(--text-muted)", fontSize: "0.78rem", fontWeight: "600", textTransform: "uppercase", letterSpacing: "0.5px", textAlign: "left", padding: "14px 16px", verticalAlign: "middle" }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredSessions.map((session) => {
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
                      style={{
                        borderBottom: "1px solid rgba(255, 255, 255, 0.04)",
                        transition: "background-color 0.2s ease"
                      }}
                      onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = "rgba(255, 255, 255, 0.01)"; }}
                      onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = "transparent"; }}
                    >
                      {/* ID Column */}
                      <td className="stats-label" style={{ textAlign: "left", padding: "14px 12px", verticalAlign: "left" }}>
                        <span style={{ fontSize: "0.8rem", fontWeight: 500, color: "var(--accent-cyan)", background: "rgba(0, 229, 255, 0.05)", padding: "3px 5px", borderRadius: "6px", border: "1px solid rgba(0, 229, 255, 0.15)", letterSpacing: "0.05em", fontFamily: "'JetBrains Mono', monospace" }}>
                          {(() => {
                            const prefix = "SYS";
                            const absoluteIndex = sessions!.findIndex(s => s.id === session.id);
                            const numStr = String(sessions!.length - absoluteIndex).padStart(2, "0");
                            return `${prefix}${numStr}`;
                          })()}
                        </span>
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
                      <td className="stats-value" style={{ padding: "14px 16px", color: "var(--text-primary)", verticalAlign: "middle", textAlign: "left", fontFamily: "inherit" }}>
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
                              month: "short",
                              day: "numeric",
                              hour: "2-digit",
                              minute: "2-digit"
                            })}
                          </span>
                        </div>
                      </td>

                      {/* Actions */}
                      <td className="stats-value" style={{ textAlign: "left", padding: "14px 16px", verticalAlign: "middle" }}>
                        <div style={{ display: "flex", justifyContent: "flex-start", gap: "8px" }}>
                          <button
                            onClick={() => handleOpenSession(session)}
                            disabled={session.status !== "completed"}
                            title="Open visual canvas review"
                            className="action-icon-btn"
                            style={{
                              background: "rgba(128, 128, 128, 0.08)",
                              border: "1px solid rgba(255, 255, 255, 0.05)",
                              color: session.status === "completed" ? "var(--accent-cyan)" : "var(--text-muted)",
                              padding: "7px",
                              borderRadius: "6px",
                              cursor: session.status === "completed" ? "pointer" : "not-allowed",
                              display: "flex",
                              alignItems: "center",
                              justifyContent: "center",
                              transition: "all 0.2s cubic-bezier(0.4, 0, 0.2, 1)"
                            }}
                            onMouseEnter={(e) => {
                              if (session.status === "completed") {
                                e.currentTarget.style.background = "rgba(0, 229, 255, 0.15)";
                                e.currentTarget.style.borderColor = "var(--accent-cyan)";
                                e.currentTarget.style.color = "var(--bg-dark)";
                                e.currentTarget.style.transform = "scale(1.05)";
                              }
                            }}
                            onMouseLeave={(e) => {
                              if (session.status === "completed") {
                                e.currentTarget.style.background = "rgba(128, 128, 128, 0.08)";
                                e.currentTarget.style.borderColor = "rgba(255, 255, 255, 0.05)";
                                e.currentTarget.style.color = "var(--accent-cyan)";
                                e.currentTarget.style.transform = "scale(1)";
                              }
                            }}
                          >
                            <FolderOpen size={14} />
                          </button>
                          <button
                            onClick={() => {
                              setSelectedSessionForEdit(session);
                              setRemarksText(session.remarks || "");
                              setIsEditModalOpen(true);
                            }}
                            title="Edit custom remarks"
                            className="action-icon-btn"
                            style={{
                              background: "rgba(128, 128, 128, 0.08)",
                              border: "1px solid rgba(255, 255, 255, 0.05)",
                              color: "var(--text-primary)",
                              padding: "7px",
                              borderRadius: "6px",
                              cursor: "pointer",
                              display: "flex",
                              alignItems: "center",
                              justifyContent: "center",
                              transition: "all 0.2s cubic-bezier(0.4, 0, 0.2, 1)"
                            }}
                            onMouseEnter={(e) => {
                              e.currentTarget.style.background = "rgba(245, 158, 11, 0.15)";
                              e.currentTarget.style.borderColor = "#f59e0b";
                              e.currentTarget.style.color = "var(--bg-dark)";
                              e.currentTarget.style.transform = "scale(1.05)";
                            }}
                            onMouseLeave={(e) => {
                              e.currentTarget.style.background = "rgba(128, 128, 128, 0.08)";
                              e.currentTarget.style.borderColor = "rgba(255, 255, 255, 0.05)";
                              e.currentTarget.style.color = "var(--text-primary)";
                              e.currentTarget.style.transform = "scale(1)";
                            }}
                          >
                            <Edit size={14} />
                          </button>
                          <button
                            onClick={() => {
                              setSelectedSessionForDelete(session);
                              setIsDeleteModalOpen(true);
                            }}
                            title="Purge session record"
                            className="action-icon-btn destructive"
                            style={{
                              background: "rgba(239, 68, 68, 0.05)",
                              border: "1px solid rgba(239, 68, 68, 0.1)",
                              color: "#ef4444",
                              padding: "7px",
                              borderRadius: "6px",
                              cursor: "pointer",
                              display: "flex",
                              alignItems: "center",
                              justifyContent: "center",
                              transition: "all 0.2s cubic-bezier(0.4, 0, 0.2, 1)"
                            }}
                            onMouseEnter={(e) => {
                              e.currentTarget.style.background = "rgba(239, 68, 68, 0.2)";
                              e.currentTarget.style.borderColor = "#ef4444";
                              e.currentTarget.style.transform = "scale(1.05)";
                            }}
                            onMouseLeave={(e) => {
                              e.currentTarget.style.background = "rgba(239, 68, 68, 0.05)";
                              e.currentTarget.style.borderColor = "rgba(239, 68, 68, 0.1)";
                              e.currentTarget.style.transform = "scale(1)";
                            }}
                          >
                            <Trash2 size={14} />
                          </button>
                          {session.is_restored && (
                            <span style={{ fontSize: "0.65rem", fontWeight: 700, padding: "4px 8px", borderRadius: "6px", background: "rgba(16, 185, 129, 0.1)", color: "#10b981", border: "1px solid rgba(16, 185, 129, 0.25)", textTransform: "uppercase", letterSpacing: "0.05em", display: "flex", alignItems: "center", marginLeft: "4px", boxShadow: "0 2px 4px rgba(16, 185, 129, 0.1)" }}>
                              Restored
                            </span>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          /* GLASSMORPHIC EMPTY STATE FALLBACK */
          <div className="card" style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "48px 24px", textAlign: "center", background: "rgba(255, 255, 255, 0.015)", border: "1px dashed rgba(255, 255, 255, 0.08)", borderRadius: "12px", marginTop: "12px", boxShadow: "inset 0 1px 3px rgba(255,255,255,0.02)" }}>
            <div style={{ width: "56px", height: "56px", borderRadius: "50%", background: "rgba(128, 128, 128, 0.08)", border: "1px solid rgba(255, 255, 255, 0.05)", display: "flex", alignItems: "center", justifyContent: "center", color: "var(--text-muted)", marginBottom: "18px" }}>
              <Database size={24} />
            </div>
            <h4 style={{ fontWeight: "700", color: "var(--text-primary)", fontSize: "1.1rem", marginBottom: "8px" }}>No matching archives found</h4>
            <p style={{ color: "var(--text-muted)", fontSize: "0.85rem", maxWidth: "420px", marginBottom: "22px", lineHeight: "1.6" }}>
              {sessions && sessions.length > 0
                ? "No historical runs match your current query or filter selectors. Reset filters to view all sessions."
                : "No CAD compliance runs have been archived yet. Go to the review workspace to launch your first compliance check!"}
            </p>
            {sessions && sessions.length > 0 ? (
              <button
                className="btn btn-secondary"
                onClick={() => {
                  setHistorySearchQuery("");
                  setHistoryStatusFilter("all");
                  setHistoryScoreFilter("all");
                }}
                style={{ padding: "8px 24px", borderRadius: "8px", fontSize: "0.85rem", cursor: "pointer" }}
              >
                Clear all filters
              </button>
            ) : (
              <button
                className="btn btn-primary"
                onClick={() => setCurrentNav("workspace")}
                style={{ padding: "10px 24px", borderRadius: "8px", fontSize: "0.85rem", cursor: "pointer", display: "inline-flex", gap: "8px", alignItems: "center" }}
              >
                <Play size={12} /> Launch Compliance Check
              </button>
            )}
          </div>
        )}
      </main>

      {/* Edit Remarks Modal — moved from AuditWorkspace (was lines 3230-3280) */}
      {isEditModalOpen && selectedSessionForEdit && (
        <div className="frosted-glass-modal-overlay">
          <div className="frosted-modal-card">
            <div className="modal-header">
              <h3 className="modal-title">Edit Session Remarks</h3>
              <p className="modal-subtitle">Add custom notes or checker logs for this revision audit.</p>
            </div>
            <div className="modal-body" style={{ marginTop: "16px" }}>
              <div className="form-group" style={{ margin: 0 }}>
                <label className="form-label" style={{ marginBottom: "8px", display: "block", fontSize: "0.8rem", color: "var(--text-muted)" }}>Remarks / Notes</label>
                <textarea
                  className="form-input"
                  style={{
                    width: "100%",
                    height: "120px",
                    resize: "none",
                    padding: "10px",
                    fontSize: "0.85rem",
                    lineHeight: "1.4",
                    background: "rgba(0, 0, 0, 0.2)",
                    border: "1px solid rgba(255, 255, 255, 0.1)",
                    borderRadius: "6px",
                    color: "var(--text-primary)"
                  }}
                  value={remarksText}
                  onChange={(e) => setRemarksText(e.target.value)}
                  placeholder="Enter custom remarks for this session..."
                />
              </div>
            </div>
            <div className="modal-footer" style={{ display: "flex", justifyContent: "flex-end", gap: "10px", marginTop: "20px" }}>
              <button
                className="btn-neutral-outline"
                onClick={() => {
                  setIsEditModalOpen(false);
                  setSelectedSessionForEdit(null);
                  setRemarksText("");
                }}
              >
                Cancel
              </button>
              <button
                className="btn-gradient-submit"
                onClick={handleSaveRemarks}
              >
                Save Remarks
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal — moved from AuditWorkspace (was lines 3282-3322) */}
      {isDeleteModalOpen && selectedSessionForDelete && (
        <div className="frosted-glass-modal-overlay">
          <div className="frosted-modal-card destructive-card">
            <div className="modal-header">
              <div className="warning-icon-wrapper">
                <AlertTriangle size={24} className="destructive-warning-icon" />
              </div>
              <h3 className="modal-title destructive-title" style={{ marginTop: "12px" }}>Purge Session Record?</h3>
              <p className="modal-subtitle destructive-desc">
                You are about to permanently delete this audit session log and all associated violations from MongoDB. This action is irreversible.
              </p>
            </div>
            <div className="modal-body" style={{ marginTop: "16px", padding: "12px", background: "rgba(239, 68, 68, 0.05)", border: "1px solid rgba(239, 68, 68, 0.15)", borderRadius: "6px" }}>
              <div style={{ fontSize: "0.8rem", display: "flex", flexDirection: "column", gap: "6px" }}>
                <span style={{ color: "var(--text-muted)" }}>Target File: <strong style={{ color: "var(--text-primary)" }}>{getDrawingName(selectedSessionForDelete.drawing_id)}</strong></span>
                {selectedSessionForDelete.reference_drawing_id && (
                  <span style={{ color: "var(--text-muted)" }}>Reference File: <strong style={{ color: "var(--text-primary)" }}>{getDrawingName(selectedSessionForDelete.reference_drawing_id)}</strong></span>
                )}
                <span style={{ color: "var(--text-muted)" }}>Session Date: <strong style={{ color: "var(--text-primary)" }}>{parseUtcDate(selectedSessionForDelete.created_at).toLocaleString()}</strong></span>
              </div>
            </div>
            <div className="modal-footer" style={{ display: "flex", justifyContent: "flex-end", gap: "10px", marginTop: "24px" }}>
              <button
                className="btn-neutral-outline"
                onClick={() => {
                  setIsDeleteModalOpen(false);
                  setSelectedSessionForDelete(null);
                }}
              >
                Keep Record
              </button>
              <button
                className="btn-destructive-submit"
                onClick={handleDeleteConfirm}
              >
                Purge Record
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};
