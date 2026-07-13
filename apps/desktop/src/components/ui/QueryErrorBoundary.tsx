/**
 * QueryErrorBoundary.tsx — Application-level error boundary for TanStack Query
 *
 * ── Why two layers? ───────────────────────────────────────────────────────────
 * React Error Boundaries must be class components (they use `componentDidCatch`
 * and `getDerivedStateFromError`, which have no hook equivalents). But TanStack
 * Query's `useQueryErrorResetBoundary` is a hook — it can only run inside a
 * function component. The solution is a two-layer pattern:
 *
 *   QueryErrorBoundary (function)     ← calls useQueryErrorResetBoundary()
 *       └── ErrorBoundaryCore (class) ← catches render-phase errors
 *               └── {children}
 *
 * When the user clicks "Try Again":
 *   1. `queryClient.resetQueries()` is called (via reset from the hook)
 *      which clears TanStack Query's error state for all affected queries.
 *   2. `this.setState({ error: null })` is called, which unmounts the
 *      fallback and remounts the children — triggering a fresh query fetch.
 *
 * Both steps are required. Without (1), TanStack Query holds the error
 * and the component would immediately crash again on remount.
 *
 * ── Placement in the tree ────────────────────────────────────────────────────
 * Wrapping `renderContent()` in App.tsx at the workspace/dashboard level.
 * The AppHeader and global drag overlay sit outside the boundary so they
 * remain intact even when a query crashes the inner content.
 *
 * ── What errors does this catch? ─────────────────────────────────────────────
 * Any error thrown during a React render cycle, including:
 *   - TanStack Query `throwOnError: true` (when enabled per-query)
 *   - Errors thrown inside child components during rendering
 *
 * Network errors that TanStack Query retries internally (default: 3 retries)
 * only reach the boundary after all retries are exhausted. This means the
 * boundary is the last line of defence, not the first.
 */

import React from "react";
import { useQueryErrorResetBoundary } from "@tanstack/react-query";

// ─── Types ────────────────────────────────────────────────────────────────────

interface ErrorBoundaryCoreProps {
  children: React.ReactNode;
  /** Called when "Try Again" is clicked — clears TanStack Query error state. */
  onReset: () => void;
  /** Optional override for the fallback UI (e.g., page-level boundaries). */
  fallback?: (error: Error, reset: () => void) => React.ReactNode;
}

interface ErrorBoundaryCoreState {
  error: Error | null;
}

// ─── Class layer: catches render errors ───────────────────────────────────────

class ErrorBoundaryCore extends React.Component<
  ErrorBoundaryCoreProps,
  ErrorBoundaryCoreState
