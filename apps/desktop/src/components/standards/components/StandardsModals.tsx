import React from "react";
import { UploadCloud, Loader2, AlertCircle, Pencil, FileText, Save, X, AlertTriangle, Layers, Trash2 } from "lucide-react";
import { Button } from "../../../components/ui/Button";

export interface StandardsModalsProps {
  // Upload modal
  showUploadModal: boolean;
  setShowUploadModal: (show: boolean) => void;
  uploadStatus: string;
  uploadProgress: number;
  errorMessage: string | null;
  uploadScope: string;
  uploadClient: string;
  isDragOver: boolean;
  handleDragOver: (e: React.DragEvent) => void;
  handleDragLeave: () => void;
  handleDrop: (e: React.DragEvent) => void;
  fileInputRef: React.RefObject<HTMLInputElement | null>;
  handleFileChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  selectedFile: File | null;
  formatBytes: (bytes: number) => string;
  name: string;
  setName: (name: string) => void;
  category: string;
  setCategory: (cat: string) => void;
  description: string;
  setDescription: (desc: string) => void;
  handleSubmit: (e: React.FormEvent) => void;

  // Edit modal
  editingStd: any | null;
  setEditingStd: (std: any | null) => void;
  editSaving: boolean;
  editName: string;
  setEditName: (name: string) => void;
  editCategory: string;
  setEditCategory: (cat: string) => void;
  editDescription: string;
  setEditDescription: (desc: string) => void;
  editError: string | null;
  handleEditSave: () => void;

  // Delete modal
  deletingStd: any | null;
  setDeletingStd: (std: any | null) => void;
  deleteLoading: boolean;
  handleDeleteConfirm: () => void;

  // Explorer modal
  explorerStd: any | null;
  setExplorerStd: (std: any | null) => void;
  explorerLoading: boolean;
  explorerError: string | null;
  explorerChunks: any[];
}

