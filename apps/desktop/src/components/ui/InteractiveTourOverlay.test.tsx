import { describe, it, expect } from "vitest";

import { describeRoomCreationFailure } from "./InteractiveTourOverlay";
import { ApiError } from "../../services/fetchUtils";

/**
 * The tour's step 1 is the first thing an engineer touches in an installed build, and its error
 * card is the only channel that failure has -- there is no console in a packaged desktop app.
 *
 * On 2026-08-28 it read "Could not create the Tutorial Room: Access Denied: Invalid security API
 * Token." The specific branch existed and did not fire, because it was selected by regexing the
 * message for a status code the message does not contain. See
 * `docs/vault/06 - .../Gotcha - The Installed App Bound to a Storage Directory at the Drive Root`.
 */
describe("describeRoomCreationFailure", () => {
  it("explains a rejected token instead of quoting the backend at the tester", () => {
    const message = describeRoomCreationFailure(
      new ApiError("Access Denied: Invalid security API Token.", 401)
    );

    expect(message).toContain("Not authorised by the backend");
    expect(message).toContain("restart the app");
    expect(message).not.toContain("Could not create the Tutorial Room:");
  });

  it("quotes the backend for anything that is not an auth failure", () => {
    // The fallback still has to carry the detail: a validation failure is actionable as written,
    // and replacing it with generic prose would lose the only useful part.
    const message = describeRoomCreationFailure(new ApiError("name: field required", 422));

    expect(message).toBe("Could not create the Tutorial Room: name: field required");
  });

  it("survives a thrown non-Error", () => {
    expect(describeRoomCreationFailure("boom")).toBe("Could not create the Tutorial Room: boom");
  });
});
