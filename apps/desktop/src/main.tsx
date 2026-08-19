import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClientProvider } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";
import App from "./App";
import { queryClient } from "./services/queryClient";
import { GlobalErrorFallback } from "./components/GlobalErrorFallback";
import "./index.css";

/**
 * React.lazy() is the correct client-side API for code-splitting a component.
 * Unlike the async-component pattern (RSC-only), React.lazy() works in any
 * client React app — it expects a dynamic import that resolves to a module
 * with a `default` export. The Suspense boundary above it renders `null`
 * while the chunk loads, so there is no visible flash.
 *
 * Vite evaluates import.meta.env.DEV at build time, so this entire lazy()
 * call — and the devtools chunk — is tree-shaken out of production bundles.
 */
const ReactQueryDevtools = import.meta.env.DEV
  ? React.lazy(() =>
      import("@tanstack/react-query-devtools").then((mod) => ({
        // React.lazy requires a { default: ComponentType } shape
        default: mod.ReactQueryDevtools,
      }))
    )
  : null;

const app = (
  <React.StrictMode>
    {/*
     * QueryClientProvider must sit above every component that uses
     * useQuery / useMutation. Placing it here (root) rather than inside App
     * keeps infrastructure concerns out of the App component tree.
     */}
    <ErrorBoundary FallbackComponent={GlobalErrorFallback} onReset={() => window.location.reload()}>
      <QueryClientProvider client={queryClient}>
        <App />
        {/*
         * Suspense is required by React.lazy(). The fallback is null because
         * the devtools panel is non-critical — a brief invisible load is fine.
         */}
        {ReactQueryDevtools && (
          <React.Suspense fallback={null}>
            <ReactQueryDevtools initialIsOpen={false} buttonPosition="bottom-right" />
          </React.Suspense>
        )}
      </QueryClientProvider>
    </ErrorBoundary>
  </React.StrictMode>
);

/**
 * HMR-safe root mounting.
 *
 * The problem: Vite's Hot Module Replacement re-executes this entire module
 * file on every save. A bare `ReactDOM.createRoot(container).render(...)` call
 * therefore runs `createRoot()` again on the same DOM node that already has a
 * React root attached — triggering React's "container already passed to
 * createRoot()" warning and potentially tearing down / rebuilding the tree.
 *
 * The fix: cache the root on `window.__reactRoot`. Unlike module-level
 * variables (which are reset on HMR re-evaluation), `window` properties
 * survive across hot-reloads. On the first load we create the root and
 * cache it; on subsequent HMR re-evaluations we reuse it via `root.render()`.
 */
declare global {
  interface Window {
    __reactRoot?: ReturnType<typeof ReactDOM.createRoot>;
  }
}

const container = document.getElementById("root") as HTMLElement;

if (!window.__reactRoot) {
  // First load: create the root and cache it for future HMR cycles.
  window.__reactRoot = ReactDOM.createRoot(container);
}

// Disable default browser context menu across the desktop app (Back, Refresh, Print, Inspect, etc.)
// Custom in-app context menus (like CAD canvas) will continue to open as they manage their own UI.
document.addEventListener("contextmenu", (e) => {
  e.preventDefault();
});

// On every load (initial + HMR), call render() on the existing root.
window.__reactRoot.render(app);


