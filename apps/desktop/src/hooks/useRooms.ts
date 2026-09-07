/**
 * useRooms.ts — TanStack Query data layer for Room management
 *
 * Covers: list query, create, update, delete — with full optimistic updates
 * and rollback on all three mutations.
 *
 * ── What stays in Zustand (intentionally NOT here) ────────────────────────────
 * useRoomStore().openRoom()  — orchestrates a waterfall of 4 sequential API
 *   calls (room → old drawing → new drawing → audit session + violations) and
 *   then hydrates workspaceStore. That is a state machine, not a query.
 * useRoomStore().activeRoom  — cross-component mutable context; Zustand is the
 *   right home for shared mutable client state.
 * useRoomStore().leaveRoom() — pure client-side action, no network call.
 *
 * ── Backward compatibility ────────────────────────────────────────────────────
 * The existing useRoomStore is NOT deleted. Components that still call
 * `fetchRooms()` continue working. Migration to useRooms() is opt-in per
 * component.
 */

import { useCallback } from "react";
import {
  useQuery,
  useMutation,
  useQueryClient,
  type QueryFunctionContext,
} from "@tanstack/react-query";

import {
  fetchRooms,
  createRoom,
  updateRoom,
  deleteRoom,
  type CreateRoomParams,
  type UpdateRoomParams,
  type DeleteRoomContext,
  type UpdateRoomContext,
} from "../services/roomsApi";
import { roomKeys } from "../services/queryKeys";
import type { Room } from "../stores/roomStore";

// ─── Rollback context for create (optimistic append) ─────────────────────────

interface CreateRoomContext {
  previousRooms: Room[];
}

// ─── Sub-hook: List query ─────────────────────────────────────────────────────

/**
 * Fetches and caches the full rooms list.
 *
 * Pillar 1 (SWR): inherited from global QueryClient config (staleTime=60s).
 * Pillar 3 (race): AbortSignal is forwarded to fetchRooms() → fetch().
 * Pillar 4 (focus/reconnect): inherited from global QueryClient config.
 */
function useRoomsList() {
  return useQuery<Room[], Error>({
    queryKey: roomKeys.list(),
    queryFn: ({ signal }: QueryFunctionContext) => fetchRooms(signal),
  });
}

// ─── Sub-hook: Create room mutation ──────────────────────────────────────────

/**
 * Optimistically prepends the new room to the list immediately.
 * Uses a client-generated placeholder ID (prefixed `optimistic_`) that is
 * replaced by the real server ID after onSettled invalidates the query.
 */
function useCreateRoom() {
  const queryClient = useQueryClient();

  return useMutation<Room, Error, CreateRoomParams, CreateRoomContext>({
    mutationFn: createRoom,

    onMutate: async (variables) => {
      // Cancel in-flight list fetches so they don't overwrite the optimistic row
      await queryClient.cancelQueries({ queryKey: roomKeys.list() });
      const previousRooms = queryClient.getQueryData<Room[]>(roomKeys.list()) ?? [];

      const optimisticRoom: Room = {
        id: `optimistic_${Date.now()}`,
        name: variables.name,
        description: variables.description ?? null,
        client_name: variables.client_name ?? null,
        comparison_method: variables.comparison_method ?? "deterministic",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        last_opened_at: null,
      };

      queryClient.setQueryData<Room[]>(roomKeys.list(), [optimisticRoom, ...previousRooms]);
      return { previousRooms };
    },

    onError: (_err, _vars, context) => {
      // Roll back to the snapshot taken in onMutate
      if (context?.previousRooms !== undefined) {
        queryClient.setQueryData<Room[]>(roomKeys.list(), context.previousRooms);
      }
    },

    onSettled: () => {
      // Replace the optimistic placeholder with the real server record
      queryClient.invalidateQueries({ queryKey: roomKeys.lists() });
    },
  });
}

// ─── Sub-hook: Update room mutation ──────────────────────────────────────────

