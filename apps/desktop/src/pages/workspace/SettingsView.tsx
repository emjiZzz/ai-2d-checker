import React from "react";
import { Moon, Sun, Check } from "lucide-react";
import { SystemDiagnostics } from "../../components/SystemDiagnostics";
import { LearningPanel } from "../../components/settings/LearningPanel";
import { useThemeStore } from "../../stores/themeStore";

/**
 * SettingsView — User Preferences, Compliance Settings form, Active Learning, and live System Connection panel.
 */
export const SettingsView: React.FC = () => {
  const { theme, setTheme } = useThemeStore();

  return (
    <main className="flex-grow h-full min-h-0 overflow-y-auto bg-bg-dark py-8 px-8 box-border">
      {/* User Preferences */}
      <div className="mb-8">
        <h2 className="text-xl font-extrabold text-text-primary m-0 tracking-tight">User Preferences</h2>
        <p className="text-xs text-text-muted mt-1 leading-relaxed">Personalize workspace visual appearance and interface settings.</p>

        <div className="bg-bg-card border border-border-color rounded-xl p-6 shadow-sm mt-4">
          <h3 className="text-sm font-bold border-l-[3px] border-accent-cyan pl-2.5 text-text-primary m-0 mb-4">
            Theme Appearance
          </h3>
          <p className="text-xs text-text-muted mb-4">
            Choose visual color scheme for the application workspace and canvas views.
          </p>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 max-w-xl">
            {/* Dark Theme Option */}
            <button
              type="button"
              onClick={() => setTheme("hc-dark")}
              className={`flex items-center justify-between p-4 rounded-xl border transition-all duration-200 text-left ${
                theme === "hc-dark"
                  ? "border-accent-cyan bg-accent-cyan/10 shadow-[0_0_12px_rgba(0,229,255,0.12)]"
                  : "border-border-color bg-bg-sidebar hover:border-text-muted/40 hover:bg-sidebar-item-hover"
              }`}
            >
              <div className="flex items-center gap-3">
                <div className={`p-2.5 rounded-lg ${theme === "hc-dark" ? "bg-purple-500/20 text-purple-400" : "bg-bg-card text-text-muted"}`}>
                  <Moon size={20} />
                </div>
                <div>
                  <div className="text-xs font-bold text-text-primary flex items-center gap-2">
                    High Contrast Dark
                    {theme === "hc-dark" && <span className="text-[10px] bg-accent-cyan/20 text-accent-cyan px-2 py-0.5 rounded-full font-semibold">Active</span>}
                  </div>
                  <div className="text-[11px] text-text-muted mt-0.5">Dark background for reduced eye strain</div>
                </div>
              </div>
              {theme === "hc-dark" && <Check size={18} className="text-accent-cyan shrink-0 ml-2" />}
            </button>

            {/* Light Theme Option */}
            <button
              type="button"
              onClick={() => setTheme("hc-light")}
              className={`flex items-center justify-between p-4 rounded-xl border transition-all duration-200 text-left ${
                theme === "hc-light"
                  ? "border-accent-cyan bg-accent-cyan/10 shadow-[0_0_12px_rgba(0,229,255,0.12)]"
                  : "border-border-color bg-bg-sidebar hover:border-text-muted/40 hover:bg-sidebar-item-hover"
              }`}
            >
              <div className="flex items-center gap-3">
                <div className={`p-2.5 rounded-lg ${theme === "hc-light" ? "bg-amber-500/20 text-amber-500" : "bg-bg-card text-text-muted"}`}>
                  <Sun size={20} />
                </div>
                <div>
                  <div className="text-xs font-bold text-text-primary flex items-center gap-2">
                    High Contrast Light
                    {theme === "hc-light" && <span className="text-[10px] bg-accent-cyan/20 text-accent-cyan px-2 py-0.5 rounded-full font-semibold">Active</span>}
                  </div>
                  <div className="text-[11px] text-text-muted mt-0.5">Clean light background for bright environments</div>
                </div>
              </div>
              {theme === "hc-light" && <Check size={18} className="text-accent-cyan shrink-0 ml-2" />}
            </button>
          </div>
        </div>
      </div>

      <div className="mb-6">
        <h2 className="text-xl font-extrabold text-text-primary m-0 tracking-tight">Compliance Settings</h2>
        <p className="text-xs text-text-muted mt-1 leading-relaxed">Tune tolerances, geometrical checks, and AI reasoner boundaries.</p>
      </div>
      <div className="bg-bg-card border-2 border-dashed border-border-color rounded-xl p-6 backdrop-blur-md shadow-sm mt-6">
        <h3 className="text-sm font-bold border-l-[3px] border-accent-cyan pl-2.5 text-text-primary m-0">Geometrical Tolerances</h3>
        <div className="flex flex-col gap-4 mt-5">
          <div className="flex flex-col gap-2">
            <label className="text-[10px] font-semibold uppercase tracking-wider text-text-muted">Coincidence Tolerance (mm)</label>
            <input type="number" className="w-full bg-bg-sidebar border border-border-color rounded-lg py-2.5 px-3.5 text-xs text-text-primary font-mono focus:outline-none focus:border-accent-cyan focus:shadow-[0_0_10px_rgba(0,229,255,0.15)] transition-all cursor-pointer" defaultValue="0.05" />
          </div>
          <div className="flex flex-col gap-2">
            <label className="text-[10px] font-semibold uppercase tracking-wider text-text-muted">Coplanar Angle Tolerance (degrees)</label>
            <input type="number" className="w-full bg-bg-sidebar border border-border-color rounded-lg py-2.5 px-3.5 text-xs text-text-primary font-mono focus:outline-none focus:border-accent-cyan focus:shadow-[0_0_10px_rgba(0,229,255,0.15)] transition-all cursor-pointer" defaultValue="0.1" />
          </div>
        </div>
      </div>

      <div className="mt-8">
        <h2 className="text-xl font-extrabold text-text-primary m-0 tracking-tight mb-4">Active Learning</h2>
        <LearningPanel />
      </div>

      <div className="mt-8">
        <h2 className="text-xl font-extrabold text-text-primary m-0 tracking-tight mb-4">System Connection</h2>
        <SystemDiagnostics />
      </div>
    </main>
  );
};
