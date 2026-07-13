/**
 * queryKeys.ts — Centralised Query Key Registry
 *
 * Why a dedicated file? TanStack Query uses query keys as both cache addresses
 * and invalidation selectors. Scattering string literals across the codebase
 * makes typos invisible and invalidation brittle. A single factory object gives
 * us one source of truth, TypeScript autocompletion, and trivial refactoring.
 *
 * Usage:
 *   useQuery({ queryKey: itemQueryKeys.list(page), queryFn: ... })
 *   queryClient.invalidateQueries({ queryKey: itemQueryKeys.lists() })
 */

export const itemQueryKeys = {
  all: ["items"] as const,
  lists: () => [...itemQueryKeys.all, "list"] as const,
  list: (page: number) => [...itemQueryKeys.lists(), { page }] as const,
  details: () => [...itemQueryKeys.all, "detail"] as const,
  detail: (itemId: string) => [...itemQueryKeys.details(), itemId] as const,
} as const;

// ─── Rooms ───────────────────────────────────────────────────────────────────

export const roomKeys = {
  /** Invalidating this nukes every room query (list + all details). */
  all: ["rooms"] as const,
  lists: () => [...roomKeys.all, "list"] as const,
  /** Key used by useQuery for the full rooms list. */
  list: () => [...roomKeys.lists()] as const,
  details: () => [...roomKeys.all, "detail"] as const,
  /** Key for a single room detail by ID. */
  detail: (roomId: string) => [...roomKeys.details(), roomId] as const,
} as const;

// ─── Standards ───────────────────────────────────────────────────────────────

export const standardKeys = {
  all: ["standards"] as const,
  lists: () => [...standardKeys.all, "list"] as const,
  list: () => [...standardKeys.lists()] as const,
  details: () => [...standardKeys.all, "detail"] as const,
  detail: (standardId: string) => [...standardKeys.details(), standardId] as const,
} as const;

// ─── Admin Users ─────────────────────────────────────────────────────────────

export const adminUserKeys = {
  all: ["admin", "users"] as const,
  lists: () => [...adminUserKeys.all, "list"] as const,
  list: () => [...adminUserKeys.lists()] as const,
  detail: (username: string) => [...adminUserKeys.all, "detail", username] as const,
} as const;

export const adminMetricsKeys = {
  all: ["admin", "metrics"] as const,
  database: () => [...adminMetricsKeys.all, "database"] as const,
  storage: () => [...adminMetricsKeys.all, "storage"] as const,
} as const;

// ─── Drawings ────────────────────────────────────────────────────────────────

export const drawingKeys = {
  all: ["drawings"] as const,
  lists: () => [...drawingKeys.all, "list"] as const,
  list: () => [...drawingKeys.lists()] as const,
  details: () => [...drawingKeys.all, "detail"] as const,
  detail: (drawingId: string) => [...drawingKeys.details(), drawingId] as const,
} as const;

// ─── Clients ──────────────────────────────────────────────────────────────────

export const clientKeys = {
  all: ["clients"] as const,
  lists: () => [...clientKeys.all, "list"] as const,
  list: () => [...clientKeys.lists()] as const,
} as const;

// ─── Polling Operations ───────────────────────────────────────────────────────

export const jobKeys = {
  all: ["jobs"] as const,
  detail: (jobId: string) => [...jobKeys.all, "detail", jobId] as const,
} as const;

export const auditKeys = {
  all: ["audits"] as const,
  sessions: () => [...auditKeys.all, "sessions"] as const,
  sessionDetail: (sessionId: string) => [...auditKeys.sessions(), "detail", sessionId] as const,
} as const;
