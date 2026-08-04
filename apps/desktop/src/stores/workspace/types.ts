import type { DrawingZonesResponse } from "../../services/drawingsApi";

export interface DrawingItem {
  id: string;
  file_name: string;
  file_path: string;
  format: string;
  file_size_bytes?: number;
  entity_counts: Record<string, number>;
  metadata: Record<string, any>;
  status?: string;
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

export function getAnnotationBadgeMap(annotations?: AnnotationItem[]): Record<string, string> {
  const list = Array.isArray(annotations) ? annotations : [];
  const sorted = [...list].sort(
    (a, b) => new Date(a?.created_at || 0).getTime() - new Date(b?.created_at || 0).getTime()
  );
  const map: Record<string, string> = {};
  sorted.forEach((ann, idx) => {
    if (ann?.id) {
      map[ann.id] = `A${String(idx + 1).padStart(3, '0')}`;
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

export interface UndoAction {
  type: "move" | "delete";
  violationId: string;
  oldCoords?: [number, number];
  newCoords?: [number, number];
  oldRefCoords?: [number, number];
  newRefCoords?: [number, number];
  violation?: ViolationItem;
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
  aiChecklistResults: Record<string, any>;
  aiScanError: string | null;
  setAiScanProgress: (progress: "idle" | "completed" | string) => void;
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
  setViolations: (violations: ViolationItem[]) => void;
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
  deletedViolationsStack: ViolationItem[];
  undoStack: UndoAction[];

  pushDeletedViolation: (violation: ViolationItem) => void;
  popAndRestoreViolation: () => void;
  pushUndoAction: (action: UndoAction) => void;
  undoLastAction: () => void;
}

export interface AnnotationsSlice {
  annotations: AnnotationItem[];
  selectedAnnotationId: string | null;
  isPlacingAnnotation: boolean;
  pendingAnnotationText: string;
  pendingAnnotationSeverity: AnnotationSeverity;

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

export interface NavSlice {
  currentNav: "workspace" | "standards" | "history" | "settings";
  hasHydrated: boolean;
  setCurrentNav: (nav: "workspace" | "standards" | "history" | "settings") => void;
  setHasHydrated: (state: boolean) => void;
  resetWorkspace: () => void;
}

export type WorkspaceState = ComparisonSlice & UploadSlice & AuditSlice & ClientSlice & UndoSlice & NavSlice & AnnotationsSlice;
