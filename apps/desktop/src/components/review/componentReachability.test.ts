import { describe, it, expect } from "vitest";
import { readFileSync, existsSync } from "node:fs";
import { dirname, resolve, join } from "node:path";
import { fileURLToPath } from "node:url";

/**
 * A component that nothing renders is not a feature, however green its own tests are.
 *
 * ## Why this file exists
 *
 * `ReviewControls` and `SummaryPanel` were first wired into `AuditConsole.tsx` — a component with
 * **zero importers anywhere in the app**. Their unit tests passed, `tsc` passed, the suite was
 * green, and none of it was reachable by a user. The mistake is the same one recorded in
 * `docs/vault/06 - .../Gotcha - A Tested Endpoint That Nothing Ever Called.md`, made one layer up:
 * a test proves a thing *works*; nothing there proved it was *reachable*.
 *
 * So this walks the real import graph from the app entry point and asserts the components a user
 * is supposed to see are actually in it. It is deliberately crude — a regex over import
 * specifiers, not a bundler — because the property is coarse and a precise tool would be a
 * dependency nobody wants for this.
 */

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = resolve(HERE, "../..");
const ENTRY = join(SRC, "App.tsx");

const EXTENSIONS = [".tsx", ".ts", "/index.tsx", "/index.ts"];

function resolveImport(fromFile: string, spec: string): string | null {
  if (!spec.startsWith(".")) return null; // package import, not ours
  const base = resolve(dirname(fromFile), spec);
  for (const ext of ["", ...EXTENSIONS]) {
    const candidate = base + ext;
    if (existsSync(candidate) && !candidate.endsWith("/")) {
      try {
        readFileSync(candidate, "utf-8");
        return candidate;
      } catch {
        /* a directory, keep looking */
      }
    }
  }
  return null;
}

/** Every module transitively imported from App.tsx. */
function reachableModules(): Set<string> {
  const seen = new Set<string>();
  const queue = [ENTRY];

  while (queue.length) {
    const file = queue.pop()!;
    if (seen.has(file)) continue;
    seen.add(file);

    let source: string;
    try {
      source = readFileSync(file, "utf-8");
    } catch {
      continue;
    }

    // Static imports and lazy/dynamic imports alike.
    const specs = [
      ...source.matchAll(/(?:from|import)\s*\(?\s*["']([^"']+)["']/g),
    ].map((m) => m[1]);

    for (const spec of specs) {
      const target = resolveImport(file, spec);
      if (target) queue.push(target);
    }
  }
  return seen;
}

describe("component reachability from the app entry point", () => {
  const reachable = reachableModules();

  it("finds a plausible graph at all (guards the walker itself)", () => {
    // If the resolver silently returned nothing, every assertion below would fail for the wrong
    // reason and every future one would pass vacuously once inverted. Pin the floor.
    expect(reachable.size).toBeGreaterThan(20);
    expect([...reachable].some((f) => f.endsWith("ChecklistPanel.tsx"))).toBe(true);
  });

  it.each([
    ["ReviewControls.tsx", "the supervisor verdict controls that fill the lessons corpus"],
    ["SummaryPanel.tsx", "the ADR-010 grounded summary"],
    ["CorrectionControls.tsx", "the existing per-finding correction verbs"],
  ])("%s is reachable from App.tsx — %s", (fileName) => {
    const found = [...reachable].some((f) => f.endsWith(fileName));
    expect(
      found,
      `${fileName} is not imported by anything reachable from App.tsx. Its own tests can be ` +
        `green while no user can see it — this is exactly how ReviewControls first shipped into ` +
        `the unmounted AuditConsole.tsx.`
    ).toBe(true);
  });

  it("AuditConsole.tsx is still unmounted, and this test is the record of that", () => {
    // Not a requirement that it stay dead — a statement of current fact, so that mounting it
    // becomes a deliberate act that updates this test rather than a silent revival.
    const mounted = [...reachable].some((f) => f.endsWith("AuditConsole.tsx"));
    expect(
      mounted,
      "AuditConsole.tsx is now reachable. That is fine, but it was dead code carrying a stale " +
        "copy of the audit UI — check it against the live ChecklistPanel path before trusting it."
    ).toBe(false);
  });
});
