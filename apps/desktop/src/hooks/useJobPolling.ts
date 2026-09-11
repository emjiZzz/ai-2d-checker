import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchJob } from "../services/jobsApi";
import { fetchDrawing } from "../services/drawingsApi";
import { jobKeys } from "../services/queryKeys";
import { useDrawingStore } from "../stores/drawingStore";
import { useThreeDStore } from "../stores/threeDStore";
import { hasThreeDMesh, is3DModelFormat } from "../config/drawingFormats";

/**
 * Polls for job status.
 * Will run `fetchJob` every 1200ms as long as the job is 'processing' or 'pending'.
 * Automatically syncs the result into `threeDStore` and `drawingStore`.
 */
export function useJobPolling(jobId: string | null) {
  const query = useQuery({
    queryKey: jobId ? jobKeys.detail(jobId) : [],
    queryFn: ({ signal }) => fetchJob(jobId!, signal),
    enabled: !!jobId,
    // Stop polling if complete or failed. Otherwise poll every 1200ms.
    refetchInterval: (query) => {
      const status = query.state?.data?.status;
      if (status === "completed" || status === "failed") {
        return false;
      }
      return 1200;
    },
    // Keep it fresh, we don't want cache hits for a fast-moving status
    staleTime: 0,
  });

  // Sync back to Zustand
  useEffect(() => {
    if (query.data && jobId) {
      const job = query.data;
      const threeDState = useThreeDStore.getState();
      const drawingState = useDrawingStore.getState();

      drawingState._setActiveJob(job);

      if (job.status === "completed") {
        console.info(`Background extraction job ${jobId} completed successfully.`);
        drawingState._setProcessingState("completed");
        drawingState.fetchDiagnostics(jobId);

        if (job.drawing_id) {
          drawingState.fetchDrawingDetails(job.drawing_id);

          fetchDrawing(job.drawing_id)
            .then((drawing) => {
              if (is3DModelFormat(drawing.format?.toLowerCase()) || hasThreeDMesh(drawing)) {
                threeDState._setDrawing(drawing as any);
                threeDState._setUploadStatus("completed", 100);
              } else {
                threeDState._setUploadStatus(
                  "failed",
                  0,
                  `This file (${drawing.file_name}) contains a 2D drawing sheet with no 3D solid model. Please view it in the 2D Workspace or upload a 3D STEP/IGES model.`
                );
              }
              threeDState._setActiveJobId(null as any);
            })
            .catch((err) => {
              console.warn("Failed to fetch drawing details after job completion", err);
              threeDState._setUploadStatus("failed", 0, "Failed to load drawing after processing.");
              threeDState._setActiveJobId(null as any);
            });
        } else {
          threeDState._setUploadStatus("completed", 100);
          threeDState._setActiveJobId(null as any);
        }
      } else if (job.status === "failed") {
        console.error(`Job ${jobId} failed: ${job.error_message}`);
        drawingState._setProcessingState("failed", job.error_message || "Extraction job failed");
        threeDState._setUploadStatus("failed", 0, job.error_message || "Extraction job failed");
        threeDState._setActiveJobId(null as any);
      }
    } else if (query.isError && jobId) {
      console.error(`Job polling for ${jobId} failed:`, query.error);
      const threeDState = useThreeDStore.getState();
      threeDState._setUploadStatus("failed", 0, "Lost contact with server while processing.");
      threeDState._setActiveJobId(null as any);
    }
  }, [query.data, query.isError, jobId]);

  return query;
}
