import type { DrawingZonesResponse } from "../../services/drawingsApi";
import type { GroundTruthMarking } from "../../services/groundTruthApi";

export interface DrawingItem {
  id: string;
  file_name: string;
  file_path: string;
  format: string;
  file_size_bytes?: number;
  entity_counts: Record<string, number>;
  metadata: Record<string, any>;
  status?: string;
  /**
   * Drawing-number-shaped tokens found on the sheet, from the backend's
   * `infrastructure/cad/drawing_identity.py`. Optional because drawings ingested before
   * that field existed simply do not carry it — and an absent list means "cannot judge",
   * never "no match". See `isDrawingPairMismatch`.
   */
  drawing_numbers?: string[];
  /**
   * Which extraction schema this drawing's entities were written under, and whether that is
   * behind the current one.
   *
   * Optional for the same reason `drawing_numbers` is: a backend predating these fields simply
   * does not send them, and an absent `extraction_is_stale` means "cannot judge", never
   * "current". `StaleExtractionBadge` renders nothing in that case rather than warning.
   *
   * Do NOT recompute staleness by comparing the two numbers here. The server does it beside
   * `EXTRACTION_SCHEMA_VERSION`; a second copy of the rule in TypeScript is one more thing to
   * miss when the constant moves, with no shared types to catch it. The numbers are sent only
   * so the badge can say "v2 of v7".
   */
  extraction_schema_version?: number;
  current_extraction_schema_version?: number;
  extraction_is_stale?: boolean;
  created_at: string;
}

export interface ViolationItem {
  id: string;
  severity: "critical" | "high" | "medium" | "low";
  category: string;
  description: string;
  recommendation: string;
  affected_entities: string[];
  confidence: number;
  coordinates?: [number, number];
  ref_coordinates?: [number, number];
  standard_reference?: string;
  pen_type?: string;
  /** null/undefined = unreviewed; REJECTED is a verdict, not an absence. See ReviewControls. */
  resolution_type?: "APPROVED" | "REJECTED" | null;
  is_resolved?: boolean;
  resolved_at?: string | null;
  original_value?: string;
  checker_remarks?: string;
  // Carried through from the comparison marking so human corrections can reference a stable
  // finding identity and reconstruct a feature snapshot. entity_handle fixes the long-standing
  // bug where feedback events shipped an always-empty handle. status is the raw deterministic
  // verdict (MATCHED/CHANGED/ADDED/REMOVED/CONFLICT); feature is the sub-item taxonomy key.
  entity_handle?: string;
  status?: string;
  feature?: string;
}

export type AnnotationSeverity = "info" | "low" | "medium" | "high" | "critical";
export type AnnotationPenType = "checker_blue" | "amber_gold" | "warning_orange" | "alert_red" | "resolved_green" | "resolved_pink";

export const SEVERITY_PEN_MAP: Record<AnnotationSeverity, AnnotationPenType> = {
  info: "checker_blue",
  low: "checker_blue",
  medium: "amber_gold",
  high: "warning_orange",
  critical: "alert_red",
};

const SUBSCRIPT_DIGITS: Record<string, string> = {
  '0': '\u2080',
  '1': '\u2081',
  '2': '\u2082',
  '3': '\u2083',
  '4': '\u2084',
  '5': '\u2085',
  '6': '\u2086',
  '7': '\u2087',
  '8': '\u2088',
  '9': '\u2089',
};

export function toSubscriptNumber(num: number): string {
  return String(num)
    .split('')
    .map((ch) => SUBSCRIPT_DIGITS[ch] || ch)
    .join('');
}

export function getAnnotationBadgeMap(annotations?: AnnotationItem[]): Record<string, string> {
  const list = Array.isArray(annotations) ? annotations : [];
  const sorted = [...list].sort(
    (a, b) => new Date(a?.created_at || 0).getTime() - new Date(b?.created_at || 0).getTime()
  );
  const map: Record<string, string> = {};
  sorted.forEach((ann, idx) => {
    if (ann?.id) {
      map[ann.id] = `X${toSubscriptNumber(idx + 1)}`;
    }
  });
  return map;
}

