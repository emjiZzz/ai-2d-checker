/**
 * The public API for the features management module, composing three sub-hooks:
 *
 *   useItemsList         list query with race protection
 *   useUpdateItemStatus  optimistic status toggle with rollback
 *   useAddItem           optimistic append with rollback
 *
 * Server state lives in TanStack Query and is never mirrored into Zustand, so the cache is the
 * only source of truth for item data and nothing has to keep the two in sync. The only local
 * state here is `page`, a UI navigation cursor, and `rollbackItemId`, which row shows an error
 * indicator -- neither has a server representation.
 */

import { useState, useCallback } from "react";
import {
  useQuery,
  useMutation,
  useQueryClient,
  type QueryFunctionContext,
} from "@tanstack/react-query";

import {
  fetchItems,
  fetchItemById,
  patchItemStatus,
  postItem,
  type Item,
  type ItemsPage,
  type UpdateItemStatusParams,
  type AddItemParams,
} from "../services/itemsApi";
import { itemQueryKeys } from "../services/queryKeys";

// ─── Rollback Context Types ───────────────────────────────────────────────────

/**
 * The data we snapshot before an optimistic status update so we can restore it
 * on failure. TanStack Query threads this value from onMutate → onError for us.
 */
interface UpdateStatusRollbackContext {
  /** Snapshot of the paginated list before the optimistic write. */
  previousList: ItemsPage | undefined;
  /** Snapshot of the single-item detail cache entry (if it was loaded). */
  previousDetail: Item | undefined;
  /** The page number that was visible when the mutation fired. */
  page: number;
}

/**
 * The data we snapshot before an optimistic add so we can restore it
 * if the POST fails.
 */
interface AddItemRollbackContext {
  previousList: ItemsPage | undefined;
  page: number;
}

// ─── Sub-hook: List Query ─────────────────────────────────────────────────────

/**
 * Fetches and caches the paginated items list. `staleTime` and `gcTime` come from the global
 * QueryClient. The `signal` is forwarded all the way to `fetch`, so a page flip or an unmount
 * aborts the in-flight HTTP request rather than letting it land on a stale key.
 */
function useItemsList(page: number) {
  return useQuery<ItemsPage, Error>({
    queryKey: itemQueryKeys.list(page),

    queryFn: async ({ signal }: QueryFunctionContext) => {
      // Also aborted by `cancelQueries` -- see useUpdateItemStatus.onMutate.
      return fetchItems(page, signal);
    },

    // Hold the previous page on screen while the next loads, so pagination does not flash blank.
    placeholderData: (previousData) => previousData,

    // Overrides the global default: this list changes without user interaction.
    refetchInterval: 30 * 1_000,
  });
}

// ─── Sub-hook: Status Toggle Mutation ────────────────────────────────────────

/**
 * Optimistic status toggling with rollback on failure.
 *
 * The ordering in `onMutate` is the part that matters: cancel in-flight queries first, then
 * snapshot, then write. Snapshotting before the cancel captures a value a settling request is
 * about to replace, and skipping the cancel lets a slow background refetch land after the
 * optimistic write and reset the UI to the pre-mutation state.
 *
 * `onSettled` invalidates only the affected list page and item detail rather than the whole items
 * cache, so one row's toggle does not refetch every page the user has visited.
 */
