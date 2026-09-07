/**
 * Coordinate envelope shared between the backend persistence layer and the desktop app.
 *
 * Mirrors `services/backend/domain/models/cad_point.py`. Keep the two in step.
 *
 * A persisted coordinate used to be a bare `[x, y]` with no record of the space it was
 * measured in or the render bounds it was authored against. That made drift silent: if a
 * drawing was re-rendered and a different paper-space layout became the render target,
 * every stored pin moved and nothing recorded it.
 */

/**
 * Where a coordinate's numbers are measured.
 *
 *  - `model`  — the source CAD file's own model space.
 *  - `paper`  — a paper-space layout: model geometry already projected through a VIEWPORT.
 *  - `render` — the renderer's output space, when no CAD transform describes it. PDF
 *               ingestion measures against the PyMuPDF page rect (top-left origin).
 *               Also the honest default for a point whose space was never qualified.
 */
export type CoordinateSpace = "model" | "paper" | "render";

/** A 2D coordinate plus the provenance needed to interpret it later. */
export interface CadPoint {
  x: number;
  y: number;
  space: CoordinateSpace;
  /** Paper-space layout name this point was authored against, if any. */
  layout: string | null;
  /** Index into the drawing's viewport transform; -1 for identity/no viewport. */
  viewport_index: number;
  /** Version of the viewport transform maths in force when this point was stamped. */
  transform_version: number;
  /** Snapshot of `render_bounds` [xmin, ymin, xmax, ymax] at authoring time. */
  bounds: number[] | null;
}

/** Extract the bare `[x, y]` the canvas works in. */
export function cadPointToPair(point: CadPoint | null | undefined): [number, number] | null {
  if (!point || typeof point.x !== "number" || typeof point.y !== "number") return null;
  return [point.x, point.y];
}