export interface AnnotationItem {
  id: string;
  review_session_id: string;
  drawing_id: string;
  author_id: string;
  annotation_type: string;
  content: string;
  severity: AnnotationSeverity;
  coordinates: [number, number] | null;
  target_entity_ids: string[];
  violation_id: string | null;
  status: string;
  pen_type: AnnotationPenType;
  created_at: string;
  updated_at: string;
  /**
   * Coordinate provenance, unwrapped from the backend's CadPoint envelope in
   * services/annotationsApi.ts. The canvas keeps working in bare [x, y]; these two carry
   * the information the pair alone cannot.
   */
  coordinate_space?: "model" | "paper" | "render" | null;
  /**
   * True when the drawing was re-rendered against different bounds since this pin was
   * placed, so its stored position no longer marks what the user marked.
   */
  coordinate_drift?: boolean;
}

export type UploadState = "idle" | "dragging" | "validating" | "uploading" | "processing" | "completed" | "failed";

export interface QueueEntry {
  id: string;
  file_name: string;
  side: "old" | "new";
  status: UploadState;
  progress: number;
  error?: string;
}

export interface ClientItem {
  id: string;
  name: string;
  created_at: string;
}

// Slice Interfaces
export interface ComparisonSlice {
  oldDrawing: DrawingItem | null;
  newDrawing: DrawingItem | null;
  oldLayers: Record<string, any[]>;
  newLayers: Record<string, any[]>;
  isComparing: boolean;
  panX: number;
  panY: number;
  zoom: number;
  syncViewport: boolean;
  activeLayers: Record<string, boolean>;
  
  setOldDrawing: (drawing: DrawingItem | null) => void;
  setNewDrawing: (drawing: DrawingItem | null) => void;
  fetchLayers: (drawingId: string, side: "old" | "new") => Promise<void>;
  setViewport: (panX: number, panY: number, zoom: number) => void;
  setSyncViewport: (sync: boolean) => void;
  toggleLayer: (layerName: string) => void;
  
  // "idle" and "completed" are the only two states other code (AuditWorkspace.tsx,
  // roomStore.ts) actually branches on; every other value is a method-specific stage id
  // from utils/comparisonStages.ts, which TwoDLeftPanel.tsx looks up to render the
  // matching label — not a fixed set of literals, since that set now varies per
  // comparison_method.
  aiScanProgress: "idle" | "completed" | string;
  aiScanProgressPct: number;
  aiChecklistResults: Record<string, any>;
  aiScanError: string | null;
  setAiScanProgress: (progress: "idle" | "completed" | string) => void;
  setAiScanProgressPct: (pct: number) => void;
  setAiChecklistResults: (results: Record<string, any>) => void;
  setAiScanError: (error: string | null) => void;

  // ─── Zone alignment ─────────────────────────────────────────────────────────
  // Zone boxes are shown only in alignment mode (reviewStore.isRoiEditModeEnabled);
  // there is no separate read-only overlay toggle. Deliberately excluded from
  // saveWorkspaceState's persisted partial: caching boxes across sessions would serve
  // stale geometry after a re-parse.
  /** Keyed by drawing id so both canvases share one cache; a ref/rev pair costs two fetches, once. */
  zoneRegions: Record<string, DrawingZonesResponse>;
  /** Keyed by drawing id. Set when a zone fetch fails, so the canvas can show the cause. */
  zoneErrors: Record<string, string>;
  fetchZoneRegions: (drawingId: string) => Promise<void>;
}

export interface UploadSlice {
  oldUploadState: UploadState;
  newUploadState: UploadState;
  oldUploadProgress: number;
  newUploadProgress: number;
  oldFileName: string | null;
  newFileName: string | null;
  oldFileSize: number | null;
  newFileSize: number | null;
  oldError: string | null;
  newError: string | null;
  compatibilityStatus: "Compatible" | "Mismatch" | "Unsupported" | "Idle";
  uploadQueue: QueueEntry[];
  activeOldJobId: string | null;
  activeNewJobId: string | null;

  setOldUploadState: (state: UploadState) => void;
  setNewUploadState: (state: UploadState) => void;
  uploadDrawingFile: (file: File, side: "old" | "new") => Promise<boolean>;
  /**
   * Installs a finished drawing into its slot, or rejects it as not belonging to this room.
   * The single gate both completion paths go through — the immediate one in
   * `uploadDrawingFile` and the polled one in `useUploadJobPolling`. Returns false when the
   * drawing was rejected and deleted.
   */
  applyCompletedDrawing: (drawing: DrawingItem, side: "old" | "new") => boolean;
  clearUpload: (side: "old" | "new") => void;
  recalculateCompatibility: () => void;
}

