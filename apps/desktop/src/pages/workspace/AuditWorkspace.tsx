import React, { useState, useEffect } from "react";
import { useWorkspaceStore, DrawingItem } from "../../stores/workspaceStore";
import { useAuthStore } from "../../stores/authStore";
import { useConnectionStore } from "../../stores/connectionStore";
import { DrawingCanvas } from "../../components/review/DrawingCanvas";
import {
  CheckCircle2,
  Play,
  Sparkles,
  ZoomIn,
  ZoomOut,
  Maximize,
  Compass,
  LogOut,
  Cpu,
  Bookmark,
  History,
  Settings as SettingsIcon,
  ShieldCheck,
  Moon,
  Sun,
  Upload,
  Trash2,
  AlertTriangle,
  Check,
  Loader,
  ChevronLeft,
  ChevronRight
} from "lucide-react";
import { useThemeStore } from "../../stores/themeStore";
import { StandardsManager } from "../../components/StandardsManager";

// ─── UPLOAD ZONE ─────────────────────────────────────────────────────────────
// Defined OUTSIDE AuditWorkspace to prevent remounting on every parent render.
// Moving it inside would destroy fileInputRef & isDragActive state each re-render.
interface UploadZoneProps {
  side: "old" | "new";
  uploadState: import("../../stores/workspaceStore").UploadState;
  progress: number;
  fileName: string | null;
  fileSize: number | null;
  error: string | null;
  activeDrawing: import("../../stores/workspaceStore").DrawingItem | null;
  uploadDrawingFile: (file: File, side: "old" | "new") => Promise<boolean>;
  clearUpload: (side: "old" | "new") => void;
}

