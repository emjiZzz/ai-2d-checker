import { describe, it, expect } from "vitest";
import { parsePersistedViolation, reconcilePersistedIds } from "./persistedViolations";
import { reviewableViolationId } from "./violationIdentity";

/** Builds a violation exactly as `orchestrator.py` writes one.
 *
 * The f-strings are reproduced literally rather than abstracted, because they ARE the join. If
 * the backend's wording changes, these tests must fail — that is the whole point of spelling
 * them out here instead of sharing a helper with the production parser.
 */
function persisted(opts: {
  id: string;
  category: string;
  status: string;
  text: string;
  details?: string;
  entityId?: string;
}) {
  return {
    id: opts.id,
    category: `comparison_${opts.category}`,
    description: `[${opts.status}] ${opts.details ?? "some detail"}`,
    recommendation: `Resolve discrepancy in '${opts.text}' against the reference drawing.`,
    affected_entities: opts.entityId ? [{ entity_id: opts.entityId, marker_shape: "BOX" }] : [],
  };
}

const OID_A = "507f1f77bcf86cd799439011";
const OID_B = "507f1f77bcf86cd799439012";

describe("parsePersistedViolation", () => {
  it("recovers category, status and text from the backend's format strings", () => {
    const parsed = parsePersistedViolation(
      persisted({ id: OID_A, category: "title_block", status: "CHANGED", text: "板厚 12" })
    );
    expect(parsed).toEqual({
      category: "title_block",
      status: "CHANGED",
      text: "板厚 12",
      entityId: null,
    });
  });

  it("handles text containing quotes and brackets without truncating it", () => {
    // The recommendation wraps the text in single quotes, so a greedy or lazy regex gets this
    // wrong in opposite directions. CAD text really does contain punctuation.
    const parsed = parsePersistedViolation(
      persisted({ id: OID_A, category: "notes_section", status: "ADDED", text: "NOTE '2' [REF]" })
    );
    expect(parsed?.text).toBe("NOTE '2' [REF]");
  });

  it("returns null for a violation that does not follow the format", () => {
    // Violations from the standards-audit path share this collection but are written by
    // different code. Silently mis-parsing one would attach a verdict to the wrong finding.
    expect(
      parsePersistedViolation({
        id: OID_A,
        category: "iso_2768",
        description: "Tolerance missing",
        recommendation: "Add a general tolerance note.",
      })
    ).toBeNull();
  });
});

describe("reconcilePersistedIds", () => {
  it("gives a marker the id of the AuditViolation that describes it", () => {
    const markers = [
      { id: "phys_chk_0_inst_0_1", category: "title_block", status: "CHANGED", description: "板厚 12" },
    ];
    const [out] = reconcilePersistedIds(markers, [
      persisted({ id: OID_A, category: "title_block", status: "CHANGED", text: "板厚 12" }),
    ]);

    expect(out.persisted_id).toBe(OID_A);
    expect(reviewableViolationId(out)).toBe(OID_A);
  });

  it("prefers the entity handle over the text", () => {
    // Two findings with identical text but different handles. Text alone cannot separate them.
    const markers = [
      { id: "m1", category: "bill_of_materials", status: "CHANGED", description: "10", entity_handle: "B2" },
      { id: "m2", category: "bill_of_materials", status: "CHANGED", description: "10", entity_handle: "A1" },
    ];
    const out = reconcilePersistedIds(markers, [
      persisted({ id: OID_A, category: "bill_of_materials", status: "CHANGED", text: "10", entityId: "A1" }),
      persisted({ id: OID_B, category: "bill_of_materials", status: "CHANGED", text: "10", entityId: "B2" }),
    ]);

    expect(out[0].persisted_id).toBe(OID_B);
    expect(out[1].persisted_id).toBe(OID_A);
  });

  it("never gives one AuditViolation to two markers", () => {
    // The failure this guards is not a missing verdict, it is a verdict recorded against a
    // finding the reviewer never looked at.
    const markers = [
      { id: "m1", category: "notes_section", status: "ADDED", description: "SAME" },
      { id: "m2", category: "notes_section", status: "ADDED", description: "SAME" },
    ];
    const out = reconcilePersistedIds(markers, [
      persisted({ id: OID_A, category: "notes_section", status: "ADDED", text: "SAME" }),
    ]);

    expect(out[0].persisted_id).toBe(OID_A);
    expect(out[1].persisted_id).toBeUndefined();
    expect(reviewableViolationId(out[1])).toBeNull();
  });

  it("leaves a MATCHED marker unreviewable, because none is ever persisted", () => {
    const markers = [
      { id: "m1", category: "title_block", status: "MATCHED", description: "100" },
    ];
    const out = reconcilePersistedIds(markers, [
      persisted({ id: OID_A, category: "title_block", status: "CHANGED", text: "100" }),
    ]);

    expect(out[0].persisted_id).toBeUndefined();
    expect(reviewableViolationId(out[0])).toBeNull();
  });

  it("does not match across categories or statuses", () => {
    const markers = [
      { id: "m1", category: "notes_section", status: "CHANGED", description: "12" },
    ];
    expect(
      reconcilePersistedIds(markers, [
        persisted({ id: OID_A, category: "title_block", status: "CHANGED", text: "12" }),
      ])[0].persisted_id
    ).toBeUndefined();
    expect(
      reconcilePersistedIds(markers, [
        persisted({ id: OID_A, category: "notes_section", status: "REMOVED", text: "12" }),
      ])[0].persisted_id
    ).toBeUndefined();
  });

  it("returns the markers untouched when the fetch yielded nothing", () => {
    // fetchPersistedViolations swallows errors and returns []. The checklist must still render.
    const markers = [{ id: "m1", category: "title_block", status: "CHANGED", description: "12" }];
    expect(reconcilePersistedIds(markers, [])).toBe(markers);
  });
});

describe("reviewableViolationId", () => {
  it("ignores a synthetic canvas id even when no persisted id was joined", () => {
    // The exact id from the production 500.
    expect(reviewableViolationId({ id: "phys_chk_restored_1_1786329084013" })).toBeNull();
  });

  it("prefers the persisted id over the canvas id", () => {
    expect(reviewableViolationId({ id: "phys_chk_0_inst_0_1", persisted_id: OID_A })).toBe(OID_A);
  });

  it("is null for junk", () => {
    expect(reviewableViolationId(null)).toBeNull();
    expect(reviewableViolationId(undefined)).toBeNull();
    expect(reviewableViolationId({})).toBeNull();
  });
});
