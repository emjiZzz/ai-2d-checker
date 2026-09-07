// Phase 0.1 test runner smoke test
// This file's sole purpose is to confirm vitest picks up *.test.ts files.
// Delete after Phase 0.2 tests are confirmed working.
import { describe, it, expect } from 'vitest';

describe('smoke', () => {
  it('runner is wired up', () => {
    expect(1 + 1).toBe(2);
  });
});
