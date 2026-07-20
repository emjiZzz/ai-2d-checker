import React, { useEffect } from "react";
import { useWorkspaceStore, DrawingItem } from "../../stores/workspaceStore";
import { useAuthStore } from "../../stores/authStore";
import { useAuditStore } from "../../stores/auditStore";
import { useNavStore } from "../../stores/navStore";
import { buildHeaders, baseUrl, parseOrThrow } from "../../services/fetchUtils";
import { useRoomStore } from "../../stores/roomStore";
import { Button } from "../../components/ui/Button";

// Sub-view component imports (Phase 1 refactor)
import { WorkspaceView } from "./WorkspaceView";
import { HistoryView } from "./HistoryView";
import { SettingsView } from "./SettingsView";
import { StandardsView } from "./StandardsView";
import { RoomsView } from "./RoomsView";
import { useDrawingsList } from "../../hooks/useDrawings";
import { fetchDrawing } from "../../services/drawingsApi";
import { useUploadJobPolling } from "../../hooks/useUploadJobPolling";

export const AuditWorkspace: React.FC = () => {
  // Selected workspace navigation sub-view
  const { currentNav, setCurrentNav } = useNavStore();
  
  // Local drawing catalog for selections (via TanStack Query)
  const { data: queryDrawings } = useDrawingsList();
  const drawings = queryDrawings ?? [];

  // Auth: read current user role to enforce access gates
  const user = useAuthStore((s) => s.user);
  const isAdmin = user?.role === "admin";

  const {
    sessions,
    fetchSessions,
    deleteSession,
    updateSession
  } = useAuditStore();

  const { activeRoom, leaveRoom, updateRoom } = useRoomStore();

  const oldDrawing = useWorkspaceStore((s) => s.oldDrawing);
  const newDrawing = useWorkspaceStore((s) => s.newDrawing);
  const activeSessionId = useWorkspaceStore((s) => s.activeSessionId);
  const aiChecklistResults = useWorkspaceStore((s) => s.aiChecklistResults);
  const aiScanProgress = useWorkspaceStore((s) => s.aiScanProgress);

  // Background Upload Polling
  const activeOldJobId = useWorkspaceStore((s) => s.activeOldJobId);
  const activeNewJobId = useWorkspaceStore((s) => s.activeNewJobId);
  
  // Call the polling hook for both sides
  useUploadJobPolling(activeOldJobId, "old");
  useUploadJobPolling(activeNewJobId, "new");

  useEffect(() => {
    if (activeRoom) {
      if (
        activeRoom.active_old_drawing_id !== (oldDrawing?.id || null) ||
        activeRoom.active_new_drawing_id !== (newDrawing?.id || null) ||
        activeRoom.active_audit_session_id !== (activeSessionId || null) ||
        (aiScanProgress === "completed" && JSON.stringify(activeRoom.physical_comparison_results) !== JSON.stringify(aiChecklistResults)) ||
        (aiScanProgress === "idle" && activeRoom.physical_comparison_results !== null)
      ) {
        const payloadToSave = {
          active_old_drawing_id: oldDrawing?.id || null,
          active_new_drawing_id: newDrawing?.id || null,
          active_audit_session_id: activeSessionId || null,
          physical_comparison_results: aiScanProgress === "completed" ? aiChecklistResults : null
        };
        updateRoom(activeRoom.id, payloadToSave);
      }
    }
  }, [activeRoom, oldDrawing?.id, newDrawing?.id, activeSessionId, aiScanProgress, aiChecklistResults, updateRoom]);

  useEffect(() => {
    if (currentNav === "history") {
      fetchSessions();
    }
  }, [currentNav, fetchSessions]);

  // Handle visual canvas loading from a historical comparison session
  const handleOpenSession = async (session: any) => {
    try {
      // Fetch active drawing details (New drawing)
      let drawingData: DrawingItem;
      try {
        drawingData = await fetchDrawing(session.drawing_id);
      } catch {
        throw new Error("Drawing details could not be retrieved. The file may have been purged.");
      }

      // Fetch reference drawing details (Old drawing, if present)
      let referenceDrawingData: DrawingItem | null = null;
      if (session.reference_drawing_id) {
        try {
          referenceDrawingData = await fetchDrawing(session.reference_drawing_id);
        } catch (err: any) {
          console.warn("Reference drawing failed to fetch or was deleted:", err.message);
        }
      }

      // Fetch violations
      const violationsRes = await fetch(`${baseUrl()}/api/v1/audits/sessions/${session.id}/violations`, { headers: buildHeaders() });
      const violationsData = await parseOrThrow<any[]>(violationsRes);

      const mappedViolations = violationsData.map((v: any) => ({
        id: v.id,
        severity: v.severity,
        category: v.category,
        description: v.description,
        recommendation: v.recommendation,
        affected_entities: v.affected_entities,
        confidence: v.confidence,
        coordinates: v.coordinates ? ([v.coordinates[0] as number, v.coordinates[1] as number] as [number, number]) : undefined,
        standard_reference: v.standard_reference || undefined,
        pen_type: v.pen_type,
        is_resolved: v.is_resolved,
        resolved_at: v.resolved_at,
        checker_remarks: v.checker_remarks
      }));

      // Load into workspaceStore via the dedicated action instead of reaching
      // into store internals from a page component (Phase 8).
      useWorkspaceStore.getState().loadSessionIntoWorkspace(
        session.id,
        drawingData,
        referenceDrawingData,
        mappedViolations,
        session.compliance_score ?? null,
        session.client_name || null
      );

      // Jump back to workspace view
      setCurrentNav("workspace");
    } catch (err: any) {
      alert(`Ingestion Warning: ${err.message}`);
    }
  };

  return (
    <div className="flex w-screen h-[calc(100vh-44px)] bg-bg-dark overflow-hidden text-text-primary">
      {/* 2. DYNAMIC WORKSPACE PORT */}
      {currentNav === "standards" && isAdmin && (
        <StandardsView />
      )}

      {currentNav === "history" && (
        <HistoryView
          sessions={sessions}
          drawings={drawings}
          updateSession={updateSession}
          deleteSession={deleteSession}
          setCurrentNav={setCurrentNav}
          handleOpenSession={handleOpenSession}
        />
      )}

      {currentNav === "settings" && (
        <SettingsView />
      )}

      {currentNav === "workspace" && (
        activeRoom ? (
          <div className="flex flex-col w-full h-full">
            <div className="flex items-center justify-between px-4 py-2 bg-bg-dark border-b border-border-color shrink-0">
              <span className="text-sm font-semibold text-text-primary">
                Room: <span className="text-accent-cyan">{activeRoom.name}</span>
              </span>
              <Button variant="ghost" size="sm" onClick={leaveRoom}>← Back to Rooms</Button>
            </div>
            <WorkspaceView currentNav={currentNav} />
          </div>
        ) : (
          <RoomsView />
        )
      )}

      {currentNav === "3d-workspace" && (
        <div className="flex flex-col w-full h-full">
          <WorkspaceView currentNav={currentNav} />
        </div>
      )}
    </div>
  );
};
