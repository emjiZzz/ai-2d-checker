import React from "react";
import { SystemDiagnostics } from "../../components/SystemDiagnostics";
import { LearningPanel } from "../../components/settings/LearningPanel";

/**
 * SettingsView — Compliance Settings form + live System Connection panel.
 * Extracted from AuditWorkspace.tsx (Phase 1 refactor).
 *
 * The Compliance Settings section (Geometrical Tolerances) remains a static
 * mockup with no state wiring — those inputs are not yet persisted or read
 * anywhere. Do not assume they affect audit behavior.
 *
 * The System Connection section below IS live: <SystemDiagnostics /> is wired
 * to useConnectionStore and performs real health checks and backend URL writes.
 * This was intentionally connected here in Phase 7 of the frontend remediation
 * plan. If you're adding new state-wired UI to this file, that's now consistent
 * with the file's purpose — just don't conflate it with the still-static
 * tolerance form above.
 */
export const SettingsView: React.FC = () => {
  return (
    <main className="flex-grow h-full min-h-0 overflow-y-auto bg-bg-dark py-8 px-8 box-border">
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
