import { findAllFuzzyMatches, EntityTextPayload } from './fuzzyMatch';
import { isEngineeringDataEntity, Bounds } from './spatialBounds';

export interface RawViolation {
  entity_id?: string;
  category?: string;
  text_content: string;
  details?: string;
  confidence?: number;
  original_value?: string;
  coordinates?: [number, number];
  ref_coordinates?: [number, number];
  status?: string;
  visual_bbox?: [number, number, number, number];
  ref_visual_bbox?: [number, number, number, number];
  // Sub-item taxonomy key within `category` (docs/checklist-taxonomy-grouping-
  // implementation-plan.md) — e.g. category="title_block", feature="scale".
  feature?: string;
}

export interface GeneratorParams {
  rawMarkings: RawViolation[];
  textEntities: EntityTextPayload[];
  refTextEntities: EntityTextPayload[];
  drawing: any;
  oldDrawing: any;
  bounds: Bounds;
  refBounds: Bounds;
}

export const generateComparisonMarkings = ({
  rawMarkings,
  textEntities,
  refTextEntities,
  drawing,
  oldDrawing,
  bounds,
  refBounds
}: GeneratorParams): any[] => {
  // Helper: convert Gemini visual_bbox [ymin, xmin, ymax, xmax] (0-1000) to CAD [x, y]
  const visualBboxToCad = (
    vbox: [number, number, number, number],
    renderBounds: number[] | undefined
  ): [number, number] | undefined => {
    if (!renderBounds || renderBounds.length < 4) return undefined;
    const [yminN, xminN, ymaxN, xmaxN] = vbox;
    const [xMinCad, yMinCad, xMaxCad, yMaxCad] = renderBounds;
    const cadW = xMaxCad - xMinCad;
    const cadH = yMaxCad - yMinCad;
    const xFrac = ((xminN + xmaxN) / 2.0) / 1000.0;
    const yFrac = ((yminN + ymaxN) / 2.0) / 1000.0;
    // Y-inversion: Gemini image origin is top-left, CAD origin is bottom-left
    return [xMinCad + xFrac * cadW, yMinCad + (1.0 - yFrac) * cadH];
  };

  const mappedMarkings: any[] = [];
  const refTextEntitiesWithMarkers = new Set<string>();
  const getCoordKey = (x: number, y: number) => `${x.toFixed(2)},${y.toFixed(2)}`;

  rawMarkings.forEach((marking: any, index: number) => {
    const preferModel = (marking.category === 'drawing_views' || !marking.category);
    const searchTerm = marking.text_content;

    let matches: any[] = [];
    let refMatches: any[] = [];
    let usedDirectIdMapping = false;

    if (marking.entity_id) {
      const id = marking.entity_id.trim();
      if (id.startsWith('REV-')) {
        const handle = id.replace('REV-', '');
        const found = textEntities.find(e => e.handle === handle);
        if (found) { matches = [found]; usedDirectIdMapping = true; }
      } else if (id.startsWith('REF-')) {
        const handle = id.replace('REF-', '');
        const found = refTextEntities.find(e => e.handle === handle);
        if (found) { refMatches = [found]; usedDirectIdMapping = true; }
      }
    }

    if (!usedDirectIdMapping) {
      const isShortAnnotation = searchTerm && searchTerm.trim().length <= 6 && !searchTerm.includes('\n');
      const exactMatchFilter = (entities: typeof textEntities) =>
        entities.filter(e => e.text.trim().toLowerCase() === searchTerm.trim().toLowerCase());

      matches = isShortAnnotation && exactMatchFilter(textEntities).length > 0
        ? exactMatchFilter(textEntities)
        : findAllFuzzyMatches(searchTerm, textEntities, preferModel);
      refMatches = isShortAnnotation && exactMatchFilter(refTextEntities).length > 0
        ? exactMatchFilter(refTextEntities)
        : findAllFuzzyMatches(searchTerm, refTextEntities, preferModel);
    }

    const rawMatchesCount = matches.length;
    const rawRefMatchesCount = refMatches.length;

    if (marking.category !== "title_block" && marking.category !== "bill_of_materials") {
      matches = matches.filter(m => isEngineeringDataEntity({ ent: m, drawing, oldDrawing, bounds }));
      refMatches = refMatches.filter(m => isEngineeringDataEntity({ ent: m, drawing: oldDrawing, oldDrawing, bounds: refBounds }));
    }

    const maxInstances = Math.max(matches.length, refMatches.length, 1);

    for (let i = 0; i < maxInstances; i++) {
      const match = matches[i] || matches[0];
      const refMatch = refMatches[i] || refMatches[0];

      let coordinates: [number, number] | undefined = undefined;
      let bbox: any = undefined;
      if (match) {
        const h = match.height || 3.0;
        if (match.bbox && Array.isArray(match.bbox) && match.bbox.length >= 2) {
          bbox = match.bbox;
          try {
            const [[, ymin], [xmax, ymax]] = match.bbox;
            const hVal = match.height || (ymax - ymin) || 3.0;
            coordinates = [xmax + hVal * 0.8, ymin + ((ymax - ymin) / 2.0)] as [number, number];
          } catch {
            coordinates = [match.x + h * 0.8, match.y + h * 0.5] as [number, number];
          }
        } else {
          coordinates = [match.x + h * 0.8, match.y + h * 0.5] as [number, number];
        }
      } else if (marking.coordinates && i === 0 && Array.isArray(marking.coordinates) && marking.coordinates.length >= 2) {
        coordinates = [marking.coordinates[0], marking.coordinates[1]] as [number, number];
      } else if (marking.visual_bbox && i === 0 && drawing?.metadata?.render_bounds) {
        coordinates = visualBboxToCad(marking.visual_bbox, drawing.metadata.render_bounds);
      }

      let ref_coordinates: [number, number] | undefined = undefined;
      let ref_bbox: any = undefined;
      if (refMatch) {
        const h = refMatch.height || 3.0;
        if (refMatch.bbox && Array.isArray(refMatch.bbox) && refMatch.bbox.length >= 2) {
          ref_bbox = refMatch.bbox;
          try {
            const [[, ymin], [xmax, ymax]] = refMatch.bbox;
            const hVal = refMatch.height || (ymax - ymin) || 3.0;
            ref_coordinates = [xmax + hVal * 0.8, ymin + ((ymax - ymin) / 2.0)] as [number, number];
          } catch {
            ref_coordinates = [refMatch.x + h * 0.8, refMatch.y + h * 0.5] as [number, number];
          }
        } else {
          ref_coordinates = [refMatch.x + h * 0.8, refMatch.y + h * 0.5] as [number, number];
        }
      } else if (marking.ref_coordinates && i === 0 && Array.isArray(marking.ref_coordinates) && marking.ref_coordinates.length >= 2) {
        ref_coordinates = [marking.ref_coordinates[0], marking.ref_coordinates[1]] as [number, number];
      } else if (marking.ref_visual_bbox && i === 0 && oldDrawing?.metadata?.render_bounds) {
        ref_coordinates = visualBboxToCad(marking.ref_visual_bbox, oldDrawing.metadata.render_bounds);
      }

      if (match && !refMatch) {
        let closestEnt: any = null;
        let minDistance = Infinity;
        refTextEntities.forEach(ent => {
          const dist = Math.hypot(ent.x - match.x, ent.y - match.y);
          if (dist < minDistance) { minDistance = dist; closestEnt = ent; }
        });
        if (closestEnt && minDistance < 50.0) {
          const identityMatches = findAllFuzzyMatches(marking.text_content, [closestEnt], preferModel, false, 80);
          const isLocked = refTextEntitiesWithMarkers.has(getCoordKey(closestEnt.x, closestEnt.y));
          if (identityMatches.length > 0 && !isLocked) {
            const rh = closestEnt.height || 3.0;
            ref_coordinates = [closestEnt.x + rh * 0.8, closestEnt.y + rh * 0.5] as [number, number];
            refTextEntitiesWithMarkers.add(getCoordKey(closestEnt.x, closestEnt.y));
          }
        }
      }

      // ── MATCHED fallback: try a lenient token search so checkmarks can be placed ──
      const isMatched = (marking.status || "").toUpperCase() === "MATCHED";
      if (isMatched && !coordinates && matches.length === 0 && refMatches.length === 0) {
        const tokens = searchTerm.split(/\s+/).filter((t: string) => t.length >= 2);
        for (const token of tokens) {
          const looseFwd = findAllFuzzyMatches(token, textEntities, preferModel, false, 50);
          if (looseFwd.length > 0) { matches = looseFwd; break; }
          const looseRef = findAllFuzzyMatches(token, refTextEntities, preferModel, false, 50);
          if (looseRef.length > 0) { refMatches = looseRef; break; }
        }
        // Recompute coordinates from loose match
        if (matches.length > 0) {
          const m = matches[0];
          const h = m.height || 3.0;
          if (m.bbox && Array.isArray(m.bbox) && m.bbox.length >= 2) {
            try {
              const [[, ymin], [xmax, ymax]] = m.bbox;
              const hVal = m.height || (ymax - ymin) || 3.0;
              coordinates = [xmax + hVal * 0.8, ymin + ((ymax - ymin) / 2.0)] as [number, number];
            } catch { coordinates = [m.x + h * 0.8, m.y + h * 0.5] as [number, number]; }
          } else {
            coordinates = [m.x + h * 0.8, m.y + h * 0.5] as [number, number];
          }
        } else if (refMatches.length > 0) {
          const m = refMatches[0];
          const h = m.height || 3.0;
          ref_coordinates = [m.x + h * 0.8, m.y + h * 0.5] as [number, number];
          coordinates = ref_coordinates; // use ref position as proxy for rev canvas
        }
      }

      const isMatchFilteredTick = (rawMatchesCount > 0 && matches.length === 0) || (rawRefMatchesCount > 0 && refMatches.length === 0);
      // Non-MATCHED: skip if no coordinate. MATCHED: only skip if entities array is completely empty.
      if (!coordinates && !isMatchFilteredTick && !isMatched) continue;
      if (!coordinates && isMatched && textEntities.length === 0 && refTextEntities.length === 0) continue;

      let penType = "resolved_green";
      if (marking.status === "REMOVED") penType = "ai_red";
      else if (marking.status === "CHANGED") penType = "ai_orange";
      else if (marking.status === "ADDED") penType = "checker_blue";
      else if (marking.status === "CONFLICT") penType = "ai_conflict";

      mappedMarkings.push({
        id: `phys_chk_${index}_inst_${i}_${Date.now()}`,
        severity: marking.status === "MATCHED" ? "low" : "high",
        category: marking.category || "Physical Checklist",
        description: marking.text_content,
        recommendation: marking.details || "Automatic verification match",
        affected_entities: [],
        confidence: 1.0,
        coordinates,
        ref_coordinates,
        bbox,
        ref_bbox,
        pen_type: penType,
        is_resolved: marking.status === "MATCHED",
        original_value: marking.original_value,
        // hybrid-only provenance (docs/hybrid-comparison-engine-implementation-plan.md,
        // Phase 6) — undefined for rag/rag_ai/ai_vision markings.
        verification: marking.verification,
        origin: marking.origin,
        // Sub-item taxonomy tag (docs/checklist-taxonomy-grouping-implementation-plan.md,
        // Phase 5) — pass-through only, undefined when the backend didn't set one.
        feature: marking.feature
      });
    }
  });

  return mappedMarkings;
};
