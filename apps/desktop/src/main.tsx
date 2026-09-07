import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClientProvider } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";
import App from "./App";
import { queryClient } from "./services/queryClient";
import { GlobalErrorFallback } from "./components/GlobalErrorFallback";
import "./index.css";

/**
 * Vite evaluates `import.meta.env.DEV` at build time, so this whole branch and the devtools
 * chunk with it are tree-shaken out of a production bundle.
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
    {/* At the root rather than inside App, so infrastructure stays out of the App tree. */}
    <ErrorBoundary FallbackComponent={GlobalErrorFallback} onReset={() => window.location.reload()}>
      <QueryClientProvider client={queryClient}>
        <App />
        {/* Null fallback: the devtools panel is non-critical, so an invisible load is fine. */}
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
 * HMR-safe root mounting. Vite re-executes this module on every save, so a bare
 * `createRoot(container).render(...)` calls `createRoot` again on a node that already has a root
 * -- React's "container already passed to createRoot" warning, and a tree that may be torn down
 * and rebuilt. The root is cached on `window` because a module-level variable is reset by the
 * re-evaluation and a `window` property is not.
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


