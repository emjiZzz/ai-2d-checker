import { useCallback } from "react";
import { useWorkspaceStore } from "../stores/workspaceStore";
import { useReviewStore } from "../stores/reviewStore";
import { computeBounds } from "../utils/spatialBounds";
import { generateComparisonMarkings } from "../utils/markerGenerator";
import { buildHeaders, baseUrl, parseOrThrow } from "../services/fetchUtils";

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
    setAiChecklistResults,
    setAiScanError
  } = useWorkspaceStore();

  const resetComparison = useCallback(() => {
    setAiChecklistResults({});
    setViolations([]);
    setAiScanProgress("idle");
    setAiScanError(null);
  }, [setAiChecklistResults, setViolations, setAiScanProgress, setAiScanError]);

  const runPhysicalComparisonAI = async () => {
    if (!oldDrawing || !newDrawing) return;

    setAiScanProgress("comparing");
    setAiScanError(null);

    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 180_000); // 3 minutes timeout
      
      const res = await fetch(`${baseUrl()}/api/v1/audits/physical-comparison`, {
        method: "POST",
        headers: buildHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          reference_drawing_id: oldDrawing.id,
          drawing_id: newDrawing.id
        }),
        signal: controller.signal
      });
      clearTimeout(timeoutId);
      
      const data = await parseOrThrow<any>(res);

      setAiChecklistResults(data);
      setAiScanProgress("completed");

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
