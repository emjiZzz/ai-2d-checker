import { useQuery, type QueryFunctionContext } from "@tanstack/react-query";
import { fetchDatabaseMetrics, fetchStorageMetrics } from "../services/adminApi";
import { adminMetricsKeys } from "../services/queryKeys";

export function useDatabaseMetrics() {
  return useQuery<any, Error>({
    queryKey: adminMetricsKeys.database(),
    queryFn: ({ signal }: QueryFunctionContext) => fetchDatabaseMetrics(signal),
    // Metrics can be polled frequently or fetched on mount.
    // For now, we'll configure standard SWR.
    staleTime: 10 * 1000, // 10 seconds
  });
}

export function useStorageMetrics() {
  return useQuery<any, Error>({
    queryKey: adminMetricsKeys.storage(),
    queryFn: ({ signal }: QueryFunctionContext) => fetchStorageMetrics(signal),
    staleTime: 60 * 1000, // 60 seconds (storage quotas change less frequently)
  });
}
