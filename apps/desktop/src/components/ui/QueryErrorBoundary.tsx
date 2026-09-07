/**
 * Application-level error boundary for TanStack Query.
 *
 * Two layers because the two requirements are incompatible: an error boundary must be a class
 * component, and `useQueryErrorResetBoundary` is a hook. So a function wrapper calls the hook and
 * a class core catches the render error.
 *
 * "Try Again" needs both halves -- reset the query error state, then clear the boundary's own
 * state to remount the children. Without the first, TanStack Query still holds the error and the
 * remounted child crashes again immediately.
 *
 * It wraps `renderContent()` in `App.tsx`, leaving `AppHeader` and the drag overlay outside so
 * they survive a crash in the inner content. Retries are exhausted before an error arrives here,
 * so this is the last line of defence rather than the first.
 */

import React, { useEffect, useState } from "react";
import { useQueryErrorResetBoundary } from "@tanstack/react-query";
import { useConnectionStore } from "../../stores/connectionStore";

// ─── Types ────────────────────────────────────────────────────────────────────

interface ErrorBoundaryCoreProps {
  children: React.ReactNode;
  /** Called when "Try Again" is clicked — clears TanStack Query error state. */
  onReset: () => void;
  /** Optional override for the fallback UI (e.g., page-level boundaries). */
  fallback?: (error: Error, reset: () => void) => React.ReactNode;
  /**
   * Bumped by the wrapper when the backend comes back online, to clear a displayed
   * fallback without the caller having to remount the whole subtree. Keying the boundary
   * on connection status would do it too, but that throws away every child's local state
   * — canvas view, scroll, in-progress input — on any connection blip, error or not.
   */
  resetSignal?: number;
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

  componentDidUpdate(prevProps: ErrorBoundaryCoreProps) {
    // Only clears a fallback that is actually displayed; a healthy subtree is untouched.
    if (prevProps.resetSignal !== this.props.resetSignal && this.state.error) {
      this.setState({ error: null });
    }
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

/** Drop-in error boundary that integrates with TanStack Query's error reset. */
export function QueryErrorBoundary({ children, fallback }: QueryErrorBoundaryProps) {
  // Clears the query error state for every query in scope. Without it, a retry re-throws.
  const { reset } = useQueryErrorResetBoundary();
  const status = useConnectionStore((s) => s.status);
  const [resetSignal, setResetSignal] = useState(0);

  // When the backend comes back online, clear TanStack Query's error state and tell the
  // boundary to drop a displayed fallback — the user should not have to click "Try Again"
  // for an error whose cause (the backend being down) has already gone away.
  useEffect(() => {
    if (status === "online") {
      reset();
      setResetSignal((n) => n + 1);
    }
  }, [status, reset]);

  return (
    <ErrorBoundaryCore onReset={reset} fallback={fallback} resetSignal={resetSignal}>
      {children}
    </ErrorBoundaryCore>
  );
}

