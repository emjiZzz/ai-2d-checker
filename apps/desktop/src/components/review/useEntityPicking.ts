import { useCallback, useMemo, useRef } from 'react';
import { useReviewStore } from '../../stores/reviewStore';
import { useIsManualCheckRoom } from '../../hooks/useManualCheckRoom';
import { useWorkspaceStore } from '../../stores/workspaceStore';
import {
  getNormalization,
  parseBounds,
  screenToWorld,
  flipWorldY,
} from '../../utils/coordinateTransform';
import {
  EntityHitIndex,
  entityValueOf,
  dimensionKindOf,
  zoneKeyForBox,
  zoneRelativePos,
  sheetRelativePos,
  isZoneMeasured,
  isStampClick,
} from './entityPicking';
import type { EntityLocator, PickedEntity } from '../../stores/workspace/types';

/**
 * Manual-check picking, layered over the existing canvas handlers.
 *
 * ## Why this wraps rather than edits
 *
 * `useCanvasInteraction` is 1100 lines and owns every gesture the review workspace already has
 * — marker drags, annotation pins, zone handles, pan, zoom. Threading a new mode through it
 * would put manual-check branches inside each of those, which is how a mode flag turns into a
 * behaviour change for everyone. Composing on the outside keeps the existing handlers exactly
 * as they are: when `isManualCheckMode` is false this hook returns them untouched.
 *
 * ## Left-click SELECTS; recording is a separate act
 *
 * A left-click resolves the entity under the cursor and makes it the selection. Nothing is
 * recorded by it — the right-click menu acts on whatever is selected. Separating the two is what
 * leaves room for a multi-select gesture later: a click that opened a menu could never serve
 * one, because a box cannot open twenty menus.
 *
 * This replaced right-click stamping (2026-08-18), then click-to-stamp a few hours later. The
 * original right-click reasoning was that aiming was hard and a second gesture would mean two
 * ways to mark a drawing. The hit index answered the first; the second still holds, and still
 * does here — **selecting is not recording**, so there remains exactly one way to write a
 * marking.
 *
 * ⚠ **A drag is not a click.** A press that travels more than `CLICK_SLOP_PX` is a pan, and
 * selects nothing on its own. Clicking empty space clears the selection.
 */

/** Click slack in screen pixels, converted to world units at the current zoom. */
const PICK_TOLERANCE_PX = 6;

export interface EntityPickingResult {
  /** Pass to `CanvasRenderer`; populated during the entity loop. */
  entityHitIndex: EntityHitIndex | undefined;
  /** The existing handlers, wrapped when manual mode is on and identical when it is off. */
  handlers: Record<string, any>;
}

