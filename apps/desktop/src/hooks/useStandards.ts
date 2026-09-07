/**
 * useStandards.ts — TanStack Query data layer for Engineering Standards
 *
 * Covers: list query, delete, and update — with full optimistic updates.
 *
 * ── What stays in Zustand ─────────────────────────────────────────────────────
 * uploadStandard() — uses XHR (not fetch) for onProgress callbacks; that is a
 *   state machine that needs Zustand's uploadStatus / uploadProgress fields.
 *   After a successful upload, the Zustand slice already calls fetchStandards()
 *   internally. With TanStack Query now owning the list, the correct pattern is
 *   to call `queryClient.invalidateQueries({ queryKey: standardKeys.lists() })`
 *   instead. See the integration note in createStandardsSlice.ts.
 *
 * ── Key benefit over the Zustand pattern ──────────────────────────────────────
 * The old pattern called `get().fetchStandards()` explicitly after EVERY delete
 * and update — that's a full round-trip that could race with other operations.
 * `invalidateQueries` in onSettled is smarter: it only triggers a refetch if
 * a component is currently subscribed to that query key. No subscription = no
 * unnecessary network call.
 */

import { useCallback } from "react";
import {
  useQuery,
  useMutation,
  useQueryClient,
  type QueryFunctionContext,
} from "@tanstack/react-query";

import {
  fetchStandards,
  deleteStandard,
  updateStandard,
  type UpdateStandardParams,
  type DeleteStandardContext,
  type UpdateStandardContext,
} from "../services/standardsApi";
import { standardKeys } from "../services/queryKeys";
import type { StandardDocument } from "../stores/audit/types";

// ─── Sub-hook: List query ─────────────────────────────────────────────────────

function useStandardsList() {
  return useQuery<StandardDocument[], Error>({
    queryKey: standardKeys.list(),
    queryFn: ({ signal }: QueryFunctionContext) => fetchStandards(signal),
    // Standards change infrequently — extend staleTime beyond the global 60s
    // default so the list doesn't refetch on every component mount cycle.
    staleTime: 3 * 60 * 1_000, // 3 min
  });
}

// ─── Sub-hook: Delete standard mutation ───────────────────────────────────────

function useDeleteStandard() {
  const queryClient = useQueryClient();

  return useMutation<void, Error, string, DeleteStandardContext>({
    mutationFn: deleteStandard,

    onMutate: async (standardId) => {
      await queryClient.cancelQueries({ queryKey: standardKeys.list() });
      const previousStandards =
        queryClient.getQueryData<StandardDocument[]>(standardKeys.list()) ?? [];

      // Optimistically remove the standard from the list immediately
      queryClient.setQueryData<StandardDocument[]>(
        standardKeys.list(),
        previousStandards.filter((s) => s.id !== standardId)
      );

      return { previousStandards };
    },

    onError: (_err, _vars, context) => {
      if (context?.previousStandards !== undefined) {
        queryClient.setQueryData<StandardDocument[]>(
          standardKeys.list(),
          context.previousStandards
        );
      }
    },

    onSettled: () => {
      // Sync with server — replaces the old `get().fetchStandards()` call
      queryClient.invalidateQueries({ queryKey: standardKeys.lists() });
    },
  });
}

// ─── Sub-hook: Update standard mutation ───────────────────────────────────────

function useUpdateStandard() {
  const queryClient = useQueryClient();

  return useMutation<StandardDocument, Error, UpdateStandardParams, UpdateStandardContext>({
    mutationFn: updateStandard,

    onMutate: async (variables) => {
      await queryClient.cancelQueries({ queryKey: standardKeys.list() });
      const previousStandards =
        queryClient.getQueryData<StandardDocument[]>(standardKeys.list()) ?? [];

      // Optimistically patch the matching standard in the cached list
      queryClient.setQueryData<StandardDocument[]>(
        standardKeys.list(),
        previousStandards.map((s) =>
          s.id === variables.id
            ? {
                ...s,
                name: variables.name || s.name,
                category: variables.category || s.category,
                description: variables.description || s.description,
              }
            : s
        )
      );

      return { previousStandards };
    },

    onError: (_err, _vars, context) => {
      if (context?.previousStandards !== undefined) {
        queryClient.setQueryData<StandardDocument[]>(
          standardKeys.list(),
          context.previousStandards
        );
      }
    },

    onSettled: (_data, _err, variables) => {
      // Surgical invalidation: only the list and the specific detail entry
      queryClient.invalidateQueries({ queryKey: standardKeys.list() });
      queryClient.invalidateQueries({ queryKey: standardKeys.detail(variables.id) });
    },
  });
}

// ─── Composed hook: useStandards ──────────────────────────────────────────────

/**
 * Primary public hook for the engineering standards list.
 *
 * Usage:
 *   const { standards, isLoading, deleteStandard, updateStandard } = useStandards();
 *
 * Integration note for upload:
 *   After a successful XHR upload in createStandardsSlice, call:
 *     queryClient.invalidateQueries({ queryKey: standardKeys.lists() })
 *   instead of get().fetchStandards() to keep the cache consistent.
 *   Import queryClient from "../services/queryClient" in the slice.
 */
export function useStandards() {
  const listQuery = useStandardsList();
  const deleteMutation = useDeleteStandard();
  const updateMutation = useUpdateStandard();

  const remove = useCallback(
    (id: string) => deleteMutation.mutateAsync(id),
    [deleteMutation]
  );

  const update = useCallback(
    (params: UpdateStandardParams) => updateMutation.mutateAsync(params),
    [updateMutation]
  );

  return {
    // ── Server state ──
    standards: listQuery.data ?? [],
    isLoading: listQuery.isLoading,
    isFetching: listQuery.isFetching,
    error: listQuery.error,

    // ── Mutation state ──
    isDeleting: deleteMutation.isPending,
    isUpdating: updateMutation.isPending,
    mutationError: deleteMutation.error ?? updateMutation.error,

    // ── Stable actions ──
    deleteStandard: remove,
    updateStandard: update,
  } as const;
}
