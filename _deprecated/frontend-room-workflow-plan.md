# Implementation Plan — Room-Based Workflow for 2D/3D Workspace

**Target repo:** `D:\RAYSAN\ai-2d-checker`
**Snapshot verified:** 2026-07-10, via direct file read of current nav/store/component structure.
**Companion to:** `frontend-refactor-plan.md` (structural refactor, now complete) and `REFACTOR_PLAN_backend_god_files.md` (backend). This is a **new feature**, not a refactor — different rules apply where noted.
**Executor-agnostic:** written for Claude, Gemini, or a human picking this up cold.

## Decisions locked in (confirmed with the user, not assumed)

1. **Rooms are backend-persisted.** New MongoDB collection, real CRUD API. Not a frontend-only placeholder.
2. **One active Room at a time.** No tab/multi-room concurrency in this pass — opening a Room replaces whatever was active.
3. **This pass is a visual scaffold only.** Room list + Create Room UI, gated in front of the existing 2D/3D workspace. **The existing upload → comparison → Stage 2 audit workflow does not change at all.** Real per-Room data isolation (a Room actually remembering its own drawings/violations when you leave and come back) is explicitly **out of scope for this pass** — see "Deferred" section at the bottom. Don't build it now, even if it looks easy to add while you're in the file.

## One assumption I'm flagging, not deciding silently

When you **leave** a Room (to go create/open a different one), the existing `workspaceStore` still holds whatever old/new drawings and violations were loaded — it's a single global persisted store, it doesn't know about Rooms yet. If Room B opens and still shows Room A's uploaded drawings, that's not a scaffold, that's a confusing bug.

**Recommendation:** on `leaveRoom()`, clear the transient workspace data (`clearUpload("old")`, `clearUpload("new")`, reset violations/complianceScore) so each Room *looks* like a clean slate. This is **not** real isolation — reopening Room A won't restore what was in it, the data is just gone, same as today. It's the minimum needed so the scaffold doesn't lie to the user. If you want Room A's uploads to actually still be there when you reopen it, that's real state work, not a visual scaffold — say so and I'll fold it into Phase A/B instead of deferring it.

---

## 0. Ground Truth (verified against current files)

**Current nav flow:** `App.tsx` → `AuditWorkspace.tsx` (shell) → switches on `useNavStore().currentNav` (`'workspace' | '3d-workspace' | 'standards' | 'history' | 'settings'`) → renders `WorkspaceView` / `HistoryView` / `SettingsView` / `StandardsView`. `WorkspaceView.tsx` further delegates to `TwoDWorkspace.tsx` or `ThreeDWorkspace.tsx` depending on `currentNav`.

**Current 2D workflow (unchanged by this plan):** `TwoDWorkspace.tsx` renders "Stage 1: Drawing Pair Ingestion" — two `UploadZone` panels (old/new). Once both are uploaded and a physical comparison runs (`isPhysicalComparisonEnabled` flips true, set inside `usePhysicalComparison.ts`), `TwoDRightPanel.tsx` ("Stage 2 AI Compliance Auditor") becomes visible — client selection + "Execute Compliance Audit" → violations feed.

