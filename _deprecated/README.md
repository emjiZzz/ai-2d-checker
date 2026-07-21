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

## implementation_plan(AI-2D-Checker).md
Previously at repo root. 10-phase backend roadmap (Gemini Vision grounding,
rule engine expansion, RAG/vector indexing, BOM/balloon reconciliation,
revision chains, engineer feedback loop, reporting, enterprise hardening).

Verified executed against current source, not just assumed complete — found
explicit `# --- PHASE 1.2 ---` / `# Phase 7.1` / `# Phase 7.3` / `# Phase 8.1`
/ `# Phase 8.2` markers left in the code matching the plan's own phase
numbering, in:
- `services/backend/infrastructure/audit/ai_engine.py` (Phase 1.1 PNG→Gemini
  Vision wiring, Phase 3.1 structured context, Phase 3.2 dual-pass audit,
  Phase 3.3 confidence calibration)
- `services/backend/infrastructure/audit/standards_loader.py` (Phase 1.2
  vector index writes on ingest)
- `services/backend/domain/models/drawing_document.py` (Phase 7.1 revision
  chain fields)
- `services/backend/api/routers/audits.py` (Phase 7.3 auto-revision linking,
  Phase 8.1 violation review endpoint, Phase 8.2 lessons-learned indexing)
- Supporting modules confirmed present: `bom_analyzer.py` (Phase 5),
  `copilot.py` router (Phase 1.3), `analytics.py` router (Phase 9.2)

The physical-comparison endpoint has grown past the plan's own Phase 1.4
spec — it now dispatches to `deterministic` / `full_ai` / `full_ai_vision`
methods via a dedicated comparison orchestrator, not the simpler version
described in the doc. Not independently re-verified: whether every one of
the 25+ individual rule-engine checks in Phase 2 and every Phase 10
enterprise-hardening item landed — the phase-marker sampling above covers
Phases 1, 3, 5, 7, 8, 9 directly; Phases 2, 4, 6, 10 were inferred from
file presence, not read line-by-line.

## frontend-refactor-plan.md
Previously at repo root. God-component decomposition plan for
`AuditWorkspace.tsx` (was 4,738 lines) and `DrawingCanvas.tsx` (was 1,956
lines). The plan's own Phase Completion Log was never filled in (all boxes
left unchecked), which is stale bookkeeping, not evidence of non-completion.

Verified directly: `AuditWorkspace.tsx` is now a 6.9 KB thin shell (not the
god component described), and `DrawingCanvas.tsx`'s decomposition exists —
`canvasInteraction.ts`, `renderEntities.ts`, `DrawingCanvas.test.tsx` are all
present in `apps/desktop/src/components/review/`. One structural deviation
from the plan: files landed flat in `components/review/` rather than in a
`components/review/canvas/` subfolder as specified — functionally
equivalent, just a different folder shape.

## frontend-room-workflow-plan.md
Previously at repo root. Room-based workflow feature plan (Phase A backend
`Room` model + CRUD, Phase B frontend Room list/create UI gating the
workspace). The plan's own Phase Completion Log claimed Phase A "code
complete, test gate NOT yet run" and Phase B "not started" — both stale.

Verified directly: `roomStore.ts` and `RoomsView.tsx` exist and are wired
into `AuditWorkspace.tsx`'s nav gate exactly as specced. The implementation
has gone further than the plan's explicit scope: the plan's Phase A.1
deliberately omitted `active_old_drawing_id` / `active_new_drawing_id` /
`active_audit_session_id` / `physical_comparison_results` fields ("don't
pre-build a data model for a feature you're not building this pass"), and
explicitly deferred real per-Room data isolation to a future pass — but the
`Room` model on disk now has all four fields, plus a `comparison_method`
field, and `AuditWorkspace.tsx` has a `useEffect` that actively syncs
workspace state into the Room on every change. The isolation feature this
plan deferred has since been built; the model's own docstring still says
isolation is "deliberately NOT modeled yet" directly above the fields that
model exactly that — worth a docstring fix independent of this archival.

One unresolved asymmetry from this plan, not something this archival
changes: the Room gate in `AuditWorkspace.tsx` only guards
`currentNav === "workspace"` (2D). The `3d-workspace` tab renders
`WorkspaceView` directly with no `activeRoom` check, so 3D workspace is
reachable with no active Room while 2D isn't. Unclear if intentional.