> {
  constructor(props: ErrorBoundaryCoreProps) {
    super(props);
    this.state = { error: null };
    this.handleReset = this.handleReset.bind(this);
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryCoreState {
    return { error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    // In production you would send this to an error tracking service.
    // console.error is intentional here — it surfaces the full stack in devtools.
    console.error("[QueryErrorBoundary] Caught render error:", error, info);
  }

  handleReset() {
    // (1) Reset TanStack Query error state so the retried fetch actually fires.
    this.props.onReset();
    // (2) Clear our own state, which unmounts the fallback and remounts children.
    this.setState({ error: null });
  }

  render() {
    const { error } = this.state;

    if (error) {
      if (this.props.fallback) {
        return this.props.fallback(error, this.handleReset);
      }
      return <DefaultErrorFallback error={error} onReset={this.handleReset} />;
    }

    return this.props.children;
  }
}

// ─── Default fallback UI ──────────────────────────────────────────────────────

interface FallbackProps {
  error: Error;
  onReset: () => void;
}

function DefaultErrorFallback({ error, onReset }: FallbackProps) {
  const isNetworkError =
    error.message.toLowerCase().includes("failed to fetch") ||
    error.message.toLowerCase().includes("network") ||
    error.message.toLowerCase().includes("http 5");

  return (
    <div className="flex-1 flex items-center justify-center w-full h-full bg-bg-dark">
      <div className="max-w-md w-full mx-4">
        {/* Card */}
        <div className="bg-bg-card border border-border-color rounded-2xl p-8 shadow-2xl">
          {/* Icon */}
          <div className="flex justify-center mb-6">
            <div className="w-16 h-16 rounded-full bg-red-500/10 border border-red-500/30 flex items-center justify-center">
              <svg
                xmlns="http://www.w3.org/2000/svg"
                width="28"
                height="28"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
                className="text-red-400"
              >
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="8" x2="12" y2="12" />
                <line x1="12" y1="16" x2="12.01" y2="16" />
              </svg>
            </div>
          </div>

          {/* Heading */}
          <h2 className="text-xl font-bold text-text-primary text-center mb-2">
            {isNetworkError ? "Connection Error" : "Something went wrong"}
          </h2>

          {/* Description */}
          <p className="text-sm text-text-muted text-center mb-6 leading-relaxed">
            {isNetworkError
              ? "Unable to reach the server. Check that the backend is running and your connection is stable."
              : "An unexpected error occurred while loading this view. This has been logged."}
          </p>

          {/* Error detail (collapsed by default — dev/support reference) */}
          <details className="mb-6 group">
            <summary className="text-xs text-text-muted cursor-pointer hover:text-text-secondary transition-colors flex items-center gap-1.5 list-none select-none">
              <svg
                xmlns="http://www.w3.org/2000/svg"
                width="12"
                height="12"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                className="transition-transform group-open:rotate-90"
              >
                <polyline points="9 18 15 12 9 6" />
              </svg>
              Error details
            </summary>
            <pre className="mt-3 text-xs text-red-400/80 bg-red-500/5 border border-red-500/10 rounded-lg p-3 overflow-auto max-h-32 font-mono leading-relaxed whitespace-pre-wrap break-all">
              {error.message}
            </pre>
          </details>

          {/* Actions */}
          <div className="flex flex-col gap-3">
            <button
              onClick={onReset}
              className="w-full h-11 rounded-lg bg-accent-cyan text-bg-dark font-semibold text-sm hover:brightness-110 active:scale-[0.98] transition-all shadow-[0_0_20px_rgba(6,182,212,0.25)] hover:shadow-[0_0_30px_rgba(6,182,212,0.4)]"
            >
              Try Again
            </button>
            <button
              onClick={() => window.location.reload()}
              className="w-full h-11 rounded-lg border border-border-color text-text-muted hover:text-text-primary hover:border-text-muted text-sm transition-all"
            >
              Reload App
            </button>
          </div>
        </div>

        {/* Footer hint */}
        <p className="text-center text-xs text-text-muted mt-4 opacity-60">
          Error boundaries prevent the entire app from crashing.
          Your other work is preserved.
        </p>
      </div>
    </div>
  );
}

// ─── Public API: functional wrapper that bridges the hook ─────────────────────

interface QueryErrorBoundaryProps {
  children: React.ReactNode;
  /** Optional custom fallback renderer for page-level boundaries. */
  fallback?: (error: Error, reset: () => void) => React.ReactNode;
}

/**
 * Drop-in error boundary that integrates with TanStack Query's error reset.
 *
 * Usage (app-level):
 *   <QueryErrorBoundary>
 *     {renderContent()}
 *   </QueryErrorBoundary>
 *
 * Usage (page-level with custom fallback):
 *   <QueryErrorBoundary
 *     fallback={(error, reset) => <MyCustomFallback error={error} onReset={reset} />}
 *   >
 *     <MyPage />
 *   </QueryErrorBoundary>
 */
export function QueryErrorBoundary({ children, fallback }: QueryErrorBoundaryProps) {
  // useQueryErrorResetBoundary returns a reset() function that clears
  // TanStack Query's internal error state for all queries in scope.
  // Without this, retrying after a query error would immediately re-throw.
  const { reset } = useQueryErrorResetBoundary();

  return (
    <ErrorBoundaryCore onReset={reset} fallback={fallback}>
      {children}
    </ErrorBoundaryCore>
  );
}
