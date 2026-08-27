/**
 * The vector drawing page, rendered by the backend.
 *
 * ## Why this is not done in the browser
 *
 * The canvas can only hand jsPDF a bitmap. Page 1 of the compliance report has therefore always
 * been a 304 dpi PNG of the sheet — it prints acceptably and cannot be searched, copied, or
 * zoomed past its capture resolution. The backend has the DXF and ezdxf, so it can emit the same
 * sheet as real vector paths with an invisible, searchable text layer over them.
 *
 * ## The markers travel with the request
 *
 * The backend renders the geometry and the text; the MARKS come from here, because this is where
 * they are already resolved — filtered to what the canvas actually drew (retracted markings
 * excluded, engine markers suppressed in a manual-check room). Re-deriving them server-side would
 * be a second opinion about what the sheet shows, and the report exists to be evidence of the
 * review that happened.
 *
 * ⚠ Coordinates are CAD paper-space, **Y-up** — `rev_coordinates` / `coordinates` straight off the
 * store, the same values `renderManualMarkings` feeds to `worldToCanvas`. Not canvas pixels, and
 * not `render_bounds` fractions: those are Y-down, and a mirrored overlay looks plausible.
 * See `utils/zoneFractions.ts` for the only place that conversion belongs.
 */

import { baseUrl, buildHeadersAsync } from "./fetchUtils";

export interface VectorSheetMarker {
  x: number;
  y: number;
  /** A `MarkerType` from `markerStyles.ts`. Unknown values still paint, in the fallback ink. */
  status: string;
  label?: string;
}

export interface VectorSheetOptions {
  markers?: VectorSheetMarker[];
  pageWidthMm?: number;
  pageHeightMm?: number;
  marginMm?: number;
}

/**
 * One drawing as a single-page vector PDF.
 *
 * Throws on any non-2xx so the caller can decide what a failure means — this one has a visible
 * fallback and must not swallow the reason for taking it.
 */
export async function fetchVectorSheet(
  drawingId: string,
  options: VectorSheetOptions = {},
): Promise<Uint8Array> {
  const headers = await buildHeadersAsync({ "Content-Type": "application/json" });
  // Not `Accept: application/json`, which `buildHeadersAsync` sets by default — this response is
  // a PDF, and asking for JSON is how a working endpoint returns a 406.
  headers.Accept = "application/pdf";

  const response = await fetch(
    `${baseUrl()}/api/v1/export/drawings/${drawingId}/vector-sheet`,
    {
      method: "POST",
      headers,
      body: JSON.stringify({
        markers: options.markers ?? [],
        page_width_mm: options.pageWidthMm,
        page_height_mm: options.pageHeightMm,
        margin_mm: options.marginMm,
      }),
    },
  );

  if (!response.ok) {
    // The body is JSON on every error path the router raises, and its `detail` is the useful
    // half — "entities have not been extracted yet" is actionable, "500" is not.
    let detail = `${response.status}`;
    try {
      const body = await response.json();
      detail = body?.detail ?? body?.message ?? detail;
    } catch {
      /* a non-JSON error body is still worth reporting as its status */
    }
    throw new Error(`Vector sheet render failed: ${detail}`);
  }

  return new Uint8Array(await response.arrayBuffer());
}
