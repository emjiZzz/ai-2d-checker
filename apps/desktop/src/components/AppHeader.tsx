import React, { useState, useEffect, useRef } from "react";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { LogOut, Minus, Square, X, Compass, Bookmark, History, Settings, Box, Columns, PanelLeft, PanelRight, Database, type LucideIcon } from "lucide-react";
import kmtiLogo from "../assets/kmti_logo.png";
import { useAuthStore } from "../stores/authStore";
import { useNavStore } from "../stores/navStore";
import { useReviewStore } from "../stores/reviewStore";
import { useRoomStore } from "../stores/roomStore";
import { ClusterUpgradeModal } from "./admin/ClusterUpgradeModal";
import { fetchDatabaseStatus, DatabaseStatusResponse } from "../services/databaseApi";
import { isPrototypeMode } from "../config/features";

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
    className={`flex items-center gap-1.5 h-full px-2.5 py-0.5 rounded-sm text-xs font-semibold transition-all duration-150 shrink-0 ${
      isActive
        ? "text-text-primary font-bold bg-bg-card shadow-xs border border-border-color"
        : "text-text-muted hover:text-text-primary hover:bg-sidebar-item-hover"
    }`}
  >
    <Icon size={15} className={`transition-transform duration-200 shrink-0 ${isActive ? `${activeColor} scale-110` : ""}`} />
    <span className="whitespace-nowrap">{label}</span>
  </button>
);

export const AppHeader: React.FC = () => {
  const { user, logout, isAuthenticated } = useAuthStore();
  const { currentNav, setCurrentNav } = useNavStore();
  const activeLayoutPreset = useReviewStore(s => s.activeLayoutPreset);
  const setActiveLayoutPreset = useReviewStore(s => s.setActiveLayoutPreset);
  const activeRoom = useRoomStore(s => s.activeRoom);

  const [isLayoutMenuOpen, setIsLayoutMenuOpen] = useState(false);
  const [isUpgradeModalOpen, setIsUpgradeModalOpen] = useState(false);
  const [dbStatus, setDbStatus] = useState<DatabaseStatusResponse | null>(null);
  const layoutMenuRef = useRef<HTMLDivElement>(null);

  const loadDbStatus = async () => {
    if (user?.role === "admin") {
      try {
        const res = await fetchDatabaseStatus();
        if (res?.connected) {
          setDbStatus(res);
        }
      } catch {
        // Silently ignore if backend is still initializing
      }
    }
  };

  useEffect(() => {
    loadDbStatus();
    (window as any).__openClusterUpgradeModal = () => {
      setIsUpgradeModalOpen(true);
    };
    const interval = setInterval(loadDbStatus, 45000);
    return () => {
      delete (window as any).__openClusterUpgradeModal;
      clearInterval(interval);
    };
  }, [user?.role, isAuthenticated]);

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
      className="flex justify-between items-center h-10 bg-bg-topbar border-b border-border-color select-none relative z-[9999] px-2.5"
    >
      {/* LEFT: Branding */}
      <div
        data-tauri-drag-region
        className="flex items-center gap-2 px-2 h-full cursor-default"
      >
        <img src={kmtiLogo} alt="KMTI Logo" className="h-6 w-auto object-contain shrink-0" />
        <span className="text-xs font-black tracking-wider uppercase text-text-primary">
          KMTI Checker
        </span>
      </div>

      {/* CENTER: Draggable space & Navigation Tabs */}
      <div
        data-tauri-drag-region
        className="flex-1 h-full flex items-center justify-center gap-1"
      >
        {!isPrototypeMode() && isAuthenticated && (
          <div
            role="tablist"
            aria-label="Workspace Navigation"
            className="flex items-center gap-[4px] h-[28px] px-1"
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
        {!isPrototypeMode() && isAuthenticated && (
          <div className="flex items-center gap-3 h-6 pr-4 mr-2 border-r border-border-color">
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

            {/* Admin Cloud Cluster Storage Badge */}
            {user?.role === "admin" && dbStatus?.storage && (
              <button
                onClick={() => setIsUpgradeModalOpen(true)}
                title="MongoDB Atlas Cluster Storage (Admin View) — Click to view capacity & upgrade details"
                className={`flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-semibold border transition-all duration-150 ${
                  dbStatus.storage.is_warning
                    ? "bg-rose-500/15 border-rose-500/30 text-rose-300 hover:bg-rose-500/25 animate-pulse"
                    : dbStatus.mode === "cloud_primary"
                    ? "bg-amber-500/10 border-amber-500/25 text-amber-300 hover:bg-amber-500/20"
                    : "bg-emerald-500/10 border-emerald-500/25 text-emerald-300 hover:bg-emerald-500/20"
                }`}
              >
                <Database size={12} className={dbStatus.storage.is_warning ? "text-rose-400" : "text-amber-400"} />
                <span className="font-mono text-[10px] font-bold">
                  {dbStatus.mode === "cloud_primary" ? `${dbStatus.storage.data_size_mb} MB / 512 MB` : "Local DB"}
                </span>
              </button>
            )}

            {/* Actions */}
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

      {/* Admin Cluster Upgrade Modal */}
      {(user?.role === "admin" || isUpgradeModalOpen) && (
        <ClusterUpgradeModal
          isOpen={isUpgradeModalOpen}
          onClose={() => setIsUpgradeModalOpen(false)}
          storage={dbStatus?.storage ?? null}
          mode={dbStatus?.mode ?? "cloud_primary"}
          onRefresh={loadDbStatus}
        />
      )}
    </div>
  );
};
