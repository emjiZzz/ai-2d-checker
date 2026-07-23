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
  selectDrawingFromLibrary: (drawing: DrawingItem, side: "old" | "new") => Promise<void>;
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

export interface NavSlice {
  currentNav: "workspace" | "standards" | "history" | "settings";
  hasHydrated: boolean;
  setCurrentNav: (nav: "workspace" | "standards" | "history" | "settings") => void;
  setHasHydrated: (state: boolean) => void;
  resetWorkspace: () => void;
}

export type WorkspaceState = ComparisonSlice & UploadSlice & AuditSlice & ClientSlice & UndoSlice & NavSlice;
