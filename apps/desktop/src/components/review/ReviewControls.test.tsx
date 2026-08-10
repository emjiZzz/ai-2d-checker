import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { ReviewControls } from "./ReviewControls";
import { reviewViolation } from "../../services/auditsApi";

vi.mock("../../services/auditsApi", () => ({
  reviewViolation: vi.fn(),
}));

const mockedReview = reviewViolation as unknown as ReturnType<typeof vi.fn>;

/** Mirrors what the backend actually returns, so a test cannot pass against a shape the server
 *  never sends. `is_resolved` tracks the verdict; `resolution_type` is the three-state field. */
const serverResult = (resolution: "APPROVED" | "REJECTED", remarks = "") => ({
  id: "v1",
  resolution_type: resolution,
  is_resolved: resolution === "APPROVED",
  checker_remarks: remarks,
  resolved_at: "2026-08-10T00:00:00Z",
});

beforeEach(() => {
  vi.clearAllMocks();
  mockedReview.mockResolvedValue(serverResult("APPROVED"));
});

describe("ReviewControls", () => {
  it("offers a verdict when the finding has never been reviewed", () => {
    render(<ReviewControls violationId="v1" resolution={null} />);
    expect(screen.getByText("Approve")).toBeTruthy();
    expect(screen.getByText("Reject")).toBeTruthy();
  });

  it("sends is_valid=true with remarks when approving", async () => {
    render(<ReviewControls violationId="v1" resolution={null} />);

    fireEvent.change(screen.getByLabelText("Review remarks"), {
      target: { value: "confirmed against the revision" },
    });
    fireEvent.click(screen.getByText("Approve"));

    await waitFor(() =>
      expect(mockedReview).toHaveBeenCalledWith("v1", true, "confirmed against the revision")
    );
  });

  it("sends is_valid=false when rejecting", async () => {
    mockedReview.mockResolvedValue(serverResult("REJECTED", "false positive"));
    render(<ReviewControls violationId="v1" resolution={null} />);

    fireEvent.click(screen.getByText("Reject"));

    await waitFor(() => expect(mockedReview).toHaveBeenCalledWith("v1", false, ""));
  });

  it("reports the verdict the SERVER stored, not the one the click implied", async () => {
    // If the two ever diverge the server wins. An optimistic UI that shows APPROVED while the
    // database holds something else is how a supervisor believes work is saved when it is not.
    mockedReview.mockResolvedValue(serverResult("REJECTED", "server disagreed"));
    const onReviewed = vi.fn();
    render(<ReviewControls violationId="v1" resolution={null} onReviewed={onReviewed} />);

    fireEvent.click(screen.getByText("Approve"));

    await waitFor(() =>
      expect(onReviewed).toHaveBeenCalledWith({
        resolution: "REJECTED",
        remarks: "server disagreed",
      })
    );
  });

  it("shows a REJECTED finding as decided, not as awaiting review", () => {
    // The defect this component exists to avoid: `is_resolved` is false for REJECTED and for
    // unreviewed alike, so a control keyed on it would put every rejected finding back in the
    // queue forever and the reviewer's work would appear not to have happened.
    render(<ReviewControls violationId="v1" resolution="REJECTED" remarks="false positive" />);

    expect(screen.getByTestId("review-verdict")).toBeTruthy();
    expect(screen.getByText("Rejected")).toBeTruthy();
    expect(screen.queryByText("Approve")).toBeNull();
    expect(screen.queryByText("Reject")).toBeNull();
  });

  it("shows an APPROVED finding as decided", () => {
    render(<ReviewControls violationId="v1" resolution="APPROVED" />);
    expect(screen.getByText("Approved")).toBeTruthy();
    expect(screen.queryByText("Approve")).toBeNull();
  });

  it("lets a reviewer change a verdict already recorded", async () => {
    mockedReview.mockResolvedValue(serverResult("REJECTED"));
    render(<ReviewControls violationId="v1" resolution="APPROVED" />);

    fireEvent.click(screen.getByLabelText("Change verdict"));
    fireEvent.click(screen.getByText("Reject"));

    await waitFor(() => expect(mockedReview).toHaveBeenCalledWith("v1", false, ""));
  });

  it("surfaces a failed save instead of looking like it worked", async () => {
    // A silently-failed review is worse than one that never happened: the supervisor moves on
    // believing the finding is handled while it is still unreviewed in the database.
    mockedReview.mockRejectedValue(new Error("Failed to record violation review (500): boom"));
    const onReviewed = vi.fn();
    render(<ReviewControls violationId="v1" resolution={null} onReviewed={onReviewed} />);

    fireEvent.click(screen.getByText("Approve"));

    await waitFor(() => expect(screen.getByTestId("review-error")).toBeTruthy());
    expect(onReviewed).not.toHaveBeenCalled();
    // Still offering the buttons matters — the reviewer must be able to retry.
    expect(screen.getByText("Approve")).toBeTruthy();
  });
});
