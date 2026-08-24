/**
 * zoneGate.ts
 *
 * Decides whether the Comparison Results panel may appear.
 *
 * The 2D workspace is sequenced: ingest both drawings -> confirm the zone boxes -> compare.
 * Zone boxes drive BOM row extraction, category assignment, safe-zone exclusion and the crop
 * verifier, and detection is measurably unreliable on real sheets (`iso` has never been
 * detected on any drawing in the corpus; `notes`/`views`/`tolerance` drift 33-64pp between
 * sheets). Running a comparison against unreviewed boxes produces confidently wrong output,
 * so the panel stays hidden until a human has looked at them.
 *
 * Pure on purpose: the rule is testable without mounting flexlayout, canvas refs or
 * ResizeObserver. Mirrors the `utils/zoneFractions.ts` + `zoneFractions.test.ts` convention.
 */

import { isPrototypeMode } from "../config/features";

/** The subset of `Room` this module needs. Structural, so tests need no store. */
export interface ZoneGateRoom {
  id: string;
  active_old_drawing_id?: string | null;
  active_new_drawing_id?: string | null;
  active_audit_session_id?: string | null;
  physical_comparison_results?: unknown;
  zones_confirmed_for?: string | null;
}

/** Identity of a confirmed pair, as stored in `Room.zones_confirmed_for`. */
export function zonePairKey(
  oldDrawingId: string | null | undefined,
  newDrawingId: string | null | undefined,
): string | null {
  if (!oldDrawingId || !newDrawingId) return null;
  return `${oldDrawingId}:${newDrawingId}`;
}

/**
 * True when the room document describes the drawings currently loaded in the workspace.
 *
 * Guards a real ordering race: `roomStore.openRoom` pushes the drawings into workspaceStore
 * well before it sets `activeRoom` (deliberately last, to avoid a different race). In that
 * window both drawings are present while `activeRoom` is still the *previous* room, so any
 * rule combining the two would be evaluating a room against someone else's drawings. Callers
 * should treat "not synced" as "decide nothing yet".
 */
export function isRoomSyncedWithDrawings(
  room: ZoneGateRoom | null | undefined,
  oldDrawingId: string | null | undefined,
  newDrawingId: string | null | undefined,
): boolean {
  if (!room || !oldDrawingId || !newDrawingId) return false;
  return (
    room.active_old_drawing_id === oldDrawingId &&
    room.active_new_drawing_id === newDrawingId
  );
}

/** True when the user confirmed the zone boxes for *this exact pair*. */
export function isZoneReviewConfirmed(
  room: ZoneGateRoom | null | undefined,
  oldDrawingId: string | null | undefined,
  newDrawingId: string | null | undefined,
): boolean {
  const pair = zonePairKey(oldDrawingId, newDrawingId);
  if (!pair || !room) return false;
  return room.zones_confirmed_for === pair;
}

/**
 * True when the room already holds work that predates this gate.
 *
 * A room with existing results must never have that work hidden behind a step introduced
 * after the fact. Checks two fields, not one: `physical_comparison_results` is the physical
 * checklist path, while `active_audit_session_id` covers rooms restored through the audit
 * session branch, which populates violations and a compliance score without necessarily
 * writing the former.
 *
 * IMPORTANT: callers must snapshot this per room-open rather than deriving it live. The
 * reverse-sync effect in AuditWorkspace nulls `physical_comparison_results` server-side
 * whenever the scan returns to idle -- which is exactly what Re-test does -- so a live
 * reading would delete the Comparison Results panel out from under a user mid-retest.
 */
export function isZoneReviewGrandfathered(room: ZoneGateRoom | null | undefined): boolean {
  if (!room) return false;
  return Boolean(room.physical_comparison_results) || Boolean(room.active_audit_session_id);
}

/**
 * The gate itself: may the Comparison Results panel be shown?
 *
 * `locallyConfirmedPair` is the optimistic value written when Done is clicked, so the panel
 * appears on click rather than after the PATCH round-trip -- and still appears if the
 * backend write fails.
 */
export function isZoneGateOpen(args: {
  oldDrawingId: string | null | undefined;
  newDrawingId: string | null | undefined;
  room: ZoneGateRoom | null | undefined;
  /** Snapshot taken when the room was opened -- see isZoneReviewGrandfathered. */
  grandfathered: boolean;
  locallyConfirmedPair?: string | null;
}): boolean {
  const { oldDrawingId, newDrawingId, room, grandfathered, locallyConfirmedPair } = args;

  const pair = zonePairKey(oldDrawingId, newDrawingId);
  if (!pair) return false; // both drawings are required regardless of confirmation

  if (isPrototypeMode()) return true;
  if (grandfathered) return true;
  if (locallyConfirmedPair === pair) return true;
  return isZoneReviewConfirmed(room, oldDrawingId, newDrawingId);
}
