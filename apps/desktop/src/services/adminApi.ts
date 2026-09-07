/**
 * adminApi.ts — Network layer for Admin User Management (SRP: no React, no cache)
 *
 * Only covers user CRUD. System diagnostics and audit-session admin actions
 * remain in useAdminStore — they have different ownership/refresh semantics
 * and would need separate query keys that aren't worth the migration cost now.
 */

import { buildHeaders, baseUrl, parseOrThrow } from "./fetchUtils";
import type { EnterpriseUser } from "../stores/adminStore";

// ─── Mutation param types ─────────────────────────────────────────────────────

export interface CreateUserParams {
  username: string;
  password: string;
  role: string;
}

export interface UpdateUserParams {
  username: string;
  updates: {
    active?: boolean;
    role?: string;
    password?: string;
  };
}

// ─── Rollback context types (consumed by useAdminUsers.ts) ────────────────────

export interface DeleteUserContext {
  previousUsers: EnterpriseUser[];
}

export interface UpdateUserContext {
  previousUsers: EnterpriseUser[];
}

// ─── Public API ───────────────────────────────────────────────────────────────

/** GET /api/v1/admin/users — fetches the full user list. */
export async function fetchAdminUsers(signal: AbortSignal): Promise<EnterpriseUser[]> {
  const res = await fetch(`${baseUrl()}/api/v1/admin/users`, {
    headers: buildHeaders(),
    signal,
  });
  return parseOrThrow<EnterpriseUser[]>(res);
}

/** POST /api/v1/admin/users — creates a new enterprise user. */
export async function createAdminUser(params: CreateUserParams): Promise<EnterpriseUser> {
  const res = await fetch(`${baseUrl()}/api/v1/admin/users`, {
    method: "POST",
    headers: { ...buildHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  return parseOrThrow<EnterpriseUser>(res);
}

/** DELETE /api/v1/admin/users/:username — removes a user account. */
export async function deleteAdminUser(username: string): Promise<void> {
  const res = await fetch(`${baseUrl()}/api/v1/admin/users/${username}`, {
    method: "DELETE",
    headers: buildHeaders(),
  });
  if (!res.ok) {
    let body: unknown;
    try { body = await res.json(); } catch { throw new Error(`HTTP ${res.status}`); }
    const b = body as Record<string, unknown>;
    throw new Error((b?.detail ?? b?.message ?? `HTTP ${res.status}`) as string);
  }
}

/** PATCH /api/v1/admin/users/:username — updates active status, role, or password. */
export async function updateAdminUser(params: UpdateUserParams): Promise<EnterpriseUser> {
  const res = await fetch(`${baseUrl()}/api/v1/admin/users/${params.username}`, {
    method: "PATCH",
    headers: { ...buildHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(params.updates),
  });
  return parseOrThrow<EnterpriseUser>(res);
}

// ─── System Metrics ──────────────────────────────────────────────────────────

/** GET /api/v1/system/database — fetches database diagnostics. */
export async function fetchDatabaseMetrics(signal?: AbortSignal): Promise<any> {
  const res = await fetch(`${baseUrl()}/api/v1/system/database`, {
    headers: buildHeaders(),
    signal,
  });
  return parseOrThrow<any>(res);
}

/** GET /api/v1/system/storage — fetches storage quota metrics. */
export async function fetchStorageMetrics(signal?: AbortSignal): Promise<any> {
  const res = await fetch(`${baseUrl()}/api/v1/system/storage`, {
    headers: buildHeaders(),
    signal,
  });
  return parseOrThrow<any>(res);
}
