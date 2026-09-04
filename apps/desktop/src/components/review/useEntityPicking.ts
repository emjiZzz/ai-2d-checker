import { useCallback, useEffect, useMemo, useRef } from 'react';
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
  entityDisplayText,
  dimensionKindOf,
  zoneKeyForBox,
  zoneRelativePos,
  sheetRelativePos,
  isZoneMeasured,
  isStampClick,
} from './entityPicking';
import type { EntityLocator, PickedEntity } from '../../stores/workspace/types';
import { findMarkingForEntity } from './manualCheckCategories';
import { submitAuditFeedbackPayload } from '../../services/auditsApi';

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
 * does here — selecting is not recording, so there remains exactly one way to write a
 * marking.
 *
 * A drag is not a click. A press that travels more than `CLICK_SLOP_PX` is a pan, and
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
  const setSelectionMenu = useWorkspaceStore((s) => s.setSelectionMenu);
  const setSelectionCounterpart = useWorkspaceStore((s) => s.setSelectionCounterpart);
  const selectionLocator = useWorkspaceStore((s) => s.selectionLocator);
  // This sheet's own zones. Zone membership is what stops a value in the BOM matching the
  // same value in a view; it is read per-drawing because the boxes are per-drawing.
  const zoneRegions = useWorkspaceStore((s) => s.zoneRegions);
  const markings = useWorkspaceStore((s) => s.markings);
  const pendingCounterpart = useReviewStore((s) => s.pendingCounterpart);
  const setPendingCounterpart = useReviewStore((s) => s.setPendingCounterpart);
  const isPenActive = useWorkspaceStore((s) => s.isPenActive);

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

      // The Y-FLIPPED transform. Entity geometry is CAD Y-up; `screenToWorldUnflipped` is the
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

      // The ENTITY's centre, not the cursor's position.
      //
      // A marking is a statement about an entity, so its coordinate belongs to that entity, and
      // the dot has to land in the same place on every value or it reads as sloppy rather than
      // as a mark. Recording the click point put it wherever the pointer happened to be inside
      // the hit box: high on one value, off the left edge of the next, never twice the same.
      //
      // Bounds come from the pick index, which stores FLIPPED world units; `flipWorldY` is its
      // own inverse, so one call returns the CAD-space point the renderer expects. The cursor
      // is the fallback for an entity the index could not measure — better a placed mark than
      // none, and `entityWorldBounds` covering everything drawable is what keeps that rare.
      const box = indexRef.current.boundsFor(String(entity.id));
      // The zone this entity sits in, resolved the same way `buildLocator` resolves it — one
      // rule for "where is this on the sheet", whether the answer is used to find a counterpart
      // or to derive a category.
      const zones = drawing?.id ? zoneRegions[String(drawing.id)] : null;
      const zone = box ? zoneKeyForBox(zones, box, (y) => flipWorldY(y, norm)) : null;
      const world = box
        ? { x: (box.x0 + box.x1) / 2, y: flipWorldY((box.y0 + box.y1) / 2, norm) }
        : screenToWorld(clientX - rect.left, clientY - rect.top, norm, viewport);

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
        // Read, never typed. Committed labels preserve full-width characters and clean CAD symbols;
        // retyping normalises away the very characters comparison turns on.
        text: entityDisplayText(entity) || String(
          entity.geometry?.text ?? entity.geometry?.content ?? entity.properties?.text ?? '',
        ),
        coordinates: [world.x, world.y],
        zone,
      };
    },
    [canvasRef, drawing?.id, norm, side, viewport, zoneRegions],
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

  /**
   * Has this entity already been marked?
   *
   * Reads the raw hit rather than a `PickedEntity`, because the hover path never builds one —
   * and the answer is needed before deciding whether to advertise the entity as markable.
   */
  const alreadyMarked = useCallback(
    (hit: any): boolean =>
      Boolean(
        findMarkingForEntity(markings, {
          side,
          handle: hit?.handle ?? hit?.properties?.handle ?? null,
        }),
      ),
    [markings, side],
  );

  /**
   * Resolve the selection's counterpart on THIS sheet, for the pane that is not the source.
   *
   * The counterpart lives in this canvas's pick index, and the pane showing the selection has no
   * access to it — so the answer has to be published rather than asked for. This is the same
   * `findMatches` call the cross-sheet outline uses, so what gets recorded is exactly the entity
   * the engineer can see outlined and labelled while they choose a status.
   *
   * Only when there is exactly ONE. Where several candidates carry the value and nothing
   * separates them the overlay outlines them all with an `xN` chip, and this publishes nothing:
   * a MATCHED that silently picked one of three would be a fabricated pair wearing the same
   * badge as a real one.
   */
  useEffect(() => {
    if (!isManualCheckMode) return;
    if (!selectionLocator) {
      setSelectionCounterpart(null);
      return;
    }
    // The source sheet holds the selection itself, not its counterpart.
    if (selectionLocator.side === side) return;

    const flipY = (y: number) => flipWorldY(y, norm);
    const zones = drawing?.id ? zoneRegions[String(drawing.id)] : null;
    const matches = indexRef.current.findMatches(selectionLocator, {
      zoneOf: (b) => zoneKeyForBox(zones, b, flipY),
      zoneMeasured: (zone) => isZoneMeasured(zones, zone),
      zonePos: (b, zone) => zoneRelativePos(zones, zone, b, flipY),
      sheetPos: (b) => sheetRelativePos(b, norm),
    });
    if (matches.length !== 1) {
      setSelectionCounterpart(null);
      return;
    }

    // `toPicked` derives the coordinate from the entity itself, so the counterpart needs no
    // special case — the cursor arguments go unused for anything the index can measure.
    setSelectionCounterpart(toPicked(matches[0].entity, 0, 0));
  }, [
    isManualCheckMode,
    selectionLocator,
    side,
    norm,
    drawing?.id,
    zoneRegions,
    setSelectionCounterpart,
    toPicked,
  ]);

  const onMouseMove = useCallback(
    (e: React.MouseEvent) => {
      handlers.onMouseMove?.(e);
      if (isPenActive || useWorkspaceStore.getState().isPenActive) return;
      const hit = pickAt(e.clientX, e.clientY);

      // An entity that already carries a marking gets NO picking highlight — no corner
      // brackets, no value chip, no cross-sheet outline.
      //
      // Those say "you can mark this", and it is already marked. What appears instead is the
      // marker's own detail card, from the same renderer an engine finding uses, driven by the
      // separate marker hit-test in `useCanvasInteraction`. Both used to fire at once, stacking
      // two hover treatments on one entity and offering an action that no longer applies.
      const markable = hit && !alreadyMarked(hit);
      setHoveredEntityId(markable ? String(hit.id) : null);
      setHoverLocator(markable ? buildLocator(hit) : null);
    },
    [handlers, pickAt, setHoveredEntityId, setHoverLocator, buildLocator, alreadyMarked, isPenActive],
  );

  /** The click point in CAD units, for a correction that records where the engineer pointed. */
  const pickedWorld = useCallback(
    (clientX: number, clientY: number) => {
      const canvas = canvasRef.current;
      if (!canvas) return null;
      const rect = canvas.getBoundingClientRect();
      return screenToWorld(clientX - rect.left, clientY - rect.top, norm, viewport);
    },
    [canvasRef, norm, viewport],
  );

  const onMouseDown = useCallback(
    (e: React.MouseEvent) => {
      handlers.onMouseDown?.(e);
      if (isPenActive || useWorkspaceStore.getState().isPenActive) return;
      pressRef.current = e.button === 0 ? { x: e.clientX, y: e.clientY } : null;
      // A middle-button pan is starting. The selection menu is anchored in canvas pixels, so
      // the drawing would slide out from under it and leave it pointing at nothing.
      if (e.button !== 0) setSelectionMenu(null);
    },
    [handlers, setSelectionMenu, isPenActive],
  );

  /**
   * Zooming closes the menu, for the same reason panning does.
   *
   * Wrapped here even though `CanvasRenderer` pulls `onWheel` out of the handler object and
   * registers it natively — it registers whichever function this hook hands back, so the wrap
   * survives. Left-clicking again reopens it at the new position.
   */
  const onWheel = useCallback(
    (e: any) => {
      handlers.onWheel?.(e);
      setSelectionMenu(null);
    },
    [handlers, setSelectionMenu],
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
      if (isPenActive || useWorkspaceStore.getState().isPenActive) return;
      const press = pressRef.current;
      pressRef.current = null;
      if (!isStampClick(e.button, press, { x: e.clientX, y: e.clientY })) return;

      const hit = pickAt(e.clientX, e.clientY);

      // ── completing a matcher correction ───────────────────────────────────────────
      // A `mispaired_*` correction was armed in the checklist and is waiting for the engineer
      // to point at the entity the engine SHOULD have paired with. That click lands here, on
      // whichever canvas they clicked, and finishes the correction instead of selecting.
      //
      // The side is read from the canvas rather than demanded up front: the engineer knows
      // which sheet holds the counterpart and the app does not, and guessing would refuse
      // half the legitimate picks.
      if (pendingCounterpart && hit) {
        const world = pickedWorld(e.clientX, e.clientY);
        submitAuditFeedbackPayload({
          ...pendingCounterpart.payload,
          corrected_counterpart: {
            side,
            handle: hit.handle ?? hit.properties?.handle ?? null,
            text: String(
              hit.properties?.text ?? hit.geometry?.text ?? hit.geometry?.content ?? '',
            ),
            coordinates: world ? [world.x, world.y] : null,
          },
        }).catch((err) => console.warn('[useEntityPicking] counterpart submit failed:', err));
        setPendingCounterpart(null);
        return;
      }

      // Same rule as hover: an already-marked entity is not selectable. Selecting it would draw
      // the solid selection outline while `SelectionMenu` declines to open — a box on the sheet
      // with nothing behind it, which reads as the menu having failed rather than as a
      // deliberate refusal. Its record is on screen already, as the hover card.
      const picked = hit && !alreadyMarked(hit) ? toPicked(hit, e.clientX, e.clientY) : null;
      // Clicking blank canvas clears, which is the only way to get back to nothing selected.
      setSelectedEntities(picked ? [picked] : []);
      // …and publish the same locator hover does, so the OTHER sheet outlines the counterpart
      // and keeps it outlined. Hover cannot serve this: it clears the moment the cursor leaves,
      // and comparing a pair means looking at both sheets with the mouse somewhere else.
      // Keyed on `picked`, not on `hit`: an already-marked entity was filtered out above, and
      // publishing its locator would still outline a counterpart on the other sheet for a
      // selection that does not exist.
      setSelectionLocator(picked ? buildLocator(hit) : null);

      // The selection carries its OWN menu, floated at the click.
      //
      // Separate from the right-click menu since 2026-08-18: that one is the canvas's tools —
      // annotation pins, labels, marker filters — and the marking taxonomy was a guest in it.
      // Two menus with different subjects sharing one gesture is how an engineer ends up
      // hunting for the marking actions among the view controls.
      //
      // Manual rooms only, matching where recording is possible at all. Elsewhere a left-click
      // selects and nothing opens.
      if (!isManualCheckMode || !picked || !drawing?.id) {
        setSelectionMenu(null);
      } else {
        const canvas = canvasRef.current;
        const rect = canvas?.getBoundingClientRect();
        const b = indexRef.current.boundsFor(String(picked.entityId));
        let targetBounds: { x0: number; y0: number; x1: number; y1: number } | undefined;
        if (b && norm.hasBounds) {
          const effectiveScale = viewport.scale * norm.normScale;
          const sx0 = (b.x0 - norm.xmin) * effectiveScale + viewport.x;
          const sx1 = (b.x1 - norm.xmin) * effectiveScale + viewport.x;
          const sy0 = (b.y0 - norm.ymin) * effectiveScale + viewport.y;
          const sy1 = (b.y1 - norm.ymin) * effectiveScale + viewport.y;
          targetBounds = {
            x0: Math.min(sx0, sx1),
            y0: Math.min(sy0, sy1),
            x1: Math.max(sx0, sx1),
            y1: Math.max(sy0, sy1),
          };
        }

        setSelectionMenu(
          rect
            ? {
                x: e.clientX - rect.left,
                y: e.clientY - rect.top,
                drawingId: String(drawing.id),
                targetBounds,
              }
            : null,
        );
      }
    },
    [handlers, pickAt, toPicked, setSelectedEntities, setSelectionLocator, buildLocator,
     setSelectionMenu, isManualCheckMode, drawing?.id, canvasRef, alreadyMarked,
     pendingCounterpart, setPendingCounterpart, pickedWorld, side, norm, viewport],
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
      // The tools menu is opening; the selection's menu would otherwise sit underneath it. The
      // SELECTION itself is untouched — right-clicking away from it must not silently empty it,
      // and the tools menu still acts on whatever is selected.
      setSelectionMenu(null);
    },
    [handlers, setSelectionMenu],
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
      onWheel,
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
