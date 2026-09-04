/**
 * Prototype-mode detection for DraftCheck.
 *
 * One build-time flag, `VITE_PROTOTYPE_MODE=true`, read here and nowhere else. Two routes set it
 * and both must keep working: `vite build --mode prototype`, which loads `.env.prototype`, and a
 * `VITE_PROTOTYPE_MODE` process variable, which is what `start_desktop.ps1` and
 * `build_prototype.ps1` export. Only the second survives `tauri build`, which re-runs the plain
 * `pnpm build` from `tauri.conf.json`. `tools/scripts/assert-build-mode.mjs` fails the build
 * rather than let the mode be decided by whichever happened to be set.
 *
 * What it does, measured against the call sites:
 *
 * - Hides UI: the header nav strip and its right-hand action block (`AppHeader`), which takes 3D
 *   Workspace, History, Standards, Settings and the layout switcher with it and pins `currentNav`
 *   to `workspace`; the Auditor/Copilot switcher and per-violation Copilot buttons
 *   (`TwoDRightPanel`).
 * - Forces every room to a manual check: `useIsManualCheckRoom()` returns true regardless of the
 *   room document, and `RoomsView` both creates and filters on `manual_check`. So no comparison
 *   engine runs in a prototype build and `TwoDLeftPanel`'s START COMPARISON is unreachable. This
 *   is a ground-truth collection build.
 * - Bypasses sequencing: login is skipped, the zone-review gate is always open (`zoneGate.ts`),
 *   and `hasHydrated` is set eagerly. `loadWorkspaceState` still runs on `openRoom`, so that last
 *   one is a render gate, not a data bypass.
 *
 * A `FEATURES` object here once declared six of these as named flags with zero consumers, so it
 * could not drift into being wrong, only into being read as the rule -- which it was, twice.
 * Deleted. If you reintroduce named flags, make the gates read them.
 *
 * Pinned by `features.test.ts`, `useManualCheckRoom.test.ts`, `engineerStore.test.ts` and
 * `ConnectionBanner.test.tsx`.
 */

/**
 * Keep this a single expression naming `import.meta.env` directly, twice. Hoisting the lookup
 * into a local `const` is behaviourally identical and silently costs the dead-code elimination:
 * Vite substitutes the literal at each `import.meta.env` site, so this folds to `() => !0` and
 * inlines into all 8 gates, dropping the untaken branches. Behind a `const`, esbuild stops
 * propagating, the function survives as a real call, and a prototype build ships the entire
 * login, AI-comparison and Copilot UI it can never reach.
 *
 * Measured both ways on the same tree: with the local, "AI Comparison", "Stage 2 Auditor" and
 * "Engineering Copilot" appear in a prototype `dist/assets/*.js`; without it they do not. Pinned
 * by `features.test.ts`, which asserts the source shape because nothing else notices -- the app
 * behaves identically either way.
 */
export const isPrototypeMode = (): boolean =>
  import.meta.env.VITE_PROTOTYPE_MODE === "true" || import.meta.env.VITE_PROTOTYPE_MODE === true;
