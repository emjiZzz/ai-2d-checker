import React from "react";
import { StandardsManager } from "../../components/StandardsManager";

export const StandardsAdministration: React.FC = () => {
  return (
    <div className="admin-standards-wrapper">
      <div className="admin-subpage">
        <div className="subpage-header" style={{ marginBottom: "12px", padding: "0 32px" }}>
          <h2 className="section-title">Standards Manual Administration</h2>
          <p className="section-desc">Upload corporate CAD engineering drafting manuals, extract rule clauses, and embed vectors in LanceDB.</p>
        </div>
        <StandardsManager />
      </div>
    </div>
  );
};
