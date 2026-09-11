/**
 * The assembly parts list: collapsible sidebar, part highlighting on row click,
 * and visibility toggling via eye icon.
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
const eyeButtons = () => screen.getAllByTitle(/part in 3D/i);

describe("PartsPanel", () => {
  beforeEach(() => {
    useReviewStore.setState({ hiddenParts: {}, selectedPart: {} });
  });

  it("lists every part, including repeated names", () => {
    render(<PartsPanel drawingId="d1" parts={PARTS} />);
    expect(rows()).toHaveLength(4);
    expect(screen.getAllByText("φ9×204")).toHaveLength(2);
  });

  it("highlights a part when its item row is clicked", () => {
    render(<PartsPanel drawingId="d1" parts={PARTS} />);
    fireEvent.click(rows()[1]);
    expect(useReviewStore.getState().selectedPart["d1"]).toBe(1);
    expect(rows()[1]).toHaveAttribute("aria-selected", "true");

    // Clicking again deselects
    fireEvent.click(rows()[1]);
    expect(useReviewStore.getState().selectedPart["d1"]).toBeNull();
    expect(rows()[1]).toHaveAttribute("aria-selected", "false");
  });

  it("hides only the instance whose eye icon was clicked", () => {
    render(<PartsPanel drawingId="d1" parts={PARTS} />);
    // The SECOND `φ9×204` eye icon. Toggling by name would take its twin with it.
    fireEvent.click(eyeButtons()[1]);
    expect(useReviewStore.getState().hiddenParts["d1"]).toEqual([1]);

    // Clicking eye icon again shows it
    fireEvent.click(eyeButtons()[1]);
    expect(useReviewStore.getState().hiddenParts["d1"]).toEqual([]);
  });

  it("keeps each drawing's hidden parts separate", () => {
    useReviewStore.setState({ hiddenParts: { other: [0, 1, 2, 3] } });
    render(<PartsPanel drawingId="d1" parts={PARTS} />);
    fireEvent.click(eyeButtons()[0]);
    const state = useReviewStore.getState().hiddenParts;
    expect(state["d1"]).toEqual([0]);
    expect(state["other"]).toEqual([0, 1, 2, 3]);
  });


  it("marks a hidden row for assistive tech", () => {
    useReviewStore.setState({ hiddenParts: { d1: [1] } });
    render(<PartsPanel drawingId="d1" parts={PARTS} />);
    expect(rows()[0]).toHaveAttribute("aria-pressed", "true");
    expect(rows()[1]).toHaveAttribute("aria-pressed", "false");
  });

  it("collapses and expands cleanly", () => {
    render(<PartsPanel drawingId="d1" parts={PARTS} />);
    expect(screen.getAllByText("φ9×204")).toHaveLength(2);

    // Collapse
    fireEvent.click(screen.getByTitle("Collapse Parts Sidebar"));
    expect(screen.queryByText("φ9×204")).not.toBeInTheDocument();
    expect(screen.getByTitle("Expand Parts Sidebar")).toBeInTheDocument();

    // Expand
    fireEvent.click(screen.getByTitle("Expand Parts Sidebar"));
    expect(screen.getAllByText("φ9×204")).toHaveLength(2);
  });

  it("renders nothing for a single-solid model", () => {
    const { container } = render(<PartsPanel drawingId="d1" parts={[PARTS[0]]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing when the model has no parts at all", () => {
    const { container } = render(<PartsPanel drawingId="d1" parts={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
