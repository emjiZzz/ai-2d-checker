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
import { Button } from "../../components/ui/Button";
import { Modal } from "../../components/ui/Modal";
import { Badge } from "../../components/ui/Badge";

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
      <main className="flex-grow h-full min-h-0 overflow-y-auto bg-bg-dark py-8 px-8 box-border flex flex-col gap-6">
        <div className="flex justify-between items-end flex-wrap gap-4 mb-2">
          <div>
            <h2 className="text-xl font-extrabold text-text-primary m-0 tracking-tight">Audit History Archive</h2>
            <p className="text-xs text-text-muted mt-1 leading-relaxed">View historically logged revision comparison sessions and compliance reports.</p>
          </div>
          {sessions && sessions.length > 0 && (
            <span className="text-xs text-text-muted bg-sidebar-item-hover py-1 px-2.5 rounded-full border border-border-color">
              Total sessions loaded: <strong className="text-text-primary">{sessions.length}</strong>
            </span>
          )}
        </div>

        {/* DYNAMIC STATISTICS SUMMARY DECK */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* Card 1: Total Runs */}
          <div className="flex items-center gap-4 p-5 bg-bg-card border border-border-color rounded-xl shadow-sm">
            <div className="w-10 h-10 rounded-lg flex items-center justify-center border shadow-xs select-none shrink-0 bg-blue-500/8 border-blue-500/15 text-accent-cyan shadow-blue-500/5">
              <Database size={18} />
            </div>
            <div>
              <span className="text-[10px] uppercase tracking-wider text-text-muted font-semibold">Total Audit Runs</span>
              <h3 className="text-xl font-bold mt-0.5 text-text-primary font-mono">
                {sessions ? sessions.length : 0}
              </h3>
            </div>
          </div>

          {/* Card 2: Average Compliance */}
          <div className="flex items-center gap-4 p-5 bg-bg-card border border-border-color rounded-xl shadow-sm">
            <div className="w-10 h-10 rounded-lg flex items-center justify-center border shadow-xs select-none shrink-0 bg-emerald-500/8 border-emerald-500/15 text-emerald-400 shadow-emerald-500/5">
              <BarChart2 size={18} />
            </div>
            <div>
              <span className="text-[10px] uppercase tracking-wider text-text-muted font-semibold">Avg Compliance</span>
              <h3 className="text-xl font-bold mt-0.5 text-emerald-400 font-mono">
                {avgCompliance}
              </h3>
            </div>
          </div>

          {/* Card 3: Success Rate */}
          <div className="flex items-center gap-4 p-5 bg-bg-card border border-border-color rounded-xl shadow-sm">
            <div className="w-10 h-10 rounded-lg flex items-center justify-center border shadow-xs select-none shrink-0 bg-purple-500/8 border-purple-500/15 text-purple-400 shadow-purple-500/5">
              <TrendingUp size={18} />
            </div>
            <div>
              <span className="text-[10px] uppercase tracking-wider text-text-muted font-semibold">Pipeline Success</span>
              <h3 className="text-xl font-bold mt-0.5 text-purple-400 font-mono">
                {successRate}
              </h3>
            </div>
          </div>
        </div>

        {/* INTERACTIVE CONTROLS BAR: SEARCH & MULTI-CRITERIA FILTERS */}
        <div className="flex flex-wrap items-center justify-between gap-4 p-4 bg-bg-card border border-border-color rounded-xl">
          <div className="flex flex-1 gap-3 items-center min-w-[290px]">
            <div className="relative flex-1">
              <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
              <input
                type="text"
                placeholder="Search drawing name, remarks, or client context..."
                value={historySearchQuery}
                onChange={(e) => setHistorySearchQuery(e.target.value)}
                className="w-full bg-bg-sidebar border border-border-color rounded-lg py-2 px-3.5 pl-9 text-xs text-text-primary font-mono focus:outline-none focus:border-accent-cyan focus:shadow-[0_0_10px_rgba(0,229,255,0.15)] transition-all cursor-pointer"
              />
            </div>
          </div>

          <div className="flex gap-4 items-center flex-wrap">
            <div className="flex items-center gap-2">
              <Filter size={13} className="text-text-muted" />
              <span className="text-xs text-text-muted font-medium">Status:</span>
              <select
                value={historyStatusFilter}
                onChange={(e) => setHistoryStatusFilter(e.target.value as any)}
                className="w-36 bg-bg-sidebar border border-border-color rounded-lg py-2 px-3 text-xs text-text-primary font-mono focus:outline-none focus:border-accent-cyan focus:shadow-[0_0_10px_rgba(0,229,255,0.15)] transition-all cursor-pointer"
              >
                <option value="all">All Statuses</option>
                <option value="completed">Completed</option>
                <option value="failed">Failed</option>
                <option value="auditing">Active Auditing</option>
              </select>
            </div>

            <div className="flex items-center gap-2">
              <span className="text-xs text-text-muted font-medium">Compliance:</span>
              <select
                value={historyScoreFilter}
                onChange={(e) => setHistoryScoreFilter(e.target.value as any)}
                className="w-40 bg-transparent border border-border-color rounded-lg py-2 px-3 text-xs text-text-primary font-mono focus:outline-none focus:border-accent-cyan focus:shadow-[0_0_10px_rgba(0,229,255,0.15)] transition-all cursor-pointer"
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
          <div className="bg-bg-card border border-border-color rounded-xl p-0 overflow-hidden shadow-sm">
            <table className="w-full border-collapse">
              <thead>
                <tr className="border-b border-border-color bg-sidebar-item-hover">
                  <th className="text-text-muted text-[11px] font-bold uppercase tracking-wider text-left p-3.5 w-[90px]">ID</th>
                  <th className="text-text-muted text-[11px] font-bold uppercase tracking-wider text-left p-3.5">Original Drawing</th>
                  <th className="text-text-muted text-[11px] font-bold uppercase tracking-wider text-left p-3.5">KMTI Drawing</th>
                  <th className="text-text-muted text-[11px] font-bold uppercase tracking-wider text-left p-3.5">Client</th>
                  <th className="text-text-muted text-[11px] font-bold uppercase tracking-wider text-left p-3.5">Compliance Score</th>
                  <th className="text-text-muted text-[11px] font-bold uppercase tracking-wider text-left p-3.5">Session Date</th>
                  <th className="text-text-muted text-[11px] font-bold uppercase tracking-wider text-left p-3.5">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredSessions.map((session) => {
                  const isCompleted = session.status === "completed";
                  const isFailed = session.status === "failed";
                  const score = session.compliance_score;
                  // Maps 1:1 onto Badge's semantic variants instead of hand-computing
                  // bg/border/text triplets per threshold.
                  let scoreVariant: "success" | "warning" | "destructive" | "secondary" = "secondary";
                  if (isCompleted && score !== null) {
                    if (score >= 85) scoreVariant = "success";
                    else if (score >= 70) scoreVariant = "warning";
                    else scoreVariant = "destructive";
                  }

                  return (
                    <tr
                      key={session.id}
                      className="border-b border-border-color hover:bg-sidebar-item-hover transition-colors duration-200"
                    >
                      {/* ID Column */}
                      <td className="p-3.5 text-xs text-text-primary align-middle">
                        <span className="text-[11px] font-bold text-accent-cyan bg-accent-cyan/5 py-1 px-1.5 rounded border border-accent-cyan/15 tracking-wider font-mono">
                          {(() => {
                            const prefix = "SYS";
                            const absoluteIndex = sessions!.findIndex(s => s.id === session.id);
                            const numStr = String(sessions!.length - absoluteIndex).padStart(2, "0");
                            return `${prefix}${numStr}`;
                          })()}
                        </span>
                      </td>

                      {/* Reference File */}
                      <td className="p-3.5 text-xs text-text-primary align-middle">
                        <div className="flex items-center gap-2">
                          <FileText size={14} className={session.reference_drawing_id ? "text-text-muted" : "opacity-15"} />
                          <span className={session.reference_drawing_id ? "text-text-primary" : "text-text-muted"}>
                            {session.reference_drawing_id ? getDrawingName(session.reference_drawing_id) : "—"}
                          </span>
                        </div>
                      </td>

                      {/* New File */}
                      <td className="p-3.5 text-xs text-text-primary align-middle font-semibold">
                        <div className="flex flex-col gap-1.5">
                          <div className="flex items-center gap-2">
                            <FileText size={14} className="text-accent-cyan" />
                            <span>{getDrawingName(session.drawing_id)}</span>
                          </div>
                          {session.remarks && (
                            <span className="text-[10px] text-accent-cyan inline-flex items-center gap-1.5 bg-accent-cyan/5 border border-accent-cyan/10 py-0.5 px-2 rounded w-fit font-normal">
                              <span className="w-1 h-1 rounded-full bg-accent-cyan inline-block"></span>
                              {session.remarks}
                            </span>
                          )}
                        </div>
                      </td>

                      {/* Client Context */}
                      <td className="p-3.5 text-xs text-text-primary align-middle">
                        <div className="flex items-center gap-2">
                          <Briefcase size={14} className="text-text-muted opacity-60" />
                          <span className={session.client_name ? "text-text-primary" : "text-text-muted"}>
                            {session.client_name || "Universal Standard"}
                          </span>
                        </div>
                      </td>

                      {/* Compliance Score */}
                      <td className="p-3.5 text-xs text-text-primary align-middle">
                        {isCompleted ? (
                          <Badge variant={scoreVariant} className="font-extrabold">
                            {score !== null ? `${score.toFixed(1)}%` : "N/A"}
                          </Badge>
                        ) : isFailed ? (
                          <Badge variant="destructive" className="text-[10px] gap-1" title={session.error_message || "Audit pipeline failed"}>
                            <AlertTriangle size={12} /> Failed
                          </Badge>
                        ) : (
                          <span className="bg-accent-cyan/5 border border-accent-cyan/12 text-accent-cyan text-[10px] inline-flex items-center gap-1 py-0.5 px-2 rounded">
                            <Loader size={12} className="spin-animation" /> Auditing...
                          </span>
                        )}
                      </td>

                      {/* Session Date */}
                      <td className="p-3.5 text-xs text-text-muted align-middle font-mono">
                        <div className="flex items-center gap-1.5">
                          <Clock size={12} className="opacity-60" />
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
                      <td className="p-3.5 text-xs text-text-primary align-middle">
                        <div className="flex justify-start gap-2">
                          <button
                            onClick={() => handleOpenSession(session)}
                            disabled={session.status !== "completed"}
                            title="Open visual canvas review"
                            className="bg-transparent border border-border-color text-text-muted p-1.5 rounded-md cursor-pointer flex items-center justify-center hover:text-accent-cyan hover:border-accent-cyan hover:bg-accent-cyan/15 transition-colors disabled:opacity-50 disabled:pointer-events-none"
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
                            className="bg-transparent border border-border-color text-text-muted p-1.5 rounded-md cursor-pointer flex items-center justify-center hover:text-warning hover:border-warning hover:bg-warning/15 transition-colors"
                          >
                            <Edit size={14} />
                          </button>
                          <button
                            onClick={() => {
                              setSelectedSessionForDelete(session);
                              setIsDeleteModalOpen(true);
                            }}
                            title="Purge session record"
                            className="bg-transparent border border-danger/30 text-danger p-1.5 rounded-md cursor-pointer flex items-center justify-center hover:bg-danger/20 hover:border-danger transition-colors"
                          >
                            <Trash2 size={14} />
                          </button>
                          {session.is_restored && (
                            <Badge variant="success" className="text-[9px] uppercase tracking-wide ml-1">
                              Restored
                            </Badge>
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
          <div className="flex flex-col items-center justify-center p-12 text-center bg-sidebar-item-hover border border-dashed border-border-color rounded-xl mt-3 shadow-xs">
            <div className="w-12 h-12 rounded-full bg-sidebar-item-hover border border-border-color flex items-center justify-center text-text-muted mb-4.5">
              <Database size={24} />
            </div>
            <h4 className="font-bold text-text-primary text-base mb-2">No matching archives found</h4>
            <p className="text-text-muted text-xs max-w-[420px] mb-5.5 leading-relaxed">
              {sessions && sessions.length > 0
                ? "No historical runs match your current query or filter selectors. Reset filters to view all sessions."
                : "No CAD compliance runs have been archived yet. Go to the review workspace to launch your first compliance check!"}
            </p>
            {sessions && sessions.length > 0 ? (
              <Button
                variant="outline"
                onClick={() => {
                  setHistorySearchQuery("");
                  setHistoryStatusFilter("all");
                  setHistoryScoreFilter("all");
                }}
              >
                Clear all filters
              </Button>
            ) : (
              <Button variant="primary" onClick={() => setCurrentNav("workspace")}>
                <Play size={12} className="mr-2" /> Launch Compliance Check
              </Button>
            )}
          </div>
        )}
      </main>

      {/* Edit Remarks Modal */}
      <Modal
        isOpen={isEditModalOpen && !!selectedSessionForEdit}
        onClose={() => {
          setIsEditModalOpen(false);
          setSelectedSessionForEdit(null);
          setRemarksText("");
        }}
        title="Edit Session Remarks"
        description="Add custom notes or checker logs for this revision audit."
        maxWidthClassName="max-w-[480px]"
        footer={
          <div className="flex justify-end gap-3">
            <Button
              variant="outline"
              onClick={() => {
                setIsEditModalOpen(false);
                setSelectedSessionForEdit(null);
                setRemarksText("");
              }}
            >
              Cancel
            </Button>
            <Button variant="primary" onClick={handleSaveRemarks}>
              Save Remarks
            </Button>
          </div>
        }
      >
        <div className="flex flex-col gap-2">
          <label className="text-[10px] font-semibold uppercase tracking-wider text-text-muted">Remarks / Notes</label>
          <textarea
            className="w-full bg-transparent border border-border-color rounded-lg py-2.5 px-3.5 text-xs text-text-primary font-mono focus:outline-none focus:border-accent-cyan transition-colors h-[120px] resize-none"
            value={remarksText}
            onChange={(e) => setRemarksText(e.target.value)}
            placeholder="Enter custom remarks for this session..."
          />
        </div>
      </Modal>

      {/* Delete Confirmation Modal */}
      <Modal
        isOpen={isDeleteModalOpen && !!selectedSessionForDelete}
        onClose={() => {
          setIsDeleteModalOpen(false);
          setSelectedSessionForDelete(null);
        }}
        title="Purge Session Record?"
        icon={<AlertTriangle size={18} className="text-danger" />}
        description="You are about to permanently delete this audit session log and all associated violations from MongoDB. This action is irreversible."
        maxWidthClassName="max-w-[480px]"
        footer={
          <div className="flex justify-end gap-3">
            <Button
              variant="outline"
              onClick={() => {
                setIsDeleteModalOpen(false);
                setSelectedSessionForDelete(null);
              }}
            >
              Keep Record
            </Button>
            <Button variant="destructive" onClick={handleDeleteConfirm}>
              Purge Record
            </Button>
          </div>
        }
      >
        {selectedSessionForDelete && (
          <div className="p-3 bg-danger/5 border border-danger/15 rounded-lg">
            <div className="text-xs flex flex-col gap-1.5 font-mono">
              <span className="text-text-muted">Target: <strong className="text-text-primary">{getDrawingName(selectedSessionForDelete.drawing_id)}</strong></span>
              {selectedSessionForDelete.reference_drawing_id && (
                <span className="text-text-muted">Reference: <strong className="text-text-primary">{getDrawingName(selectedSessionForDelete.reference_drawing_id)}</strong></span>
              )}
              <span className="text-text-muted">Date: <strong className="text-text-primary">{parseUtcDate(selectedSessionForDelete.created_at).toLocaleString()}</strong></span>
            </div>
          </div>
        )}
      </Modal>
    </>
  );
};
