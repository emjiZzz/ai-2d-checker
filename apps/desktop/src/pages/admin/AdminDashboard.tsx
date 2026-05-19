import React, { useState } from "react";
import { useAuthStore } from "../../stores/authStore";
import { UserManagement } from "./UserManagement";
import { SystemDiagnostics } from "./SystemDiagnostics";
import { AIConfiguration } from "./AIConfiguration";
import { BackupRecovery } from "./BackupRecovery";
import { StandardsAdministration } from "./StandardsAdministration";
import {
  Cpu,
  Users,
  Database,
  Sliders,
  Archive,
  BookOpen,
  LogOut,
  ShieldCheck,
  Moon,
  Sun
} from "lucide-react";
import { useThemeStore } from "../../stores/themeStore";

export const AdminDashboard: React.FC = () => {
  const [activeTab, setActiveTab] = useState<"diagnostics" | "users" | "standards" | "ai" | "backups">("diagnostics");
  const { user, logout } = useAuthStore();
  const { theme, toggleTheme } = useThemeStore();

  return (
    <div className="admin-dashboard-container">
      {/* 1. LEFT SIDEBAR */}
      <aside className="admin-sidebar">
        <div className="sidebar-branding">
          <div className="brand-logo">
            <Cpu size={20} style={{ color: "#a855f7" }} />
          </div>
          <div className="brand-text">
            <h1 className="brand-title">AI-2D-Checker</h1>
            <span className="brand-badge">ADMIN CONTROL</span>
          </div>
        </div>

        <nav className="sidebar-nav">
          <button
            className={`nav-item ${activeTab === "diagnostics" ? "active" : ""}`}
            onClick={() => setActiveTab("diagnostics")}
          >
            <Database size={16} />
            <span>System Analytics</span>
          </button>

          <button
            className={`nav-item ${activeTab === "users" ? "active" : ""}`}
            onClick={() => setActiveTab("users")}
          >
            <Users size={16} />
            <span>User Directory</span>
          </button>

          <button
            className={`nav-item ${activeTab === "standards" ? "active" : ""}`}
            onClick={() => setActiveTab("standards")}
          >
            <BookOpen size={16} />
            <span>Standards Library</span>
          </button>

          <button
            className={`nav-item ${activeTab === "ai" ? "active" : ""}`}
            onClick={() => setActiveTab("ai")}
          >
            <Sliders size={16} />
            <span>AI Configurations</span>
          </button>

          <button
            className={`nav-item ${activeTab === "backups" ? "active" : ""}`}
            onClick={() => setActiveTab("backups")}
          >
            <Archive size={16} />
            <span>Snapshots & Backups</span>
          </button>
        </nav>

        <div className="sidebar-footer">
          <div className="user-profile">
            <ShieldCheck size={16} style={{ color: "#a855f7" }} />
            <div className="profile-details">
              <span className="profile-name">{user?.username || "Admin"}</span>
              <span className="profile-role">Root Administrator</span>
            </div>
          </div>

          <div style={{ display: "flex", gap: "8px", marginTop: "12px" }}>
            <button 
              className="theme-toggle-btn" 
              onClick={toggleTheme} 
              title="Toggle Theme" 
              style={{ 
                background: "transparent", 
                border: "1px solid var(--border-color)", 
                padding: "10px", 
                borderRadius: "6px", 
                color: "var(--text-muted)",
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                justifyContent: "center"
              }}
            >
              {theme === "hc-dark" ? <Moon size={16} /> : <Sun size={16} />}
            </button>
            <button className="btn-logout" onClick={() => logout()} title="Logout Session" style={{ flexGrow: 1 }}>
              <LogOut size={16} />
              <span>Logout</span>
            </button>
          </div>
        </div>
      </aside>

      {/* 2. MAIN CENTER CONTENT */}
      <main className="admin-main-viewport">
        {activeTab === "diagnostics" && <SystemDiagnostics />}
        {activeTab === "users" && <UserManagement />}
        {activeTab === "standards" && <StandardsAdministration />}
        {activeTab === "ai" && <AIConfiguration />}
        {activeTab === "backups" && <BackupRecovery />}
      </main>

      <style>{`
        .admin-dashboard-container {
          display: flex;
          width: 100vw;
          height: 100vh;
          background: var(--bg-dark);
          overflow: hidden;
          font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
          color: var(--text-primary, #e4e4e7);
        }

        .admin-sidebar {
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
          background: rgba(168, 85, 247, 0.1);
          border: 1px solid rgba(168, 85, 247, 0.2);
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
          color: #c084fc;
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

        .admin-main-viewport {
          flex-grow: 1;
          height: 100%;
          overflow-y: auto;
          background: var(--bg-dark);
          padding: 30px 0;
        }
      `}</style>
    </div>
  );
};