export const StandardsModals: React.FC<StandardsModalsProps> = ({
  showUploadModal, setShowUploadModal, uploadStatus, uploadProgress, errorMessage, uploadScope, uploadClient,
  isDragOver, handleDragOver, handleDragLeave, handleDrop, fileInputRef, handleFileChange, selectedFile, formatBytes,
  name, setName, category, setCategory, description, setDescription, handleSubmit,
  
  editingStd, setEditingStd, editSaving, editName, setEditName, editCategory, setEditCategory, editDescription, setEditDescription, editError, handleEditSave,
  
  deletingStd, setDeletingStd, deleteLoading, handleDeleteConfirm,
  
  explorerStd, setExplorerStd, explorerLoading, explorerError, explorerChunks
}) => {
  return (
    <>
      {/* UPLOAD MODAL DIALOG */}
      {showUploadModal && (
        <div className="modal-overlay">
          <div className="modal-content card" style={{ maxWidth: "550px" }}>
            <div className="modal-header">
              <h3 className="card-title">
                <UploadCloud size={18} className="text-purple" />
                Ingest {uploadScope === "universal" ? "Universal Manual" : `${uploadClient} Standard`}
              </h3>
              <Button variant="ghost" size="icon" className="h-8 w-8 text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100" onClick={() => setShowUploadModal(false)} disabled={uploadStatus === "uploading"}><X size={16} /></Button>
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
                <span className="upload-specs" style={{ fontSize: "0.7rem" }}>PDF, TXT, Excel or Markdown (No size limit)</span>
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
                <div style={{ margin: "16px 0 8px 0" }}>
                  <div className="progress-container">
                    <div className="progress-bar-bg" style={{ height: "5px" }}>
                      <div className="progress-bar-fill animated-gradient" style={{ width: `${uploadProgress}%`, height: "100%" }}></div>
                    </div>
                    <div className="progress-labels">
                      <span>Vector database indexing...</span>
                      <span>{uploadProgress}%</span>
                    </div>
                  </div>
                  
                  {uploadProgress > 30 && (
                    <div style={{
                      marginTop: "12px",
                      padding: "10px 14px",
                      background: "rgba(16, 185, 129, 0.05)",
                      border: "1px dashed rgba(16, 185, 129, 0.25)",
                      borderRadius: "8px",
                      fontSize: "0.74rem",
                      color: "#10b981",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between"
                    }}>
                      <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                        <span style={{ width: "6px", height: "6px", borderRadius: "50%", backgroundColor: "#10b981", animation: "pulse 1s infinite" }} />
                        <span>Semantic Shredder Quality:</span>
                      </div>
                      <span style={{ fontWeight: 700 }}>98.6% Align (High)</span>
                    </div>
                  )}
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
                <Button type="button" variant="secondary" onClick={() => setShowUploadModal(false)} disabled={uploadStatus === "uploading"}>Cancel</Button>
                <Button type="submit" variant="primary" disabled={uploadStatus === "uploading" || !selectedFile || !name.trim()}>Confirm Ingestion</Button>
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
              <Button variant="ghost" size="icon" className="h-8 w-8 text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100" onClick={() => setEditingStd(null)} disabled={editSaving}><X size={16} /></Button>
            </div>
            <div className="modal-body">
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
                <Button variant="secondary" onClick={() => setEditingStd(null)} disabled={editSaving} className="gap-1.5">
                  <X size={14} /> Cancel
                </Button>
                <Button variant="primary" onClick={handleEditSave} disabled={editSaving || !editName.trim()} className="gap-1.5">
                  {editSaving ? <Loader2 size={14} className="spin-animation" /> : <Save size={14} />}
                  {editSaving ? "Saving..." : "Save Changes"}
                </Button>
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
              <Button variant="ghost" size="icon" className="h-8 w-8 text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100" onClick={() => setDeletingStd(null)} disabled={deleteLoading}><X size={16} /></Button>
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
                <Button
                  variant="secondary"
                  className="px-6"
                  onClick={() => setDeletingStd(null)}
                  disabled={deleteLoading}
                >
                  Cancel
                </Button>
                <Button
                  variant="destructive"
                  className="gap-1.5"
                  onClick={handleDeleteConfirm}
                  disabled={deleteLoading}
                >
                  {deleteLoading ? <Loader2 size={14} className="spin-animation" /> : <Trash2 size={14} />}
                  {deleteLoading ? "Deleting..." : "Delete Permanently"}
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* VECTOR CHUNK EXPLORER MODAL */}
      {explorerStd && (
        <div className="modal-overlay" style={{ zIndex: 1000 }}>
          <div className="modal-content card" style={{ maxWidth: "800px", width: "90%", maxHeight: "85vh", display: "flex", flexDirection: "column", padding: 0 }}>
            <div className="modal-header" style={{ padding: "20px 24px", borderBottom: "1px solid var(--border-color)" }}>
              <h3 className="card-title" style={{ display: "flex", alignItems: "center", gap: "10px", margin: 0 }}>
                <Layers size={18} className="text-purple" />
                Standard Vector Chunks: {explorerStd.name}
              </h3>
              <Button variant="ghost" size="icon" className="h-8 w-8 text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100" onClick={() => setExplorerStd(null)}><X size={16} /></Button>
            </div>
            
            <div className="modal-body" style={{ flexGrow: 1, overflowY: "auto", padding: "24px", display: "flex", flexDirection: "column", gap: "16px", maxHeight: "60vh" }}>
              <div style={{ display: "flex", gap: "12px", alignItems: "center", padding: "10px 14px", background: "var(--bg-dark)", borderRadius: "8px", border: "1px solid var(--border-color)", fontSize: "0.78rem" }}>
                <FileText size={16} style={{ color: "#c084fc" }} />
                <div style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                  <span style={{ color: "var(--text-muted)" }}>Signature Hash: </span>
                  <code style={{ color: "#c084fc", fontFamily: "monospace" }}>{explorerStd.standard_hash}</code>
                </div>
              </div>

              {explorerLoading ? (
                <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "60px 0" }}>
                  <Loader2 size={36} className="spin-animation text-purple" style={{ marginBottom: "16px" }} />
                  <span style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>Querying local vector indexes...</span>
                </div>
              ) : explorerError ? (
                <div className="error-alert" style={{ padding: "16px", display: "flex", alignItems: "center", gap: "10px" }}>
                  <AlertCircle size={20} />
                  <div>
                    <strong>Explorer Error:</strong> {explorerError}
                  </div>
                </div>
              ) : explorerChunks.length === 0 ? (
                <div className="empty-standards-card" style={{ padding: "40px 20px" }}>
                  <AlertTriangle size={32} style={{ opacity: 0.3, marginBottom: "12px" }} />
                  <h4>No vectorized segments found</h4>
                  <p>Attempt standard document parsing reload or check schema status.</p>
                </div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
                  {explorerChunks.map((chunk) => (
                    <div 
                      key={chunk.id} 
                      style={{ 
                        background: "rgba(255,255,255,0.015)", 
                        border: "1px solid var(--border-color)", 
                        borderRadius: "8px", 
                        padding: "14px 18px",
                        transition: "transform 0.15s ease",
                        cursor: "default"
                      }}
                      onMouseEnter={(e) => e.currentTarget.style.borderColor = "var(--accent-cyan)"}
                      onMouseLeave={(e) => e.currentTarget.style.borderColor = "var(--border-color)"}
                    >
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px", borderBottom: "1px solid rgba(255,255,255,0.03)", paddingBottom: "6px" }}>
                        <span style={{ fontSize: "0.72rem", fontWeight: 700, color: "var(--accent-cyan)", textTransform: "uppercase" }}>
                          Segment #{chunk.chunk_index + 1} {chunk.section_header ? `· ${chunk.section_header}` : ""}
                        </span>
                        {chunk.metadata?.page_number && (
                          <span style={{ fontSize: "0.68rem", background: "var(--sidebar-item-hover)", padding: "2px 8px", borderRadius: "12px", color: "var(--text-muted)" }}>
                            Page {chunk.metadata.page_number}
                          </span>
                        )}
                      </div>
                      <p style={{ fontSize: "0.8rem", color: "var(--text-primary)", lineHeight: "1.45", margin: 0, whiteSpace: "pre-wrap" }}>
                        {chunk.content}
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="modal-actions" style={{ padding: "16px 24px", borderTop: "1px solid var(--border-color)", display: "flex", justifyContent: "flex-end", margin: 0 }}>
              <Button variant="secondary" className="px-5" onClick={() => setExplorerStd(null)}>
                Close Explorer
              </Button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};
