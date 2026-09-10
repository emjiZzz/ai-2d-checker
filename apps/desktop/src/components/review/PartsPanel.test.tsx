/**
 * The assembly parts list, and which rows it hides.
 *
 * The one thing that must not regress: iCAD REPEATS a part name across instances -- two
 * `φ9×204` on one assembly are two real parts, not a duplicate row. Rows are therefore keyed
 * and toggled by glTF node index, and a name-based implementation would hide both at once
 * while looking perfectly correct on any assembly whose parts happen to be unique.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { PartsPanel, type AssemblyPart } from "./PartsPanel";
import { useReviewStore } from "../../stores/reviewStore";

/** `M745246A01_FSRS2.icd` as the backend reports it -- note the repeated names. */
const PARTS: AssemblyPart[] = [
  { index: 0, node: 0, name: "φ9×204", surfaces: 7, triangles: 5114, volume_mm3: 12935.88 },
  { index: 1, node: 1, name: "φ9×204", surfaces: 7, triangles: 5106, volume_mm3: 12935.88 },
  { index: 2, node: 2, name: "2.3×80×257", surfaces: 6, triangles: 86, volume_mm3: 41676.34 },
  { index: 3, node: 3, name: "2.3×700×711", surfaces: 30, triangles: 1274, volume_mm3: 1122003.56 },
];

const rows = () => screen.getAllByRole("button").filter((b) => b.textContent?.includes("×"));

describe("PartsPanel", () => {
  beforeEach(() => {
    useReviewStore.setState({ hiddenParts: {} });
  });

  it("lists every part, including repeated names", () => {
    render(<PartsPanel drawingId="d1" parts={PARTS} />);
    expect(rows()).toHaveLength(4);
    expect(screen.getAllByText("φ9×204")).toHaveLength(2);
  });

  it("hides only the instance that was clicked", () => {
    render(<PartsPanel drawingId="d1" parts={PARTS} />);
    // The SECOND `φ9×204`. Toggling by name would take its twin with it.
    fireEvent.click(rows()[1]);
    expect(useReviewStore.getState().hiddenParts["d1"]).toEqual([1]);
  });

  it("toggles back on a second click", () => {
    render(<PartsPanel drawingId="d1" parts={PARTS} />);
    fireEvent.click(rows()[2]);
    fireEvent.click(rows()[2]);
    expect(useReviewStore.getState().hiddenParts["d1"]).toEqual([]);
  });

  it("keeps each drawing's hidden parts separate", () => {
    useReviewStore.setState({ hiddenParts: { other: [0, 1, 2, 3] } });
    render(<PartsPanel drawingId="d1" parts={PARTS} />);
    fireEvent.click(rows()[0]);
    const state = useReviewStore.getState().hiddenParts;
    expect(state["d1"]).toEqual([0]);
    expect(state["other"]).toEqual([0, 1, 2, 3]);
  });

  it("hides all, then shows all", () => {
    render(<PartsPanel drawingId="d1" parts={PARTS} />);
    fireEvent.click(screen.getByRole("button", { name: "Hide all" }));
    expect(useReviewStore.getState().hiddenParts["d1"]).toEqual([0, 1, 2, 3]);
    fireEvent.click(screen.getByRole("button", { name: "Show all" }));
    expect(useReviewStore.getState().hiddenParts["d1"]).toEqual([]);
  });

  it("marks a hidden row for assistive tech", () => {
    useReviewStore.setState({ hiddenParts: { d1: [1] } });
    render(<PartsPanel drawingId="d1" parts={PARTS} />);
    expect(rows()[0]).toHaveAttribute("aria-pressed", "true");
    expect(rows()[1]).toHaveAttribute("aria-pressed", "false");
  });

  it("renders nothing for a single-solid model", () => {
    // A list of one thing you can only hide is not a feature.
    const { container } = render(<PartsPanel drawingId="d1" parts={[PARTS[0]]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing when the model has no parts at all", () => {
    const { container } = render(<PartsPanel drawingId="d1" parts={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
