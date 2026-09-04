/**
 * itemsApi.ts — Pure API Layer (Network I/O Only)
 *
 * Single Responsibility: this file knows nothing about React, TanStack Query,
 * or component state. It is exclusively responsible for translating domain
 * intent into HTTP calls and normalising raw responses into typed results.
 *
 * Keeping this layer separate from the query/mutation definitions means:
 *  - It is independently unit-testable (mock fetch, not the whole hook).
 *  - Query keys and cache logic live in one place; network logic lives here.
 *  - Swapping transport (fetch → axios) never touches the hook layer.
 */

import { useConnectionStore } from "../stores/connectionStore";
import { useAuthStore } from "../stores/authStore";

// ─── Domain Types ─────────────────────────────────────────────────────────────

/** The canonical shape of a single managed item returned by the API. */
export interface Item {
  id: string;
  name: string;
  description: string;
  /** Whether this feature/item is currently active. */
  status: "active" | "inactive" | "archived";
  /** ISO-8601 timestamp of the last server-side modification. */
  updatedAt: string;
  /** Arbitrary key-value metadata (extensible without schema migrations). */
  metadata: Record<string, unknown>;
}

/** The shape of the paginated list response from GET /api/v1/items. */
export interface ItemsPage {
  items: Item[];
  total: number;
  page: number;
  pageSize: number;
}

/** Parameters accepted by the status-toggle mutation endpoint. */
export interface UpdateItemStatusParams {
  itemId: string;
  status: Item["status"];
}

/** Parameters accepted by the add-item mutation endpoint. */
export interface AddItemParams {
  name: string;
  description: string;
  metadata?: Record<string, unknown>;
}

// ─── Internal request builder ─────────────────────────────────────────────────

/**
 * Builds a fully authenticated fetch Request object.
 *
 * We read auth tokens from Zustand outside of React (`.getState()`) so this
 * function can be called from a plain async function — not just a hook.
 */
function buildRequest(path: string, init: RequestInit = {}): Request {
  const backendUrl = useConnectionStore.getState().backendUrl;
  const apiToken = useConnectionStore.getState().apiToken;
  const sessionToken = useAuthStore.getState().sessionToken;

  const headers: Record<string, string> = {
    Accept: "application/json",
    "Content-Type": "application/json",
    ...(init.headers as Record<string, string> | undefined),
  };

  if (apiToken) headers["Authorization"] = `Bearer ${apiToken}`;
  if (sessionToken) headers["X-Session-Token"] = sessionToken;

  // Spread init but omit headers — we replace them above after merging
  const { headers: _ignored, ...restInit } = init;
  return new Request(`${backendUrl}${path}`, { ...restInit, headers });
}

/**
 * Parses a Response into a typed result or throws a normalised Error.
 *
 * Throwing (rather than returning { ok: false }) lets TanStack Query's
 * built-in retry / error state machinery handle failures automatically.
 * Components simply read `query.error` — no manual error-propagation needed.
 */
async function parseOrThrow<T>(res: Response): Promise<T> {
  let body: unknown;

  try {
    body = await res.json();
  } catch {
    throw new Error(`HTTP ${res.status}: non-JSON body`);
  }

  if (!res.ok) {
    const b = body as Record<string, unknown>;
    const message =
      (b?.detail as string) ??
      (b?.message as string) ??
      `Request failed: HTTP ${res.status}`;
    throw new Error(message);
  }

  // Backend wraps successes in { success: true, data: T }
  const b = body as Record<string, unknown>;
  if (b?.success === true) return b.data as T;

  // Fallback for endpoints that return unwrapped JSON
  return body as T;
}

// ─── Public API functions ─────────────────────────────────────────────────────

/**
 * Fetches a paginated list of items.
 *
 * @param page    - 1-indexed page number.
 * @param signal  - AbortSignal forwarded from TanStack Query's queryFn context.
 *
 * WHY signal matters here: when the user navigates away or a newer query fires
 * (e.g. page flip), TanStack Query aborts the stale signal. Because we pass it
 * straight to fetch(), the browser terminates the underlying TCP connection
 * rather than just ignoring the response — saving bandwidth and preventing
 * a stale response from racing with fresh data in the cache.
 */
export async function fetchItems(page: number, signal: AbortSignal): Promise<ItemsPage> {
  const req = buildRequest(`/api/v1/items?page=${page}&pageSize=20`);
  const res = await fetch(req, { signal });
  return parseOrThrow<ItemsPage>(res);
}

/**
 * Fetches a single item by ID.
 *
 * @param signal - AbortSignal from TanStack Query for race protection.
 */
export async function fetchItemById(itemId: string, signal: AbortSignal): Promise<Item> {
  const req = buildRequest(`/api/v1/items/${itemId}`);
  const res = await fetch(req, { signal });
  return parseOrThrow<Item>(res);
}

/**
 * Sends a PATCH to toggle an item's status.
 *
 * No AbortSignal on mutations: aborting a PATCH mid-flight can leave the
 * server in an inconsistent state. Mutation cancellation is handled by the
 * optimistic-update rollback in onError, not by network abortion.
 */
export async function patchItemStatus(params: UpdateItemStatusParams): Promise<Item> {
  const req = buildRequest(`/api/v1/items/${params.itemId}/status`, {
    method: "PATCH",
    body: JSON.stringify({ status: params.status }),
  });
  const res = await fetch(req);
  return parseOrThrow<Item>(res);
}

/**
 * Creates a new item via POST.
 *
 * Returns the server-generated Item (with its canonical ID and updatedAt).
 */
export async function postItem(params: AddItemParams): Promise<Item> {
  const req = buildRequest("/api/v1/items", {
    method: "POST",
    body: JSON.stringify(params),
  });
  const res = await fetch(req);
  return parseOrThrow<Item>(res);
}
