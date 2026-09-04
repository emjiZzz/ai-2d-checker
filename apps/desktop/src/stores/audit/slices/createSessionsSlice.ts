import { StateCreator } from "zustand";
import { AuditState, SessionsSlice, AuditSession } from "../types";
import { useAuthStore } from "../../authStore";
import { logger } from "../../../services/logger";
import { buildHeaders, baseUrl, parseOrThrow } from "../../../services/fetchUtils";

export const createSessionsSlice: StateCreator<AuditState, [], [], SessionsSlice> = (set, get) => ({
  sessions: [],
  activeSession: null,
  activeViolations: [],
  activeDiagnostics: null,
  auditState: "idle",
  errorMessage: null,

  launchAudit: async (drawingId: string, standardId: string) => {
    set({
      auditState: "processing",
      errorMessage: null,
      activeSession: null,
      activeViolations: [],
      activeDiagnostics: null
    });

    logger.info(`Launching compliance audit: Drawing ID ${drawingId} vs Standard ID ${standardId}`);

    try {
      const response = await fetch(`${baseUrl()}/api/v1/audits/launch`, {
        method: "POST",
        headers: buildHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ drawing_id: drawingId, standard_id: standardId })
      });
      const data = await parseOrThrow<any>(response);

      const session: AuditSession = data;
      set({ activeSession: session, auditState: "processing" });
      await get().fetchSessions();
      // useAuditPolling hook will pick this up automatically
      return true;

    } catch (err: any) {
      logger.error(`Audit launch exception: ${err.message}`);
      set({ auditState: "failed", errorMessage: err.message });
      return false;
    }
  },
  _setActiveSession: (session) => set({ activeSession: session }),
  _setAuditState: (state, error) => set({ auditState: state, errorMessage: error || null }),

  fetchSessionDetails: async (sessionId: string) => {
    try {
      const response = await fetch(`${baseUrl()}/api/v1/audits/sessions/${sessionId}`, { headers: buildHeaders() });
      const data = await parseOrThrow<any>(response);
      set({ activeSession: data });
    } catch (err: any) {
      logger.warn(`Failed to fetch session details: ${err.message}`);
    }
  },

  fetchViolations: async (sessionId: string) => {
    try {
      const response = await fetch(`${baseUrl()}/api/v1/audits/sessions/${sessionId}/violations`, { headers: buildHeaders() });
      const data = await parseOrThrow<any>(response);
      set({ activeViolations: data });
    } catch (err: any) {
      logger.warn(`Failed to fetch session violations: ${err.message}`);
    }
  },

  fetchDiagnostics: async (sessionId: string) => {
    try {
      const response = await fetch(`${baseUrl()}/api/v1/audits/sessions/${sessionId}/diagnostics`, { headers: buildHeaders() });
      const data = await parseOrThrow<any>(response);
      set({ activeDiagnostics: data });
    } catch (err: any) {
      logger.warn(`Failed to fetch session diagnostics: ${err.message}`);
    }
  },

  fetchSessions: async () => {
    try {
      const currentUser = useAuthStore.getState().user?.username;
      let url = `/api/v1/audits/sessions`;
      if (currentUser) {
        url += `?username=${encodeURIComponent(currentUser)}`;
      }

      const response = await fetch(`${baseUrl()}${url}`, { headers: buildHeaders() });
      const data = await parseOrThrow<any>(response);
      set({ sessions: data });
    } catch (err: any) {
      logger.warn(`Failed to fetch audit sessions archive: ${err.message}`);
    }
  },

  deleteSession: async (id: string) => {
    try {
      const response = await fetch(`${baseUrl()}/api/v1/audits/sessions/${id}`, {
        method: "DELETE",
        headers: buildHeaders()
      });
      await parseOrThrow(response);
      
      set((state) => ({
        sessions: state.sessions.filter((s) => s.id !== id),
        activeSession: state.activeSession?.id === id ? null : state.activeSession,
        activeViolations: state.activeSession?.id === id ? [] : state.activeViolations,
        activeDiagnostics: state.activeSession?.id === id ? null : state.activeDiagnostics,
      }));
      return true;
    } catch (err: any) {
      logger.warn(`Failed to delete session ${id}: ${err.message}`);
      return false;
    }
  },

  updateSession: async (id: string, remarks: string) => {
    try {
      const response = await fetch(`${baseUrl()}/api/v1/audits/sessions/${id}`, {
        method: "PATCH",
        headers: buildHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ remarks })
      });
      const data = await parseOrThrow<any>(response);
      
      set((state) => ({
        sessions: state.sessions.map((s) => s.id === id ? data : s),
        activeSession: state.activeSession?.id === id ? data : state.activeSession,
      }));
      return true;
    } catch (err: any) {
      logger.warn(`Failed to update session remarks for ${id}: ${err.message}`);
      return false;
    }
  },

  resetStore: () => {
    set({
      activeStandard: null,
      activeSession: null,
      activeViolations: [],
      activeDiagnostics: null,
      uploadStatus: "idle",
      uploadProgress: 0,
      auditState: "idle",
      errorMessage: null
    });
  }
});
