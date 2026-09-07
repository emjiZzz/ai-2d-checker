/**
 * Tests for prototype-mode detection.
 *
 * Prototype mode is the configuration this project actually ships to evaluators, and until now it
 * had zero test coverage: no test referenced `isPrototypeMode` or `VITE_PROTOTYPE_MODE`, and
 * vitest runs with the flag unset, so all 633 tests exercised the non-prototype branch of every
 * gate. The shipped build was the untested one.
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import { afterEach, describe, expect, it, vi } from "vitest";

import { isPrototypeMode } from "./features";

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("isPrototypeMode", () => {
  it("is false when the flag is absent — the default for dev, CI and every other test file", () => {
    expect(isPrototypeMode()).toBe(false);
  });

  it('is true for the string "true", which is how Vite delivers it', () => {
    // Both carriers (`.env.prototype` and a VITE_PROTOTYPE_MODE process variable) arrive as a
    // string; nothing in the build ever hands this a boolean.
    vi.stubEnv("VITE_PROTOTYPE_MODE", "true");
    expect(isPrototypeMode()).toBe(true);
  });

  it("is false for every near-miss spelling rather than truthy-testing the value", () => {
    for (const value of ["false", "1", "yes", "TRUE", "True", "", " true"]) {
      vi.stubEnv("VITE_PROTOTYPE_MODE", value);
      expect(isPrototypeMode(), `value ${JSON.stringify(value)}`).toBe(false);
    }
  });
});

describe("the source shape that makes dead-code elimination work", () => {
  /**
   * This asserts on the FILE, not on behaviour, and that is deliberate — the property it
   * protects is invisible to every behavioural test.
   *
   * Vite substitutes the literal for each `import.meta.env.VITE_PROTOTYPE_MODE` it sees, so
   * writing the comparison inline makes the whole function fold to `() => !0`, which esbuild then
   * inlines into all 8 gates and drops the untaken branches. Hoisting the lookup into a local
   * `const` stops that propagation. The app behaves identically either way, so the only symptom is
   * a prototype build that ships the login screen and the AI-comparison UI it can never reach.
   *
   * Measured on this tree: with the local, "AI Comparison" / "Stage 2 Auditor" /
   * "Engineering Copilot" all appear in a PROTOTYPE `dist/assets/*.js`. Without it, a prototype
   * bundle is 147,729 bytes smaller than a full one and drops "START COMPARISON",
   * "AI Comparison" and the "Restoring session" login path entirely.
   */
  const source = readFileSync(
    join(dirname(fileURLToPath(import.meta.url)), "features.ts"),
    "utf8",
  );
  const body = source.slice(source.indexOf("export const isPrototypeMode"));

  it("names import.meta.env directly in the expression, twice", () => {
    const direct = body.match(/import\.meta\.env\.VITE_PROTOTYPE_MODE/g) ?? [];
    expect(direct).toHaveLength(2);
  });

  it("does not hoist the flag into a local first", () => {
    expect(body).not.toMatch(/(?:const|let|var)\s+\w+\s*=\s*import\.meta\.env/);
  });
});
