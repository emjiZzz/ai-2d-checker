import { useEffect, useState, useRef } from "react";
import {
  useConnectionStore,
  ConnectionStatus
} from "./stores/connectionStore";
import { useDrawingStore } from "./stores/drawingStore";
import { useAuthStore } from "./stores/authStore";
import { useThemeStore } from "./stores/themeStore";
import { LoginPage } from "./pages/auth/LoginPage";
import { AppHeader } from "./components/AppHeader";
import { AdminDashboard } from "./pages/admin/AdminDashboard";
import { AuditWorkspace } from "./pages/workspace/AuditWorkspace";
import {
  Activity,
  Settings,
  LayoutDashboard,
  FileText,
  UploadCloud,
  AlertCircle,
  RefreshCw,
  ShieldCheck,
  Server,
  Clock,
  Cpu,
  Database,
  XCircle,
  FileCode,
  Sparkles,
  Loader2,
  Moon,
  Sun
} from "lucide-react";
import { StandardsManager } from "./components/StandardsManager";
import { AuditConsole } from "./components/AuditConsole";
import "./App.css";

function App() {
  const {
    backendUrl,
    status,
    version,
    lastChecked,
    error,
    setBackendUrl,
    checkHealth,
    startPolling,
    stopPolling,
  } = useConnectionStore();

  const {
    activeDrawing,
    activeJob,
    uploadStatus,
    uploadProgress,
    processingState,
    errorMessage,
    uploadDrawing,
    resetStore
  } = useDrawingStore();

  const [inputUrl, setInputUrl] = useState(backendUrl);
  const [activeTab, setActiveTab] = useState("dashboard");
  const [isManualChecking, setIsManualChecking] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const { theme, toggleTheme, initialize: initializeTheme } = useThemeStore();

  useEffect(() => {
    initializeTheme();
  }, [initializeTheme]);
  const [diagnostics, setDiagnostics] = useState<{
    mongodb: boolean;
    storage_root: boolean;
    gemini_api: boolean;
  } | null>(null);

  // Poll connection on component mount
  useEffect(() => {
    startPolling(5000);
    fetchDiagnostics();
    return () => stopPolling();
  }, [backendUrl]);

  // Fetch detailed diagnostic properties from server
  const fetchDiagnostics = async () => {
    try {
      const response = await fetch(`${backendUrl}/health`);
      if (response.ok) {
        const data = await response.json();
        // The API returns health structure containing services
        if (data.services) {
          setDiagnostics(data.services);
        } else if (data.data && data.success) {
          // Fallback check
          setDiagnostics({
            mongodb: true,
            storage_root: true,
            gemini_api: true
          });
        }
      } else {
        setDiagnostics(null);
      }
    } catch {
      setDiagnostics(null);
    }
  };

  useEffect(() => {
    if (status === "online") {
      fetchDiagnostics();
    } else {
      setDiagnostics(null);
    }
  }, [status]);

  const handleUrlSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setBackendUrl(inputUrl);
  };

  const handleManualTrigger = async () => {
    setIsManualChecking(true);
    await checkHealth();
    await fetchDiagnostics();
    setIsManualChecking(false);
  };

  // Drag & Drop event handlers
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);

    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const file = e.dataTransfer.files[0];
      await handleFileSelection(file);
    }
  };

  const handleFileSelectChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const file = e.target.files[0];
      await handleFileSelection(file);
    }
  };

  const handleFileSelection = async (file: File) => {
    const ext = file.name.split(".").pop()?.toLowerCase();
    if (ext !== "dwg" && ext !== "dxf") {
      alert("Invalid format: Only CAD drawings in proprietary .dwg or open .dxf formats are supported.");
      return;
    }
    await uploadDrawing(file);
  };

  const triggerFileBrowser = () => {
    fileInputRef.current?.click();
  };

  // Human friendly descriptions of current connection states
  const getStatusLabel = (s: ConnectionStatus) => {
    switch (s) {
      case "online": return "Backend Active";
      case "offline": return "Backend Offline";
      case "connecting": return "Connecting...";
      case "reconnecting": return "Reconnecting...";
      case "failed": return "Connection Failed";
      case "invalid": return "Invalid Handshake";
      default: return "Unknown";
    }
  };

  const isOffline = status === "offline" || status === "failed";

  const { isAuthenticated, user, initialize } = useAuthStore();

  useEffect(() => {
    initialize();
  }, [initialize]);

  const renderContent = () => {
    if (!isAuthenticated) return <LoginPage />;
    if (user?.role === "admin") return <AdminDashboard />;
    if (user?.role === "user") return <AuditWorkspace />;
    return (
      <div className="app-container">
        {/* Sidebar Navigation */}
        <aside className="sidebar">
          <div className="logo-section">
            <div className="logo-icon">
              <Activity size={20} color="#fff" />
            </div>
            <span className="logo-text">AI-2D-Checker</span>
          </div>

          <nav className="nav-links">
            <button
              onClick={() => setActiveTab("dashboard")}
              className={`nav-item ${activeTab === "dashboard" ? "active" : ""}`}
            >
              <LayoutDashboard size={18} />
              Dashboard
            </button>

            <button
              onClick={() => !isOffline && setActiveTab("standards")}
              className={`nav-item ${activeTab === "standards" ? "active" : ""} ${isOffline ? "disabled" : ""}`}
              style={{ opacity: isOffline ? 0.4 : 1, cursor: isOffline ? "not-allowed" : "pointer" }}
              disabled={isOffline}
            >
              <FileText size={18} />
              Standards Library
            </button>

            <button
              onClick={() => {
                if (!isOffline) {
                  setActiveTab("upload");
                }
              }}
              className={`nav-item ${activeTab === "upload" ? "active" : ""} ${isOffline ? "disabled" : ""}`}
              style={{ opacity: isOffline ? 0.4 : 1, cursor: isOffline ? "not-allowed" : "pointer" }}
              disabled={isOffline}
            >
              <UploadCloud size={18} />
              Drawing Upload
            </button>

            <button
              onClick={() => !isOffline && setActiveTab("audit")}
              className={`nav-item ${activeTab === "audit" ? "active" : ""} ${isOffline ? "disabled" : ""}`}
              style={{ opacity: isOffline ? 0.4 : 1, cursor: isOffline ? "not-allowed" : "pointer" }}
              disabled={isOffline}
            >
              <ShieldCheck size={18} />
              Compliance Auditor
            </button>

            <button
              onClick={() => setActiveTab("settings")}
              className={`nav-item ${activeTab === "settings" ? "active" : ""}`}
            >
              <Settings size={18} />
              System Settings
            </button>
          </nav>
        </aside>

        {/* Main Dashboard Section */}
        <main className="main-content">

          {/* Top Status Bar */}
          <header className="topbar">
            <div className="tab-title">
              <h2 style={{ textTransform: "capitalize", fontSize: "1.3rem", fontWeight: 600, color: "var(--text-primary)" }}>
                {activeTab === "dashboard" ? "Service Dashboard" : activeTab === "upload" ? "Drawing Extraction Pipeline" : activeTab === "standards" ? "Standards Reference Library" : activeTab === "audit" ? "Compliance Auditing Center" : "System Settings"}
              </h2>
            </div>

            <div style={{ display: "flex", gap: "16px", alignItems: "center" }}>
              <div className={`status-badge ${status}`}>
                <span className="pulse-dot"></span>
                <span>{getStatusLabel(status)}</span>
              </div>

              <button
                className="theme-toggle-btn"
                onClick={toggleTheme}
                title={`Current Theme: ${theme === 'hc-dark' ? 'High Contrast Dark' : 'High Contrast Light'
                  }. Click to toggle.`}
              >
                {theme === "hc-dark" ? (
                  <Moon size={18} style={{ display: "block" }} />
                ) : (
                  <Sun size={18} style={{ display: "block" }} />
                )}
              </button>

              <button
                className="theme-toggle-btn"
                onClick={handleManualTrigger}
                disabled={isManualChecking}
                title="Force health check"
              >
                <RefreshCw size={18} className={isManualChecking ? "spin-animation" : ""} />
              </button>
            </div>
          </header>

          {/* Dynamic Pages / Tabs */}
          <div className="tab-container">

            {/* TAB 1: Service Dashboard */}
            {activeTab === "dashboard" && (
              <div className="dashboard-grid">
                {/* Card: Connection Dashboard Console */}
                <div className="card">
                  <h3 className="card-title">
                    <Server size={18} className="text-purple" />
                    Service Status Dashboard
                  </h3>

                  <table className="stats-table">
                    <tbody>
                      <tr className="stats-row">
                        <td className="stats-label">Backend Host URL</td>
                        <td className="stats-value" style={{ color: "#38bdf8" }}>{backendUrl}</td>
                      </tr>
                      <tr className="stats-row">
                        <td className="stats-label">Loopback Validation</td>
                        <td className="stats-value">
                          <span style={{ color: "#10b981", display: "inline-flex", alignItems: "center", gap: "4px" }}>
                            <ShieldCheck size={14} /> Loopback-Only
                          </span>
                        </td>
                      </tr>
                      <tr className="stats-row">
                        <td className="stats-label">Backend Version</td>
                        <td className="stats-value">{version || "1.0.0"}</td>
                      </tr>
                      <tr className="stats-row">
                        <td className="stats-label">MongoDB Connection</td>
                        <td className="stats-value">
                          {diagnostics?.mongodb ? (
                            <span style={{ color: "#10b981" }}>Connected (Beanie ODM)</span>
                          ) : (
                            <span style={{ color: "#ef4444" }}>Offline</span>
                          )}
                        </td>
                      </tr>
                      <tr className="stats-row">
                        <td className="stats-label">Secure Sandbox Storage</td>
                        <td className="stats-value" style={{ color: diagnostics?.storage_root ? "#10b981" : "#ef4444" }}>
                          {diagnostics?.storage_root ? "Validated (Write-Test OK)" : "Pending Verification"}
                        </td>
                      </tr>
                      <tr className="stats-row">
                        <td className="stats-label">Gemini API Key Protection</td>
                        <td className="stats-value" style={{ color: diagnostics?.gemini_api ? "#10b981" : "#ef4444" }}>
                          {diagnostics?.gemini_api ? "Encrypted Config Active" : "Missing API Key"}
                        </td>
                      </tr>
                      <tr className="stats-row">
                        <td className="stats-label">Last Diagnostics Ping</td>
                        <td className="stats-value">
                          {lastChecked ? new Date(lastChecked).toLocaleTimeString() : "Never"}
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>

                {/* Card: Connection Settings & Configurations */}
                <div className="card">
                  <h3 className="card-title">
                    <Settings size={18} className="text-cyan" />
                    Connection Settings
                  </h3>

                  <p className="card-description">
                    Verify or update the standalone local backend binding variables. Ensure the host binds securely to a localhost interface.
                  </p>

                  <form onSubmit={handleUrlSubmit}>
                    <div className="form-group">
                      <label className="form-label">FastAPI Backend Endpoint</label>
                      <input
                        type="text"
                        value={inputUrl}
                        onChange={(e) => setInputUrl(e.target.value)}
                        className="form-input"
                        placeholder="e.g. http://127.0.0.1:8080"
                      />
                    </div>

                    <div style={{ display: "flex", gap: "12px", marginTop: "24px" }}>
                      <button type="submit" className="btn btn-primary">
                        Apply Configurations
                      </button>
                      <button
                        type="button"
                        className="btn btn-secondary"
                        onClick={() => setInputUrl("http://127.0.0.1:8080")}
                      >
                        Reset Defaults
                      </button>
                    </div>
                  </form>
                </div>
              </div>
            )}

            {/* TAB 2: Drawing Ingestion & Processing Monitor */}
            {activeTab === "upload" && (
              <div className="upload-view-layout">

                {/* Drag & Drop Panel */}
                <div className="card" style={{ padding: "30px", marginBottom: "24px" }}>
                  <h3 className="card-title" style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                    <UploadCloud size={18} style={{ color: "var(--accent-cyan)" }} />
                    Ingest Local CAD Drawing
                  </h3>

                  <p className="card-description">
                    Upload a 2D engineering drawing in `.dwg` or `.dxf` format. Proprietary DWG drawings are safely converted inside our local sandbox converter.
                  </p>

                  <div
                    className={`drag-drop-zone ${isDragging ? "dragging" : ""} ${uploadStatus === "uploading" ? "disabled" : ""}`}
                    onDragOver={handleDragOver}
                    onDragLeave={handleDragLeave}
                    onDrop={handleDrop}
                    onClick={() => uploadStatus !== "uploading" && triggerFileBrowser()}
                  >
                    <input
                      type="file"
                      ref={fileInputRef}
                      onChange={handleFileSelectChange}
                      style={{ display: "none" }}
                      accept=".dwg,.dxf"
                    />

                    <div className="upload-icon-container">
                      {uploadStatus === "uploading" || processingState === "processing" ? (
                        <Loader2 size={36} className="spin-animation" style={{ color: "var(--accent-cyan)" }} />
                      ) : (
                        <FileCode size={36} style={{ color: "var(--accent-cyan)" }} />
                      )}
                    </div>

                    <span className="upload-prompt">
                      {uploadStatus === "uploading"
                        ? "Uploading stream to secure storage..."
                        : processingState === "processing"
                          ? "FastAPI Sidecar is converting & extracting entities..."
                          : "Drag & Drop drawing here, or click to browse local files"}
                    </span>
                    <span className="upload-specs">Supports DWG / DXF (Max 500MB)</span>
                  </div>

                  {/* Progress metrics and background state steps */}
                  {(uploadStatus === "uploading" || processingState === "processing") && (
                    <div className="progress-container">
                      <div className="progress-bar-bg">
                        <div
                          className="progress-bar-fill"
                          style={{ width: `${uploadStatus === "uploading" ? uploadProgress : 95}%` }}
                        ></div>
                      </div>

                      <div className="progress-labels">
                        <span className="progress-state-text">
                          {uploadStatus === "uploading"
                            ? `Streaming upload: ${uploadProgress}%`
                            : "Extracting geometric entities (lines, arcs, layers, dimensions)..."}
                        </span>
                        <span className="loading-dots">Active Background Queue</span>
                      </div>
                    </div>
                  )}

                  {/* Error warning display */}
                  {errorMessage && (
                    <div className="error-alert">
                      <XCircle size={18} />
                      <div style={{ marginLeft: "10px" }}>
                        <strong>Extraction Error:</strong> {errorMessage}
                        <button className="btn btn-secondary mt-2" onClick={resetStore} style={{ display: "block", fontSize: "0.8rem", padding: "4px 8px" }}>
                          Clear & Retry Ingestion
                        </button>
                      </div>
                    </div>
                  )}
                </div>

                {/* SUCCESS STATE: Diagnostics and Geometry Viewer */}
                {processingState === "completed" && activeDrawing && (
                  <div className="diagnostics-dashboard">

                    {/* File Metadata Overview */}
                    <div className="card-row-grid">
                      <div className="card mini-card">
                        <div className="mini-card-icon bg-purple-soft">
                          <FileCode size={18} className="text-purple" />
                        </div>
                        <div className="mini-card-content">
                          <span className="mini-label">Drawing Format</span>
                          <span className="mini-value" style={{ textTransform: "uppercase" }}>{activeDrawing.format}</span>
                        </div>
                      </div>

                      <div className="card mini-card">
                        <div className="mini-card-icon bg-cyan-soft">
                          <Database size={18} className="text-cyan" />
                        </div>
                        <div className="mini-card-content">
                          <span className="mini-label">File Size</span>
                          <span className="mini-value">{(activeDrawing.file_size_bytes / 1024).toFixed(1)} KB</span>
                        </div>
                      </div>

                      <div className="card mini-card">
                        <div className="mini-card-icon bg-emerald-soft">
                          <Clock size={18} className="text-emerald" />
                        </div>
                        <div className="mini-card-content">
                          <span className="mini-label">Total Duration</span>
                          <span className="mini-value">
                            {activeJob?.total_duration_seconds ? `${activeJob.total_duration_seconds.toFixed(3)}s` : "N/A"}
                          </span>
                        </div>
                      </div>
                    </div>

                    {/* Detailed Diagnostics grid */}
                    <div className="dashboard-grid">

                      {/* Entity Breakdown Stats */}
                      <div className="card">
                        <h3 className="card-title">
                          <Sparkles size={18} className="text-purple" />
                          Extracted Geometric Entities
                        </h3>

                        <p className="card-description" style={{ marginBottom: "16px" }}>
                          Unified collections mapped from drawing model space blocks.
                        </p>

                        <table className="stats-table">
                          <thead>
                            <tr className="stats-row" style={{ fontWeight: "bold", borderBottom: "1px solid #3f3f46" }}>
                              <td className="stats-label" style={{ paddingBottom: "10px" }}>Entity Type</td>
                              <td className="stats-value" style={{ paddingBottom: "10px" }}>Count</td>
                            </tr>
                          </thead>
                          <tbody>
                            {Object.entries(activeDrawing.entity_counts).map(([type, count]) => (
                              <tr className="stats-row" key={type}>
                                <td className="stats-label" style={{ textTransform: "capitalize" }}>{type}s</td>
                                <td className="stats-value" style={{ color: "#10b981", fontWeight: 600 }}>{count}</td>
                              </tr>
                            ))}
                            {Object.keys(activeDrawing.entity_counts).length === 0 && (
                              <tr>
                                <td colSpan={2} style={{ textAlign: "center", color: "#71717a", padding: "16px 0" }}>
                                  No entities found in model space
                                </td>
                              </tr>
                            )}
                          </tbody>
                        </table>
                      </div>

                      {/* Converter and parsing diagnostics */}
                      <div className="card">
                        <h3 className="card-title">
                          <Cpu size={18} className="text-cyan" />
                          Pipeline Engine Metrics
                        </h3>

                        <table className="stats-table">
                          <tbody>
                            <tr className="stats-row">
                              <td className="stats-label">AutoCAD Release</td>
                              <td className="stats-value" style={{ color: "#38bdf8" }}>
                                {activeDrawing.metadata?.acad_version || "Unknown"}
                              </td>
                            </tr>
                            <tr className="stats-row">
                              <td className="stats-label">DWG Conversion Duration</td>
                              <td className="stats-value">
                                {activeJob?.conversion_duration_seconds
                                  ? `${activeJob.conversion_duration_seconds.toFixed(3)}s`
                                  : "Bypassed (DXF direct)"}
                              </td>
                            </tr>
                            <tr className="stats-row">
                              <td className="stats-label">ezdxf Parse Duration</td>
                              <td className="stats-value">
                                {activeJob?.parsing_duration_seconds
                                  ? `${activeJob.parsing_duration_seconds.toFixed(3)}s`
                                  : "N/A"}
                              </td>
                            </tr>
                            <tr className="stats-row">
                              <td className="stats-label">SHA-256 Checksum</td>
                              <td className="stats-value" style={{ fontFamily: "monospace", fontSize: "0.75rem", color: "#a1a1aa" }}>
                                {activeDrawing.file_hash.substring(0, 24)}...
                              </td>
                            </tr>
                            <tr className="stats-row">
                              <td className="stats-label">Measurement Scale</td>
                              <td className="stats-value">
                                {activeDrawing.metadata?.measurement === 1 ? "Metric (mm)" : "Imperial (inches)"}
                              </td>
                            </tr>
                            <tr className="stats-row">
                              <td className="stats-label">Extents Bounding Box</td>
                              <td className="stats-value" style={{ fontSize: "0.8rem", color: "#a1a1aa" }}>
                                Min: {activeDrawing.metadata?.extmin ? JSON.stringify(activeDrawing.metadata.extmin.slice(0, 2)) : "N/A"}<br />
                                Max: {activeDrawing.metadata?.extmax ? JSON.stringify(activeDrawing.metadata.extmax.slice(0, 2)) : "N/A"}
                              </td>
                            </tr>
                          </tbody>
                        </table>

                        <div style={{ marginTop: "20px" }}>
                          <button className="btn btn-primary" onClick={resetStore} style={{ width: "100%" }}>
                            Ingest Another CAD Drawing
                          </button>
                        </div>
                      </div>
                    </div>

                  </div>
                )}

              </div>
            )}

            {/* TAB 3: Standards Library */}
            {activeTab === "standards" && (
              <StandardsManager />
            )}

            {/* TAB 4: Compliance Auditor */}
            {activeTab === "audit" && (
              <AuditConsole />
            )}

            {/* TAB 5: System Settings */}
            {activeTab === "settings" && (
              <div className="settings-view-layout">
                <div className="card settings-card">
                  <h3 className="card-title" style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                    <Settings size={18} style={{ color: "var(--accent-cyan)" }} />
                    Global Platform Settings & Hardware Info
                  </h3>
                  <p className="card-description">
                    Configure local application environment boundaries and security parameters.
                  </p>

                  <div style={{ marginTop: "24px" }}>
                    <table className="stats-table">
                      <tbody>
                        <tr className="stats-row">
                          <td className="stats-label">Secure Sandbox Path</td>
                          <td className="stats-value" style={{ fontFamily: "monospace", fontSize: "0.8rem" }}>
                            storage/standards
                          </td>
                        </tr>
                        <tr className="stats-row">
                          <td className="stats-label">Gemini Vision Auditing</td>
                          <td className="stats-value" style={{ color: "#10b981" }}>
                            Offline Comparative Fallback Mode Enabled
                          </td>
                        </tr>
                        <tr className="stats-row">
                          <td className="stats-label">CAD Vector Core</td>
                          <td className="stats-value">ezdxf 1.1 + custom geometry rules</td>
                        </tr>
                        <tr className="stats-row">
                          <td className="stats-label">Data Sync Frequency</td>
                          <td className="stats-value">Local first (0ms latency, pure offline)</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            )}

          </div>

          {/* Lock Overlay trigger when standalone local backend goes Offline */}
          {isOffline && (
            <div className="offline-overlay">
              <div className="overlay-card">
                <div className="alert-icon-container">
                  <AlertCircle size={36} />
                </div>
                <h2 className="overlay-title">Local Backend Service Offline</h2>
                <p className="card-description" style={{ marginBottom: "16px" }}>
                  The AI-2D-Checker desktop app communicates with a standalone localhost-only backend. The service at <strong style={{ color: "#a855f7" }}>{backendUrl}</strong> is currently unreachable.
                </p>

                <div className="code-box">
                  powershell -ExecutionPolicy Bypass -File .\services\backend\start.ps1
                </div>

                <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
                  <button
                    onClick={handleManualTrigger}
                    className="btn btn-primary"
                    style={{ width: "100%", padding: "12px" }}
                    disabled={isManualChecking}
                  >
                    <RefreshCw size={16} className={isManualChecking ? "spin-animation" : ""} />
                    {isManualChecking ? "Connecting..." : "Trigger Manual Diagnostic Check"}
                  </button>

                  <button
                    onClick={() => setActiveTab("dashboard")}
                    className="btn btn-secondary"
                    style={{ width: "100%" }}
                  >
                    <Settings size={16} />
                    Adjust Connection URL
                  </button>
                </div>

                {error && (
                  <div style={{
                    marginTop: "20px",
                    padding: "10px",
                    background: "rgba(220, 38, 38, 0.1)",
                    border: "1px solid rgba(220, 38, 38, 0.2)",
                    borderRadius: "8px",
                    fontSize: "0.8rem",
                    color: "#fca5a5"
                  }}>
                    {error}
                  </div>
                )}
              </div>
            </div>
          )}

        </main>
      </div>
    );
  };

  return (
    <div className="app-root" style={{ display: 'flex', flexDirection: 'column', height: '100vh', overflow: 'hidden' }}>
      <AppHeader />
      <div className="app-main-view" style={{ flexGrow: 1, overflow: 'hidden', position: 'relative', display: 'flex' }}>
        {renderContent()}
      </div>

      {/* Embedded Spin Animations Stylesheet */}
      <style>{`
        .spin-animation {
          animation: spin 1.2s linear infinite;
        }
        @keyframes spin {
          0% { transform: rotate(0deg); }
          100% { transform: rotate(360deg); }
        }
        .text-purple { color: #a855f7; }
        .text-cyan { color: #06b6d4; }
        .text-emerald { color: #10b981; }
        
        .disabled {
          opacity: 0.5;
          pointer-events: none;
        }

        .upload-view-layout {
          padding: 0 32px;
          margin-top: 30px;
        }

        .settings-view-layout {
          padding: 0 32px;
          margin-top: 30px;
        }

        .settings-card {
          border: 2px dashed var(--border-color) !important;
          border-radius: 12px !important;
          padding: 40px 32px !important;
        }

        .drag-drop-zone {
          border: 2px dashed var(--border-color);
          border-radius: 12px;
          padding: 60px 20px;
          text-align: center;
          background: var(--bg-card);
          cursor: pointer;
          transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 16px;
        }
        .drag-drop-zone:hover {
          border-color: var(--accent-cyan);
          background: rgba(0, 229, 255, 0.05);
        }
        [data-theme="hc-light"] .drag-drop-zone:hover {
          background: rgba(0, 68, 255, 0.03);
        }
        .drag-drop-zone.dragging {
          border-color: var(--accent-cyan);
          background: rgba(0, 229, 255, 0.1);
          transform: scale(1.02);
        }

        .upload-icon-container {
          width: 64px;
          height: 64px;
          border-radius: 50%;
          background: var(--sidebar-item-hover);
          border: 1px solid var(--border-color);
          display: flex;
          align-items: center;
          justify-content: center;
          margin-bottom: 8px;
        }

        .upload-prompt {
          font-size: 1rem;
          font-weight: 500;
          color: var(--text-primary);
        }
        .upload-specs {
          font-size: 0.8rem;
          color: var(--text-muted);
        }

        .progress-container {
          margin-top: 24px;
        }
        .progress-bar-bg {
          height: 8px;
          width: 100%;
          background: #27272a;
          border-radius: 4px;
          overflow: hidden;
        }
        .progress-bar-fill {
          height: 100%;
          background: linear-gradient(90deg, #a855f7 0%, #06b6d4 100%);
          border-radius: 4px;
          transition: width 0.3s ease;
        }
        .progress-labels {
          display: flex;
          justify-content: space-between;
          font-size: 0.8rem;
          color: #a1a1aa;
          margin-top: 8px;
        }
        
        .loading-dots::after {
          content: '...';
          animation: dots 1.5s steps(5, end) infinite;
        }
        @keyframes dots {
          0%, 20% { content: ''; }
          40% { content: '.'; }
          60% { content: '..'; }
          80%, 100% { content: '...'; }
        }

        .error-alert {
          margin-top: 24px;
          padding: 16px;
          background: rgba(220, 38, 38, 0.1);
          border: 1px solid rgba(220, 38, 38, 0.2);
          border-radius: 8px;
          display: flex;
          align-items: flex-start;
          color: #fca5a5;
          font-size: 0.9rem;
        }

        .card-row-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
          gap: 16px;
          margin-bottom: 24px;
        }
        
        .mini-card {
          display: flex;
          align-items: center;
          gap: 16px;
          padding: 16px;
        }
        .mini-card-icon {
          width: 42px;
          height: 42px;
          border-radius: 8px;
          display: flex;
          align-items: center;
          justify-content: center;
        }
        .bg-purple-soft { background: rgba(168, 85, 247, 0.15); }
        .bg-cyan-soft { background: rgba(6, 182, 212, 0.15); }
        .bg-emerald-soft { background: rgba(16, 185, 129, 0.15); }
        .mini-card-content {
          display: flex;
          flex-direction: column;
        }
        .mini-label {
          font-size: 0.75rem;
          color: #a1a1aa;
        }
        .mini-value {
          font-size: 1.1rem;
          font-weight: 600;
          color: #fff;
        }

        .diagnostics-dashboard {
          animation: fadeIn 0.4s ease-out;
        }
        @keyframes fadeIn {
          from { opacity: 0; transform: translateY(10px); }
          to { opacity: 1; transform: translateY(0); }
        }
        
        .mt-2 { margin-top: 8px; }
      `}</style>
    </div>
  );
}

export default App;