export function useEntityPicking(params: {
  handlers: Record<string, any>;
  drawing: any;
  oldDrawing: any;
  canvasRef: React.RefObject<HTMLCanvasElement | null>;
}): EntityPickingResult {
  const { handlers, drawing, oldDrawing, canvasRef } = params;

  const isManualCheckMode = useIsManualCheckRoom();
  const viewport = useReviewStore((s) => s.viewport);

  const setHoveredEntityId = useWorkspaceStore((s) => s.setHoveredEntityId);
  const setSelectedEntities = useWorkspaceStore((s) => s.setSelectedEntities);
  const setHoverLocator = useWorkspaceStore((s) => s.setHoverLocator);
  const setSelectionLocator = useWorkspaceStore((s) => s.setSelectionLocator);
  // This sheet's own zones. Zone membership is what stops a value in the BOM matching the
  // same value in a view; it is read per-drawing because the boxes are per-drawing.
  const zoneRegions = useWorkspaceStore((s) => s.zoneRegions);

  // One index per canvas, rebuilt each render by `renderEntities`. A ref rather than state:
  // it is written during the render loop, which must not trigger another render.
  const indexRef = useRef<EntityHitIndex>(new EntityHitIndex());

  // Where the left button went down, so a pan can be told from a click. A ref because it is
  // read in the same gesture it is written and must not cost a render.
  const pressRef = useRef<{ x: number; y: number } | null>(null);

  // Which sheet this canvas is showing. A marking has to record the side it was stamped on,
  // and a REMOVED anchors on the reference — the side where handle coverage is worst and the
  // composite address earns its keep.
  const side: 'ref' | 'rev' = oldDrawing && drawing?.id === oldDrawing.id ? 'ref' : 'rev';

  const norm = useMemo(
    () => getNormalization(parseBounds(drawing?.metadata?.render_bounds)),
    [drawing?.metadata?.render_bounds],
  );

  const pickAt = useCallback(
    (clientX: number, clientY: number) => {
      const canvas = canvasRef.current;
      if (!canvas) return null;
      const rect = canvas.getBoundingClientRect();
      const sx = clientX - rect.left;
      const sy = clientY - rect.top;

      // ⚠ The Y-FLIPPED transform. Entity geometry is CAD Y-up; `screenToWorldUnflipped` is the
      // zone-fraction variant and using it here would mirror every hit box about the sheet's
      // centreline — plausible near the middle, far out at the top.
      const world = screenToWorld(sx, sy, norm, viewport);
      const effectiveScale = viewport.scale * norm.normScale;
      const tolerance = PICK_TOLERANCE_PX / (effectiveScale || 1);

      // The index stores flipped-world bounds, matching what the renderer draws.
      return indexRef.current.hitTest(world.x, flipWorldY(world.y, norm), tolerance);
    },
    [canvasRef, norm, viewport],
  );

  const toPicked = useCallback(
    (entity: any, clientX: number, clientY: number): PickedEntity | null => {
      if (!entity || !drawing?.id) return null;
      const canvas = canvasRef.current;
      if (!canvas) return null;
      const rect = canvas.getBoundingClientRect();
      const world = screenToWorld(clientX - rect.left, clientY - rect.top, norm, viewport);

      return {
        drawingId: String(drawing.id),
        side,
        entityId: String(entity.id),
        // Every key that might survive a re-extraction. `handle` is the only guaranteed one and
        // it is absent on block-exploded children, so the rest are not redundant padding.
        handle: entity.handle ?? entity.properties?.handle ?? null,
        parentHandle: entity.properties?.parent_handle ?? null,
        entityType: String(entity.type ?? entity.entity_type ?? 'unknown'),
        layer: String(entity.layer ?? entity.properties?.layer ?? '0'),
        // Read, never typed. Committed labels preserve full-width characters and stray drawing
        // artifacts exactly; retyping normalises away the very characters comparison turns on.
        text: String(
          entity.geometry?.text ?? entity.geometry?.content ?? entity.properties?.text ?? '',
        ),
        coordinates: [world.x, world.y],
      };
    },
    [canvasRef, drawing?.id, norm, side, viewport],
  );

  /**
   * What the OTHER canvas needs in order to outline this entity's counterpart.
   *
   * The single construction site, used by both hover and selection. They published the same
   * thing from two copies until 2026-08-18; two copies of "what is this entity, for matching
   * purposes" is the drift shape this codebase keeps paying for — both would keep working while
   * they slowly disagreed, and the visible symptom would be the overlay pairing different
   * entities depending on which gesture you used.
   *
   * Returns `null` for anything that carries no value. That is the honest answer rather than a
   * degraded one: there is no way to say which of two sheets' unlabelled lines correspond, and
   * outlining an arbitrary line would assert exactly that.
   */
  const buildLocator = useCallback(
    (hit: any): EntityLocator | null => {
      // A VALUE, not a position. The two sheets do not lay out alike, and mapping through each
      // sheet's `render_bounds` provably resolved to the same canvas pixel on both — see
      // `EntityLocator`. A value is the one thing the two drawings genuinely share.
      const value = hit ? entityValueOf(hit) : '';
      if (!value) return null;

      // Zone and zone-relative position are what narrow the match from "every entity reading
      // 145" to the one the engineer is looking at. Both are computed in FLIPPED-world space,
      // because that is what the index stores; `zoneKeyForBox` applies the flip to the zone.
      const bounds = indexRef.current.boundsFor(String(hit.id));
      const zones = drawing?.id ? zoneRegions[String(drawing.id)] : null;
      const flipY = (y: number) => flipWorldY(y, norm);
      const zone = bounds ? zoneKeyForBox(zones, bounds, flipY) : null;
      const pos = bounds ? zoneRelativePos(zones, zone, bounds, flipY) : null;
      const sheet = bounds ? sheetRelativePos(bounds, norm) : null;
      // Where this entity sits among the other copies of its value on THIS sheet. Computed from
      // the index rather than from `bounds` alone, because it is a statement about the group.
      const group = indexRef.current.groupFractionOf(hit);

      return {
        side,
        value,
        entityType: String(hit.type ?? 'unknown'),
        dimKind: dimensionKindOf(hit),
        zone,
        // A `percentage_fallback` zone is a guess about this sheet, and the other sheet will
        // have guessed differently. Published so the matcher can decline to filter on it.
        zoneMeasured: isZoneMeasured(zones, zone),
        zfx: pos ? pos.zfx : null,
        zfy: pos ? pos.zfy : null,
        cfx: group ? group.cfx : null,
        cfy: group ? group.cfy : null,
        sfx: sheet ? sheet.sfx : null,
        sfy: sheet ? sheet.sfy : null,
      };
    },
    [side, drawing?.id, zoneRegions, norm],
  );

  const onMouseMove = useCallback(
    (e: React.MouseEvent) => {
      handlers.onMouseMove?.(e);
      const hit = pickAt(e.clientX, e.clientY);
      setHoveredEntityId(hit ? String(hit.id) : null);
      setHoverLocator(hit ? buildLocator(hit) : null);
    },
    [handlers, pickAt, setHoveredEntityId, setHoverLocator, buildLocator],
  );

  const onMouseDown = useCallback(
    (e: React.MouseEvent) => {
      handlers.onMouseDown?.(e);
      pressRef.current = e.button === 0 ? { x: e.clientX, y: e.clientY } : null;
    },
    [handlers],
  );

  /**
   * Left-click makes the entity under the cursor the selection.
   *
   * Captured as a full `PickedEntity` rather than an id: the context menu needs the side, the
   * handle and the coordinate to build a marking, and by the time a menu item is clicked the
   * cursor is over the menu, where a fresh hit test would resolve to whatever sits underneath.
   */
  const onClick = useCallback(
    (e: React.MouseEvent) => {
      handlers.onClick?.(e);
      const press = pressRef.current;
      pressRef.current = null;
      if (!isStampClick(e.button, press, { x: e.clientX, y: e.clientY })) return;

      const hit = pickAt(e.clientX, e.clientY);
      const picked = hit ? toPicked(hit, e.clientX, e.clientY) : null;
      // Clicking blank canvas clears, which is the only way to get back to nothing selected.
      setSelectedEntities(picked ? [picked] : []);
      // …and publish the same locator hover does, so the OTHER sheet outlines the counterpart
      // and keeps it outlined. Hover cannot serve this: it clears the moment the cursor leaves,
      // and comparing a pair means looking at both sheets with the mouse somewhere else.
      setSelectionLocator(hit ? buildLocator(hit) : null);
    },
    [handlers, pickAt, toPicked, setSelectedEntities, setSelectionLocator, buildLocator],
  );

  /**
   * Right-click opens the menu over the CURRENT selection and changes nothing about it.
   *
   * Deliberately non-destructive: right-clicking away from the selection must not silently
   * empty it, or a box drawn over twenty rows would evaporate on the gesture meant to record it.
   */
  const onContextMenu = useCallback(
    (e: React.MouseEvent) => {
      handlers.onContextMenu?.(e);
    },
    [handlers],
  );

  // The index is built in EVERY room, not just manual ones. Selecting an entity is now part of
  // the canvas's mouse scheme rather than a manual-check feature, and the index is what makes a
  // click resolve to something. It costs little: only value carriers are recorded, which is
  // roughly half the payload — 184 of 402 entities on `M745204N01`'s reference.
  //
  // Recording a marking is still manual-only; that gate lives in the context menu, which is the
  // only thing that writes one.
  if (!isManualCheckMode) {
    return { entityHitIndex: indexRef.current, handlers: { ...handlers, onMouseDown, onClick, onMouseMove } };
  }

  return {
    entityHitIndex: indexRef.current,
    handlers: {
      ...handlers,
      onMouseDown,
      onClick,
      onMouseMove,
      onContextMenu,
      // Without this the ghost strands on the other sheet after the cursor leaves, pointing at
      // a place nobody is looking.
      onMouseLeave: (e: React.MouseEvent) => {
        handlers.onMouseLeave?.(e);
        setHoveredEntityId(null);
        setHoverLocator(null);
      },
    },
  };
}
