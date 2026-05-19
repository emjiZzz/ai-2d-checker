import React, { useState, useEffect, useRef } from "react";
import { useAuditStore } from "../stores/auditStore";
import {
  FileText,
  UploadCloud,
  Plus,
  Loader2,
  AlertCircle,
  Tag,
  Layers,
  Calendar,
  HardDrive
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

  const [name, setName] = useState("");
  const [category, setCategory] = useState("");
  const [description, setDescription] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const [showUploadModal, setShowUploadModal] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    fetchStandards();
  }, []);

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
      if (ext && ["pdf", "txt", "md"].includes(ext)) {
        setSelectedFile(file);
        if (!name) {
          // Pre-populate name with friendly filename
          setName(file.name.replace(/\.[^/.]+$/, "").replace(/[_\-]/g, " ").toUpperCase());
        }
      } else {
        alert("Unsupported file format! Please upload PDF, TXT or Markdown.");
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
      description || "Engineering drafting compliance parameters."
    );

    if (success) {
      // Clear forms
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

  return (
    <div className="standards-layout">
      {/* Header section with Action Button */}
      <div className="standards-header">
        <div>
          <h3 className="section-title">Standards Knowledge Library</h3>
          <p className="section-desc">
            Manage your offline engineering rules and reference files inside the traversal-hardened local sidecar sandbox.
          </p>
        </div>
        <button
          className="btn btn-primary"
          onClick={() => {
            resetStore();
            setShowUploadModal(true);
          }}
          style={{ display: "inline-flex", alignItems: "center", gap: "8px" }}
        >
          <Plus size={16} /> Add Standard Document
        </button>
      </div>

      {/* Grid of Standards */}
      {standards.length === 0 ? (
        <div className="empty-standards-card">
          <FileText size={48} style={{ opacity: 0.3, marginBottom: "16px" }} />
          <h4>No Ingested Standards Yet</h4>
          <p>Ingest standard reference PDF/Markdown templates to initiate comparative compliance checks.</p>
          <button
            className="btn btn-secondary mt-3"
            onClick={() => setShowUploadModal(true)}
          >
            Ingest Your First Standard
          </button>
        </div>
      ) : (
        <div className="standards-grid">
          {standards.map((std) => (
            <div className="card standard-card" key={std.id}>
              <div className="std-card-top">
                <div className="std-icon-box">
                  <FileText size={20} />
                </div>
                <div className="std-badge">
                  {std.format.toUpperCase()}
                </div>
              </div>

              <h4 className="std-title" title={std.name}>{std.name}</h4>
              <p className="std-desc">{std.description || "No description provided."}</p>

              <div className="std-meta-grid">
                <div className="std-meta-item">
                  <Tag size={12} />
                  <span>{std.category || "General"}</span>
                </div>
                <div className="std-meta-item">
                  <HardDrive size={12} />
                  <span>{formatBytes(std.file_size_bytes)}</span>
                </div>
                <div className="std-meta-item">
                  <Layers size={12} />
                  <span>{std.metadata.page_count || 1} sections</span>
                </div>
                <div className="std-meta-item">
                  <Calendar size={12} />
                  <span>{new Date(std.created_at).toLocaleDateString()}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* UPLOAD MODAL DIALOG */}
      {showUploadModal && (
        <div className="modal-overlay">
          <div className="modal-content card" style={{ maxWidth: "550px" }}>
            <div className="modal-header">
              <h3 className="card-title">
                <UploadCloud size={18} className="text-purple" />
                Ingest Reference Standard
              </h3>
              <button
                className="close-button"
                onClick={() => setShowUploadModal(false)}
                disabled={uploadStatus === "uploading"}
              >
                &times;
              </button>
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
                  accept=".pdf,.txt,.md"
                />
                <div className="upload-icon-container">
                  {uploadStatus === "uploading" ? (
                    <Loader2 size={24} className="spin-animation text-purple" />
                  ) : (
                    <UploadCloud size={24} className="text-purple" />
                  )}
                </div>
                <span className="upload-prompt" style={{ fontSize: "0.85rem" }}>
                  {selectedFile
                    ? `Selected: ${selectedFile.name} (${formatBytes(selectedFile.size)})`
                    : "Drag & Drop standard reference, or browse"}
                </span>
                <span className="upload-specs" style={{ fontSize: "0.7rem" }}>PDF, TXT, or Markdown (Max 50MB)</span>
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
                    <div
                      className="progress-bar-fill"
                      style={{ width: `${uploadProgress}%` }}
                    ></div>
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
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setShowUploadModal(false)}
                  disabled={uploadStatus === "uploading"}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={uploadStatus === "uploading" || !selectedFile || !name.trim()}
                >
                  Confirm Ingestion
                </button>
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
