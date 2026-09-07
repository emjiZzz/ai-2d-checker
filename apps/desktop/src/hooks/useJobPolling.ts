import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchJob } from "../services/jobsApi";
import { jobKeys } from "../services/queryKeys";
import { useDrawingStore } from "../stores/drawingStore";

/**
 * Polls for job status.
 * Will run `fetchJob` every 1500ms as long as the job is 'processing' or 'pending'.
 * Automatically syncs the result into `drawingStore` to maintain UI compatibility.
 */
export function useJobPolling(jobId: string | null) {
  const query = useQuery({
    queryKey: jobId ? jobKeys.detail(jobId) : [],
    queryFn: ({ signal }) => fetchJob(jobId!, signal),
    enabled: !!jobId,
    // Stop polling if complete or failed. Otherwise poll every 1500ms.
    refetchInterval: (query) => {
      const status = query.state?.data?.status;
      if (status === "completed" || status === "failed") {
        return false;
      }
      return 1500;
    },
    // Keep it fresh, we don't want cache hits for a fast-moving status
    staleTime: 0,
  });

  // Sync back to Zustand
  useEffect(() => {
    if (query.data && jobId) {
      const state = useDrawingStore.getState();
      const job = query.data;
      
      state._setActiveJob(job);
      
      if (job.status === "completed") {
        console.info(`Background extraction job ${jobId} completed successfully.`);
        state._setProcessingState("completed");
        state.fetchDiagnostics(jobId);
        if (job.drawing_id) {
          state.fetchDrawingDetails(job.drawing_id);
        }
      } else if (job.status === "failed") {
        console.error(`Job ${jobId} failed: ${job.error_message}`);
        state._setProcessingState("failed", job.error_message || "Extraction job failed");
      }
    }
  }, [query.data, jobId]);

  return query;
}
