import { create } from "zustand";
import { useConnectionStore } from "./connectionStore";
import { logger } from "../services/logger";

export interface Drawing {
  id: string;
  file_name: string;
  file_path: string;
  file_hash: string;
  file_size_bytes: number;
  format: string;
  status: string;
  entity_counts: Record<string, number>;
  metadata: Record<string, any>;
  created_at: string;
  updated_at: string;
}

export interface Job {
  id: string;
  drawing_id: string;
  status: string;
  error_message: string | null;
  diagnostics: Record<string, any>;
  conversion_duration_seconds: number | null;
  parsing_duration_seconds: number | null;
  total_duration_seconds: number | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

interface DrawingState {
  drawings: Drawing[];
  activeDrawing: Drawing | null;
  activeJob: Job | null;
  activeDiagnostics: Record<string, any> | null;
  uploadStatus: "idle" | "uploading" | "success" | "error";
  uploadProgress: number;
  processingState: "idle" | "processing" | "completed" | "failed";
  errorMessage: string | null;
  pollingIntervalId: number | null;

  // Actions
  uploadDrawing: (file: File) => Promise<boolean>;
  pollJobStatus: (jobId: string) => void;
  fetchDiagnostics: (jobId: string) => Promise<void>;
  fetchDrawingDetails: (drawingId: string) => Promise<void>;
  resetStore: () => void;
}

export const useDrawingStore = create<DrawingState>((set, get) => ({
  drawings: [],
  activeDrawing: null,
  activeJob: null,
  activeDiagnostics: null,
  uploadStatus: "idle",
  uploadProgress: 0,
  processingState: "idle",
  errorMessage: null,
  pollingIntervalId: null,

  uploadDrawing: async (file: File) => {
    // 1. Get backend configuration and token from connectionStore
    const { backendUrl, apiToken } = useConnectionStore.getState();
    
    set({
      uploadStatus: "uploading",
      uploadProgress: 10,
      processingState: "idle",
      errorMessage: null,
      activeDrawing: null,
      activeJob: null,
      activeDiagnostics: null,
    });
    
    logger.info(`Initiating multipart upload for CAD drawing: ${file.name} (${(file.size / 1024).toFixed(1)} KB)`);

    const formData = new FormData();
    formData.append("file", file);

    try {
      const headers: Record<string, string> = {};
      if (apiToken) {
        headers["Authorization"] = `Bearer ${apiToken}`;
      }

      // We use XMLHttpRequest instead of fetch to get upload progress metrics!
      return new Promise<boolean>((resolve) => {
        const xhr = new XMLHttpRequest();
        xhr.open("POST", `${backendUrl}/api/v1/drawings/upload`);
        
        // Headers
        for (const [key, value] of Object.entries(headers)) {
          xhr.setRequestHeader(key, value);
        }

        // Progress Listener
        xhr.upload.onprogress = (event) => {
          if (event.lengthComputable) {
            const percentComplete = Math.round((event.loaded / event.total) * 90);
            set({ uploadProgress: percentComplete });
          }
        };

        xhr.onload = async () => {
          if (xhr.status >= 200 && xhr.status < 300) {
            try {
              const response = JSON.parse(xhr.responseText);
              if (response.success && response.data) {
                const { drawing, job, is_duplicate } = response.data;
                
                logger.info(
                  `Upload complete for drawing ${drawing.file_name}. ` +
                  `Duplicate: ${is_duplicate}. Job ID: ${job.id}`
                );

                set({
                  uploadStatus: "success",
                  uploadProgress: 100,
                  activeDrawing: drawing,
                  activeJob: job,
                  processingState: job.status === "completed" ? "completed" : "processing"
                });

                // If job is already done (duplicate bypass), fetch details directly
                if (job.status === "completed") {
                  get().fetchDiagnostics(job.id);
                } else {
                  // Kickoff background status polling
                  get().pollJobStatus(job.id);
                }
                
                resolve(true);
              } else {
                const errMsg = response.error?.message || "Invalid upload response schema";
                logger.error(`Drawing upload failed inside handler: ${errMsg}`);
                set({ uploadStatus: "error", errorMessage: errMsg, uploadProgress: 0 });
                resolve(false);
              }
            } catch (jsonErr) {
              logger.error("Failed to parse drawing upload response JSON");
              set({ uploadStatus: "error", errorMessage: "Invalid JSON response from server.", uploadProgress: 0 });
              resolve(false);
            }
          } else {
            let errMsg = `Upload request failed with status: ${xhr.status}`;
            try {
              const errResp = JSON.parse(xhr.responseText);
              errMsg = errResp.detail || errResp.error?.message || errMsg;
            } catch {}
            
            logger.error(`Drawing upload server rejected: ${errMsg}`);
            set({ uploadStatus: "error", errorMessage: errMsg, uploadProgress: 0 });
            resolve(false);
          }
        };

        xhr.onerror = () => {
          logger.error("Connection failure occurred during drawing upload.");
          set({
            uploadStatus: "error",
            errorMessage: "Network error occurred. Standalone backend may be offline.",
            uploadProgress: 0
          });
          resolve(false);
        };

        xhr.send(formData);
      });

    } catch (err: any) {
      logger.error(`Critical upload exception: ${err.message}`);
      set({ uploadStatus: "error", errorMessage: err.message, uploadProgress: 0 });
      return false;
    }
  },

  pollJobStatus: (jobId: string) => {
    // 1. Clear any existing intervals first
    get().resetStore(); // Stops active intervals
    
    set({ processingState: "processing" });
    const { backendUrl, apiToken } = useConnectionStore.getState();

    const intervalId = window.setInterval(async () => {
      try {
        const headers: Record<string, string> = { "Accept": "application/json" };
        if (apiToken) {
          headers["Authorization"] = `Bearer ${apiToken}`;
        }

        const response = await fetch(`${backendUrl}/api/v1/jobs/${jobId}`, { headers });
        if (!response.ok) {
          throw new Error(`Job poll failed: HTTP ${response.status}`);
        }

        const result = await response.json();
        if (result.success && result.data) {
          const job: Job = result.data;
          set({ activeJob: job });

          if (job.status === "completed") {
            logger.info(`Background extraction job ${jobId} completed successfully.`);
            window.clearInterval(intervalId);
            set({
              pollingIntervalId: null,
              processingState: "completed"
            });
            // Fetch updated drawing details and diagnostics
            get().fetchDrawingDetails(job.drawing_id);
            get().fetchDiagnostics(job.id);
          } else if (job.status === "failed") {
            const err = job.error_message || "Unknown background CAD pipeline failure.";
            logger.error(`Background extraction job ${jobId} failed: ${err}`);
            window.clearInterval(intervalId);
            set({
              pollingIntervalId: null,
              processingState: "failed",
              errorMessage: err
            });
          }
        }
      } catch (err: any) {
        logger.warn(`Job polling transient request failure: ${err.message}`);
      }
    }, 1500); // Poll every 1.5 seconds

    set({ pollingIntervalId: intervalId });
  },

  fetchDiagnostics: async (jobId: string) => {
    const { backendUrl, apiToken } = useConnectionStore.getState();
    try {
      const headers: Record<string, string> = { "Accept": "application/json" };
      if (apiToken) {
        headers["Authorization"] = `Bearer ${apiToken}`;
      }

      const response = await fetch(`${backendUrl}/api/v1/jobs/${jobId}/diagnostics`, { headers });
      if (response.ok) {
        const result = await response.json();
        if (result.success) {
          set({ activeDiagnostics: result.data });
        }
      }
    } catch (err: any) {
      logger.warn(`Failed to fetch job diagnostics: ${err.message}`);
    }
  },

  fetchDrawingDetails: async (drawingId: string) => {
    const { backendUrl, apiToken } = useConnectionStore.getState();
    try {
      const headers: Record<string, string> = { "Accept": "application/json" };
      if (apiToken) {
        headers["Authorization"] = `Bearer ${apiToken}`;
      }

      const response = await fetch(`${backendUrl}/api/v1/drawings/${drawingId}`, { headers });
      if (response.ok) {
        const result = await response.json();
        if (result.success) {
          set({ activeDrawing: result.data });
        }
      }
    } catch (err: any) {
      logger.warn(`Failed to fetch drawing details: ${err.message}`);
    }
  },

  resetStore: () => {
    const { pollingIntervalId } = get();
    if (pollingIntervalId) {
      window.clearInterval(pollingIntervalId);
    }
    set({
      activeDrawing: null,
      activeJob: null,
      activeDiagnostics: null,
      uploadStatus: "idle",
      uploadProgress: 0,
      processingState: "idle",
      errorMessage: null,
      pollingIntervalId: null
    });
  }
}));
