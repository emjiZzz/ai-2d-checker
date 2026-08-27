---
title: Gotcha - The Prototype Build Was Prototype By Accident
type: gotcha
tags: [gotcha, prototype, build, vite, tauri, feature-flags, dead-code-elimination, desktop]
status: fixed — 2026-08-27. `dist/build-mode.json` is stamped by `buildModeStamp` in
  `apps/desktop/vite.config.ts` and asserted by `tools/scripts/assert-build-mode.mjs`, which
  `build_prototype.ps1` now runs after `tauri build` and aborts on. Guarded by
  `features.test.ts`, `useManualCheckRoom.test.ts` and `ConnectionBanner.test.tsx`.
cache-version: n/a — frontend build and UI only. No engine, extraction or `render_bounds` change.
related: [ADR-011 Vector as the Only Render Path, ADR-006 Removing the Three AI Comparison Methods, Gotcha - The Layer Rule Was Reviewed, Never Enforced]
date: 2026-08-27
---

# Gotcha — The Prototype Build Was Prototype By Accident

> `VITE_PROTOTYPE_MODE` is the flag that decides whether the app ships with a login screen. Nothing
> in the pipeline reported which value a build resolved, the documented build command discarded the
> step that set it, and the one file that described what the flag *does* described the opposite.

---

## 1. The installer's mode was decided by an ambient variable, and nothing checked

`build_prototype.ps1` read as though it built the prototype frontend and then packaged it:

```powershell
& $pnpmExe --filter desktop build:prototype     # vite build --mode prototype
& $pnpmExe --filter desktop tauri build
```

`tauri.conf.json` sets `beforeBuildCommand: "pnpm build"` — the **plain** script. So `tauri build`
re-runs Vite in production mode and **overwrites `apps/desktop/dist`**. The first command's output
never reaches the installer; it cost a full frontend build and proved nothing, while reading like
the step that set the mode.

The installers were prototype builds anyway, because the same script also exports
`$env:VITE_PROTOTYPE_MODE = "true"`, and Vite merges `VITE_`-prefixed **process** variables
alongside the `.env` files. So the real carrier was the environment variable, and the `--mode`
flag was decoration.

⚠ **The failure mode is silent and ships.** `pnpm build:prototype` is documented in the README's
"Useful Commands"; follow it with `tauri build` in a shell that has no `VITE_PROTOTYPE_MODE`, and
you get a **full installer with a login screen** with no error, no warning, and no way to tell
afterwards — the flag is inlined and folded away, so the two builds differ in content but declare
nothing.

**Fix: make the mode observable, then assert it.** A `closeBundle` plugin writes
`dist/build-mode.json` from the *resolved env* (the half that survives, not `mode`), and
`assert-build-mode.mjs prototype|full` fails the build against it. ⚠ **Assert after `tauri build`,
not before** — asserting on `build:prototype`'s output checks a directory that is about to be
overwritten, which is the exact mistake being guarded. The redundant step was deleted rather than
fixed.

Demonstrated rather than argued, on this tree:

| build command | stamp | assertion |
| :--- | :--- | :--- |
| `vite build --mode prototype` | `prototype: true` | OK |
| `vite build` *(what `tauri build` runs)* | `prototype: false` | **FAIL** |
| `VITE_PROTOTYPE_MODE=true vite build` | `prototype: true` | OK |

⚠ `loadEnv` must be imported from `vite`, not from `vitest/config` — this config file uses
`defineConfig` from the latter because it also carries the `test` block, and `vitest/config` does
not re-export `loadEnv`. Importing it from there fails at config load with *"does not provide an
export named 'loadEnv'"*.

---

## 2. The docstring described the opposite of the behaviour

`features.ts` said prototype mode focused *"100% on deterministic & physical CAD comparison"*.

It does the reverse. `useIsManualCheckRoom()` returned `true` unconditionally under the flag, so
`TwoDLeftPanel` rendered `ManualMarkingList` outright — and its `"CAD Comparison"` header, its
START COMPARISON button and its own prototype-specific idle copy were **unreachable in a prototype
build**. `RoomsView` forces `room_mode: "manual_check"` on create and filters the list to those
rooms; the tour's Tutorial Room is created the same way. **No comparison engine runs in a prototype
build.** It is a ground-truth collection build, which is coherent — the documentation simply named
the other thing. The README's Option B carried the same claim and was corrected with it.

