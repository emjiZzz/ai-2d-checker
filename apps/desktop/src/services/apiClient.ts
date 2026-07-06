/**
 * Centralized API Client for AI-2D-Checker.
 *
 * Single source of truth for all HTTP communication with the FastAPI backend.
 * Handles auth token injection, session token forwarding, error normalization,
 * and typed response unwrapping so callers never touch raw fetch().
 *
 * Usage:
 *   import { apiClient } from "../services/apiClient";
 *   const drawing = await apiClient.get<Drawing>("/api/v1/drawings/123");
 */

import { useConnectionStore } from "../stores/connectionStore";
import { useAuthStore } from "../stores/authStore";

// ─── Response shapes mirroring the backend StandardResponse[T] ───────────────

export interface ApiSuccess<T> {
  ok: true;
  data: T;
  status: number;
}

export interface ApiError {
  ok: false;
  message: string;
  code?: string;
  status: number;
}

export type ApiResult<T> = ApiSuccess<T> | ApiError;

// ─── Internal helpers ────────────────────────────────────────────────────────

function buildHeaders(extra: Record<string, string> = {}): Record<string, string> {
  const { apiToken } = useConnectionStore.getState();
  const { sessionToken } = useAuthStore.getState();

  const headers: Record<string, string> = {
    Accept: "application/json",
    ...extra,
  };

  if (apiToken) {
    headers["Authorization"] = `Bearer ${apiToken}`;
  }
  if (sessionToken) {
    headers["X-Session-Token"] = sessionToken;
  }

  return headers;
}

function baseUrl(): string {
  return useConnectionStore.getState().backendUrl;
}

async function parseResponse<T>(res: Response): Promise<ApiResult<T>> {
  let body: any;
  try {
    body = await res.json();
  } catch {
    return { ok: false, message: `HTTP ${res.status}: non-JSON response`, status: res.status };
  }

  if (!res.ok) {
    const message =
      body?.detail ||
      body?.error?.message ||
      body?.message ||
      `Request failed with status ${res.status}`;
    const code = body?.error?.code;
    return { ok: false, message, code, status: res.status };
  }

  // Backend wraps success in { success: true, data: T }
  if (body?.success === true) {
    return { ok: true, data: body.data as T, status: res.status };
  }

  // Some endpoints return unwrapped JSON (e.g. raw health endpoint)
  return { ok: true, data: body as T, status: res.status };
}

// ─── Timeout wrapper ─────────────────────────────────────────────────────────

function withTimeout(ms: number): AbortController {
  const controller = new AbortController();
  setTimeout(() => controller.abort(), ms);
  return controller;
}

// ─── Core request methods ────────────────────────────────────────────────────

async function get<T>(
  path: string,
  timeoutMs = 10_000
): Promise<ApiResult<T>> {
  const controller = withTimeout(timeoutMs);
  try {
    const res = await fetch(`${baseUrl()}${path}`, {
      method: "GET",
      headers: buildHeaders(),
      signal: controller.signal,
    });
    return parseResponse<T>(res);
  } catch (err: any) {
    const message =
      err?.name === "AbortError"
        ? "Request timed out."
        : err?.message || "Network error.";
    return { ok: false, message, status: 0 };
  }
}

async function post<T>(
  path: string,
  body?: unknown,
  timeoutMs = 15_000
): Promise<ApiResult<T>> {
  const controller = withTimeout(timeoutMs);
  try {
    const res = await fetch(`${baseUrl()}${path}`, {
      method: "POST",
      headers: buildHeaders({ "Content-Type": "application/json" }),
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });
    return parseResponse<T>(res);
  } catch (err: any) {
    const message =
      err?.name === "AbortError" ? "Request timed out." : err?.message || "Network error.";
    return { ok: false, message, status: 0 };
  }
}

