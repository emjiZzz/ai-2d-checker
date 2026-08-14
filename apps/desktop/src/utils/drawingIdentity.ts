/**
 * Rejects a reference/revision pair that is not a pair.
 *
 * The two slots of a room are meant to hold the same part at two revisions. Nothing used to
 * check that, so ingesting an unrelated drawing into the revision slot produced a full,
 * confident, entirely meaningless comparison — every value on the sheet reported as changed,
 * with no signal that the premise was wrong.
 *
 * The tokens come from the backend (`infrastructure/cad/drawing_identity.py`), which collects
 * every drawing-number-shaped string on the sheet. Neither side tries to identify *the*
 * drawing number; the question is only whether the two sheets **share** one. Measured over
 * the eval corpus: 7/7 real pairs share a token, 42/42 cross-pairings share none.
 *
 * ⚠ **Absent evidence is not a mismatch.** A drawing whose numbering does not match the
 * expected shape yields no tokens, and an older drawing ingested before the field existed
 * carries none at all. Both must pass. A false reject deletes a drawing the user just
 * uploaded; a false accept only runs the comparison they already asked for.
 */

/** True only when both drawings carry numbers and share none of them. */
export function isDrawingPairMismatch(
  a: string[] | undefined | null,
  b: string[] | undefined | null
): boolean {
  const left = a ?? [];
  const right = b ?? [];
  if (left.length === 0 || right.length === 0) return false;

  const rightSet = new Set(right.map((n) => n.toUpperCase()));
  return !left.some((n) => rightSet.has(n.toUpperCase()));
}

/**
 * The message shown when a pair is rejected. Names both drawing numbers, because "these are
 * different drawings" is not actionable on its own — the user needs to see *which* two, to
 * know which slot holds the file they did not mean to upload.
 */
export function describeDrawingPairMismatch(
  rejectedNumbers: string[],
  existingNumbers: string[],
  existingFileName: string
): string {
  const rejected = rejectedNumbers.join(", ");
  const existing = existingNumbers.join(", ");
  return (
    `Different drawing: this file is ${rejected}, but this room already holds ${existing} ` +
    `(${existingFileName}). A comparison only makes sense between two revisions of the same ` +
    `drawing, so this upload was discarded. Please upload a revision of ${existing} instead.`
  );
}
