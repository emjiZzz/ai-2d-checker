/**
 * The backend address the app uses must be one the webview's CSP allows.
 *
 * ## Why this needs a test rather than a comment
 *
 * Three places declare where the backend lives, in three languages, with no shared type:
 *
 * | declared in | what it says |
 * | :-- | :-- |
 * | `src-tauri/tauri.conf.json` | `connect-src` — what the webview may reach |
 * | `stores/connectionStore.ts` | `DEFAULT_BACKEND_URL` — where the app looks |
 * | `.env` `SIDECAR_PORT` (+ `start_desktop.ps1`, `config.py`) | where the backend listens |
 *
 * They were three independent literals that happened to agree on `8080`. When they disagree the
 * failure is invisible in the worst way: **CSP is enforced by the webview, so the request never
 * leaves the app.** No network error, no backend log, no entry in the dev tools network tab worth
 * reading — just a UI stuck on "Connection Lost" against an address that looks correct.
 *
 * That is not hypothetical. `.env` documents `SIDECAR_PORT=0` for dynamic allocation and
 * `services/backend/config.py` honours it, so the backend can legitimately answer on a port
 * nothing knows at build time — while the CSP pinned `:8080` exactly. In that configuration the
 * app could never reach its own backend, and the offline overlay's address field could not fix it
 * either, because a corrected port was blocked by the same CSP.
 *
 * `tests/test_host_header_guard.py` already asserts the backend's own host guard passes a
 * non-default `SIDECAR_PORT`. The CSP was the one layer that disagreed.
 *
 * ## What was widened, and what deliberately was not
 *
 * `connect-src` now allows any PORT on the two loopback hosts (`http://127.0.0.1:*`,
 * `http://localhost:*`, plus the `ws://` forms) — not any host. The last test below pins that
 * distinction, because "make the CSP less annoying" and "make the CSP not a boundary" look
 * identical in a diff. The backend still refuses any request whose Host is not exactly
 * `localhost`, `127.0.0.1` or `::1`, and still requires the bearer token.
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import { describe, expect, it } from "vitest";

import { DEFAULT_BACKEND_URL } from "./connectionStore";

const TAURI_CONF = join(
  dirname(fileURLToPath(import.meta.url)),
  "..",
  "..",
  "src-tauri",
  "tauri.conf.json",
);

/** The `connect-src` sources, as written in the shipped CSP. */
function connectSrc(): string[] {
  const conf = JSON.parse(readFileSync(TAURI_CONF, "utf8"));
  const csp: string = conf?.app?.security?.csp ?? "";
  expect(csp, "tauri.conf.json declares no CSP").not.toBe("");

  const directive = csp
    .split(";")
    .map((d) => d.trim())
    .find((d) => d.startsWith("connect-src"));
  expect(directive, "CSP has no connect-src directive").toBeTruthy();

  return directive!.split(/\s+/).slice(1).filter(Boolean);
}

/**
 * Whether a CSP host-source permits a URL.
 *
 * Only the subset this CSP actually uses: `scheme://host` with an optional port that may be `*`.
 * Keyword sources such as `'self'` are not resolved — a URL matching only `'self'` is reported as
 * not allowed, which is correct here, since the app is served from `tauri://localhost` and never
 * from the backend's origin.
 */
function permits(source: string, target: string): boolean {
  if (source.startsWith("'")) return false;

  const m = /^([a-z]+):\/\/([^/:]+)(?::(\*|\d+))?$/.exec(source);
  if (!m) return false;
  const [, scheme, host, port] = m;

  const url = new URL(target);
  if (url.protocol !== `${scheme}:`) return false;
  if (url.hostname !== host) return false;
  if (port === undefined) return true;
  if (port === "*") return true;
  return (url.port || (url.protocol === "https:" ? "443" : "80")) === port;
}

const allows = (target: string) => connectSrc().some((s) => permits(s, target));

describe("the shipped CSP and the app's backend address agree", () => {
  it("permits DEFAULT_BACKEND_URL", () => {
    // The regression this file exists for: change the default without touching the CSP and the
    // app cannot reach its backend, with no error anywhere that names the cause.
    expect(allows(DEFAULT_BACKEND_URL), `connect-src blocks ${DEFAULT_BACKEND_URL}`).toBe(true);
  });

  it("permits a dynamically allocated port on both loopback spellings", () => {
    // `SIDECAR_PORT=0` is a documented mode, so no build-time constant can know the port.
    for (const url of [
      "http://127.0.0.1:49213",
      "http://localhost:49213",
      "http://127.0.0.1:9001",
      "http://localhost:8080",
    ]) {
      expect(allows(url), `connect-src blocks ${url}`).toBe(true);
    }
  });

  it("permits the websocket forms on both loopback spellings", () => {
    for (const url of ["ws://127.0.0.1:8080", "ws://localhost:49213"]) {
      expect(allows(url), `connect-src blocks ${url}`).toBe(true);
    }
  });

  it("still refuses non-loopback hosts", () => {
    /**
     * The half that keeps the widening honest. Only the PORT axis was opened; the host axis was
     * not. A centralized backend on another machine is intentionally NOT reachable — that would
     * need this CSP, the CORS origins in `main.py`, the `ALLOWED_HOST_NAMES` guard and the
     * file-based local token model all changed together, which is a decision, not a config tweak.
     */
    for (const url of [
      "http://192.168.1.50:8080",
      "http://backend.internal:8080",
      "https://evil.example.com",
      "http://0.0.0.0:8080",
      "http://localhost.attacker.com:8080",
    ]) {
      expect(allows(url), `connect-src unexpectedly permits ${url}`).toBe(false);
    }
  });
});
