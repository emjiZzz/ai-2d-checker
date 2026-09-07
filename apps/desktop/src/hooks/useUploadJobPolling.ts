import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchJob } from "../services/jobsApi";
import { fetchDrawing } from "../services/drawingsApi";
import { jobKeys } from "../services/queryKeys";
import { useWorkspaceStore } from "../stores/workspaceStore";

export function useUploadJobPolling(jobId: string | null, side: "old" | "new") {
  const query = useQuery({
    queryKey: jobId ? jobKeys.detail(jobId) : [],
    queryFn: ({ signal }) => fetchJob(jobId!, signal),
    enabled: !!jobId,
    // Poll every 1200ms while processing or pending
    refetchInterval: (query) => {
      const status = query.state?.data?.status;
      if (status === "completed" || status === "failed") {
        return false;
      }
      return 1200;
    },
    staleTime: 0,
  });

  // Sync back to Zustand Workspace Store
  useEffect(() => {
    if (query.data && jobId) {
      const state = useWorkspaceStore.getState();
      const job = query.data;

      if (job.status === "completed") {
        console.info(`Background extraction job ${jobId} for ${side} completed successfully.`);
        
        // Fetch the finalized drawing details and update the workspace
        if (job.drawing_id) {
          fetchDrawing(job.drawing_id)
            .then(completedDrawing => {
              // Extraction succeeding does not mean the drawing belongs in this room.
              // applyCompletedDrawing installs it, or rejects and deletes it when it is not
              // a revision of what the other slot already holds.
              state.applyCompletedDrawing(completedDrawing, side);
            })
            .catch(err => {
              console.warn("Failed to fetch drawing details after job completion", err);
            });
        }
      } else if (job.status === "failed") {
        // The job carries both the reason and the drawing it was for, and both were going to
        // the console only. The reason is what the engineer needs to see, and the drawing id is
        // what makes `/reextract` possible -- without it the sole recovery is another upload,
        // which creates a second row because dedupe is deliberately gone.
        console.error(`Upload job ${jobId} failed: ${job.error_message}`);
        state.setUploadFailure(side, job.drawing_id ?? null, job.error_message ?? null);
      }
    } else if (query.isError && jobId) {
      // Polling itself failed, so nothing is known about the drawing's state on the server.
      // No drawing id: offering a retry here would be guessing at what to retry.
      console.error(`Upload job polling for ${jobId} failed:`, query.error);
      const state = useWorkspaceStore.getState();
      state.setUploadFailure(side, null, "Lost contact with the server while it was ingesting.");
    }
  }, [query.data, query.isError, query.error, jobId, side]);

  return query;
}
