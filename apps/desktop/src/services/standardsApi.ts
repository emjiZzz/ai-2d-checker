/**
 * standardsApi.ts — Network layer for the Standards domain (SRP: no React, no cache)
 *
 * NOTE: uploadStandard is intentionally NOT here. File uploads use XHR
 * (not fetch) because they need `onProgress` callbacks for the progress bar.
 * XHR state is owned by the Zustand createStandardsSlice — it is a genuine
 * state machine that TanStack Query cannot model cleanly. Only the read and
 * simple-write operations are migrated.
 */

import { buildHeaders, baseUrl, parseOrThrow } from "./fetchUtils";
import type { StandardDocument } from "../stores/audit/types";

// ─── Mutation param types ─────────────────────────────────────────────────────

export interface UpdateStandardParams {
  id: string;
  name: string;
  category: string;
  description: string;
}

// ─── Rollback context types (consumed by useStandards.ts) ─────────────────────

export interface DeleteStandardContext {
  previousStandards: StandardDocument[];
}

export interface UpdateStandardContext {
  previousStandards: StandardDocument[];
}

// ─── Public API ───────────────────────────────────────────────────────────────

/** GET /api/v1/standards — fetches all available standards. */
export async function fetchStandards(signal: AbortSignal): Promise<StandardDocument[]> {
  const res = await fetch(`${baseUrl()}/api/v1/standards`, {
    headers: buildHeaders(),
    signal,
  });
  return parseOrThrow<StandardDocument[]>(res);
}

/**
 * DELETE /api/v1/standards/:id — removes a standard.
 *
 * The current Zustand implementation calls fetchStandards() after every
 * delete/update. With TanStack Query this is replaced by invalidateQueries()
 * in onSettled, which is more precise: it only refetches if the query is
 * currently observed by a mounted component.
 */
export async function deleteStandard(id: string): Promise<void> {
  const res = await fetch(`${baseUrl()}/api/v1/standards/${id}`, {
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

/** PATCH /api/v1/standards/:id — updates name/category/description via query params. */
export async function updateStandard(params: UpdateStandardParams): Promise<StandardDocument> {
  const qp = new URLSearchParams();
  if (params.name) qp.set("name", params.name);
  if (params.category) qp.set("category", params.category);
  if (params.description) qp.set("description", params.description);
  const res = await fetch(`${baseUrl()}/api/v1/standards/${params.id}?${qp.toString()}`, {
    method: "PATCH",
    headers: buildHeaders(),
  });
  return parseOrThrow<StandardDocument>(res);
}
