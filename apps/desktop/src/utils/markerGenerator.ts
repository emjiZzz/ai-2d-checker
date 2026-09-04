import { findAllFuzzyMatches, EntityTextPayload } from './fuzzyMatch';
import { isEngineeringDataEntity, Bounds } from './spatialBounds';

export interface RawViolation {
  entity_id?: string;
  category?: string;
  text_content: string;
  details?: string;
  confidence?: number;
  original_value?: string;
  // `null`, not just absent, when the backend could not place the value —
  // `resolution_method: "unresolved"`. The type said `[number, number] | undefined`, which is
  // not what the payload carries, and that gap is part of why the unresolved case went
  // unhandled below: a reader checking the type would conclude it could not arise.
  coordinates?: [number, number] | null;
  ref_coordinates?: [number, number] | null;
  status?: string;
  visual_bbox?: [number, number, number, number];
  ref_visual_bbox?: [number, number, number, number];
  // Sub-item taxonomy key within `category` (docs/checklist-taxonomy-grouping-
  // implementation-plan.md) — e.g. category="title_block", feature="scale".
  feature?: string;
}

/**
 * Centre of a piece of drawing text, in CAD units — where a marker glyph is drawn.
 *
 * `renderEntities.ts` fills the glyph with `textAlign='center'` / `textBaseline='middle'` at
 * exactly this coordinate, so the coordinate IS the glyph's centre. The formula used to be
 * `[bbox.xmax + height * 0.8, verticalCentre]`, putting the glyph a character-width PAST the
 * text; on a long value that carries the tick clear of the data it refers to, and inside a
 * title block it lands outside the value's own ruled cell.
 *
 * Mirror of `marker_anchor()` in
 * services/backend/infrastructure/audit/bom/anchors.py — keep the two in step.
 */
