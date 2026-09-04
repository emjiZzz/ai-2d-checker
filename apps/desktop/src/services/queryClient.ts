/** The singleton QueryClient, and the one place to tune cache behaviour app-wide. */

import { QueryClient, onlineManager } from "@tanstack/react-query";
import { useConnectionStore } from "../stores/connectionStore";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Long enough to stop request storms on tab-switch and remount, short enough that nobody
      // reads data more than a minute old.
      staleTime: 60 * 1_000,

      // Above staleTime on purpose: navigating back within 5 minutes renders instantly from the
      // stale cache while the background fetch runs.
      gcTime: 5 * 60 * 1_000,

      refetchOnWindowFocus: true,
      refetchOnReconnect: true,

      // Capped at 2 so a dead backend does not hold the UI in a loading state for 7 s.
      retry: 2,
    },
    mutations: {
      // A failed write must surface immediately so the rollback in onError runs.
      retry: false,
    },
  },
});

/**
 * Synchronizes TanStack Query's onlineManager with local backend health status.
 * In a desktop context (Tauri/Vite), navigator.onLine stays true even when local
 * localhost backend is unreachable. Updating onlineManager according to connectionStore
 * ensures refetchOnReconnect fires automatically when the backend server opens/reconnects.
 */
export function setupConnectionSync() {
  const initialStatus = useConnectionStore.getState().status;
  onlineManager.setOnline(initialStatus === "online");

  return useConnectionStore.subscribe((state, prevState) => {
    const isOnline = state.status === "online";
    onlineManager.setOnline(isOnline);

    const wasOffline =
      prevState.status === "offline" ||
      prevState.status === "connecting" ||
      prevState.status === "reconnecting" ||
      prevState.status === "failed";

    if (wasOffline && isOnline) {
      console.log("[queryClient] Backend connection restored — invalidating queries & triggering refetch.");
      queryClient.invalidateQueries();
    }
  });
}
