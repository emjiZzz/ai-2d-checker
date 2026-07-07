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

      const isMatchFilteredTick = (rawMatchesCount > 0 && matches.length === 0) || (rawRefMatchesCount > 0 && refMatches.length === 0);
      if (!coordinates && !isMatchFilteredTick) continue;

      let penType = "resolved_green";
      if (marking.status === "REMOVED") penType = "ai_red";
      else if (marking.status === "CHANGED") penType = "ai_orange";
      else if (marking.status === "ADDED") penType = "checker_blue";

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
        original_value: marking.original_value
      });
    }
  });

  return mappedMarkings;
};
