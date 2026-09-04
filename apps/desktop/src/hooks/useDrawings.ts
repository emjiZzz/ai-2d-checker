/**
 * useDrawings.ts — TanStack Query data layer for Drawings
 *
 * Covers: drawings list query.
 */

import { useQuery, type QueryFunctionContext } from "@tanstack/react-query";
import { fetchDrawings } from "../services/drawingsApi";
import { drawingKeys } from "../services/queryKeys";
import type { DrawingItem } from "../stores/workspaceStore";

// ─── Sub-hook: List query ─────────────────────────────────────────────────────

/**
 * Fetches and caches the full drawings list.
 */
export function useDrawingsList() {
  return useQuery<DrawingItem[], Error>({
    queryKey: drawingKeys.list(),
    queryFn: ({ signal }: QueryFunctionContext) => fetchDrawings(signal),
  });
}
