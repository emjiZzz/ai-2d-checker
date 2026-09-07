---
title: Gotcha - The Installed App Bound to a Storage Directory at the Drive Root
type: gotcha
tags: [gotcha, desktop, tauri, installer, auth, storage, prototype]
status: resolved
date: 2026-08-28
---

# 🔥 Gotcha — The Installed App Read Its API Token From `C:\storage`

## ⚠️ The Problem

The installed prototype build (0.1.8) showed the onboarding tour's step 1 failing with:

> Could not create the Tutorial Room: Access Denied: Invalid security API Token.

The backend was running, reachable, and healthy. `/health` returned 200, so the app reported
itself **CONNECTED** while every authenticated request answered 401.

## 🔍 Root Cause

`security::find_storage_root()` (`apps/desktop/src-tauri/src/security/mod.rs`) accepts **any**
directory named `storage` found by ascending up to six parents from the working directory and
from the executable. An app installed to `%LOCALAPPDATA%\KMTI Checker\` sits five parents below
`C:\`, so `C:\storage` is inside that budget — and `C:\storage` **exists on these machines**,
created by the frozen backend when it was launched from `C:\` (the incident whose backend half
`27fb0ab` fixed by anchoring a relative `STORAGE_ROOT` to the app root, leaving the client half).

So the app read `C:\storage\secure\.api-token`: a token published there the previous day, which
the running backend had never issued.

## 💥 Why it is nasty

**A wrong token fails differently from a missing one.** The key is derived from machine and user
identity, not from provenance, so a stale token decrypts perfectly — it is a plausible credential,
not a corrupt file. Nothing on either side can tell the difference until a request comes back 401.

Three separate mechanisms then failed to surface it:

- **`/health` needs no token**, so the connection indicator stayed green. This is the same
  presentation as [[Gotcha - The Prototype Build Was Prototype By Accident]] §6 and as the
  original per-user-token fix; it is now the third time this exact disguise has been paid for.
- **The frontend's 401 self-heal made it look intermittent rather than broken.** `parseOrThrow`
  clears `apiToken` on 401 and `checkHealth` re-reads it on the next 5-second poll — a design that
  recovers from a *rotated* token and cannot recover from a *wrong file*. The app log shows the
  loop running every five seconds indefinitely.
- **The per-user branch carried a comment calling itself "the only branch an INSTALLED build can
  reach".** It was false for as long as any directory named `storage` sat above the install
  location, and a comment cannot notice that. The branch was never reached in the shipped build.

## 🧭 How it was found

By its side effects, not by reading the code. `logging::init_logger` puts the app log under the
same resolved root, so `C:\storage\logs\app\app.log` existing — and being written *today* — is
what proved which root the installed binary had bound to. The log lines it contained
(`Successfully loaded secure API token in-memory.`) also dated the running binary to the committed
`get_api_token`, not the working tree's.

Confirmed by decrypting each candidate token and putting it against the live backend, printing
only the HTTP status:

| Candidate | Result |
| :--- | :--- |
| `C:\storage\secure\.api-token` | decrypts, **401** |
| `%LOCALAPPDATA%\kmti-2d-checker\secure\.api-token` (the published mirror) | decrypts, **200** |
| `%LOCALAPPDATA%\KMTI Checker\server\storage\secure\.api-token` | decrypts, 200 |
| `<repo>/storage/secure/.api-token` | decrypts, 200 |

**Three of four candidates worked.** Reading "a token" was never the problem; reading the *right*
one was, and only one of them was wrong.

## ✅ The Fix

`looks_like_checkout(root)` — a `storage` directory is this project's only when a project marker
sits beside it (`pyproject.toml`, or `services/backend` **and** `apps/desktop` together). Applied
to all three discovery branches: the ascent from the working directory, the ascent from the
executable, and the relative fallbacks, **which are that ascent unrolled** — gating two of the
three leaves the defect intact.

The explicit `STORAGE_ROOT` environment override is deliberately **not** gated: it names a
directory rather than discovering one, and requiring a marker would break the override for anyone
pointing at a storage root outside a checkout, which is its entire purpose.

Two consequences worth knowing:

- The per-user branch is now genuinely reachable, as its comment always claimed. It also
  **creates** the directory when missing, so an app opened before its first backend start has
  somewhere to write the log that says so.
- `get_api_token` reads **every** candidate, newest file first, rather than the first one found.
  The mirror is rewritten on every backend startup while the storage-root copy is written once at
  generation, and only one backend can hold the port — so "most recently published" is the closest
  available proxy for "the backend that is actually answering". ⚠ **It is a proxy, not proof.**
  Nothing validates a token against the backend before returning it.

## 🔴 The second defect, which the first one was hiding

Renaming the stray directory changed the error rather than clearing it:

> Could not create the Tutorial Room: Access Denied: **Missing Authorization Header.**

A different message, naming a different subsystem, for the same underlying problem — and it is
the self-heal that produced it.

`parseOrThrow` cleared the token on a 401 (`setState({ apiToken: null })`) and relied on
`checkHealth`'s 5-second poll to re-read it. But the **synchronous** `buildHeaders()` — 71 call
sites, `createRoom` among them — omits the `Authorization` header entirely when the token is null
rather than waiting for one. So every request issued between the clear and the next successful
read went out **unauthenticated**. Clicking the tour button twice inside five seconds is enough.

**A hole in the credential is not a safer state than a stale credential.** `refreshApiToken` now
replaces the token in place and never nulls it: the worst case is one more request carrying the
token already known to be wrong, failing exactly the way it already failed, while the read that
fixes it is in flight. `fetchApiToken` coalesces concurrent reads, because a failing screen issues
several requests at once and each 401 now asks for a refresh.

⚠ **The asymmetric variant is still open**: `buildHeaders()` (sync, 71 sites) silently drops the
header, while `buildHeadersAsync()` (13 sites) awaits `resolveApiToken()` and does not. The fix
above closes the window that was reachable in practice; converting the remaining call sites is a
separate, mechanical change.

⚠ **Two errors, one cause, and the second one reads like progress.** "Missing Authorization
Header" looks like a *client wiring* bug — a header dropped somewhere in the fetch layer — and
sends the next hour into `buildHeaders`. It was a symptom of the token file being wrong, one layer
further out. When an error message changes after a fix, check whether the cause did.

## 🧪 Guarded by

- `apps/desktop/src-tauri/src/security/mod.rs` — `cargo test --lib`, 9 tests. Two reproduce the
  shipped layout: an install five directories deep with a stray `storage` above it must not
  resolve to it, and a real checkout must still resolve to its own.
- `tests/test_storage_root_resolution.py` — parses the Rust and fails if **any** discovery branch
  accepts an `is_dir()` without a marker check. CI runs pytest and does **not** run `cargo test`,
  so this is the one that gates a merge.
- `apps/desktop/src/stores/connectionStore.token.test.ts` — the token cache is never null while the
  app runs, and `buildHeaders()` omitting the header when it is null is pinned as the *reason*,
  so the fix cannot be reverted on the grounds that "buildHeaders handles it".
- `apps/desktop/src/services/fetchUtils.test.ts` and
  `apps/desktop/src/components/ui/InteractiveTourOverlay.test.tsx` — the status now travels on the
  error, and the tour explains a rejected token instead of quoting the backend at the tester.

Both were verified to fail against the ungated code before being kept — the Rust escape test and
the Python parse test each caught it.

## 📌 Rules

**A path discovered by searching upward must prove it is the right one, not merely the right
shape.** The search was written for a checkout, where "a directory named `storage` above me" is
unambiguous. Installed, the same search has the whole filesystem in scope and the name alone
carries no evidence.

**Corollary, and the reason this is worth a note rather than a one-line fix:** the failure was not
in the token mechanism, which worked — it published correctly, encrypted correctly, and decrypted
correctly. It was in *which file* was chosen, one layer below anything the token code can check.
The same shape as [[Gotcha - Two Ground-Truth Stores That Never Met]].

## 🔗 Related

- [[Gotcha - The Prototype Build Was Prototype By Accident]] — the 200-on-`/health`-while-401ing
  disguise, and the other four localhost-only layers
- [[Gotcha - Two Ground-Truth Stores That Never Met]] — one rule, two stores, no error
