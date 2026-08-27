import { Check, FolderOpen, X } from "lucide-react";

import type { ExportStatus } from "../../hooks/useComplianceReportExport";

/**
 * What happened to the last PDF export, shown next to the button that started it.
 *
 * The export writes **two files, with names it chooses, into a folder the user picked** — so
 * neither the names nor the outcome are guessable from the button. Before this existed the only
 * signal was "Building…" ceasing to say "Building…", which is also exactly what cancelling the
 * folder picker looks like. A user reported that as a bug, correctly.
 *
 * Shared by `ManualMarkingList` (a sidebar with room for a line of text) and `TwoDWorkspace` (a
 * 24 px toolbar), rather than written twice at two sizes — the palette and the wording would
 * drift, which is the failure this codebase has already paid for in `ChecklistPanel`.
 */
export function ExportStatusNote({
  status,
  onReveal,
  compact = false,
}: {
  status: ExportStatus;
  onReveal: () => void;
  compact?: boolean;
}) {
  if (!status) return null;

  if (status.kind === "cancelled") {
    return (
      <div
        role="status"
        style={{
          display: "flex",
          alignItems: "center",
          gap: 5,
          fontSize: compact ? 10 : 11,
          color: "var(--text-muted)",
          padding: compact ? 0 : "2px 0",
        }}
      >
        <X size={compact ? 10 : 12} aria-hidden />
        Export cancelled
      </div>
    );
  }

  // The folder's own name, not the whole path: the full thing is 60+ characters of absolute path
  // in a sidebar 200 px wide, and it wraps to three lines to tell the user something they just
  // chose themselves. The full path stays on the title, and "Show" is the real answer to "where".
  const folderName = status.folder.split(/[\\/]/).filter(Boolean).pop() || status.folder;

  return (
    <div
      role="status"
      style={{
        display: "flex",
        alignItems: "center",
        gap: 6,
        fontSize: compact ? 10 : 11,
        color: "var(--accent-cyan)",
        padding: compact ? 0 : "2px 0",
        minWidth: 0,
      }}
      title={`Saved to ${status.folder}\n\n${status.names.join("\n")}`}
    >
      <Check size={compact ? 10 : 12} aria-hidden style={{ flexShrink: 0 }} />
      <span
        style={{
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
          minWidth: 0,
        }}
      >
        {compact
          ? `Saved ${status.names.length}`
          : `Saved ${status.names.length} ${status.names.length === 1 ? "file" : "files"} to ${folderName}`}
      </span>
      <button
        type="button"
        onClick={onReveal}
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 3,
          flexShrink: 0,
          background: "none",
          border: "none",
          padding: 0,
          cursor: "pointer",
          font: "inherit",
          color: "inherit",
          textDecoration: "underline",
        }}
        title="Open the folder with the exported files"
      >
        <FolderOpen size={compact ? 10 : 12} aria-hidden />
        Show
      </button>
    </div>
  );
}
