/**
 * The desktop app's version is declared three times and must agree.
 *
 * | declared in | consumed by |
 * | :-- | :-- |
 * | `src-tauri/tauri.conf.json` | the bundler — this is the number stamped on the .msi / .exe |
 * | `src-tauri/Cargo.toml` | the Rust crate, and Tauri's fallback when the config omits one |
 * | `package.json` | npm tooling, and what a human reads first |
 *
 * ## Why a mismatch matters more here than it looks
 *
 * The bundle version is what Windows uses to decide whether an installer is an UPGRADE or a
 * separate product. Ship two builds carrying the same version and the second does not cleanly
 * replace the first — you get two entries in Add/Remove Programs and two copies on disk, silently.
 * That is not hypothetical: `0.1.0` shipped twice during the prototype rollout before the version
 * was bumped, and the second install had to be preceded by a manual uninstall.
 *
 * The inverse — Cargo or package.json drifting away from the config — is quieter still. The
 * installer is stamped from `tauri.conf.json` alone, so the artifact says one thing while the
 * source of truth a developer happens to read says another, and nothing fails.
 *
 * Same treatment as `connectionStore.csp.test.ts` and `tests/test_user_token_dir.py`: where a
 * value cannot be shared across languages, pin the duplication with a test that parses each side.
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import { describe, expect, it } from "vitest";

const DESKTOP_ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");

const read = (...parts: string[]) => readFileSync(join(DESKTOP_ROOT, ...parts), "utf8");

function tauriConfVersion(): string {
  return JSON.parse(read("src-tauri", "tauri.conf.json")).version;
}

function packageJsonVersion(): string {
  return JSON.parse(read("package.json")).version;
}

function cargoVersion(): string {
  // The FIRST `version = "..."` after [package]. Cargo.toml carries other tables (and a
  // [lib] with its own name), so an unanchored search can pick up a dependency's pin.
  const toml = read("src-tauri", "Cargo.toml");
  const pkg = toml.slice(toml.indexOf("[package]"));
  const match = /^version\s*=\s*"([^"]+)"/m.exec(pkg);
  expect(match, "no version found under [package] in Cargo.toml").toBeTruthy();
  return match![1];
}

describe("the desktop app version", () => {
  it("is a plain semver triple, which is what the Windows bundler expects", () => {
    // A pre-release suffix is legal semver and NOT legal in an MSI ProductVersion; catching it
    // here beats catching it minutes into a release build.
    expect(tauriConfVersion()).toMatch(/^\d+\.\d+\.\d+$/);
  });

  it("agrees between tauri.conf.json, Cargo.toml and package.json", () => {
    const versions = {
      "tauri.conf.json": tauriConfVersion(),
      "Cargo.toml": cargoVersion(),
      "package.json": packageJsonVersion(),
    };

    // Asserted as an object so a failure names WHICH file disagrees and with what, rather than
    // reporting that two strings differ.
    expect(versions).toEqual({
      "tauri.conf.json": versions["tauri.conf.json"],
      "Cargo.toml": versions["tauri.conf.json"],
      "package.json": versions["tauri.conf.json"],
    });
  });
});
