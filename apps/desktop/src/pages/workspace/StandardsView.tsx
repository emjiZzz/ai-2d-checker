import React from "react";
import { StandardsManager } from "../../components/StandardsManager";

/**
 * StandardsView — admin-only standards management panel.
 * Extracted from AuditWorkspace.tsx (Phase 1 refactor).
 * Previously lines 2163-2167 of AuditWorkspace.tsx.
 *
 * Note: isAdmin gate is enforced by the parent AuditWorkspace shell.
 */
export const StandardsView: React.FC = () => {
  return (
    <div className="viewport-standards-manager">
      <StandardsManager />
    </div>
  );
};
