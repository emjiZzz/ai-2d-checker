/**
 * The 2D/3D switch appears only where there is something to switch to.
 *
 * In this shop every reference drawing is 2D and only the revision is an .icd carrying both
 * halves, so a control rendered greyed-out on every reference pane would be dead weight on the
 * majority of panes. It is absent there, not disabled.
 *
 * The condition is `entity_counts.mesh` -- a glTF was written for this drawing -- rather than
 * the file extension, which only says one might have been. An .icd holding just a sheet gets
 * no toggle, and that is correct.
 *
 * Single-button design:
 * When the canvas is 2D, the button displays "3D".
 * When the canvas is 3D, the button displays "2D".
 */
import { act, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { ViewModeToggle } from "./ViewModeToggle";
import { useReviewStore } from "../../stores/reviewStore";

const withMesh = {
  id: "d1",
  file_name: "17131ML-A4031-0.icd",
  format: "icd",
  entity_counts: { line: 7661, text: 247, mesh: 1, faces: 86 },
} as any;

const drawingOnly = {
  id: "d2",
  file_name: "M745305N01.dxf",
  format: "dxf",
  entity_counts: { line: 327, text: 260 },
} as any;

const icdWithoutModel = {
  id: "d3",
  file_name: "sheet_only.icd",
  format: "icd",
  entity_counts: { line: 120, text: 40 },
} as any;

describe("ViewModeToggle", () => {
  beforeEach(() => {
    useReviewStore.setState({ viewMode: { old: "2d", new: "2d" } });
  });

  it("renders '3D' button for a 2D drawing that has a 3D model available", () => {
    render(<ViewModeToggle side="new" drawing={withMesh} />);
    expect(screen.getByRole("button", { name: "3D" })).toBeInTheDocument();
  });

  it("renders '2D' button when the pane is currently in 3D mode", () => {
    useReviewStore.setState({ viewMode: { old: "2d", new: "3d" } });
    render(<ViewModeToggle side="new" drawing={withMesh} />);
    expect(screen.getByRole("button", { name: "2D" })).toBeInTheDocument();
  });

  it("renders nothing for a 2D-only drawing", () => {
    const { container } = render(<ViewModeToggle side="old" drawing={drawingOnly} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing for an .icd that carries no model", () => {
    // The extension is not the condition. This file is `.icd` and still has nothing to show.
    const { container } = render(<ViewModeToggle side="new" drawing={icdWithoutModel} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing when the pane is empty", () => {
    const { container } = render(<ViewModeToggle side="new" drawing={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("switches only its own pane and toggles the button label", () => {
    const { rerender } = render(<ViewModeToggle side="new" drawing={withMesh} />);
    
    // In 2D mode, button says "3D"
    const button = screen.getByRole("button", { name: "3D" });
    act(() => {
      button.click();
    });
    
    // Store updated to 3D for 'new' pane, 'old' remains 2D
    expect(useReviewStore.getState().viewMode).toEqual({ old: "2d", new: "3d" });

    // Rerender shows "2D" label
    rerender(<ViewModeToggle side="new" drawing={withMesh} />);
    expect(screen.getByRole("button", { name: "2D" })).toBeInTheDocument();
  });
});
