/**
 * Prototype-mode detection for DraftCheck.
 *
 * One build-time flag, `VITE_PROTOTYPE_MODE=true`, read here and nowhere else. Vite inlines it,
 * so `isPrototypeMode()` folds to a constant at build time and the untaken branches are dropped
 * from the bundle. It is set two ways and both must keep working:
 *
 * - `vite --mode prototype` / `vite build --mode prototype`, which loads `.env.prototype`;
 * - `VITE_PROTOTYPE_MODE=true` in the process environment, which is how `start_desktop.ps1` and
 *   `build_prototype.ps1` set it — `tauri build` re-runs the plain `pnpm build` from
 *   `tauri.conf.json`, so `--mode prototype` alone never survives into an installer.
 *   See `tools/scripts/assert-build-mode.mjs`, which fails the build rather than let the mode be
 *   decided by whichever of the two happened to be set.
 *
 * ## What prototype mode actually does
 *
 * Measured against the call sites, not intended. Three different kinds of change, and the middle
 * one is the one this comment used to describe backwards:
 *
 * **Hides UI.** The whole header nav strip and the header's right-hand action block
 * (`AppHeader`) — which takes 3D Workspace, History, Standards **and Settings and the layout
 * switcher** with it, leaving `currentNav` pinned to `workspace`; the Stage 2 Auditor / Copilot
 * mode switcher and the per-violation "ask Copilot" buttons (`TwoDRightPanel`).
 *
 * **Forces every room to be a manual check.** `useIsManualCheckRoom()` returns true regardless of
 * the room document, `RoomsView` creates rooms as `manual_check` and lists only those, and the
 * tour's Tutorial Room is created the same way. **So no comparison engine runs in a prototype
 * build.** `TwoDLeftPanel` renders `ManualMarkingList` outright, and its "CAD Comparison" header,
 * its START COMPARISON button and its prototype-specific idle copy are all unreachable —
 * this comment claimed prototype mode focused "100% on deterministic & physical CAD comparison",
 * which is the opposite of what the flag does. It is a ground-truth collection build.
 *
 * **Bypasses sequencing.** Login is skipped (`App.tsx` renders the workspace directly, and the
 * window maximises on startup instead of on login), the zone-review gate is always open
 * (`zoneGate.ts`), and `hasHydrated` is set eagerly so the workspace renders before a room is
 * opened — `loadWorkspaceState` still runs on `openRoom` and overwrites it, so this is a render
 * gate, not a data bypass.
 *
 * There was a `FEATURES` object here declaring six of these as named flags. It had **zero
 * consumers** — every gate calls `isPrototypeMode()` directly — so it could not drift into being
 * wrong, only into being read as if it were the rule. It was, twice: it never declared `settings`
 * or the layout controls, and it declared an `aiEngine` toggle for a mode in which the engine is
 * unreachable for an entirely different reason. Deleted rather than wired up, on the same grounds
 * as `domain/contracts.py`: dead code whose only live effect is the claim it appears to make.
 * If you reintroduce named flags, make the gates read them, or they are documentation with a
 * type signature.
 *
 * Pinned by `features.test.ts` and `prototypeMode.test.tsx`.
 */

/**
 * **Keep this a single expression that names `import.meta.env` directly, twice.**
 *
 * It looks like it is begging to be tidied into a local:
 *
 *     const flag = import.meta.env.VITE_PROTOTYPE_MODE;   // <- do not
 *     return flag === "true" || flag === true;
 *
 * That version is behaviourally identical and **silently costs the dead-code elimination.** Vite
 * substitutes the literal for `import.meta.env.VITE_PROTOTYPE_MODE`, so the form below becomes
 * `() => "true" === "true" || ...`, which esbuild folds to `() => !0` and then inlines into every
 * `isPrototypeMode()` call site — collapsing all 8 gates to constants and dropping the untaken
 * branches. Behind a `const`, esbuild stops propagating and the function survives as a real call,
 * so a prototype build ships the entire login / AI-comparison / Copilot UI it can never reach.
 *
 * Measured, both ways, on the same tree: with the local, "AI Comparison", "Stage 2 Auditor" and
 * "Engineering Copilot" are all present in `dist/assets/*.js` of a PROTOTYPE build; without it,
 * none of them are. Pinned by `features.test.ts`, which asserts the source shape, because nothing
 * else notices — the app behaves identically either way.
 */
export const isPrototypeMode = (): boolean =>
  import.meta.env.VITE_PROTOTYPE_MODE === "true" || import.meta.env.VITE_PROTOTYPE_MODE === true;