⚠ **Why it drifted: the file's `FEATURES` object had zero consumers.** All 8 gates call
`isPrototypeMode()` directly. A declaration nothing reads cannot drift into being *wrong* — only
into being read as if it were the rule, which is worse, because it looks like a flag system. It
had already under-declared twice: it never mentioned `settings` or the layout controls (both
hidden), and it declared an `aiEngine` toggle for a mode where the engine is unreachable for an
entirely unrelated reason. **Deleted rather than wired up**, on the same grounds as
`domain/contracts.py` — see [[Gotcha - The Layer Rule Was Reviewed, Never Enforced]]. If named
flags come back, the gates must read them or they are documentation with a type signature.

---

## 3. Tidying the flag lookup would have silently doubled the shipped UI

The detector must stay a **single expression naming `import.meta.env` directly, twice**:

```ts
export const isPrototypeMode = (): boolean =>
  import.meta.env.VITE_PROTOTYPE_MODE === "true" || import.meta.env.VITE_PROTOTYPE_MODE === true;
```

Hoisting the lookup into a local `const flag` is behaviourally identical and **costs the dead-code
elimination**. Vite substitutes the literal at each `import.meta.env` site, so the form above
becomes `() => "true" === "true" || …`, which esbuild folds to `() => !0` and inlines into all 8
gates, dropping the untaken branches. Behind a `const`, esbuild stops propagating, the function
survives as a real call, and a prototype build ships the entire login / AI-comparison / Copilot UI
it can never reach.

🔴 **This was introduced accidentally while fixing item 2, and caught only by grepping the bundle.**
With the local, `"AI Comparison"`, `"Stage 2 Auditor"` and `"Engineering Copilot"` all appear in a
PROTOTYPE `dist/assets/*.js`. Without it they do not, and a prototype bundle is **147,729 bytes
smaller** than a full one, also dropping `"START COMPARISON"` and the `"Restoring session"` login
path.

⚠ **No behavioural test can catch this** — the app is identical either way. `features.test.ts`
therefore asserts on the **source shape** of the file, which is unusual and deliberate; verified
non-vacuous by applying the bad form and watching exactly those two assertions fail while the three
behavioural ones still passed.

---

## 4. A conditional hook call, inert only by luck

`useIsManualCheckRoom` read the flag and returned **before** `useRoomStore(...)`:

```ts
if (isPrototypeMode()) return true;          // 0 hooks
return useRoomStore((s) => …);               // 1 hook
```

Safe today only because Vite folds the flag to a build-time constant, so the count cannot vary
between renders. `eslint-plugin-react-hooks` is **not installed** in this repo — the ESLint config
carries exactly one hand-written rule — so nothing would have caught it if the flag ever became
runtime state. Now subscribes first and overrides after.

⚠ **The regression test cannot assert on the return value** — it is `true` under both versions.
React is the oracle instead: flip the flag between two renders of the same mounted hook, and a
varying hook count raises *"Rendered more hooks than during the previous render"*. Verified
non-vacuous against the old body. A first attempt spying on `useRoomStore.getState` does **not**
work — zustand's `create()` copies the api onto the hook with `Object.assign`, so the internal
`useStore(api, selector)` calls the original `api.getState`, not the spied property.

---

## 5. Prototype mode had zero test coverage, and hid its own escape hatch

No test file referenced `isPrototypeMode` or `VITE_PROTOTYPE_MODE`. vitest runs with the flag
unset, so all 633 tests exercised the **non-prototype** branch of every gate: the shipped
configuration was the untested one. Now 16 tests across three files, using `vi.stubEnv`.

