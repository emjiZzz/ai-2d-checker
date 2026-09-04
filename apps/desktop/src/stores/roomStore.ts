/**
 * Room store — Phase B of the room-based workflow (see frontend-room-workflow-plan.md).
 *
 * Scaffold phase only: Rooms are backend-persisted containers, but they do NOT
 * yet remember their own drawings/violations. leaveRoom() clears the shared
 * workspaceStore so the next room starts visually clean, but this is not real
 * per-room data isolation — see the plan's "Deferred" section.
 * TODO(room-isolation): replace clear-on-leave with real per-room persisted state.
 */
import { create } from "zustand";
import { parseOrThrow, parseAndValidate, buildHeaders, baseUrl } from "../services/fetchUtils";
import { RoomSchema, RoomListSchema } from "../schemas/apiSchemas";
import { useWorkspaceStore, DrawingItem, saveWorkspaceState, loadWorkspaceState } from "./workspaceStore";
import { reconcilePersistedIds } from "../utils/persistedViolations";
import { fetchPersistedViolations } from "../utils/persistedViolationsApi";
import { mapCanvasMarkingsToMarkers } from "../utils/restoreCanvasMarkings";

/**
 * The only comparison method. Renamed from `"rag"`, which named a technique it does not
 * contain — no retrieval, no LLM (see docs/vault/00 - AI Maturity Status.md).
 *
 * The backend accepts `"rag"` on input permanently and normalises it, so rooms written
 * before the rename still load. That means this type describes what the API *returns*, and
 * nothing here needs to handle the legacy spelling.
 */
export type ComparisonMethod = "deterministic";

/**
 * What a room is FOR — orthogonal to which engine compares.
 *
 * `manual_check` rooms never invoke the comparison engine: an engineer stamps entities by hand
 * and the result is ground truth. Kept off `ComparisonMethod` on purpose — that names an
 * engine, and a manual check does not run one. See `domain/models/room_mode.py`.
 *
 * Optional on `Room` because rooms created before the field existed carry none, and they were
 * all AI comparison rooms. Absent and `"ai_comparison"` mean the same thing.
 */
export type RoomMode = "ai_comparison" | "manual_check";

export interface Room {
  id: string;
  name: string;
  description: string | null;
  client_name: string | null;
  created_at: string;
  updated_at: string;
  last_opened_at: string | null;
  active_old_drawing_id?: string | null;
  active_new_drawing_id?: string | null;
  active_old_drawing_name?: string | null;
  active_new_drawing_name?: string | null;
  active_audit_session_id?: string | null;
  physical_comparison_results?: any | null;
  /** "{old_drawing_id}:{new_drawing_id}" whose zone boxes the user confirmed. */
  zones_confirmed_for?: string | null;
  /** Only the deterministic method exists (ADR-006). Optional: a room predating the field. */
  comparison_method?: ComparisonMethod;
  /** Chosen at room creation. Absent on rooms predating it, which were all AI comparisons. */
  room_mode?: RoomMode;
}

interface RoomState {
  rooms: Room[];
  activeRoom: Room | null;
  isLoading: boolean;
  error: string | null;

  fetchRooms: () => Promise<void>;
  createRoom: (name: string, description?: string, clientName?: string, comparisonMethod?: ComparisonMethod, roomMode?: RoomMode) => Promise<Room | null>;
  openRoom: (roomId: string) => Promise<void>;
  leaveRoom: () => Promise<void>;
  deleteRoom: (roomId: string) => Promise<boolean>;
  updateRoom: (roomId: string, payload: Partial<Room>) => Promise<void>;
  clearError: () => void;
}

/** One drawing by id. Module scope so `openRoom` can start it before it has the room. */
const fetchDrawingById = async (id: string): Promise<DrawingItem | null> => {
  try {
    return await parseOrThrow<DrawingItem>(
      await fetch(`${baseUrl()}/api/v1/drawings/${id}`, { headers: buildHeaders() }),
    );
  } catch {
    return null;
  }
};