**Backend patterns confirmed from existing code (follow these, don't invent new ones):**

- Beanie `Document` models live in `domain/models/`, use `Field(..., description=...)`, a `Settings` class with `name` + `IndexModel` list. `AuditSession` uses a soft-delete convention (`is_deleted: bool`, `deleted_at`, `deleted_by`) rather than a status enum — **use this same pattern for Room**, not a new one.
- Routers live in `api/routers/`, use `router = APIRouter()`, `dependencies=[Depends(get_auth_token)]` on protected endpoints, responses wrapped in the `StandardResponse[T]` generic from `api/schemas.py`.
- Routers get registered in `api/v1.py` via `from .routers import X` + `router.include_router(X.router)`.

**Nav is currently a flat tab switch, not scoped to anything.** Rooms need to gate specifically the `workspace`/`3d-workspace` tabs — `history`/`settings`/`standards` stay exactly as they are, untouched by this plan.

---

## 1. Non-Negotiable Execution Rules (same discipline as the other two plans)

1. One phase at a time. Test/manual-QA gate before moving on.
2. This is new code, not a move — but still: don't let scope creep in. If you notice a chance to also wire up real data isolation while you're in `AuditWorkspace.tsx`, don't. That's explicitly deferred — note it as a `// TODO(room-isolation):` comment and keep going.
3. Commit after each phase: `feat(rooms): <what> [phase N/2]`.

---

## Phase A — Backend: Room model + CRUD API

### A.1 — `services/backend/domain/models/room.py` (new file)

```python
from datetime import datetime

from beanie import Document
from pydantic import Field
from pymongo import ASCENDING, DESCENDING, IndexModel


class Room(Document):
    name: str = Field(..., description="User-facing room label, e.g. 'Bracket Rev C vs Rev D'")
    description: str | None = Field(None, description="Optional free-text notes about this test session")
    client_name: str | None = Field(None, description="Optional associated client, for grounding/filtering later")
    created_by: str | None = Field(None, description="Username who created the room")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_opened_at: datetime | None = Field(None, description="Updated each time the room is opened")
    is_deleted: bool = Field(False, description="Soft deletion flag, matches AuditSession's convention")
    deleted_at: datetime | None = Field(None)
    deleted_by: str | None = Field(None)

    class Settings:
        name = "rooms"
        indexes = [
            IndexModel([("is_deleted", ASCENDING)]),
            IndexModel([("created_at", DESCENDING)]),
            IndexModel([("client_name", ASCENDING)]),
        ]
```

Deliberately **not** adding `active_old_drawing_id`/`active_new_drawing_id`/`audit_session_ids` fields yet — that's the deferred isolation work, and MongoDB is schemaless, so adding fields later costs nothing. Don't pre-build a data model for a feature you're not building this pass.

**Register the model** wherever `AuditSession`/`DrawingDocument` etc. get registered with Beanie's `init_beanie(document_models=[...])` call (find it in `main.py` or a db-init module — grep for where `AuditSession` appears in that list, add `Room` next to it).

### A.2 — `services/backend/api/schemas.py` — add request/response models

Follow the existing pattern in this file (check how `StandardDocumentResponse` etc. are shaped) and add:

```python
class RoomCreateRequest(BaseModel):
    name: str
    description: str | None = None
    client_name: str | None = None

class RoomResponse(BaseModel):
    id: str
    name: str
    description: str | None
    client_name: str | None
    created_at: datetime
    updated_at: datetime
    last_opened_at: datetime | None
```

### A.3 — `services/backend/api/routers/rooms.py` (new file)

```python
from fastapi import APIRouter, Depends, HTTPException, status
from ...domain.models.room import Room
from ...logger import logger
from ..dependencies import get_auth_token
from ..schemas import StandardResponse, RoomResponse, RoomCreateRequest

router = APIRouter()


@router.post("/rooms", response_model=StandardResponse[RoomResponse],
             summary="Create a new testing Room", dependencies=[Depends(get_auth_token)])
async def create_room(payload: RoomCreateRequest):
    room = Room(name=payload.name, description=payload.description, client_name=payload.client_name)
    await room.save()
    return StandardResponse(success=True, data=_to_response(room))


@router.get("/rooms", response_model=StandardResponse[list[RoomResponse]],
            summary="List all active (non-deleted) Rooms", dependencies=[Depends(get_auth_token)])
async def list_rooms():
    rooms = await Room.find(Room.is_deleted == False).sort(-Room.updated_at).to_list()
    return StandardResponse(success=True, data=[_to_response(r) for r in rooms])


@router.get("/rooms/{room_id}", response_model=StandardResponse[RoomResponse],
            summary="Get a Room and mark it opened", dependencies=[Depends(get_auth_token)])
async def get_room(room_id: str):
    room = await Room.get(room_id)
    if not room or room.is_deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found")
    from datetime import datetime
    room.last_opened_at = datetime.utcnow()
    await room.save()
    return StandardResponse(success=True, data=_to_response(room))


@router.delete("/rooms/{room_id}", response_model=StandardResponse[dict],
               summary="Soft-delete a Room", dependencies=[Depends(get_auth_token)])
async def delete_room(room_id: str):
    room = await Room.get(room_id)
    if not room or room.is_deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found")
    from datetime import datetime
    room.is_deleted = True
    room.deleted_at = datetime.utcnow()
    await room.save()
    logger.info(f"Room soft-deleted: {room_id}")
    return StandardResponse(success=True, data={"deleted": True})


def _to_response(room: Room) -> RoomResponse:
    return RoomResponse(
        id=str(room.id), name=room.name, description=room.description,
        client_name=room.client_name, created_at=room.created_at,
        updated_at=room.updated_at, last_opened_at=room.last_opened_at
    )
```

### A.4 — Register in `api/v1.py`

Add `from .routers import rooms` alongside the existing router imports, and `router.include_router(rooms.router)` alongside the others.

### Test gate for Phase A

No existing test file covers a pattern this simple to copy from directly — write `tests/test_rooms.py` following the `mock_beanie_docs` fixture pattern from `test_phase4_audit_pipeline.py` (mock `Room.save`/`get`/`find`). Cover: create → appears in list → get updates `last_opened_at` → delete → no longer appears in list (soft-deleted, not gone from DB).
Manual gate: hit the four endpoints via the FastAPI `/docs` Swagger UI once, confirm request/response shapes match what the frontend will expect below.

---

## Phase B — Frontend: Room store + Room list/create UI + workspace gate

### B.1 — `apps/desktop/src/stores/roomStore.ts` (new file)

```ts
import { create } from "zustand";
import { apiClient } from "../services/apiClient";
import { useWorkspaceStore } from "./workspaceStore";

export interface Room {
  id: string;
  name: string;
  description: string | null;
  client_name: string | null;
  created_at: string;
  updated_at: string;
  last_opened_at: string | null;
}

interface RoomState {
  rooms: Room[];
  activeRoom: Room | null;
  isLoading: boolean;
  error: string | null;

  fetchRooms: () => Promise<void>;
  createRoom: (name: string, description?: string, clientName?: string) => Promise<Room | null>;
  openRoom: (roomId: string) => Promise<void>;
  leaveRoom: () => void;
  deleteRoom: (roomId: string) => Promise<boolean>;
}

export const useRoomStore = create<RoomState>((set, get) => ({
  rooms: [],
  activeRoom: null,
  isLoading: false,
  error: null,

  fetchRooms: async () => {
    set({ isLoading: true, error: null });
    const res = await apiClient.get<Room[]>("/api/v1/rooms");
    if (res.ok) {
      set({ rooms: res.data, isLoading: false });
    } else {
      set({ error: res.message, isLoading: false });
    }
  },

  createRoom: async (name, description, clientName) => {
    const res = await apiClient.post<Room>("/api/v1/rooms", {
      name, description: description || null, client_name: clientName || null,
    });
    if (res.ok) {
      set((s) => ({ rooms: [res.data, ...s.rooms] }));
      return res.data;
    }
    set({ error: res.message });
    return null;
  },

  openRoom: async (roomId) => {
    const res = await apiClient.get<Room>(`/api/v1/rooms/${roomId}`);
    if (res.ok) {
      set({ activeRoom: res.data });
    }
  },

  // Scaffold-phase behavior: clears the shared workspace so the next room
  // starts visually clean. This does NOT persist Room A's data for later —
  // that's deferred, see frontend-room-workflow-plan.md "Deferred" section.
  // TODO(room-isolation): replace this with real per-room state once built.
  leaveRoom: () => {
    const ws = useWorkspaceStore.getState();
    ws.clearUpload("old");
    ws.clearUpload("new");
    set({ activeRoom: null });
  },

  deleteRoom: async (roomId) => {
    const res = await apiClient.del<{ deleted: boolean }>(`/api/v1/rooms/${roomId}`);
    if (res.ok) {
      set((s) => ({ rooms: s.rooms.filter((r) => r.id !== roomId) }));
      return true;
    }
    return false;
  },
}));
```

Check `apiClient.ts`'s actual exported method names before wiring this in (`.get`/`.post`/`.del` — confirm the delete method's real name, don't assume `.del`) — verified pattern exists there for the other stores already, just match it exactly.

### B.2 — `apps/desktop/src/pages/workspace/RoomsView.tsx` (new file)

Room grid (cards showing name, client, last opened, a delete icon) + a "Create Room" button opening a small inline modal (name + optional description/client fields). On successful create, call `openRoom(newRoom.id)` immediately — don't make the user create then separately click open.

Reuse the existing `Button` component (`components/ui/Button.tsx`) and match the card/dashed-border visual language already used in `TwoDRightPanel.tsx` (`bg-bg-card border-2 border-dashed border-border-color rounded-xl`) so this doesn't look like a bolted-on page.

Empty state (zero rooms): a centered prompt with the Create Room button — don't just show a blank grid.

### B.3 — Gate `AuditWorkspace.tsx`

This is the **only** change to existing files in this plan. Current block:

```tsx
{(currentNav === "workspace" || currentNav === "3d-workspace") && (
  <WorkspaceView currentNav={currentNav} />
)}
```

Becomes:

```tsx
{(currentNav === "workspace" || currentNav === "3d-workspace") && (
  activeRoom ? (
    <div className="flex flex-col w-full h-full">
      <div className="flex items-center justify-between px-4 py-2 bg-bg-dark border-b border-border-color shrink-0">
        <span className="text-sm font-semibold text-text-primary">
          Room: <span className="text-accent-cyan">{activeRoom.name}</span>
        </span>
        <Button variant="ghost" size="sm" onClick={leaveRoom}>← Back to Rooms</Button>
      </div>
      <WorkspaceView currentNav={currentNav} />
    </div>
  ) : (
    <RoomsView />
  )
)}
```

Pull `activeRoom`/`leaveRoom` from `useRoomStore()` at the top of `AuditWorkspace.tsx` alongside the existing store hooks. **Do not touch `WorkspaceView.tsx`, `TwoDWorkspace.tsx`, `TwoDLeftPanel.tsx`, or `TwoDRightPanel.tsx` at all** — this is the entire point of gating at the shell level instead of threading Room state down through the existing components.

### Test gate for Phase B

No test runner precedent for full-page flows in this codebase yet (component tests generally aren't present — see the frontend audit). Manual QA:

1. Fresh app launch, navigate to Workspace tab → see empty Room list (or existing rooms if backend has data), not the upload panels.
2. Create a Room → immediately lands in the existing Stage 1 upload UI, unchanged.
3. Upload both drawings, run comparison, confirm Stage 2 still triggers exactly as before (this validates Phase B.3 didn't disturb `WorkspaceView`'s render tree).
4. Click "Back to Rooms" → returns to Room list, upload panels are empty again (confirms `leaveRoom()`'s clear-on-leave behavior).
5. Create a second Room, confirm both Rooms appear in the list, `last_opened_at` differs appropriately.
6. Restart the app entirely → Rooms still appear in the list (confirms backend persistence actually works, not just in-memory).

---

## Deferred — NOT part of this plan, don't build now

Listed so the next phase has a target, and so nobody "helpfully" builds this early and breaks the "visual scaffold only" agreement:

- **Real per-Room data isolation.** A Room remembering its own old/new drawings, layers, violations, and compliance score when you leave and reopen it. Requires either keying `workspaceStore`'s state by `roomId` or giving each Room its own persisted sub-document server-side (`active_old_drawing_id`/`active_new_drawing_id`/linked `AuditSession` IDs on the `Room` model — the fields deliberately left off in Phase A.1).
- **Room rename/edit.** Only create + list + open + delete exist in this plan.
- **Associating Audit History with a Room.** `HistoryView.tsx`/`AuditHistory.tsx` stay completely room-agnostic in this plan — they show all sessions globally, same as today.
- **Multi-room concurrency (tabs).** Explicitly ruled out by the user's answer — one active Room at a time.

## Definition of Done

- [ ] Phase A — `Room` model + 4 endpoints + registered in `v1.py` + `init_beanie` model list + `test_rooms.py` passing
- [ ] Phase B — `roomStore.ts`, `RoomsView.tsx`, `AuditWorkspace.tsx` gate wired in
- [ ] Manual QA checklist (Phase B, 6 steps above) completed and passed
- [ ] Zero changes to `WorkspaceView.tsx`, `TwoDWorkspace.tsx`, `ThreeDWorkspace.tsx`, `TwoDLeftPanel.tsx`, `TwoDRightPanel.tsx`, `usePhysicalComparison.ts` — confirm via `git diff` before committing Phase B
- [ ] One commit per phase

## Phase Completion Log

```
Phase A: [x] code complete, [ ] test gate NOT yet run — Claude has no execution access to this
         machine, only file read/write via the Filesystem connector. Code written:
           - domain/models/room.py (new)
           - domain/models/__init__.py (Room added to imports + __all_models__)
           - api/schemas.py (RoomCreateRequest, RoomResponse added)
           - api/routers/rooms.py (new — 4 endpoints: POST/GET/GET-by-id/DELETE)
           - api/v1.py (rooms router registered)
           - tests/test_rooms.py (new — 4 tests, offline-mocked, same pattern as
             test_phase4_audit_pipeline.py)
         YOU need to run: `pytest tests/test_rooms.py -v` and confirm all 4 pass.
         Also start the backend once (`start-mongo.ps1` + backend start) and hit
         POST/GET /api/v1/rooms via the FastAPI /docs Swagger UI to confirm the
         real (non-mocked) MongoDB path works too — the test suite only proves the
         logic is correct against mocks, not that init_beanie picked up the new
         Room model correctly at runtime.
Phase B: [ ] not started   [ ] in progress   [ ] complete — manual QA notes: ___
```
