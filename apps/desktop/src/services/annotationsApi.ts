import { buildHeadersAsync, baseUrl, parseOrThrow } from "./fetchUtils";
import type { AnnotationItem, AnnotationSeverity, AnnotationPenType } from "../stores/workspace/types";
import { cadPointToPair, type CadPoint } from "../utils/coordinateTransform";

/**
 * Wire shape of an annotation. `coordinates` is a provenance-carrying envelope
 * (see services/backend/domain/models/cad_point.py); the canvas works in bare pairs, so
 * the envelope is unwrapped here at the boundary rather than threaded through the stores.
 */
interface AnnotationWire extends Omit<AnnotationItem, "coordinates"> {
  coordinates: CadPoint | null;
  coordinate_drift?: boolean;
}

/**
 * Unwrap the coordinate envelope, preserving the provenance the UI can act on.
 *
 * `coordinate_drift` is the backend's verdict that the drawing was re-rendered against
 * different bounds since this pin was placed, so its stored position no longer marks what
 * the user marked. Surfacing it is the point of the envelope — previously that situation
 * was silent and unrecoverable.
 */
function fromWire(wire: AnnotationWire): AnnotationItem {
  return {
    ...wire,
    coordinates: cadPointToPair(wire.coordinates),
    coordinate_space: wire.coordinates?.space ?? null,
    coordinate_drift: wire.coordinate_drift ?? false,
  };
}

export interface CreateAnnotationPayload {
  review_session_id: string;
  drawing_id: string;
  content: string;
  coordinates?: [number, number] | null;
  annotation_type?: string;
  severity?: AnnotationSeverity;
  target_entity_ids?: string[];
  violation_id?: string | null;
  pen_type?: AnnotationPenType;
}

export interface UpdateAnnotationPayload {
  content?: string;
  status?: string;
  severity?: AnnotationSeverity;
  coordinates?: [number, number] | null;
  pen_type?: AnnotationPenType;
}

/** GET /api/v1/annotations?drawing_id= — annotations pinned to a drawing. */
export async function fetchAnnotations(drawingId: string, signal?: AbortSignal): Promise<AnnotationItem[]> {
  const headers = await buildHeadersAsync();
  const res = await fetch(`${baseUrl()}/api/v1/annotations?drawing_id=${encodeURIComponent(drawingId)}`, {
    headers,
    signal,
  });
  const items = await parseOrThrow<AnnotationWire[]>(res);
  return items.map(fromWire);
}

/** POST /api/v1/annotations — create a pin. author_id is derived server-side. */
export async function createAnnotation(payload: CreateAnnotationPayload): Promise<AnnotationItem> {
  const headers = await buildHeadersAsync({ "Content-Type": "application/json" });
  const res = await fetch(`${baseUrl()}/api/v1/annotations`, {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
  });
  return fromWire(await parseOrThrow<AnnotationWire>(res));
}

/** PATCH /api/v1/annotations/:id — partial update (content, status, etc.). */
export async function updateAnnotation(id: string, payload: Partial<UpdateAnnotationPayload>): Promise<AnnotationItem> {
  const headers = await buildHeadersAsync({ "Content-Type": "application/json" });
  const res = await fetch(`${baseUrl()}/api/v1/annotations/${id}`, {
    method: "PATCH",
    headers,
    body: JSON.stringify(payload),
  });
  return fromWire(await parseOrThrow<AnnotationWire>(res));
}

/** DELETE /api/v1/annotations/:id */
export async function deleteAnnotation(id: string): Promise<void> {
  const headers = await buildHeadersAsync();
  const res = await fetch(`${baseUrl()}/api/v1/annotations/${id}`, {
    method: "DELETE",
    headers,
  });
  await parseOrThrow<{ deleted: boolean }>(res);
}
