# Zone Review Gate — Implementation Plan

**Project:** ai-2d-checker
**Source:** Third in the zone series, after `docs/zone-bbox-overlay-implementation-plan.md`
(made zones visible) and `docs/zone-template-alignment-implementation-plan.md` (made them
correctable and persistable). This one makes reviewing them **mandatory** before a comparison
can be run.
**Status:** Implemented. See completion log.

## Context

The workspace previously showed everything at once: as soon as both drawings were ingested,
the Comparison Results panel appeared with "Ready for Comparison", while zone editing was an
opt-in item in the ⋮ View menu. Nothing required a user to look at the zone boxes, and
nothing stopped them running a comparison against boxes that are known to be wrong — `iso`
has never been detected on any drawing in the corpus, and `notes`/`views`/`tolerance` drift
33–64pp between sheets.

Since the template resolver landed, those boxes genuinely drive the audit: BOM row
extraction, category assignment in `result_parser`, safe-zone exclusion, and crop-verifier
tiles. Running a comparison before the boxes are reviewed produces confidently wrong output.

The workflow is now sequenced:

**ingest both drawings → zone editor opens automatically → user clicks Done → Comparison
Results panel appears → run comparison.**

## Architecture decisions

1. **The flag stores the drawing *pair*, not a boolean.** `Room.zones_confirmed_for` holds
   `"{old_id}:{new_id}"`. The gate is a comparison against live state, so swapping either
   drawing invalidates the confirmation on its own. A boolean would need explicit clearing in
   every upload/clear path (`clearUpload`, `setOldDrawing`, `setNewDrawing`, and the
   `handleAction` DELETE_TAB veto that calls `clearUpload` directly) — four places to keep in
   step, and a stale `true` silently lets a comparison run against unreviewed zones.

2. **The rule lives in one pure module**, `apps/desktop/src/utils/zoneGate.ts`, so it is
   testable without mounting flexlayout, canvas refs and `ResizeObserver`. Same convention as
   `utils/zoneFractions.ts`.

3. **Grandfathering is snapshotted per room open, never derived live.** `AuditWorkspace`'s
   reverse-sync nulls `physical_comparison_results` server-side whenever the scan returns to
   idle — which is exactly what **Re-test** does. A live reading would delete the Comparison
   Results panel out from under a user mid-retest. Consequence accepted deliberately: a
   grandfathered room stays grandfathered for the session even if a drawing is swapped.

4. **Grandfathering checks two fields, not one.** `physical_comparison_results` is the
   physical-checklist path; `active_audit_session_id` covers rooms restored through the audit
   session branch, which populates violations and a compliance score without necessarily
   writing the former. Checking only the first would push a room that plainly has results
   back through the gate.

5. **The runtime effect is the sole owner of `leftPanelTab`.** The layout seed no longer
   creates it. Seeding the tab and deleting it one frame later flashed the gated panel at
   every fresh user, and two sources of truth for one tab is what made the previous show/hide
   behaviour hard to reason about.

6. **`LAYOUT_STORAGE_PREFIX` was deliberately NOT bumped.** Bumping it would discard every
   user's rearranged layout to cover a case already handled twice over: the gate effect's
   delete branch runs unguarded on first mount (which is what removes a `leftPanelTab`
   persisted by an earlier session), and `TwoDLeftPanel` has its own early return so a leaked
   tab renders an empty body rather than a usable START COMPARISON button.

## Traps

**The Zod schema strips unknown keys.** `RoomSchema` in `schemas/apiSchemas.ts` is a
`z.object`, and `parseAndValidate` calls `schema.parse`. A field missing from that schema is
silently dropped from every `openRoom` and `updateRoom` result. The gate would appear to work
on click (optimistic local state) and then re-close on the next sync — presenting as a React
bug, not a schema one. **Any new Room field must be added there as well as to the TS
interface.**

**`openRoom` has an ordering race.** It pushes drawings into `workspaceStore` well before it
sets `activeRoom` (deliberately last, to avoid a different race). In that window both
drawings are present while `activeRoom` is still the *previous* room. Any rule combining the
two must gate on `isRoomSyncedWithDrawings` first, or it evaluates a room against someone
else's drawings — here, flashing the editor open over a room that is already confirmed.