function useUpdateItemStatus(
  page: number,
  onRollback: (itemId: string) => void
) {
  const queryClient = useQueryClient();

  return useMutation<Item, Error, UpdateItemStatusParams, UpdateStatusRollbackContext>({
    mutationFn: patchItemStatus,

    onMutate: async (variables) => {
      await queryClient.cancelQueries({ queryKey: itemQueryKeys.list(page) });
      await queryClient.cancelQueries({
        queryKey: itemQueryKeys.detail(variables.itemId),
      });

      // After the cancel, so this is the latest settled state. See the docstring above.
      const previousList = queryClient.getQueryData<ItemsPage>(
        itemQueryKeys.list(page)
      );
      const previousDetail = queryClient.getQueryData<Item>(
        itemQueryKeys.detail(variables.itemId)
      );

      // Optimistically rewrite the list cache: find the item and swap its status.
      if (previousList) {
        queryClient.setQueryData<ItemsPage>(itemQueryKeys.list(page), {
          ...previousList,
          items: previousList.items.map((item) =>
            item.id === variables.itemId
              ? { ...item, status: variables.status }
              : item
          ),
        });
      }

      // Optimistically rewrite the detail cache if it exists in memory.
      if (previousDetail) {
        queryClient.setQueryData<Item>(itemQueryKeys.detail(variables.itemId), {
          ...previousDetail,
          status: variables.status,
        });
      }

      // Return the snapshot as `context` — TanStack Query passes it to onError.
      return { previousList, previousDetail, page };
    },

    // ── Step 2: Rollback on failure ───────────────────────────────────────────
    onError: (_error, variables, context) => {
      if (!context) return;

      // Restore the exact pre-mutation state from the snapshot.
      if (context.previousList !== undefined) {
        queryClient.setQueryData<ItemsPage>(
          itemQueryKeys.list(context.page),
          context.previousList
        );
      }
      if (context.previousDetail !== undefined) {
        queryClient.setQueryData<Item>(
          itemQueryKeys.detail(variables.itemId),
          context.previousDetail
        );
      }

      // Delegate UI feedback to the parent hook's local state.
      // This is the ONLY client state that crosses the server/client boundary —
      // it is purely ephemeral, never serialised, and resets automatically.
      onRollback(variables.itemId);
    },

    // ── Step 3: Surgical invalidation ─────────────────────────────────────────
    onSettled: (_data, _error, variables) => {
      // Always run after success or error. Fetch the authoritative server state
      // for only the queries that could have been affected — not everything.
      queryClient.invalidateQueries({ queryKey: itemQueryKeys.list(page) });
      queryClient.invalidateQueries({
        queryKey: itemQueryKeys.detail(variables.itemId),
      });
    },
  });
}

// ─── Sub-hook: Add Item Mutation ─────────────────────────────────────────────

/**
 * Handles optimistic item creation with rollback.
 *
 * We append a temporary "pending" item to the list immediately. Because we
 * don't know the server-generated ID yet, we use a deterministic client-side
 * placeholder ID prefixed with `optimistic_`. The invalidation in onSettled
 * replaces it with the real server record.
 */
function useAddItem(page: number) {
  const queryClient = useQueryClient();

  return useMutation<Item, Error, AddItemParams, AddItemRollbackContext>({
    mutationFn: postItem,

    onMutate: async (variables) => {
      await queryClient.cancelQueries({ queryKey: itemQueryKeys.list(page) });

      const previousList = queryClient.getQueryData<ItemsPage>(
        itemQueryKeys.list(page)
      );

      if (previousList) {
        // Construct an optimistic item using a client-generated placeholder ID.
        // The `updatedAt` here is intentionally set to now so the row renders
        // with a "just created" timestamp that is visually coherent.
        const optimisticItem: Item = {
          id: `optimistic_${Date.now()}`,
          name: variables.name,
          description: variables.description,
          status: "active",
          updatedAt: new Date().toISOString(),
          metadata: variables.metadata ?? {},
        };

        queryClient.setQueryData<ItemsPage>(itemQueryKeys.list(page), {
          ...previousList,
          items: [optimisticItem, ...previousList.items],
          total: previousList.total + 1,
        });
      }

      return { previousList, page };
    },

    onError: (_error, _variables, context) => {
      if (!context || context.previousList === undefined) return;
      // Restore the pre-mutation list, removing the optimistic placeholder.
      queryClient.setQueryData<ItemsPage>(
        itemQueryKeys.list(context.page),
        context.previousList
      );
    },

    onSettled: () => {
      // Invalidate all list queries so the real server record (with its true ID)
      // replaces the optimistic placeholder.
      queryClient.invalidateQueries({ queryKey: itemQueryKeys.lists() });
    },
  });
}

// ─── Composed Hook: useManageItems ────────────────────────────────────────────

