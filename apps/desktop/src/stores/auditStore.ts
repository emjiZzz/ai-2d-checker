import { create } from "zustand";
import { useConnectionStore } from "./connectionStore";
import { logger } from "../services/logger";

export interface StandardDocument {
  id: string;
  name: string;
  file_path: string;
  standard_hash: string;
  file_size_bytes: number;
  format: string;
  category: string | null;
  description: string | null;
  metadata: Record<string, any>;
  created_at: string;
  scope?: string;
  client_name?: string | null;
}

export interface AuditSession {
  id: string;
  drawing_id: string;
  standard_id?: string | null;
  client_name?: string | null;
  status: string;
  compliance_score: number | null;
  confidence_score: number | null;
  error_message: string | null;
  timings: Record<string, number>;
  diagnostics: Record<string, any>;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface AuditViolation {
  id: string;
  audit_session_id: string;
  severity: string;
  category: string;
  description: string;
  recommendation: string;
  affected_entities: Array<Record<string, any>>;
  confidence: number;
  source: string;
  coordinates: number[][] | null;
  standard_reference: string | null;
  pen_type: string;
  is_resolved: boolean;
  resolved_at: string | null;
  checker_remarks: string | null;
  created_at: string;
}

interface AuditState {
  standards: StandardDocument[];
  activeStandard: StandardDocument | null;
  activeSession: AuditSession | null;
  activeViolations: AuditViolation[];
  activeDiagnostics: Record<string, any> | null;
  uploadStatus: "idle" | "uploading" | "success" | "error";
  uploadProgress: number;
  auditState: "idle" | "processing" | "completed" | "failed";
  errorMessage: string | null;
  pollingIntervalId: number | null;