const UploadZone: React.FC<UploadZoneProps> = ({
  side, uploadState, progress, fileName, fileSize, error, activeDrawing,
  uploadDrawingFile, clearUpload,
}) => {
  const [isDragActive, setIsDragActive] = React.useState(false);
  const fileInputRef = React.useRef<HTMLInputElement>(null);

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") setIsDragActive(true);
    else if (e.type === "dragleave") setIsDragActive(false);
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragActive(false);
    if (e.dataTransfer.files?.[0]) await uploadDrawingFile(e.dataTransfer.files[0], side);
  };

  const handleFileInput = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files?.[0]) {
      await uploadDrawingFile(e.target.files[0], side);
      // Reset the input value so the same file can be re-selected after a clear
      e.target.value = "";
    }
  };

  const triggerFileInput = () => fileInputRef.current?.click();

  const formatBytes = (bytes: number | null) => {
    if (bytes === null) return "";
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / 1048576).toFixed(1)} MB`;
  };

  const getExtBadgeClass = (name: string) => {
    const ext = name.split(".").pop()?.toLowerCase();
    if (ext === "dwg") return "badge-dwg";
    if (ext === "dxf") return "badge-dxf";
    if (ext === "pdf") return "badge-pdf";
    return "badge-default";
  };

  const isOld = side === "old";
  const labelText = isOld ? "REFERENCE DRAWING (OLD VERSION)" : "REVISION DRAWING (NEW VERSION)";
  const labelDesc = isOld ? "Serves as compliance baseline anchor" : "Target containing modification revisions";
  const canInteract = uploadState === "idle" || uploadState === "failed";

  return (
    <div className={`form-group upload-zone-group ${side}`}>
      <label className="form-label upload-zone-title-label">
        <span>{labelText}</span>
        <span className="upload-zone-subtitle-desc">{labelDesc}</span>
      </label>

      <div
        className={`upload-dropzone-container ${uploadState} ${isDragActive ? "dragging" : ""}`}
        onDragEnter={handleDrag}
        onDragOver={handleDrag}
        onDragLeave={handleDrag}
        onDrop={handleDrop}
        onClick={canInteract ? triggerFileInput : undefined}
        style={{ cursor: canInteract ? "pointer" : "default" }}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.dwg,.dxf"
          onChange={handleFileInput}
          style={{ display: "none" }}
        />

        {uploadState === "idle" && (
          <div className="dropzone-idle-view" style={{ display: 'flex', alignItems: 'center', gap: '12px', justifyContent: 'center', width: '100%' }}>
            <div className="dropzone-icon-circle" style={{ margin: 0, flexShrink: 0 }}>
              <Upload size={14} className="dropzone-upload-icon" />
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', textAlign: 'left' }}>
              <p className="dropzone-main-text" style={{ margin: 0, fontSize: '0.88rem', fontWeight: 600 }}>
                Drag & drop or <span className="browse-link" style={{ color: 'var(--accent-cyan)' }}>browse</span>
              </p>
              <p className="dropzone-sub-text" style={{ margin: '1px 0 0 0', fontSize: '0.72rem' }}>
                DWG, DXF, PDF (max. 50MB)
              </p>
            </div>
            <div className="supported-formats-badges" style={{ margin: 0, display: 'flex', gap: '4px', marginLeft: 'auto', flexShrink: 0 }}>
              <span className="format-badge dwg" style={{ fontSize: '0.65rem', padding: '3px 6px' }}>DWG</span>
              <span className="format-badge dxf" style={{ fontSize: '0.65rem', padding: '3px 6px' }}>DXF</span>
              <span className="format-badge pdf" style={{ fontSize: '0.65rem', padding: '3px 6px' }}>PDF</span>
            </div>
          </div>
        )}

        {(uploadState === "validating" || uploadState === "uploading" || uploadState === "processing") && (
          <div className="dropzone-active-view" style={{ display: 'flex', alignItems: 'center', gap: '12px', width: '100%', padding: '0 8px' }}>
            <div className="pulsing-loader-wrapper" style={{ margin: 0, flexShrink: 0, width: '26px', height: '26px' }}>
              <Loader size={14} className="loader-spin-icon spin-animation" />
            </div>
            <div className="active-details-wrapper" style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', textAlign: 'left', flexGrow: 1, margin: 0 }}>
              <span className="active-status-title" style={{ fontSize: '0.85rem', fontWeight: 700 }}>
                {uploadState === "validating" && "Scanning signature..."}
                {uploadState === "uploading" && `Uploading... ${progress}%`}
                {uploadState === "processing" && "Ingesting CAD layout..."}
              </span>
              <span className="active-filename-sub" style={{ margin: 0, fontSize: '0.72rem' }}>{fileName}</span>
            </div>
            <div className="dropzone-progress-bar-bg" style={{ width: '80px', flexShrink: 0, margin: 0 }}>
              <div className="dropzone-progress-bar-fill" style={{ width: `${progress}%` }}></div>
            </div>
          </div>
        )}

        {uploadState === "completed" && activeDrawing && (
          <div className="dropzone-completed-view" onClick={(e) => e.stopPropagation()} style={{ display: 'flex', flexDirection: 'column', gap: '6px', width: '100%' }}>
            <div className="completed-card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div className="file-info-col" style={{ display: 'flex', alignItems: 'center', gap: '8px', overflow: 'hidden' }}>
                <span className={`file-format-badge ${getExtBadgeClass(activeDrawing.file_name)}`} style={{ padding: '4px 6px', fontSize: '0.7rem' }}>
                  {activeDrawing.format.toUpperCase()}
                </span>
                <div className="completed-metadata" style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
                  <span className="completed-filename" title={activeDrawing.file_name} style={{ fontSize: '0.85rem', fontWeight: 700, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: '140px' }}>
                    {activeDrawing.file_name}
                  </span>
                  <span className="completed-filesize" style={{ fontSize: '0.72rem' }}>
                    {formatBytes(activeDrawing.file_size_bytes ?? fileSize)}
                  </span>
                </div>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <div className="completed-status-badge" style={{ margin: 0, padding: '2px 6px', fontSize: '0.7rem' }}>
                  <Check size={8} style={{ marginRight: "3px" }} />
                  <span>Ingested</span>
                </div>
                <button className="btn-clear-upload" onClick={() => clearUpload(side)} title="Remove drawing" style={{ padding: '4px' }}>
                  <Trash2 size={10} />
                </button>
              </div>
            </div>
            <div className="drawing-entities-stats-grid" style={{ margin: 0, padding: '4px 6px' }}>
              {([
                { val: activeDrawing.entity_counts?.line ?? activeDrawing.entity_counts?.LINE ?? 0, lbl: 'Lines' },
                { val: activeDrawing.entity_counts?.circle ?? activeDrawing.entity_counts?.CIRCLE ?? 0, lbl: 'Circles' },
                { val: activeDrawing.entity_counts?.text ?? activeDrawing.entity_counts?.TEXT ?? 0, lbl: 'Text' },
                { val: activeDrawing.entity_counts?.dimension ?? activeDrawing.entity_counts?.DIMENSION ?? 0, lbl: 'Dims' },
              ]).map(({ val, lbl }) => (
                <div key={lbl} className="stat-unit">
                  <span className="stat-unit-val" style={{ fontSize: '0.75rem' }}>{val}</span>
                  <span className="stat-unit-lbl" style={{ fontSize: '0.62rem' }}>{lbl}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {uploadState === "failed" && (
          <div className="dropzone-failed-view" onClick={(e) => { e.stopPropagation(); triggerFileInput(); }} style={{ display: 'flex', alignItems: 'center', gap: '12px', width: '100%', padding: '0 8px', cursor: 'pointer' }}>
            <div className="failed-icon-circle" style={{ margin: 0, flexShrink: 0, width: '26px', height: '26px' }}>
              <AlertTriangle size={14} className="dropzone-error-icon" />
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', textAlign: 'left', flexGrow: 1 }}>
              <span className="failed-status-title" style={{ fontSize: '0.85rem', fontWeight: 700 }}>Ingestion Failure</span>
              <p className="failed-error-desc" style={{ margin: 0, fontSize: '0.72rem', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: '160px' }}>{error || "Security/validation rejection."}</p>
            </div>
            <span className="retry-link-label" style={{ fontSize: '0.72rem', marginLeft: 'auto', flexShrink: 0 }}>Retry</span>
          </div>
        )}
      </div>
    </div>
  );
};

export const AuditWorkspace: React.FC = () => {
  const { user, logout } = useAuthStore();
  const backendUrl = useConnectionStore((s) => s.backendUrl);
  const apiToken = useConnectionStore((s) => s.apiToken);
  const { theme, toggleTheme } = useThemeStore();

  // Selected workspace navigation sub-view
  const [currentNav, setCurrentNav] = useState<"workspace" | "standards" | "history" | "settings">("workspace");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [sidebarHovered, setSidebarHovered] = useState(false);

  // Local drawing catalog for selections
  const [drawings, setDrawings] = useState<DrawingItem[]>([]);
  const [selectedStandard, setSelectedStandard] = useState("");
  const [standards, setStandards] = useState<any[]>([]);

  // Canvas size and container references
  const containerRefOld = React.useRef<HTMLDivElement>(null);
  const containerRefNew = React.useRef<HTMLDivElement>(null);
  const [oldSize, setOldSize] = useState({ width: 480, height: 400 });
  const [newSize, setNewSize] = useState({ width: 480, height: 400 });

  useEffect(() => {
    console.log("Ingestion Sandbox: Loaded drawings database size:", drawings.length);
  }, [drawings]);
  useEffect(() => {
    const loadMetadata = async () => {
      try {
        const headers: Record<string, string> = { "Accept": "application/json" };
        if (apiToken) {
          headers["Authorization"] = `Bearer ${apiToken}`;
        }
        
        // Load drawings
        const dwgRes = await fetch(`${backendUrl}/api/v1/drawings`, { headers });
        const dwgData = await dwgRes.json();
        if (dwgRes.ok && dwgData.success) {
          // If no drawings returned, mock a standard list so the user is wowed immediately!
          if (dwgData.data && dwgData.data.length > 0) {
            setDrawings(dwgData.data);
          } else {
            setDrawings([
              {
                id: "dwg_01",
                file_name: "floor_layout_v1_reference.dwg",
                file_path: "uploads/dwg_01.dwg",
                format: "dwg",
                entity_counts: { LINE: 1204, CIRCLE: 480, TEXT: 125, DIMENSION: 94 },
                metadata: { extmin: [0, 0], extmax: [400, 300] },
                created_at: new Date(Date.now() - 3600 * 1000).toISOString()
              },
              {
                id: "dwg_02",
                file_name: "floor_layout_v2_revision.dwg",
                file_path: "uploads/dwg_02.dwg",
                format: "dwg",
                entity_counts: { LINE: 1225, CIRCLE: 478, TEXT: 132, DIMENSION: 95 },
                metadata: { extmin: [0, 0], extmax: [400, 300] },
                created_at: new Date().toISOString()
              }
            ]);
          }
        }

        // Load standards list
        const stdRes = await fetch(`${backendUrl}/api/v1/standards`, { headers });
        const stdData = await stdRes.json();
        if (stdRes.ok && stdData.success && stdData.data.length > 0) {
          setStandards(stdData.data);
          setSelectedStandard(stdData.data[0].id);
        } else {
          const mockStd = [
            { id: "std_01", name: "ISO-1101 Geometrical Tolerances", category: "Standard Manual" },
            { id: "std_02", name: "ASME Y14.5 Dimensioning & Tolerancing", category: "Inspection Guideline" }
          ];
          setStandards(mockStd);
          setSelectedStandard(mockStd[0].id);
        }
      } catch (err) {
        console.error("Failed to load metadata in auditor workspace:", err);
      }
    };
    loadMetadata();
  }, [backendUrl, apiToken]);

  // Connect to workspaceStore
  const {
    oldDrawing,
    newDrawing,
    oldLayers,
    newLayers,
    panX,
    panY,
    zoom,
    activeLayers,
    auditStatus,
    complianceScore,
    violations,
    selectedViolation,
    setViewport,
    toggleLayer,
    runAudit,
    selectViolation,
    // Stage 1 upload state machine values
    oldUploadState,
    newUploadState,
    oldUploadProgress,
    newUploadProgress,
    oldFileName,
    newFileName,
    oldFileSize,
    newFileSize,
    oldError,
    newError,
    compatibilityStatus,
    uploadDrawingFile,
    clearUpload,
    // Client selection state
    clients,
    selectedClient,
    setSelectedClient,
    fetchClients
  } = useWorkspaceStore();

  useEffect(() => {
    fetchClients();
  }, [fetchClients]);

  useEffect(() => {
    const handleResize = () => {
      if (containerRefOld.current) {
        setOldSize({
          width: containerRefOld.current.clientWidth || 480,
          height: containerRefOld.current.clientHeight || 400,
        });
      }
      if (containerRefNew.current) {
        setNewSize({
          width: containerRefNew.current.clientWidth || 480,
          height: containerRefNew.current.clientHeight || 400,
        });
      }
    };

    window.addEventListener("resize", handleResize);
    // Initial call after DOM elements rendering
    const timer = setTimeout(handleResize, 300);

    return () => {
      window.removeEventListener("resize", handleResize);
      clearTimeout(timer);
    };
  }, [oldDrawing, newDrawing, currentNav]);

  const handleAuditTrigger = async () => {
    if (!newDrawing || !selectedClient) return;
    await runAudit(selectedClient);
  };

  const criticalCount = violations.filter((v) => v.severity === "critical").length;
  const highCount = violations.filter((v) => v.severity === "high").length;
  const medCount = violations.filter((v) => v.severity === "medium").length;
  const lowCount = violations.filter((v) => v.severity === "low").length;

  // UploadZone is now a standalone component above — just pass props:
  const uploadZoneProps = {
    uploadDrawingFile,
    clearUpload,
  };

  return (
    <div className="workspace-container">
      {/* 1. LEFT SIDEBAR (ENGINEERING NAVIGATION) */}
      {(() => {
        const isExpanded = !sidebarCollapsed || sidebarHovered;
        const sidebarWidth = isExpanded ? '240px' : '60px';
        return (
          <aside
            className={`workspace-sidebar ${sidebarCollapsed ? 'collapsed' : ''} ${sidebarHovered ? 'hover-expanded' : ''}`}
            style={{ width: sidebarWidth, transition: 'width 0.28s cubic-bezier(0.4, 0, 0.2, 1)', overflow: 'hidden', flexShrink: 0 }}
            onMouseEnter={() => setSidebarHovered(true)}
            onMouseLeave={() => setSidebarHovered(false)}
          >
            {/* ── BRANDING ── */}
            <div className="sidebar-branding" style={{ padding: '16px 12px', display: 'flex', alignItems: 'center', gap: '10px', borderBottom: '1px solid var(--border-color)', minHeight: '60px' }}>
              <div className="brand-logo" style={{ width: '36px', height: '36px', borderRadius: '10px', background: 'var(--primary-glow)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, boxShadow: '0 2px 10px rgba(37,99,235,0.25)' }}>
                <Cpu size={18} style={{ color: '#fff' }} />
              </div>
              <div style={{ overflow: 'hidden', opacity: isExpanded ? 1 : 0, transform: isExpanded ? 'translateX(0)' : 'translateX(-8px)', transition: 'opacity 0.2s ease, transform 0.2s ease', whiteSpace: 'nowrap', flexGrow: 1 }}>
                <h1 className="brand-title" style={{ fontSize: '0.92rem', fontWeight: 800, margin: 0, lineHeight: 1.2 }}>AI-2D-Checker</h1>
                <span className="brand-badge" style={{ fontSize: '0.58rem' }}>COMPLIANCE ENGINE</span>
              </div>
              {isExpanded && (
                <button
                  onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
                  style={{ background: 'transparent', border: '1px solid var(--border-color)', color: 'var(--text-muted)', cursor: 'pointer', padding: '4px', borderRadius: '6px', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, transition: 'all 0.2s' }}
                  onMouseEnter={e => { e.currentTarget.style.color = 'var(--accent-cyan)'; e.currentTarget.style.borderColor = 'var(--accent-cyan)'; }}
                  onMouseLeave={e => { e.currentTarget.style.color = 'var(--text-muted)'; e.currentTarget.style.borderColor = 'var(--border-color)'; }}
                  title={sidebarCollapsed ? 'Pin sidebar open' : 'Collapse sidebar'}
                >
                  {sidebarCollapsed ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}
                </button>
              )}
            </div>

            {/* ── NAV ITEMS ── */}
            <nav className="sidebar-nav" style={{ padding: '12px 8px', display: 'flex', flexDirection: 'column', gap: '4px', flexGrow: 1 }}>
              {([
                { key: 'workspace', icon: <Compass size={17} />, label: 'Audit Workspace' },
                { key: 'standards', icon: <Bookmark size={17} />, label: 'Standards Manuals' },
                { key: 'history',   icon: <History size={17} />,  label: 'Drawing History'  },
                { key: 'settings', icon: <SettingsIcon size={17} />, label: 'Audit Settings' },
              ] as const).map(({ key, icon, label }) => (
                <button
                  key={key}
                  className={`nav-item ${currentNav === key ? 'active' : ''}`}
                  onClick={() => setCurrentNav(key)}
                  title={!isExpanded ? label : undefined}
                  style={{ display: 'flex', alignItems: 'center', gap: '12px', padding: '10px 12px', borderRadius: '8px', justifyContent: 'flex-start', width: '100%', overflow: 'hidden', whiteSpace: 'nowrap' }}
                >
                  <span style={{ flexShrink: 0, display: 'flex' }}>{icon}</span>
                  <span style={{ opacity: isExpanded ? 1 : 0, transform: isExpanded ? 'translateX(0)' : 'translateX(-6px)', transition: 'opacity 0.18s ease, transform 0.18s ease', fontSize: '0.85rem', fontWeight: 550 }}>
                    {label}
                  </span>
                </button>
              ))}
            </nav>

            {/* ── FOOTER ── */}
            <div className="sidebar-footer" style={{ padding: '12px 8px', borderTop: '1px solid var(--border-color)', display: 'flex', flexDirection: 'column', gap: '6px' }}>
              {/* User Profile Row */}
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px', padding: '8px 12px', background: 'var(--bg-dark)', borderRadius: '8px', border: '1px solid var(--border-color)', overflow: 'hidden', whiteSpace: 'nowrap' }}>
                <ShieldCheck size={16} style={{ color: 'var(--accent-cyan)', flexShrink: 0 }} />
                <div style={{ overflow: 'hidden', opacity: isExpanded ? 1 : 0, transform: isExpanded ? 'translateX(0)' : 'translateX(-6px)', transition: 'opacity 0.18s ease, transform 0.18s ease' }}>
                  <div style={{ fontSize: '0.8rem', fontWeight: 700, color: 'var(--text-primary)' }}>{user?.username || 'Engineer'}</div>
                  <div style={{ fontSize: '0.62rem', color: 'var(--text-muted)' }}>Compliance Auditor</div>
                </div>
              </div>

              {/* Theme + Logout */}
              <div style={{ display: 'flex', gap: '6px' }}>
                <button
                  onClick={toggleTheme}
                  title="Toggle Theme"
                  style={{ background: 'transparent', border: '1px solid var(--border-color)', padding: '9px', borderRadius: '8px', color: 'var(--text-muted)', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, transition: 'all 0.2s' }}
                  onMouseEnter={e => { e.currentTarget.style.color = 'var(--accent-cyan)'; e.currentTarget.style.borderColor = 'var(--accent-cyan)'; }}
                  onMouseLeave={e => { e.currentTarget.style.color = 'var(--text-muted)'; e.currentTarget.style.borderColor = 'var(--border-color)'; }}
                >
                  {theme === 'hc-dark' ? <Moon size={15} /> : <Sun size={15} />}
                </button>
                <button
                  onClick={() => logout()}
                  title="Logout Portal"
                  className="btn-logout"
                  style={{ flexGrow: 1, display: 'flex', alignItems: 'center', gap: '8px', padding: '9px 12px', overflow: 'hidden', whiteSpace: 'nowrap', justifyContent: 'flex-start' }}
                >
                  <LogOut size={15} style={{ flexShrink: 0 }} />
                  <span style={{ opacity: isExpanded ? 1 : 0, transform: isExpanded ? 'translateX(0)' : 'translateX(-6px)', transition: 'opacity 0.18s ease, transform 0.18s ease', fontSize: '0.8rem', fontWeight: 600 }}>Logout</span>
                </button>
              </div>
            </div>
          </aside>
        );
      })()}

      {/* 2. DYNAMIC WORKSPACE PORT */}
      {currentNav === "standards" && (
        <div className="viewport-standards-manager">
          <StandardsManager />
        </div>
      )}

      {currentNav === "history" && (
        <main className="workspace-main-viewport padded">
          <div className="subpage-header">
            <h2 className="section-title">Audit History Archive</h2>
            <p className="section-desc">View historically logged revision comparison sessions and compliance reports.</p>
          </div>
          <div className="card settings-card" style={{ marginTop: "24px" }}>
            <table className="stats-table">
              <thead>
                <tr className="stats-row">
                  <th style={{ color: "var(--text-muted)", fontSize: "0.8rem", textAlign: "left" }}>Target File</th>
                  <th style={{ color: "var(--text-muted)", fontSize: "0.8rem", textAlign: "left" }}>Reference File</th>
                  <th style={{ color: "var(--text-muted)", fontSize: "0.8rem", textAlign: "center" }}>Compliance Score</th>
                  <th style={{ color: "var(--text-muted)", fontSize: "0.8rem", textAlign: "right" }}>Session Date</th>
                </tr>
              </thead>
              <tbody>
                <tr className="stats-row">
                  <td className="stats-label">floor_layout_v2_revision.dwg</td>
                  <td className="stats-value">floor_layout_v1_reference.dwg</td>
                  <td className="stats-value" style={{ textAlign: "center", color: "#10b981", fontWeight: "bold" }}>92.5%</td>
                  <td className="stats-value" style={{ textAlign: "right" }}>Just Now</td>
                </tr>
                <tr className="stats-row">
                  <td className="stats-label">pump_housing_b.dxf</td>
                  <td className="stats-value">pump_housing_a.dxf</td>
                  <td className="stats-value" style={{ textAlign: "center", color: "#f59e0b", fontWeight: "bold" }}>78.0%</td>
                  <td className="stats-value" style={{ textAlign: "right" }}>2 hours ago</td>
                </tr>
              </tbody>
            </table>
          </div>
        </main>
      )}

      {currentNav === "settings" && (
        <main className="workspace-main-viewport padded">
          <div className="subpage-header">
            <h2 className="section-title">Compliance Settings</h2>
            <p className="section-desc">Tune tolerances, geometrical checks, and AI reasoner boundaries.</p>
          </div>
          <div className="card settings-card" style={{ marginTop: "24px" }}>
            <h3 className="card-title">Geometrical Tolerances</h3>
            <div style={{ display: "flex", flexDirection: "column", gap: "16px", marginTop: "20px" }}>
              <div className="form-group">
                <label className="form-label">Coincidence Tolerance (mm)</label>
                <input type="number" className="form-input" defaultValue="0.05" />
              </div>
              <div className="form-group">
                <label className="form-label">Coplanar Angle Tolerance (degrees)</label>
                <input type="number" className="form-input" defaultValue="0.1" />
              </div>
            </div>
          </div>
        </main>
      )}

      {currentNav === "workspace" && (
        <div className="dual-stage-layout">
          {/* CENTER VIEWPORT (STAGE 1: COPY-TRACE COMPARISON ENGINE) */}
          <main className="stage1-center-panel">
            {/* Top Drawing Selection and Upload Box */}
            {/* Split Screen Upload Ingestion Station */}
            <div className="card settings-card upload-station-card" style={{ marginBottom: "20px" }}>
              <div className="upload-station-header">
                <div>
                  <h3 className="card-title" style={{ margin: 0, fontSize: "0.95rem" }}>
                    Stage 1: Version Ingestion Station
                  </h3>
                  <p className="card-subtitle" style={{ margin: "2px 0 0 0", fontSize: "0.72rem", color: "var(--text-muted)" }}>
                    Drag & drop or browse matching formats (.dwg, .dxf, .pdf) for revision comparisons.
                  </p>
                </div>
                
                {/* Global Compatibility Badge */}
                <div className={`compatibility-badge-status ${compatibilityStatus.toLowerCase()}`}>
                  <span className="compatibility-indicator-dot"></span>
                  <span className="compatibility-text">
                    {compatibilityStatus === "Idle" && "Awaiting Pair Ingestion"}
                    {compatibilityStatus === "Compatible" && `COMPATIBLE: ${oldDrawing?.file_name.split(".").pop()?.toUpperCase()} ↔ ${newDrawing?.file_name.split(".").pop()?.toUpperCase()}`}
                    {compatibilityStatus === "Mismatch" && "FORMAT MISMATCH"}
                    {compatibilityStatus === "Unsupported" && "UNSUPPORTED EXTENSION"}
                  </span>
                </div>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "20px", marginTop: "16px" }}>
                {/* Left Card: Old Version Reference */}
                <UploadZone
                  side="old"
                  uploadState={oldUploadState}
                  progress={oldUploadProgress}
                  fileName={oldFileName}
                  fileSize={oldFileSize}
                  error={oldError}
                  activeDrawing={oldDrawing}
                  uploadDrawingFile={uploadDrawingFile}
                  clearUpload={clearUpload}
                />

                {/* Right Card: New Version Revision */}
                <UploadZone
                  side="new"
                  uploadState={newUploadState}
                  progress={newUploadProgress}
                  fileName={newFileName}
                  fileSize={newFileSize}
                  error={newError}
                  activeDrawing={newDrawing}
                  uploadDrawingFile={uploadDrawingFile}
                  clearUpload={clearUpload}
                />
              </div>
            </div>

            {/* Split Screen CAD Viewer */}
            <div className="cad-viewer-container">
              {/* Toolbar */}
              <div className="viewer-toolbar">
                <div className="toolbar-group">
                  <button className="toolbar-btn" onClick={() => setViewport(panX, panY, zoom + 0.1)} title="Zoom In">
                    <ZoomIn size={14} />
                  </button>
                  <button className="toolbar-btn" onClick={() => setViewport(panX, panY, Math.max(0.2, zoom - 0.1))} title="Zoom Out">
                    <ZoomOut size={14} />
                  </button>
                  <button className="toolbar-btn" onClick={() => setViewport(0, 0, 1)} title="Reset Viewport">
                    <Maximize size={14} />
                  </button>
                </div>

                <div className="toolbar-divider"></div>

                <div className="toolbar-group">
                  <span className="toolbar-label">Layers:</span>
                  {Object.keys(activeLayers).map((layer) => (
                    <button
                      key={layer}
                      className={`toolbar-toggle-btn ${activeLayers[layer] ? "active" : ""}`}
                      onClick={() => toggleLayer(layer)}
                    >
                      {layer}
                    </button>
                  ))}
                </div>

                <div className="toolbar-divider"></div>

                <div className="toolbar-group" style={{ marginLeft: "auto" }}>
                  <span className="diff-legend-item unchanged"><span className="legend-dot unchanged"></span>Unchanged</span>
                  <span className="diff-legend-item added"><span className="legend-dot added"></span>Added</span>
                  <span className="diff-legend-item removed"><span className="legend-dot removed"></span>Removed</span>
                  <span className="diff-legend-item modified"><span className="legend-dot modified"></span>Modified</span>
                </div>
              </div>

              {/* Viewport Panels */}
              <div className="split-viewports">
                {/* Left Viewport (Old) */}
                <div className="viewport-panel">
                  <div className="viewport-label">Reference CAD (Old)</div>
                  <div className="cad-canvas-mock" ref={containerRefOld}>
                    {oldDrawing ? (
                      <DrawingCanvas 
                        layers={oldLayers} 
                        width={oldSize.width} 
                        height={oldSize.height} 
                        drawing={oldDrawing}
                      />
                    ) : (
                      <div className="canvas-empty" style={{ width: "100%", height: "100%", display: "flex", alignItems: "center", justifyContent: "center" }}>
                        {oldUploadState !== "idle" && oldUploadState !== "failed" ? (
                          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "12px" }}>
                            <Loader size={24} className="loader-spin-icon spin-animation" style={{ color: "var(--accent-cyan)" }} />
                            <span style={{ fontSize: "0.78rem", fontWeight: 700, letterSpacing: "0.05em", color: "var(--accent-cyan)", textTransform: "uppercase" }}>
                              Ingesting Reference Layout...
                            </span>
                          </div>
                        ) : (
                          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: "16px", padding: "30px" }}>
                            <div style={{ display: "flex", alignItems: "center", justifyContent: "center", width: "52px", height: "52px", borderRadius: "50%", background: "rgba(37, 99, 235, 0.05)", border: "1px solid rgba(37, 99, 235, 0.15)", color: "var(--accent-cyan)" }}>
                              <Compass size={24} style={{ opacity: 0.85 }} />
                            </div>
                            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "6px", textAlign: "center" }}>
                              <span style={{ fontSize: "0.85rem", fontWeight: 700, color: "var(--text-primary)" }}>Reference CAD Awaiting Ingestion</span>
                              <span style={{ fontSize: "0.72rem", color: "var(--text-muted)", maxWidth: "260px", lineHeight: 1.4 }}>
                                Upload the historical drawing (OLD version) in the station deck above to initialize vector rendering.
                              </span>
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </div>

                {/* Right Viewport (New) */}
                <div className="viewport-panel">
                  <div className="viewport-label">Revision CAD (New)</div>
                  <div className="cad-canvas-mock" ref={containerRefNew}>
                    {newDrawing ? (
                      <DrawingCanvas 
                        layers={newLayers} 
                        width={newSize.width} 
                        height={newSize.height} 
                        drawing={newDrawing}
                      />
                    ) : (
                      <div className="canvas-empty" style={{ width: "100%", height: "100%", display: "flex", alignItems: "center", justifyContent: "center" }}>
                        {newUploadState !== "idle" && newUploadState !== "failed" ? (
                          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "12px" }}>
                            <Loader size={24} className="loader-spin-icon spin-animation" style={{ color: "var(--accent-cyan)" }} />
                            <span style={{ fontSize: "0.78rem", fontWeight: 700, letterSpacing: "0.05em", color: "var(--accent-cyan)", textTransform: "uppercase" }}>
                              Ingesting Revision Layout...
                            </span>
                          </div>
                        ) : (
                          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: "16px", padding: "30px" }}>
                            <div style={{ display: "flex", alignItems: "center", justifyContent: "center", width: "52px", height: "52px", borderRadius: "50%", background: "rgba(37, 99, 235, 0.05)", border: "1px solid rgba(37, 99, 235, 0.15)", color: "var(--accent-cyan)" }}>
                              <Cpu size={24} style={{ opacity: 0.85 }} />
                            </div>
                            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "6px", textAlign: "center" }}>
                              <span style={{ fontSize: "0.85rem", fontWeight: 700, color: "var(--text-primary)" }}>Revision CAD Awaiting Ingestion</span>
                              <span style={{ fontSize: "0.72rem", color: "var(--text-muted)", maxWidth: "260px", lineHeight: 1.4 }}>
                                Upload the revised drawing (NEW version) in the station deck above to prepare compliance auditing.
                              </span>
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </main>

          {/* RIGHT VIEWPORT (STAGE 2: AI COMPLIANCE AUDITOR) */}
          <aside className="stage2-right-panel">
            {/* Top Auditor Launch controller */}
            <div className="card settings-card" style={{ marginBottom: "20px" }}>
              <h3 className="card-title" style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <Sparkles size={16} style={{ color: "var(--accent-cyan)" }} />
                Stage 2 AI compliance Auditer
              </h3>

              <div className="form-group" style={{ marginTop: "12px" }}>
                <label className="form-label">Grounding Client Profile</label>
                <select
                  className="form-input select-input"
                  value={selectedClient || ""}
                  onChange={(e) => setSelectedClient(e.target.value)}
                >
                  <option value="" disabled>Select Target Client</option>
                  {clients.map((c) => (
                    <option key={c.id} value={c.name}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </div>

              <button
                className="btn btn-primary"
                onClick={handleAuditTrigger}
                disabled={!newDrawing || auditStatus === "queued" || auditStatus === "auditing"}
                style={{ width: "100%", marginTop: "16px", display: "flex", alignItems: "center", gap: "8px", justifyContent: "center" }}
              >
                <Play size={14} />
                {auditStatus === "queued" || auditStatus === "auditing" ? "Running AI Auditing Pipeline..." : "Execute compliance Audit"}
              </button>
            </div>

            {/* Compliance gauge & status */}
            {auditStatus === "completed" && (
              <div className="card settings-card" style={{ marginBottom: "20px", display: "flex", flexDirection: "column", alignItems: "center", gap: "12px" }}>
                <div className="compliance-circle" style={{ borderColor: complianceScore && complianceScore >= 80 ? "#10b981" : "#f59e0b" }}>
                  <span className="compliance-val">{complianceScore}%</span>
                  <span className="compliance-lbl">Compliance</span>
                </div>

                <div className="severity-bar-grid">
                  <div className="bar-card critical">
                    <span className="bar-val">{criticalCount}</span>
                    <span className="bar-lbl">Critical</span>
                  </div>
                  <div className="bar-card high">
                    <span className="bar-val">{highCount}</span>
                    <span className="bar-lbl">High</span>
                  </div>
                  <div className="bar-card medium">
                    <span className="bar-val">{medCount}</span>
                    <span className="bar-lbl">Med</span>
                  </div>
                  <div className="bar-card low">
                    <span className="bar-val">{lowCount}</span>
                    <span className="bar-lbl">Low</span>
                  </div>
                </div>
              </div>
            )}

            {/* Violations feed container */}
            <div className="violations-feed-card card settings-card" style={{ flexGrow: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
              <h4 className="card-title">Infractions & Grounding Explanations</h4>

              <div className="violations-list" style={{ overflowY: "auto", flexGrow: 1, marginTop: "16px", display: "flex", flexDirection: "column", gap: "12px" }}>
                {auditStatus === "idle" && (
                  <div className="empty-state">Trigger compliance run to scan revision drawing against engineering manuals.</div>
                )}
                {auditStatus === "queued" || auditStatus === "auditing" ? (
                  <div className="empty-state">
                    <div className="loader spin-animation"></div>
                    <span style={{ marginTop: "12px" }}>Reasoning over draft dimensions...</span>
                  </div>
                ) : null}

                {auditStatus === "completed" && violations.length === 0 ? (
                  <div className="empty-state success">
                    <CheckCircle2 size={36} style={{ color: "#10b981" }} />
                    <span style={{ marginTop: "12px", color: "#10b981" }}>No compliance infractions found! Drawing is perfectly grounded.</span>
                  </div>
                ) : null}

                {auditStatus === "completed" && violations.map((v) => (
                  <div
                    key={v.id}
                    className={`violation-card-item ${v.severity} ${selectedViolation?.id === v.id ? "selected" : ""}`}
                    onClick={() => selectViolation(v)}
                  >
                    <div className="card-header-row">
                      <span className={`sev-badge ${v.severity}`}>{v.severity.toUpperCase()}</span>
                      <span className="clause-lbl">{v.standard_reference || "General"}</span>
                    </div>

                    <h5 className="violation-title">{v.category}</h5>
                    <p className="violation-desc">{v.description}</p>

                    <div className="recommendation-box">
                      <strong>AI Suggestion:</strong> {v.recommendation}
                    </div>

                    <div className="card-footer-row">
                      <span className="confidence-badge">Confidence: {(v.confidence * 100).toFixed(0)}%</span>
                      <span className="focus-action-btn">Focus on Drawing →</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </aside>
        </div>
      )}

      <style>{`
        .workspace-container {
          display: flex;
          width: 100vw;
          height: 100vh;
          background: var(--bg-dark);
          overflow: hidden;
          font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
          color: var(--text-primary);
        }

        .workspace-sidebar {
          height: 100%;
          background: var(--bg-sidebar);
          border-right: 1px solid var(--border-color);
          display: flex;
          flex-direction: column;
          flex-shrink: 0;
          transition: width 0.28s cubic-bezier(0.4, 0, 0.2, 1), box-shadow 0.28s ease;
          overflow: hidden;
          position: relative;
          z-index: 10;
        }

        .workspace-sidebar.hover-expanded {
          box-shadow: 4px 0 24px rgba(0, 0, 0, 0.12);
        }
        [data-theme="hc-dark"] .workspace-sidebar.hover-expanded {
          box-shadow: 4px 0 30px rgba(0, 0, 0, 0.5);
        }

        .sidebar-branding {
          display: flex;
          align-items: center;
          gap: 10px;
          padding: 16px 12px;
          border-bottom: 1px solid var(--border-color);
          min-height: 60px;
        }

        .brand-logo {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 36px;
          height: 36px;
          border-radius: 10px;
          background: var(--primary-glow);
          box-shadow: 0 2px 10px rgba(37, 99, 235, 0.25);
          flex-shrink: 0;
        }
        [data-theme="hc-dark"] .brand-logo {
          box-shadow: 0 2px 10px rgba(0, 229, 255, 0.2);
        }

        .brand-title {
          font-size: 1rem;
          font-weight: 700;
          color: var(--text-primary);
          margin: 0;
          line-height: 1.2;
        }

        .brand-badge {
          font-size: 0.65rem;
          font-weight: 800;
          color: var(--accent-cyan);
          letter-spacing: 0.05em;
          text-transform: uppercase;
        }

        .sidebar-nav {
          padding: 20px 12px;
          display: flex;
          flex-direction: column;
          gap: 4px;
          flex-grow: 1;
        }

        .nav-item {
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 10px 16px;
          background: transparent;
          border: none;
          color: var(--text-muted);
          font-size: 0.85rem;
          font-weight: 550;
          text-align: left;
          cursor: pointer;
          border-radius: 6px;
          transition: all 0.2s ease;
        }

        .nav-item:hover {
          color: var(--text-primary);
          background: var(--sidebar-item-hover);
        }

        .nav-item.active {
          color: var(--accent-cyan);
          background: rgba(37, 99, 235, 0.07);
          border: 1px solid rgba(37, 99, 235, 0.18);
          border-left: 3px solid var(--accent-cyan);
          padding-left: 13px;
        }
        [data-theme="hc-dark"] .nav-item.active {
          background: rgba(0, 229, 255, 0.06);
          border: 1px solid rgba(0, 229, 255, 0.15);
          border-left: 3px solid var(--accent-cyan);
        }
        [data-theme="hc-light"] .nav-item.active {
          background: rgba(37, 99, 235, 0.08);
          border: 1px solid rgba(37, 99, 235, 0.15);
          border-left: 3px solid var(--accent-cyan);
        }

        .sidebar-footer {
          padding: 20px 16px;
          border-top: 1px solid var(--border-color);
          display: flex;
          flex-direction: column;
          gap: 12px;
        }

        .user-profile {
          display: flex;
          align-items: center;
          gap: 10px;
          background: var(--bg-dark);
          padding: 10px 12px;
          border-radius: 6px;
          border: 1px solid var(--border-color);
        }

        .profile-details {
          display: flex;
          flex-direction: column;
        }

        .profile-name {
          font-size: 0.8rem;
          font-weight: 600;
          color: var(--text-primary);
        }

        .profile-role {
          font-size: 0.65rem;
          color: var(--text-muted);
        }

        .btn-logout {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 9px 12px;
          background: transparent;
          border: 1px solid var(--border-color);
          border-radius: 8px;
          color: #ef4444;
          font-size: 0.8rem;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.2s ease;
          justify-content: flex-start;
          overflow: hidden;
          white-space: nowrap;
        }

        .btn-logout:hover {
          background: rgba(239, 68, 68, 0.05);
          border-color: rgba(239, 68, 68, 0.2);
        }

        .viewport-standards-manager {
          flex-grow: 1;
          height: 100%;
          overflow-y: auto;
          background: var(--bg-dark);
          padding: 30px 0;
        }

        .workspace-main-viewport.padded {
          flex-grow: 1;
          height: 100%;
          overflow-y: auto;
          background: var(--bg-dark);
          padding: 30px 32px;
        }

        .dual-stage-layout {
          display: flex;
          flex-grow: 1;
          height: 100%;
          overflow: hidden;
        }

        .stage1-center-panel {
          flex-grow: 1;
          height: 100%;
          display: flex;
          flex-direction: column;
          padding: 20px;
          overflow: hidden;
          border-right: 1px solid var(--border-color);
        }

        .cad-viewer-container {
          flex-grow: 1;
          background: var(--bg-sidebar);
          border: 1px solid var(--border-color);
          border-radius: 12px;
          display: flex;
          flex-direction: column;
          overflow: hidden;
          min-height: 0;
          box-shadow: 0 2px 12px rgba(0, 0, 0, 0.04);
        }
        [data-theme="hc-dark"] .cad-viewer-container {
          box-shadow: 0 2px 12px rgba(0, 0, 0, 0.3);
        }

        .viewer-toolbar {
          display: flex;
          align-items: center;
          background: var(--bg-dark);
          border-bottom: 1px solid var(--border-color);
          padding: 8px 16px;
          gap: 12px;
        }

        .toolbar-group {
          display: flex;
          align-items: center;
          gap: 6px;
        }

        .toolbar-btn {
          background: transparent;
          border: 1px solid var(--border-color);
          color: var(--text-muted);
          padding: 6px;
          border-radius: 4px;
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
        }

        .toolbar-btn:hover {
          color: var(--text-primary);
          border-color: #52525b;
        }

        .toolbar-divider {
          width: 1px;
          height: 16px;
          background: var(--border-color);
        }

        .toolbar-label {
          font-size: 0.7rem;
          font-weight: 700;
          color: var(--text-muted);
          text-transform: uppercase;
        }

        .toolbar-toggle-btn {
          background: transparent;
          border: 1px solid var(--border-color);
          color: var(--text-muted);
          font-size: 0.75rem;
          padding: 4px 10px;
          border-radius: 4px;
          cursor: pointer;
        }

        .toolbar-toggle-btn.active {
          color: var(--accent-cyan);
          border-color: rgba(37, 99, 235, 0.3);
          background: rgba(37, 99, 235, 0.06);
        }
        [data-theme="hc-dark"] .toolbar-toggle-btn.active {
          border-color: rgba(0, 229, 255, 0.3);
          background: rgba(0, 229, 255, 0.06);
        }

        .diff-legend-item {
          display: flex;
          align-items: center;
          gap: 6px;
          font-size: 0.75rem;
          color: var(--text-muted);
        }

        .legend-dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
        }

        .legend-dot.unchanged { background: #10b981; }
        .legend-dot.added { background: #3b82f6; }
        .legend-dot.removed { background: #ef4444; }
        .legend-dot.modified { background: #f59e0b; }

        .split-viewports {
          display: grid;
          grid-template-columns: 1fr 1fr;
          flex-grow: 1;
          overflow: hidden;
        }

        .viewport-panel {
          display: flex;
          flex-direction: column;
          border-right: 1px solid var(--border-color);
        }

        .viewport-panel:last-child {
          border-right: none;
        }

        .viewport-label {
          font-size: 0.7rem;
          font-weight: 700;
          color: var(--text-primary);
          text-transform: uppercase;
          padding: 8px 12px;
          background: var(--bg-dark);
          border-bottom: 1px solid var(--border-color);
        }

        .cad-canvas-mock {
          flex-grow: 1;
          background: var(--bg-dark);
          position: relative;
          display: flex;
          align-items: center;
          justify-content: center;
        }

        .blueprint-overlay {
          width: 100%;
          height: 100%;
          position: relative;
          background-image: 
            radial-gradient(rgba(255,255,255,0.03) 1px, transparent 1px),
            radial-gradient(rgba(255,255,255,0.03) 1px, transparent 1px);
          background-size: 20px 20px;
          background-position: 0 0, 10px 10px;
        }

        .cad-element {
          position: absolute;
          background: #10b981; /* Default green unchanged */
        }

        .cad-element.unchanged-line {
          height: 1px;
          background: #10b981;
        }

        .cad-element.added-line {
          height: 1px;
          background: #3b82f6;
          box-shadow: 0 0 8px #3b82f6;
        }

        .cad-element.removed-line {
          height: 1px;
          background: #ef4444;
          box-shadow: 0 0 8px #ef4444;
          text-decoration: line-through;
        }

        .cad-element.circle {
          border: 1px solid #10b981;
          border-radius: 50%;
          background: transparent;
        }

        .cad-element.circle.modified {
          border-color: #f59e0b;
          box-shadow: 0 0 8px #f59e0b;
        }

        .cad-coordinate-axis {
          position: absolute;
          bottom: 12px;
          right: 12px;
          font-family: monospace;
          font-size: 0.7rem;
          color: #52525b;
        }

        .cad-highlight-reticle {
          position: absolute;
          width: 24px;
          height: 24px;
          border: 2px dashed #ef4444;
          border-radius: 50%;
          transform: translate(-50%, -50%);
          animation: pulse 1.5s infinite;
        }

        @keyframes pulse {
          0% { transform: translate(-50%, -50%) scale(1); opacity: 1; }
          100% { transform: translate(-50%, -50%) scale(1.8); opacity: 0; }
        }

        .canvas-empty {
          color: var(--text-muted);
          font-size: 0.85rem;
        }

        .stage2-right-panel {
          width: 400px;
          height: 100%;
          background: var(--bg-sidebar);
          display: flex;
          flex-direction: column;
          flex-shrink: 0;
          padding: 20px;
          overflow-y: auto;
          border-left: 1px solid var(--border-color);
          box-shadow: -4px 0 20px rgba(0, 0, 0, 0.04);
        }
        [data-theme="hc-dark"] .stage2-right-panel {
          box-shadow: -4px 0 20px rgba(0, 0, 0, 0.3);
        }

        .compliance-circle {
          width: 110px;
          height: 110px;
          border-radius: 50%;
          border: 4px solid #10b981;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          margin-top: 10px;
        }

        .compliance-val {
          font-size: 1.6rem;
          font-weight: 800;
          color: var(--text-primary);
          line-height: 1.1;
        }

        .compliance-lbl {
          font-size: 0.65rem;
          font-weight: 700;
          text-transform: uppercase;
          color: var(--text-muted);
        }

        .severity-bar-grid {
          display: grid;
          grid-template-columns: repeat(4, 1fr);
          gap: 10px;
          width: 100%;
          margin-top: 15px;
        }

        .bar-card {
          display: flex;
          flex-direction: column;
          align-items: center;
          background: var(--bg-dark);
          padding: 8px;
          border-radius: 6px;
          border: 1px solid var(--border-color);
        }

        .bar-val {
          font-size: 1.1rem;
          font-weight: 700;
        }

        .bar-lbl {
          font-size: 0.6rem;
          color: var(--text-muted);
          text-transform: uppercase;
        }

        .bar-card.critical { border-left: 3px solid #ef4444; }
        .bar-card.high { border-left: 3px solid #f97316; }
        .bar-card.medium { border-left: 3px solid #eab308; }
        .bar-card.low { border-left: 3px solid #3b82f6; }

        .violation-card-item {
          background: var(--bg-dark);
          border: 1px solid var(--border-color);
          border-left: 3px solid transparent;
          border-radius: 10px;
          padding: 14px;
          cursor: pointer;
          transition: all 0.22s cubic-bezier(0.4, 0, 0.2, 1);
        }

        .violation-card-item:hover {
          border-color: var(--border-color);
          border-left-color: var(--accent-cyan);
          transform: translateY(-2px);
          box-shadow: 0 6px 20px rgba(0, 0, 0, 0.12);
        }
        [data-theme="hc-dark"] .violation-card-item:hover {
          box-shadow: 0 6px 20px rgba(0, 0, 0, 0.4);
        }

        .violation-card-item.selected {
          border-color: var(--accent-cyan);
          border-left-color: var(--accent-cyan);
          box-shadow: 0 0 10px rgba(37, 99, 235, 0.18);
        }
        [data-theme="hc-dark"] .violation-card-item.selected {
          box-shadow: 0 0 12px rgba(0, 229, 255, 0.2);
        }

        .card-header-row {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 8px;
        }

        .sev-badge {
          font-size: 0.6rem;
          font-weight: 800;
          padding: 2px 6px;
          border-radius: 4px;
        }

        .sev-badge.critical { background: rgba(239, 68, 68, 0.15); color: #fca5a5; }
        .sev-badge.high { background: rgba(249, 73, 22, 0.15); color: #fed7aa; }
        .sev-badge.medium { background: rgba(234, 179, 8, 0.15); color: #fef08a; }
        .sev-badge.low { background: rgba(59, 130, 246, 0.15); color: #bfdbfe; }

        .clause-lbl {
          font-size: 0.7rem;
          font-family: monospace;
          color: var(--text-muted);
        }

        .violation-title {
          font-size: 0.85rem;
          font-weight: 700;
          color: var(--text-primary);
          margin: 0 0 6px 0;
        }

        .violation-desc {
          font-size: 0.75rem;
          color: var(--text-muted);
          margin: 0 0 10px 0;
          line-height: 1.4;
        }

        .recommendation-box {
          background: var(--bg-dark);
          border: 1px solid var(--border-color);
          padding: 8px 10px;
          border-radius: 4px;
          font-size: 0.7rem;
          color: var(--text-primary);
          line-height: 1.4;
          margin-bottom: 10px;
        }

        .card-footer-row {
          display: flex;
          justify-content: space-between;
          align-items: center;
          font-size: 0.65rem;
        }

        .confidence-badge {
          color: var(--text-muted);
        }

        .focus-action-btn {
          color: var(--accent-cyan);
          font-weight: 600;
          cursor: pointer;
          transition: opacity 0.2s ease;
        }
        .focus-action-btn:hover {
          opacity: 0.75;
        }

        .loader {
          border: 3px solid var(--border-color);
          border-top-color: var(--accent-cyan);
          border-radius: 50%;
          width: 24px;
          height: 24px;
        }

        /* ------------------------------------------------------------------------- */
        /* VERSION INGESTION STATION (STAGE 1 STYLING)                               */
        /* ------------------------------------------------------------------------- */
        .upload-station-card {
          border: 1px solid var(--border-color);
          background: var(--bg-card);
          padding: 12px 18px !important;
          margin-bottom: 12px !important;
        }

        .upload-station-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          border-bottom: 1px solid var(--border-color);
          padding-bottom: 6px;
        }

        .compatibility-badge-status {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 6px 12px;
          border-radius: 20px;
          font-size: 0.68rem;
          font-weight: 800;
          letter-spacing: 0.05em;
          text-transform: uppercase;
          background: var(--bg-dark);
          border: 1px solid var(--border-color);
          transition: all 0.3s ease;
        }

        .compatibility-badge-status.idle {
          color: #a1a1aa;
          border-color: #3f3f46;
        }

        .compatibility-badge-status.compatible {
          color: #10b981;
          background: rgba(16, 185, 129, 0.08);
          border-color: rgba(16, 185, 129, 0.25);
          box-shadow: 0 0 10px rgba(16, 185, 129, 0.1);
        }

        .compatibility-badge-status.mismatch {
          color: #f97316;
          background: rgba(249, 115, 22, 0.08);
          border-color: rgba(249, 115, 22, 0.25);
          animation: badge-pulse 2s infinite;
        }

        .compatibility-badge-status.unsupported {
          color: #ef4444;
          background: rgba(239, 68, 68, 0.08);
          border-color: rgba(239, 68, 68, 0.25);
        }

        .compatibility-indicator-dot {
          width: 6px;
          height: 6px;
          border-radius: 50%;
          background: currentColor;
        }

        @keyframes badge-pulse {
          0% { opacity: 0.85; }
          50% { opacity: 1; transform: scale(1.02); }
          100% { opacity: 0.85; }
        }

        .upload-zone-group {
          display: flex;
          flex-direction: column;
          gap: 8px;
        }

        .upload-zone-title-label {
          display: flex;
          justify-content: space-between;
          align-items: baseline;
        }

        .upload-zone-subtitle-desc {
          font-size: 0.65rem;
          color: var(--text-muted, #71717a);
          font-weight: normal;
        }        .upload-dropzone-container {
          position: relative;
          min-height: 85px;
          border: 1.5px dashed var(--border-color);
          background: var(--bg-dark);
          border-radius: 10px;
          transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          padding: 14px 16px;
          box-sizing: border-box;
          overflow: hidden;
        }

        .upload-zone-group.old .upload-dropzone-container.idle:hover,
        .upload-zone-group.old .upload-dropzone-container.failed:hover {
          border-color: var(--accent-cyan);
          background: rgba(37, 99, 235, 0.02);
          box-shadow: 0 4px 15px rgba(37, 99, 235, 0.04);
        }
        [data-theme="hc-dark"] .upload-zone-group.old .upload-dropzone-container.idle:hover,
        [data-theme="hc-dark"] .upload-zone-group.old .upload-dropzone-container.failed:hover {
          border-color: var(--accent-cyan);
          background: rgba(0, 229, 255, 0.03);
          box-shadow: 0 4px 15px rgba(0, 229, 255, 0.08);
        }

        .upload-zone-group.new .upload-dropzone-container.idle:hover,
        .upload-zone-group.new .upload-dropzone-container.failed:hover {
          border-color: #8b5cf6;
          background: rgba(139, 92, 246, 0.02);
          box-shadow: 0 4px 15px rgba(139, 92, 246, 0.04);
        }
        [data-theme="hc-dark"] .upload-zone-group.new .upload-dropzone-container.idle:hover,
        [data-theme="hc-dark"] .upload-zone-group.new .upload-dropzone-container.failed:hover {
          border-color: #a78bfa;
          background: rgba(167, 139, 250, 0.03);
          box-shadow: 0 4px 15px rgba(167, 139, 250, 0.08);
        }

        .upload-zone-group.old .upload-dropzone-container.dragging {
          border-color: var(--accent-cyan) !important;
          background: rgba(37, 99, 235, 0.06) !important;
          box-shadow: 0 0 15px rgba(37, 99, 235, 0.12) !important;
        }
        [data-theme="hc-dark"] .upload-zone-group.old .upload-dropzone-container.dragging {
          background: rgba(0, 229, 255, 0.08) !important;
          box-shadow: 0 0 15px rgba(0, 229, 255, 0.2) !important;
        }

        .upload-zone-group.new .upload-dropzone-container.dragging {
          border-color: #8b5cf6 !important;
          background: rgba(139, 92, 246, 0.06) !important;
          box-shadow: 0 0 15px rgba(139, 92, 246, 0.12) !important;
        }
        [data-theme="hc-dark"] .upload-zone-group.new .upload-dropzone-container.dragging {
          border-color: #a78bfa !important;
          background: rgba(167, 139, 250, 0.08) !important;
          box-shadow: 0 0 15px rgba(167, 139, 250, 0.2) !important;
        }

        .dropzone-idle-view {
          display: flex;
          flex-direction: column;
          align-items: center;
          text-align: center;
        }

        .dropzone-icon-circle {
          width: 26px;
          height: 26px;
          border-radius: 50%;
          background: var(--bg-dark);
          border: 1px solid var(--border-color);
          display: flex;
          align-items: center;
          justify-content: center;
          color: var(--text-muted);
          transition: all 0.25s ease;
        }

        .upload-dropzone-container:hover .dropzone-icon-circle {
          transform: translateY(-2px);
          border-color: var(--accent-cyan);
          color: var(--accent-cyan);
          background: rgba(37, 99, 235, 0.06);
        }
        [data-theme="hc-dark"] .upload-dropzone-container:hover .dropzone-icon-circle {
          background: rgba(0, 229, 255, 0.08);
        }

        .dropzone-main-text {
          font-size: 0.8rem;
          font-weight: 550;
          color: var(--text-primary, #f4f4f5);
          margin: 0 0 2px 0;
        }

        .browse-link {
          color: var(--accent-cyan);
          text-decoration: underline;
          font-weight: 700;
        }

        .dropzone-sub-text {
          font-size: 0.68rem;
          color: var(--text-muted, #71717a);
          margin: 0;
        }

        .supported-formats-badges {
          display: flex;
          gap: 6px;
          margin-top: 4px;
        }

        .format-badge {
          font-size: 0.58rem;
          font-weight: 800;
          padding: 2px 6px;
          border-radius: 4px;
          letter-spacing: 0.03em;
        }

        .format-badge.dwg { background: rgba(249, 115, 22, 0.1); color: #fdba74; border: 1px solid rgba(249, 115, 22, 0.2); }
        .format-badge.dxf { background: rgba(20, 184, 166, 0.1); color: #99f6e4; border: 1px solid rgba(20, 184, 166, 0.2); }
        .format-badge.pdf { background: rgba(239, 68, 68, 0.1); color: #fca5a5; border: 1px solid rgba(239, 68, 68, 0.2); }

        /* Active Processing View */
        .dropzone-active-view {
          width: 100%;
          display: flex;
          flex-direction: column;
          align-items: center;
          text-align: center;
          padding: 10px;
        }

        .pulsing-loader-wrapper {
          width: 32px;
          height: 32px;
          border-radius: 50%;
          background: var(--bg-dark);
          border: 1px solid var(--border-color);
          display: flex;
          align-items: center;
          justify-content: center;
          margin-bottom: 10px;
          color: var(--accent-cyan);
          animation: pulse-glow 1.5s infinite;
        }

        @keyframes pulse-glow {
          0% { box-shadow: 0 0 0 0 rgba(37, 99, 235, 0.25); }
          70% { box-shadow: 0 0 0 8px rgba(37, 99, 235, 0); }
          100% { box-shadow: 0 0 0 0 rgba(37, 99, 235, 0); }
        }
        [data-theme="hc-dark"] .pulsing-loader-wrapper {
          animation-name: pulse-glow-dark;
        }
        @keyframes pulse-glow-dark {
          0% { box-shadow: 0 0 0 0 rgba(0, 229, 255, 0.25); }
          70% { box-shadow: 0 0 0 8px rgba(0, 229, 255, 0); }
          100% { box-shadow: 0 0 0 0 rgba(0, 229, 255, 0); }
        }

        .active-details-wrapper {
          display: flex;
          flex-direction: column;
          margin-bottom: 12px;
        }

        .active-status-title {
          font-size: 0.78rem;
          font-weight: 700;
          color: var(--text-primary, #f4f4f5);
        }

        .active-filename-sub {
          font-size: 0.65rem;
          color: var(--text-muted, #71717a);
          margin-top: 2px;
          max-width: 250px;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        .dropzone-progress-bar-bg {
          width: 80%;
          max-width: 240px;
          height: 4px;
          background: var(--border-color);
          border-radius: 2px;
          overflow: hidden;
        }

        .dropzone-progress-bar-fill {
          height: 100%;
          background: linear-gradient(90deg, var(--accent-cyan), #818cf8);
          border-radius: 2px;
          transition: width 0.2s ease;
        }

        /* Completed Ingestion View */
        .dropzone-completed-view {
          width: 100%;
          height: 100%;
          display: flex;
          flex-direction: column;
          justify-content: space-between;
        }

        .completed-card-header {
          display: flex;
          justify-content: space-between;
          align-items: flex-start;
          width: 100%;
        }

        .file-info-col {
          display: flex;
          align-items: center;
          gap: 10px;
          overflow: hidden;
        }

        .file-format-badge {
          font-size: 0.7rem;
          font-weight: 800;
          padding: 6px 8px;
          border-radius: 6px;
          letter-spacing: 0.02em;
        }

        .file-format-badge.badge-dwg { background: rgba(249, 115, 22, 0.15); color: #f97316; border: 1px solid rgba(249, 115, 22, 0.3); }
        .file-format-badge.badge-dxf { background: rgba(20, 184, 166, 0.15); color: #14b8a6; border: 1px solid rgba(20, 184, 166, 0.3); }
        .file-format-badge.badge-pdf { background: rgba(239, 68, 68, 0.15); color: #ef4444; border: 1px solid rgba(239, 68, 68, 0.3); }

        .completed-metadata {
          display: flex;
          flex-direction: column;
          overflow: hidden;
        }

        .completed-filename {
          font-size: 0.8rem;
          font-weight: 700;
          color: var(--text-primary, #f4f4f5);
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
          max-width: 180px;
        }

        .completed-filesize {
          font-size: 0.65rem;
          color: var(--text-muted, #71717a);
        }

        .btn-clear-upload {
          background: transparent;
          border: 1px solid var(--border-color, #27272a);
          color: var(--text-muted, #71717a);
          padding: 6px;
          border-radius: 6px;
          cursor: pointer;
          transition: all 0.2s ease;
          display: flex;
          align-items: center;
          justify-content: center;
        }

        .btn-clear-upload:hover {
          color: #ef4444;
          background: rgba(239, 68, 68, 0.05);
          border-color: rgba(239, 68, 68, 0.2);
          transform: scale(1.05);
        }

        .drawing-entities-stats-grid {
          display: grid;
          grid-template-columns: repeat(4, 1fr);
          gap: 4px;
          background: var(--bg-dark);
          border: 1px solid var(--border-color);
          padding: 4px 8px;
          border-radius: 6px;
          margin-top: 6px;
        }

        .stat-unit {
          display: flex;
          flex-direction: column;
          align-items: center;
        }

        .stat-unit-val {
          font-size: 0.72rem;
          font-weight: 800;
          color: var(--text-primary, #f4f4f5);
          font-family: monospace;
        }

        .stat-unit-lbl {
          font-size: 0.55rem;
          color: var(--text-muted, #71717a);
          text-transform: uppercase;
          margin-top: 1px;
        }

        .completed-status-badge {
          display: inline-flex;
          align-items: center;
          font-size: 0.62rem;
          font-weight: 700;
          color: #10b981;
          margin-top: 4px;
          background: rgba(16, 185, 129, 0.05);
          padding: 2px 8px;
          border-radius: 4px;
          border: 1px solid rgba(16, 185, 129, 0.15);
          align-self: flex-start;
        }

        /* Ingestion Failure View */
        .dropzone-failed-view {
          display: flex;
          flex-direction: column;
          align-items: center;
          text-align: center;
          padding: 4px;
        }

        .failed-icon-circle {
          width: 32px;
          height: 32px;
          border-radius: 50%;
          background: rgba(239, 68, 68, 0.08);
          border: 1px solid rgba(239, 68, 68, 0.2);
          display: flex;
          align-items: center;
          justify-content: center;
          margin-bottom: 6px;
          color: #ef4444;
        }

        .failed-status-title {
          font-size: 0.76rem;
          font-weight: 700;
          color: #ef4444;
        }

        .failed-error-desc {
          font-size: 0.66rem;
          color: var(--text-muted, #71717a);
          margin: 3px 0 8px 0;
          max-width: 250px;
          line-height: 1.3;
        }

        .retry-link-label {
          font-size: 0.68rem;
          color: var(--accent-cyan);
          text-decoration: underline;
          cursor: pointer;
          font-weight: 600;
          transition: opacity 0.2s ease;
        }
        .retry-link-label:hover {
          opacity: 0.75;
        }

        .spin-animation {
          animation: spin-icon-anim 2s linear infinite;
        }

        @keyframes spin-icon-anim {
          0% { transform: rotate(0deg); }
          100% { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
};
