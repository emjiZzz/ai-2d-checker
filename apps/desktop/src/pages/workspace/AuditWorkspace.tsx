import React, { useEffect } from "react";
import { useWorkspaceStore, DrawingItem } from "../../stores/workspaceStore";
import { useAuthStore } from "../../stores/authStore";
import { useAuditStore } from "../../stores/auditStore";
import { useNavStore } from "../../stores/navStore";
import { buildHeaders, baseUrl, parseOrThrow } from "../../services/fetchUtils";
import { useRoomStore } from "../../stores/roomStore";

// Sub-view component imports (Phase 1 refactor)
import { WorkspaceView } from "./WorkspaceView";
import { HistoryView } from "./HistoryView";
import { SettingsView } from "./SettingsView";
import { StandardsView } from "./StandardsView";
import { RoomsView } from "./RoomsView";
import { InteractiveTourOverlay } from "../../components/ui/InteractiveTourOverlay";
import { useDrawingsList } from "../../hooks/useDrawings";
import { fetchDrawing } from "../../services/drawingsApi";
import { useUploadJobPolling } from "../../hooks/useUploadJobPolling";
import { isPrototypeMode } from "../../config/features";

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

  const { activeRoom, updateRoom } = useRoomStore();

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

  // See the twin in TwoDWorkspace: prototype builds render before any room is opened, so the
  // hydration flag has to be lifted here too. Through the named action — `useWorkspaceStore
  // .setState` is what eslint.config.js's single rule exists to forbid.
  const setHasHydrated = useWorkspaceStore((s) => s.setHasHydrated);
  useEffect(() => {
    if (isPrototypeMode()) {
      setHasHydrated(true);
    }
  }, [setHasHydrated]);

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
          active_old_drawing_name: oldDrawing?.file_name || null,
          active_new_drawing_name: newDrawing?.file_name || null,
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

      {/* 2D workspace is kept MOUNTED while a room is active and merely hidden
          when off-tab, so returning to it doesn't re-fetch layers + the
          background PNG or rebuild the canvas. Only 2D is kept warm; 3D still
          unmounts below. The inner WorkspaceView is pinned to "workspace" so
          this instance always renders the 2D canvas regardless of the tab.
          `hidden` collapses the canvas to 0x0, but its ResizeObserver restores
          the size on re-show and no redraws run while hidden. */}
      {activeRoom && (
        <div className={`flex-col w-full h-full ${currentNav === "workspace" ? "flex" : "hidden"}`}>
          <WorkspaceView currentNav="workspace" />
        </div>
      )}

      {currentNav === "workspace" && !activeRoom && (
        <RoomsView />
      )}

      {/* 3D workspace is intentionally not Room-gated: it runs on its own
          useThreeDStore, separate from the workspaceStore state Rooms sync
          (oldDrawing/newDrawing/activeSessionId). There's no "3D room" state
          model to gate into yet — confirmed decision, not an oversight. */}
      {currentNav === "3d-workspace" && (
        <div className="flex flex-col w-full h-full">
          <WorkspaceView currentNav={currentNav} />
        </div>
      )}

      {/* ── Global Interactive Spotlight Tour Overlay ── */}
      <InteractiveTourOverlay />
    </div>
  );
};