Writing them surfaced a dead end. `AppHeader` gates the whole nav strip **and** the whole
right-hand action block on `!isPrototypeMode()`, which takes Settings and the layout switcher with
it — neither of which the docstring listed — and pins `currentNav` to `workspace`.
`SystemDiagnostics`, inside `SettingsView`, is the **only** caller of `setBackendUrl`. So a
prototype build could report "Connection Lost" and retry forever against an address the user could
neither see nor change. Not hypothetical: `connectionStore` hardcodes port **8080** while
`start_desktop.ps1` starts the backend on `SIDECAR_PORT` from `.env`, so the two disagree the
moment anyone sets that variable.

Fixed at the point of failure — the offline overlay now shows the backend address and applies a
correction — rather than by un-hiding Settings, which would also surface Active Learning and the
Cloud Database panel and reopen the AI surfaces the flag exists to hide. Scoped to prototype mode
so the full build keeps one place to change one value.

⚠ **The same class of dead end had already been found one screen earlier**: `RoomsView` showed a
single empty state for both "no search matches" and "no rooms at all", so a fresh install — which
is what a demo is — was offered a Clear Search button for a search it had not typed, and the
"Create New" card lives in a grid that does not render when there are no rooms. **A prototype build
is the only configuration where "first run" and "every run" are the same thing**, so first-run dead
ends do not surface anywhere else.

---

## 6. 🔴 The worst one: the stale-extraction warning was unreachable in the build that needed it

Found while answering *"can we deploy this for data gathering?"* — which is the only question that
would have found it, because it is not a bug in any code path. Nothing is wrong with the badge,
the panel, or the flag. The defect is in the **intersection**.

`StaleExtractionBadge` was mounted in exactly one place, `TwoDRightPanel`, which renders only when:

```ts
isPhysicalComparisonEnabled || aiScanProgress === "completed" || isStandardsAuditCompleted
```

`isPhysicalComparisonEnabled: true` is written in **exactly one place** — `usePhysicalComparison`,
after the comparison engine finishes. (`togglePhysicalComparison` exists on the store and has zero
callers.) Prototype mode forces every room to `manual_check`, so the engine never runs, the flag is
permanently `false`, `aiScanProgress` stays `idle`, `complianceScore` stays `null` — the right
panel is never created and **the badge could not appear in a prototype build at all.**

🔴 **That is precisely the build handed to engineers to collect ground truth**, and at the time
`tools/extraction_status.py` reported **38 of 65 stored drawings stale, 20 of them at v2** — five
versions behind. The badge's own docstring states the cost: *an engineer marking up a v2 sheet is
reading missing arrowheads, short leader landings and a dimension that says `1.05` where the paper
says `60°`.* A stale sheet renders wrong while looking entirely ordinary, so nothing else would
have flagged it, and the resulting markings become **corpus ground truth** — the thing every other
measurement in this system is scored against.

⚠ **A warning is only as good as the least-privileged surface it appears on.** The badge was
correct, tested, and documented; it was mounted beside the *results* of a pipeline that a
ground-truth build deliberately never runs. **When a mode removes a feature, audit what was
mounted inside it** — the removal takes unrelated passengers, and they leave no error. Prototype
mode had already done this twice before anyone noticed: it takes **Settings** with the nav strip
(§5) and it takes the **stale badge** with the comparison results.

Fixed by mounting it in `ManualMarkingList`, the panel that *is* always visible in a manual-check
room, and pinned by `ManualMarkingList.stale.test.tsx` — which asserts both directions, because
"renders nothing when current" is the half that keeps the warning credible on an estate where most
rows are stale.

The estate itself was repaired in the same pass with `tools/reextract_stale_drawings.py`, which
drives `POST /drawings/{id}/reextract` one drawing at a time and **reuses
`extraction_status.collect`** rather than restating the staleness rule — two copies of "which rows
are behind" would disagree silently, one tool reporting clean while the other re-extracts nothing.

---

## The rule

**A build flag that changes what ships must leave evidence in the artifact.** Inlining is what
makes feature flags cheap and it is also what makes them unfalsifiable after the fact: the mode is
gone from the output by design. Stamp it, and assert the stamp at the end of the pipeline that
produces the thing you hand to someone — not at the step that sets it.

**And the corollary, which cost more than the flag did:** a mode that hides a feature also hides
whatever was mounted inside it. Grep for what renders under the gate you are closing, not just for
the gate.
