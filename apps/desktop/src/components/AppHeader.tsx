import React from "react";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { Moon, Sun, LogOut, Minus, Square, X, Cpu, Compass, Bookmark, History, Settings } from "lucide-react";
import { useAuthStore } from "../stores/authStore";
import { useThemeStore } from "../stores/themeStore";
import { useWorkspaceStore } from "../stores/workspaceStore";

export const AppHeader: React.FC = () => {
  const { user, logout, isAuthenticated } = useAuthStore();
  const { theme, toggleTheme } = useThemeStore();
  const currentNav = useWorkspaceStore((s) => s.currentNav);
  const setCurrentNav = useWorkspaceStore((s) => s.setCurrentNav);
  const isAdmin = user?.role === "admin";

  const handleMinimize = () => getCurrentWindow().minimize();
  const handleToggleMaximize = async () => {
    try {
      const window = getCurrentWindow();
      const maximized = await window.isMaximized();
      if (maximized) {
        await window.unmaximize();
      } else {
        await window.maximize();
      }
    } catch (e) { }
  };
  const handleClose = () => getCurrentWindow().close();

  return (
    <div
      className="app-header"
      data-tauri-drag-region
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        height: "44px",
        background: "var(--bg-sidebar)",
        borderBottom: "1px solid var(--border-color)",
        userSelect: "none",
        zIndex: 9999
      }}
    >
      {/* LEFT: Branding */}
      <div
        className="header-branding"
        data-tauri-drag-region
        style={{ display: "flex", alignItems: "center", gap: "10px", padding: "0 16px", height: "100%" }}
      >
        <Cpu size={18} style={{ color: "var(--accent-cyan)" }} />
        <div style={{ display: "flex", flexDirection: "column", justifyContent: "center" }}>
          <span style={{ fontSize: "0.9rem", fontWeight: 700, lineHeight: 1.2, color: "var(--text-primary)" }}>KMTI Checker</span>
        </div>
      </div>

      {/* CENTER: Draggable padding */}
      <div data-tauri-drag-region style={{ flexGrow: 1, height: "100%" }}></div>

      {/* CENTER: Horizontal Navigation Menu */}
      <div style={{ display: "flex", alignItems: "center", gap: "4px", height: "100%", justifyContent: "center" }}>
        {isAuthenticated && ([
          { key: 'workspace', icon: <Compass size={13} />, label: 'Audit Workspace' },
          ...(isAdmin ? [{ key: 'standards' as const, icon: <Bookmark size={13} />, label: 'Standards' }] : []),
          { key: 'history', icon: <History size={13} />, label: 'History Archive' },
          { key: 'settings', icon: <Settings size={13} />, label: 'Settings' },
        ] as const).map(({ key, icon, label }) => (
          <button
            key={key}
            onClick={() => setCurrentNav(key)}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "6px",
              height: "28px",
              padding: "0 12px",
              borderRadius: "6px",
              border: "none",
              background: currentNav === key ? "rgba(0, 229, 255, 0.08)" : "transparent",
              color: currentNav === key ? "var(--accent-cyan)" : "var(--text-muted)",
              cursor: "pointer",
              fontSize: "0.78rem",
              fontWeight: 600,
              transition: "all 0.15s ease",
            }}
            className="nav-header-btn"
          >
            {icon}
            <span>{label}</span>
          </button>
        ))}
      </div>

      {/* CENTER RIGHT: Draggable padding */}
      <div data-tauri-drag-region style={{ flexGrow: 1, height: "100%" }}></div>

      {/* RIGHT: User Info & Actions */}
      <div style={{ display: "flex", alignItems: "center", height: "100%" }}>
        {isAuthenticated && (
          <div style={{ display: "flex", alignItems: "center", gap: "16px", paddingRight: "16px", borderRight: "1px solid var(--border-color)", height: "24px", marginRight: "8px" }}>
            {/* User Profile */}
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <div style={{ display: "flex", flexDirection: "column", justifyContent: "center" }}>
                <span style={{ fontSize: "0.75rem", fontWeight: 400, color: "var(--accent-cyan)", lineHeight: 1, textTransform: "uppercase" }}>{user?.username || "Engineer"}</span>
              </div>
            </div>

            {/* Actions */}
            <button
              onClick={toggleTheme}
              title="Toggle Theme"
              className="action-btn theme-toggle-btn"
              style={{ background: "transparent", border: "none", color: "var(--text-muted)", cursor: "pointer", display: "flex", padding: "4px", borderRadius: "4px", transition: "all 0.2s" }}
            >
              <span className="icon-default">{theme === "hc-dark" ? <Moon size={16} /> : <Sun size={16} />}</span>
              <span className="icon-hover">{theme === "hc-dark" ? <Sun size={16} /> : <Moon size={16} />}</span>
            </button>
            <button
              onClick={() => logout()}
              title="Logout Portal"
              className="action-btn logout-btn"
              style={{ background: "transparent", border: "none", color: "var(--text-muted)", cursor: "pointer", display: "flex", padding: "4px", borderRadius: "4px", transition: "all 0.2s" }}
            >
              <LogOut size={16} />
            </button>
          </div>
        )}

        {/* Window Controls */}
        <div style={{ display: "flex", height: "100%" }}>
          <button
            onClick={handleMinimize}
            className="window-control-btn"
            style={{ width: "46px", height: "100%", background: "transparent", border: "none", color: "var(--text-muted)", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }}
          >
            <Minus size={16} />
          </button>
          <button
            onClick={handleToggleMaximize}
            className="window-control-btn"
            style={{ width: "46px", height: "100%", background: "transparent", border: "none", color: "var(--text-muted)", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }}
          >
            <Square size={14} />
          </button>
          <button
            onClick={handleClose}
            className="window-control-btn close-btn"
            style={{ width: "46px", height: "100%", background: "transparent", border: "none", color: "var(--text-muted)", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }}
          >
            <X size={16} />
          </button>
        </div>
      </div>
      <style>{`
        .action-btn:hover {
          color: var(--text-primary) !important;
          background: rgba(128, 128, 128, 0.1) !important;
        }
        .logout-btn:hover {
          color: #ef4444 !important; /* Premium red */
          background: rgba(239, 68, 68, 0.08) !important;
        }
        .theme-toggle-btn .icon-hover {
          display: none;
        }
        .theme-toggle-btn:hover .icon-default {
          display: none;
        }
        .theme-toggle-btn:hover .icon-hover {
          display: flex;
          color: #f59e0b !important; /* Golden yellow */
          filter: drop-shadow(0 0 6px rgba(245, 158, 11, 0.65));
        }
        .window-control-btn:hover {
          background: rgba(128, 128, 128, 0.15) !important;
          color: var(--text-primary) !important;
        }
        .window-control-btn.close-btn:hover {
          background: #e81123 !important;
          color: white !important;
        }
        .nav-header-btn {
          border: 1px solid transparent !important;
        }
        .nav-header-btn:hover {
          color: var(--text-primary) !important;
          background: rgba(255, 255, 255, 0.04) !important;
        }
        .nav-header-btn:active {
          transform: scale(0.97);
        }
      `}</style>
    </div>
  );
};
