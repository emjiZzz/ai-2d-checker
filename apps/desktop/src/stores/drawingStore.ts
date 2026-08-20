import { create } from "zustand";
import { buildHeaders, baseUrl, uploadFile, parseOrThrow } from "../services/fetchUtils";
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
  // Extraction-schema provenance. Optional because a backend predating these fields does not
  // send them, and absent means "cannot judge", not "current". The staleness decision is the
  // server's — see `DrawingItem` in stores/workspace/types.ts for why it is not recomputed here.
  extraction_schema_version?: number;
  current_extraction_schema_version?: number;
  extraction_is_stale?: boolean;
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

interface UploadResponse {
  drawing: Drawing;
  job: Job;
  is_duplicate: boolean;
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

  // Actions
  uploadDrawing: (file: File) => Promise<boolean>;
  fetchDiagnostics: (jobId: string) => Promise<void>;
  fetchDrawingDetails: (drawingId: string) => Promise<void>;
  resetStore: () => void;
  _setActiveJob: (job: Job) => void;
  _setProcessingState: (state: DrawingState["processingState"], error?: string) => void;
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

  uploadDrawing: async (file: File) => {
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
      const res = await uploadFile<UploadResponse>(
        "/api/v1/drawings/upload",
        formData,
        (percent) => set({ uploadProgress: percent })
      );

      const { drawing, job, is_duplicate } = res;

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

      if (job.status === "completed") {
        get().fetchDiagnostics(job.id);
      } else {
        set({ processingState: "processing" });
      }

      return true;
    } catch (err: any) {
      logger.error(`Critical upload exception: ${err.message}`);
      set({ uploadStatus: "error", errorMessage: err.message, uploadProgress: 0 });
      return false;
    }
  },

  _setActiveJob: (job) => set({ activeJob: job }),

  _setProcessingState: (state, error) => set({ 
    processingState: state, 
    errorMessage: error || null 
  }),

  fetchDiagnostics: async (jobId: string) => {
    try {
      const res = await fetch(`${baseUrl()}/api/v1/jobs/${jobId}/diagnostics`, {
        headers: buildHeaders()
      });
      const data = await parseOrThrow<Record<string, any>>(res);
      set({ activeDiagnostics: data });
    } catch {
      // Ignored
    }
  },

  fetchDrawingDetails: async (drawingId: string) => {
    try {
      const res = await fetch(`${baseUrl()}/api/v1/drawings/${drawingId}`, {
        headers: buildHeaders()
      });
      const data = await parseOrThrow<Drawing>(res);
      set({ activeDrawing: data });
    } catch (err: any) {
      logger.error(`Failed to refresh drawing details: ${err.message}`);
    }
  },

  resetStore: () => {
    set({
      activeDrawing: null,
      activeJob: null,
      activeDiagnostics: null,
      uploadStatus: "idle",
      uploadProgress: 0,
      processingState: "idle",
      errorMessage: null
    });
  }
}));
