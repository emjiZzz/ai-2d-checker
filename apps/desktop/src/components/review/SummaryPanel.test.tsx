import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { SummaryPanel } from "./SummaryPanel";
import { getComparisonSummary, type ComparisonSummary } from "../../services/auditsApi";

vi.mock("../../services/auditsApi", () => ({
  getComparisonSummary: vi.fn(),
}));

const mockedGet = getComparisonSummary as unknown as ReturnType<typeof vi.fn>;

const summary = (over: Partial<ComparisonSummary> = {}): ComparisonSummary => ({
  status: "ok",
  headline: "One revision touched three notes.",
  claims: [{ text: "Plate thickness values were revised.", finding_ids: ["f0", "f1", "f2"] }],
  fallback_text: "3 findings: 3 in comparison_notes_section.",
  withheld_reasons: [],
  withheld_detail: "",
  finding_count: 3,
  model_used: "gemini-flash-latest",
  cached: false,
  ...over,
});

beforeEach(() => {
  vi.clearAllMocks();
  mockedGet.mockResolvedValue(summary());
});

describe("SummaryPanel", () => {
  it("renders a verified summary with its claims", async () => {
    render(<SummaryPanel sessionId="s1" />);
    await waitFor(() =>
      expect(screen.getByText("One revision touched three notes.")).toBeTruthy()
    );
    expect(screen.getByText(/Plate thickness values were revised/)).toBeTruthy();
  });

  it("always states the finding count, whatever the status", async () => {
    // ADR-010's mitigation for the failure mode it introduces: a reader who stops at the summary
    // still knows how many items they skipped.
    for (const status of ["ok", "withheld", "unavailable", "disabled"] as const) {
      mockedGet.mockResolvedValue(summary({ status, finding_count: 7 }));
      const { unmount } = render(<SummaryPanel sessionId="s1" />);
      await waitFor(() =>
        expect(screen.getByTestId("summary-finding-count").textContent).toContain("7")
      );
      unmount();
    }
  });

  it("shows the deterministic text AND says the summary was withheld", async () => {
    // The rule: "the generated summary was rejected" and "there were no notable changes" must
    // never look the same to a reader.
    mockedGet.mockResolvedValue(
      summary({
        status: "withheld",
        headline: null,
        claims: [],
        withheld_reasons: ["uncited_finding"],
      })
    );
    render(<SummaryPanel sessionId="s1" />);

    await waitFor(() => expect(screen.getByTestId("summary-fallback")).toBeTruthy());
    expect(screen.getByTestId("summary-note").textContent).toMatch(/withheld/i);
  });

  it("never renders claims for a non-ok status", async () => {
    // A withheld summary must not leak partially through the UI even if the server ever sent
    // claims alongside a non-ok status.
    mockedGet.mockResolvedValue(
      summary({ status: "withheld", headline: "leaked headline", withheld_reasons: ["count_mismatch"] })
    );
    render(<SummaryPanel sessionId="s1" />);

    await waitFor(() => expect(screen.getByTestId("summary-fallback")).toBeTruthy());
    expect(screen.queryByText("leaked headline")).toBeNull();
    expect(screen.queryByText(/Plate thickness values were revised/)).toBeNull();
  });

  it("explains that generation is switched off rather than showing nothing", async () => {
    mockedGet.mockResolvedValue(summary({ status: "disabled", headline: null, claims: [] }));
    render(<SummaryPanel sessionId="s1" />);

    await waitFor(() => expect(screen.getByTestId("summary-note").textContent).toMatch(/turned off/i));
    expect(screen.getByTestId("summary-fallback")).toBeTruthy();
  });

  it("distinguishes a transport failure from an absent summary", async () => {
    mockedGet.mockRejectedValue(new Error("Failed to fetch comparison summary (500): boom"));
    render(<SummaryPanel sessionId="s1" />);

    await waitFor(() => expect(screen.getByRole("alert").textContent).toMatch(/Summary unavailable/));
  });
});
