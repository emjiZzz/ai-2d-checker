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
    fireEvent.click(screen.getByText("Reclassify category"));
    fireEvent.change(screen.getByTestId("correction-category-select-r1"), { target: { value: "title_block" } });
    await waitFor(() => expect(mockedSubmit).toHaveBeenCalled());

    const payload = mockedSubmit.mock.calls[0][0];
    expect(payload.human_corrected_status).toBe("category_override");
    expect(payload.corrected_category).toBe("title_block");
  });

  it("value correction sends corrected_value", async () => {
    render(<CorrectionControls {...baseProps} />);
    fireEvent.click(screen.getByTestId("correction-open-r1"));
    fireEvent.click(screen.getByText("Fix value / note"));
    fireEvent.change(screen.getByTestId("correction-value-input-r1"), { target: { value: "ø30" } });
    fireEvent.click(screen.getByTestId("correction-value-save-r1"));
    await waitFor(() => expect(mockedSubmit).toHaveBeenCalled());

    const payload = mockedSubmit.mock.calls[0][0];
    expect(payload.human_corrected_status).toBe("value_correction");
    expect(payload.corrected_value).toBe("ø30");
  });

  it("on a MATCHED row, offers 'Actually a change' (verdict_changed)", async () => {
    render(<CorrectionControls {...baseProps} statusText="MATCHED" />);
    fireEvent.click(screen.getByTestId("correction-open-r1"));
    fireEvent.click(screen.getByTestId("correction-realchange-r1"));
    await waitFor(() => expect(mockedSubmit).toHaveBeenCalled());
    expect(mockedSubmit.mock.calls[0][0].human_corrected_status).toBe("verdict_changed");
  });
});
