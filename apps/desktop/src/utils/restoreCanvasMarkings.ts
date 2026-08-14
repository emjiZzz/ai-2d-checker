/**
 * Rebuilds checklist markers from a room's stored `canvas_markings`.
 *
 * ## Why this is the render source, and persisted violations are not
 *
 * A comparison produces markings for **every** compared row. `orchestrator.py` then persists an
 * `AuditViolation` only for the non-MATCHED ones (`non_matched = [m for m in clean_markings if
 * m.get("status") != "MATCHED"]`), because a violation is a *finding* — there is nothing to
 * review about a row that matched.
 *
 * So the MATCHED rows — every green checkmark on the canvas — exist **only** in
 * `physical_comparison_results.canvas_markings` on the Room document. Restoring a room from its
 * audit session's violations alone brings back the findings and silently drops every checkmark,
 * which is exactly the bug this module was extracted to fix: results present, checkmarks gone.
 *
 * Persisted violations still matter, but only for *identity* — `reconcilePersistedIds` stamps
 * `persisted_id` onto the markers that have one, so a supervisor's verdict PATCHes a document
 * that exists. MATCHED markers never match and are simply not reviewable, by design.
 *
 * Previously inlined in `roomStore.openRoom`'s no-session branch, where it was unreachable for
 * any room that had an `active_audit_session_id` — i.e. every room a comparison had been run in.
 */

// Type-only: `roomStore.ts` imports this module, so an erased import keeps that edge acyclic.
import type { ViolationItem } from "../stores/workspace/types";

const PEN_BY_STATUS: Record<string, string> = {
  REMOVED: "ai_red",
  CHANGED: "ai_orange",
  ADDED: "checker_blue",
  CONFLICT: "ai_conflict",
};

/**
 * Marker shape consumed by the checklist and canvas overlay.
 *
 * Extends `ViolationItem` rather than restating it, so this stays assignable to the store's
 * `violations` and to `reconcilePersistedIds`'s `MarkerLike`. The four extras below are carried
 * by canvas markings but are not part of a violation.
 *
 * The index signature is load-bearing, not laziness: `MarkerLike` declares `[key: string]:
 * unknown`, and TypeScript grants an *implicit* index signature to object type literals but never
 * to an interface — so without it this is not assignable to `MarkerLike` at all. It is also
 * honest, since markings carry pass-through keys nothing here names. The named fields keep their
 * real types regardless; the signature only admits additional ones.
 */
export interface RestoredMarker extends ViolationItem {
  bbox?: unknown;
  ref_bbox?: unknown;
  verification?: unknown;
  origin?: unknown;
  [key: string]: unknown;
}

export function mapCanvasMarkingsToMarkers(
  markings: any[] | null | undefined,
  idPrefix = "phys_chk_restored"
): RestoredMarker[] {
  if (!Array.isArray(markings)) return [];

  // One timestamp for the whole batch rather than per marker: ids only need to be unique
  // within the set, and calling Date.now() inside the loop made them depend on how long the
  // map took to run.
  const stamp = Date.now();

  return markings.map((marking: any, index: number) => ({
    id: `${idPrefix}_${index}_${stamp}`,
    severity: marking.status === "MATCHED" ? "low" : "high",
    category: marking.category || "Physical Checklist",
    description: marking.text_content,
    recommendation: marking.details || "Automatic verification match",
    affected_entities: [],
    confidence: 1.0,
    coordinates: marking.coordinates,
    ref_coordinates: marking.ref_coordinates,
    bbox: marking.bbox,
    ref_bbox: marking.ref_bbox,
    pen_type: PEN_BY_STATUS[marking.status] ?? "resolved_green",
    is_resolved: marking.status === "MATCHED",
    original_value: marking.original_value,
    // Provenance from the removed `hybrid` method (ADR-006) — always undefined now, kept for
    // cached payloads written before the removal, same as backend.
    verification: marking.verification,
    origin: marking.origin,
    // Sub-item taxonomy tag (docs/checklist-taxonomy-grouping-implementation-plan.md, Phase 5)
    // — pass-through only, undefined when the backend didn't set one.
    feature: marking.feature,
    // Both were dropped here once while the live path (markerGenerator.ts) kept them, so a
    // restored room lost the two fields that identify a finding. `entity_handle` is what a
    // human correction sends to the trainer, and both are the join key back to the persisted
    // AuditViolation.
    entity_handle: marking.entity_id,
    status: marking.status,
  }));
}
