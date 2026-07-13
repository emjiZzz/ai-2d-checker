import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchAuditSession } from "../services/auditApi";
import { auditKeys } from "../services/queryKeys";
import { useAuditStore } from "../stores/auditStore";

/**
 * Polls for audit session status.
 * Syncs the result into `auditStore`.
 */
export function useAuditPolling(sessionId: string | null) {
  const query = useQuery({
    queryKey: sessionId ? auditKeys.sessionDetail(sessionId) : [],
    queryFn: ({ signal }) => fetchAuditSession(sessionId!, signal),
    enabled: !!sessionId,
    refetchInterval: (query) => {
      const status = query.state?.data?.status;
      if (status === "completed" || status === "failed") {
        return false;
      }
      return 1500;
    },
    staleTime: 0,
  });

  // Sync back to Zustand
  useEffect(() => {
    if (query.data && sessionId) {
      const state = useAuditStore.getState();
      const session = query.data;

      state._setActiveSession(session);

      if (session.status === "completed") {
        console.info(`Audit session ${sessionId} successfully completed.`);
        state._setAuditState("completed");
        state.fetchViolations(sessionId);
        state.fetchDiagnostics(sessionId);
        state.fetchSessions();
      } else if (session.status === "failed") {
        const err = session.error_message || "Audit session pipeline crashed.";
        console.error(`Audit session ${sessionId} failed: ${err}`);
        state._setAuditState("failed", err);
        state.fetchSessions();
      }
    }
  }, [query.data, sessionId]);

  return query;
}
