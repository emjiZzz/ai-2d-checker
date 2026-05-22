import React, { useState, useEffect } from "react";
import { useWorkspaceStore, DrawingItem } from "../../stores/workspaceStore";
import { useConnectionStore } from "../../stores/connectionStore";
import { DrawingCanvas } from "../../components/review/DrawingCanvas";
import { useReviewStore } from "../../stores/reviewStore";
import { useAuthStore } from "../../stores/authStore";
import {
  CheckCircle2,
  Play,
  Sparkles,
  ZoomIn,
  ZoomOut,
  Maximize,
  Compass,
  Loader,
  Upload,
  Trash2,
  AlertTriangle,
  Bookmark,
  History,
  Layers,
  Settings as SettingsIcon,
  ChevronRight,
  ChevronLeft
} from "lucide-react";

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
  side, uploadState, progress, fileName, error,
  uploadDrawingFile,
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
      e.target.value = "";
    }
  };

  const triggerFileInput = () => fileInputRef.current?.click();
  const canInteract = uploadState === "idle" || uploadState === "failed";

  return (
    <div
      className={`upload-dropzone-container ${side} ${uploadState} ${isDragActive ? "dragging" : ""}`}
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
        <div className="dropzone-idle-view">
          <div className="dropzone-icon-circle">
            <Upload size={14} className="dropzone-upload-icon" />
          </div>
          <div className="dropzone-text-group">
            <p className="dropzone-main-text">
              Drag & drop or <span className="browse-link">browse</span>
            </p>
            <p className="dropzone-sub-text">
              DWG, DXF, PDF (max. 50MB)
            </p>
          </div>
        </div>
      )}

      {(uploadState === "validating" || uploadState === "uploading" || uploadState === "processing") && (
        <div className="dropzone-active-view">
          <div className="pulsing-loader-wrapper">
            <Loader size={14} className="loader-spin-icon spin-animation" />
          </div>
          <div className="active-details-wrapper">
            <span className="active-status-title">
              {uploadState === "validating" && "Scanning signature..."}
              {uploadState === "uploading" && `Uploading... ${progress}%`}
              {uploadState === "processing" && "Ingesting CAD layout..."}
            </span>
            <span className="active-filename-sub">{fileName}</span>
          </div>
          <div className="dropzone-progress-bar-bg">
            <div className="dropzone-progress-bar-fill" style={{ width: `${progress}%` }}></div>
          </div>
        </div>
      )}

      {uploadState === "failed" && (
        <div className="dropzone-failed-view" onClick={(e) => { e.stopPropagation(); triggerFileInput(); }}>
          <div className="failed-icon-circle">
            <AlertTriangle size={14} className="dropzone-error-icon" />
          </div>
          <div className="failed-text-group">
            <span className="failed-status-title">Ingestion Failure</span>
            <p className="failed-error-desc">{error || "Security/validation rejection."}</p>
          </div>
          <span className="retry-link-label">Retry browse</span>
        </div>
      )}
    </div>
  );
};

