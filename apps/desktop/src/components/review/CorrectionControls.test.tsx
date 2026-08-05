import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { CorrectionControls } from "./CorrectionControls";
import { submitAuditFeedbackPayload } from "../../services/auditsApi";

vi.mock("../../services/auditsApi", () => ({
  submitAuditFeedbackPayload: vi.fn().mockResolvedValue({ id: "1", status: "recorded", auto_documented: false, message: "" }),
}));

const mockedSubmit = submitAuditFeedbackPayload as unknown as ReturnType<typeof vi.fn>;

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
    mockedSubmit.mockClear();
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

  it("'wrongly paired' sends a matcher verb, not a verdict, and carries the note", async () => {
    // The finding in the screenshot that motivated this: "NONE vs 260" is neither a real
    // change nor a false alarm — the matcher failed to pair it. No previous verb could say so.
    render(<CorrectionControls {...baseProps} />);
    fireEvent.click(screen.getByTestId("correction-open-r1"));
    fireEvent.click(screen.getByTestId("correction-paired-open-r1"));
    fireEvent.change(screen.getByTestId("correction-paired-note-r1"), {
      target: { value: "pairs with 260 on the reference" },
    });
    fireEvent.click(screen.getByTestId("correction-paired-missing-r1"));
    await waitFor(() => expect(mockedSubmit).toHaveBeenCalled());

    const payload = mockedSubmit.mock.calls[0][0];
    expect(payload.human_corrected_status).toBe("mispaired_missing_counterpart");
    expect(payload.human_comment).toBe("pairs with 260 on the reference");
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
