import React from "react";
import {
  FileText, UploadCloud, Plus, AlertTriangle,
  FolderOpen, Trash2, CheckCircle2
} from "lucide-react";
import { useStandardsManager } from "./standards/hooks/useStandardsManager";
import { StandardCard } from "./standards/components/StandardCard";
import { StandardsModals } from "./standards/components/StandardsModals";
import { Button } from "../components/ui/Button";

export const StandardsManager: React.FC = () => {
  const {
    standards, clients, universalStandards,
    deleteClient,
    
    name, setName, category, setCategory, description, setDescription,
    selectedFile, isDragOver,
    showUploadModal, setShowUploadModal, uploadScope, uploadClient,
    fileInputRef, uploadStatus, uploadProgress, errorMessage,
    
    activeClientTab, setActiveClientTab,
    newClientName, setNewClientName,
    isAddingClient, setIsAddingClient,
    
    editingStd, setEditingStd, editName, setEditName, editCategory, setEditCategory,
    editDescription, setEditDescription, editSaving, editError,
    
    deletingStd, setDeletingStd, deleteLoading,
    toast,
    
    explorerStd, setExplorerStd, explorerChunks, explorerLoading, explorerError,
    
    openExplorer, handleDragOver, handleDragLeave, handleDrop, handleFileChange, handleSubmit,
    formatBytes, triggerUploadModal, handleCreateClient,
    openEdit, handleEditSave, handleDeleteConfirm
  } = useStandardsManager();

  return (
    <div className="standards-layout">
      {/* TOAST NOTIFICATION */}
      {toast && (
        <div className={`std-toast ${toast.type}`}>
          {toast.type === "success" ? <CheckCircle2 size={14} /> : <AlertTriangle size={14} />}
          {toast.message}
        </div>
      )}

      {/* MODALS */}
      <StandardsModals
        showUploadModal={showUploadModal}
        setShowUploadModal={setShowUploadModal}
        uploadStatus={uploadStatus}
        uploadProgress={uploadProgress}
        errorMessage={errorMessage}
        uploadScope={uploadScope}
        uploadClient={uploadClient}
        isDragOver={isDragOver}
        handleDragOver={handleDragOver}
        handleDragLeave={handleDragLeave}
        handleDrop={handleDrop}
        fileInputRef={fileInputRef}
        handleFileChange={handleFileChange}
        selectedFile={selectedFile}
        formatBytes={formatBytes}
        name={name}
        setName={setName}
        category={category}
        setCategory={setCategory}
        description={description}
        setDescription={setDescription}
        handleSubmit={handleSubmit}
        
        editingStd={editingStd}
        setEditingStd={setEditingStd}
        editSaving={editSaving}
        editName={editName}
        setEditName={setEditName}
        editCategory={editCategory}
        setEditCategory={setEditCategory}
        editDescription={editDescription}
        setEditDescription={setEditDescription}
        editError={editError}
        handleEditSave={handleEditSave}
        
        deletingStd={deletingStd}
        setDeletingStd={setDeletingStd}
        deleteLoading={deleteLoading}
        handleDeleteConfirm={handleDeleteConfirm}
        
        explorerStd={explorerStd}
        setExplorerStd={setExplorerStd}
        explorerLoading={explorerLoading}
        explorerError={explorerError}
        explorerChunks={explorerChunks}
      />

      {/* 1. UNIVERSAL STANDARDS SECTION */}
      <div className="standards-header">
        <div>
          <h3 className="section-title">KMTI Checking Manuals (Universal)</h3>
          <p className="section-desc">Global internal standards and checksheets applied universally across all drawing audits.</p>
        </div>
        <Button variant="primary" onClick={() => triggerUploadModal("universal")} className="inline-flex items-center gap-2">
          <Plus size={16} /> Add Universal Checklist Manual
        </Button>
      </div>

      {universalStandards.length === 0 ? (
        <div className="empty-standards-card" style={{ padding: "40px 20px" }}>
          <FileText size={36} style={{ opacity: 0.3, margin: "0 auto 16px", display: "block" }} />
          <h4>No Universal Manuals</h4>
          <p>Ingest the baseline KMTI Checking Manual or Checksheet Excel files here.</p>
        </div>
      ) : (
        <div className="standards-grid" style={{ marginBottom: "40px" }}>
          {universalStandards.map(std => (
            <StandardCard
              key={std.id}
              std={std}
              formatBytes={formatBytes}
              openExplorer={openExplorer}
              openEdit={openEdit}
              setDeletingStd={setDeletingStd}
            />
          ))}
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
            <Button variant="ghost" size="icon" className="h-8 w-8 text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100" onClick={() => setIsAddingClient(!isAddingClient)} title="New Client">
              <Plus size={16} />
            </Button>
          </div>

          {isAddingClient && (
            <div style={{ display: "flex", gap: "8px", marginBottom: "16px" }}>
              <input type="text" className="form-input" style={{ padding: "6px" }} placeholder="Client Code..." value={newClientName} onChange={(e) => setNewClientName(e.target.value)} autoFocus />
              <Button variant="primary" size="sm" className="px-3" onClick={handleCreateClient}>Add</Button>
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
                <Button variant="secondary" onClick={() => triggerUploadModal("client_specific", activeClientTab)} className="inline-flex items-center gap-2">
                  <UploadCloud size={16} /> Ingest {activeClientTab} Standard
                </Button>
              </div>

              {standards.filter(s => s.scope === "client_specific" && s.client_name === activeClientTab).length === 0 ? (
                <div className="empty-standards-card" style={{ padding: "40px 20px" }}>
                  <p>No specific standards ingested for {activeClientTab} yet.</p>
                </div>
              ) : (
                <div className="standards-grid">
                  {standards.filter(s => s.scope === "client_specific" && s.client_name === activeClientTab).map(std => (
                    <StandardCard
                      key={std.id}
                      std={std}
                      formatBytes={formatBytes}
                      openExplorer={openExplorer}
                      openEdit={openEdit}
                      setDeletingStd={setDeletingStd}
                    />
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

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
          align-items: flex-start;
          margin-bottom: 16px;
        }
        .std-icon-box {
          width: 40px;
          height: 40px;
          border-radius: 10px;
          background: rgba(6, 182, 212, 0.1);
          border: 1px solid rgba(6, 182, 212, 0.2);
          display: flex;
          align-items: center;
          justify-content: center;
          color: var(--accent-cyan);
        }
        .std-badge {
          font-size: 0.65rem;
          font-weight: 700;
          letter-spacing: 0.5px;
          background: var(--bg-dark);
          color: var(--text-muted);
          padding: 4px 8px;
          border-radius: 12px;
          border: 1px solid rgba(255, 255, 255, 0.05);
        }
        .std-title {
          font-size: 1.05rem;
          font-weight: 600;
          margin: 0 0 8px 0;
          color: var(--text-primary);
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .std-desc {
          font-size: 0.8rem;
          color: var(--text-secondary);
          line-height: 1.4;
          margin-bottom: 20px;
          display: -webkit-box;
          -webkit-line-clamp: 2;
          -webkit-box-orient: vertical;
          overflow: hidden;
          flex-grow: 1;
        }
        .std-meta-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 12px;
          padding-top: 16px;
          border-top: 1px dashed var(--border-color);
        }
        .std-meta-item {
          display: flex;
          align-items: center;
          gap: 6px;
          font-size: 0.75rem;
          color: var(--text-muted);
        }
        .std-meta-item svg {
          opacity: 0.7;
        }

        /* ACTIONS BAR HOVER */
        .std-actions-bar {
          position: absolute;
          bottom: 0;
          left: 0;
          right: 0;
          padding: 12px;
          background: rgba(9, 9, 11, 0.95);
          backdrop-filter: blur(4px);
          border-top: 1px solid rgba(255, 255, 255, 0.1);
          display: flex;
          gap: 8px;
          opacity: 0;
          transform: translateY(10px);
          transition: all 0.25s ease;
        }
        .std-action-btn {
          flex: 1;
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 6px;
          padding: 8px;
          background: rgba(255,255,255,0.05);
          border: 1px solid rgba(255,255,255,0.1);
          border-radius: 6px;
          color: var(--text-secondary);
          font-size: 0.75rem;
          font-weight: 500;
          cursor: pointer;
          transition: all 0.2s;
        }
        .std-action-btn:hover {
          color: var(--text-primary);
          background: rgba(255,255,255,0.1);
        }
        .std-action-btn.edit:hover {
          border-color: rgba(6, 182, 212, 0.3);
          color: var(--accent-cyan);
          background: rgba(6, 182, 212, 0.1);
        }
        .std-action-btn.delete:hover {
          border-color: rgba(239, 68, 68, 0.3);
          color: #ef4444;
          background: rgba(239, 68, 68, 0.1);
        }

        /* MODAL OVERLAYS */
        .modal-overlay {
          position: fixed;
          top: 0; left: 0; right: 0; bottom: 0;
          background: rgba(0, 0, 0, 0.7);
          backdrop-filter: blur(4px);
          z-index: 1000;
          display: flex;
          align-items: center;
          justify-content: center;
          animation: fadeIn 0.2s ease-out;
        }
        .modal-content {
          width: 90%;
          border: 1px solid rgba(255, 255, 255, 0.1);
          box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
          animation: scaleUp 0.3s cubic-bezier(0.16, 1, 0.3, 1);
        }
        .modal-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 16px 20px;
          border-bottom: 1px solid var(--border-color);
        }
        .modal-header h3 {
          margin: 0;
          display: flex;
          align-items: center;
          gap: 10px;
          font-size: 1.1rem;
        }
        .close-button {
          background: none;
          border: none;
          color: var(--text-muted);
          font-size: 1.5rem;
          cursor: pointer;
          padding: 0 8px;
        }
        .close-button:hover { color: var(--text-primary); }
        .modal-body { padding: 20px; }
        
        .form-group { margin-bottom: 16px; }
        .form-label {
          display: block;
          font-size: 0.8rem;
          font-weight: 500;
          color: var(--text-secondary);
          margin-bottom: 8px;
        }
        .form-input {
          width: 100%;
          background: var(--bg-primary);
          border: 1px solid var(--border-color);
          color: var(--text-primary);
          padding: 10px 14px;
          border-radius: 6px;
          font-size: 0.9rem;
          font-family: inherit;
        }
        .form-input:focus {
          outline: none;
          border-color: var(--accent-cyan);
          box-shadow: 0 0 0 2px rgba(6, 182, 212, 0.1);
        }
        .form-input:disabled { opacity: 0.6; cursor: not-allowed; }

        .drag-drop-zone {
          border: 2px dashed rgba(255,255,255,0.15);
          border-radius: 12px;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          background: rgba(0,0,0,0.2);
          cursor: pointer;
          transition: all 0.2s ease;
        }
        .drag-drop-zone:hover {
          border-color: var(--accent-cyan);
          background: rgba(6, 182, 212, 0.05);
        }
        .drag-drop-zone.dragging {
          border-color: #a855f7;
          background: rgba(168, 85, 247, 0.1);
          transform: scale(1.02);
        }
        .drag-drop-zone.disabled {
          opacity: 0.5;
          cursor: not-allowed;
          pointer-events: none;
        }

        .upload-icon-container {
          width: 48px;
          height: 48px;
          border-radius: 50%;
          background: rgba(168, 85, 247, 0.1);
          display: flex;
          align-items: center;
          justify-content: center;
          margin-bottom: 12px;
        }

        .upload-prompt { color: var(--text-primary); font-weight: 500; margin-bottom: 4px; }
        .upload-specs { color: var(--text-muted); }

        .progress-container {
          background: var(--bg-dark);
          padding: 12px;
          border-radius: 8px;
          border: 1px solid var(--border-color);
        }
        .progress-bar-bg {
          background: rgba(255,255,255,0.1);
          border-radius: 4px;
          overflow: hidden;
          margin-bottom: 8px;
        }
        .animated-gradient {
          background: linear-gradient(90deg, var(--accent-cyan), #a855f7, var(--accent-cyan));
          background-size: 200% 100%;
          animation: gradientShift 2s linear infinite;
        }
        .progress-labels {
          display: flex;
          justify-content: space-between;
          font-size: 0.75rem;
          color: var(--text-muted);
          font-weight: 500;
        }

        .std-toast {
          position: fixed;
          bottom: 24px;
          right: 24px;
          display: flex;
          align-items: center;
          gap: 10px;
          padding: 12px 20px;
          border-radius: 8px;
          box-shadow: 0 10px 30px rgba(0, 0, 0, 0.4);
          font-size: 0.85rem;
          color: white;
          z-index: 2000;
          animation: slideUp 0.3s cubic-bezier(0.16, 1, 0.3, 1);
        }
        .std-toast.success { background: #18181b; border: 1px solid rgba(16, 185, 129, 0.3); border-left: 4px solid #10b981; }
        .std-toast.error { background: #18181b; border: 1px solid rgba(239, 68, 68, 0.3); border-left: 4px solid #ef4444; }

        @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
        @keyframes scaleUp { from { opacity: 0; transform: scale(0.95); } to { opacity: 1; transform: scale(1); } }
        @keyframes slideUp { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes gradientShift { 0% { background-position: 100% 0; } 100% { background-position: -100% 0; } }
      `}</style>
    </div>
  );
};
