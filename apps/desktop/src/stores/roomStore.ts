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
 * The backend accepts `"rag"` on input **permanently** and normalises it, so rooms written
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
    // Save current active room's state before switching
    const currentRoom = get().activeRoom;
    if (currentRoom) {
      await saveWorkspaceState(currentRoom.id);
    }
    
    // Switch to new room's state immediately for fast UI feedback
    await loadWorkspaceState(roomId);
    
    set({ isLoading: true, error: null });
    try {
      const roomRes = await fetch(`${baseUrl()}/api/v1/rooms/${roomId}`, { headers: buildHeaders() });
      const roomData = await parseAndValidate<Room>(roomRes, RoomSchema);

      // Fetch drawings FIRST before updating activeRoom to prevent sync race condition
      const ws = useWorkspaceStore.getState();
      
      let oldDoc: DrawingItem | null = null;
      if (roomData.active_old_drawing_id) {
        try {
          const oldRes = await fetch(`${baseUrl()}/api/v1/drawings/${roomData.active_old_drawing_id}`, { headers: buildHeaders() });
          oldDoc = await parseOrThrow<DrawingItem>(oldRes);
        } catch {}
      }
      
      let newDoc: DrawingItem | null = null;
      if (roomData.active_new_drawing_id) {
        try {
          const newRes = await fetch(`${baseUrl()}/api/v1/drawings/${roomData.active_new_drawing_id}`, { headers: buildHeaders() });
          newDoc = await parseOrThrow<DrawingItem>(newRes);
        } catch {}
      }

      if (roomData.active_audit_session_id && newDoc) {
        try {
          const sessionRes = await fetch(`${baseUrl()}/api/v1/audits/sessions/${roomData.active_audit_session_id}`, { headers: buildHeaders() });
          const sessionData = await parseOrThrow<any>(sessionRes);
          
          let violationsData = [];
          try {
            const violationsRes = await fetch(`${baseUrl()}/api/v1/audits/sessions/${roomData.active_audit_session_id}/violations`, { headers: buildHeaders() });
            violationsData = await parseOrThrow<any>(violationsRes);
          } catch {}
          
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
