# _deprecated/

Files moved here during Phase 7 of the frontend remediation plan (see
`frontend-remediation-plan.md`).

## DiagnosticsDashboard.tsx
Previously at `apps/desktop/src/components/system/DiagnosticsDashboard.tsx`.

Orphaned prototype — no imports found anywhere in the codebase during the
audit (`App.tsx`, `AuditWorkspace.tsx`, `AppHeader.tsx`, `SettingsView.tsx`,
and all `pages/` views checked). Its state was entirely mocked (hardcoded
backup records, a static "Active: CPU (Quantized MiniLM)" hardware badge).

Its intended functionality is already live and properly wired elsewhere:
- Storage/DB/vector-index diagnostics → `apps/desktop/src/pages/admin/SystemDiagnostics.tsx`
  (wired to `useAdminStore`, real MongoDB/LanceDB/disk stats)
- Backup & restore → `apps/desktop/src/pages/admin/BackupRecovery.tsx`
  (wired to `useAdminStore`, real `triggerBackup`/`triggerRestore` calls)

Both are mounted in `AdminDashboard.tsx`. This file is superseded, not just
unused — safe to `git rm` once confirmed. Kept here for one review cycle
instead of hard-deleted, since this tool couldn't run `git rm` directly.
