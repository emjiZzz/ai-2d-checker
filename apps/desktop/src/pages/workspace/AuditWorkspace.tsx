import React, { useState, useEffect } from "react";
import { useWorkspaceStore, DrawingItem } from "../../stores/workspaceStore";
import { useAuthStore } from "../../stores/authStore";
import { useConnectionStore } from "../../stores/connectionStore";
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
  Sun
} from "lucide-react";
import { useThemeStore } from "../../stores/themeStore";
import { StandardsManager } from "../../components/StandardsManager";

export const AuditWorkspace: React.FC = () => {
  const { user, logout } = useAuthStore();
  const { backendUrl, apiToken } = useConnectionStore.getState();
  const { theme, toggleTheme } = useThemeStore();

  // Selected workspace navigation sub-view
  const [currentNav, setCurrentNav] = useState<"workspace" | "standards" | "history" | "settings">("workspace");

  // Local drawing catalog for selections
  const [drawings, setDrawings] = useState<DrawingItem[]>([]);
  const [selectedStandard, setSelectedStandard] = useState("");
  const [standards, setStandards] = useState<any[]>([]);

  // Fetch initial drawings and standards list
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
    panX,
    panY,
    zoom,
    activeLayers,
    auditStatus,
    complianceScore,
    violations,
    selectedViolation,
    setOldDrawing,
    setNewDrawing,
    setViewport,
    toggleLayer,
    runAudit,
    selectViolation
  } = useWorkspaceStore();

  const handleAuditTrigger = async () => {
    if (!newDrawing) return;
    await runAudit(selectedStandard);
  };

  const criticalCount = violations.filter((v) => v.severity === "critical").length;
  const highCount = violations.filter((v) => v.severity === "high").length;
  const medCount = violations.filter((v) => v.severity === "medium").length;
  const lowCount = violations.filter((v) => v.severity === "low").length;

  return (
    <div className="workspace-container">
      {/* 1. LEFT SIDEBAR (ENGINEERING NAVIGATION) */}
      <aside className="workspace-sidebar">
        <div className="sidebar-branding">
          <div className="brand-logo">
            <Cpu size={20} style={{ color: "#00e5ff" }} />
          </div>
          <div className="brand-text">
            <h1 className="brand-title">AI-2D-Checker</h1>
            <span className="brand-badge">COMPLIANCE ENGINE</span>
          </div>
        </div>

        <nav className="sidebar-nav">
          <button
            className={`nav-item ${currentNav === "workspace" ? "active" : ""}`}
            onClick={() => setCurrentNav("workspace")}
          >
            <Compass size={16} />
            <span>Audit Workspace</span>
          </button>

          <button
            className={`nav-item ${currentNav === "standards" ? "active" : ""}`}
            onClick={() => setCurrentNav("standards")}
          >
            <Bookmark size={16} />
            <span>Standards Manuals</span>
          </button>

          <button
            className={`nav-item ${currentNav === "history" ? "active" : ""}`}
            onClick={() => setCurrentNav("history")}
          >
            <History size={16} />
            <span>Drawing History</span>
          </button>

          <button
            className={`nav-item ${currentNav === "settings" ? "active" : ""}`}
            onClick={() => setCurrentNav("settings")}
          >
            <SettingsIcon size={16} />
            <span>Audit Settings</span>
          </button>
        </nav>

        <div className="sidebar-footer">
          <div className="user-profile">
            <ShieldCheck size={16} style={{ color: "var(--accent-cyan, #00e5ff)" }} />
            <div className="profile-details">
              <span className="profile-name">{user?.username || "Engineer"}</span>
              <span className="profile-role">Compliance Auditor</span>
            </div>
          </div>

          <div style={{ display: "flex", gap: "8px", marginTop: "12px" }}>
            <button 
              className="theme-toggle-btn" 
              onClick={toggleTheme} 
              title="Toggle Theme" 
              style={{ 
                background: "transparent", 
                border: "1px solid var(--border-color, #27272a)", 
                padding: "10px", 
                borderRadius: "6px", 
                color: "var(--text-muted, #a1a1aa)",
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                justifyContent: "center"
              }}
            >
              {theme === "hc-dark" ? <Moon size={16} /> : <Sun size={16} />}
            </button>
            <button className="btn-logout" onClick={() => logout()} title="Logout Portal" style={{ flexGrow: 1 }}>
              <LogOut size={16} />
              <span>Logout</span>
            </button>
          </div>
        </div>
      </aside>

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
            <div className="card settings-card" style={{ marginBottom: "20px" }}>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "20px" }}>
                {/* Left Upload Box */}
                <div className="form-group">
                  <label className="form-label">1. Reference Drawing (Old Version)</label>
                  <select
                    className="form-input select-input"
                    value={oldDrawing?.id || ""}
                    onChange={(e) => {
                      const dwg = drawings.find((d) => d.id === e.target.value);
                      setOldDrawing(dwg || null);
                    }}
                  >
                    <option value="">-- Choose Reference CAD --</option>
                    {drawings.map((d) => (
                      <option key={d.id} value={d.id}>
                        {d.file_name} ({d.format.toUpperCase()})
                      </option>
                    ))}
                  </select>
                </div>

                {/* Right Upload Box */}
                <div className="form-group">
                  <label className="form-label">2. Revision Drawing (New Version)</label>
                  <select
                    className="form-input select-input"
                    value={newDrawing?.id || ""}
                    onChange={(e) => {
                      const dwg = drawings.find((d) => d.id === e.target.value);
                      setNewDrawing(dwg || null);
                    }}
                  >
                    <option value="">-- Choose Revision CAD --</option>
                    {drawings.map((d) => (
                      <option key={d.id} value={d.id}>
                        {d.file_name} ({d.format.toUpperCase()})
                      </option>
                    ))}
                  </select>
                </div>
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
                  <div className="cad-canvas-mock">
                    {oldDrawing ? (
                      <div className="blueprint-overlay">
                        {/* Render standard drafting layout mock elements */}
                        <div className="cad-element unchanged-line" style={{ left: "20%", top: "30%", width: "60%" }}></div>
                        <div className="cad-element unchanged-line" style={{ left: "20%", top: "30%", height: "40%" }}></div>
                        <div className="cad-element removed-line" style={{ left: "40%", top: "45%", width: "20%" }}></div>
                        <div className="cad-element circle" style={{ left: "50%", top: "50%", width: "40px", height: "40px" }}></div>
                        <span className="cad-coordinate-axis">X: 20.40, Y: -12.44</span>
                      </div>
                    ) : (
                      <div className="canvas-empty">Reference drawing not selected.</div>
                    )}
                  </div>
                </div>

                {/* Right Viewport (New) */}
                <div className="viewport-panel">
                  <div className="viewport-label">Revision CAD (New)</div>
                  <div className="cad-canvas-mock">
                    {newDrawing ? (
                      <div className="blueprint-overlay">
                        {/* Render standard drafting layout mock elements */}
                        <div className="cad-element unchanged-line" style={{ left: "20%", top: "30%", width: "60%" }}></div>
                        <div className="cad-element unchanged-line" style={{ left: "20%", top: "30%", height: "40%" }}></div>
                        <div className="cad-element added-line" style={{ left: "40%", top: "55%", width: "30%" }}></div>
                        <div className="cad-element circle modified" style={{ left: "55%", top: "50%", width: "40px", height: "40px" }}></div>
                        <span className="cad-coordinate-axis">X: 20.40, Y: -12.44</span>

                        {selectedViolation?.coordinates && (
                          <div
                            className="cad-highlight-reticle"
                            style={{
                              left: `${selectedViolation.coordinates[0]}%`,
                              top: `${selectedViolation.coordinates[1]}%`,
                            }}
                          ></div>
                        )}
                      </div>
                    ) : (
                      <div className="canvas-empty">Revision drawing not selected.</div>
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
                <label className="form-label">Grounding Standards Manual</label>
                <select
                  className="form-input select-input"
                  value={selectedStandard}
                  onChange={(e) => setSelectedStandard(e.target.value)}
                >
                  {standards.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}
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
          width: 260px;
          height: 100%;
          background: var(--bg-sidebar);
          border-right: 1px solid var(--border-color);
          display: flex;
          flex-direction: column;
          flex-shrink: 0;
        }

        .sidebar-branding {
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 24px;
          border-bottom: 1px solid var(--border-color);
        }

        .brand-logo {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 32px;
          height: 32px;
          border-radius: 6px;
          background: rgba(0, 229, 255, 0.1);
          border: 1px solid rgba(0, 229, 255, 0.2);
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
          color: #00e5ff;
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
          background: rgba(39, 39, 42, 0.5);
        }

        .nav-item.active {
          color: #00e5ff;
          background: rgba(0, 229, 255, 0.05);
          border: 1px solid rgba(0, 229, 255, 0.15);
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
          background: rgba(39, 39, 42, 0.3);
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
          gap: 10px;
          padding: 10px 16px;
          background: transparent;
          border: 1px solid var(--border-color);
          border-radius: 6px;
          color: #ef4444;
          font-size: 0.8rem;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.2s ease;
          justify-content: center;
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
          overflow-y: auto;
          border-right: 1px solid var(--border-color);
        }

        .cad-viewer-container {
          flex-grow: 1;
          background: var(--bg-sidebar);
          border: 1px solid var(--border-color);
          border-radius: 8px;
          display: flex;
          flex-direction: column;
          overflow: hidden;
          min-height: 480px;
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
          color: #00e5ff;
          border-color: rgba(0, 229, 255, 0.3);
          background: rgba(0, 229, 255, 0.05);
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
          color: var(--text-muted);
          text-transform: uppercase;
          padding: 8px 12px;
          background: rgba(9, 9, 11, 0.5);
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
          border-radius: 8px;
          padding: 14px;
          cursor: pointer;
          transition: all 0.2s ease;
        }

        .violation-card-item:hover {
          border-color: #52525b;
          transform: translateY(-1px);
        }

        .violation-card-item.selected {
          border-color: #00e5ff;
          box-shadow: 0 0 8px rgba(0, 229, 255, 0.1);
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
          background: rgba(39, 39, 42, 0.3);
          border: 1px solid var(--border-color);
          padding: 8px 10px;
          border-radius: 4px;
          font-size: 0.7rem;
          color: #d4d4d8;
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
          color: #00e5ff;
          font-weight: 600;
        }

        .loader {
          border: 3px solid rgba(255,255,255,0.05);
          border-top-color: #00e5ff;
          border-radius: 50%;
          width: 24px;
          height: 24px;
        }
      `}</style>
    </div>
  );
};
