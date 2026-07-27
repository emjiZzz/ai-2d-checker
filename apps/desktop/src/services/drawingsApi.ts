/**
 * drawingsApi.ts — Network layer for Drawings (SRP: no React, no cache)
 *
 * Covers read operations for drawings. Uploads are handled via XHR in
 * createUploadSlice.ts because they need progress callbacks.
 */

import { buildHeaders, baseUrl, parseOrThrow } from "./fetchUtils";
import type { DrawingItem } from "../stores/workspaceStore";

// ─── Public API ───────────────────────────────────────────────────────────────

/** GET /api/v1/drawings — fetches all available drawings. */
export async function fetchDrawings(signal?: AbortSignal): Promise<DrawingItem[]> {
  const res = await fetch(`${baseUrl()}/api/v1/drawings`, {
    headers: buildHeaders(),
    signal,
  });
  return parseOrThrow<DrawingItem[]>(res);
}

/** GET /api/v1/drawings/:id — fetches a single drawing's metadata. */
export async function fetchDrawing(id: string, signal?: AbortSignal): Promise<DrawingItem> {
  const res = await fetch(`${baseUrl()}/api/v1/drawings/${id}`, {
    headers: buildHeaders(),
    signal,
  });
  return parseOrThrow<DrawingItem>(res);
}

/** GET /api/v1/drawings/:id/scene — fetches vector scene primitives and CAD handles. */
export async function fetchDrawingScene(id: string, signal?: AbortSignal): Promise<any> {
  const res = await fetch(`${baseUrl()}/api/v1/drawings/${id}/scene`, {
    headers: buildHeaders(),
    signal,
  });
  return parseOrThrow<any>(res);
}