export interface AuditSlice {
  auditStatus: "idle" | "queued" | "auditing" | "completed" | "failed";
  complianceScore: number | null;
  violations: ViolationItem[];
  hiddenViolationIds: Record<string, boolean>;
  selectedViolation: ViolationItem | null;
  auditError: string | null;
  activeSessionId: string | null;

  runAudit: (clientName: string) => Promise<boolean>;
  selectViolation: (violation: ViolationItem | null) => void;
  toggleViolationVisibility: (violationId: string) => void;
  setViolationsVisibility: (violationIds: string[], hidden: boolean) => void;
  setActiveSessionId: (sessionId: string | null) => void;
  setViolations: (violations: ViolationItem[]) => void;
  applyViolationReview: (
    violationId: string,
    resolution: "APPROVED" | "REJECTED" | null,
    remarks: string
  ) => void;
  loadSessionIntoWorkspace: (
    sessionId: string,
    drawing: DrawingItem,
    referenceDrawing: DrawingItem | null,
    violations: ViolationItem[],
    complianceScore: number | null,
    clientName: string | null
  ) => void;
}

export interface ClientSlice {
  selectedClient: string | null;
  setSelectedClient: (name: string | null) => void;
}

export interface UndoSlice {
  /** Deleted markers, for the context menu's "Undo Delete". See createUndoSlice for how this
   *  stays consistent with the Ctrl+Z history in `stores/historyStore.ts`. */
  deletedViolationsStack: ViolationItem[];

  pushDeletedViolation: (violation: ViolationItem) => void;
  popAndRestoreViolation: () => void;
}

export interface PenStroke {
  id: string;
  drawingId: string;
  points: [number, number][]; // in CAD world coordinates
  color: string;             // hex color e.g. '#ff2850'
  width: number;             // stroke thickness
  createdAt: string;
}

export interface AnnotationsSlice {
  annotations: AnnotationItem[];
  selectedAnnotationId: string | null;
  isPlacingAnnotation: boolean;
  pendingAnnotationText: string;
  pendingAnnotationSeverity: AnnotationSeverity;

  // Freehand Pen Tool
  penStrokes: PenStroke[];
  isPenActive: boolean;
  penColor: string;
  penWidth: number;
  addPenStroke: (stroke: Omit<PenStroke, 'id' | 'createdAt'>) => void;
  removePenStroke: (id: string) => void;
  undoLastPenStroke: (drawingId?: string) => void;
  clearPenStrokes: (drawingId?: string) => void;
  setIsPenActive: (active: boolean) => void;
  setPenColor: (color: string) => void;
  setPenWidth: (width: number) => void;

  fetchAnnotations: (drawingId: string) => Promise<void>;
  createAnnotationAt: (
    coordinates: [number, number],
    content: string,
    drawingId: string,
    severity?: AnnotationSeverity,
    violationId?: string | null
  ) => Promise<void>;
  deleteAnnotationById: (id: string) => Promise<void>;
  updateAnnotationDetails: (
    id: string,
    updates: Partial<{ content: string; status: string; severity: AnnotationSeverity; pen_type: AnnotationPenType; coordinates: [number, number] | null }>
  ) => Promise<void>;
  updateAnnotationStatus: (id: string, status: string) => Promise<void>;
  // Local-only coordinate update for drag-in-progress — no network round trip.
  // Callers must follow up with updateAnnotationDetails({ coordinates }) on
  // drag end to persist; this exists purely so the pin can track the cursor
  // at 60fps without hitting the PATCH endpoint on every mousemove.
  moveAnnotationLocal: (id: string, coordinates: [number, number]) => void;
  selectAnnotation: (id: string | null) => void;
  setIsPlacingAnnotation: (v: boolean) => void;
  setPendingAnnotationText: (text: string) => void;
  setPendingAnnotationSeverity: (severity: AnnotationSeverity) => void;
}

