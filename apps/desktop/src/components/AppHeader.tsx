import React, { useState, useEffect, useRef } from "react";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { Moon, Sun, LogOut, Minus, Square, X, Compass, Bookmark, History, Settings, Box, Columns, PanelLeft, PanelRight, type LucideIcon } from "lucide-react";
import { useAuthStore } from "../stores/authStore";
import { useThemeStore } from "../stores/themeStore";
import { useNavStore } from "../stores/navStore";
import { useReviewStore } from "../stores/reviewStore";
import { useRoomStore } from "../stores/roomStore";

type NavKey = "workspace" | "3d-workspace" | "standards" | "history" | "settings";

interface NavTabProps {
  navKey: NavKey;
  label: string;
  icon: LucideIcon;
  isActive: boolean;
  activeColor: string;
  onSelect: (key: NavKey) => void;
}

const NavTab: React.FC<NavTabProps> = ({ navKey, label, icon: Icon, isActive, activeColor, onSelect }) => (
  <button
    role="tab"
    aria-selected={isActive}
    aria-controls={`${navKey}-panel`}
    tabIndex={0}
    onClick={() => onSelect(navKey)}
    className={`flex items-center gap-2 h-full px-3.5 py-1 rounded-full text-xs md:text-sm font-semibold transition-all duration-200 shrink-0 ${
      isActive
        ? "text-text-primary font-bold"
        : "text-text-muted hover:text-text-primary"
    }`}
  >
    <Icon size={15} className={`transition-transform duration-200 shrink-0 ${isActive ? `${activeColor} scale-110` : ""}`} />
    <span className="whitespace-nowrap">{label}</span>
  </button>
);

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
      case 'left': return <PanelLeft size={16} />;
      case 'right': return <PanelRight size={16} />;
      default: return <Columns size={16} />;
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
      data-tauri-drag-region
      className="flex justify-between items-center h-14 bg-bg-topbar border-b border-border-color select-none relative z-[9999] px-3"
    >
      {/* LEFT: Branding */}
      <div
        data-tauri-drag-region
        className="flex items-center gap-3 px-3 h-full cursor-default"
      >
        <div className="flex items-center justify-center w-10 h-10 rounded-2xl bg-accent-cyan/10 border border-accent-cyan/15">
          <Box size={20} strokeWidth={1.75} className="text-accent-cyan" />
        </div>
        <span className="text-sm font-black tracking-wider uppercase text-text-primary">
          KMTI Checker
        </span>
      </div>

      {/* CENTER: Draggable space & Navigation Tabs */}
      <div
        data-tauri-drag-region
        className="flex-1 h-full flex items-center justify-center gap-1"
      >
        {isAuthenticated && (
          <div
            role="tablist"
            aria-label="Workspace Navigation"
            className="flex items-center gap-[6px] h-[40px] px-2"
          >
            <NavTab navKey="workspace" label="2D Workspace" icon={Compass} activeColor="text-accent-cyan" isActive={currentNav === "workspace"} onSelect={setCurrentNav} />
            <NavTab navKey="3d-workspace" label="3D Workspace" icon={Box} activeColor="text-violet-400" isActive={currentNav === "3d-workspace"} onSelect={setCurrentNav} />
            {user?.role === "admin" && (
              <NavTab navKey="standards" label="Standards" icon={Bookmark} activeColor="text-rose-400" isActive={currentNav === "standards"} onSelect={setCurrentNav} />
            )}
            <NavTab navKey="history" label="History" icon={History} activeColor="text-amber-400" isActive={currentNav === "history"} onSelect={setCurrentNav} />
            <NavTab navKey="settings" label="Settings" icon={Settings} activeColor="text-slate-500" isActive={currentNav === "settings"} onSelect={setCurrentNav} />
          </div>
        )}
      </div>

      {/* RIGHT: User Info & Actions */}
      <div className="flex items-center h-full">
        {isAuthenticated && (
          <div className="flex items-center gap-3 h-6 pr-4 mr-2 border-r border-border-color">
            {/* User Profile Badge */}
            <div className="flex items-center gap-2 px-2.5 py-0.5 rounded-full bg-bg-card border border-border-color">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              <span className="text-[11px] font-medium text-text-secondary">
                {user?.username || "Engineer"}
              </span>
            </div>

            {/* Layout Toggles (Only show in workspace when a room is active) */}
            {currentNav === "workspace" && activeRoom && (
              <div ref={layoutMenuRef} className="relative mr-1">
                <button
                  title="Change Layout"
                  onClick={() => setIsLayoutMenuOpen(!isLayoutMenuOpen)}
                  className={`flex p-1.5 rounded-md border transition-all duration-200 ${
                    isLayoutMenuOpen
                      ? "text-accent-cyan bg-accent-cyan/10 border-accent-cyan/30"
                      : "text-text-muted border-border-color hover:text-text-primary hover:bg-sidebar-item-hover"
                  }`}
                >
                  {getActiveLayoutIcon()}
                </button>

                {isLayoutMenuOpen && (
                  <div className="absolute top-full right-0 mt-2 flex flex-col gap-1 p-1.5 glass-panel rounded-xl shadow-2xl z-[99999] animate-in fade-in slide-in-from-top-2 duration-150">
                    <button
                      onClick={() => { setActiveLayoutPreset('grid'); setIsLayoutMenuOpen(false); }}
                      className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-all duration-150 ${
                        activeLayoutPreset === 'grid' ? "text-accent-cyan bg-accent-cyan/15 border border-accent-cyan/20" : "text-text-muted hover:text-text-primary hover:bg-sidebar-item-hover"
                      }`}
                    >
                      <Columns size={14} /> Default Grid
                    </button>
                    <button
                      onClick={() => { setActiveLayoutPreset('left'); setIsLayoutMenuOpen(false); }}
                      className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-all duration-150 ${
                        activeLayoutPreset === 'left' ? "text-accent-cyan bg-accent-cyan/15 border border-accent-cyan/20" : "text-text-muted hover:text-text-primary hover:bg-sidebar-item-hover"
                      }`}
                    >
                      <PanelLeft size={14} /> Left Panel Focus
                    </button>
                    <button
                      onClick={() => { setActiveLayoutPreset('right'); setIsLayoutMenuOpen(false); }}
                      className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-all duration-150 ${
                        activeLayoutPreset === 'right' ? "text-accent-cyan bg-accent-cyan/15 border border-accent-cyan/20" : "text-text-muted hover:text-text-primary hover:bg-sidebar-item-hover"
                      }`}
                    >
                      <PanelRight size={14} /> Right Panel Focus
                    </button>
                  </div>
                )}
              </div>
            )}

            {/* Actions */}
            <button
              onClick={toggleTheme}
              title="Toggle Theme"
              className="flex p-1.5 rounded-md text-text-muted hover:bg-sidebar-item-hover transition-all duration-150 active:scale-95"
            >
              {theme === "hc-dark" ? (
                <Moon size={15} className="text-purple-400 fill-purple-400/20" />
              ) : (
                <Sun size={15} className="text-amber-500 fill-amber-400/20" />
              )}
            </button>
            <button
              onClick={() => logout()}
              title="Logout Portal"
              className="flex p-1.5 rounded-md text-text-muted hover:text-danger hover:bg-danger/10 transition-all duration-150 active:scale-95"
            >
              <LogOut size={15} />
            </button>
          </div>
        )}

        {/* Window Controls */}
        <div className="flex h-full">
          <button
            onClick={handleMinimize}
            className="w-[46px] h-full flex items-center justify-center text-text-muted hover:bg-sidebar-item-hover hover:text-text-primary transition-colors"
          >
            <Minus size={15} />
          </button>
          <button
            onClick={handleToggleMaximize}
            className="w-[46px] h-full flex items-center justify-center text-text-muted hover:bg-sidebar-item-hover hover:text-text-primary transition-colors"
          >
            <Square size={13} />
          </button>
          <button
            onClick={handleClose}
            className="w-[46px] h-full flex items-center justify-center text-text-muted hover:bg-red-600 hover:text-white transition-colors"
          >
            <X size={15} />
          </button>
        </div>
      </div>
    </div>
  );
};
