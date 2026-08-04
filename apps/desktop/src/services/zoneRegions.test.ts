/**
 * Tests for the zone-overlay confidence helpers
 * (docs/zone-bbox-overlay-implementation-plan.md, Phase 2).
 *
 * These two predicates are what stands between the canvas and rendering geometry that
 * carries no information. The backend test suite pins the strings they match against
 * (tests/test_zone_overlay_endpoint.py); these pin the behavior keyed off them.
 */
import { describe, expect, it } from "vitest";

import {
  NO_SHEET_BOUNDS,
  ZONE_KEYS,
  countFallbackZones,
  isPlaceholderOnly,
  type DrawingZonesResponse,
  type ZoneBBox,
} from "./drawingsApi";

const box = (confidence: string): ZoneBBox => ({
  xmin: 0,
  ymin: 0,
  xmax: 100,
  ymax: 100,
  confidence,
});

/** A response where every zone shares one confidence value. */
const uniform = (confidence: string): DrawingZonesResponse =>
  ({
    drawing_id: "d1",
    render_bounds: [0, 0, 100, 100],
    ...Object.fromEntries(ZONE_KEYS.map((k) => [k, box(confidence)])),
  }) as DrawingZonesResponse;

describe("isPlaceholderOnly", () => {
  it("is true when zone detection had no sheet bounds", () => {
    expect(isPlaceholderOnly(uniform(NO_SHEET_BOUNDS))).toBe(true);
  });

  it("is false for a healthy content-aware response", () => {
    expect(isPlaceholderOnly(uniform("content_aware"))).toBe(false);
  });

  it("is false for ordinary percentage fallback", () => {
    // A percentage-grid box is a guess, but a guess about *this* drawing — it still
    // carries relative structure and must stay drawable. Conflating it with the
    // no-bounds placeholder would blank the overlay on most real drawings.
    expect(isPlaceholderOnly(uniform("percentage_fallback"))).toBe(false);
  });

  it("is false for null/undefined rather than throwing", () => {
    expect(isPlaceholderOnly(null)).toBe(false);
    expect(isPlaceholderOnly(undefined)).toBe(false);
  });

  it("trips on a single no-bounds zone, since the backend sets it for all seven at once", () => {
    const zones = uniform("content_aware");
    zones.bom = box(NO_SHEET_BOUNDS);
    expect(isPlaceholderOnly(zones)).toBe(true);
  });
});

describe("countFallbackZones", () => {
  it("counts zero when every zone is content-aware", () => {
    expect(countFallbackZones(uniform("content_aware"))).toBe(0);
  });

  it("counts every zone when they all fell back", () => {
    // `uniform` assigns a box to every ZONE_KEY, so the count tracks the key list rather
    // than a fixed number — shim was added as an eighth (optional) zone.
    expect(countFallbackZones(uniform("percentage_fallback"))).toBe(ZONE_KEYS.length);
  });

  it("counts only the fallback zones in a mixed response", () => {
    const zones = uniform("content_aware");
    zones.notes = box("percentage_fallback");
    zones.iso = box("percentage_fallback");
    zones.title_upper_left = box("percentage_fallback");
    expect(countFallbackZones(zones)).toBe(3);
  });

  it("treats an unknown confidence string as a fallback, not as trustworthy", () => {
    // Defaulting an unrecognized value to "measured" would silently present a box as
    // reliable. Erring toward the dashed style is the safe direction for a debug view.
    const zones = uniform("content_aware");
    zones.title = box("unknown");
    expect(countFallbackZones(zones)).toBe(1);
  });

  it("ignores absent zones instead of counting them", () => {
    const zones = uniform("content_aware");
    zones.tolerance = null;
    expect(countFallbackZones(zones)).toBe(0);
  });

  it("returns 0 for null/undefined rather than throwing", () => {
    expect(countFallbackZones(null)).toBe(0);
    expect(countFallbackZones(undefined)).toBe(0);
  });
});