export const useRoomStore = create<RoomState>((set, get) => ({
  rooms: [],
  activeRoom: null,
  isLoading: false,
  error: null,

  clearError: () => set({ error: null }),

  fetchRooms: async () => {
    set({ isLoading: true, error: null });
    try {
      const res = await fetch(`${baseUrl()}/api/v1/rooms`, { headers: buildHeaders() });
      const data = await parseAndValidate<Room[]>(res, RoomListSchema);
      set({ rooms: data, isLoading: false });
    } catch (err: any) {
      set({ error: err.message || "Failed to fetch rooms", isLoading: false });
    }
  },

  createRoom: async (name, description, clientName, comparisonMethod = "deterministic", roomMode = "ai_comparison") => {
    set({ error: null });
    try {
      const res = await fetch(`${baseUrl()}/api/v1/rooms`, {
        method: "POST",
        headers: buildHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          name,
          description: description || null,
          client_name: clientName || null,
          comparison_method: comparisonMethod,
          room_mode: roomMode,
        })
      });
      const data = await parseAndValidate<Room>(res, RoomSchema);
      set((s) => ({ rooms: [data, ...s.rooms] }));
      return data;
    } catch (err: any) {
      set({ error: err.message || "Failed to create room" });
      return null;
    }
  },

  openRoom: async (roomId) => {
    // Saving the room being LEFT is not on the critical path of opening the next one.
    //
    // Safe to leave unawaited because `saveWorkspaceState` snapshots `getState()` synchronously
    // before its first await — the bytes are already captured, so a later `loadWorkspaceState`
    // cannot race it into writing the wrong room's state. The two also address different
    // IndexedDB keys (`workspace-<roomId>`), so they cannot collide.
    const currentRoom = get().activeRoom;
    if (currentRoom) {
      void saveWorkspaceState(currentRoom.id).catch((err) =>
        console.warn("[roomStore] could not save the outgoing room's workspace:", err),
      );
    }

    set({ isLoading: true, error: null });
    try {
      // Start the drawings BEFORE the room detail comes back.
      //
      // The chain was strictly serial — `/rooms/{id}` (833 ms; it carries the whole comparison
      // checklist) then `/drawings/{id}` then `/layers` — so the canvas could not begin
      // rendering until all three had landed. The room LIST already carries both drawing ids,
      // so when the room was opened from it there is nothing to wait for.
      //
      // This is a prefetch, never a source of truth. `/rooms/{id}` stays authoritative for
      // WHICH drawings the room points at: the list can be stale, and a room re-pointed at a
      // different drawing elsewhere would otherwise load the old one and look perfectly normal.
      // Results are keyed by drawing id and consumed below only when the authoritative id
      // matches — a miss simply refetches, costing what it costs today.
      const prefetch = new Map<string, Promise<DrawingItem | null>>();
      const listed = get().rooms.find((r) => r.id === roomId);
      for (const id of [listed?.active_old_drawing_id, listed?.active_new_drawing_id]) {
        if (id) prefetch.set(id, fetchDrawingById(id));
      }

      // The IndexedDB restore and the room fetch are independent — one reads local storage, the
      // other the network — and they were awaited one after the other. Run together they cost
      // the slower of the two rather than their sum.
      //
      // `loadWorkspaceState` must still finish BEFORE the drawings below are applied: it can
      // call `resetWorkspace()`, and a reset landing after them would blank the room that was
      // just opened. Awaiting both here keeps that ordering while removing the serial wait.
      const [, roomRes] = await Promise.all([
        loadWorkspaceState(roomId),
        fetch(`${baseUrl()}/api/v1/rooms/${roomId}`, { headers: buildHeaders() }),
      ]);
      const roomData = await parseAndValidate<Room>(roomRes, RoomSchema);

      // Fetch drawings FIRST before updating activeRoom to prevent sync race condition
      const ws = useWorkspaceStore.getState();
      
      // ── fetched CONCURRENTLY, not one after another ──────────────────────────────
      // These three are independent: two drawings and an audit session, all keyed off ids the
      // room document already gave us. They used to await in sequence, so opening a room cost
      // four serial round trips (room -> old -> new -> session -> violations) before anything
      // appeared. Nothing downstream needed that ordering; it was just written top to bottom.
      //
      // `Promise.all` is safe here only because each branch keeps its own try/catch: a rejected
      // promise would otherwise abandon the other two, and a missing drawing is a normal state
      // for a half-configured room, not a reason to fail the open.
      // Takes the prefetched promise when the authoritative id matches one, otherwise fetches.
      // `prefetch` holds promises rather than results, so a hit awaits a request already in
      // flight instead of issuing a second one.
      const fetchDrawing = (id?: string | null): Promise<DrawingItem | null> => {
        if (!id) return Promise.resolve(null);
        return prefetch.get(id) ?? fetchDrawingById(id);
      };

      // The session's two calls stay sequential with respect to each OTHER — violations are
      // addressed by the session id — but the pair runs alongside the drawings.
      const fetchSession = async () => {
        const sessionId = roomData.active_audit_session_id;
        if (!sessionId) return null;
        try {
          const sessionData = await parseOrThrow<any>(
            await fetch(`${baseUrl()}/api/v1/audits/sessions/${sessionId}`, { headers: buildHeaders() }),
          );
          let violationsData: any = [];
          try {
            violationsData = await parseOrThrow<any>(
              await fetch(`${baseUrl()}/api/v1/audits/sessions/${sessionId}/violations`, { headers: buildHeaders() }),
            );
          } catch {}
          return { sessionData, violationsData };
        } catch {
          return null;
        }
      };

      const [oldDoc, newDoc, session] = await Promise.all([
        fetchDrawing(roomData.active_old_drawing_id),
        fetchDrawing(roomData.active_new_drawing_id),
        fetchSession(),
      ]);

      if (roomData.active_audit_session_id && newDoc && session) {
        try {
          const { sessionData, violationsData } = session;
          
          ws.loadSessionIntoWorkspace(
            roomData.active_audit_session_id,
            newDoc,
            oldDoc,
            violationsData,
            sessionData.compliance_score ?? null,
            sessionData.client_name || null
          );

          // The session's violations are the NON-MATCHED findings only — `orchestrator.py`
          // never persists an AuditViolation for a MATCHED row, because there is nothing to
          // review about one. So restoring from them alone brings the findings back and drops
          // every green checkmark, which is what re-entering a compared room used to do.
          //
          // `canvas_markings` is the full set and the same source the live path renders from,
          // so when the room carries it, it wins — reconciled against the very violations
          // fetched above, which is what gives the reviewable rows their real ids. Falls
          // through to the session violations when a room has no markings stored (an audit
          // that was not a physical comparison), so this can only add rows, never remove them.
          const sessionMarkings = roomData.physical_comparison_results?.canvas_markings;
          if (Array.isArray(sessionMarkings) && sessionMarkings.length > 0) {
            useWorkspaceStore.setState({
              violations: reconcilePersistedIds(
                mapCanvasMarkingsToMarkers(sessionMarkings),
                violationsData
              ),
            });
          }
        } catch {}
      } else {
        if (oldDoc) ws.setOldDrawing(oldDoc);
        else ws.clearUpload("old");
        
        if (newDoc) ws.setNewDrawing(newDoc);
        else ws.clearUpload("new");

        if (roomData.physical_comparison_results && roomData.physical_comparison_results.canvas_markings) {
          const mappedMarkings = mapCanvasMarkingsToMarkers(
            roomData.physical_comparison_results.canvas_markings
          );

          // The comparison persisted an AuditViolation per non-MATCHED finding and stamped the
          // owning session id into diagnostics *before* the payload was cached, so a restored
          // room can still recover it even though this branch runs precisely when the room has
          // no `active_audit_session_id` of its own. Without this join every restored marker
          // keeps its synthetic `phys_chk_restored_*` id and cannot be reviewed.
          const restoredSessionId =
            roomData.physical_comparison_results.diagnostics?.audit_session_id ?? null;
          if (restoredSessionId) {
            useWorkspaceStore.getState().setActiveSessionId(restoredSessionId);
          }
          const reconciled = restoredSessionId
            ? reconcilePersistedIds(
                mappedMarkings,
                await fetchPersistedViolations(restoredSessionId)
              )
            : mappedMarkings;

          useWorkspaceStore.setState({ violations: reconciled });
        } else {
          useWorkspaceStore.setState({ violations: [] });
        }
      }
      
      if (roomData.physical_comparison_results) {
        useWorkspaceStore.setState({
          aiChecklistResults: roomData.physical_comparison_results,
          aiScanProgress: "completed"
        });
      } else {
        useWorkspaceStore.setState({
          aiChecklistResults: [],
          aiScanProgress: "idle"
        });
      }
      
      // NOW set activeRoom, so AuditWorkspace.tsx useEffect sees synchronized state
      set({ activeRoom: roomData, isLoading: false });
    } catch (err: any) {
      set({ error: err.message || "Failed to open room", isLoading: false });
    }
  },

  updateRoom: async (roomId, payload) => {
    try {
      const res = await fetch(`${baseUrl()}/api/v1/rooms/${roomId}`, {
        method: "PATCH",
        headers: buildHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify(payload)
      });
      const data = await parseAndValidate<Room>(res, RoomSchema);
      set((s) => ({
        rooms: s.rooms.map(r => r.id === roomId ? data : r),
        activeRoom: s.activeRoom?.id === roomId ? data : s.activeRoom
      }));
      // Invalidate the TanStack query cache so RoomsView gets the updated room details
      const { queryClient } = await import("../services/queryClient");
      const { roomKeys } = await import("../services/queryKeys");
      queryClient.invalidateQueries({ queryKey: roomKeys.lists() });
    } catch (err: any) {
      set({ error: err.message || "Failed to update room" });
    }
  },

  leaveRoom: async () => {
    const currentRoom = get().activeRoom;
    if (currentRoom) {
      await saveWorkspaceState(currentRoom.id);
    }
    useWorkspaceStore.getState().resetWorkspace();
    set({ activeRoom: null });
  },

  deleteRoom: async (roomId) => {
    try {
      const res = await fetch(`${baseUrl()}/api/v1/rooms/${roomId}`, {
        method: "DELETE",
        headers: buildHeaders()
      });
      await parseOrThrow(res);
      set((s) => ({ rooms: s.rooms.filter((r) => r.id !== roomId) }));
      return true;
    } catch (err: any) {
      set({ error: err.message || "Failed to delete room" });
      return false;
    }
  },
}));
