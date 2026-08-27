#!/usr/bin/env node
/**
 * Fail the build if `apps/desktop/dist` is not the mode the caller asked for.
 *
 *   node tools/scripts/assert-build-mode.mjs prototype
 *   node tools/scripts/assert-build-mode.mjs full
 *
 * ## Why this exists
 *
 * `VITE_PROTOTYPE_MODE` is inlined by Vite and folds to a constant, so a prototype build and a
 * full build are byte-different but not *distinguishable* — nothing in the output said which one
 * it was. And the two ways of asking for prototype do not survive the same distance:
 *
 * - `vite build --mode prototype` loads `.env.prototype`, and is what `pnpm build:prototype` runs;
 * - `VITE_PROTOTYPE_MODE=true` in the process environment is what `build_prototype.ps1` exports.
 *
 * `tauri.conf.json` sets `beforeBuildCommand: "pnpm build"` — the plain script. So `tauri build`
 * re-runs Vite in production mode and **overwrites the `dist/` that `build:prototype` just
 * produced**. The installer came out as a prototype only because the surrounding PowerShell had
 * also exported the process variable; the `--mode prototype` step was doing nothing. Run the two
 * commands by hand in a shell without that variable — which is what the README's
 * `pnpm build:prototype` invites — and you ship a full build with a login screen, silently.
 *
 * The stamp comes from `buildModeStamp` in `apps/desktop/vite.config.ts`, written from the
 * resolved env at `closeBundle`, i.e. from whichever route actually won.
 *
 * ⚠ Assert AFTER `tauri build`, not before it. Asserting on the output of `build:prototype` checks
 * a directory that is about to be overwritten, which is the exact mistake this guards against.
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const repoRoot = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const stampPath = join(repoRoot, "apps", "desktop", "dist", "build-mode.json");

const arg = (process.argv[2] ?? "").toLowerCase();
if (arg !== "prototype" && arg !== "full") {
  console.error(`usage: assert-build-mode.mjs <prototype|full>   (got: ${process.argv[2] ?? "nothing"})`);
  process.exit(2);
}
const wantPrototype = arg === "prototype";

let stamp;
try {
  stamp = JSON.parse(readFileSync(stampPath, "utf8"));
} catch (err) {
  console.error(`\n  FAIL  no build-mode stamp at ${stampPath}`);
  console.error(`        ${err.message}`);
  console.error("        A build older than the buildModeStamp plugin, or dist/ was never built.");
  console.error("        Rebuild; do not assume the mode.\n");
  process.exit(1);
}

if (typeof stamp.prototype !== "boolean") {
  console.error(`\n  FAIL  stamp at ${stampPath} has no boolean "prototype" field.\n`);
  process.exit(1);
}

if (stamp.prototype !== wantPrototype) {
  const got = stamp.prototype ? "PROTOTYPE" : "FULL";
  console.error(`\n  FAIL  asked for ${arg.toUpperCase()}, dist/ is ${got}  (built ${stamp.builtAt})`);
  console.error("");
  console.error("        `tauri build` re-runs `pnpm build` from tauri.conf.json, which overwrites");
  console.error("        dist/. Only a VITE_PROTOTYPE_MODE process variable survives that; a");
  console.error("        `--mode prototype` flag does not. Set it and rebuild:");
  console.error("");
  console.error("            $env:VITE_PROTOTYPE_MODE = \"true\"   # PowerShell");
  console.error("            pnpm --filter desktop tauri build");
  console.error("");
  process.exit(1);
}

console.log(`  OK    dist/ is a ${wantPrototype ? "PROTOTYPE" : "FULL"} build (built ${stamp.builtAt})`);