  // Actions
  fetchStandards: () => Promise<void>;
  uploadStandard: (file: File, name: string, category?: string, description?: string, scope?: string, clientName?: string) => Promise<boolean>;
  launchAudit: (drawingId: string, standardId: string) => Promise<boolean>;
  pollAuditStatus: (sessionId: string) => void;
  fetchSessionDetails: (sessionId: string) => Promise<void>;
  fetchViolations: (sessionId: string) => Promise<void>;
  fetchDiagnostics: (sessionId: string) => Promise<void>;
  resetStore: () => void;
}

export const useAuditStore = create<AuditState>((set, get) => ({
  standards: [],
  activeStandard: null,
  activeSession: null,
  activeViolations: [],
  activeDiagnostics: null,
  uploadStatus: "idle",
  uploadProgress: 0,
  auditState: "idle",
  errorMessage: null,
  pollingIntervalId: null,

  fetchStandards: async () => {
    const { backendUrl, apiToken } = useConnectionStore.getState();
    try {
      const headers: Record<string, string> = { "Accept": "application/json" };
      if (apiToken) {
        headers["Authorization"] = `Bearer ${apiToken}`;
      }

      const response = await fetch(`${backendUrl}/api/v1/standards`, { headers });
      if (!response.ok) {
        throw new Error(`Fetch standards failed: HTTP ${response.status}`);
      }

      const result = await response.json();
      if (result.success && result.data) {
        set({ standards: result.data });
      }
    } catch (err: any) {
      logger.warn(`Failed to fetch engineering standards list: ${err.message}`);
    }
  },

  uploadStandard: async (file: File, name: string, category = "", description = "", scope = "universal", clientName = "") => {
    const { backendUrl, apiToken } = useConnectionStore.getState();
    
    set({
      uploadStatus: "uploading",
      uploadProgress: 10,
      errorMessage: null,
    });

    logger.info(`Uploading engineering standard: ${name} (${file.name}) [Scope: ${scope}]`);

    const formData = new FormData();
    formData.append("file", file);
    formData.append("name", name);
    if (category) formData.append("category", category);
    if (description) formData.append("description", description);
    formData.append("scope", scope);
    if (clientName && scope === "client_specific") formData.append("client_name", clientName);

    try {
      const headers: Record<string, string> = {};
      if (apiToken) {
        headers["Authorization"] = `Bearer ${apiToken}`;
      }

      return new Promise<boolean>((resolve) => {
        const xhr = new XMLHttpRequest();
        xhr.open("POST", `${backendUrl}/api/v1/standards/upload`);
        
        for (const [key, value] of Object.entries(headers)) {
          xhr.setRequestHeader(key, value);
        }

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
                logger.info(`Standard ingested successfully: ${response.data.name}`);
                set({
                  uploadStatus: "success",
                  uploadProgress: 100,
                  activeStandard: response.data
                });
                await get().fetchStandards();
                resolve(true);
              } else {
                const errMsg = response.error?.message || "Invalid response format";
                set({ uploadStatus: "error", errorMessage: errMsg, uploadProgress: 0 });
                resolve(false);
              }
            } catch {
              set({ uploadStatus: "error", errorMessage: "Failed to parse server response.", uploadProgress: 0 });
              resolve(false);
            }
          } else {
            let errMsg = `Upload failed with status: ${xhr.status}`;
            try {
              const errResp = JSON.parse(xhr.responseText);
              errMsg = errResp.detail || errResp.error?.message || errMsg;
            } catch {}
            set({ uploadStatus: "error", errorMessage: errMsg, uploadProgress: 0 });
            resolve(false);
          }
        };

        xhr.onerror = () => {
          set({
            uploadStatus: "error",
            errorMessage: "Network error occurred during standard upload.",
            uploadProgress: 0
          });
          resolve(false);
        };

        xhr.send(formData);
      });
    } catch (err: any) {
      set({ uploadStatus: "error", errorMessage: err.message, uploadProgress: 0 });
      return false;
    }
  },

  launchAudit: async (drawingId: string, standardId: string) => {
    const { backendUrl, apiToken } = useConnectionStore.getState();
    
    set({
      auditState: "processing",
      errorMessage: null,
      activeSession: null,
      activeViolations: [],
      activeDiagnostics: null
    });

    logger.info(`Launching compliance audit: Drawing ID ${drawingId} vs Standard ID ${standardId}`);

    try {
      const headers: Record<string, string> = {
        "Accept": "application/json",
        "Content-Type": "application/json"
      };
      if (apiToken) {
        headers["Authorization"] = `Bearer ${apiToken}`;
      }

      const response = await fetch(`${backendUrl}/api/v1/audits/launch`, {
        method: "POST",
        headers,
        body: JSON.stringify({ drawing_id: drawingId, standard_id: standardId })
      });

      if (!response.ok) {
        let errMsg = `Launch request failed: HTTP ${response.status}`;
        try {
          const errResp = await response.json();
          errMsg = errResp.detail || errResp.error?.message || errMsg;
        } catch {}
        throw new Error(errMsg);
      }

      const result = await response.json();
      if (result.success && result.data) {
        const session: AuditSession = result.data;
        set({ activeSession: session });
        get().pollAuditStatus(session.id);
        return true;
      } else {
        const errMsg = result.error?.message || "Failed to initialize audit session.";
        set({ auditState: "failed", errorMessage: errMsg });
        return false;
      }

    } catch (err: any) {
      logger.error(`Audit launch exception: ${err.message}`);
      set({ auditState: "failed", errorMessage: err.message });
      return false;
    }
  },

  pollAuditStatus: (sessionId: string) => {
    const { pollingIntervalId } = get();
    if (pollingIntervalId) {
      window.clearInterval(pollingIntervalId);
    }

    set({ auditState: "processing" });
    const { backendUrl, apiToken } = useConnectionStore.getState();

    const intervalId = window.setInterval(async () => {
      try {
        const headers: Record<string, string> = { "Accept": "application/json" };
        if (apiToken) {
          headers["Authorization"] = `Bearer ${apiToken}`;
        }

        const response = await fetch(`${backendUrl}/api/v1/audits/sessions/${sessionId}`, { headers });
        if (!response.ok) {
          throw new Error(`Audit poll failed: HTTP ${response.status}`);
        }

        const result = await response.json();
        if (result.success && result.data) {
          const session: AuditSession = result.data;
          set({ activeSession: session });

          if (session.status === "completed") {
            logger.info(`Audit session ${sessionId} successfully completed.`);
            window.clearInterval(intervalId);
            set({
              pollingIntervalId: null,
              auditState: "completed"
            });
            await get().fetchViolations(sessionId);
            await get().fetchDiagnostics(sessionId);
          } else if (session.status === "failed") {
            const err = session.error_message || "Audit session pipeline crashed.";
            logger.error(`Audit session ${sessionId} failed: ${err}`);
            window.clearInterval(intervalId);
            set({
              pollingIntervalId: null,
              auditState: "failed",
              errorMessage: err
            });
          }
        }
      } catch (err: any) {
        logger.warn(`Audit polling transient connection issue: ${err.message}`);
      }
    }, 1500);

    set({ pollingIntervalId: intervalId });
  },

  fetchSessionDetails: async (sessionId: string) => {
    const { backendUrl, apiToken } = useConnectionStore.getState();
    try {
      const headers: Record<string, string> = { "Accept": "application/json" };
      if (apiToken) {
        headers["Authorization"] = `Bearer ${apiToken}`;
      }

      const response = await fetch(`${backendUrl}/api/v1/audits/sessions/${sessionId}`, { headers });
      if (response.ok) {
        const result = await response.json();
        if (result.success) {
          set({ activeSession: result.data });
        }
      }
    } catch (err: any) {
      logger.warn(`Failed to fetch session details: ${err.message}`);
    }
  },

  fetchViolations: async (sessionId: string) => {
    const { backendUrl, apiToken } = useConnectionStore.getState();
    try {
      const headers: Record<string, string> = { "Accept": "application/json" };
      if (apiToken) {
        headers["Authorization"] = `Bearer ${apiToken}`;
      }

      const response = await fetch(`${backendUrl}/api/v1/audits/sessions/${sessionId}/violations`, { headers });
      if (response.ok) {
        const result = await response.json();
        if (result.success && result.data) {
          set({ activeViolations: result.data });
        }
      }
    } catch (err: any) {
      logger.warn(`Failed to fetch session violations: ${err.message}`);
    }
  },

  fetchDiagnostics: async (sessionId: string) => {
    const { backendUrl, apiToken } = useConnectionStore.getState();
    try {
      const headers: Record<string, string> = { "Accept": "application/json" };
      if (apiToken) {
        headers["Authorization"] = `Bearer ${apiToken}`;
      }

      const response = await fetch(`${backendUrl}/api/v1/audits/sessions/${sessionId}/diagnostics`, { headers });
      if (response.ok) {
        const result = await response.json();
        if (result.success) {
          set({ activeDiagnostics: result.data });
        }
      }
    } catch (err: any) {
      logger.warn(`Failed to fetch session diagnostics: ${err.message}`);
    }
  },

  resetStore: () => {
    const { pollingIntervalId } = get();
    if (pollingIntervalId) {
      window.clearInterval(pollingIntervalId);
    }
    set({
      activeStandard: null,
      activeSession: null,
      activeViolations: [],
      activeDiagnostics: null,
      uploadStatus: "idle",
      uploadProgress: 0,
      auditState: "idle",
      errorMessage: null,
      pollingIntervalId: null
    });
  }
}));
