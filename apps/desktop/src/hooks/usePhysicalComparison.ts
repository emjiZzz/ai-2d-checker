import { useCallback } from "react";
import { useWorkspaceStore } from "../stores/workspaceStore";
import { useReviewStore } from "../stores/reviewStore";
import { useRoomStore } from "../stores/roomStore";
import { computeBounds } from "../utils/spatialBounds";
import { generateComparisonMarkings } from "../utils/markerGenerator";
import { getComparisonStages, getComparisonTimeoutMs } from "../utils/comparisonStages";
import { buildHeaders, baseUrl, parseOrThrow, streamApi } from "../services/fetchUtils";

export const usePhysicalComparison = () => {
  const {
    oldDrawing,
    newDrawing,
    oldLayers,
    newLayers,
    setViolations,
    aiScanProgress,
    aiChecklistResults,
    aiScanError,
    setAiScanProgress,
    setAiScanProgressPct,
    setAiChecklistResults,
    setAiScanError
  } = useWorkspaceStore();

  const activeRoom = useRoomStore((s) => s.activeRoom);

  const resetComparison = useCallback(() => {
    setAiChecklistResults({});
    setViolations([]);
    setAiScanProgress("idle");
    setAiScanProgressPct(0);
    setAiScanError(null);
  }, [setAiChecklistResults, setViolations, setAiScanProgress, setAiScanProgressPct, setAiScanError]);

  const runPhysicalComparisonAI = async (forceRefresh = false, refreshOcr = false) => {
    if (!oldDrawing || !newDrawing) return;

    setAiScanError(null);
    setAiScanProgressPct(5);

    try {
      const comparisonMethod = activeRoom?.comparison_method ?? "deterministic";
      const stages = getComparisonStages(comparisonMethod);
      if (stages.length > 0) {
        setAiScanProgress(stages[0].id);
      }

      const requestBody = {
        reference_drawing_id: oldDrawing.id,
        drawing_id: newDrawing.id,
        comparison_method: comparisonMethod,
        force_refresh: forceRefresh,
        refresh_ocr: refreshOcr,
      };

      const timeoutMs = getComparisonTimeoutMs(comparisonMethod);
      let streamSucceeded = false;
      let data: any = null;

      // Two failure modes, deliberately handled differently. A TRANSPORT failure (older
      // backend without the /stream route, dropped socket, malformed frame) means we learned
      // nothing about the comparison, so fall back to the plain POST. A backend-REPORTED
      // error means the comparison itself failed — falling back there would re-run the whole
      // pipeline only to fail the same way. That one is rethrown to the outer handler. (The
      // distinction was originally worth minutes and a second Gemini bill on `hybrid`, removed
      // in ADR-006; it still holds on the deterministic path, just more cheaply.)
      class ComparisonStreamError extends Error {}

      try {
        const stream = streamApi("/api/v1/audits/physical-comparison/stream", requestBody, timeoutMs);
        for await (const rawChunk of stream) {
          let event: any;
          try {
            event = JSON.parse(rawChunk);
          } catch {
            // streamApi also yields non-`data:` lines; a frame we can't parse is not fatal.
            continue;
          }
          if (event.type === "progress") {
            if (event.stage) setAiScanProgress(event.stage);
            if (typeof event.progress_pct === "number") setAiScanProgressPct(event.progress_pct);
          } else if (event.type === "complete") {
            streamSucceeded = true;
            data = event.result;
            setAiScanProgressPct(100);
          } else if (event.type === "error") {
            throw new ComparisonStreamError(event.error || "Comparison stream error");
          }
        }
      } catch (streamErr: any) {
        if (streamErr instanceof ComparisonStreamError) throw streamErr;
        console.warn("[usePhysicalComparison] SSE transport failed, falling back to standard POST:", streamErr);
      }

      // Fallback if SSE streaming did not complete
      if (!streamSucceeded || !data) {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

        const res = await fetch(`${baseUrl()}/api/v1/audits/physical-comparison`, {
          method: "POST",
          headers: buildHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify(requestBody),
          signal: controller.signal
        });
        clearTimeout(timeoutId);
        data = await parseOrThrow<any>(res);
      }

      setAiChecklistResults(data);
      setAiScanProgress("completed");
      setAiScanProgressPct(100);

      try {
        const cleanCadText = (text: string): string => {
          if (!text) return "";
          let clean = text;
          clean = clean.replace(/Ø/g, "x");
          clean = clean.replace(/[{}]/g, "");
          clean = clean.replace(/\\[A-Za-z0-9\-~|.]+;/g, "");
          clean = clean.replace(/\\P/g, " ");
          clean = clean.replace(/\\[LlOo]/g, "");
          return clean.trim();
        };

        const isDuplicateEntity = (
          list: { text: string; x: number; y: number }[],
          text: string,
          x: number,
          y: number
        ): boolean => {
          return list.some(ent => ent.text === text && Math.hypot(ent.x - x, ent.y - y) < 1.0);
        };

        const textEntities: any[] = [];
        if (newLayers) {
          Object.entries(newLayers).forEach(([layerName, entities]: any) => {
            if (Array.isArray(entities)) {
              entities.forEach((ent: any) => {
                const eType = ent.type || ent.entity_type;
                if (['text', 'mtext', 'tolerance', 'multileader', 'attrib', 'insert', 'block', 'dimension'].includes(eType)) {
                  let rawText = ent.geometry?.text || ent.geometry?.content || ent.properties?.text || '';
                  if (eType === 'block' && ent.properties?.attributes) {
                    rawText = Object.values(ent.properties.attributes).join(' ');
                  }
                  const textVal = cleanCadText(rawText);
                  if (textVal && (ent.geometry?.location || ent.geometry?.insert || ent.geometry?.text_point)) {
                    const [tx, ty] = ent.geometry.location || ent.geometry.insert || ent.geometry.text_point;
                    const cleanedText = textVal.trim();
                    if (!isDuplicateEntity(textEntities, cleanedText, tx, ty)) {
                      textEntities.push({
                        text: cleanedText, x: tx, y: ty,
                        handle: ent.properties?.handle, bbox: ent.properties?.bbox,
                        height: ent.properties?.height, layoutSpace: ent.properties?.layout_space || 'Model',
                        layer: layerName, eType: eType
                      });
                    }
                  }
                }
              });
            }
          });
        }

        const refTextEntities: any[] = [];
        if (oldLayers) {
          Object.entries(oldLayers).forEach(([layerName, entities]: any) => {
            if (Array.isArray(entities)) {
              entities.forEach((ent: any) => {
                const eType = ent.type || ent.entity_type;
                if (['text', 'mtext', 'tolerance', 'multileader', 'attrib', 'insert', 'block', 'dimension'].includes(eType)) {
                  let rawText = ent.geometry?.text || ent.geometry?.content || ent.properties?.text || '';
                  if (eType === 'block' && ent.properties?.attributes) {
                    rawText = Object.values(ent.properties.attributes).join(' ');
                  }
                  const textVal = cleanCadText(rawText);
                  if (textVal && (ent.geometry?.location || ent.geometry?.insert || ent.geometry?.text_point)) {
                    const [tx, ty] = ent.geometry.location || ent.geometry.insert || ent.geometry.text_point;
                    const cleanedText = textVal.trim();
                    if (!isDuplicateEntity(refTextEntities, cleanedText, tx, ty)) {
                      refTextEntities.push({
                        text: cleanedText, x: tx, y: ty,
                        handle: ent.properties?.handle, bbox: ent.properties?.bbox,
                        height: ent.properties?.height, layoutSpace: ent.properties?.layout_space || 'Model',
                        layer: layerName, eType: eType
                      });
                    }
                  }
                }
              });
            }
          });
        }

        const bounds = computeBounds(textEntities);
        const refBounds = computeBounds(refTextEntities);

        const mappedMarkings = generateComparisonMarkings({
          rawMarkings: data.canvas_markings || [],
          textEntities,
          refTextEntities,
          drawing: newDrawing,
          oldDrawing,
          bounds,
          refBounds
        });

        // The backend persists this comparison's findings under an AuditSession and now
        // returns its id. Recording it is what lets the ADR-010 summary panel ask for a
        // summary of THIS comparison -- previously the id existed only in a server log.
        const comparisonSessionId = data.diagnostics?.audit_session_id ?? null;
        if (comparisonSessionId) {
          useWorkspaceStore.getState().setActiveSessionId(comparisonSessionId);
        }

        // Use the newly added store action instead of setState
        setViolations(mappedMarkings);
        useReviewStore.setState({ showViolations: true, isPhysicalComparisonEnabled: true });

      } catch (err) {
        console.warn("Visual checklist overlay failed:", err);
      }
    } catch (err: any) {
      console.error(err);
      setAiScanError(err.message || String(err));
      setAiScanProgress("idle");
    }
  };

  return {
    runPhysicalComparisonAI,
    aiScanProgress,
    aiChecklistResults,
    aiScanError,
    resetComparison
  };
};
