/** Is this id a persisted `AuditViolation`, or a client-side canvas marker?
 *
 * The two live in the same `violations` array and are indistinguishable by shape. Persisted
 * findings carry a Mongo ObjectId; the physical-comparison path synthesises markers client-side
 * as `phys_chk_<i>_inst_<j>_<timestamp>` in `markerGenerator.ts`, and `CanvasContextMenu` adds
 * more for manual pins.
 *
 * This matters wherever a control writes back to the server by id. A supervisor verdict on a
 * synthetic marker would PATCH a document that does not exist — a 404 the reviewer would read as
 * "my review did not save", on a row that was never reviewable in the first place. Better to not
 * offer the control than to offer one that cannot work.
 */
export function isPersistedViolationId(id: string | undefined | null): boolean {
  return typeof id === "string" && /^[a-f0-9]{24}$/i.test(id);
}

/** The id to send to `PATCH /audits/violations/{id}/review`, or `null` if there isn't one.
 *
 * Checklist markers carry a synthetic `id` for canvas bookkeeping and, once
 * `reconcilePersistedIds` has run, a `persisted_id` pointing at the real `AuditViolation`
 * document. Reviews must use the latter; the synthetic id references nothing, which is what
 * produced `PATCH /audits/violations/phys_chk_restored_1_.../review -> 500`.
 *
 * Returning `null` rather than a boolean is deliberate: it makes "can this be reviewed" and
 * "what do I send" the same question with one answer, so a caller cannot check one id and then
 * submit a different one.
 */
export function reviewableViolationId(violation: unknown): string | null {
  const v = violation as { persisted_id?: unknown; id?: unknown } | null | undefined;
  if (!v) return null;
  const candidate = typeof v.persisted_id === "string" ? v.persisted_id : v.id;
  return isPersistedViolationId(candidate as string) ? (candidate as string) : null;
}
