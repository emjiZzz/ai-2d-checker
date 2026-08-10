import { StateCreator } from "zustand";
import { WorkspaceState, AuditSlice } from "../types";
import { useAuditStore } from "../../auditStore";
import { buildHeaders, baseUrl, parseOrThrow } from "../../../services/fetchUtils";

export const createAuditSlice: StateCreator<WorkspaceState, [], [], AuditSlice> = (set, get) => ({
  auditStatus: "idle",
  complianceScore: null,
  violations: [],
  hiddenViolationIds: {},
  selectedViolation: null,
  auditError: null,
  activeSessionId: null,

  selectViolation: (violation) => set({ selectedViolation: violation ? { ...violation } : null }),
  toggleViolationVisibility: (violationId) => set((state) => {
    const hidden = { ...state.hiddenViolationIds };
    if (hidden[violationId]) {
      delete hidden[violationId];
    } else {
      hidden[violationId] = true;
    }
    return { hiddenViolationIds: hidden };
  }),
  setViolationsVisibility: (violationIds, isHidden) => set((state) => {
    const hidden = { ...state.hiddenViolationIds };
    violationIds.forEach(id => {
      if (isHidden) {
        hidden[id] = true;
      } else {
        delete hidden[id];
      }
    });
    return { hiddenViolationIds: hidden };
  }),
  // Fold a supervisor verdict the server has already accepted back into the loaded findings, so
  // the card updates without refetching the session. Takes the values the server stored, never the
  // ones the UI optimistically hoped for.
  applyViolationReview: (violationId, resolution, remarks) => {
    set((state) => ({
      violations: state.violations.map((v) =>
        v.id === violationId
          ? { ...v, resolution_type: resolution, is_resolved: resolution === "APPROVED", checker_remarks: remarks }
          : v
      ),
    }));
  },

  setActiveSessionId: (sessionId) => set({ activeSessionId: sessionId }),

  setViolations: (violations) => {
    set({ violations: violations });
  },

  // Loads a previously-run audit session (from History) back into the active
  // workspace in one atomic write. Added in Phase 8 to replace call sites that
  // were reaching into useWorkspaceStore.setState() directly from page
  // components — see AuditWorkspace.tsx's handleOpenSession.
  loadSessionIntoWorkspace: (sessionId, drawing, referenceDrawing, violations, complianceScore, clientName) => {
    // setNewDrawing/setOldDrawing already clear oldLayers/newLayers synchronously
    // before swapping metadata (fixed at the source, since uploadDrawingFile
    // needs the same guard and doesn't go through these setters) — no separate
    // clear needed here.
    get().setNewDrawing(drawing);
    if (referenceDrawing) {
      get().setOldDrawing(referenceDrawing);
    } else {
      get().clearUpload("old");
    }
    const sanitizedViolations = violations;

    set({
      activeSessionId: sessionId,
      violations: sanitizedViolations,
      hiddenViolationIds: {},
      complianceScore,
      auditStatus: "completed",
      selectedClient: clientName,
    });
  },

  runAudit: async (clientName) => {
    const { newDrawing } = get();
    if (!newDrawing) {
      set({ auditError: "Target engineering drawing must be selected." });
      return false;
    }

    set({ auditStatus: "queued", auditError: null, violations: [], hiddenViolationIds: {}, complianceScore: null, activeSessionId: null });
    const { oldDrawing } = get();

    try {
      const launchRes = await fetch(`${baseUrl()}/api/v1/audits/launch`, {
        method: "POST",
        headers: buildHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          drawing_id: newDrawing.id,
          reference_drawing_id: oldDrawing?.id || null,
          client_name: clientName,
        })
      });
      const launchData = await parseOrThrow<any>(launchRes);

      const sessionId = launchData.id;
      set({ auditStatus: "auditing", activeSessionId: sessionId });

      // Poll session status until completion or failure
      let finished = false;
      let attempts = 0;

      while (!finished && attempts < 30) {
        attempts++;
        await new Promise((r) => setTimeout(r, 1500));

        try {
          const statusRes = await fetch(`${baseUrl()}/api/v1/audits/sessions/${sessionId}`, { headers: buildHeaders() });
          const session = await parseOrThrow<any>(statusRes);

          if (session.status === "completed") {
            finished = true;

            try {
              const violationsRes = await fetch(`${baseUrl()}/api/v1/audits/sessions/${sessionId}/violations`, { headers: buildHeaders() });
              const violationsData = await parseOrThrow<any>(violationsRes);
              
              set({
                violations: violationsData,
                complianceScore: session.compliance_score ?? null,
                auditStatus: "completed",
              });
            } catch {
              set({
                violations: [],
                complianceScore: session.compliance_score ?? null,
                auditStatus: "completed",
              });
            }
            await useAuditStore.getState().fetchSessions();
            return true;
          } else if (session.status === "failed") {
            finished = true;
            set({
              auditStatus: "failed",
              auditError: session.error_message || "Audit completed with failure status.",
            });
            return false;
          }
        } catch {
          // Ignore network errors during polling
        }
      }

      if (!finished) {
        set({
          auditStatus: "failed",
          auditError: "Audit timed out after 45 seconds.",
        });
        return false;
      }

      return true;
    } catch (err) {
      set({ auditStatus: "failed", auditError: "Network connection lost with background audit service." });
      return false;
    }
  },
});
