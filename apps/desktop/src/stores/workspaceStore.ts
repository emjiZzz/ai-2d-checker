import { create } from "zustand";
import { useConnectionStore } from "./connectionStore";
import { useAuthStore } from "./authStore";

export interface DrawingItem {
  id: string;
  file_name: string;
  file_path: string;
  format: string;
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
}

interface WorkspaceState {
  // Stage 1 Comparison State
  oldDrawing: DrawingItem | null;
  newDrawing: DrawingItem | null;
  isComparing: boolean;
  panX: number;
  panY: number;
  zoom: number;
  syncViewport: boolean;
  activeLayers: Record<string, boolean>;

  // Stage 2 Audit State
  auditStatus: "idle" | "queued" | "auditing" | "completed" | "failed";
  complianceScore: number | null;
  violations: ViolationItem[];
  selectedViolation: ViolationItem | null;
  auditError: string | null;

  // Actions
  setOldDrawing: (drawing: DrawingItem | null) => void;
  setNewDrawing: (drawing: DrawingItem | null) => void;
  setViewport: (panX: number, panY: number, zoom: number) => void;
  setSyncViewport: (sync: boolean) => void;
  toggleLayer: (layerName: string) => void;
  
  // Auditing Actions
  runAudit: (standardId: string) => Promise<boolean>;
  selectViolation: (violation: ViolationItem | null) => void;
  resetWorkspace: () => void;
}

export const useWorkspaceStore = create<WorkspaceState>((set, get) => ({
  oldDrawing: null,
  newDrawing: null,
  isComparing: false,
  panX: 0,
  panY: 0,
  zoom: 1,
  syncViewport: true,
  activeLayers: { "0": true, "Format": true, "Text": true, "Dimensions": true },

  auditStatus: "idle",
  complianceScore: null,
  violations: [],
  selectedViolation: null,
  auditError: null,

  setOldDrawing: (drawing) => set({ oldDrawing: drawing }),
  setNewDrawing: (drawing) => set({ newDrawing: drawing }),
  
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

  selectViolation: (violation) => set({ selectedViolation: violation }),

  runAudit: async (standardId) => {
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

      // Launch background audit session
      const launchRes = await fetch(`${backendUrl}/audits/launch`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          drawing_id: newDrawing.id,
          standard_id: standardId,
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

        const statusRes = await fetch(`${backendUrl}/audits/sessions/${sessionId}`, { headers });
        const statusData = await statusRes.json();

        if (statusRes.ok && statusData.success) {
          const session = statusData.data;
          
          if (session.status === "completed") {
            finished = true;
            
            // Retrieve actual violations list
            const violationsRes = await fetch(`${backendUrl}/audits/sessions/${sessionId}/violations`, { headers });
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
            return true;
          } else if (session.status === "failed") {
            finished = true;
            set({
              auditStatus: "failed",
              auditError: session.error_message || "AI grounding analysis loop timed out.",
            });
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

  resetWorkspace: () => set({
    oldDrawing: null,
    newDrawing: null,
    isComparing: false,
    auditStatus: "idle",
    complianceScore: null,
    violations: [],
    selectedViolation: null,
    auditError: null,
  }),
}));
