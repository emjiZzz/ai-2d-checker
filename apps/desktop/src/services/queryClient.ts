/**
 * queryClient.ts — Global QueryClient Configuration
 *
 * This module exports a singleton QueryClient with application-wide defaults.
 * It is the single place to tune cache behaviour for the entire app.
 *
 * Provider setup (add to App.tsx or main.tsx):
 * ─────────────────────────────────────────────
 *   import { QueryClientProvider } from "@tanstack/react-query";
 *   import { queryClient } from "./services/queryClient";
 *
 *   <QueryClientProvider client={queryClient}>
 *     <App />
 *   </QueryClientProvider>
 *
 * For development, optionally mount ReactQueryDevtools:
 *   import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
 *   <ReactQueryDevtools initialIsOpen={false} />
 */

import { QueryClient } from "@tanstack/react-query";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // ── Pillar 1: Stale-While-Revalidate (SWR) ────────────────────────────
      //
      // staleTime: How long cached data is considered "fresh". During this
      // window TanStack Query serves data from cache instantly without any
      // background network request. After staleTime elapses, the data is
      // "stale" — it is still displayed immediately from cache (zero layout
      // shift) but a silent background revalidation is fired automatically.
      //
      // 60 seconds is a good default: short enough that users rarely see
      // data older than a minute, long enough to prevent request storms on
      // tab-switch or component remounts.
      staleTime: 60 * 1_000, // 60 s

      // gcTime (formerly cacheTime): How long *inactive* (unmounted) query
      // data lingers in memory before the garbage collector removes it.
      // Setting this higher than staleTime means navigating back to a page
      // within 5 minutes still gets an instant render from the old cache
      // (even if stale) while the background fetch runs.
      gcTime: 5 * 60 * 1_000, // 5 min

      // ── Pillar 4: Window Focus & Network Reconnection Sync ────────────────
      //
      // refetchOnWindowFocus: When the user switches browser tabs and comes
      // back, stale queries are silently refetched. This catches changes
      // made in another tab or by another user. Set to "always" if your
      // data changes extremely frequently; false to opt out globally.
      refetchOnWindowFocus: true,

      // refetchOnReconnect: When the browser goes offline and reconnects
      // (e.g. a laptop waking from sleep), stale queries are refetched.
      // Ensures data is fresh after extended periods offline.
      refetchOnReconnect: true,

      // Retry failed requests up to 2 times with exponential back-off.
      // TanStack Query waits 1s → 2s → 4s between retries automatically.
      // We cap at 2 to avoid holding the UI in a loading state for too long.
      retry: 2,
    },
    mutations: {
      // Do not retry mutations by default — a failed write should surface as
      // an error immediately so the rollback in onError runs promptly.
      retry: false,
    },
  },
});
