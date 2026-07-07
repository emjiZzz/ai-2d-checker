import React from "react";

/**
 * SettingsView — static Compliance Settings form (no state wiring).
 * Extracted from AuditWorkspace.tsx (Phase 1 refactor).
 * Previously lines 2602-2620 of AuditWorkspace.tsx.
 *
 * IMPORTANT: Per the refactor plan, this view must remain unwired during Phase 1.
 * It is a static mockup. Do not add feature/state logic here until a dedicated
 * settings feature pass — adding it here turns a structural refactor into a feature change.
 */
export const SettingsView: React.FC = () => {
  return (
    <main className="workspace-main-viewport padded">
      <div className="subpage-header">
        <h2 className="section-title">Compliance Settings</h2>
        <p className="section-desc">Tune tolerances, geometrical checks, and AI reasoner boundaries.</p>
      </div>
      <div className="card settings-card" style={{ marginTop: "24px" }}>
        <h3 className="card-title">Geometrical Tolerances</h3>
        <div style={{ display: "flex", flexDirection: "column", gap: "16px", marginTop: "20px" }}>
          <div className="form-group">
            <label className="form-label">Coincidence Tolerance (mm)</label>
            <input type="number" className="form-input" defaultValue="0.05" />
          </div>
          <div className="form-group">
            <label className="form-label">Coplanar Angle Tolerance (degrees)</label>
            <input type="number" className="form-input" defaultValue="0.1" />
          </div>
        </div>
      </div>
    </main>
  );
};
