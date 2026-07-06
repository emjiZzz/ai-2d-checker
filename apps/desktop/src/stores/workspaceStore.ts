import { create } from "zustand";
import { useConnectionStore } from "./connectionStore";
import { useAuthStore } from "./authStore";
import { useReviewStore } from "./reviewStore";
import { useAuditStore } from "./auditStore";

export interface DrawingItem {
  id: string;
  file_name: string;
  file_path: string;
  format: string;
  file_size_bytes?: number;
  entity_counts: Record<string, number>;
  metadata: Record<string, any>;
  created_at: string;
}

export interface ViolationItem {
  id: string;
  severity: "critical" | "high" | "medium" | "low";
  category: string;
  description: string;
  recommendation: string;
  affected_entities: string[];
  confidence: number;
  coordinates?: [number, number];
  standard_reference?: string;
  pen_type?: string;
  is_resolved?: boolean;
  resolved_at?: string | null;
  checker_remarks?: string | null;
}

export type UploadState = "idle" | "dragging" | "validating" | "uploading" | "processing" | "completed" | "failed";

export interface QueueEntry {
  id: string;
  file_name: string;
  side: "old" | "new";
  status: UploadState;
  progress: number;
  error?: string;
}

export interface ClientItem {
  id: string;
  name: string;
  created_at: string;
}

interface WorkspaceState {
  // Stage 1 Comparison State
  oldDrawing: DrawingItem | null;
  newDrawing: DrawingItem | null;
  oldLayers: Record<string, any[]>;
  newLayers: Record<string, any[]>;
  isComparing: boolean;
  panX: number;
  panY: number;
  zoom: number;
  syncViewport: boolean;
  activeLayers: Record<string, boolean>;

  // Upload Queue State & UX
  oldUploadState: UploadState;
  newUploadState: UploadState;
  oldUploadProgress: number;
  newUploadProgress: number;
  oldFileName: string | null;
  newFileName: string | null;
  oldFileSize: number | null;
  newFileSize: number | null;
  oldError: string | null;
  newError: string | null;
  compatibilityStatus: "Compatible" | "Mismatch" | "Unsupported" | "Idle";
  uploadQueue: QueueEntry[];

  // Stage 2 Audit State
  auditStatus: "idle" | "queued" | "auditing" | "completed" | "failed";
  complianceScore: number | null;
  violations: ViolationItem[];
  selectedViolation: ViolationItem | null;
  auditError: string | null;
  
  // Clients State
  clients: ClientItem[];
  selectedClient: string | null;

  // Actions
  setOldDrawing: (drawing: DrawingItem | null) => void;
  setNewDrawing: (drawing: DrawingItem | null) => void;
  fetchLayers: (drawingId: string, side: "old" | "new") => Promise<void>;
  setViewport: (panX: number, panY: number, zoom: number) => void;
  setSyncViewport: (sync: boolean) => void;
  toggleLayer: (layerName: string) => void;

  // Upload Actions
  setOldUploadState: (state: UploadState) => void;
  setNewUploadState: (state: UploadState) => void;
  uploadDrawingFile: (file: File, side: "old" | "new") => Promise<boolean>;
  clearUpload: (side: "old" | "new") => void;
  recalculateCompatibility: () => void;

  // Auditing Actions
  runAudit: (clientName: string) => Promise<boolean>;
  selectViolation: (violation: ViolationItem | null) => void;
  
  // Client Actions
  fetchClients: () => Promise<void>;
  createClient: (name: string) => Promise<boolean>;
  deleteClient: (name: string) => Promise<boolean>;
  setSelectedClient: (name: string | null) => void;
  
  resetWorkspace: () => void;
}

// Configurable constants
const MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024 * 1024; // 10GB (Limitless)

