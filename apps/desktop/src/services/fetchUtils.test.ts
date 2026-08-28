import { describe, it, expect } from "vitest";

import { ApiError, isAuthFailure, parseOrThrow } from "./fetchUtils";

/**
 * The backend's own 401 body, copied verbatim from
 * `services/backend/core/security.py::verify_api_token`.
 *
 * 🔴 This exact string is why these tests exist. It contains no status code and none of the words
 * the previous check looked for, so an installed build showed the generic failure message where a
 * specific one had been written for it.
 */
const REJECTED_TOKEN_DETAIL = "Access Denied: Invalid security API Token.";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("parseOrThrow", () => {
  it("carries the HTTP status on the thrown error", async () => {
    await expect(
      parseOrThrow(jsonResponse(401, { detail: REJECTED_TOKEN_DETAIL }))
    ).rejects.toMatchObject({ status: 401, message: REJECTED_TOKEN_DETAIL });
  });

  it("still throws an Error carrying the backend's message", async () => {
    // Every existing caller does `err instanceof Error` or reads `.message`; ApiError must not
    // break either, which is the whole reason it subclasses Error rather than replacing it.
    const failure = parseOrThrow(jsonResponse(422, { detail: "name: field required" }));
    await expect(failure).rejects.toBeInstanceOf(Error);
    await expect(failure).rejects.toThrow("name: field required");
  });

  it("unwraps a success envelope", async () => {
    const data = await parseOrThrow(jsonResponse(200, { success: true, data: { id: "r1" } }));
    expect(data).toEqual({ id: "r1" });
  });
});

describe("isAuthFailure", () => {
  it("recognises a rejected token from the status, not from the prose", () => {
    // The assertion that would have caught the shipped defect: the message alone says nothing.
    expect(isAuthFailure(new ApiError(REJECTED_TOKEN_DETAIL, 401))).toBe(true);
    expect(/\b40[13]\b|unauthor|forbidden/i.test(REJECTED_TOKEN_DETAIL)).toBe(false);
  });

  it("recognises a forbidden response", () => {
    expect(isAuthFailure(new ApiError("Access Denied: Insufficient workspace permissions.", 403))).toBe(true);
  });

  it("does not treat other failures as auth failures", () => {
    expect(isAuthFailure(new ApiError("name: field required", 422))).toBe(false);
    expect(isAuthFailure(new ApiError("Internal Server Error", 500))).toBe(false);
    expect(isAuthFailure(new Error("Failed to fetch"))).toBe(false);
  });

  it("falls back to the message when there is no status to read", () => {
    // Errors raised before a response exists, or by a path that does not use parseOrThrow.
    expect(isAuthFailure(new Error("HTTP 401 from the sidecar"))).toBe(true);
    expect(isAuthFailure("Unauthorized")).toBe(true);
    expect(isAuthFailure(new Error(REJECTED_TOKEN_DETAIL))).toBe(true);
  });
});
