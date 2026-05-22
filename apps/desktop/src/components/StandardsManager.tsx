import React, { useState, useEffect, useRef } from "react";
import { useAuditStore } from "../stores/auditStore";
import { useWorkspaceStore } from "../stores/workspaceStore";
import {
  FileText, UploadCloud, Plus, Loader2, AlertCircle,
  Tag, Layers, Calendar, HardDrive, FolderOpen, Trash2,
  Pencil, Save, X, AlertTriangle, CheckCircle2
} from "lucide-react";

export const StandardsManager: React.FC = () => {
  const {
    standards,
    fetchStandards,
    uploadStandard,
    deleteStandard,
    updateStandard,
    uploadStatus,
    uploadProgress,
    errorMessage,
    resetStore
  } = useAuditStore();

  const {
    clients,
    fetchClients,
    createClient,
    deleteClient
  } = useWorkspaceStore();

  const [name, setName] = useState("");
  const [category, setCategory] = useState("");
  const [description, setDescription] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const [showUploadModal, setShowUploadModal] = useState(false);

  // Scoping context for the upload modal
  const [uploadScope, setUploadScope] = useState<"universal" | "client_specific">("universal");
  const [uploadClient, setUploadClient] = useState<string>("");

  // Directory explorer state
  const [activeClientTab, setActiveClientTab] = useState<string | null>(null);
  const [newClientName, setNewClientName] = useState("");
  const [isAddingClient, setIsAddingClient] = useState(false);

  // Edit modal state
  const [editingStd, setEditingStd] = useState<any | null>(null);
  const [editName, setEditName] = useState("");
  const [editCategory, setEditCategory] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editSaving, setEditSaving] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);

  // Delete confirmation state
  const [deletingStd, setDeletingStd] = useState<any | null>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);

  // Toast notification
  const [toast, setToast] = useState<{ type: "success" | "error"; message: string } | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    fetchStandards();
    fetchClients();
  }, [fetchStandards, fetchClients]);

  const showToast = (type: "success" | "error", message: string) => {
    setToast({ type, message });
    setTimeout(() => setToast(null), 3500);
  };

  const universalStandards = standards.filter(s => s.scope === "universal" || !s.scope);

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(true);
  };

  const handleDragLeave = () => setIsDragOver(false);

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    const files = e.dataTransfer.files;
    if (files && files.length > 0) {
      const file = files[0];
      const ext = file.name.split(".").pop()?.toLowerCase();
      if (ext && ["pdf", "txt", "md", "xlsx", "xls"].includes(ext)) {
        setSelectedFile(file);
        if (!name) setName(file.name.replace(/\.[^/.]+$/, "").replace(/[_\-]/g, " ").toUpperCase());
      } else {
        alert("Unsupported file format! Please upload PDF, TXT, Excel or Markdown.");
      }
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      const file = files[0];
      setSelectedFile(file);
      if (!name) setName(file.name.replace(/\.[^/.]+$/, "").replace(/[_\-]/g, " ").toUpperCase());
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile || !name.trim()) return;
    const success = await uploadStandard(
      selectedFile, name,
      category || "General Compliance",
      description || "Engineering drafting compliance parameters.",
      uploadScope, uploadClient
    );
    if (success) {
      setName(""); setCategory(""); setDescription(""); setSelectedFile(null);
      setShowUploadModal(false);
      showToast("success", "Standard ingested successfully.");
    }
  };

  const formatBytes = (bytes: number) => {
    if (bytes === 0) return "0 Bytes";
    const k = 1024;
    const sizes = ["Bytes", "KB", "MB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
  };

  const triggerUploadModal = (scope: "universal" | "client_specific", clientName = "") => {
    resetStore();
    setUploadScope(scope);
    setUploadClient(clientName);
    setShowUploadModal(true);
  };

  const handleCreateClient = async () => {
    if (newClientName.trim()) {
      await createClient(newClientName.trim());
      setNewClientName("");
      setIsAddingClient(false);
    }
  };

  // ─── Edit handlers ─────────────────────────────────────────────
  const openEdit = (std: any) => {
    setEditingStd(std);
    setEditName(std.name);
    setEditCategory(std.category || "");
    setEditDescription(std.description || "");
    setEditError(null);
  };

  const handleEditSave = async () => {
    if (!editingStd || !editName.trim()) return;
    setEditSaving(true);
    setEditError(null);
    const ok = await updateStandard(editingStd.id, editName.trim(), editCategory.trim(), editDescription.trim());
    setEditSaving(false);
    if (ok) {
      setEditingStd(null);
      showToast("success", "Standard updated successfully.");
    } else {
      setEditError("Failed to update. Please try again.");
    }
  };

  // ─── Delete handlers ────────────────────────────────────────────
  const handleDeleteConfirm = async () => {
    if (!deletingStd) return;
    setDeleteLoading(true);
    const ok = await deleteStandard(deletingStd.id);
    setDeleteLoading(false);
    setDeletingStd(null);
    if (ok) showToast("success", `"${deletingStd.name}" has been deleted.`);
    else showToast("error", "Failed to delete. Please try again.");
  };

  // ─── Standard Card component ────────────────────────────────────
  const StandardCard = ({ std }: { std: any }) => (
    <div className="card standard-card" key={std.id}>
      <div className="std-card-top">
        <div className="std-icon-box"><FileText size={20} /></div>
        <div className="std-badge">{std.format.toUpperCase()}</div>
      </div>
      <h4 className="std-title" title={std.name}>{std.name}</h4>
      <p className="std-desc">{std.description || "No description provided."}</p>
      <div className="std-meta-grid">
        <div className="std-meta-item"><Tag size={12} /><span>{std.category || "General"}</span></div>
        <div className="std-meta-item"><HardDrive size={12} /><span>{formatBytes(std.file_size_bytes)}</span></div>
        <div className="std-meta-item"><Layers size={12} /><span>{std.metadata.page_count || 1} sections</span></div>
        <div className="std-meta-item"><Calendar size={12} /><span>{new Date(std.created_at).toLocaleDateString()}</span></div>
      </div>
      {/* Admin action bar */}
      <div className="std-actions-bar">
        <button
          className="std-action-btn edit"
          onClick={() => openEdit(std)}
          title="Edit metadata"
        >
          <Pencil size={13} /> Edit
        </button>
        <button
          className="std-action-btn delete"
          onClick={() => setDeletingStd(std)}
          title="Delete standard"
        >
          <Trash2 size={13} /> Delete
        </button>
      </div>
    </div>
  );

  return (
    <div className="standards-layout">

      {/* TOAST NOTIFICATION */}
      {toast && (
        <div className={`std-toast ${toast.type}`}>
          {toast.type === "success" ? <CheckCircle2 size={14} /> : <AlertTriangle size={14} />}
          {toast.message}
        </div>
      )}

      {/* 1. UNIVERSAL STANDARDS SECTION */}
      <div className="standards-header">
        <div>
          <h3 className="section-title">KMTI Checking Manuals (Universal)</h3>
          <p className="section-desc">Global internal standards and checksheets applied universally across all drawing audits.</p>
        </div>
        <button className="btn btn-primary" onClick={() => triggerUploadModal("universal")} style={{ display: "inline-flex", alignItems: "center", gap: "8px" }}>
          <Plus size={16} /> Add Universal Manual
        </button>
      </div>

      {universalStandards.length === 0 ? (
        <div className="empty-standards-card" style={{ padding: "40px 20px" }}>
          <FileText size={36} style={{ opacity: 0.3, marginBottom: "16px" }} />
          <h4>No Universal Manuals</h4>
          <p>Ingest the baseline KMTI Checking Manual or Checksheet Excel files here.</p>
        </div>
      ) : (
        <div className="standards-grid" style={{ marginBottom: "40px" }}>
          {universalStandards.map(std => <StandardCard key={std.id} std={std} />)}
        </div>
      )}

      {/* 2. CLIENT SPECIFIC DIRECTORIES */}
      <div className="standards-header" style={{ marginTop: "50px", borderTop: "1px solid var(--border-color)", paddingTop: "30px" }}>
        <div>
          <h3 className="section-title">Client Target Directories</h3>
          <p className="section-desc">Manage specific checking guidelines aligned to independent clients.</p>
        </div>
      </div>

      <div className="clients-explorer-container" style={{ display: "flex", gap: "24px", minHeight: "400px" }}>

        {/* Left Sidebar: Clients Roster */}
        <div className="card clients-sidebar" style={{ width: "260px", flexShrink: 0, padding: "16px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
            <h4 style={{ margin: 0, fontSize: "0.95rem" }}>Clients</h4>
            <button className="btn-icon" onClick={() => setIsAddingClient(!isAddingClient)} title="New Client">
              <Plus size={16} />
            </button>
          </div>

          {isAddingClient && (
            <div style={{ display: "flex", gap: "8px", marginBottom: "16px" }}>
              <input type="text" className="form-input" style={{ padding: "6px" }} placeholder="Client Code..." value={newClientName} onChange={(e) => setNewClientName(e.target.value)} autoFocus />
              <button className="btn btn-primary" style={{ padding: "6px 12px" }} onClick={handleCreateClient}>Add</button>
            </div>
          )}

          <div className="clients-list" style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
            {clients.map(c => (
              <div
                key={c.id}
                className={`client-nav-item ${activeClientTab === c.name ? "active" : ""}`}
                onClick={() => setActiveClientTab(c.name)}
                style={{
                  display: "flex", justifyContent: "space-between", alignItems: "center",
                  padding: "10px 12px", borderRadius: "8px", cursor: "pointer",
                  background: activeClientTab === c.name ? "var(--sidebar-item-hover)" : "transparent",
                  border: activeClientTab === c.name ? "1px solid var(--accent-cyan)" : "1px solid transparent"
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                  <FolderOpen size={16} style={{ color: activeClientTab === c.name ? "var(--accent-cyan)" : "var(--text-muted)" }} />
                  <span style={{ fontWeight: 500, color: activeClientTab === c.name ? "var(--text-primary)" : "var(--text-muted)" }}>{c.name}</span>
                </div>
                {activeClientTab === c.name && (
                  <Trash2
                    size={14} className="text-danger"
                    style={{ cursor: "pointer", opacity: 0.7 }}
                    onClick={(e) => { e.stopPropagation(); if (confirm(`Delete ${c.name} and all its standards?`)) deleteClient(c.name); }}
                  />
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Right Content: Selected Client Standards */}
        <div className="client-content-area" style={{ flexGrow: 1 }}>
          {!activeClientTab ? (
            <div className="empty-standards-card" style={{ height: "100%", display: "flex", flexDirection: "column", justifyContent: "center" }}>
              <FolderOpen size={48} style={{ opacity: 0.2, margin: "0 auto 16px" }} />
              <h4>Select a Client Directory</h4>
              <p>Choose a client from the sidebar to view or inject their specific drafting standards.</p>
            </div>
          ) : (
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "20px" }}>
                <h4 style={{ margin: 0, fontSize: "1.1rem", display: "flex", alignItems: "center", gap: "10px" }}>
                  <FolderOpen size={20} className="text-purple" /> {activeClientTab} Standards
                </h4>
                <button className="btn btn-secondary" onClick={() => triggerUploadModal("client_specific", activeClientTab)} style={{ display: "inline-flex", alignItems: "center", gap: "8px" }}>
                  <UploadCloud size={16} /> Ingest {activeClientTab} Standard
                </button>
              </div>

              {standards.filter(s => s.scope === "client_specific" && s.client_name === activeClientTab).length === 0 ? (
                <div className="empty-standards-card" style={{ padding: "40px 20px" }}>
                  <p>No specific standards ingested for {activeClientTab} yet.</p>
                </div>
              ) : (
                <div className="standards-grid">
                  {standards.filter(s => s.scope === "client_specific" && s.client_name === activeClientTab).map(std => <StandardCard key={std.id} std={std} />)}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* UPLOAD MODAL DIALOG */}
      {showUploadModal && (
        <div className="modal-overlay">
          <div className="modal-content card" style={{ maxWidth: "550px" }}>
            <div className="modal-header">
              <h3 className="card-title">
                <UploadCloud size={18} className="text-purple" />
                Ingest {uploadScope === "universal" ? "Universal Manual" : `${uploadClient} Standard`}
              </h3>
              <button className="close-button" onClick={() => setShowUploadModal(false)} disabled={uploadStatus === "uploading"}>&times;</button>
            </div>

            <form onSubmit={handleSubmit} className="modal-body">
              <div
                className={`drag-drop-zone ${isDragOver ? "dragging" : ""} ${uploadStatus === "uploading" ? "disabled" : ""}`}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
                onClick={() => uploadStatus !== "uploading" && fileInputRef.current?.click()}
                style={{ height: "140px", marginBottom: "20px" }}
              >
                <input type="file" ref={fileInputRef} onChange={handleFileChange} style={{ display: "none" }} accept=".pdf,.txt,.md,.xlsx,.xls" />
                <div className="upload-icon-container">
                  {uploadStatus === "uploading" ? <Loader2 size={24} className="spin-animation text-purple" /> : <UploadCloud size={24} className="text-purple" />}
                </div>
                <span className="upload-prompt" style={{ fontSize: "0.85rem" }}>
                  {selectedFile ? `Selected: ${selectedFile.name} (${formatBytes(selectedFile.size)})` : "Drag & Drop standard reference, or browse"}
                </span>
                <span className="upload-specs" style={{ fontSize: "0.7rem" }}>PDF, TXT, Excel or Markdown (Max 50MB)</span>
              </div>

              <div className="form-group">
                <label className="form-label">Standard Title Identifier</label>
                <input type="text" className="form-input" placeholder="e.g. ISO 128 TECHNICAL DRAWING PRINCIPLES" value={name} onChange={(e) => setName(e.target.value)} required disabled={uploadStatus === "uploading"} />
              </div>

              <div className="form-group">
                <label className="form-label">Category Group</label>
                <input type="text" className="form-input" placeholder="e.g. Dimensioning, Tolerancing, Layering" value={category} onChange={(e) => setCategory(e.target.value)} disabled={uploadStatus === "uploading"} />
              </div>

              <div className="form-group">
                <label className="form-label">Context Description</label>
                <textarea className="form-input" style={{ height: "60px", resize: "none" }} placeholder="Summarize compliance parameters inside reference standard..." value={description} onChange={(e) => setDescription(e.target.value)} disabled={uploadStatus === "uploading"} />
              </div>

              {uploadStatus === "uploading" && (
                <div className="progress-container" style={{ margin: "16px 0 8px 0" }}>
                  <div className="progress-bar-bg" style={{ height: "4px" }}>
                    <div className="progress-bar-fill" style={{ width: `${uploadProgress}%` }}></div>
                  </div>
                  <div className="progress-labels">
                    <span>Processing & chunking knowledge blocks...</span>
                    <span>{uploadProgress}%</span>
                  </div>
                </div>
              )}

              {errorMessage && (
                <div className="error-alert" style={{ marginTop: "12px", padding: "12px" }}>
                  <AlertCircle size={16} />
                  <div style={{ marginLeft: "8px", fontSize: "0.8rem" }}>
                    <strong>Ingestion Fault:</strong> {errorMessage}
                  </div>
                </div>
              )}

              <div className="modal-actions" style={{ marginTop: "24px", display: "flex", gap: "12px", justifyContent: "flex-end" }}>
                <button type="button" className="btn btn-secondary" onClick={() => setShowUploadModal(false)} disabled={uploadStatus === "uploading"}>Cancel</button>
                <button type="submit" className="btn btn-primary" disabled={uploadStatus === "uploading" || !selectedFile || !name.trim()}>Confirm Ingestion</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* EDIT MODAL */}
      {editingStd && (
        <div className="modal-overlay">
          <div className="modal-content card" style={{ maxWidth: "480px" }}>
            <div className="modal-header">
              <h3 className="card-title" style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                <Pencil size={16} style={{ color: "var(--accent-cyan)" }} /> Edit Standard
              </h3>
              <button className="close-button" onClick={() => setEditingStd(null)} disabled={editSaving}>&times;</button>
            </div>
            <div className="modal-body">
              {/* Format + file info */}
              <div style={{ display: "flex", gap: "10px", alignItems: "center", padding: "10px 12px", background: "var(--bg-dark)", borderRadius: "8px", marginBottom: "20px", border: "1px solid var(--border-color)" }}>
                <FileText size={16} style={{ color: "var(--accent-cyan)" }} />
                <div>
                  <div style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Source file · {editingStd.format.toUpperCase()} · {formatBytes(editingStd.file_size_bytes)}</div>
                  <div style={{ fontSize: "0.75rem", color: "var(--text-primary)", fontFamily: "monospace" }}>{editingStd.file_path.split(/[/\\]/).pop()}</div>
                </div>
              </div>

              <div className="form-group">
                <label className="form-label">Standard Title</label>
                <input type="text" className="form-input" value={editName} onChange={(e) => setEditName(e.target.value)} disabled={editSaving} autoFocus />
              </div>
              <div className="form-group">
                <label className="form-label">Category Group</label>
                <input type="text" className="form-input" placeholder="e.g. Dimensioning, Tolerancing" value={editCategory} onChange={(e) => setEditCategory(e.target.value)} disabled={editSaving} />
              </div>
              <div className="form-group">
                <label className="form-label">Context Description</label>
                <textarea className="form-input" style={{ height: "80px", resize: "none" }} value={editDescription} onChange={(e) => setEditDescription(e.target.value)} disabled={editSaving} />
              </div>

              {editError && (
                <div className="error-alert" style={{ marginTop: "8px", padding: "10px" }}>
                  <AlertCircle size={14} />
                  <span style={{ marginLeft: "8px", fontSize: "0.78rem" }}>{editError}</span>
                </div>
              )}

              <div className="modal-actions" style={{ marginTop: "24px", display: "flex", gap: "12px", justifyContent: "flex-end" }}>
                <button className="btn btn-secondary" onClick={() => setEditingStd(null)} disabled={editSaving}>
                  <X size={14} style={{ marginRight: "4px" }} /> Cancel
                </button>
                <button className="btn btn-primary" onClick={handleEditSave} disabled={editSaving || !editName.trim()} style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                  {editSaving ? <Loader2 size={14} className="spin-animation" /> : <Save size={14} />}
                  {editSaving ? "Saving..." : "Save Changes"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* DELETE CONFIRMATION MODAL */}
      {deletingStd && (
        <div className="modal-overlay">
          <div className="modal-content card" style={{ maxWidth: "420px" }}>
            <div className="modal-header">
              <h3 className="card-title" style={{ display: "flex", alignItems: "center", gap: "10px", color: "#ef4444", borderLeftColor: "#ef4444" }}>
                <AlertTriangle size={16} /> Confirm Deletion
              </h3>
              <button className="close-button" onClick={() => setDeletingStd(null)} disabled={deleteLoading}>&times;</button>
            </div>
            <div className="modal-body">
              <p style={{ fontSize: "0.88rem", color: "var(--text-primary)", marginBottom: "12px" }}>
                You are about to permanently delete:
              </p>
              <div style={{
                display: "flex",
                alignItems: "center",
                gap: "16px",
                background: "linear-gradient(135deg, rgba(239, 68, 68, 0.1) 0%, rgba(239, 68, 68, 0.02) 100%)",
                border: "1px solid rgba(239, 68, 68, 0.25)",
                borderRadius: "12px",
                padding: "16px",
                marginBottom: "20px",
                boxShadow: "inset 0 0 12px rgba(239, 68, 68, 0.05)"
              }}>
                <div style={{
                  width: "44px",
                  height: "44px",
                  borderRadius: "10px",
                  background: "rgba(239, 68, 68, 0.15)",
                  border: "1px solid rgba(239, 68, 68, 0.3)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  color: "#ef4444",
                  flexShrink: 0
                }}>
                  <FileText size={22} />
                </div>
                <div style={{ flexGrow: 1, minWidth: 0 }}>
                  <div style={{
                    fontWeight: 700,
                    fontSize: "0.95rem",
                    color: "var(--text-primary)",
                    whiteSpace: "nowrap",
                    overflow: "hidden",
                    textOverflow: "ellipsis"
                  }} title={deletingStd.name}>
                    {deletingStd.name}
                  </div>
                  <div style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "8px",
                    marginTop: "6px"
                  }}>
                    <span style={{
                      fontSize: "0.68rem",
                      fontWeight: 700,
                      background: "rgba(239, 68, 68, 0.2)",
                      border: "1px solid rgba(239, 68, 68, 0.35)",
                      color: "#ef4444",
                      padding: "2px 8px",
                      borderRadius: "12px",
                      textTransform: "uppercase",
                      letterSpacing: "0.5px"
                    }}>
                      {deletingStd.format}
                    </span>
                    <span style={{ color: "var(--text-muted)", fontSize: "0.72rem" }}>•</span>
                    <span style={{
                      fontSize: "0.72rem",
                      color: "var(--text-muted)",
                      fontWeight: 500
                    }}>
                      {formatBytes(deletingStd.file_size_bytes)}
                    </span>
                  </div>
                  <div style={{
                    fontSize: "0.75rem",
                    color: "rgba(239, 68, 68, 0.85)",
                    marginTop: "8px",
                    display: "flex",
                    alignItems: "center",
                    gap: "6px",
                    fontWeight: 500
                  }}>
                    <span style={{ display: "inline-block", width: "4px", height: "4px", borderRadius: "50%", background: "#ef4444" }}></span>
                    All associated knowledge chunks will be removed.
                  </div>
                </div>
              </div>
              <p style={{ fontSize: "0.8rem", color: "#ef4444", marginBottom: "24px" }}>
                ⚠ This action is irreversible. The standard and all its AI knowledge chunks will be deleted from the database.
              </p>
              <div style={{ display: "flex", gap: "12px", justifyContent: "flex-end" }}>
                <button
                  className="btn btn-secondary"
                  style={{ padding: "10px 24px" }}
                  onClick={() => setDeletingStd(null)}
                  disabled={deleteLoading}
                >
                  Cancel
                </button>
                <button
                  className="btn btn-danger-confirm"
                  onClick={handleDeleteConfirm}
                  disabled={deleteLoading}
                >
                  {deleteLoading ? <Loader2 size={14} className="spin-animation" /> : <Trash2 size={14} />}
                  {deleteLoading ? "Deleting..." : "Delete Permanently"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* COMPONENT SCOPED CSS STYLES */}
      <style>{`
        .standards-layout {
          animation: fadeIn 0.4s ease-out;
          padding: 0 32px;
        }
        .standards-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-top: 30px;
          margin-bottom: 30px;
        }
        .section-title {
          font-size: 1.25rem;
          font-weight: 600;
          color: var(--text-primary);
          margin-bottom: 4px;
        }
        .section-desc {
          font-size: 0.85rem;
          color: var(--text-muted);
        }
        .empty-standards-card {
          background: var(--bg-card);
          border: 2px dashed var(--border-color);
          border-radius: 12px;
          padding: 60px 20px;
          text-align: center;
          color: var(--text-primary);
        }
        .empty-standards-card h4 { font-weight: 500; margin-bottom: 8px; }
        .empty-standards-card p { font-size: 0.85rem; color: var(--text-muted); max-width: 400px; margin: 0 auto; }
        .standards-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
          gap: 20px;
        }
        .standard-card {
          display: flex;
          flex-direction: column;
          padding: 20px;
          transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
          background: var(--bg-card);
          border: 1px solid var(--border-color);
          border-radius: 12px;
          position: relative;
          overflow: hidden;
        }
        .standard-card:hover {
          transform: translateY(-4px);
          border-color: var(--accent-cyan);
          box-shadow: 0 10px 25px -5px rgba(0, 229, 255, 0.1);
        }
        .standard-card:hover .std-actions-bar {
          opacity: 1;
          transform: translateY(0);
        }
        .std-card-top {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 16px;
        }
        .std-icon-box {
          width: 36px;
          height: 36px;
          border-radius: 8px;
          background: rgba(37, 99, 235, 0.1);
          border: 1px solid var(--border-color);
          display: flex;
          align-items: center;
          justify-content: center;
          color: var(--accent-cyan);
        }
        .std-badge {
          font-size: 0.7rem;
          font-weight: 600;
          padding: 2px 8px;
          background: var(--sidebar-item-hover);
          border: 1px solid var(--border-color);
          border-radius: 20px;
          color: var(--text-primary);
        }
        .std-title {
          font-size: 0.95rem;
          font-weight: 600;
          color: var(--text-primary);
          margin-bottom: 6px;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .std-desc {
          font-size: 0.8rem;
          color: var(--text-muted);
          line-height: 1.4;
          height: 3.2em;
          overflow: hidden;
          display: -webkit-box;
          -webkit-line-clamp: 2;
          -webkit-box-orient: vertical;
          margin-bottom: 16px;
        }
        .std-meta-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 10px;
          border-top: 1px solid var(--border-color);
          padding-top: 12px;
          margin-top: auto;
        }
        .std-meta-item {
          display: flex;
          align-items: center;
          gap: 6px;
          color: var(--text-muted);
          font-size: 0.72rem;
        }
        .std-meta-item span { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

        /* ── Admin action bar (hover-reveal) ── */
        .std-actions-bar {
          display: flex;
          gap: 8px;
          margin-top: 14px;
          padding-top: 12px;
          border-top: 1px solid var(--border-color);
          opacity: 0;
          transform: translateY(4px);
          transition: opacity 0.2s ease, transform 0.2s ease;
        }
        .std-action-btn {
          flex: 1;
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 5px;
          padding: 6px 10px;
          border-radius: 6px;
          font-size: 0.72rem;
          font-weight: 600;
          cursor: pointer;
          border: 1px solid transparent;
          transition: all 0.15s ease;
        }
        .std-action-btn.edit {
          background: rgba(0, 229, 255, 0.06);
          border-color: rgba(0, 229, 255, 0.2);
          color: var(--accent-cyan);
        }
        .std-action-btn.edit:hover {
          background: var(--accent-cyan);
          border-color: var(--accent-cyan);
          color: var(--bg-dark);
          box-shadow: 0 4px 12px rgba(0, 229, 255, 0.25);
          transform: translateY(-1px);
        }
        .std-action-btn.delete {
          background: rgba(239, 68, 68, 0.06);
          border-color: rgba(239, 68, 68, 0.2);
          color: #ef4444;
        }
        .std-action-btn.delete:hover {
          background: #ef4444;
          border-color: #ef4444;
          color: #ffffff;
          box-shadow: 0 4px 12px rgba(239, 68, 68, 0.25);
          transform: translateY(-1px);
        }

        /* ── Danger Confirm button inside deletion modal ── */
        .btn.btn-danger-confirm {
          background: #ef4444;
          color: #ffffff;
          border: 1px solid transparent;
          box-shadow: 0 4px 14px rgba(239, 68, 68, 0.25);
          transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
          display: flex;
          align-items: center;
          gap: 6px;
          padding: 10px 24px;
          border-radius: 8px;
          font-weight: 600;
          font-size: 0.88rem;
          cursor: pointer;
        }
        .btn.btn-danger-confirm:hover:not(:disabled) {
          transform: translateY(-2px);
          background: #dc2626;
          box-shadow: 0 6px 20px rgba(239, 68, 68, 0.45);
          border-color: rgba(239, 68, 68, 0.4);
        }
        .btn.btn-danger-confirm:active:not(:disabled) {
          transform: translateY(0);
          box-shadow: 0 4px 10px rgba(239, 68, 68, 0.2);
        }
        .btn.btn-danger-confirm:disabled {
          opacity: 0.6;
          cursor: not-allowed;
          transform: none;
          box-shadow: none;
        }

        /* ── Toast ── */
        .std-toast {
          position: fixed;
          bottom: 24px;
          right: 24px;
          display: flex;
          align-items: center;
          gap: 10px;
          padding: 12px 20px;
          border-radius: 10px;
          font-size: 0.82rem;
          font-weight: 500;
          z-index: 9999;
          box-shadow: 0 8px 24px rgba(0,0,0,0.35);
          animation: toastSlideIn 0.3s cubic-bezier(0.34,1.56,0.64,1);
        }
        .std-toast.success { background: rgba(16,185,129,0.12); border: 1px solid rgba(16,185,129,0.35); color: #10b981; }
        .std-toast.error { background: rgba(239,68,68,0.12); border: 1px solid rgba(239,68,68,0.35); color: #ef4444; }
        @keyframes toastSlideIn {
          from { opacity: 0; transform: translateY(16px) scale(0.95); }
          to { opacity: 1; transform: translateY(0) scale(1); }
        }

        /* MODAL OVERLAY */
        .modal-overlay {
          position: fixed;
          top: 0; left: 0; right: 0; bottom: 0;
          background: rgba(0, 0, 0, 0.75);
          backdrop-filter: blur(8px);
          display: flex;
          align-items: center;
          justify-content: center;
          z-index: 1000;
          animation: modalFadeIn 0.25s ease-out;
        }
        .modal-content {
          width: 90%;
          border: 1px solid var(--border-color);
          box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
          animation: modalSlideIn 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
        }
        @keyframes modalFadeIn { from { opacity: 0; } to { opacity: 1; } }
        @keyframes modalSlideIn {
          from { transform: translateY(20px) scale(0.95); opacity: 0; }
          to { transform: translateY(0) scale(1); opacity: 1; }
        }
        .modal-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          border-bottom: 1px solid var(--border-color);
          padding-bottom: 16px;
          margin-bottom: 16px;
        }
        .close-button {
          background: none; border: none; color: var(--text-muted);
          font-size: 1.5rem; cursor: pointer; line-height: 1;
        }
        .close-button:hover { color: var(--text-primary); }
        .close-button:disabled { opacity: 0.3; cursor: not-allowed; }
        .mt-3 { margin-top: 12px; }
      `}</style>
    </div>
  );
};
