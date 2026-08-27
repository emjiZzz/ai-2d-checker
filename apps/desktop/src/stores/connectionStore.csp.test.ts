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
 * **Port axis, 2026-08-27:** any port on the two loopback hosts, because `SIDECAR_PORT=0` is a
 * documented mode and no build-time constant can know the result.
 *
 * **Host axis, same day:** exactly ONE host — `192.168.200.105`, the shared LAN backend the
 * prototype is deployed against. Not a subnet, not a wildcard. That was a deliberate decision
 * taken together with `ALLOWED_HOSTS` and the CORS origins in `main.py` and a shared `API_TOKEN`,
 * because a per-machine backend cannot give 21 engineers one shared drawing corpus.
 *
 * The last test pins the distinction, because "make the CSP less annoying" and "make the CSP not
 * a boundary" look identical in a diff — `192.168.200.106` must still fail. The backend's own host
 * guard remains an exact match and still requires the bearer token; this CSP is one of four layers
 * that had to move together, not a lock that was simply removed.
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

  it("permits the LAN server the prototype is deployed against", () => {
    /**
     * The host axis was opened on 2026-08-27, for ONE host: the shared backend at
     * 192.168.200.105. That was a deliberate decision taken with the CORS origins in `main.py`,
     * the `ALLOWED_HOSTS` guard and a shared `API_TOKEN` — not a config tweak, which is why the
     * test below still exists.
     *
     * Port-wildcarded so a `SIDECAR_PORT` change on the server does not need a client rebuild.
     */
    for (const url of ["http://192.168.200.105:8080", "http://192.168.200.105:9000"]) {
      expect(allows(url), `connect-src blocks the LAN server at ${url}`).toBe(true);
    }
  });

  it("still refuses every OTHER non-loopback host", () => {
    /**
     * The half that keeps the widening honest. One named server was added — not a subnet, not a
     * wildcard. `192.168.1.50` and `192.168.200.106` are the interesting cases: both look like
     * plausible LAN addresses and both must fail, which is what proves this is a host allowlist
     * rather than "anything on a private network".
     */
    for (const url of [
      "http://192.168.1.50:8080",
      "http://192.168.200.106:8080",
      "http://backend.internal:8080",
      "https://evil.example.com",
      "http://0.0.0.0:8080",
      "http://localhost.attacker.com:8080",
    ]) {
      expect(allows(url), `connect-src unexpectedly permits ${url}`).toBe(false);
    }
  });
});
