import React, { useState, useEffect, useRef } from "react";
import { useAuditStore } from "../stores/auditStore";
import { useWorkspaceStore } from "../stores/workspaceStore";
import {
  FileText, UploadCloud, Plus, Loader2, AlertCircle,
  Tag, Layers, Calendar, HardDrive, FolderOpen, Trash2
} from "lucide-react";

export const StandardsManager: React.FC = () => {
  const {
    standards,
    fetchStandards,
    uploadStandard,
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

  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    fetchStandards();
    fetchClients();
  }, [fetchStandards, fetchClients]);

  const universalStandards = standards.filter(s => s.scope === "universal" || !s.scope);
  
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(true);
  };

  const handleDragLeave = () => {
    setIsDragOver(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    const files = e.dataTransfer.files;
    if (files && files.length > 0) {
      const file = files[0];
      const ext = file.name.split(".").pop()?.toLowerCase();
      if (ext && ["pdf", "txt", "md", "xlsx", "xls"].includes(ext)) {
        setSelectedFile(file);
        if (!name) {
          setName(file.name.replace(/\.[^/.]+$/, "").replace(/[_\-]/g, " ").toUpperCase());
        }
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
      if (!name) {
        setName(file.name.replace(/\.[^/.]+$/, "").replace(/[_\-]/g, " ").toUpperCase());
      }
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile || !name.trim()) return;

    const success = await uploadStandard(
      selectedFile,
      name,
      category || "General Compliance",
      description || "Engineering drafting compliance parameters.",
      uploadScope,
      uploadClient
    );

    if (success) {
      setName("");
      setCategory("");
      setDescription("");
      setSelectedFile(null);
      setShowUploadModal(false);
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

  const StandardCard = ({ std }: { std: any }) => (
    <div className="card standard-card" key={std.id}>
      <div className="std-card-top">
        <div className="std-icon-box">
          <FileText size={20} />
        </div>
        <div className="std-badge">{std.format.toUpperCase()}</div>
      </div>
      <h4 className="std-title" title={std.name}>{std.name}</h4>
      <p className="std-desc">{std.description || "No description provided."}</p>
      <div className="std-meta-grid">
        <div className="std-meta-item">
          <Tag size={12} /><span>{std.category || "General"}</span>
        </div>
        <div className="std-meta-item">
          <HardDrive size={12} /><span>{formatBytes(std.file_size_bytes)}</span>
        </div>
        <div className="std-meta-item">
          <Layers size={12} /><span>{std.metadata.page_count || 1} sections</span>
        </div>
        <div className="std-meta-item">
          <Calendar size={12} /><span>{new Date(std.created_at).toLocaleDateString()}</span>
        </div>
      </div>
    </div>
  );

  return (
    <div className="standards-layout">
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
                    size={14} 
                    className="text-danger" 
                    style={{ cursor: "pointer", opacity: 0.7 }}
                    onClick={(e) => { e.stopPropagation(); if(confirm(`Delete ${c.name} and all its standards?`)) deleteClient(c.name); }} 
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
                <input
                  type="file"
                  ref={fileInputRef}
                  onChange={handleFileChange}
                  style={{ display: "none" }}
                  accept=".pdf,.txt,.md,.xlsx,.xls"
                />
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
                <input
                  type="text"
                  className="form-input"
                  placeholder="e.g. ISO 128 TECHNICAL DRAWING PRINCIPLES"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                  disabled={uploadStatus === "uploading"}
                />
              </div>

              <div className="form-group">
                <label className="form-label">Category Group</label>
                <input
                  type="text"
                  className="form-input"
                  placeholder="e.g. Dimensioning, Tolerancing, Layering"
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  disabled={uploadStatus === "uploading"}
                />
              </div>

              <div className="form-group">
                <label className="form-label">Context Description</label>
                <textarea
                  className="form-input"
                  style={{ height: "60px", resize: "none" }}
                  placeholder="Summarize compliance parameters inside reference standard..."
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  disabled={uploadStatus === "uploading"}
                />
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
        .empty-standards-card h4 {
          font-weight: 500;
          margin-bottom: 8px;
        }
        .empty-standards-card p {
          font-size: 0.85rem;
          color: var(--text-muted);
          max-width: 400px;
          margin: 0 auto;
        }
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
        }
        .standard-card:hover {
          transform: translateY(-4px);
          border-color: var(--accent-cyan);
          box-shadow: 0 10px 25px -5px rgba(0, 229, 255, 0.1);
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
        .std-meta-item span {
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }

        /* MODAL OVERLAY */
        .modal-overlay {
          position: fixed;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
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
          transform: scale(1);
          animation: modalSlideIn 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
        }
        @keyframes modalFadeIn {
          from { opacity: 0; }
          to { opacity: 1; }
        }
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
          background: none;
          border: none;
          color: var(--text-muted);
          font-size: 1.5rem;
          cursor: pointer;
          line-height: 1;
        }
        .close-button:hover {
          color: var(--text-primary);
        }
        .close-button:disabled {
          opacity: 0.3;
          cursor: not-allowed;
        }
        .mt-3 { margin-top: 12px; }
      `}</style>
    </div>
  );
};