/** A stamped entity, captured at click time from the picking index. */
export interface PickedEntity {
  /**
   * The semantic zone the entity sits in, or null where none was measured.
   *
   * Carried so a marking can derive its category without a dialog. Null means ASK — the engineer
   * still chooses — rather than "unclassified"; see `categoryForZone`.
   */
  zone?: string | null;
  drawingId: string;
  side: "ref" | "rev";
  entityId: string;
  handle: string | null;
  parentHandle: string | null;
  entityType: string;
  layer: string;
  /** Verbatim entity text. Read, never typed — nothing in the UI can edit it. */
  text: string;
  coordinates: [number, number];
}

/**
 * The VALUE under the cursor, so the other canvas can outline the same value.
 *
 * ## Why this is a value and no longer a position
 *
 * It was fractions of each sheet's `render_bounds` until 2026-08-18, on the reasoning that a
 * position is a weaker hint than a pairing. Two things were wrong with that.
 *
 * The arithmetic was a no-op: both canvases share ONE `viewport` from `reviewStore`, and each
 * builds `scale = viewport.scale * 1000/spanX` with `transX = viewport.x - xmin*scale`, so a
 * fraction resolves to `f*1000*viewport.scale + viewport.x` on either sheet. The target's span
 * cancels exactly — measured dx = 0.000000 and dw = 0.000000 across a 3x bounds difference. The
 * "ghost" was the source rectangle redrawn at the same canvas pixel, off in Y by the ratio of
 * the two aspect ratios and by nothing else.
 *
 * And the premise was wrong regardless: `render_bounds` is the extracted-entity bounding box
 * plus 5% (`viewport_generator.py`), not the paper, and the sheets do not lay out alike.
 * `M745204N01` is a clean 3x uniform scaling of that box, matching aspect to four decimals, and
 * its two sides still place their views differently — so the same fraction is a different
 * feature. Owner's call, 2026-08-18: match the value, not the place.
 *
 * This does now suggest a correspondence, which the position version deliberately withheld —
 * see the note in `renderManualMarkings`. The category selector stays unfilled.
 */
/**
 * Enough of an entity's identity to find its counterpart on the OTHER sheet.
 *
 * Named for hover until 2026-08-18, when selecting an entity started publishing one too. The
 * two gestures build it the same way on purpose — see `buildLocator` in `useEntityPicking`,
 * which is the single place that constructs it. Two constructions of "what is this entity, for
 * matching purposes" would keep working while they drifted, and the overlay would just quietly
 * pair different things depending on which gesture you used.
 */
export interface EntityLocator {
  /** Which canvas the entity is on. The other one outlines the match. */
  side: "ref" | "rev";
  /** Normalized value of the entity — see `normalizeEntityValue`. Never empty. */
  value: string;
  /** `text` / `dimension` / `leader`. A dimension must not match a note that reads the same. */
  entityType: string;
  /** Low 3 bits of `dim_type`; `null` when not a dimension. Separates 80° from a linear 80. */
  dimKind: number | null;
  /** Semantic zone the entity sits in, so a BOM value never matches the same value in a view. */
  zone: string | null;
  /**
   * Whether the source sheet MEASURED that zone (`content_aware`) or guessed it
   * (`percentage_fallback`). Zone is only filtered on where both sides measured it: gating
   * unconditionally blanked 120 of 184 hovers on `M745204N01`, whose reference guesses
   * `tolerance`, `notes` and `iso` and so disagrees with the revision about where they are.
   */
  zoneMeasured: boolean;
  /** Position within that zone. Tie-break only, when both sides measured the same zone. */
  zfx: number | null;
  zfy: number | null;
  /**
   * Where the entity sits among the other copies of its own value on its sheet. The tie-break
   * that survives the two sheets being laid out differently — see `ValueMatchSpec.cfx`.
   */
  cfx: number | null;
  cfy: number | null;
  /** Position within the sheet. The weakest tie-break; orders equals, identifies nothing. */
  sfx: number | null;
  sfy: number | null;
}

export type StampTool = "matched" | "added" | "removed" | "changed" | "mismatched" | "not_a_finding";

