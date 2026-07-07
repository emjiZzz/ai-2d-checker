import React, { useState, useEffect } from "react";
import { useWorkspaceStore, DrawingItem } from "../../stores/workspaceStore";
import { useConnectionStore } from "../../stores/connectionStore";
import { useAuthStore } from "../../stores/authStore";
import { useAuditStore } from "../../stores/auditStore";
import { useNavStore } from "../../stores/navStore";

// Sub-view component imports (Phase 1 refactor)
import { WorkspaceView } from "./WorkspaceView";
import { HistoryView } from "./HistoryView";
import { SettingsView } from "./SettingsView";
import { StandardsView } from "./StandardsView";
import "./AuditWorkspace.css";

export const AuditWorkspace: React.FC = () => {
  const backendUrl = useConnectionStore((s) => s.backendUrl);
  const apiToken = useConnectionStore((s) => s.apiToken);

  // Selected workspace navigation sub-view
  const { currentNav, setCurrentNav } = useNavStore();
  
  // Local drawing catalog for selections
  const [drawings, setDrawings] = useState<DrawingItem[]>([]);

  // Load drawing metadata from backend database
  useEffect(() => {
    const loadMetadata = async () => {
      try {
        const headers: Record<string, string> = { "Accept": "application/json" };
        if (apiToken) {
          headers["Authorization"] = `Bearer ${apiToken}`;
        }

        const dwgRes = await fetch(`${backendUrl}/api/v1/drawings`, { headers });
        const dwgData = await dwgRes.json();
        if (dwgRes.ok && dwgData.success) {
          setDrawings(dwgData.data && dwgData.data.length > 0 ? dwgData.data : []);
        }
      } catch (err) {
        console.error("Failed to load metadata in auditor workspace:", err);
      }
    };
    loadMetadata();
  }, [backendUrl, apiToken]);

  // Auth: read current user role to enforce access gates
  const user = useAuthStore((s) => s.user);
  const isAdmin = user?.role === "admin";

  const {
    sessions,
    fetchSessions,
    deleteSession,
    updateSession
  } = useAuditStore();

  const { fetchClients } = useWorkspaceStore();

  useEffect(() => {
    fetchClients();
  }, [fetchClients]);

  useEffect(() => {
    if (currentNav === "history") {
      fetchSessions();
    }
  }, [currentNav, fetchSessions]);

  // Handle visual canvas loading from a historical comparison session
  const handleOpenSession = async (session: any) => {
    try {
      const headers: Record<string, string> = { "Accept": "application/json" };
      if (apiToken) {
        headers["Authorization"] = `Bearer ${apiToken}`;
      }

      // Fetch active drawing details (New drawing)
      const drawingRes = await fetch(`${backendUrl}/api/v1/drawings/${session.drawing_id}`, { headers });
      if (!drawingRes.ok) {
        throw new Error(`Drawing details could not be retrieved. The file may have been purged.`);
      }
      const drawingData = await drawingRes.json();
      if (!drawingData.success || !drawingData.data) {
        throw new Error("Failed to load drawing record.");
      }

      // Fetch reference drawing details (Old drawing, if present)
      let referenceDrawingData = null;
      if (session.reference_drawing_id) {
        try {
          const refRes = await fetch(`${backendUrl}/api/v1/drawings/${session.reference_drawing_id}`, { headers });
          if (refRes.ok) {
            const parsedRef = await refRes.json();
            if (parsedRef.success && parsedRef.data) {
              referenceDrawingData = parsedRef.data;
            }
          }
        } catch (refErr) {
          console.warn("Reference drawing failed to fetch or was deleted:", refErr);
        }
      }

      // Fetch violations
      const violationsRes = await fetch(`${backendUrl}/api/v1/audits/sessions/${session.id}/violations`, { headers });
      if (!violationsRes.ok) {
        throw new Error("Failed to retrieve violations logs.");
      }
      const violationsData = await violationsRes.json();
      if (!violationsData.success || !violationsData.data) {
        throw new Error("Failed to parse violations payload.");
      }

      // Load into workspaceStore
      const workspaceStore = useWorkspaceStore.getState();
      workspaceStore.setNewDrawing(drawingData.data);
      if (referenceDrawingData) {
        workspaceStore.setOldDrawing(referenceDrawingData);
      } else {
        workspaceStore.clearUpload("old");
      }

      useWorkspaceStore.setState({
        violations: violationsData.data.map((v: any) => ({
          id: v.id,
          severity: v.severity,
          category: v.category,
          description: v.description,
          recommendation: v.recommendation,
          affected_entities: v.affected_entities,
          confidence: v.confidence,
          coordinates: v.coordinates ? [v.coordinates[0], v.coordinates[1]] : undefined,
          standard_reference: v.standard_reference || undefined,
          pen_type: v.pen_type,
          is_resolved: v.is_resolved,
          resolved_at: v.resolved_at,
          checker_remarks: v.checker_remarks
        })),
        complianceScore: session.compliance_score,
        auditStatus: "completed",
        selectedClient: session.client_name || null
      });

      // Jump back to workspace view
      setCurrentNav("workspace");
    } catch (err: any) {
      alert(`Ingestion Warning: ${err.message}`);
    }
  };

  return (
    <div className="workspace-container">
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

      {(currentNav === "workspace" || currentNav === "3d-workspace") && (
        <WorkspaceView currentNav={currentNav} />
      )}
    </div>
  );
};
