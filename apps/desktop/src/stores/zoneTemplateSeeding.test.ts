/**
 * Tests that a hand-aligned zone template is layered over detection when the editor seeds.
 *
 * The bug: `fetchZoneTemplate` existed in drawingsApi but had ZERO call sites. The desktop
 * client was write-only for templates — `saveZoneTemplate` persisted the alignment and the
 * backend honoured it during comparison (`extract_dynamic_regions_async` →
 * `resolve_zone_overrides`), but the editor re-seeded from the detector every time it
 * opened. So the user's pinned boxes appeared to have been discarded, and the editor showed
 * a different set of zones than the audit actually ran on.
 *
 * Precedence must mirror the backend: defaults < detected < template. A per-drawing saved
 * alignment still outranks all three, because that is the user's own in-progress work.
 */
import { beforeEach, describe, expect, it } from "vitest";

import { useReviewStore } from "./reviewStore";
import { DEFAULT_CUSTOM_REGIONS } from "../utils/zoneFractions";

// render_bounds of the real reference sheet: 1155 x 816.75, CAD Y-up.
const BOUNDS: [number, number, number, number] = [-52.5, -37.125, 1102.5, 779.625];

const DRAWING = "drawing-1";

/** A detected box, CAD Y-up, occupying the sheet's bottom-right corner. */
const DETECTED_TITLE = { xmin: 500.0, ymin: -37.125, xmax: 1102.5, ymax: 200.0 };

/** A pinned template zone, Y-DOWN fractions — the same space as customRegions. */
const PINNED_TITLE = { xMin: 0.375, xMax: 0.931, yMin: 0.796, yMax: 0.925 };

function reset() {
  useReviewStore.setState({ customRegions: {}, hasSeededCustomRegions: false });
  localStorage.clear();
}

describe("seedCustomRegionsFromDetected — template layering", () => {
  beforeEach(reset);

  it("uses the detected box when no template exists", () => {
    useReviewStore.getState().seedCustomRegionsFromDetected(
      { title: DETECTED_TITLE }, BOUNDS, DRAWING,
    );

    const title = useReviewStore.getState().getRegionsFor(DRAWING).title;
    expect(title).toBeDefined();
    // Not the coarse default any more.
    expect(title).not.toEqual(DEFAULT_CUSTOM_REGIONS.title);
  });

  it("a pinned template zone overrides the detected box", () => {
    useReviewStore.getState().seedCustomRegionsFromDetected(
      { title: DETECTED_TITLE }, BOUNDS, DRAWING, { title: PINNED_TITLE },
    );

    const title = useReviewStore.getState().getRegionsFor(DRAWING).title;
    expect(title.xMin).toBeCloseTo(PINNED_TITLE.xMin, 6);
    expect(title.xMax).toBeCloseTo(PINNED_TITLE.xMax, 6);
    expect(title.yMin).toBeCloseTo(PINNED_TITLE.yMin, 6);
    expect(title.yMax).toBeCloseTo(PINNED_TITLE.yMax, 6);
  });

  it("template fractions are applied without a Y flip", () => {
    // ZoneFractions is stored Y-DOWN specifically to match customRegions. Flipping here
    // would mirror every pinned zone — and because zones cluster near the sheet's vertical
    // centre, the result looks plausible on screen.
    useReviewStore.getState().seedCustomRegionsFromDetected(
      {}, BOUNDS, DRAWING, { title: PINNED_TITLE },
    );

    const title = useReviewStore.getState().getRegionsFor(DRAWING).title;
    expect(title.yMin).toBeCloseTo(0.796, 6);
    expect(title.yMin).not.toBeCloseTo(1 - PINNED_TITLE.yMax, 3);
  });

  it("zones absent from the template keep detecting", () => {
    useReviewStore.getState().seedCustomRegionsFromDetected(
      { title: DETECTED_TITLE, notes: { xmin: 0, ymin: 400, xmax: 300, ymax: 700 } },
      BOUNDS, DRAWING, { title: PINNED_TITLE },
    );

    const regions = useReviewStore.getState().getRegionsFor(DRAWING);
    expect(regions.title.xMin).toBeCloseTo(PINNED_TITLE.xMin, 6);
    // `notes` is not templatable and must still come from detection, not the default.
    expect(regions.notes).not.toEqual(DEFAULT_CUSTOM_REGIONS.notes);
  });

  it("an existing per-drawing alignment still wins over the template", () => {
    const mine = { xMin: 0.1, xMax: 0.2, yMin: 0.3, yMax: 0.4 };
    useReviewStore.setState({ customRegions: { [DRAWING]: { title: mine } } });

    useReviewStore.getState().seedCustomRegionsFromDetected(
      { title: DETECTED_TITLE }, BOUNDS, DRAWING, { title: PINNED_TITLE },
    );

    expect(useReviewStore.getState().getRegionsFor(DRAWING).title).toEqual(mine);
  });

  it("a null or empty template is a no-op", () => {
    useReviewStore.getState().seedCustomRegionsFromDetected(
      { title: DETECTED_TITLE }, BOUNDS, DRAWING, null,
    );
    const withNull = useReviewStore.getState().getRegionsFor(DRAWING).title;

    reset();
    useReviewStore.getState().seedCustomRegionsFromDetected(
      { title: DETECTED_TITLE }, BOUNDS, DRAWING, {},
    );
    const withEmpty = useReviewStore.getState().getRegionsFor(DRAWING).title;

    expect(withNull).toEqual(withEmpty);
  });

  it("each drawing is seeded independently", () => {
    useReviewStore.getState().seedCustomRegionsFromDetected(
      { title: DETECTED_TITLE }, BOUNDS, "ref", { title: PINNED_TITLE },
    );
    useReviewStore.getState().seedCustomRegionsFromDetected(
      { title: DETECTED_TITLE }, BOUNDS, "rev", null,
    );

    const ref = useReviewStore.getState().getRegionsFor("ref").title;
    const rev = useReviewStore.getState().getRegionsFor("rev").title;
    expect(ref.xMin).toBeCloseTo(PINNED_TITLE.xMin, 6);
    expect(rev.xMin).not.toBeCloseTo(PINNED_TITLE.xMin, 6);
  });
});
