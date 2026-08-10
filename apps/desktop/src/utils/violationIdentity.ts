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
