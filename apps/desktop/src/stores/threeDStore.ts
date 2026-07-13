import { create } from "zustand";
import { uploadFile } from "../services/fetchUtils";
import { DrawingItem, UploadState } from "./workspace/types";

export interface ThreeDStoreState {
  activeDrawing: DrawingItem | null;
  uploadState: UploadState;
  uploadProgress: number;
  fileName: string | null;
  fileSize: number | null;
  errorMessage: string | null;
  activeUploadJobId: string | null;

  selectedClient: string | null;
  auditStatus: "idle" | "queued" | "auditing" | "completed" | "failed";
  complianceScore: number | null;
  violations: any[];
  selectedViolation: string | null;

  uploadDrawingFile: (file: File) => Promise<boolean>;
  clearUpload: () => void;
  setSelectedClient: (client: string) => void;
  selectViolation: (id: string | null) => void;
  runAudit: (clientName: string) => Promise<void>;
  _setActiveJobId: (jobId: string) => void;
  _setDrawing: (drawing: DrawingItem) => void;
  _setUploadStatus: (state: UploadState, progress: number, errorMsg?: string | null) => void;
}

export const useThreeDStore = create<ThreeDStoreState>((set) => ({
  activeDrawing: null,
  uploadState: "idle",
  uploadProgress: 0,
  fileName: null,
  fileSize: null,
  errorMessage: null,
  activeUploadJobId: null,

  selectedClient: null,
  auditStatus: "idle",
  complianceScore: null,
  violations: [],
  selectedViolation: null,

  uploadDrawingFile: async (file: File) => {
    const MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024; // 50MB
    set({
      uploadState: "validating",
      uploadProgress: 10,
      fileName: file.name,
      fileSize: file.size,
      errorMessage: null,
      activeDrawing: null,
      auditStatus: "idle",
      violations: [],
      complianceScore: null
    });

    const updateStatus = (state: UploadState, progress: number, errorMsg: string | null = null) => {
      set({ uploadState: state, uploadProgress: progress, errorMessage: errorMsg });
    };

    const extension = file.name.split(".").pop()?.toLowerCase();
    const is3D = ["step", "stp", "iges", "igs", "icd", "sldprt", "sldasm"].includes(extension || "");
    if (!extension || !is3D) {
      updateStatus("failed", 0, "Unsupported format. Only 3D (STEP, IGES, ICD, SolidWorks) files are allowed here.");
      return false;
    }

    if (file.size > MAX_FILE_SIZE_BYTES) {
      updateStatus("failed", 0, "File exceeds the maximum limit.");
      return false;
    }

    updateStatus("uploading", 40);

    const formData = new FormData();
    formData.append("file", file);

    try {
      const uploadResult = await uploadFile<any>(
        "/api/v1/drawings/upload",
        formData,
        (percent) => updateStatus("processing", percent)
      );

      const { drawing, job } = uploadResult;
      updateStatus("processing", 80);

      if (job.status === "completed") {
        set({ activeDrawing: drawing, uploadState: "completed", uploadProgress: 100 });
      } else if (job.status === "failed") {
        throw new Error(job.error_message || "Background extraction job aborted.");
      } else {
        set({ uploadState: "processing", uploadProgress: 80, activeUploadJobId: job.id });
        return true;
      }
      return true;

    } catch (err: any) {
      updateStatus("failed", 0, err.message || "Failed to process 3D drawing ingestion.");
      return false;
    }
  },

  clearUpload: () => {
    set({
      activeDrawing: null,
      uploadState: "idle",
      uploadProgress: 0,
      fileName: null,
      fileSize: null,
      errorMessage: null,
      activeUploadJobId: null,
      auditStatus: "idle",
      complianceScore: null,
      violations: [],
      selectedViolation: null
    });
  },

  setSelectedClient: (client) => set({ selectedClient: client }),
  
  selectViolation: (id) => set({ selectedViolation: id }),

  runAudit: async (_clientName) => {
    set({ auditStatus: "auditing" });
    // Mock a 3D audit execution wait
    await new Promise((res) => setTimeout(res, 2000));
    set({
      auditStatus: "completed",
      complianceScore: 85,
      violations: [
        {
          id: "v_3d_01",
          severity: "high",
          category: "Dimensional Tolerance",
          description: "Pillar height exceeds maximum mounting footprint by 1.2mm in Z-axis.",
          recommendation: "Reduce vertical pillar extrusion to match bracket specification standard.",
          confidence: 0.94,
          standard_reference: "ISO-2768-m",
          affected_entities: []
        },
        {
          id: "v_3d_02",
          severity: "medium",
          category: "Feature Clearance",
          description: "Counterbore depth leaves thin wall thickness of 0.85mm at bottom face.",
          recommendation: "Increase bottom pocket wall thickness to at least 1.50mm to prevent shear cracking.",
          confidence: 0.87,
          standard_reference: "ASME Y14.5",
          affected_entities: []
        }
      ]
    });
  },

  _setActiveJobId: (jobId) => set({ activeUploadJobId: jobId }),
  _setDrawing: (drawing) => set({ activeDrawing: drawing }),
  _setUploadStatus: (state, progress, errorMsg) => set({ uploadState: state, uploadProgress: progress, errorMessage: errorMsg || null })
}));
