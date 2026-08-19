import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { CorrectionControls } from "./CorrectionControls";
import { submitAuditFeedbackPayload, retractAuditFeedback } from "../../services/auditsApi";
import { useReviewStore } from "../../stores/reviewStore";

vi.mock("../../services/auditsApi", () => ({
  submitAuditFeedbackPayload: vi.fn().mockResolvedValue({ id: "1", status: "recorded", auto_documented: false, message: "" }),
  retractAuditFeedback: vi.fn().mockResolvedValue(undefined),
}));

const mockedSubmit = submitAuditFeedbackPayload as unknown as ReturnType<typeof vi.fn>;
const mockedRetract = retractAuditFeedback as unknown as ReturnType<typeof vi.fn>;

const baseProps = {
  rowId: "r1",
  categoryKey: "drawing_views",
  statusText: "CHANGED",
  row: { field: "Dim", original: "20", kmti: "25" },
  matchingViolation: {
    entity_handle: "1B2A",
    description: "25",
    original_value: "20",
    status: "CHANGED",
    category: "drawing_views",
    feature: "dimension",
    coordinates: [1, 2],
    ref_coordinates: [1, 3],
  },
  sessionId: "sess",
  drawingId: "dwg",
  clientName: "KMTI",
};

describe("CorrectionControls", () => {
  beforeEach(() => {
    // The armed correction is global on purpose — it has to survive the engineer scrolling the
    // panel — so it also survives a test. One armed pick would otherwise leave every later card
    // rendering its "waiting" state instead of its menu.
    useReviewStore.getState().setPendingCounterpart(null);
    mockedSubmit.mockClear();
    mockedRetract.mockClear();
  });

  // --- a mis-click has to be reversible ------------------------------------------------
  //
  // The menu was one-way: the correction was already persisted and had already kicked a
  // retrain, and the card then rendered a terminal "Taught: …" with no route back.

  it("a correction can be taken back, and the menu returns", async () => {
    render(<CorrectionControls {...baseProps} />);
    fireEvent.click(screen.getByTestId("correction-open-r1"));
    fireEvent.click(screen.getByTestId("correction-matched-r1"));
    await waitFor(() => expect(screen.getByTestId("correction-done-r1")).toBeTruthy());

    fireEvent.click(screen.getByTestId("correction-undo-r1"));
    await waitFor(() => expect(mockedRetract).toHaveBeenCalledWith("1"));

    // Back to the un-corrected state, so the row can be answered again.
    await waitFor(() => expect(screen.getByTestId("correction-open-r1")).toBeTruthy());
    expect(screen.queryByTestId("correction-done-r1")).toBeNull();
  });

  it("offers no undo when the backend returned no id to retract", async () => {
    mockedSubmit.mockResolvedValueOnce({ status: "recorded", auto_documented: false, message: "" });
    render(<CorrectionControls {...baseProps} />);
    fireEvent.click(screen.getByTestId("correction-open-r1"));
    fireEvent.click(screen.getByTestId("correction-matched-r1"));
    await waitFor(() => expect(screen.getByTestId("correction-done-r1")).toBeTruthy());

    // A dead Undo button would be worse than none — it would look like it worked.
    expect(screen.queryByTestId("correction-undo-r1")).toBeNull();
  });

  it("sends verdict_matched with the real entity handle + a finding snapshot", async () => {
    render(<CorrectionControls {...baseProps} />);
    fireEvent.click(screen.getByTestId("correction-open-r1"));
    fireEvent.click(screen.getByTestId("correction-matched-r1"));
    await waitFor(() => expect(mockedSubmit).toHaveBeenCalled());

    const payload = mockedSubmit.mock.calls[0][0];
    expect(payload.human_corrected_status).toBe("verdict_matched");
    expect(payload.entity_handle).toBe("1B2A"); // regression: handle used to always be empty
    expect(payload.finding_snapshot.rev_text).toBe("25");
    expect(payload.finding_snapshot.ref_text).toBe("20");
  });

  it("reclassify sends category_override with corrected_category", async () => {
    render(<CorrectionControls {...baseProps} />);
    fireEvent.click(screen.getByTestId("correction-open-r1"));
    fireEvent.click(screen.getByText("Wrong section"));
    fireEvent.change(screen.getByTestId("correction-category-select-r1"), { target: { value: "title_block" } });
    await waitFor(() => expect(mockedSubmit).toHaveBeenCalled());

    const payload = mockedSubmit.mock.calls[0][0];
    expect(payload.human_corrected_status).toBe("category_override");
    expect(payload.corrected_category).toBe("title_block");
  });

  it("value correction sends corrected_value", async () => {
    render(<CorrectionControls {...baseProps} />);
    fireEvent.click(screen.getByTestId("correction-open-r1"));
    fireEvent.click(screen.getByText("Wrong value"));
    fireEvent.change(screen.getByTestId("correction-value-input-r1"), { target: { value: "ø30" } });
    fireEvent.click(screen.getByTestId("correction-value-save-r1"));
    await waitFor(() => expect(mockedSubmit).toHaveBeenCalled());

    const payload = mockedSubmit.mock.calls[0][0];
    expect(payload.human_corrected_status).toBe("value_correction");
    expect(payload.corrected_value).toBe("ø30");
  });

  it("asks the same question on a MATCHED row, only the wire verb differs", async () => {
    // The menu used to read "Actually a change" vs "Confirm real change" depending on the
    // engine's verdict, which made the reviewer decode that verdict first. One wording now;
    // verdict_changed vs confirmed_change is chosen underneath, and both are label 1.
    const { unmount } = render(<CorrectionControls {...baseProps} statusText="MATCHED" />);
    fireEvent.click(screen.getByTestId("correction-open-r1"));
    expect(screen.getByText("This is a real change")).toBeTruthy();
    fireEvent.click(screen.getByTestId("correction-realchange-r1"));
    await waitFor(() => expect(mockedSubmit).toHaveBeenCalled());
    expect(mockedSubmit.mock.calls[0][0].human_corrected_status).toBe("verdict_changed");
    unmount();
    mockedSubmit.mockClear();

    render(<CorrectionControls {...baseProps} statusText="CHANGED" />);
    fireEvent.click(screen.getByTestId("correction-open-r1"));
    expect(screen.getByText("This is a real change")).toBeTruthy();
    fireEvent.click(screen.getByTestId("correction-realchange-r1"));
    await waitFor(() => expect(mockedSubmit).toHaveBeenCalled());
    expect(mockedSubmit.mock.calls[0][0].human_corrected_status).toBe("confirmed_change");
  });

  it("'wrongly paired' ARMS a counterpart pick rather than submitting a bare rejection", async () => {
    // Changed 2026-08-19. This verb used to submit on the spot, with the correct counterpart
    // offered as an optional text box — skipped 103 times out of 106, leaving a corpus of
    // rejections with no corrections. A matcher cannot be trained on those: there is no target
    // to learn toward.
    //
    // So the click now arms a pick and the canvas completes it. Nothing is submitted here,
    // because a rejection without its correction is the row we already have too many of.
    render(<CorrectionControls {...baseProps} />);
    fireEvent.click(screen.getByTestId("correction-open-r1"));
    fireEvent.click(screen.getByTestId("correction-paired-open-r1"));
    fireEvent.click(screen.getByTestId("correction-paired-missing-r1"));

    expect(mockedSubmit).not.toHaveBeenCalled();

    // The card says it is waiting. Without this the menu just closes and the one gesture that
    // finishes the correction is one nobody has been told to make.
    expect(screen.getByTestId("correction-awaiting-r1")).toBeTruthy();

    const armed = useReviewStore.getState().pendingCounterpart;
    expect(armed?.payload.human_corrected_status).toBe("mispaired_missing_counterpart");
    // The whole payload is carried, not rebuilt at completion: the engineer will scroll and pan
    // before clicking, and this card may be gone from view by then.
    expect(armed?.payload.category).toBe("drawing_views");
    expect(armed?.payload.finding_snapshot).toBeTruthy();
  });

  it("an armed correction can be cancelled", async () => {
    render(<CorrectionControls {...baseProps} />);
    fireEvent.click(screen.getByTestId("correction-open-r1"));
    fireEvent.click(screen.getByTestId("correction-paired-open-r1"));
    fireEvent.click(screen.getByTestId("correction-paired-wrong-r1"));
    expect(useReviewStore.getState().pendingCounterpart).toBeTruthy();

    fireEvent.click(screen.getByText("Cancel"));
    expect(useReviewStore.getState().pendingCounterpart).toBeNull();
    expect(mockedSubmit).not.toHaveBeenCalled();
  });

  it("offers 'not a change' only where it makes sense", async () => {
    const { unmount } = render(<CorrectionControls {...baseProps} statusText="MATCHED" />);
    fireEvent.click(screen.getByTestId("correction-open-r1"));
    // The engine already says these match; asking the reviewer to confirm it adds a click
    // and no signal.
    expect(screen.queryByTestId("correction-matched-r1")).toBeNull();
    unmount();

    render(<CorrectionControls {...baseProps} statusText="ADDED" />);
    fireEvent.click(screen.getByTestId("correction-open-r1"));
    expect(screen.getByTestId("correction-matched-r1")).toBeTruthy();
  });
});