export const markerAnchor = (ent: {
  bbox?: any; x?: number; y?: number; height?: number; text?: string;
}): [number, number] | undefined => {
  const h = ent.height || 3.0;
  if (Array.isArray(ent.bbox) && ent.bbox.length >= 2) {
    try {
      const [[xmin, ymin], [xmax, ymax]] = ent.bbox;
      if ([xmin, ymin, xmax, ymax].every(v => typeof v === 'number' && Number.isFinite(v))) {
        return [(xmin + xmax) / 2.0, (ymin + ymax) / 2.0];
      }
    } catch {
      // fall through to the insert-based estimate
    }
  }
  if (typeof ent.x !== 'number' || typeof ent.y !== 'number') return undefined;
  // No bbox: estimate the width so the anchor still lands inside the text rather than at its
  // left edge. The insert sits on the baseline, so the vertical centre is half a height up.
  const width = (ent.text?.length ?? 0) * h * 0.6;
  return [ent.x + width / 2.0, ent.y + h / 2.0];
};

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

    // Title-block and BOM values are extracted by the backend from specific cells and carry
    // authoritative coordinates. Re-grounding a short value like "4"/"1"/"0" by text match
    // anchors it to a same-valued cell elsewhere on the sheet — e.g. a tolerance-grid cell —
    // so for these structured categories we trust the backend coordinate and skip text
    // grounding entirely. (drawing_views/notes still ground by text, where it is correct.)
    //
    // This guard used to also require `hasBackendCoord`, and so failed open in exactly the
    // case it was written for: when the backend resolves nothing the marking arrives with
    // `coordinates: null` and `resolution_method: "unresolved"`, `hasBackendCoord` is false,
    // and the whole thing fell through into fuzzy matching — with no coordinate to sanity-check
    // the result against. Reported from a live review on M745227N01: one unresolved BOM row
    // (`Q'ty: 1 vs 1`) text-matched every entity reading `1` on the sheet and, because the loop
    // below emits one marker per match, painted MATCHED checkmarks down the 一組分個数 column of
    // the シム表 — a SAFE zone that is never compared. One finding, several wrong markers, all
    // labelled `bill_of_materials`.
    //
    // A structured value has no meaning outside the cell the backend read it from, so when the
    // backend could not place it, it gets no marker. The value is still reported in the
    // BOM / title-block table; what is dropped is a claim about *where* it is that nothing
    // could support.
    const isStructuredCategory =
      marking.category === "title_block" || marking.category === "bill_of_materials";

    // A sheet-wide finding has no position, so it gets no marker — the same invariant as the
    // structured case above, arrived at from the opposite direction. `line_attributes` answers
    // "what line types does the drawing use", which is a statement about every stroke of one
    // kind across the whole view; the backend says so and deliberately emits no `coordinates`
    // ("there is no single point a canvas marker could honestly sit at",
    // line_attribute_differ.diff_line_attributes).
    //
    // It is `drawing_views`, though, and the guard above is keyed on CATEGORY — so this fell
    // straight through into fuzzy matching, where `text_content` ("CONTINUOUS 1mm") was matched
    // against sheet text and painted a marker at whatever it hit. Reported from a live review
    // on M745221N01 as marker [M009], sitting near the title block and claiming to be a line
    // attribute. Same defect as the シム表 checkmarks, one category over: the fix for those was
    // written as a category rule when the invariant is per-finding.
    const isSheetWideFinding = marking.feature === "line_attributes";

    if (!usedDirectIdMapping && !isStructuredCategory && !isSheetWideFinding) {
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
        if (match.bbox && Array.isArray(match.bbox) && match.bbox.length >= 2) bbox = match.bbox;
        coordinates = markerAnchor(match);
      } else if (marking.coordinates && i === 0 && Array.isArray(marking.coordinates) && marking.coordinates.length >= 2) {
        coordinates = [marking.coordinates[0], marking.coordinates[1]] as [number, number];
      } else if (marking.visual_bbox && i === 0 && drawing?.metadata?.render_bounds) {
        coordinates = visualBboxToCad(marking.visual_bbox, drawing.metadata.render_bounds);
      }

      let ref_coordinates: [number, number] | undefined = undefined;
      let ref_bbox: any = undefined;
      if (refMatch) {
        if (refMatch.bbox && Array.isArray(refMatch.bbox) && refMatch.bbox.length >= 2) ref_bbox = refMatch.bbox;
        ref_coordinates = markerAnchor(refMatch);
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
            ref_coordinates = markerAnchor(closestEnt);
            refTextEntitiesWithMarkers.add(getCoordKey(closestEnt.x, closestEnt.y));
          }
        }
      }

      // ── MATCHED fallback: try a lenient token search so checkmarks can be placed ──
      const isMatched = (marking.status || "").toUpperCase() === "MATCHED";
      // `isSheetWideFinding` has to be repeated here, not just at the grounding guard above.
      // This fallback splits `text_content` into tokens and loose-matches each at threshold 50,
      // so suppressing the strict pass alone just hands the same string to a LOOSER search —
      // "CONTINUOUS 1mm" tokenises to ["CONTINUOUS", "1mm"] and lands on whatever it first
      // brushes against. That is how marker [M009] reached the title block on M745221N01.
      // A finding about every stroke on the sheet stays coordinate-less; the checklist row is
      // built from `violations` in the store, not from here, so it is unaffected.
      if (isMatched && !isSheetWideFinding && !coordinates && matches.length === 0 && refMatches.length === 0) {
        const tokens = searchTerm.split(/\s+/).filter((t: string) => t.length >= 2);
        for (const token of tokens) {
          const looseFwd = findAllFuzzyMatches(token, textEntities, preferModel, false, 50);
          if (looseFwd.length > 0) { matches = looseFwd; break; }
          const looseRef = findAllFuzzyMatches(token, refTextEntities, preferModel, false, 50);
          if (looseRef.length > 0) { refMatches = looseRef; break; }
        }
        // Recompute coordinates from loose match
        if (matches.length > 0) {
          coordinates = markerAnchor(matches[0]);
        } else if (refMatches.length > 0) {
          ref_coordinates = markerAnchor(refMatches[0]);
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
        // Provenance from the removed `hybrid` method (ADR-006) — always undefined now.
        // Passed through rather than dropped: it is present in cached payloads written
        // before the removal, and dropping it would silently change how those render.
        verification: marking.verification,
        origin: marking.origin,
        // Sub-item taxonomy tag (docs/checklist-taxonomy-grouping-implementation-plan.md,
        // Phase 5) — pass-through only, undefined when the backend didn't set one.
        feature: marking.feature,
        // Carry the stable finding identity + raw verdict through to the store so a human
        // correction can send a real entity handle and a feature snapshot for model training
        // (previously entity_id was dropped here, so feedback events had no handle at all).
        entity_handle: marking.entity_id,
        status: marking.status
      });
    }
  });

  return mappedMarkings;
};
