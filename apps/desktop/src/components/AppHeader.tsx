import React, { useState, useEffect, useRef } from "react";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { Moon, Sun, LogOut, Minus, Square, X, Cpu, Compass, Bookmark, History, Settings, Box, Columns, PanelLeft, PanelRight } from "lucide-react";
import { useAuthStore } from "../stores/authStore";
import { useThemeStore } from "../stores/themeStore";
import { useNavStore } from "../stores/navStore";
import { useReviewStore } from "../stores/reviewStore";
import { useRoomStore } from "../stores/roomStore";

export const AppHeader: React.FC = () => {
  const { user, logout, isAuthenticated } = useAuthStore();
  const { theme, toggleTheme } = useThemeStore();
  const { currentNav, setCurrentNav } = useNavStore();
  const activeLayoutPreset = useReviewStore(s => s.activeLayoutPreset);
  const setActiveLayoutPreset = useReviewStore(s => s.setActiveLayoutPreset);
  const activeRoom = useRoomStore(s => s.activeRoom);

  const [isLayoutMenuOpen, setIsLayoutMenuOpen] = useState(false);
  const layoutMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (layoutMenuRef.current && !layoutMenuRef.current.contains(event.target as Node)) {
        setIsLayoutMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const getActiveLayoutIcon = () => {
    switch (activeLayoutPreset) {
      case 'left': return <PanelLeft size={15} />;
      case 'right': return <PanelRight size={15} />;
      default: return <Columns size={15} />;
    }
  };

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

      {/* CENTER: Draggable space & Sleek Navigation Tabs */}
      <div 
        data-tauri-drag-region 
        style={{ 
          flexGrow: 1, 
          height: "100%", 
          display: "flex", 
          alignItems: "center", 
          justifyContent: "center",
          gap: "4px"
        }}
      >
        {isAuthenticated && (
          <div 
            role="tablist"
            aria-label="Workspace Navigation"
            style={{ display: "flex", gap: "2px", height: "30px", background: "rgba(0,0,0,0.2)", borderRadius: "6px", padding: "2px", border: "1px solid var(--border-color)" }}
          >
            <button
              role="tab"
              aria-selected={currentNav === "workspace"}
              aria-controls="workspace-panel"
              tabIndex={0}
              onClick={() => setCurrentNav("workspace")}
              className={`header-nav-tab ${currentNav === "workspace" ? "active" : ""}`}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "6px",
                padding: "0 12px",
                height: "100%",
                background: currentNav === "workspace" ? "rgba(128, 128, 128, 0.18)" : "transparent",
                border: "none",
                borderRadius: "4px",
                color: currentNav === "workspace" ? "var(--text-primary)" : "var(--text-muted)",
                fontSize: "0.78rem",
                fontWeight: 600,
                cursor: "pointer",
                transition: "all 0.15s"
              }}
            >
              <Compass size={13} />
              2D Workspace
            </button>

            <button
              role="tab"
              aria-selected={currentNav === "3d-workspace"}
              aria-controls="3d-workspace-panel"
              tabIndex={0}
              onClick={() => setCurrentNav("3d-workspace")}
              className={`header-nav-tab ${currentNav === "3d-workspace" ? "active" : ""}`}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "6px",
                padding: "0 12px",
                height: "100%",
                background: currentNav === "3d-workspace" ? "rgba(168, 85, 247, 0.18)" : "transparent",
                border: "none",
                borderRadius: "4px",
                color: currentNav === "3d-workspace" ? "#c084fc" : "var(--text-muted)",
                fontSize: "0.78rem",
                fontWeight: 600,
                cursor: "pointer",
                transition: "all 0.15s"
              }}
            >
              <Box size={13} style={{ color: currentNav === "3d-workspace" ? "#c084fc" : "var(--text-muted)" }} />
              3D Workspace
            </button>

            {user?.role === "admin" && (
              <button
                onClick={() => setCurrentNav("standards")}
                className={`header-nav-tab ${currentNav === "standards" ? "active" : ""}`}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "6px",
                  padding: "0 12px",
                  height: "100%",
                  background: currentNav === "standards" ? "rgba(128, 128, 128, 0.18)" : "transparent",
                  border: "none",
                  borderRadius: "4px",
                  color: currentNav === "standards" ? "var(--text-primary)" : "var(--text-muted)",
                  fontSize: "0.78rem",
                  fontWeight: 600,
                  cursor: "pointer",
                  transition: "all 0.15s"
                }}
              >
                <Bookmark size={13} />
                Standards
              </button>
            )}

            <button
              role="tab"
              aria-selected={currentNav === "history"}
              aria-controls="history-panel"
              tabIndex={0}
              onClick={() => setCurrentNav("history")}
              className={`header-nav-tab ${currentNav === "history" ? "active" : ""}`}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "6px",
                padding: "0 12px",
                height: "100%",
                background: currentNav === "history" ? "rgba(128, 128, 128, 0.18)" : "transparent",
                border: "none",
                borderRadius: "4px",
                color: currentNav === "history" ? "var(--text-primary)" : "var(--text-muted)",
                fontSize: "0.78rem",
                fontWeight: 600,
                cursor: "pointer",
                transition: "all 0.15s"
              }}
            >
              <History size={13} />
              History
            </button>

            <button
              role="tab"
              aria-selected={currentNav === "settings"}
              aria-controls="settings-panel"
              tabIndex={0}
              onClick={() => setCurrentNav("settings")}
              className={`header-nav-tab ${currentNav === "settings" ? "active" : ""}`}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "6px",
                padding: "0 12px",
                height: "100%",
                background: currentNav === "settings" ? "rgba(128, 128, 128, 0.18)" : "transparent",
                border: "none",
                borderRadius: "4px",
                color: currentNav === "settings" ? "var(--text-primary)" : "var(--text-muted)",
                fontSize: "0.78rem",
                fontWeight: 600,
                cursor: "pointer",
                transition: "all 0.15s"
              }}
            >
              <Settings size={13} />
              Settings
            </button>
          </div>
        )}
      </div>

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

            {/* Layout Toggles (Only show in workspace when a room is active) */}
            {currentNav === "workspace" && activeRoom && (
              <div ref={layoutMenuRef} style={{ position: "relative", marginRight: "6px" }}>
                <button 
                  className="layout-btn active" 
                  title="Change Layout" 
                  onClick={() => setIsLayoutMenuOpen(!isLayoutMenuOpen)}
                >
                  {getActiveLayoutIcon()}
                </button>
                
                {isLayoutMenuOpen && (
                  <div style={{ 
                    position: "absolute", 
                    top: "100%", 
                    right: 0, 
                    marginTop: "8px", 
                    background: "var(--bg-card)", 
                    border: "1px solid var(--border-color)", 
                    borderRadius: "6px", 
                    padding: "4px",
                    display: "flex", 
                    flexDirection: "column",
                    gap: "2px",
                    boxShadow: "0 4px 12px rgba(0,0,0,0.5)",
                    zIndex: 99999
                  }}>
                    <button 
                      className={`layout-dropdown-btn ${activeLayoutPreset === 'grid' ? 'active' : ''}`} 
                      onClick={() => { setActiveLayoutPreset('grid'); setIsLayoutMenuOpen(false); }}
                    >
                      <Columns size={14} /> <span style={{fontSize: "0.75rem", fontWeight: 600}}>Default</span>
                    </button>
                    <button 
                      className={`layout-dropdown-btn ${activeLayoutPreset === 'left' ? 'active' : ''}`} 
                      onClick={() => { setActiveLayoutPreset('left'); setIsLayoutMenuOpen(false); }}
                    >
                      <PanelLeft size={14} /> <span style={{fontSize: "0.75rem", fontWeight: 600}}>Left Panel</span>
                    </button>
                    <button 
                      className={`layout-dropdown-btn ${activeLayoutPreset === 'right' ? 'active' : ''}`} 
                      onClick={() => { setActiveLayoutPreset('right'); setIsLayoutMenuOpen(false); }}
                    >
                      <PanelRight size={14} /> <span style={{fontSize: "0.75rem", fontWeight: 600}}>Right Panel</span>
                    </button>
                  </div>
                )}
              </div>
            )}

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
        .layout-btn {
          background: transparent;
          border: 1px solid transparent;
          color: var(--text-muted);
          cursor: pointer;
          display: flex;
          padding: 4px;
          border-radius: 4px;
          transition: all 0.2s;
        }
        .layout-btn:hover {
          background: rgba(128, 128, 128, 0.15);
          color: var(--text-primary);
        }
        .layout-btn.active {
          background: rgba(255, 255, 255, 0.1);
          color: var(--text-primary);
          border: 1px solid rgba(255, 255, 255, 0.1);
        }
        .layout-dropdown-btn {
          background: transparent;
          border: none;
          color: var(--text-muted);
          cursor: pointer;
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 6px 12px;
          border-radius: 4px;
          transition: all 0.2s;
          white-space: nowrap;
        }
        .layout-dropdown-btn:hover {
          background: rgba(128, 128, 128, 0.15);
          color: var(--text-primary);
        }
        .layout-dropdown-btn.active {
          color: var(--accent-cyan);
          background: rgba(0, 229, 255, 0.05);
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
