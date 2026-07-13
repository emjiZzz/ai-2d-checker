/**
 * useManageItems.ts — Feature Management Data Layer
 *
 * This is the primary public API for the features management module.
 * It composes three focused sub-hooks into a single surface that components
 * consume — each sub-hook is responsible for exactly one concern (SRP):
 *
 *   useItemsList         → Stale-while-revalidate list query with race protection
 *   useUpdateItemStatus  → Optimistic status toggle with rollback
 *   useAddItem           → Optimistic append mutation with rollback
 *
 * ── Pillar 5: Server vs. Client State Boundary ────────────────────────────────
 *
 * ALL asynchronous server state (loading, data, error, pagination) is owned
 * exclusively by TanStack Query. We do NOT mirror it into Zustand.
 *
 * The only local (client) state in this file is:
 *   - `page` (pagination cursor) — pure UI navigation state, not server data.
 *   - `rollbackItemId` — which item's row should show an error indicator.
 *     This is ephemeral UI feedback; it has no server representation and is
 *     reset automatically after a fixed interval.
 *
 * This clean boundary means the cache is the single source of truth for item
 * data. Components never need to sync Zustand ↔ Query — a category of bugs
 * that plagues apps that keep server data in multiple places.
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
 * Handles fetching and caching the paginated items list.
 *
 * Pillar 1 — SWR: staleTime/gcTime are configured on the global QueryClient;
 * they do not need to be repeated here unless this query has different needs.
 *
 * Pillar 3 — Race Protection: TanStack Query passes an AbortSignal into every
 * queryFn. We destructure it from the context and forward it to fetchItems(),
 * which passes it to fetch(). This aborts the underlying HTTP request at the
 * browser layer when the query key changes (e.g. page flip) or the component
 * unmounts while a request is in flight.
 */
function useItemsList(page: number) {
  return useQuery<ItemsPage, Error>({
    queryKey: itemQueryKeys.list(page),

    queryFn: async ({ signal }: QueryFunctionContext) => {
      // `signal` is TanStack Query's own AbortSignal. It is aborted when:
      //   1. The query key changes while this fetch is in-flight (e.g. page++)
      //   2. The component unmounts before the response arrives
      //   3. cancelQueries() is called (see useUpdateItemStatus.onMutate)
      return fetchItems(page, signal);
    },

    // Keep showing previous page data while the next page loads, preventing
    // a jarring blank → loaded flash during pagination.
    placeholderData: (previousData) => previousData,

    // Pillar 4 (hook-level override example): for this specific high-change
    // list query, we want to refetch every 30 s even without user interaction.
    // This overrides the global default for just this query.
    refetchInterval: 30 * 1_000, // 30 s
  });
}

// ─── Sub-hook: Status Toggle Mutation ────────────────────────────────────────

/**
 * Handles optimistic status toggling with clean rollback on failure.
 *
 * ── Optimistic Update Lifecycle (Pillar 2) ────────────────────────────────────
 *
 * onMutate  → fires BEFORE the network call. We:
 *   1. Cancel outgoing queries for this key to prevent a stale response from
 *      overwriting the optimistic UI state after we write it.
 *   2. Snapshot the current cache so we have a clean state to roll back to.
 *   3. Write the optimistic (expected) result directly into the cache. The UI
 *      re-renders instantly — users see the change without waiting for the
 *      network.
 *   4. Return the snapshot as `context` so TanStack Query threads it into onError.
 *
 * onError   → fires if the network call fails (or throws). We:
 *   1. Restore the exact pre-mutation cache using the snapshotted context.
 *   2. Set rollbackItemId local state so the UI can render an error indicator
 *      on the specific row that failed (client state — ephemeral, UI-only).
 *
 * onSettled → fires after EITHER success OR error. We:
 *   1. Invalidate the relevant query keys so TanStack Query fetches the
 *      authoritative server state — closing the loop on the optimistic cycle.
 *   This is "surgical" invalidation: we only invalidate the affected list page
 *   and the specific item detail, not the entire items cache.
 */
function useUpdateItemStatus(
  page: number,
  onRollback: (itemId: string) => void
) {
  const queryClient = useQueryClient();

  return useMutation<Item, Error, UpdateItemStatusParams, UpdateStatusRollbackContext>({
    mutationFn: patchItemStatus,

    // ── Step 1: Optimistic write ──────────────────────────────────────────────
    onMutate: async (variables) => {
      // Cancel any in-flight GETs for the list and detail so they don't
      // overwrite the optimistic state we are about to write. This is critical:
      // without it, a slow background refetch could arrive AFTER our optimistic
      // write and reset the UI to the stale pre-mutation state.
      await queryClient.cancelQueries({ queryKey: itemQueryKeys.list(page) });
      await queryClient.cancelQueries({
        queryKey: itemQueryKeys.detail(variables.itemId),
      });

      // Snapshot the current cache value for the list page and the detail entry.
      // We must do this AFTER cancelQueries so we get the latest settled state.
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