function useUpdateRoom() {
  const queryClient = useQueryClient();

  return useMutation<Room, Error, UpdateRoomParams, UpdateRoomContext>({
    mutationFn: updateRoom,

    onMutate: async (variables) => {
      await queryClient.cancelQueries({ queryKey: roomKeys.list() });
      await queryClient.cancelQueries({ queryKey: roomKeys.detail(variables.roomId) });

      const previousRooms = queryClient.getQueryData<Room[]>(roomKeys.list()) ?? [];

      // Optimistically merge the updated fields into the cached list entry
      queryClient.setQueryData<Room[]>(
        roomKeys.list(),
        previousRooms.map((r) =>
          r.id === variables.roomId ? { ...r, ...variables.payload } : r
        )
      );

      return { previousRooms };
    },

    onError: (_err, _vars, context) => {
      if (context?.previousRooms !== undefined) {
        queryClient.setQueryData<Room[]>(roomKeys.list(), context.previousRooms);
      }
    },

    onSettled: (_data, _err, variables) => {
      // Surgical: only the list and the specific detail, not the whole rooms cache
      queryClient.invalidateQueries({ queryKey: roomKeys.list() });
      queryClient.invalidateQueries({ queryKey: roomKeys.detail(variables.roomId) });
    },
  });
}

// ─── Sub-hook: Delete room mutation ──────────────────────────────────────────

function useDeleteRoom() {
  const queryClient = useQueryClient();

  return useMutation<{ deleted: boolean }, Error, string, DeleteRoomContext>({
    mutationFn: deleteRoom,

    onMutate: async (roomId) => {
      await queryClient.cancelQueries({ queryKey: roomKeys.list() });
      const previousRooms = queryClient.getQueryData<Room[]>(roomKeys.list()) ?? [];

      // Optimistically remove the room from the list immediately
      queryClient.setQueryData<Room[]>(
        roomKeys.list(),
        previousRooms.filter((r) => r.id !== roomId)
      );

      return { previousRooms };
    },

    onError: (_err, _vars, context) => {
      if (context?.previousRooms !== undefined) {
        queryClient.setQueryData<Room[]>(roomKeys.list(), context.previousRooms);
      }
    },

    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: roomKeys.lists() });
    },
  });
}

// ─── Composed hook: useRooms ──────────────────────────────────────────────────

/**
 * Primary public hook for room list management.
 *
 * Server state (rooms, loading, error) lives entirely in TanStack Query.
 * No loading flags are stored in Zustand — components read directly from
 * `isLoading`, `isFetching`, and `error` returned here.
 *
 * Usage:
 *   const { rooms, isLoading, createRoom, deleteRoom } = useRooms();
 */
export function useRooms() {
  const listQuery = useRoomsList();
  const createMutation = useCreateRoom();
  const updateMutation = useUpdateRoom();
  const deleteRoomMutation = useDeleteRoom();

  const create = useCallback(
    (params: CreateRoomParams) => createMutation.mutateAsync(params),
    [createMutation]
  );

  const update = useCallback(
    (roomId: string, payload: UpdateRoomParams["payload"]) =>
      updateMutation.mutateAsync({ roomId, payload }),
    [updateMutation]
  );

  const remove = useCallback(
    (roomId: string) => deleteRoomMutation.mutateAsync(roomId),
    [deleteRoomMutation]
  );

  return {
    // ── Server state ──
    rooms: listQuery.data ?? [],
    isLoading: listQuery.isLoading,
    /** true during a silent background refetch — show a subtle indicator, not a spinner */
    isFetching: listQuery.isFetching,
    error: listQuery.error,

    // ── Mutation pending states ──
    isCreating: createMutation.isPending,
    isUpdating: updateMutation.isPending,
    isDeleting: deleteRoomMutation.isPending,

    // ── Stable action callbacks ──
    createRoom: create,
    updateRoom: update,
    deleteRoom: remove,
  } as const;
}
