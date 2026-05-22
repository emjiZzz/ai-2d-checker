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
  Moon,
  Sun
} from "lucide-react";
import { useThemeStore } from "../../stores/themeStore";

export const AdminDashboard: React.FC = () => {
  const [activeTab, setActiveTab] = useState<"diagnostics" | "users" | "standards" | "ai" | "backups">("diagnostics");
  const { logout } = useAuthStore();
  const { theme, toggleTheme } = useThemeStore();

  return (
    <div className="admin-dashboard-container">
      {/* 1. LEFT SIDEBAR (ADMIN CONTROL PANEL) */}
      <aside className="admin-sidebar">
        <div className="sidebar-branding">
          <div className="brand-logo">
            <Cpu size={22} />
          </div>
        </div>

        <nav className="sidebar-nav">
          {([
            { key: "diagnostics", icon: <Database size={22} />, label: "System Analytics" },
            { key: "users", icon: <Users size={22} />, label: "User Directory" },
            { key: "standards", icon: <BookOpen size={22} />, label: "Standards Library" },
            { key: "ai", icon: <Sliders size={22} />, label: "AI Configurations" },
            { key: "backups", icon: <Archive size={22} />, label: "Snapshots & Backups" },
          ] as const).map(({ key, icon, label }) => (
            <button
              key={key}
              className={`nav-item ${activeTab === key ? "active" : ""}`}
              onClick={() => setActiveTab(key)}
              data-tooltip={label}
            >
              {icon}
            </button>
          ))}
        </nav>

        <div className="sidebar-footer">
          <button
            className="theme-toggle-btn nav-item"
            onClick={toggleTheme}
            data-tooltip="Toggle Theme"
          >
            {theme === "hc-dark" ? <Moon size={22} /> : <Sun size={22} />}
          </button>
          <button
            className="btn-logout nav-item"
            onClick={() => logout()}
            data-tooltip="Logout Session"
          >
            <LogOut size={22} />
          </button>
        </div>
      </aside>

      {/* 2. MAIN CENTER CONTENT */}
      <main className={`admin-main-viewport ${activeTab !== "standards" ? "padded" : ""}`}>
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
          width: 60px;
          height: 100%;
          background: var(--bg-card);
          border-right: 1px solid var(--border-color);
          display: flex;
          flex-direction: column;
          flex-shrink: 0;
          overflow: visible;
          position: relative;
          z-index: 10;
        }

        .sidebar-branding {
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 16px 8px;
          border-bottom: 1px solid var(--border-color);
          min-height: 60px;
        }

        .brand-logo {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 44px;
          height: 44px;
          border-radius: 8px;
          background: rgba(0, 229, 255, 0.1);
          border: 1px solid rgba(0, 229, 255, 0.25);
          box-shadow: 0 2px 10px rgba(0, 229, 255, 0.2);
          color: #00e5ff;
        }

        .sidebar-nav {
          padding: 12px 8px;
          display: flex;
          flex-direction: column;
          gap: 8px;
          flex-grow: 1;
        }

        .nav-item {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 44px;
          height: 44px;
          margin: 0 auto;
          background: transparent;
          border: none;
          color: var(--text-muted);
          cursor: pointer;
          border-radius: 8px;
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
          background: var(--sidebar-item-hover, rgba(255, 255, 255, 0.08));
        }

        .nav-item.active {
          color: #00e5ff;
          background: rgba(0, 229, 255, 0.1);
          border: 1px solid rgba(0, 229, 255, 0.15);
          border-left: 3px solid #00e5ff;
          padding-left: 13px; /* adjusted to account for border-left */
        }

        .sidebar-footer {
          padding: 20px 8px;
          border-top: 1px solid var(--border-color);
          display: flex;
          flex-direction: column;
          gap: 12px;
          align-items: center;
        }

        .btn-logout.nav-item {
          color: #ef4444;
        }

        .btn-logout.nav-item:hover {
          background: rgba(239, 68, 68, 0.1);
          color: #fca5a5;
        }

        .admin-main-viewport {
          flex-grow: 1;
          height: 100%;
          min-height: 0;
          overflow-y: auto;
          background: var(--bg-dark);
          padding: 30px 0;
          box-sizing: border-box;
        }

        .admin-main-viewport.padded {
          padding: 30px 32px;
        }

        /* Override dashed borders on admin dashboard subpages to match standard solid cards */
        .admin-subpage .card.settings-card {
          border: 1px solid var(--border-color) !important;
          border-radius: 14px !important;
          padding: 20px !important;
          box-shadow: 0 8px 30px rgba(0, 0, 0, 0.03), 0 1px 3px rgba(0, 0, 0, 0.02) !important;
        }
        
        [data-theme="hc-dark"] .admin-subpage .card.settings-card {
          box-shadow: 0 8px 32px rgba(0, 0, 0, 0.6), 0 0 1px rgba(255, 255, 255, 0.1) !important;
        }

        /* Ensure responsive layout for the grids on tablets/smaller views */
        @media (max-width: 1024px) {
          .diagnostics-dashboard-grid,
          .admin-grid-2 {
            grid-template-columns: 1fr !important;
          }
        }
      `}</style>
    </div>
  );
};