/**
 * One stamp, as the canvas assembled it. The argument to `recordStamp`.
 *
 * It was once "a stamp awaiting the engineer's category and notes", held in store state while a
 * modal collected them. That modal was deleted on 2026-08-20 — see `CommitStampInput` — so this
 * is now a plain argument type and never store state.
 */
export interface PendingStamp {
  tool: StampTool;
  ref: PickedEntity | null;
  rev: PickedEntity | null;
}

/**
 * Everything `recordStamp` needs beyond the stamp itself.
 *
 * `textWasEdited`, `isBulk` and `notes` are structurally always `false` / `false` / `''`.
 * They are on the wire model and on `GroundTruthMarking` because the capture schema is a
 * deliberate superset of what a corpus label needs, but the only surface that writes a marking
 * is `SelectionMenu`, and it has no field for any of the three.
 *
 * `StampMarkingModal` was the UI that collected them, and it was dead code: `openStamp` had five
 * call sites and every one passed `null`, so `pendingStamp` was permanently null and the modal
 * never rendered. Deleted 2026-08-20 rather than revived, so that the emptiness is visible here
 * instead of looking like data nobody happened to fill in.
 *
 * The downstream consequence, which is the part that matters: `ExpectedFinding.is_bulk` is
 * therefore always `false`, and the eval manifest's `bulk_count` is always `0`. Do not read
 * either as a measurement. See
 * `docs/vault/06 - Gotchas & Debugging Lessons/Gotcha - Manual Check Wrote Through And Still Lost Work.md`.
 */
export interface CommitStampInput {
  category: string;
  /** Where the category came from. Omitted means a person chose it. */
  categorySource?: 'human' | 'zone';
  feature?: string | null;
  refText: string;
  revText: string;
  textWasEdited: boolean;
  isBulk: boolean;
  notes: string;
}

export interface NavSlice {
  currentNav: "workspace" | "standards" | "history" | "settings";
  hasHydrated: boolean;
  setCurrentNav: (nav: "workspace" | "standards" | "history" | "settings") => void;
  setHasHydrated: (state: boolean) => void;
  resetWorkspace: () => void;
}

/**
 * Manual engineer check — the ground-truth capture session.
 *
 * Held here rather than in `reviewStore` because these are *records*, not view state: every
 * marking is already persisted server-side by the time it lands in `markings`. The mode flag
 * itself lives in `reviewStore` beside every other mode toggle.
 *
 * `pendingPairRef` is the half-finished CHANGED pair — whichever half was picked FIRST, which
 * since 2026-08-18 may be either sheet's; its own `side` says which, and the pair is assembled
 * from that rather than from click order. (The name predates the symmetry and is kept because
 * renaming state that several components read is not worth a docstring.) It exists as explicit
 * state rather than as a closure inside the mouse handler so the toolbar can show that a
 * pairing is in flight — a click that silently does nothing until the second click is how a
 * user concludes the tool is broken.
 */