/**
 * useManageItems — Primary public hook for the features management module.
 *
 * This is the only hook components should import. It composes the focused
 * sub-hooks above and exposes a clean, stable API surface.
 *
 * Client state kept here (NOT in server cache):
 *   - `page`          — current pagination page (pure navigation state)
 *   - `rollbackItemId` — ID of the last item that failed a mutation, used to
 *                        show an error indicator on that specific row. This is
 *                        reset after 3 seconds automatically.
 *
 * Everything else (items data, loading, error) comes directly from the
 * TanStack Query cache — no duplication, no syncing, no stale reads.
 */
export function useManageItems() {
  // ── Client-only state (not server state) ──────────────────────────────────
  const [page, setPage] = useState<number>(1);

  // Tracks which item row should display a rollback error indicator.
  // This is ephemeral UI state — it has no server representation.
  const [rollbackItemId, setRollbackItemId] = useState<string | null>(null);

  const handleRollback = useCallback((itemId: string) => {
    setRollbackItemId(itemId);
    // Auto-clear after 3 s so the error badge disappears without user action.
    setTimeout(() => setRollbackItemId(null), 3_000);
  }, []);

  // ── Compose sub-hooks ──────────────────────────────────────────────────────
  const listQuery = useItemsList(page);
  const updateStatusMutation = useUpdateItemStatus(page, handleRollback);
  const addItemMutation = useAddItem(page);

  // ── Stable action callbacks ────────────────────────────────────────────────
  const toggleItemStatus = useCallback(
    (itemId: string, currentStatus: Item["status"]) => {
      const nextStatus: Item["status"] =
        currentStatus === "active" ? "inactive" : "active";
      updateStatusMutation.mutate({ itemId, status: nextStatus });
    },
    [updateStatusMutation]
  );

  const addItem = useCallback(
    (params: AddItemParams) => addItemMutation.mutate(params),
    [addItemMutation]
  );

  // ── Public surface ─────────────────────────────────────────────────────────
  return {
    // ── Server state (from TanStack Query) ──
    items: listQuery.data?.items ?? [],
    total: listQuery.data?.total ?? 0,
    isLoading: listQuery.isLoading,
    isFetching: listQuery.isFetching, // silent background refetch indicator
    listError: listQuery.error,

    // ── Mutation state ──
    isUpdatingStatus: updateStatusMutation.isPending,
    isAdding: addItemMutation.isPending,
    mutationError: updateStatusMutation.error ?? addItemMutation.error,

    // ── Client UI state ──
    page,
    setPage,
    rollbackItemId, // the ID of the row that just rolled back (show error badge)

    // ── Actions ──
    toggleItemStatus,
    addItem,
  } as const;
}

// ─── Optional: Single-item detail hook ───────────────────────────────────────

/**
 * Fetches a single item's full detail record.
 *
 * Extracted as a separate hook to follow SRP: components that render an item
 * list don't need the detail data, and detail panels don't need the full list.
 *
 * Pillar 3 (race protection) is active via the `signal` forwarding in
 * fetchItemById(). If the user quickly navigates between items, only the last
 * request completes; previous in-flight fetches are aborted.
 *
 * Pillar 4: refetchOnWindowFocus is inherited from the global QueryClient
 * config, ensuring the detail view is always fresh when the user returns from
 * another tab.
 */
export function useItemDetail(itemId: string | null) {
  return useQuery<Item, Error>({
    queryKey: itemQueryKeys.detail(itemId ?? ""),
    queryFn: ({ signal }: QueryFunctionContext) => {
      // Type-safe guard: enabled:false prevents this from firing when itemId is
      // null, but TypeScript doesn't know that, so we assert here.
      if (!itemId) throw new Error("itemId is required");
      return fetchItemById(itemId, signal);
    },
    // Only run the query when we actually have an ID to fetch.
    enabled: itemId !== null && itemId.length > 0,
    // Detail records change less often — use a longer staleTime to reduce
    // unnecessary re-fetches while a user is reading the detail panel.
    staleTime: 2 * 60 * 1_000, // 2 min
  });
}
