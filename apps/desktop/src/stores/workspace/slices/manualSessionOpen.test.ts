import { describe, it, expect } from 'vitest';
import { shouldOpenManualSession } from './createManualCheckSlice';

/**
 * When the workspace opens a manual-check session.
 *
 * Reported twice, the same way both times: "the panel is empty after every app refresh". The
 * first cause was on the server — a non-idempotent open minted a fresh session per reload. This
 * is the second, and it is a client-side mirror of it: the effect asked whether a session was
 * open rather than whether one was open FOR THE PAIR ON SCREEN.
 *
 * Both failures look identical to the engineer, and neither raises anything. The panel simply
 * says nothing has been recorded — about the one screen whose whole job is to show that it has.
 */

const PAIR_A = 'room1:ref1:rev1';
const PAIR_B = 'room1:ref2:rev2';

describe('shouldOpenManualSession', () => {
  it('opens when nothing is open yet', () => {
    expect(shouldOpenManualSession(true, null, PAIR_A)).toBe(true);
  });

  it('does not reopen the pair that is already open', () => {
    // The guard that has to survive: this effect runs on every render of the workspace, and an
    // open per render would create a session per frame on the old server and hammer the new one.
    expect(shouldOpenManualSession(true, PAIR_A, PAIR_A)).toBe(false);
  });

  it('REOPENS when the drawings changed under an open session', () => {
    // The defect. On a reload the workspace restores its drawings from IndexedDB and `openRoom`
    // then replaces them with the server's; a session opened in that window belongs to the
    // previous pair. Asking only "is a session open" answered yes, so the correction never ran
    // and the panel listed a pair with no markings in it.
    expect(shouldOpenManualSession(true, PAIR_A, PAIR_B)).toBe(true);
  });

  it('waits while the workspace is still assembling', () => {
    // Both drawings have to be present before a pair means anything. Opening against a half-
    // filled workspace is what produces the stale session in the first place.
    expect(shouldOpenManualSession(true, null, null)).toBe(false);
    expect(shouldOpenManualSession(true, PAIR_A, null)).toBe(false);
  });

  it('does nothing in an AI room', () => {
    // A session here would attach a ground-truth record to a room whose findings came from the
    // engine, which is the one thing the independence rule exists to prevent.
    expect(shouldOpenManualSession(false, null, PAIR_A)).toBe(false);
  });

  it('retries after a failed open, because a failure leaves no pair recorded', () => {
    // `startManualSession` clears `manualSessionPair` when it fails, so this stays true and the
    // panel's Retry has something to do. It is deliberately NOT an automatic loop: the effect's
    // dependencies do not change on failure, so nothing re-fires at a server that just refused.
    expect(shouldOpenManualSession(true, null, PAIR_A)).toBe(true);
  });
});
