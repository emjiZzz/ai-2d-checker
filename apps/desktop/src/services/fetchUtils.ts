/**
 * fetchUtils.ts — Shared low-level fetch helpers for all API layers
 *
 * Previously, buildHeaders(), baseUrl(), and parseOrThrow() were copy-pasted
 * into roomsApi.ts, standardsApi.ts, and adminApi.ts. Any change to auth
 * headers (e.g. adding a new token type) would require editing 3+ files.
 *
 * This module is the single source of truth for those helpers. API layers
 * import from here and stay focused exclusively on their own endpoint logic.
 *
 * Intentionally NOT exported through the barrel index — it is an internal
 * utility, not part of the public service API surface.
 */

import { useConnectionStore } from "../stores/connectionStore";
import { useAuthStore } from "../stores/authStore";
import { ZodType } from "zod";

/**
 * Builds authenticated request headers from the current Zustand store state.
 * Called outside React (no hooks), so we use .getState() directly.
 *
 * @param extra - Optional additional headers to merge in (e.g. Content-Type).
 */
export function buildHeaders(extra: Record<string, string> = {}): Record<string, string> {
  const apiToken = useConnectionStore.getState().apiToken;
  const sessionToken = useAuthStore.getState().sessionToken;

  const headers: Record<string, string> = {
    Accept: "application/json",
    "Cache-Control": "no-store, no-cache, must-revalidate",
    Pragma: "no-cache",
    ...extra,
  };

  if (apiToken) headers["Authorization"] = `Bearer ${apiToken}`;
  if (sessionToken) headers["X-Session-Token"] = sessionToken;

  return headers;
}

/** Returns the current backend base URL from connection store state. */
export function baseUrl(): string {
  return useConnectionStore.getState().backendUrl;
}

/**
 * Parses a fetch Response into a typed result or throws a normalised Error.
 *
 * Throws instead of returning { ok: false } so TanStack Query's built-in
 * retry/error-state machinery activates automatically on failure.
 *
 * Handles both:
 *   - Wrapped responses:   { success: true, data: T }
 *   - Unwrapped responses: raw JSON (some endpoints return this)
 */
export async function parseOrThrow<T>(res: Response): Promise<T> {
  let body: unknown;
  try {
    body = await res.json();
  } catch {
    throw new Error(`HTTP ${res.status}: non-JSON body`);
  }

  if (!res.ok) {
    const b = body as Record<string, unknown>;
    let message = "HTTP request failed";
    if (typeof b?.detail === "string") {
      message = b.detail;
    } else if (Array.isArray(b?.detail)) {
      message = b.detail.map((err: any) => err.msg ? `${err.loc?.slice(1)?.join(".") || "field"}: ${err.msg}` : JSON.stringify(err)).join("; ");
    } else if (typeof b?.message === "string") {
      message = b.message;
    } else if (b?.detail) {
      message = JSON.stringify(b.detail);
    } else {
      message = `HTTP ${res.status}`;
    }
    throw new Error(message);
  }

  let payload = body;

  // Backend wraps success in { success: true, data: T }
  if (body && typeof body === "object" && "success" in body) {
    if ((body as any).success === true) {
      payload = (body as any).data;
    }
  }

  if (typeof payload === "object" && payload !== null && "error" in payload) {
    const apiError = payload as { error: any };
    throw new Error(apiError.error?.message || "Unknown error inside 2xx envelope");
  }

  return payload as T;
}

/**
 * Extends parseOrThrow to add runtime Zod validation of the payload.
 * Useful to catch backend contract changes gracefully at the network boundary.
 */
export async function parseAndValidate<T>(res: Response, schema: ZodType<T>): Promise<T> {
  const data = await parseOrThrow<unknown>(res);
  try {
    return schema.parse(data);
  } catch (err: any) {
    console.error("Zod Validation Error:", err);
    throw new Error(`API payload validation failed: ${err.message}`);
  }
}

/**
 * Multipart file upload with XHR for upload progress tracking.
 * Throws an Error on failure to match parseOrThrow semantics.
 */
export function uploadFile<T>(
  path: string,
  formData: FormData,
  onProgress?: (percent: number) => void
): Promise<T> {
  const { apiToken } = useConnectionStore.getState();
  const { sessionToken } = useAuthStore.getState();

  return new Promise((resolve, reject) => {
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
        return reject(new Error(`HTTP ${xhr.status}: non-JSON body`));
      }

      if (xhr.status >= 200 && xhr.status < 300) {
        // Handle wrapped responses
        if (body && typeof body === "object" && "success" in body) {
          if (body.success) return resolve(body.data as T);
        }
        return resolve(body as T);
      } else {
        const message = body?.detail || body?.error?.message || body?.message || `Upload failed with status ${xhr.status}`;
        return reject(new Error(message));
      }
    };

    xhr.onerror = () => reject(new Error("Network error during upload."));
    xhr.send(formData);
  });
}

/**
 * Streaming POST — yields text chunks from a server-sent or chunked response.
 */
export async function* streamApi(
  path: string,
  body: unknown,
  timeoutMs = 60_000
): AsyncGenerator<string, void, unknown> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const res = await fetch(`${baseUrl()}${path}`, {
      method: "POST",
      headers: buildHeaders({ 
        "Accept": "text/event-stream",
        "Content-Type": "application/json" 
      }),
      body: JSON.stringify(body),
      signal: controller.signal,
    });

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
        
        for (const line of chunk.split("\n")) {
          if (line.startsWith("data: ")) {
            const payload = line.slice(6).trim();
            if (payload && payload !== "[DONE]") {
              yield payload;
            }
          } else if (line.trim() && !line.startsWith(":")) {
            yield line.trim();
          }
        }
      }
    } finally {
      reader.releaseLock();
    }
  } finally {
    clearTimeout(timeoutId);
  }
}

/**
 * A native fetch wrapper that automatically injects auth headers and baseUrl.
 * Does NOT throw on error and does NOT parse the response, giving full control to the caller.
 * Use this when you need blob responses or specific status code handling (like 204).
 */
export async function fetchWithAuth(endpoint: string, options: RequestInit = {}): Promise<Response> {
  const url = endpoint.startsWith("http") ? endpoint : `${baseUrl()}${endpoint}`;
  return fetch(url, {
    ...options,
    headers: buildHeaders(options.headers as Record<string, string>),
  });
}
