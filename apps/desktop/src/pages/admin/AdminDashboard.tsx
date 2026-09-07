import React, { useState } from "react";
import { UserManagement } from "./UserManagement";
import { SystemDiagnostics } from "./SystemDiagnostics";
import { AIConfiguration } from "./AIConfiguration";
import { BackupRecovery } from "./BackupRecovery";
import { StandardsAdministration } from "./StandardsAdministration";
import { AuditHistory } from "./AuditHistory";
import { CustomReportingEngine } from "./CustomReportingEngine";
import {
  Users,
  Database,
  Sliders,
  Archive,
  BookOpen,
  FileText
} from "lucide-react";

export const AdminDashboard: React.FC = () => {
  const [activeTab, setActiveTab] = useState<"diagnostics" | "users" | "standards" | "audits" | "ai" | "backups" | "reporting">("diagnostics");

  return (
    <div className="admin-dashboard-container">
      {/* 1. LEFT SIDEBAR (ADMIN CONTROL PANEL) */}
      <aside className="admin-sidebar">
        <nav className="sidebar-nav">
          {([
            { key: "diagnostics", icon: <Database size={22} />, label: "System Analytics" },
            { key: "users", icon: <Users size={22} />, label: "User Directory" },
            { key: "standards", icon: <BookOpen size={22} />, label: "Standards Library" },
            { key: "audits", icon: <FileText size={22} />, label: "Audit History" },
            { key: "reporting", icon: <FileText size={22} />, label: "Custom Reporting Engine" },
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
      </aside>

      {/* 2. MAIN CENTER CONTENT */}
      <main className={`admin-main-viewport ${activeTab !== "standards" ? "padded" : ""}`}>
        { activeTab === "diagnostics" && <SystemDiagnostics /> }
        { activeTab === "users" && <UserManagement /> }
        { activeTab === "standards" && <StandardsAdministration /> }
        { activeTab === "audits" && <AuditHistory /> }
        { activeTab === "reporting" && <CustomReportingEngine /> }
        { activeTab === "ai" && <AIConfiguration /> }
        { activeTab === "backups" && <BackupRecovery /> }
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

        .sidebar-nav {
          padding: 16px 8px 12px 8px;
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
          background: rgba(128, 128, 128, 0.08);
        }

        .nav-item.active {
          color: var(--text-primary);
          background: rgba(128, 128, 128, 0.15);
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

        /* Cohesive Global Header Styles across all Admin Subpages */
        .subpage-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 24px;
          padding-bottom: 18px;
          border-bottom: 1px solid var(--border-color);
        }

        .section-title {
          font-size: 1.45rem;
          font-weight: 700;
          color: var(--text-primary);
          line-height: 1.2;
          letter-spacing: -0.01em;
        }

        .section-desc {
          font-size: 0.82rem;
          color: var(--text-muted);
          margin-top: 5px;
          font-weight: 400;
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
