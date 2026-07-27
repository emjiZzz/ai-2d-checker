/**
 * reportsApi.ts — API calls for exporting audit reports and CAD redline DXF files.
 */

import { fetchWithAuth } from "./fetchUtils";

/**
 * Downloads a redlined copy of the source DXF drawing for an audit session.
 *
 * The backend opens the original DXF file, injects findings as revision clouds,
 * leaders, and MTEXT on an `AI_REDLINE_<session_id>` layer, and returns the result.
 *
 * @param sessionId - The audit session ID to export redlines for.
 * @param filename - Optional custom filename for the downloaded file.
 */
export async function downloadRedlineDxf(sessionId: string, filename?: string): Promise<void> {
  const res = await fetchWithAuth(`/api/v1/reports/${sessionId}/redline.dxf`, {
    headers: { Accept: "application/dxf, application/octet-stream" },
  });

  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try {
      const err = await res.json();
      msg = err.detail || err.message || msg;
    } catch {
      // non-JSON response body
    }
    throw new Error(`Redline export failed: ${msg}`);
  }

  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename || `redline_${sessionId}.dxf`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
