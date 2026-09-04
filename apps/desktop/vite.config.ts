// `defineConfig` from vitest/config, because this file also carries the `test` block.
// `loadEnv`/`Plugin` from vite itself — vitest/config does not re-export them, and importing
// them from there fails at config load with "does not provide an export named 'loadEnv'".
import { defineConfig } from "vitest/config";
import { loadEnv, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import tailwind from "@tailwindcss/vite";
import { writeFileSync } from "node:fs";
import { join } from "node:path";

// @ts-expect-error process is a nodejs global
const host = process.env.TAURI_DEV_HOST;

/**
 * Stamp `dist/build-mode.json` with the prototype flag this build actually resolved.
 *
 * The flag reaches Vite by two routes — `--mode prototype` (via `.env.prototype`) and a
 * `VITE_PROTOTYPE_MODE` process variable — and only the second one survives `tauri build`, which
 * re-runs the plain `pnpm build` from `tauri.conf.json` and overwrites whatever `build:prototype`
 * just produced. Nothing used to report which route won, so a prototype installer and a full one
 * were the same command with a different ambient environment and no way to tell them apart
 * afterwards. The stamp is what `tools/scripts/assert-build-mode.mjs` reads.
 *
 * ⚠ Written from the resolved env, not from `mode`, precisely because `mode` is the half that
 * gets lost.
 */
function buildModeStamp(isPrototype: boolean): Plugin {
  return {
    name: "kmti-build-mode-stamp",
    apply: "build",
    closeBundle() {
      const stamp = { prototype: isPrototype, builtAt: new Date().toISOString() };
      writeFileSync(
        join(__dirname, "dist", "build-mode.json"),
        JSON.stringify(stamp, null, 2) + "\n",
      );
      console.log(`\n  build mode: ${isPrototype ? "PROTOTYPE" : "FULL"} -> dist/build-mode.json\n`);
    },
  };
}

// https://vite.dev/config/
export default defineConfig(async ({ mode }) => {
  // Third argument "" so process-environment variables are merged in alongside the `.env` files,
  // which is the route `start_desktop.ps1` and `build_prototype.ps1` use.
  const env = loadEnv(mode ?? "development", __dirname, "");
  const isPrototype = env.VITE_PROTOTYPE_MODE === "true";

  return {
    plugins: [react(), tailwind(), buildModeStamp(isPrototype)],

    test: {
      environment: 'jsdom',
      setupFiles: ['./src/setupTests.ts'],
      globals: true,
      exclude: ['**/node_modules/**', '**/e2e/**'],
    },


    // Vite options tailored for Tauri development and only applied in `tauri dev` or `tauri build`
    //
    // 1. prevent Vite from obscuring rust errors
    clearScreen: false,
    // 2. tauri expects a fixed port, fail if that port is not available
    server: {
      port: 1420,
      strictPort: true,
      host: host || false,
      hmr: host
        ? {
            protocol: "ws",
            host,
            port: 1421,
          }
        : undefined,
      watch: {
        // 3. tell Vite to ignore watching `src-tauri`
        ignored: ["**/src-tauri/**"],
      },
    },
  };
});
