import { describe, it, expect } from "vitest";
import { isPersistedViolationId } from "./violationIdentity";

describe("isPersistedViolationId", () => {
  it("accepts a Mongo ObjectId", () => {
    expect(isPersistedViolationId("6a7054aa91fcddc32ab4adfc")).toBe(true);
  });

  it("rejects the physical-comparison path's synthetic marker ids", () => {
    // The exact shape markerGenerator.ts emits. A supervisor verdict on one of these would
    // PATCH a document that does not exist.
    expect(isPersistedViolationId("phys_chk_0_inst_0_1760000000000")).toBe(false);
  });

  it("rejects empty, missing and near-miss ids", () => {
    expect(isPersistedViolationId(undefined)).toBe(false);
    expect(isPersistedViolationId(null)).toBe(false);
    expect(isPersistedViolationId("")).toBe(false);
    expect(isPersistedViolationId("6a7054aa91fcddc32ab4adf")).toBe(false);  // 23 chars
    expect(isPersistedViolationId("6a7054aa91fcddc32ab4adfcc")).toBe(false); // 25 chars
    expect(isPersistedViolationId("zzzz54aa91fcddc32ab4adfc")).toBe(false);  // not hex
  });
});