export const AuditWorkspace: React.FC = () => {
  const backendUrl = useConnectionStore((s) => s.backendUrl);
  const apiToken = useConnectionStore((s) => s.apiToken);

  // Selected workspace navigation sub-view
  const [currentNav, setCurrentNav] = useState<"workspace" | "standards" | "history" | "settings">("workspace");
  const [isRightPanelCollapsed, setIsRightPanelCollapsed] = useState(false);
  // Local drawing catalog for selections
  const [drawings, setDrawings] = useState<DrawingItem[]>([]);

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
          // No longer assigning standards here
        } else {
          // No longer assigning mock standards here
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
    auditStatus,
    complianceScore,
    violations,
    selectedViolation,
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

  // Connect to reviewStore for synchronized viewport control
  const {
    viewport: reviewViewport,
    setViewport: setReviewViewport,
    isLaserSyncEnabled,
    toggleLaserSync,
    isOverlayModeEnabled,
    toggleOverlayMode
  } = useReviewStore();

  // Auth: read current user role to enforce access gates
  const user = useAuthStore((s) => s.user);
  const isAdmin = user?.role === "admin";

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

    // Use ResizeObserver for instant container-driven size updates
    const observer = new ResizeObserver(() => {
      // Use requestAnimationFrame to avoid "ResizeObserver loop limit exceeded" warnings
      window.requestAnimationFrame(() => {
        handleResize();
      });
    });

    if (containerRefOld.current) {
      observer.observe(containerRefOld.current);
    }
    if (containerRefNew.current) {
      observer.observe(containerRefNew.current);
    }

    // Call initially to ensure correct dimensions are set immediately
    handleResize();

    return () => {
      observer.disconnect();
    };
  }, [oldDrawing, newDrawing, currentNav, isRightPanelCollapsed]);

  const handleAuditTrigger = async () => {
    if (!newDrawing || !selectedClient) return;
    await runAudit(selectedClient);
  };

  const criticalCount = violations.filter((v) => v.severity === "critical").length;
  const highCount = violations.filter((v) => v.severity === "high").length;
  const medCount = violations.filter((v) => v.severity === "medium").length;
  const lowCount = violations.filter((v) => v.severity === "low").length;

  // Calculate entity counts for delta scanner
  const getEntitySum = (drawing: any) => {
    if (!drawing || !drawing.entity_counts) return 0;
    return Object.values(drawing.entity_counts).reduce((sum: number, count: any) => sum + (Number(count) || 0), 0);
  };
  const oldEntityCount = getEntitySum(oldDrawing);
  const newEntityCount = getEntitySum(newDrawing);
  const entityDelta = newEntityCount - oldEntityCount;

  // Coordinate Shift / Scale Mismatch Diagnostics
  let hasAlignmentDisparity = false;
  if (oldDrawing?.metadata?.render_bounds && newDrawing?.metadata?.render_bounds) {
    const [oldXmin, oldYmin, oldXmax, oldYmax] = oldDrawing.metadata.render_bounds;
    const [newXmin, newYmin, newXmax, newYmax] = newDrawing.metadata.render_bounds;

    const oldW = oldXmax - oldXmin;
    const oldH = oldYmax - oldYmin;
    const newW = newXmax - newXmin;
    const newH = newYmax - newYmin;

    const oldCx = (oldXmin + oldXmax) / 2;
    const oldCy = (oldYmin + oldYmax) / 2;
    const newCx = (newXmin + newXmax) / 2;
    const newCy = (newYmin + newYmax) / 2;

    const dimMismatch = Math.abs(oldW - newW) / Math.max(oldW, 1) > 0.1 || Math.abs(oldH - newH) / Math.max(oldH, 1) > 0.1;
    const centerMismatch = Math.abs(oldCx - newCx) / Math.max(oldW, 1) > 0.1 || Math.abs(oldCy - newCy) / Math.max(oldH, 1) > 0.1;

    if (dimMismatch || centerMismatch) {
      hasAlignmentDisparity = true;
    }
  }

  // uploadZoneProps was removed

  return (
    <div className="workspace-container">
      {/* 1. LEFT SIDEBAR (ENGINEERING NAVIGATION) */}
      <aside
        className="workspace-sidebar"
        style={{ width: '60px', flexShrink: 0, display: 'flex', flexDirection: 'column', background: 'var(--bg-card)', borderRight: '1px solid var(--border-color)', zIndex: 10 }}
      >
        {/* ── NAV ITEMS ── */}
        <nav className="sidebar-nav" style={{ padding: '12px 8px', display: 'flex', flexDirection: 'column', gap: '8px', flexGrow: 1 }}>
          {([
            { key: 'workspace', icon: <Compass size={22} />, label: 'Audit Workspace' },
            // Standards Manuals: admin-only — completely hidden from regular users
            ...(isAdmin ? [{ key: 'standards' as const, icon: <Bookmark size={22} />, label: 'Standards Manuals' }] : []),
            { key: 'history', icon: <History size={22} />, label: 'Drawing History' },
            { key: 'settings', icon: <SettingsIcon size={22} />, label: 'Audit Settings' },
          ] as const).map(({ key, icon, label }) => (
            <button
              key={key}
              className={`nav-item ${currentNav === key ? 'active' : ''}`}
              onClick={() => setCurrentNav(key)}
              data-tooltip={label}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                width: '44px',
                height: '44px',
                margin: '0 auto',
                borderRadius: '8px',
                border: 'none',
                background: currentNav === key ? 'rgba(128, 128, 128, 0.15)' : 'transparent',
                color: currentNav === key ? 'var(--text-primary)' : 'var(--text-muted)',
                cursor: 'pointer',
                transition: 'all 0.2s ease',
              }}
              onMouseEnter={(e) => {
                if (currentNav !== key) {
                  e.currentTarget.style.color = 'var(--text-primary)';
                  e.currentTarget.style.background = 'rgba(128, 128, 128, 0.08)';
                }
              }}
              onMouseLeave={(e) => {
                if (currentNav !== key) {
                  e.currentTarget.style.color = 'var(--text-muted)';
                  e.currentTarget.style.background = 'transparent';
                }
              }}
            >
              {icon}
            </button>
          ))}
        </nav>
      </aside>

      {/* 2. DYNAMIC WORKSPACE PORT */}
      {/* Standards Manuals — admin-only panel */}
      {currentNav === "standards" && isAdmin && (
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
            <div className="card settings-card upload-station-card" style={{ marginBottom: "12px", padding: "10px 16px" }}>
              <div style={{ display: "flex", flexDirection: "column", gap: "8px", width: "100%" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", width: "100%", gap: "16px", flexWrap: "wrap" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "12px", flexWrap: "wrap" }}>
                    <h3 className="card-title" style={{ margin: 0, fontSize: "0.85rem", borderLeft: "3px solid var(--accent-cyan)", paddingLeft: "8px" }}>
                      Stage 1: Version Ingestion
                    </h3>
                    <div className={`compatibility-badge-status ${compatibilityStatus.toLowerCase()}`} style={{ padding: "3px 8px", fontSize: "0.62rem" }}>
                      <span className="compatibility-indicator-dot"></span>
                      <span className="compatibility-text">
                        {compatibilityStatus === "Idle" && "Awaiting Pair Ingestion"}
                        {compatibilityStatus === "Compatible" && `COMPATIBLE: ${oldDrawing?.file_name.split(".").pop()?.toUpperCase()} ↔ ${newDrawing?.file_name.split(".").pop()?.toUpperCase()}`}
                        {compatibilityStatus === "Mismatch" && "FORMAT MISMATCH"}
                        {compatibilityStatus === "Unsupported" && "UNSUPPORTED EXTENSION"}
                      </span>
                    </div>

                    {/* File Format Badges */}
                    {oldDrawing && (
                      <span className="format-badge-pill ref-format">
                        REF: {oldDrawing.file_name.split(".").pop()?.toUpperCase()}
                      </span>
                    )}
                    {newDrawing && (
                      <span className="format-badge-pill rev-format">
                        REV: {newDrawing.file_name.split(".").pop()?.toUpperCase()}
                      </span>
                    )}

                    {/* Delta Complexity Pill */}
                    {oldDrawing && newDrawing && (
                      <span className="complexity-delta-pill">
                        REF: {oldEntityCount.toLocaleString()} ↔ REV: {newEntityCount.toLocaleString()} Entities ({entityDelta >= 0 ? `+${entityDelta.toLocaleString()}` : entityDelta.toLocaleString()})
                      </span>
                    )}
                  </div>

                  {/* Laser Sync Controller Switch */}
                  <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                    <span style={{ fontSize: "0.7rem", color: "var(--text-muted)", fontWeight: "500" }}>Laser Sync:</span>
                    <button
                      onClick={toggleLaserSync}
                      className={`laser-sync-toggle-switch ${isLaserSyncEnabled ? "active" : "inactive"}`}
                      title={isLaserSyncEnabled ? "Disable Synchronized Crosshairs" : "Enable Synchronized Crosshairs"}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        position: "relative",
                        width: "36px",
                        height: "18px",
                        borderRadius: "10px",
                        background: isLaserSyncEnabled ? "rgba(0, 255, 204, 0.15)" : "rgba(255, 255, 255, 0.05)",
                        border: isLaserSyncEnabled ? "1px solid rgba(0, 255, 204, 0.4)" : "1px solid rgba(255, 255, 255, 0.1)",
                        cursor: "pointer",
                        transition: "all 0.2s cubic-bezier(0.4, 0, 0.2, 1)",
                        padding: 0,
                        outline: "none"
                      }}
                    >
                      <span
                        className="laser-sync-dot"
                        style={{
                          display: "block",
                          width: "10px",
                          height: "10px",
                          borderRadius: "50%",
                          background: isLaserSyncEnabled ? "#00ffcc" : "#a1a1aa",
                          boxShadow: isLaserSyncEnabled ? "0 0 8px #00ffcc" : "none",
                          position: "absolute",
                          left: isLaserSyncEnabled ? "22px" : "4px",
                          transition: "all 0.2s cubic-bezier(0.4, 0, 0.2, 1)"
                        }}
                      />
                    </button>
                  </div>
                </div>

                {/* Bounds Scanner Warning */}
                {hasAlignmentDisparity && (
                  <div className="alignment-mismatch-banner">
                    <span className="warning-icon">⚠️</span>
                    <span className="warning-text">Alignment warning: Scale or coordinate shift detected between viewports (bounds mismatch &gt; 10%). Direct alignment mapping may require offset adjustment.</span>
                  </div>
                )}
              </div>
            </div>

            <div className="cad-viewer-container">
              {/* Toolbar */}
              <div className="viewer-toolbar">
                <div className="toolbar-group">
                  <button
                    className="toolbar-btn"
                    onClick={() => setReviewViewport({ ...reviewViewport, scale: Math.min(25, reviewViewport.scale * 1.25) })}
                    title="Zoom In"
                  >
                    <ZoomIn size={14} />
                  </button>
                  <button
                    className="toolbar-btn"
                    onClick={() => setReviewViewport({ ...reviewViewport, scale: Math.max(0.1, reviewViewport.scale / 1.25) })}
                    title="Zoom Out"
                  >
                    <ZoomOut size={14} />
                  </button>
                  <button
                    className="toolbar-btn"
                    onClick={() => setReviewViewport({ x: 0, y: 0, scale: 1 })}
                    title="Reset Viewport"
                  >
                    <Maximize size={14} />
                  </button>
                </div>

                <div className="toolbar-divider"></div>

                {/* Visual Diff Overlay Toggle — only when both drawings loaded */}
                {oldDrawing && newDrawing && (
                  <>
                    <button
                      className={`toolbar-btn overlay-toggle-btn ${isOverlayModeEnabled ? "active" : ""}`}
                      onClick={toggleOverlayMode}
                      title={isOverlayModeEnabled ? "Disable Visual Diff Overlay" : "Enable Visual Diff Overlay (Red/Green blend)"}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "5px",
                        padding: "4px 10px",
                        fontSize: "0.65rem",
                        fontWeight: 600,
                        letterSpacing: "0.03em",
                        background: isOverlayModeEnabled ? "rgba(244,63,94,0.12)" : undefined,
                        border: isOverlayModeEnabled ? "1px solid rgba(244,63,94,0.5)" : undefined,
                        color: isOverlayModeEnabled ? "#f43f5e" : undefined,
                        boxShadow: isOverlayModeEnabled ? "0 0 10px rgba(244,63,94,0.25)" : undefined,
                        borderRadius: "6px",
                        transition: "all 0.2s cubic-bezier(0.4,0,0.2,1)",
                        whiteSpace: "nowrap"
                      }}
                    >
                      <Layers size={12} />
                      DIFF OVERLAY
                    </button>
                    <div className="toolbar-divider"></div>
                  </>
                )}

                <div className="toolbar-group" style={{ marginLeft: "auto" }}>
                  {isOverlayModeEnabled ? (
                    <>
                      <span className="diff-legend-item" style={{ color: "#f43f5e", display: "flex", alignItems: "center", gap: "5px", fontSize: "0.65rem", fontWeight: 500 }}>
                        <span style={{ width: "8px", height: "8px", borderRadius: "50%", backgroundColor: "#f43f5e", display: "inline-block", boxShadow: "0 0 6px #f43f5e" }} />
                        Reference (V1)
                      </span>
                      <span className="diff-legend-item" style={{ color: "#10b981", display: "flex", alignItems: "center", gap: "5px", fontSize: "0.65rem", fontWeight: 500 }}>
                        <span style={{ width: "8px", height: "8px", borderRadius: "50%", backgroundColor: "#10b981", display: "inline-block", boxShadow: "0 0 6px #10b981" }} />
                        Revision (V2)
                      </span>
                      <span className="diff-legend-item" style={{ color: "#eab308", display: "flex", alignItems: "center", gap: "5px", fontSize: "0.65rem", fontWeight: 500 }}>
                        <span style={{ width: "8px", height: "8px", borderRadius: "50%", backgroundColor: "#eab308", display: "inline-block", boxShadow: "0 0 6px #eab308" }} />
                        Overlapping / Unchanged
                      </span>
                    </>
                  ) : (
                    <>
                      <span className="diff-legend-item unchanged"><span className="legend-dot unchanged"></span>Unchanged</span>
                      <span className="diff-legend-item added"><span className="legend-dot added"></span>Added</span>
                      <span className="diff-legend-item removed"><span className="legend-dot removed"></span>Removed</span>
                      <span className="diff-legend-item modified"><span className="legend-dot modified"></span>Modified</span>
                    </>
                  )}
                </div>
              </div>

              {/* Viewport Panels */}
              {isOverlayModeEnabled && oldDrawing && newDrawing ? (
                // ── VISUAL DIFF OVERLAY MODE: Single full-width fused canvas ──
                <div className="split-viewports" data-overlay="true">
                  <div className="viewport-panel">
                    <div className="viewport-header" style={{ background: "linear-gradient(90deg, rgba(244,63,94,0.08) 0%, rgba(16,185,129,0.08) 100%)", borderBottom: "1px solid rgba(244,63,94,0.2)" }}>
                      <div className="viewport-label" style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                        <span style={{ color: "#f43f5e", fontWeight: 700, fontSize: "0.68rem" }}>V1</span>
                        <span style={{ color: "var(--text-muted)", fontSize: "0.6rem" }}>⊕</span>
                        <span style={{ color: "#10b981", fontWeight: 700, fontSize: "0.68rem" }}>V2</span>
                        <span style={{ color: "var(--text-muted)", fontSize: "0.68rem", marginLeft: "4px" }}>Visual Diff Overlay</span>
                      </div>
                      <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                        <div className="ingested-file-pill ref" style={{ borderColor: "rgba(244,63,94,0.4)" }}>
                          <span className="pill-label" style={{ color: "#f43f5e" }}>REF:</span>
                          <span className="pill-filename" title={oldDrawing.file_name}>{oldDrawing.file_name}</span>
                        </div>
                        <div className="ingested-file-pill rev" style={{ borderColor: "rgba(16,185,129,0.4)" }}>
                          <span className="pill-label" style={{ color: "#10b981" }}>REV:</span>
                          <span className="pill-filename" title={newDrawing.file_name}>{newDrawing.file_name}</span>
                        </div>
                      </div>
                    </div>
                    <div className="cad-canvas-mock" ref={containerRefOld}>
                      <div style={{ position: "absolute", top: 0, left: 0, width: "100%", height: "100%", overflow: "hidden" }}>
                        <DrawingCanvas
                          layers={oldLayers}
                          width={oldSize.width}
                          height={oldSize.height}
                          drawing={oldDrawing}
                        />
                      </div>
                    </div>
                  </div>
                </div>
              ) : (
                // ── STANDARD SPLIT-VIEW MODE ──
                <div className="split-viewports">
                  {/* Left Viewport (Old) */}
                  <div className="viewport-panel">
                    <div className="viewport-header">
                      <div className="viewport-label">Reference CAD (Old)</div>
                      {oldDrawing && (
                        <div className="ingested-file-pill ref">
                          <span className="pill-label">REF:</span>
                          <span className="pill-filename" title={oldDrawing.file_name}>
                            {oldDrawing.file_name}
                          </span>
                          <button className="pill-clear-btn" onClick={() => clearUpload("old")} title="Remove reference drawing">
                            <Trash2 size={10} />
                          </button>
                        </div>
                      )}
                    </div>
                    <div className="cad-canvas-mock" ref={containerRefOld}>
                      {oldDrawing ? (
                        <div style={{ position: "absolute", top: 0, left: 0, width: "100%", height: "100%", overflow: "hidden" }}>
                          <DrawingCanvas
                            layers={oldLayers}
                            width={oldSize.width}
                            height={oldSize.height}
                            drawing={oldDrawing}
                          />
                        </div>
                      ) : (
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
                      )}
                    </div>
                  </div>

                  {/* Right Viewport (New) */}
                  <div className="viewport-panel">
                    <div className="viewport-header">
                      <div className="viewport-label">Revision CAD (New)</div>
                      {newDrawing && (
                        <div className="ingested-file-pill rev">
                          <span className="pill-label">REV:</span>
                          <span className="pill-filename" title={newDrawing.file_name}>
                            {newDrawing.file_name}
                          </span>
                          <button className="pill-clear-btn" onClick={() => clearUpload("new")} title="Remove revision drawing">
                            <Trash2 size={10} />
                          </button>
                        </div>
                      )}
                    </div>
                    <div className="cad-canvas-mock" ref={containerRefNew}>
                      {newDrawing ? (
                        <div style={{ position: "absolute", top: 0, left: 0, width: "100%", height: "100%", overflow: "hidden" }}>
                          <DrawingCanvas
                            layers={newLayers}
                            width={newSize.width}
                            height={newSize.height}
                            drawing={newDrawing}
                          />
                        </div>
                      ) : (
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
                      )}
                    </div>
                  </div>
                </div>
              )}
            </div>
          </main>

          {/* RIGHT VIEWPORT (STAGE 2: AI COMPLIANCE AUDITOR) */}
          <aside className={`stage2-right-panel ${isRightPanelCollapsed ? "collapsed" : ""}`}>
            <button
              className="panel-collapse-btn"
              onClick={() => setIsRightPanelCollapsed(!isRightPanelCollapsed)}
              title={isRightPanelCollapsed ? "Expand Stage 2 Panel" : "Collapse Stage 2 Panel"}
            >
              {isRightPanelCollapsed ? <ChevronLeft size={16} /> : <ChevronRight size={16} />}
            </button>
            <div className="panel-content-wrapper">
              {/* Top Auditor Launch controller */}
              <div className="card settings-card" style={{ marginBottom: "20px" }}>
                <h3 className="card-title" style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                  <Sparkles size={16} style={{ color: "var(--accent-cyan)" }} />
                  Stage 2 AI Compliance Auditor
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
                  style={{
                    width: "100%",
                    marginTop: "16px",
                    display: "flex",
                    alignItems: "center",
                    gap: "8px",
                    justifyContent: "center",
                    padding: "10px 16px",
                    whiteSpace: "nowrap"
                  }}
                >
                  <Play size={14} fill="currentColor" />
                  <span>
                    {auditStatus === "queued" || auditStatus === "auditing" ? "Running AI Auditing Pipeline..." : "Execute Compliance Audit"}
                  </span>
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
            </div>
          </aside>
        </div>
      )}

      <style>{`
        .workspace-container {
          display: flex;
          width: 100vw;
          height: calc(100vh - 44px); /* Account for AppHeader height */
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
          overflow: visible;
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
          position: relative;
        }

        .nav-item::after {
          content: attr(data-tooltip);
          position: absolute;
          left: 100%;
          top: 50%;
          transform: translateY(-50%);
          margin-left: 8px;
          padding: 6px 10px;
          background: rgba(24, 24, 27, 0.95);
          border: 1px solid var(--border-color);
          color: var(--text-primary);
          font-size: 0.75rem;
          white-space: nowrap;
          border-radius: 6px;
          opacity: 0;
          visibility: hidden;
          transition: opacity 0.15s ease, margin-left 0.15s ease;
          pointer-events: none;
          z-index: 1000;
          box-shadow: 0 2px 10px rgba(0,0,0,0.3);
        }

        .nav-item:hover::after {
          opacity: 1;
          visibility: visible;
          margin-left: 12px;
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
          min-height: 0;
          overflow-y: auto;
          background: var(--bg-dark);
          padding: 30px 32px;
          box-sizing: border-box;
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
          min-height: 0;
          min-width: 0;
          display: flex;
          flex-direction: column;
          padding: 20px;
          overflow: hidden;
          border-right: 1px solid var(--border-color);
          box-sizing: border-box;
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
          min-width: 0;
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
          grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
          flex-grow: 1;
          min-height: 0;
          min-width: 0;
          overflow: hidden;
        }

        .viewport-panel {
          display: flex;
          flex-direction: column;
          min-height: 0;
          min-width: 0;
          border-right: 1px solid var(--border-color);
        }

        .viewport-panel:last-child {
          border-right: none;
        }

        .viewport-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          background: var(--bg-dark);
          border-bottom: 1px solid var(--border-color);
          padding-right: 8px;
        }

        .viewport-header .viewport-label {
          border-bottom: none;
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
          min-height: 0;
          min-width: 0;
          background: var(--bg-dark);
          position: relative;
          display: flex;
          align-items: center;
          justify-content: center;
          overflow: hidden;
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
          border-left: 1px solid var(--border-color);
          box-shadow: -4px 0 20px rgba(0, 0, 0, 0.04);
          position: relative;
          transition: width 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        [data-theme="hc-dark"] .stage2-right-panel {
          box-shadow: -4px 0 20px rgba(0, 0, 0, 0.3);
        }

        .stage2-right-panel.collapsed {
          width: 0px;
          overflow: visible;
        }

        .panel-content-wrapper {
          display: flex;
          flex-direction: column;
          width: 400px;
          flex: 1;
          min-height: 0;
          padding: 20px;
          opacity: 1;
          transition: opacity 0.2s ease;
          overflow-y: auto;
          box-sizing: border-box;
        }

        .stage2-right-panel.collapsed .panel-content-wrapper {
          opacity: 0;
          pointer-events: none;
        }

        .panel-collapse-btn {
          position: absolute;
          top: 50%;
          left: -18px;
          transform: translateY(-50%);
          width: 18px;
          height: 48px;
          background: rgba(24, 24, 27, 0.85);
          backdrop-filter: blur(6px);
          border: 1px solid var(--border-color);
          border-right: none;
          border-radius: 8px 0 0 8px;
          display: flex;
          align-items: center;
          justify-content: center;
          cursor: pointer;
          color: var(--text-muted);
          z-index: 50;
          transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
          box-shadow: -3px 0 8px rgba(0,0,0,0.2);
        }
        .panel-collapse-btn:hover {
          color: var(--accent-cyan);
          background: rgba(37, 99, 235, 0.15);
          width: 24px;
          left: -24px;
          border-color: var(--accent-cyan);
          box-shadow: -3px 0 15px rgba(0, 229, 255, 0.25);
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

        [data-theme="hc-light"] .sev-badge.critical { color: #b91c1c; background: rgba(239, 68, 68, 0.1); }
        [data-theme="hc-light"] .sev-badge.high { color: #c2410c; background: rgba(249, 115, 22, 0.1); }
        [data-theme="hc-light"] .sev-badge.medium { color: #a16207; background: rgba(234, 179, 8, 0.1); }
        [data-theme="hc-light"] .sev-badge.low { color: #1d4ed8; background: rgba(59, 130, 246, 0.1); }

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
          padding: 10px 16px !important;
          margin-bottom: 12px !important;
        }

        .format-badge-pill {
          padding: 2px 6px;
          border-radius: 4px;
          font-size: 0.62rem;
          font-weight: 700;
          letter-spacing: 0.02em;
          background: rgba(255, 255, 255, 0.05);
          border: 1px solid rgba(255, 255, 255, 0.08);
          color: var(--text-muted);
        }
        .format-badge-pill.ref-format {
          color: var(--accent-cyan);
          background: rgba(0, 255, 204, 0.05);
          border-color: rgba(0, 255, 204, 0.15);
        }
        .format-badge-pill.rev-format {
          color: #a78bfa;
          background: rgba(139, 92, 246, 0.05);
          border-color: rgba(139, 92, 246, 0.15);
        }
        .complexity-delta-pill {
          padding: 3px 8px;
          border-radius: 20px;
          font-size: 0.65rem;
          font-weight: 600;
          color: var(--text-secondary);
          background: rgba(255, 255, 255, 0.03);
          border: 1px solid rgba(255, 255, 255, 0.08);
          display: inline-flex;
          align-items: center;
          gap: 6px;
          letter-spacing: 0.01em;
        }
        .alignment-mismatch-banner {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 8px 12px;
          border-radius: 6px;
          background: rgba(245, 158, 11, 0.06);
          border: 1px solid rgba(245, 158, 11, 0.2);
          margin-top: 4px;
          animation: banner-fade-in 0.3s ease;
        }
        .alignment-mismatch-banner .warning-icon {
          font-size: 0.85rem;
          filter: drop-shadow(0 0 4px rgba(245, 158, 11, 0.4));
        }
        .alignment-mismatch-banner .warning-text {
          font-size: 0.68rem;
          color: #f59e0b;
          font-weight: 500;
          line-height: 1.3;
        }
        @keyframes banner-fade-in {
          from { opacity: 0; transform: translateY(-4px); }
          to { opacity: 1; transform: translateY(0); }
        }

        .compatibility-badge-status {
          display: flex;
          align-items: center;
          gap: 6px;
          padding: 3px 8px;
          border-radius: 20px;
          font-size: 0.62rem;
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
          width: 5px;
          height: 5px;
          border-radius: 50%;
          background: currentColor;
        }

        @keyframes badge-pulse {
          0% { opacity: 0.85; }
          50% { opacity: 1; transform: scale(1.02); }
          100% { opacity: 0.85; }
        }

        .ingested-files-pills {
          display: flex;
          gap: 8px;
          align-items: center;
        }

        .ingested-file-pill {
          display: flex;
          align-items: center;
          gap: 6px;
          padding: 3px 8px;
          border-radius: 6px;
          background: var(--bg-dark);
          border: 1px solid var(--border-color);
          font-size: 0.68rem;
          color: var(--text-primary);
          transition: all 0.2s ease;
        }

        .ingested-file-pill.ref {
          border-left: 3px solid var(--accent-cyan);
        }

        .ingested-file-pill.rev {
          border-left: 3px solid #8b5cf6;
        }

        .ingested-file-pill .pill-label {
          font-weight: 800;
          font-size: 0.65rem;
          letter-spacing: 0.03em;
        }

        .ingested-file-pill.ref .pill-label {
          color: var(--accent-cyan);
        }

        .ingested-file-pill.rev .pill-label {
          color: #a78bfa;
        }

        .ingested-file-pill .pill-filename {
          font-weight: 500;
          max-width: 180px;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        .pill-clear-btn {
          background: transparent;
          border: none;
          color: var(--text-muted);
          cursor: pointer;
          padding: 2px;
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
          transition: all 0.2s ease;
        }

        .pill-clear-btn:hover {
          color: #ef4444;
          background: rgba(239, 68, 68, 0.1);
          transform: scale(1.1);
        }

        .upload-dropzone-container {
          position: relative;
          width: 100%;
          height: 100%;
          transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          padding: 20px;
          box-sizing: border-box;
          overflow: hidden;
          background: transparent;
          border: 1px dashed rgba(255, 255, 255, 0.05);
        }

        .upload-dropzone-container * {
          pointer-events: none;
        }

        [data-theme="hc-light"] .upload-dropzone-container {
          border-color: rgba(0, 0, 0, 0.05);
        }

        .upload-dropzone-container.old:hover {
          background: rgba(37, 99, 235, 0.01);
          border-color: rgba(37, 99, 235, 0.15);
        }

        .upload-dropzone-container.new:hover {
          background: rgba(139, 92, 246, 0.01);
          border-color: rgba(139, 92, 246, 0.15);
        }

        .upload-dropzone-container.old.dragging {
          border-color: var(--accent-cyan) !important;
          background: rgba(37, 99, 235, 0.05) !important;
          box-shadow: inset 0 0 10px rgba(37, 99, 235, 0.1) !important;
        }
        [data-theme="hc-dark"] .upload-dropzone-container.old.dragging {
          background: rgba(0, 229, 255, 0.06) !important;
        }

        .upload-dropzone-container.new.dragging {
          border-color: #8b5cf6 !important;
          background: rgba(139, 92, 246, 0.05) !important;
          box-shadow: inset 0 0 10px rgba(139, 92, 246, 0.1) !important;
        }
        [data-theme="hc-dark"] .upload-dropzone-container.new.dragging {
          border-color: #a78bfa !important;
          background: rgba(167, 139, 250, 0.06) !important;
        }

        .dropzone-idle-view {
          display: flex;
          flex-direction: column;
          align-items: center;
          text-align: center;
          gap: 12px;
        }

        .dropzone-icon-circle {
          width: 32px;
          height: 32px;
          border-radius: 50%;
          background: rgba(255, 255, 255, 0.02);
          border: 1px solid var(--border-color);
          display: flex;
          align-items: center;
          justify-content: center;
          color: var(--text-muted);
          transition: all 0.25s ease;
        }

        .upload-dropzone-container.old:hover .dropzone-icon-circle {
          transform: translateY(-2px);
          border-color: var(--accent-cyan);
          color: var(--accent-cyan);
          background: rgba(37, 99, 235, 0.06);
        }

        .upload-dropzone-container.new:hover .dropzone-icon-circle {
          transform: translateY(-2px);
          border-color: #8b5cf6;
          color: #a78bfa;
          background: rgba(139, 92, 246, 0.06);
        }

        .dropzone-main-text {
          font-size: 0.88rem;
          font-weight: 600;
          color: var(--text-primary);
          margin: 0;
        }

        .browse-link {
          color: var(--accent-cyan);
          text-decoration: underline;
          font-weight: 700;
        }

        .upload-dropzone-container.new .browse-link {
          color: #a78bfa;
        }

        .dropzone-sub-text {
          font-size: 0.72rem;
          color: var(--text-muted);
          margin: 4px 0 0 0;
        }

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