export interface ManualCheckSlice {
  manualSessionId: string | null;
  manualSessionStatus: "in_progress" | "submitted" | "completed" | null;
  /**
   * The drawing pair the open session belongs to, as `room:ref:rev`.
   *
   * Without it the open effect can only ask "is a session open?", which is the wrong question:
   * on an app reload the workspace restores its drawings from IndexedDB and then `openRoom`
   * overwrites them with the server's, so a session opened in that window is bound to the
   * previous pair — and the guard that stops a second open also stops the correction. The panel
   * then lists a different pair's markings, which is usually none.
   */
  manualSessionPair: string | null;
  /**
   * Why the last open failed, or null.
   *
   * Recorded because the failure was silent: the catch reset `manualSessionId` to the null it
   * already held, so nothing re-rendered and nothing retried, and the panel showed
   * "0 markings recorded" — indistinguishable from a session that really is empty.
   */
  manualSessionError: string | null;
  markings: GroundTruthMarking[];
  pendingPairRef: PickedEntity | null;
  /**
   * What the half-finished pair will become when its counterpart is picked.
   *
   * CHANGED was the only two-click status until 2026-08-18. MATCHED joined it because automatic
   * pairing genuinely cannot always answer: on `M745204N01` the reference reads `2 ロール：4
   * (2x2台)` and the revision `2ロール：4（2×6台）` — different VALUES, not different spellings,
   * so the matcher is right to refuse and only a person can say they correspond. Without a manual
   * route that judgement was unrecordable.
   */
  pendingPairTool: StampTool;
  /** The entity under the cursor, or null. Drives the hover highlight only. */
  hoveredEntityId: string | null;
  /**
   * Where to float the selection's own menu, in canvas pixels, and which canvas owns it.
   *
   * In the store rather than in `DrawingCanvas` because there are TWO canvases and only one menu
   * may be open: local state would leave the other pane's menu standing after a click over here.
   * `drawingId` is what each pane compares against to decide whether the menu is its own.
   */
  selectionMenu: {
    x: number;
    y: number;
    drawingId: string;
    targetBounds?: { x0: number; y0: number; x1: number; y1: number };
  } | null;
  /**
   * The OTHER sheet's entity for the current selection, when exactly one was resolved.
   *
   * Published by the pane that resolved it — the counterpart lives in that canvas's pick index,
   * and the pane showing the selection cannot see it. `null` whenever the match was ambiguous
   * (several candidates carry the value and nothing separates them), which is the case a
   * MATCHED must not silently guess through.
   */
  selectionCounterpart: PickedEntity | null;
  /** Same value, other sheet, following the cursor. See `EntityLocator`. */
  hoverLocator: EntityLocator | null;
  /**
   * Same value, other sheet, for what is SELECTED — so the pair stays outlined once the cursor
   * moves away. Hover could not do this job: it is cleared the moment you leave the entity, and
   * the engineer needs to look at both sheets at once to judge a pair.
   */
  selectionLocator: EntityLocator | null;
  /**
   * The entity the context menu was opened on.
   *
   * Captured at right-click rather than re-picked when a menu item fires: the menu sits over
   * the canvas, so by the time the click lands the cursor is on the menu and a fresh hit test
   * would resolve to whatever happens to be underneath it.
   */
  /**
   * What the engineer has selected on the canvas — currently always one entity, from a
   * left-click. A LIST rather than a single pick because the context menu and the renderer both
   * read it, and a multi-select gesture would otherwise change the shape both depend on.
   *
   * Replaced `contextPickedEntity` on 2026-08-18, when left-click stopped opening the stamping
   * menu and started selecting instead. A single nullable pick and a list would have been two
   * sources of truth for "what am I about to record against", so there is only the list.
   */
  selectedEntities: PickedEntity[];
  /**
   * Why the last WRITE failed, or null. Distinct from `manualSessionError`, which is about
   * opening the session.
   *
   * Recorded because all three write actions used to fail silently: `SelectionMenu` swallowed
   * `recordStamp`'s rejection in a bare `.catch(() => {})`, and retract and submit swallowed
   * theirs in the store. A failed stamp left the entity unmarked with no UI at all —
   * indistinguishable from a mis-click — and a failed submit still rendered "Check submitted".
   */
  markingError: string | null;

  setSelectedEntities: (picked: PickedEntity[]) => void;
  setHoveredEntityId: (id: string | null) => void;
  setHoverLocator: (locator: EntityLocator | null) => void;
  setSelectionLocator: (locator: EntityLocator | null) => void;
  setSelectionMenu: (
    menu: {
      x: number;
      y: number;
      drawingId: string;
      targetBounds?: { x0: number; y0: number; x1: number; y1: number };
    } | null,
  ) => void;
  setSelectionCounterpart: (picked: PickedEntity | null) => void;
  setPendingPairRef: (picked: PickedEntity | null, tool?: StampTool) => void;
  clearMarkingError: () => void;
  startManualSession: (roomId: string, refDrawingId: string, revDrawingId: string) => Promise<void>;
  recordStamp: (stamp: PendingStamp, input: CommitStampInput) => Promise<void>;
  /** Resolves true when the server confirmed the retraction. Never throws. */
  retractManualMarking: (markingId: string) => Promise<boolean>;
  /** Resolves true when the server confirmed the submit. Never throws. */
  submitManualSession: () => Promise<boolean>;
  /** Reopen a submitted session for editing. Never throws. */
  reopenManualSession: () => Promise<boolean>;
}

export type WorkspaceState = ComparisonSlice & UploadSlice & AuditSlice & ClientSlice & UndoSlice & NavSlice & AnnotationsSlice & ManualCheckSlice;