**`isRoiEditModeEnabled` is global and ephemeral.** It lives in `reviewStore`, is not
room-scoped, and does not persist. The room-change cleanup effect in `TwoDWorkspace` is
load-bearing, not tidiness: without it, edit mode bleeds from an unconfirmed room into a
confirmed one and the amber toolbar renders over a room already past the gate.

**Do not copy the AI Auditor effect's `isInitialModelLoadRef` guard onto the gate effect.**
That guard exists so a newly arrived score doesn't fight the seeded layout. On the gate
effect it would defeat the mechanism that removes a stale `leftPanelTab` from a persisted
layout on first mount.

## Changes

**Backend**
- `domain/models/room.py` — `zones_confirmed_for: str | None`. Nullable default, so existing
  documents load unchanged; no migration.
- `api/schemas.py` — added to `RoomResponse` and `UpdateRoomRequest`.
- `api/routers/rooms.py` — mapped in `_to_response`. The PATCH handler needed no change: it
  already applies fields via `setattr` over `model_dump(exclude_unset=True)`, which gives
  both required semantics for free — an absent key preserves, an explicit `null` clears.

**Frontend**
- `utils/zoneGate.ts` *(new)* — `zonePairKey`, `isRoomSyncedWithDrawings`,
  `isZoneReviewConfirmed`, `isZoneReviewGrandfathered`, `isZoneGateOpen`.
- `schemas/apiSchemas.ts`, `stores/roomStore.ts` — field added to the Zod schema and the
  `Room` interface.
- `stores/reviewStore.ts` — `setRoiEditMode`, because the auto-open flow needs idempotence
  that a toggle cannot provide.
- `components/review/TwoDWorkspace.tsx` — `toggleZoneEditing` split into an idempotent
  `openZoneEditing` plus the menu toggle; the gate on the `leftPanelTab` effect; the
  auto-open effect; the room-change cleanup; the **Done** button in the amber toolbar; the
  tabset weight re-applied on the runtime add path.
- `components/review/TwoDLeftPanel.tsx` — second, independent gate on the panel body.

## Verification

Automated: `tests/test_rooms.py` (+6, including the partial-PATCH preservation regression),
`apps/desktop/src/utils/zoneGate.test.ts` (20). Backend 340 passed, frontend 121 passed,
`tsc --noEmit` clean — the three known pre-existing failures unchanged.

Live, against the running backend on a throwaway room that was deleted afterwards:
`zones_confirmed_for` set via PATCH → **preserved** through the exact partial payload
`AuditWorkspace` sends → cleared by explicit `null`. The field is present on every room in
the list response.

Manual, still to be run in the Tauri app:
1. New room, ingest both drawings → editor opens by itself, no Comparison Results panel.
2. Align, click Done → editor closes, panel appears, START COMPARISON works.
3. Reload and reopen → straight to the panel, no re-confirmation.
4. Swap the revision drawing → gate re-closes, editor reopens.
5. Room with existing results → panel shows immediately, gate never appears.
6. Reopen the editor from ⋮ after Done → confirmation is not lost.

## Out of scope

- Requiring an actual edit before Done — clicking Done immediately is allowed.
- Any change to zone detection, the template resolver, or comparison logic.
- The three uncollected test files in `services/backend/tests/`, outside `pyproject.toml`'s
  `testpaths` and all failing collection on bare imports.

## Completion log

### Implementation — **done (automated + live API verified; UI unverified)**

All changes above landed. Two design errors were caught in review before implementation and
are worth recording because both were silent failures:

- The original plan omitted `schemas/apiSchemas.ts` entirely. Zod would have stripped the
  field from every room fetch.
- The original plan derived grandfathering live, which would have deleted the Comparison
  Results panel mid-Re-test.

The layout seed's copy of `leftPanelTab` was also removed during implementation (decision 5)
after noticing it would flash the gated panel for one frame on a fresh layout.
