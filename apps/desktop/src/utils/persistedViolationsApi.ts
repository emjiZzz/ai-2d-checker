import { buildHeaders, baseUrl, parseOrThrow } from "../services/fetchUtils";
import type { PersistedViolation } from "./persistedViolations";

/**
 * Fetches the `AuditViolation` documents the backend persisted for a comparison session.
 *
 * Never throws. The checklist renders from `canvas_markings` and is fully usable without
 * this; all the call buys is the ability to *review* a finding. A failed fetch must therefore
 * degrade to "no verdict controls", exactly as it does for a MATCHED row — not to a broken
 * checklist. The alternative, letting it reject, would mean a transient network blip wipes the
 * comparison results a user just waited on.
 *
 * Returning `[]` on failure is safe precisely because `reconcilePersistedIds` treats an unmatched
 * marker as unreviewable rather than guessing an id.
 */
export async function fetchPersistedViolations(sessionId: string): Promise<PersistedViolation[]> {
  try {
    const res = await fetch(
      `${baseUrl()}/api/v1/audits/sessions/${sessionId}/violations`,
      { headers: buildHeaders() }
    );
    const data = await parseOrThrow<PersistedViolation[]>(res);
    return Array.isArray(data) ? data : [];
  } catch (err) {
    console.warn("[persistedViolations] Could not load persisted violations; verdict controls will be unavailable:", err);
    return [];
  }
}
