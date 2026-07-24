/**
 * annotationsApi.ts — Network layer for review annotations/pins (SRP: no React, no cache)
 */

import { buildHeaders, baseUrl, parseOrThrow } from "./fetchUtils";
import type { AnnotationItem, AnnotationSeverity, AnnotationPenType } from "../stores/workspace/types";

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
  const res = await fetch(`${baseUrl()}/api/v1/annotations?drawing_id=${encodeURIComponent(drawingId)}`, {
    headers: buildHeaders(),
    signal,
  });
  return parseOrThrow<AnnotationItem[]>(res);
}

/** POST /api/v1/annotations — create a pin. author_id is derived server-side. */
export async function createAnnotation(payload: CreateAnnotationPayload): Promise<AnnotationItem> {
  const res = await fetch(`${baseUrl()}/api/v1/annotations`, {
    method: "POST",
    headers: buildHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(payload),
  });
  return parseOrThrow<AnnotationItem>(res);
}

/** PATCH /api/v1/annotations/:id — partial update (content, status, etc.). */
export async function updateAnnotation(id: string, payload: Partial<UpdateAnnotationPayload>): Promise<AnnotationItem> {
  const res = await fetch(`${baseUrl()}/api/v1/annotations/${id}`, {
    method: "PATCH",
    headers: buildHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(payload),
  });
  return parseOrThrow<AnnotationItem>(res);
}

/** DELETE /api/v1/annotations/:id */
export async function deleteAnnotation(id: string): Promise<void> {
  const res = await fetch(`${baseUrl()}/api/v1/annotations/${id}`, {
    method: "DELETE",
    headers: buildHeaders(),
  });
  await parseOrThrow<{ deleted: boolean }>(res);
}
