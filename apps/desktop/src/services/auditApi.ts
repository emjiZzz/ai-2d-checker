import { buildHeaders, baseUrl, parseOrThrow } from "./fetchUtils";

/** GET /api/v1/audits/sessions/:sessionId */
export async function fetchAuditSession(sessionId: string, signal?: AbortSignal): Promise<any> {
  const res = await fetch(`${baseUrl()}/api/v1/audits/sessions/${sessionId}`, {
    headers: buildHeaders(),
    signal,
  });
  return parseOrThrow<any>(res);
}
