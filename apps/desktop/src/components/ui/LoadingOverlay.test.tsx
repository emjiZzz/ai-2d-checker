import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { LoadingOverlay, Z_INDEX } from "./LoadingOverlay";

describe("LoadingOverlay (Signature Global Component)", () => {
  it("renders null when active is false", () => {
    render(<LoadingOverlay active={false} title="Analyzing CAD Drawing" />);
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });

  it("renders title and dynamic phase correctly", () => {
    render(
      <LoadingOverlay
        active={true}
        title="Processing Drawing"
        phase="Parsing DXF entity table…"
      />
    );

    const dialog = screen.getByRole("alertdialog");
    expect(dialog).toBeInTheDocument();
    expect(dialog).toHaveTextContent("Processing Drawing");
    expect(dialog).toHaveTextContent("Parsing DXF entity table…");
  });

  it("captures pointer events and covers the full viewport", () => {
    render(<LoadingOverlay active={true} title="Analyzing" />);
    const dialog = screen.getByRole("alertdialog");
    expect(dialog.style.position).toBe("fixed");
    expect(dialog.style.inset).toBe("0px");
    expect(dialog.style.pointerEvents).not.toBe("none");
  });

  it("respects Z_INDEX invariant", () => {
    expect(Z_INDEX).toBe(9998);
  });
});
