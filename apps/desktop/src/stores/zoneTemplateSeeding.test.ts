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

  it("a pinned zone is re-applied even when an alignment already exists", () => {
    // The reported bug: `customRegions` is restored from localStorage on reload, so it
    // exists before the user has touched anything. Skipping the template in that case made
    // pinned zones appear to revert to detector boxes on every open.
    useReviewStore.setState({
      customRegions: { [DRAWING]: { title: { xMin: 0.1, xMax: 0.2, yMin: 0.3, yMax: 0.4 } } },
    });

    useReviewStore.getState().seedCustomRegionsFromDetected(
      { title: DETECTED_TITLE }, BOUNDS, DRAWING, { title: PINNED_TITLE },
    );

    const title = useReviewStore.getState().getRegionsFor(DRAWING).title;
    expect(title.xMin).toBeCloseTo(PINNED_TITLE.xMin, 6);
    expect(title.yMin).toBeCloseTo(PINNED_TITLE.yMin, 6);
  });

  it("an existing alignment is preserved for zones the template does NOT pin", () => {
    const myNotes = { xMin: 0.1, xMax: 0.2, yMin: 0.3, yMax: 0.4 };
    useReviewStore.setState({ customRegions: { [DRAWING]: { notes: myNotes } } });

    useReviewStore.getState().seedCustomRegionsFromDetected(
      { title: DETECTED_TITLE }, BOUNDS, DRAWING, { title: PINNED_TITLE },
    );

    // `notes` is not templatable, so the user's own box must survive untouched — and the
    // detector must NOT re-seed over it either.
    expect(useReviewStore.getState().getRegionsFor(DRAWING).notes).toEqual(myNotes);
  });

  it("records which zones are pinned so the overlay can stop marking them as guesses", () => {
    useReviewStore.getState().seedCustomRegionsFromDetected(
      { title: DETECTED_TITLE }, BOUNDS, DRAWING,
      { title: PINNED_TITLE, views: PINNED_TITLE },
    );

    expect(useReviewStore.getState().getPinnedZoneKeys(DRAWING).sort())
      .toEqual(["title", "views"]);
  });

  it("pinned keys are recorded even when seeding is skipped", () => {
    useReviewStore.setState({ customRegions: { [DRAWING]: { title: PINNED_TITLE } } });

    useReviewStore.getState().seedCustomRegionsFromDetected(
      { title: DETECTED_TITLE }, BOUNDS, DRAWING, { title: PINNED_TITLE },
    );

    expect(useReviewStore.getState().getPinnedZoneKeys(DRAWING)).toEqual(["title"]);
  });

  it("reset clears the pinned marks too", () => {
    useReviewStore.getState().seedCustomRegionsFromDetected(
      { title: DETECTED_TITLE }, BOUNDS, DRAWING, { title: PINNED_TITLE },
    );
    expect(useReviewStore.getState().getPinnedZoneKeys(DRAWING)).toEqual(["title"]);

    useReviewStore.getState().resetCustomRegions(DRAWING);

    // Leaving them set would label plain detector boxes as human-aligned.
    expect(useReviewStore.getState().getPinnedZoneKeys(DRAWING)).toEqual([]);
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

/**
 * Reshaping a zone (adding nodes to its outline) must survive the editor being re-opened and
 * must survive a round trip through the template.
 *
 * Two defects, both introduced by the reshape feature and both silent because an outline is
 * *additive* — a zone with no `points` is a perfectly valid rectangle, so dropping the field
 * degrades instead of failing:
 *
 *   1. `saveZonesAsTemplate` rebuilt each zone as a four-field literal, so every hand-drawn
 *      outline was flattened to its bounding box on save. Covered in TwoDWorkspace's tests.
 *   2. The template was stamped over the local regions on EVERY editor open, so a reshape
 *      the user had not saved was replaced by the template's rectangle — the nodes they
 *      placed simply disappeared. Covered here.
 */
describe("seedCustomRegionsFromDetected — a live edit outranks the template", () => {
  beforeEach(() => {
    reset();
    useReviewStore.setState({ userAlignedZoneKeys: {} });
  });

  const RESHAPED = {
    xMin: 0.1, xMax: 0.5, yMin: 0.1, yMax: 0.5,
    points: [
      { x: 0.1, y: 0.1 },
      { x: 0.5, y: 0.1 },
      { x: 0.5, y: 0.3 },
      { x: 0.3, y: 0.3 },
      { x: 0.3, y: 0.5 },
      { x: 0.1, y: 0.5 },
    ],
  };

  it("does not stamp the template over a zone the user reshaped this session", () => {
    // The user drags/reshapes: this is the only write path a user's own edit takes.
    useReviewStore.getState().updateCustomRegion(DRAWING, "title", RESHAPED);

    // The editor is re-opened, which re-seeds with the template still holding a rectangle.
    useReviewStore.getState().seedCustomRegionsFromDetected(
      { title: DETECTED_TITLE }, BOUNDS, DRAWING, { title: PINNED_TITLE },
    );

    const title = useReviewStore.getState().getRegionsFor(DRAWING).title;
    expect(title.points, "the reshaped outline must survive a re-open").toHaveLength(6);
    expect(title.xMin).toBeCloseTo(RESHAPED.xMin, 5);
  });

  it("still stamps the template over a zone the user has NOT touched", () => {
    useReviewStore.getState().updateCustomRegion(DRAWING, "notes", RESHAPED);

    useReviewStore.getState().seedCustomRegionsFromDetected(
      { title: DETECTED_TITLE }, BOUNDS, DRAWING, { title: PINNED_TITLE },
    );

    // `title` was never touched, so the template must still win — that rule exists because a
    // stale localStorage seed used to mask a pinned zone and make it look reverted.
    const title = useReviewStore.getState().getRegionsFor(DRAWING).title;
    expect(title.xMin).toBeCloseTo(PINNED_TITLE.xMin, 5);
    expect(title.points).toBeUndefined();
  });

  it("Reset clears the protection, so the template can reach the zone again", () => {
    useReviewStore.getState().updateCustomRegion(DRAWING, "title", RESHAPED);
    useReviewStore.getState().resetCustomRegions(DRAWING);

    useReviewStore.getState().seedCustomRegionsFromDetected(
      { title: DETECTED_TITLE }, BOUNDS, DRAWING, { title: PINNED_TITLE },
    );

    const title = useReviewStore.getState().getRegionsFor(DRAWING).title;
    expect(title.xMin, "Reset means discard my alignment, including its immunity")
      .toBeCloseTo(PINNED_TITLE.xMin, 5);
    expect(title.points).toBeUndefined();
  });

  it("the protection is per drawing, not global", () => {
    useReviewStore.getState().updateCustomRegion(DRAWING, "title", RESHAPED);

    useReviewStore.getState().seedCustomRegionsFromDetected(
      { title: DETECTED_TITLE }, BOUNDS, "drawing-2", { title: PINNED_TITLE },
    );

    // The other pane never had this zone touched, so it takes the template.
    expect(useReviewStore.getState().getRegionsFor("drawing-2").title.xMin)
      .toBeCloseTo(PINNED_TITLE.xMin, 5);
    // And the edited one is untouched.
    expect(useReviewStore.getState().getRegionsFor(DRAWING).title.points).toHaveLength(6);
  });
});

/**
 * The alignment record must survive a restart, or a hand-aligned zone "goes back to default"
 * every time the app is reopened.
 *
 * `customRegions` cannot answer "who placed this box" — the detector's seeds and the user's
 * drags are written to the same key and the same localStorage entry. Persisting the record of
 * which keys a *human* touched is what lets the template override one and not the other.
 */
describe("userAlignedZoneKeys — persistence across a reload", () => {
  beforeEach(() => {
    reset();
    useReviewStore.setState({ userAlignedZoneKeys: {} });
  });

  const MOVED = { xMin: 0.11, xMax: 0.22, yMin: 0.33, yMax: 0.44 };

  function simulateRestart() {
    // A fresh store, as after a page load: in-memory state is gone, localStorage is not.
    useReviewStore.setState({ customRegions: {}, userAlignedZoneKeys: {} });
    useReviewStore.getState().loadCustomRegions(DRAWING);
  }

  it("a hand-aligned zone still beats the template after a restart", () => {
    useReviewStore.getState().updateCustomRegion(DRAWING, "title", MOVED);

    simulateRestart();
    useReviewStore.getState().seedCustomRegionsFromDetected(
      { title: DETECTED_TITLE }, BOUNDS, DRAWING, { title: PINNED_TITLE },
    );

    const title = useReviewStore.getState().getRegionsFor(DRAWING).title;
    expect(title.xMin, "the user's box must survive a restart").toBeCloseTo(MOVED.xMin, 5);
  });

  it("a zone the user never touched still takes the template after a restart", () => {
    useReviewStore.getState().updateCustomRegion(DRAWING, "notes", MOVED);

    simulateRestart();
    useReviewStore.getState().seedCustomRegionsFromDetected(
      { title: DETECTED_TITLE }, BOUNDS, DRAWING, { title: PINNED_TITLE },
    );

    // This is the original bug the stamping exists to prevent: a stale local *seed* must not
    // mask a pinned template zone.
    expect(useReviewStore.getState().getRegionsFor(DRAWING).title.xMin)
      .toBeCloseTo(PINNED_TITLE.xMin, 5);
  });

  it("Reset clears the persisted record too, not just the in-memory one", () => {
    useReviewStore.getState().updateCustomRegion(DRAWING, "title", MOVED);
    useReviewStore.getState().resetCustomRegions(DRAWING);

    simulateRestart();
    useReviewStore.getState().seedCustomRegionsFromDetected(
      { title: DETECTED_TITLE }, BOUNDS, DRAWING, { title: PINNED_TITLE },
    );

    expect(useReviewStore.getState().getRegionsFor(DRAWING).title.xMin)
      .toBeCloseTo(PINNED_TITLE.xMin, 5);
  });

  it("an install with no record reads as 'nothing hand-aligned', so the template applies", () => {
    // Pre-existing regions with no sibling record — what every install has before this key.
    localStorage.setItem(
      `custom_regions_${DRAWING}`,
      JSON.stringify({ title: MOVED }),
    );
    simulateRestart();
    useReviewStore.getState().seedCustomRegionsFromDetected(
      { title: DETECTED_TITLE }, BOUNDS, DRAWING, { title: PINNED_TITLE },
    );

    expect(useReviewStore.getState().getRegionsFor(DRAWING).title.xMin)
      .toBeCloseTo(PINNED_TITLE.xMin, 5);
  });
});
