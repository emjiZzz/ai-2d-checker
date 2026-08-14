import { StateCreator } from "zustand";
import { WorkspaceState, UploadSlice, UploadState, QueueEntry } from "../types";
import { uploadFile } from "../../../services/fetchUtils";
import { deleteDrawing } from "../../../services/drawingsApi";
import {
  describeDrawingPairMismatch,
  isDrawingPairMismatch,
} from "../../../utils/drawingIdentity";

const MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024 * 1024; // 10GB

export const createUploadSlice: StateCreator<WorkspaceState, [], [], UploadSlice> = (set, get) => ({
  oldUploadState: "idle",
  newUploadState: "idle",
  oldUploadProgress: 0,
  newUploadProgress: 0,
  oldFileName: null,
  newFileName: null,
  oldFileSize: null,
  newFileSize: null,
  oldError: null,
  newError: null,
  compatibilityStatus: "Idle",
  uploadQueue: [],
  activeOldJobId: null,
  activeNewJobId: null,

  setOldUploadState: (state) => set({ oldUploadState: state }),
  setNewUploadState: (state) => set({ newUploadState: state }),

  applyCompletedDrawing: (drawing, side) => {
    const isOld = side === "old";
    const other = isOld ? get().newDrawing : get().oldDrawing;

    // The room's two slots must hold two revisions of ONE drawing. Without this, an
    // unrelated file ingests cleanly and produces a full comparison in which every value
    // differs — confident, complete, and meaningless.
    if (other && isDrawingPairMismatch(drawing.drawing_numbers, other.drawing_numbers)) {
      const message = describeDrawingPairMismatch(
        drawing.drawing_numbers ?? [],
        other.drawing_numbers ?? [],
        other.file_name
      );

      // Discard the drawing that was just ingested — not the one already in the room. The
      // rejected upload is the user's mistake and the slot it targeted is unambiguous, which
      // is what makes deleting here safe (§ room-owned drawings: deletion belongs only where
      // intent is explicit). Best-effort: a lingering record is better than a lost one, and
      // the slot is cleared either way so it can never be compared.
      deleteDrawing(drawing.id).catch((err) =>
        console.warn(`Failed to delete rejected drawing ${drawing.id}:`, err)
      );

      if (isOld) {
        set({
          oldDrawing: null,
          oldUploadState: "failed",
          oldUploadProgress: 0,
          oldError: message,
          activeOldJobId: null,
        });
      } else {
        set({
          newDrawing: null,
          newUploadState: "failed",
          newUploadProgress: 0,
          newError: message,
          activeNewJobId: null,
        });
      }

      set((prev) => {
        const existing = prev.uploadQueue.find((q) => q.side === side);
        const entry: QueueEntry = {
          id: existing?.id || Math.random().toString(36).substring(7),
          file_name: existing?.file_name || drawing.file_name,
          side,
          status: "failed",
          progress: 0,
          error: message,
        };
        return {
          uploadQueue: [...prev.uploadQueue.filter((q) => q.side !== side), entry],
          compatibilityStatus: "Mismatch",
        };
      });

      return false;
    }

    // setOldDrawing/setNewDrawing own the rest: layers, annotations, zone regions and the
    // compatibility recalc all hang off them.
    if (isOld) {
      set({ oldUploadState: "completed", oldUploadProgress: 100, oldError: null, activeOldJobId: null });
      get().setOldDrawing(drawing);
    } else {
      set({ newUploadState: "completed", newUploadProgress: 100, newError: null, activeNewJobId: null });
      get().setNewDrawing(drawing);
    }
    return true;
  },

  clearUpload: (side) => {
    if (side === "old") {
      set({
        oldDrawing: null,
        oldUploadState: "idle",
        oldUploadProgress: 0,
        oldFileName: null,
        oldFileSize: null,
        oldError: null,
        activeOldJobId: null,
      });
    } else {
      set({
        newDrawing: null,
        newUploadState: "idle",
        newUploadProgress: 0,
        newFileName: null,
        newFileSize: null,
        newError: null,
        activeNewJobId: null,
      });
    }
    // Update queue
    set((state) => ({
      uploadQueue: state.uploadQueue.filter((q) => q.side !== side),
      activeSessionId: null,
      auditStatus: "idle",
      violations: [],
      complianceScore: null,
      aiScanProgress: "idle",
      aiChecklistResults: {},
      aiScanError: null
    }));
    get().recalculateCompatibility();
  },

  uploadDrawingFile: async (file, side) => {
    const isOld = side === "old";

    // Capture the drawing this slot currently holds BEFORE the reset below nulls
    // it. In the room-owned model each drawing belongs to exactly one slot, so
    // replacing a slot must hard-delete the drawing it displaced (§ room-owned
    // drawings). Deleted only after the new upload succeeds — see step 8.
    const previousDrawingId = (isOld ? get().oldDrawing : get().newDrawing)?.id ?? null;

    // 1. Initial State update
    if (isOld) {
      set({
        oldUploadState: "validating",
        oldUploadProgress: 10,
        oldFileName: file.name,
        oldFileSize: file.size,
        oldError: null,
        oldDrawing: null,
        activeSessionId: null,
        auditStatus: "idle",
        violations: [],
        complianceScore: null,
        aiScanProgress: "idle",
        aiChecklistResults: {},
        aiScanError: null
      });
    } else {
      set({
        newUploadState: "validating",
        newUploadProgress: 10,
        newFileName: file.name,
        newFileSize: file.size,
        newError: null,
        newDrawing: null,
        activeSessionId: null,
        auditStatus: "idle",
        violations: [],
        complianceScore: null,
        aiScanProgress: "idle",
        aiChecklistResults: {},
        aiScanError: null
      });
    }

    const updateStatus = (state: UploadState, progress: number, errorMsg: string | null = null) => {
      if (isOld) {
        set({ oldUploadState: state, oldUploadProgress: progress, oldError: errorMsg });
      } else {
        set({ newUploadState: state, newUploadProgress: progress, newError: errorMsg });
      }
      
      // Keep queue in sync
      set((prev) => {
        const existing = prev.uploadQueue.find((q) => q.side === side);
        const entry: QueueEntry = {
          id: existing?.id || Math.random().toString(36).substring(7),
          file_name: file.name,
          side,
          status: state,
          progress,
          error: errorMsg || undefined,
        };
        const filtered = prev.uploadQueue.filter((q) => q.side !== side);
        return { uploadQueue: [...filtered, entry] };
      });
    };

    // 2. Validate Extension Normalized to Lowercase
    const extension = file.name.split(".").pop()?.toLowerCase();
    const is3D = ["step", "stp", "iges", "igs", "icd", "sldprt", "sldasm"].includes(extension || "");
    const is2D = ["dwg", "dxf", "pdf"].includes(extension || "");
    
    if (!extension || (!is2D && !is3D)) {
      updateStatus("failed", 0, "Unsupported format. Only 2D (PDF, DWG, DXF) or 3D (STEP, IGES, ICD, SolidWorks sldprt/sldasm) files are allowed.");
      set({ compatibilityStatus: "Unsupported" });
      return false;
    }

    // 3. Validate File Size Configurable Limits
    if (file.size > MAX_FILE_SIZE_BYTES) {
      updateStatus("failed", 0, `File exceeds the maximum limit.`);
      return false;
    }

    // 4. Executable magic bytes verification (MZ Header check)
    try {
      const slice = file.slice(0, 2);
      const isExecutable = await new Promise<boolean>((resolve) => {
        const reader = new FileReader();
        reader.onloadend = (e) => {
          if (e.target?.readyState === FileReader.DONE) {
            const arr = new Uint8Array(e.target.result as ArrayBuffer);
            if (arr.length >= 2 && arr[0] === 0x4D && arr[1] === 0x5A) {
              resolve(true); // PE "MZ" executable binary
              return;
            }
          }
          resolve(false);
        };
        reader.readAsArrayBuffer(slice);
      });

      if (isExecutable) {
        updateStatus("failed", 0, "Security Violation: Executable binaries are strictly prohibited.");
        return false;
      }
    } catch (e) {
      updateStatus("failed", 0, "Failed sandboxed file validation scanning.");
      return false;
    }

    // 5. Check compatibility mismatch with other loaded drawing
    const otherDrawing = isOld ? get().newDrawing : get().oldDrawing;
    if (otherDrawing) {
      const otherExt = otherDrawing.file_name.split(".").pop()?.toLowerCase() || "";
      if (otherExt !== extension) {
        updateStatus("failed", 0, `Format Mismatch: Can only compare matching extensions (${otherExt.toUpperCase()} vs ${extension.toUpperCase()}).`);
        set({ compatibilityStatus: "Mismatch" });
        return false;
      }
    }

    // 6. Generate SHA-256 Hash using browser Web Crypto APIs
    // REMOVED: Client-side hashing forces the entire file into RAM (OOM crash for large files).
    // The FastAPI backend securely computes the SHA-256 hash automatically via stream chunking.

    // 7. Initiate HTTP multipart upload to local FastAPI sandbox
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

      // The new drawing is now persisted on the backend. Purge the one this slot
      // displaced (room-owned: no orphans). Best-effort — a lingering drawing is
      // far better than throwing away a good upload, so failures are logged only.
      if (previousDrawingId && previousDrawingId !== drawing.id) {
        deleteDrawing(previousDrawingId).catch((err) =>
          console.warn(`Failed to delete replaced drawing ${previousDrawingId}:`, err)
        );
      }

      // 8. Poll Stage 1 background conversion and schema parsing pipeline
      // Offloaded to useUploadJobPolling hook!
      if (job.status === "completed") {
        // Goes through the same gate as the polled path — a drawing that is not a revision
        // of the room's other slot is rejected and deleted here too.
        if (!get().applyCompletedDrawing(drawing, side)) {
          return false;
        }
      } else if (job.status === "failed") {
        throw new Error(job.error_message || "Background extraction job aborted.");
      } else {
        // We set the active job ID and the React hook `useUploadJobPolling` takes over polling
        // NOTE: we need to add activeOldUploadJobId / activeNewUploadJobId to the store for this to work natively
        if (isOld) {
            set({ oldUploadState: "processing", oldUploadProgress: 80, activeOldJobId: job.id });
        } else {
            set({ newUploadState: "processing", newUploadProgress: 80, activeNewJobId: job.id });
        }
        
        return true; // We successfully queued the upload, polling handles the rest
      }

      if (job.status === "completed") {
        get().recalculateCompatibility();
      }
      return true;

    } catch (err: any) {
      updateStatus("failed", 0, err.message || "Failed to process drawing ingestion.");
      return false;
    }
  },

  recalculateCompatibility: () => {
    const { oldDrawing, newDrawing } = get();
    if (!oldDrawing && !newDrawing) {
      set({ compatibilityStatus: "Idle" });
      return;
    }

    const formats = ["dwg", "dxf", "pdf", "step", "stp", "iges", "igs", "icd", "sldprt", "sldasm"];

    if (oldDrawing && newDrawing) {
      const extOld = oldDrawing.file_name.split(".").pop()?.toLowerCase();
      const extNew = newDrawing.file_name.split(".").pop()?.toLowerCase();
      
      if (extOld !== extNew) {
        set({ compatibilityStatus: "Mismatch" });
      } else if (!formats.includes(extOld || "")) {
        set({ compatibilityStatus: "Unsupported" });
      } else {
        set({ compatibilityStatus: "Compatible" });
      }
    } else {
      // Just one loaded
      const active = oldDrawing || newDrawing;
      const ext = active?.file_name.split(".").pop()?.toLowerCase() || "";
      if (!formats.includes(ext)) {
        set({ compatibilityStatus: "Unsupported" });
      } else {
        set({ compatibilityStatus: "Idle" });
      }
    }
  },
});
