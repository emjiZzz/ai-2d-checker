/**
 * useAdminUsers.ts — TanStack Query data layer for Enterprise User Management
 *
 * Covers: user list query, create user, update user, delete user — with
 * full optimistic updates and typed rollback contexts on all mutations.
 *
 * ── What stays in useAdminStore ───────────────────────────────────────────────
 * fetchDiagnostics()        — fetches separate system metrics; different key/scope
 * fetchAdminAuditSessions() — audit history with its own is_deleted flag filter
 * softDeleteAuditSession()  — intertwined with audit session domain
 * restoreAuditSession()     — same
 * emptyTrash()              — same
 * triggerBackup/Restore()   — currently mock; not server state
 *
 * ── Why optimistic creates need a placeholder ID ──────────────────────────────
 * We don't know the server-generated user ID before the POST resolves. The
 * optimistic row uses `optimistic_${username}` as a placeholder. Because
 * username is the lookup key for this entity (not a UUID), the placeholder ID
 * is never exposed to users — it is replaced by the real record after
 * invalidateQueries triggers a fresh fetch in onSettled.
 */

import { useCallback } from "react";
import {
  useQuery,
  useMutation,
  useQueryClient,
  type QueryFunctionContext,
} from "@tanstack/react-query";

import {
  fetchAdminUsers,
  createAdminUser,
  deleteAdminUser,
  updateAdminUser,
  type CreateUserParams,
  type UpdateUserParams,
  type DeleteUserContext,
  type UpdateUserContext,
} from "../services/adminApi";
import { adminUserKeys } from "../services/queryKeys";
import type { EnterpriseUser } from "../stores/adminStore";

// ─── Rollback context for create ─────────────────────────────────────────────

interface CreateUserContext {
  previousUsers: EnterpriseUser[];
}

// ─── Sub-hook: User list query ────────────────────────────────────────────────

function useAdminUsersList() {
  return useQuery<EnterpriseUser[], Error>({
    queryKey: adminUserKeys.list(),
    queryFn: ({ signal }: QueryFunctionContext) => fetchAdminUsers(signal),
    // The admin user list is an admin-only view that doesn't need real-time
    // freshness. 2 minutes is a reasonable staleTime for this use case.
    staleTime: 2 * 60 * 1_000, // 2 min
  });
}

// ─── Sub-hook: Create user mutation ──────────────────────────────────────────

function useCreateUser() {
  const queryClient = useQueryClient();

  return useMutation<EnterpriseUser, Error, CreateUserParams, CreateUserContext>({
    mutationFn: createAdminUser,

    onMutate: async (variables) => {
      await queryClient.cancelQueries({ queryKey: adminUserKeys.list() });
      const previousUsers = queryClient.getQueryData<EnterpriseUser[]>(adminUserKeys.list()) ?? [];

      const optimisticUser: EnterpriseUser = {
        id: `optimistic_${variables.username}`,
        username: variables.username,
        role: variables.role,
        active: true,
        created_at: new Date().toISOString(),
        permissions: [],
      };

      queryClient.setQueryData<EnterpriseUser[]>(adminUserKeys.list(), [
        optimisticUser,
        ...previousUsers,
      ]);

      return { previousUsers };
    },

    onError: (_err, _vars, context) => {
      if (context?.previousUsers !== undefined) {
        queryClient.setQueryData<EnterpriseUser[]>(adminUserKeys.list(), context.previousUsers);
      }
    },

    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: adminUserKeys.lists() });
    },
  });
}

// ─── Sub-hook: Delete user mutation ──────────────────────────────────────────

function useDeleteUser() {
  const queryClient = useQueryClient();

  return useMutation<void, Error, string, DeleteUserContext>({
    mutationFn: deleteAdminUser,

    onMutate: async (username) => {
      await queryClient.cancelQueries({ queryKey: adminUserKeys.list() });
      const previousUsers = queryClient.getQueryData<EnterpriseUser[]>(adminUserKeys.list()) ?? [];

      queryClient.setQueryData<EnterpriseUser[]>(
        adminUserKeys.list(),
        previousUsers.filter((u) => u.username !== username)
      );

      return { previousUsers };
    },

    onError: (_err, _vars, context) => {
      if (context?.previousUsers !== undefined) {
        queryClient.setQueryData<EnterpriseUser[]>(adminUserKeys.list(), context.previousUsers);
      }
    },

    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: adminUserKeys.lists() });
    },
  });
}

// ─── Sub-hook: Update user mutation ──────────────────────────────────────────

function useUpdateUser() {
  const queryClient = useQueryClient();

  return useMutation<EnterpriseUser, Error, UpdateUserParams, UpdateUserContext>({
    mutationFn: updateAdminUser,

    onMutate: async (variables) => {
      await queryClient.cancelQueries({ queryKey: adminUserKeys.list() });
      const previousUsers = queryClient.getQueryData<EnterpriseUser[]>(adminUserKeys.list()) ?? [];

      // Optimistically merge the partial update into the cached user record
      queryClient.setQueryData<EnterpriseUser[]>(
        adminUserKeys.list(),
        previousUsers.map((u) =>
          u.username === variables.username
            ? {
                ...u,
                ...(variables.updates.active !== undefined && { active: variables.updates.active }),
                ...(variables.updates.role !== undefined && { role: variables.updates.role }),
              }
            : u
        )
      );

      return { previousUsers };
    },

    onError: (_err, _vars, context) => {
      if (context?.previousUsers !== undefined) {
        queryClient.setQueryData<EnterpriseUser[]>(adminUserKeys.list(), context.previousUsers);
      }
    },

    onSettled: (_data, _err, variables) => {
      queryClient.invalidateQueries({ queryKey: adminUserKeys.list() });
      queryClient.invalidateQueries({
        queryKey: adminUserKeys.detail(variables.username),
      });
    },
  });
}

// ─── Composed hook: useAdminUsers ─────────────────────────────────────────────

/**
 * Primary public hook for admin user management.
 *
 * Replaces the isLoading / fetchUsers / createUser / deleteUser / updateUser
 * boilerplate that was duplicated across adminStore actions. Components now
 * get automatic loading states, error states, and background refetch for free.
 *
 * Usage:
 *   const { users, isLoading, createUser, deleteUser, updateUser } = useAdminUsers();
 */
export function useAdminUsers() {
  const listQuery = useAdminUsersList();
  const createMutation = useCreateUser();
  const deleteMutation = useDeleteUser();
  const updateMutation = useUpdateUser();

  const create = useCallback(
    (params: CreateUserParams) => createMutation.mutateAsync(params),
    [createMutation]
  );

  const remove = useCallback(
    (username: string) => deleteMutation.mutateAsync(username),
    [deleteMutation]
  );

  const update = useCallback(
    (username: string, updates: UpdateUserParams["updates"]) =>
      updateMutation.mutateAsync({ username, updates }),
    [updateMutation]
  );

  return {
    // ── Server state ──
    users: listQuery.data ?? [],
    isLoading: listQuery.isLoading,
    isFetching: listQuery.isFetching,
    error: listQuery.error,

    // ── Mutation state ──
    isCreating: createMutation.isPending,
    isDeleting: deleteMutation.isPending,
    isUpdating: updateMutation.isPending,
    mutationError:
      createMutation.error ?? deleteMutation.error ?? updateMutation.error,

    // ── Stable actions ──
    createUser: create,
    deleteUser: remove,
    updateUser: update,
  } as const;
}
