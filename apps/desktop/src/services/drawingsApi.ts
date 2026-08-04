/**
 * drawingsApi.ts — Network layer for Drawings (SRP: no React, no cache)
 *
 * Covers read operations for drawings. Uploads are handled via XHR in
 * createUploadSlice.ts because they need progress callbacks.
 */

import { buildHeaders, baseUrl, parseOrThrow } from "./fetchUtils";
import type { DrawingItem } from "../stores/workspaceStore";

// ─── Types ────────────────────────────────────────────────────────────────────

/**
 * Mirrors `services/backend/api/schemas.py::ZoneBBox`. Hand-mirrored rather than
 * imported — apps/desktop has no cross-language type sharing (same precedent as
 * comparisonStages.ts and coordinateTransform.ts). Keep both in step.
 */
export interface ZoneBBox {
  xmin: number;
  ymin: number;
  xmax: number;
  ymax: number;
  /**
   * How the backend resolved this box. Not a two-state flag — the third value is the
   * one that matters:
   *  - "content_aware": semantic anchor found, box flood-filled around it. A measurement.
   *  - "percentage_fallback": no anchor; percentage grid over real sheet bounds. A guess,
   *    but a guess about *this* drawing — worth drawing, marked dashed.
   *  - "percentage_fallback_no_sheet_bounds": bounds detection failed entirely; every zone
   *    is the literal (0,0,1000,1000) placeholder describing no drawing at all. Must NOT
   *    be drawn — see isPlaceholderOnly() below.
   */
  confidence: string;
}

/** Mirrors `services/backend/api/schemas.py::DrawingZonesResponse`. */
export interface DrawingZonesResponse {
  drawing_id: string;
  /** Flat [xmin, ymin, xmax, ymax] the boxes were computed against. */
  render_bounds: number[] | null;
  views: ZoneBBox | null;
  notes: ZoneBBox | null;
  bom: ZoneBBox | null;
  title: ZoneBBox | null;
  tolerance: ZoneBBox | null;
  iso: ZoneBBox | null;
  title_upper_left: ZoneBBox | null;
  shim: ZoneBBox | null;
}

/** The zone keys, in the order they should render. Mirrors backend ZONE_KEYS. `shim` is
 *  optional (only present on sheets with a シム表 table) but always listed so the editor can
 *  offer it; it simply renders no box when the drawing has none. */
export const ZONE_KEYS = [
  "views",
  "notes",
  "bom",
  "title",
  "tolerance",
  "iso",
  "title_upper_left",
  "shim",
] as const;

export type ZoneKey = (typeof ZONE_KEYS)[number];

export const NO_SHEET_BOUNDS = "percentage_fallback_no_sheet_bounds";

/**
 * Zone colors for React chrome (the zone picker). Kept in step with ZONE_COLORS in
 * renderEntities.ts, which is the canvas-side copy — the canvas draws with the 2D context
 * and cannot read Tailwind classes, so the values live in both places by necessity.
 */
export const ZONE_UI_COLORS: Record<string, string> = {
  views: "#38bdf8",
  notes: "#fb7185",
  bom: "#34d399",
  title: "#818cf8",
  tolerance: "#fbbf24",
  iso: "#c084fc",
  title_upper_left: "#2dd4bf",
  shim: "#f472b6",
};

/** Compact labels for the zone picker chips; the canvas badges use longer names. */
export const ZONE_SHORT_LABELS: Record<string, string> = {
  views: "Views",
  notes: "Notes",
  bom: "BOM",
  title: "Title",
  tolerance: "Tolerance",
  iso: "ISO",
  title_upper_left: "Title UL",
  shim: "Shim",
};

/**
 * True when zone detection had no sheet bounds and every box is the (0,0,1000,1000)
 * placeholder. Callers must render nothing in this case: seven identical rectangles
 * near the origin read as a broken overlay rather than as failed bounds detection,
 * which is the opposite of what a debugging tool should communicate.
 */
export function isPlaceholderOnly(zones: DrawingZonesResponse | null | undefined): boolean {
  if (!zones) return false;
  return ZONE_KEYS.some((key) => zones[key]?.confidence === NO_SHEET_BOUNDS);
}

/** Count of zones that fell back to the percentage grid — surfaced in the header notice. */
export function countFallbackZones(zones: DrawingZonesResponse | null | undefined): number {
  if (!zones) return 0;
  return ZONE_KEYS.filter((key) => {
    const c = zones[key]?.confidence;
    return c !== undefined && c !== "content_aware";
  }).length;
}

// ─── Public API ───────────────────────────────────────────────────────────────

/** GET /api/v1/drawings — fetches all available drawings. */
export async function fetchDrawings(signal?: AbortSignal): Promise<DrawingItem[]> {
  const res = await fetch(`${baseUrl()}/api/v1/drawings`, {
    headers: buildHeaders(),
    signal,
  });
  return parseOrThrow<DrawingItem[]>(res);
}

/** GET /api/v1/drawings/:id — fetches a single drawing's metadata. */
export async function fetchDrawing(id: string, signal?: AbortSignal): Promise<DrawingItem> {
  const res = await fetch(`${baseUrl()}/api/v1/drawings/${id}`, {
    headers: buildHeaders(),
    signal,
  });
  return parseOrThrow<DrawingItem>(res);
}

/**
 * DELETE /api/v1/drawings/:id — hard-deletes a drawing and every artifact it owns
 * (entities, jobs, files, caches). Used by the room-owned upload flow to purge the
 * drawing a slot previously held when it is replaced by a fresh upload.
 */
