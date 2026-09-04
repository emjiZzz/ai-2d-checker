import React from "react";
import { FileText, Tag, Layers, Calendar, HardDrive, Trash2, Pencil } from "lucide-react";

// Helper utility to parse ISO datetime strings from backend reliably as UTC
const parseUtcDate = (dateStr: string | null | undefined): Date => {
  if (!dateStr) return new Date();
  const utcStr = dateStr.includes("Z") || dateStr.includes("+") ? dateStr : dateStr + "Z";
  return new Date(utcStr);
};

export interface StandardCardProps {
  std: any;
  formatBytes: (bytes: number) => string;
  openExplorer: (std: any) => void;
  openEdit: (std: any) => void;
  setDeletingStd: (std: any) => void;
}

export const StandardCard: React.FC<StandardCardProps> = ({
  std,
  formatBytes,
  openExplorer,
  openEdit,
  setDeletingStd
}) => {
  return (
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
        <div className="std-meta-item"><Calendar size={12} /><span>{parseUtcDate(std.created_at).toLocaleDateString()}</span></div>
      </div>
      {/* Admin action bar */}
      <div className="std-actions-bar">
        <button
          className="std-action-btn edit"
          onClick={() => openExplorer(std)}
          style={{
            background: "rgba(192, 132, 252, 0.06)",
            borderColor: "rgba(192, 132, 252, 0.2)",
            color: "#c084fc"
          }}
          title="Explore vectorized chunks"
        >
          <Layers size={13} /> Chunks
        </button>
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
};