async function patch<T>(
  path: string,
  body?: unknown,
  timeoutMs = 10_000
): Promise<ApiResult<T>> {
  const controller = withTimeout(timeoutMs);
  try {
    const params =
      body && typeof body === "object" && !Array.isArray(body)
        ? new URLSearchParams(
            Object.fromEntries(
              Object.entries(body as Record<string, string>).filter(([, v]) => v !== undefined && v !== "")
            )
          ).toString()
        : "";

    // PATCH with query params for endpoints that use them (e.g. /standards/:id)
    const url = params ? `${baseUrl()}${path}?${params}` : `${baseUrl()}${path}`;
    const res = await fetch(url, {
      method: "PATCH",
      headers: buildHeaders({ "Content-Type": "application/json" }),
      body: body && !params ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });
    return parseResponse<T>(res);
  } catch (err: any) {
    const message =
      err?.name === "AbortError" ? "Request timed out." : err?.message || "Network error.";
    return { ok: false, message, status: 0 };
  }
}

async function del<T>(path: string, timeoutMs = 10_000): Promise<ApiResult<T>> {
  const controller = withTimeout(timeoutMs);
  try {
    const res = await fetch(`${baseUrl()}${path}`, {
      method: "DELETE",
      headers: buildHeaders(),
      signal: controller.signal,
    });
    return parseResponse<T>(res);
  } catch (err: any) {
    const message =
      err?.name === "AbortError" ? "Request timed out." : err?.message || "Network error.";
    return { ok: false, message, status: 0 };
  }
}

/**
 * Multipart file upload with XHR for upload progress tracking.
 * Returns ApiResult<T> with the same shape as other methods.
 */
function upload<T>(
  path: string,
  formData: FormData,
  onProgress?: (percent: number) => void
): Promise<ApiResult<T>> {
  const { apiToken } = useConnectionStore.getState();
  const { sessionToken } = useAuthStore.getState();

  return new Promise((resolve) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${baseUrl()}${path}`);

    if (apiToken) xhr.setRequestHeader("Authorization", `Bearer ${apiToken}`);
    if (sessionToken) xhr.setRequestHeader("X-Session-Token", sessionToken);
    xhr.setRequestHeader("Accept", "application/json");

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress(Math.round((e.loaded / e.total) * 90));
      }
    };

    xhr.onload = () => {
      let body: any;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        resolve({ ok: false, message: "Invalid JSON response from server.", status: xhr.status });
        return;
      }

      if (xhr.status >= 200 && xhr.status < 300 && body?.success) {
        resolve({ ok: true, data: body.data as T, status: xhr.status });
      } else {
        const message =
          body?.detail || body?.error?.message || `Upload failed with status ${xhr.status}`;
        resolve({ ok: false, message, status: xhr.status });
      }
    };

    xhr.onerror = () =>
      resolve({ ok: false, message: "Network error during upload.", status: 0 });

    xhr.send(formData);
  });
}

/**
 * Streaming POST — yields text chunks from a server-sent or chunked response.
 * Used for the AI Copilot streaming endpoint.
 */
async function* stream(
  path: string,
  body: unknown,
  timeoutMs = 60_000
): AsyncGenerator<string, void, unknown> {
  const controller = withTimeout(timeoutMs);
  const { apiToken } = useConnectionStore.getState();
  const { sessionToken } = useAuthStore.getState();

  const headers: Record<string, string> = {
    Accept: "text/event-stream",
    "Content-Type": "application/json",
  };
  if (apiToken) headers["Authorization"] = `Bearer ${apiToken}`;
  if (sessionToken) headers["X-Session-Token"] = sessionToken;

  let res: Response;
  try {
    res = await fetch(`${baseUrl()}${path}`, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
      signal: controller.signal,
    });
  } catch (err: any) {
    throw new Error(err?.message || "Stream connection failed.");
  }

  if (!res.ok || !res.body) {
    throw new Error(`Stream request failed: HTTP ${res.status}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      const chunk = decoder.decode(value, { stream: true });
      // SSE format: "data: <content>\n\n" — strip the prefix
      for (const line of chunk.split("\n")) {
        if (line.startsWith("data: ")) {
          const payload = line.slice(6).trim();
          if (payload && payload !== "[DONE]") {
            yield payload;
          }
        } else if (line.trim() && !line.startsWith(":")) {
          // Plain chunked response (non-SSE fallback)
          yield line.trim();
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}

// ─── Public API surface ───────────────────────────────────────────────────────

export const apiClient = { get, post, patch, delete: del, upload, stream };