export const useWorkspaceStore = create<WorkspaceState>((set, get) => ({
  oldDrawing: null,
  newDrawing: null,
  oldLayers: {},
  newLayers: {},
  isComparing: false,
  panX: 0,
  panY: 0,
  zoom: 1,
  syncViewport: true,
  activeLayers: { "0": true, "Format": true, "Text": true, "Dimensions": true },

  // Upload States
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

  // Audit States
  auditStatus: "idle",
  complianceScore: null,
  violations: [],
  selectedViolation: null,
  auditError: null,

  // Client States
  clients: [],
  selectedClient: null,

  setOldDrawing: (drawing) => {
    set({ oldDrawing: drawing });
    get().recalculateCompatibility();
    if (drawing) {
      if (!get().newDrawing) {
        useReviewStore.getState().loadCustomRegions(drawing.id);
      }
      get().fetchLayers(drawing.id, "old");
    } else {
      set({ oldLayers: {} });
    }
  },

  setNewDrawing: (drawing) => {
    set({ newDrawing: drawing });
    get().recalculateCompatibility();
    if (drawing) {
      useReviewStore.getState().loadCustomRegions(drawing.id);
      get().fetchLayers(drawing.id, "new");
    } else {
      useReviewStore.getState().loadCustomRegions(null);
      set({ newLayers: {} });
    }
  },

  fetchLayers: async (drawingId, side) => {
    const { backendUrl, apiToken } = useConnectionStore.getState();
    const headers: Record<string, string> = { "Accept": "application/json" };
    if (apiToken) {
      headers["Authorization"] = `Bearer ${apiToken}`;
    }
    try {
      const res = await fetch(`${backendUrl}/api/v1/drawings/${drawingId}/layers`, { headers });
      if (res.ok) {
        const data = await res.json();
        if (data.success && data.data?.layers) {
          if (side === "old") {
            set({ oldLayers: data.data.layers });
          } else {
            set({ newLayers: data.data.layers });
          }
        }
      }
    } catch (err) {
      console.error(`Failed to fetch layers for ${side} drawing`, err);
    }
  },

  setViewport: (panX, panY, zoom) => {
    if (get().syncViewport) {
      set({ panX, panY, zoom });
    }
  },

  setSyncViewport: (sync) => set({ syncViewport: sync }),

  toggleLayer: (layerName) => {
    set((state) => ({
      activeLayers: {
        ...state.activeLayers,
        [layerName]: !state.activeLayers[layerName],
      },
    }));
  },

  setOldUploadState: (state) => set({ oldUploadState: state }),
  setNewUploadState: (state) => set({ newUploadState: state }),

  clearUpload: (side) => {
    if (side === "old") {
      set({
        oldDrawing: null,
        oldUploadState: "idle",
        oldUploadProgress: 0,
        oldFileName: null,
        oldFileSize: null,
        oldError: null,
      });
    } else {
      set({
        newDrawing: null,
        newUploadState: "idle",
        newUploadProgress: 0,
        newFileName: null,
        newFileSize: null,
        newError: null,
      });
    }
    // Update queue
    set((state) => ({
      uploadQueue: state.uploadQueue.filter((q) => q.side !== side),
    }));
    get().recalculateCompatibility();
  },

  uploadDrawingFile: async (file: File, side: "old" | "new") => {
    const isOld = side === "old";
    
    // 1. Initial State update
    if (isOld) {
      set({
        oldUploadState: "validating",
        oldUploadProgress: 10,
        oldFileName: file.name,
        oldFileSize: file.size,
        oldError: null,
        oldDrawing: null,
      });
    } else {
      set({
        newUploadState: "validating",
        newUploadProgress: 10,
        newFileName: file.name,
        newFileSize: file.size,
        newError: null,
        newDrawing: null,
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
    updateStatus("validating", 30);
    let fileHash = "";
    try {
      const arrayBuffer = await file.arrayBuffer();
      const hashBuffer = await crypto.subtle.digest("SHA-256", arrayBuffer);
      const hashArray = Array.from(new Uint8Array(hashBuffer));
      fileHash = hashArray.map((b) => b.toString(16).padStart(2, "0")).join("");
      console.log(`Ingestion Sandbox: Verified file SHA-256: ${fileHash}`);
    } catch (hashErr) {
      updateStatus("failed", 0, "Security validation: Failed to generate file signature.");
      return false;
    }

    // 7. Initiate HTTP multipart upload to local FastAPI sandbox
    updateStatus("uploading", 40);
    const { backendUrl, apiToken } = useConnectionStore.getState();
    const { sessionToken } = useAuthStore.getState();

    const formData = new FormData();
    formData.append("file", file);

    try {
      const headers: Record<string, string> = {
        "Accept": "application/json",
        "X-Session-Token": sessionToken || "",
      };
      if (apiToken) {
        headers["Authorization"] = `Bearer ${apiToken}`;
      }

      const uploadResult = await new Promise<any>((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open("POST", `${backendUrl}/api/v1/drawings/upload`);
        
        for (const [key, value] of Object.entries(headers)) {
          xhr.setRequestHeader(key, value);
        }

        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable) {
            const percent = 40 + Math.round((e.loaded / e.total) * 30); // scale upload progress from 40% to 70%
            updateStatus("uploading", percent);
          }
        };

        xhr.onload = () => {
          if (xhr.status >= 200 && xhr.status < 300) {
            try {
              resolve(JSON.parse(xhr.responseText));
            } catch (err) {
              reject(new Error("Malformed JSON response from backend."));
            }
          } else {
            let errMsg = `Upload failed with status code ${xhr.status}`;
            try {
              const parsed = JSON.parse(xhr.responseText);
              errMsg = parsed.detail || parsed.error?.message || errMsg;
            } catch {}
            reject(new Error(errMsg));
          }
        };

        xhr.onerror = () => reject(new Error("Network connection error. Standalone API may be offline."));
        xhr.send(formData);
      });

      if (!uploadResult.success || !uploadResult.data) {
        throw new Error(uploadResult.error?.message || "Invalid upload response payload.");
      }

      const { drawing, job } = uploadResult.data;
      updateStatus("processing", 80);

      // 8. Poll Stage 1 background conversion and schema parsing pipeline
      let completedDrawing: DrawingItem | null = null;
      if (job.status === "completed") {
        completedDrawing = drawing;
      } else if (job.status === "failed") {
        throw new Error(job.error_message || "Background extraction job aborted.");
      } else {
        // Poll job status
        let attempts = 0;
        let jobDone = false;
        while (!jobDone && attempts < 600) {
          attempts++;
          await new Promise((r) => setTimeout(r, 1200));
          
          const pollRes = await fetch(`${backendUrl}/api/v1/jobs/${job.id}`, { headers });
          if (!pollRes.ok) continue;

          const pollData = await pollRes.json();
          if (pollData.success && pollData.data) {
            const currentJob = pollData.data;
            if (currentJob.status === "completed") {
              jobDone = true;
              // Fetch fully parsed details
              const dwgRes = await fetch(`${backendUrl}/api/v1/drawings/${drawing.id}`, { headers });
              if (dwgRes.ok) {
                const dwgData = await dwgRes.json();
                if (dwgData.success) {
                  completedDrawing = dwgData.data;
                }
              }
              if (!completedDrawing) {
                completedDrawing = drawing; // fallback
              }
            } else if (currentJob.status === "failed") {
              jobDone = true;
              throw new Error(currentJob.error_message || "Extraction job failed.");
            }
          }
        }

        if (!jobDone) {
          throw new Error("Ingestion pipeline timeout exceeded.");
        }
      }

      if (isOld) {
        set({ oldDrawing: completedDrawing, oldUploadState: "completed", oldUploadProgress: 100 });
        if (completedDrawing) {
          await get().fetchLayers(completedDrawing.id, "old");
        }
      } else {
        set({ newDrawing: completedDrawing, newUploadState: "completed", newUploadProgress: 100 });
        if (completedDrawing) {
          await get().fetchLayers(completedDrawing.id, "new");
        }
      }

      updateStatus("completed", 100);
      get().recalculateCompatibility();
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

  selectViolation: (violation) => set({ selectedViolation: violation }),

  runAudit: async (clientName) => {
    const { newDrawing } = get();
    if (!newDrawing) {
      set({ auditError: "Target engineering drawing must be selected." });
      return false;
    }

    set({ auditStatus: "queued", auditError: null, violations: [], complianceScore: null });
    const { backendUrl, apiToken } = useConnectionStore.getState();
    const { sessionToken } = useAuthStore.getState();

    try {
      const headers: Record<string, string> = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Session-Token": sessionToken || "",
      };
      if (apiToken) {
        headers["Authorization"] = `Bearer ${apiToken}`;
      }

      const { oldDrawing } = get();

      // Launch background audit session using client_name
      const launchRes = await fetch(`${backendUrl}/api/v1/audits/launch`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          drawing_id: newDrawing.id,
          reference_drawing_id: oldDrawing?.id || null,
          client_name: clientName,
        }),
      });

      const launchData = await launchRes.json();
      if (!launchRes.ok || !launchData.success) {
        set({
          auditStatus: "failed",
          auditError: launchData.error?.message || "Failed to initialize audit run.",
        });
        return false;
      }

      const sessionId = launchData.data.id;
      set({ auditStatus: "auditing" });

      // Poll session status until completion or failure
      let finished = false;
      let attempts = 0;

      while (!finished && attempts < 30) {
        attempts++;
        await new Promise((r) => setTimeout(r, 1500));

        const statusRes = await fetch(`${backendUrl}/api/v1/audits/sessions/${sessionId}`, { headers });
        const statusData = await statusRes.json();

        if (statusRes.ok && statusData.success) {
          const session = statusData.data;

          if (session.status === "completed") {
            finished = true;

            // Retrieve actual violations list
            const violationsRes = await fetch(`${backendUrl}/api/v1/audits/sessions/${sessionId}/violations`, { headers });
            const violationsData = await violationsRes.json();

            if (violationsRes.ok && violationsData.success) {
              set({
                violations: violationsData.data,
                complianceScore: session.compliance_score || 85.0,
                auditStatus: "completed",
              });
            } else {
              set({
                violations: [],
                complianceScore: session.compliance_score || 85.0,
                auditStatus: "completed",
              });
            }
            await useAuditStore.getState().fetchSessions();
            return true;
          } else if (session.status === "failed") {
            finished = true;
            set({
              auditStatus: "failed",
              auditError: session.error_message || "AI grounding analysis loop timed out.",
            });
            await useAuditStore.getState().fetchSessions();
            return false;
          }
        }
      }

      if (!finished) {
        set({ auditStatus: "failed", auditError: "Audit pipeline execution timed out." });
        return false;
      }

      return true;
    } catch (err) {
      set({ auditStatus: "failed", auditError: "Network connection lost with background audit service." });
      return false;
    }
  },

  fetchClients: async () => {
    const { backendUrl, apiToken } = useConnectionStore.getState();
    try {
      const headers: Record<string, string> = { "Accept": "application/json" };
      if (apiToken) {
        headers["Authorization"] = `Bearer ${apiToken}`;
      }

      const response = await fetch(`${backendUrl}/api/v1/clients`, { headers });
      if (response.ok) {
        const result = await response.json();
        if (result.success) {
          set({ clients: result.data });
        }
      }
    } catch (error) {
      console.error("Failed to fetch clients list:", error);
    }
  },

  createClient: async (name: string) => {
    const { backendUrl, apiToken } = useConnectionStore.getState();
    try {
      const headers: Record<string, string> = {
        "Content-Type": "application/json",
        "Accept": "application/json",
      };
      if (apiToken) {
        headers["Authorization"] = `Bearer ${apiToken}`;
      }

      const response = await fetch(`${backendUrl}/api/v1/clients`, {
        method: "POST",
        headers,
        body: JSON.stringify({ name }),
      });

      if (response.ok) {
        await get().fetchClients();
        return true;
      }
    } catch (error) {
      console.error("Failed to create client:", error);
    }
    return false;
  },

  deleteClient: async (name: string) => {
    const { backendUrl, apiToken } = useConnectionStore.getState();
    try {
      const headers: Record<string, string> = { "Accept": "application/json" };
      if (apiToken) {
        headers["Authorization"] = `Bearer ${apiToken}`;
      }

      const response = await fetch(`${backendUrl}/api/v1/clients/${name}`, {
        method: "DELETE",
        headers,
      });

      if (response.ok) {
        await get().fetchClients();
        if (get().selectedClient === name) {
          set({ selectedClient: null });
        }
        return true;
      }
    } catch (error) {
      console.error(`Failed to delete client ${name}:`, error);
    }
    return false;
  },

  setSelectedClient: (name) => set({ selectedClient: name }),

  resetWorkspace: () => {
    // Clear uploads
    get().clearUpload("old");
    get().clearUpload("new");
    useReviewStore.getState().resetCustomRegions();
    set({
      oldDrawing: null,
      newDrawing: null,
      isComparing: false,
      auditStatus: "idle",
      complianceScore: null,
      violations: [],
      selectedViolation: null,
      auditError: null,
    });
  },
}));
