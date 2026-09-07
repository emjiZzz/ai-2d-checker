/**
 * Tests for the zone-review gate.
 *
 * The gate decides whether the Comparison Results panel may appear. Its failure modes are
 * all silent — the panel simply shows or hides — so the rule is pinned here as a pure
 * function rather than through a component test that would have to mount flexlayout, canvas
 * refs and ResizeObserver.
 */
import { describe, expect, it } from "vitest";

import {
  isRoomSyncedWithDrawings,
  isZoneGateOpen,
  isZoneReviewConfirmed,
  isZoneReviewGrandfathered,
  zonePairKey,
  type ZoneGateRoom,
} from "./zoneGate";

const OLD = "6a66cab4fef0570aff55418c";
const NEW = "6a66cac6fef0570aff55439e";
const OTHER = "6a66c8c633f4f6780d76b519";

const room = (over: Partial<ZoneGateRoom> = {}): ZoneGateRoom => ({
  id: "room1",
  active_old_drawing_id: OLD,
  active_new_drawing_id: NEW,
  active_audit_session_id: null,
  physical_comparison_results: null,
  zones_confirmed_for: null,
  ...over,
});

describe("zonePairKey", () => {
  it("is null unless both drawings are present", () => {
    expect(zonePairKey(OLD, null)).toBeNull();
    expect(zonePairKey(null, NEW)).toBeNull();
    expect(zonePairKey(undefined, undefined)).toBeNull();
  });

  it("is a stable string when both are present", () => {
    expect(zonePairKey(OLD, NEW)).toBe(`${OLD}:${NEW}`);
  });

  it("is order-sensitive, so swapping which side is reference invalidates it", () => {
    expect(zonePairKey(OLD, NEW)).not.toBe(zonePairKey(NEW, OLD));
  });
});

describe("isZoneGateOpen", () => {
  const open = (over: Parameters<typeof isZoneGateOpen>[0]) => isZoneGateOpen(over);

  it("opens when the confirmed pair matches the loaded pair", () => {
    expect(
      open({
        oldDrawingId: OLD,
        newDrawingId: NEW,
        room: room({ zones_confirmed_for: `${OLD}:${NEW}` }),
        grandfathered: false,
      }),
    ).toBe(true);
  });

  it("stays shut when the confirmation is for a DIFFERENT pair", () => {
    // The drawing-swap case: zones aligned against one sheet say nothing about another.
    expect(
      open({
        oldDrawingId: OLD,
        newDrawingId: OTHER,
        room: room({ zones_confirmed_for: `${OLD}:${NEW}` }),
        grandfathered: false,
      }),
    ).toBe(false);
  });

  it("stays shut with no confirmation at all", () => {
    expect(
      open({ oldDrawingId: OLD, newDrawingId: NEW, room: room(), grandfathered: false }),
    ).toBe(false);
  });

  it("stays shut with only one drawing, even if grandfathered", () => {
    // Both drawings are required regardless: the panel has nothing to compare.
    expect(
      open({ oldDrawingId: OLD, newDrawingId: null, room: room(), grandfathered: true }),
    ).toBe(false);
  });

  it("opens for a grandfathered room with no confirmation", () => {
    expect(
      open({ oldDrawingId: OLD, newDrawingId: NEW, room: room(), grandfathered: true }),
    ).toBe(true);
  });

  it("opens optimistically on the locally confirmed pair before the PATCH lands", () => {
    expect(
      open({
        oldDrawingId: OLD,
        newDrawingId: NEW,
        room: room(),
        grandfathered: false,
        locallyConfirmedPair: `${OLD}:${NEW}`,
      }),
    ).toBe(true);
  });

  it("ignores a stale optimistic value from a previous pair", () => {
    expect(
      open({
        oldDrawingId: OLD,
        newDrawingId: OTHER,
        room: room(),
        grandfathered: false,
        locallyConfirmedPair: `${OLD}:${NEW}`,
      }),
    ).toBe(false);
  });

  it("stays shut when there is no room yet", () => {
    expect(
      open({ oldDrawingId: OLD, newDrawingId: NEW, room: null, grandfathered: false }),
    ).toBe(false);
  });
});

describe("isZoneReviewConfirmed", () => {
  it("treats a legacy room with the field undefined as unconfirmed", () => {
    const legacy = room();
    delete (legacy as unknown as Record<string, unknown>).zones_confirmed_for;
    expect(isZoneReviewConfirmed(legacy, OLD, NEW)).toBe(false);
  });
});

describe("isZoneReviewGrandfathered", () => {
  it("is true when the room holds physical comparison results", () => {
    expect(isZoneReviewGrandfathered(room({ physical_comparison_results: { a: 1 } }))).toBe(true);
  });

  it("is true when the room has an audit session but no physical results", () => {
    // Rooms restored through the audit-session branch populate violations and a compliance
    // score without necessarily writing physical_comparison_results. Checking only the
    // latter would push a room that plainly has results back through the gate.
    expect(isZoneReviewGrandfathered(room({ active_audit_session_id: "sess1" }))).toBe(true);
  });

  it("is false for a fresh room", () => {
    expect(isZoneReviewGrandfathered(room())).toBe(false);
  });

  it("is false for no room", () => {
    expect(isZoneReviewGrandfathered(null)).toBe(false);
  });
});

describe("isRoomSyncedWithDrawings", () => {
  it("is true when the room describes the loaded drawings", () => {
    expect(isRoomSyncedWithDrawings(room(), OLD, NEW)).toBe(true);
  });

  it("is false when activeRoom is still the PREVIOUS room", () => {
    // openRoom pushes drawings into the workspace well before it sets activeRoom. In that
    // window the new drawings are live against the old room; acting then would flash the
    // editor open over a room that is already confirmed.
    expect(isRoomSyncedWithDrawings(room(), OTHER, NEW)).toBe(false);
  });

  it("is false before both drawings are loaded", () => {
    expect(isRoomSyncedWithDrawings(room(), OLD, null)).toBe(false);
  });

  it("is false with no room", () => {
    expect(isRoomSyncedWithDrawings(null, OLD, NEW)).toBe(false);
  });
});
