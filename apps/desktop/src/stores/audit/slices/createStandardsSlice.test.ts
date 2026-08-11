/** The standards upload posts to the route that accepts POST.
 *
 * This existed as a defect for the whole life of the feature: the slice posted to
 * `/api/v1/standards`, which is **GET-only** (`standards.py::list_standards`), so every upload
 * returned `405 Method Not Allowed` and no standard could be ingested through the UI. The live
 * backend's own route table:
 *
 *     /api/v1/standards/upload    POST
 *     /api/v1/standards           GET
 *     /api/v1/standards/{id}      DELETE, GET
 *
 * It is worth a test rather than a comment because of what it cost downstream. An empty
 * `standard_chunks` collection was read as *"no standard has ever been uploaded"* — a **data**
 * problem — and a whole track was retired on that reading. The real cause was one missing path
 * segment. Same family as `Gotcha - A Tested Endpoint That Nothing Ever Called`: the endpoint
 * was fine and nothing reached it.
 *
 * TypeScript cannot catch this. The URL is a string, and both spellings type-check.
 */

import { describe, expect, it, vi, beforeEach } from "vitest";

const uploadFile = vi.fn();

vi.mock("../../../services/fetchUtils", () => ({
  uploadFile: (...args: unknown[]) => uploadFile(...args),
  buildHeaders: () => ({}),
  baseUrl: () => "http://127.0.0.1:8080",
  parseOrThrow: async (r: unknown) => r,
}));

vi.mock("../../../services/queryClient", () => ({
  queryClient: { invalidateQueries: vi.fn() },
}));

vi.mock("../../../services/logger", () => ({
  logger: { info: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));

import { createStandardsSlice } from "./createStandardsSlice";

function makeSlice() {
  const state: Record<string, unknown> = {};
  const set = (patch: Record<string, unknown>) => Object.assign(state, patch);
  // The slice only uses `set`; get/store are unused by uploadStandard.
  const slice = (createStandardsSlice as any)(set, () => state, {});
  return { slice, state };
}

describe("uploadStandard", () => {
  beforeEach(() => {
    uploadFile.mockReset();
    uploadFile.mockResolvedValue({ id: "std_1" });
  });

  it("posts to /api/v1/standards/upload, not the GET-only collection route", async () => {
    const { slice } = makeSlice();
    await slice.uploadStandard(new File(["x"], "jis.xlsx"), "JIS");

    expect(uploadFile).toHaveBeenCalledTimes(1);
    const path = uploadFile.mock.calls[0][0] as string;

    expect(path).toBe("/api/v1/standards/upload");
    // Stated separately so the failure message names the actual defect if the suffix is
    // ever dropped again, rather than just printing two similar strings.
    expect(path.endsWith("/upload")).toBe(true);
  });

  it("sends the fields the endpoint requires as Form fields", async () => {
    const { slice } = makeSlice();
    await slice.uploadStandard(
      new File(["x"], "jis.xlsx"),
      "KEMCO AND JIS STANDARDS",
      "Dimensioning",
      "desc",
      "client_specific",
      "KEMCO"
    );

    const body = uploadFile.mock.calls[0][1] as FormData;
    expect(body.get("name")).toBe("KEMCO AND JIS STANDARDS");
    expect(body.get("scope")).toBe("client_specific");
    expect(body.get("client_name")).toBe("KEMCO");
    expect(body.get("category")).toBe("Dimensioning");
  });

  it("omits client_name when the scope is universal", async () => {
    const { slice } = makeSlice();
    await slice.uploadStandard(new File(["x"], "jis.xlsx"), "JIS", "", "", "universal", "KEMCO");

    const body = uploadFile.mock.calls[0][1] as FormData;
    expect(body.get("client_name")).toBeNull();
  });

  it("reports failure rather than claiming success", async () => {
    uploadFile.mockRejectedValue(new Error("Method Not Allowed"));
    const { slice, state } = makeSlice();

    await expect(slice.uploadStandard(new File(["x"], "jis.xlsx"), "JIS")).resolves.toBe(false);
    expect(state.uploadStatus).toBe("error");
    expect(state.errorMessage).toBe("Method Not Allowed");
  });
});