export async function deleteDrawing(id: string): Promise<void> {
  const res = await fetch(`${baseUrl()}/api/v1/drawings/${id}`, {
    method: "DELETE",
    headers: buildHeaders(),
  });
  await parseOrThrow<{ deleted_id: string }>(res);
}

/** GET /api/v1/drawings/:id/scene — fetches vector scene primitives and CAD handles. */
export async function fetchDrawingScene(id: string, signal?: AbortSignal): Promise<any> {
  const res = await fetch(`${baseUrl()}/api/v1/drawings/${id}/scene`, {
    headers: buildHeaders(),
    signal,
  });
  return parseOrThrow<any>(res);
}

/**
 * GET /api/v1/drawings/:id/zones — template-zone boxes for the canvas debug overlay.
 *
 * Independent of any comparison run: zone detection needs one drawing's entities and no
 * AI call. Throws with the backend's message on ENTITIES_NOT_READY (entities not yet
 * extracted), which callers surface as a notice rather than swallowing.
 */
export async function fetchDrawingZones(
  id: string,
  signal?: AbortSignal,
): Promise<DrawingZonesResponse> {
  const res = await fetch(`${baseUrl()}/api/v1/drawings/${id}/zones`, {
    headers: buildHeaders(),
    signal,
  });
  return parseOrThrow<DrawingZonesResponse>(res);
}

// ─── Zone templates ───────────────────────────────────────────────────────────

/** Mirrors `services/backend/domain/models/zone_template.py::ZoneFractions` (Y-DOWN). */
export interface ZoneTemplateFractions {
  xMin: number;
  xMax: number;
  yMin: number;
  yMax: number;
}

export interface ZoneTemplate {
  signature: string;
  name: string;
  zones: Record<string, ZoneTemplateFractions>;
  /** True on the single template used as the global fallback for sheets with no signature match. */
  is_default: boolean;
  updated_by: string | null;
  updated_at: string | null;
}

/**
 * Sheet-template identity. Mirrors `zone_template.py::zone_signature` — keep in step.
 *
 * Bucketed aspect ratio. Every A-series sheet is 1.414, so two different layouts on
 * A-series paper share one template; that is a known limitation, not an oversight. Never
 * present matching aspect ratio to the user as proof of matching layout.
 */
export function zoneSignature(renderBounds: number[] | null | undefined): string | null {
  if (!renderBounds || renderBounds.length !== 4) return null;
  const [x0, y0, x1, y1] = renderBounds;
  const w = x1 - x0;
  const h = y1 - y0;
  if (!(w > 0) || !(h > 0)) return null;
  return `aspect-${(Math.round((w / h) * 1000) / 1000).toFixed(3)}`;
}

/** GET /api/v1/zone-templates/:signature — resolves to null when nothing is aligned yet. */
export async function fetchZoneTemplate(
  signature: string,
  signal?: AbortSignal,
): Promise<ZoneTemplate | null> {
  const res = await fetch(`${baseUrl()}/api/v1/zone-templates/${signature}`, {
    headers: buildHeaders(),
    signal,
  });
  return parseOrThrow<ZoneTemplate | null>(res);
}

/** PUT /api/v1/zone-templates/:signature — `zones` replaces the stored set wholesale. */
export async function saveZoneTemplate(
  signature: string,
  payload: { name?: string; zones: Record<string, ZoneTemplateFractions>; updated_by?: string },
): Promise<ZoneTemplate> {
  const res = await fetch(`${baseUrl()}/api/v1/zone-templates/${signature}`, {
    method: "PUT",
    headers: buildHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(payload),
  });
  return parseOrThrow<ZoneTemplate>(res);
}

/** GET /api/v1/zone-templates — fetch all saved templates. */
export async function fetchAllZoneTemplates(
  signal?: AbortSignal,
): Promise<ZoneTemplate[]> {
  const res = await fetch(`${baseUrl()}/api/v1/zone-templates`, {
    headers: buildHeaders(),
    signal,
  });
  const data = await parseOrThrow<ZoneTemplate[]>(res);
  return data || [];
}

/** DELETE /api/v1/zone-templates/:signature — delete a saved template. */
export async function deleteZoneTemplate(
  signature: string,
): Promise<boolean> {
  const res = await fetch(`${baseUrl()}/api/v1/zone-templates/${signature}`, {
    method: "DELETE",
    headers: buildHeaders(),
  });
  return parseOrThrow<boolean>(res);
}

/** GET /api/v1/zone-templates-default — the global fallback template, or null if none is set. */
export async function fetchDefaultZoneTemplate(
  signal?: AbortSignal,
): Promise<ZoneTemplate | null> {
  const res = await fetch(`${baseUrl()}/api/v1/zone-templates-default`, {
    headers: buildHeaders(),
    signal,
  });
  return parseOrThrow<ZoneTemplate | null>(res);
}

/**
 * PUT /api/v1/zone-templates/:signature/default — designate (or clear) the global default.
 * Setting one default clears any prior one (single-default invariant, enforced server-side).
 */
export async function setDefaultZoneTemplate(
  signature: string,
  isDefault: boolean,
): Promise<ZoneTemplate> {
  const res = await fetch(`${baseUrl()}/api/v1/zone-templates/${signature}/default`, {
    method: "PUT",
    headers: buildHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ is_default: isDefault }),
  });
  return parseOrThrow<ZoneTemplate>(res);
}

