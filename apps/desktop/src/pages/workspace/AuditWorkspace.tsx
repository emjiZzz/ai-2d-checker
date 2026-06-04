import React, { useState, useEffect } from "react";
import { useWorkspaceStore, DrawingItem } from "../../stores/workspaceStore";
import { useConnectionStore } from "../../stores/connectionStore";
import { DrawingCanvas, DrawingCanvasRef } from "../../components/review/DrawingCanvas";
import { useReviewStore } from "../../stores/reviewStore";
import { useAuthStore } from "../../stores/authStore";
import { useAuditStore } from "../../stores/auditStore";
import {
  CheckCircle2,
  Play,
  Sparkles,
  ZoomIn,
  ZoomOut,
  Maximize,
  Loader,
  Upload,
  Trash2,
  AlertTriangle,
  ChevronRight,
  ChevronLeft,
  FolderOpen,
  Edit,
  Search,
  Filter,
  Clock,
  Database,
  TrendingUp,
  BarChart2,
  Briefcase,
  FileText,
  ChevronDown,
  Download
} from "lucide-react";

import { jsPDF } from "jspdf";
import { save } from "@tauri-apps/plugin-dialog";
import { writeFile } from "@tauri-apps/plugin-fs";
import { StandardsManager } from "../../components/StandardsManager";

// Helper utility to parse ISO datetime strings from backend reliably as UTC
const parseUtcDate = (dateStr: string | null | undefined): Date => {
  if (!dateStr) return new Date();
  const utcStr = dateStr.includes("Z") || dateStr.includes("+") ? dateStr : dateStr + "Z";
  return new Date(utcStr);
};

// ─── UPLOAD ZONE ─────────────────────────────────────────────────────────────
// Defined OUTSIDE AuditWorkspace to prevent remounting on every parent render.
// Moving it inside would destroy fileInputRef & isDragActive state each re-render.
interface UploadZoneProps {
  side: "old" | "new";
  uploadState: import("../../stores/workspaceStore").UploadState;
  progress: number;
  fileName: string | null;
  fileSize: number | null;
  error: string | null;
  activeDrawing: import("../../stores/workspaceStore").DrawingItem | null;
  uploadDrawingFile: (file: File, side: "old" | "new") => Promise<boolean>;
  clearUpload: (side: "old" | "new") => void;
}

const UploadZone: React.FC<UploadZoneProps> = ({
  side, uploadState, progress, fileName, error,
  uploadDrawingFile,
}) => {
  const [isDragActive, setIsDragActive] = React.useState(false);
  const fileInputRef = React.useRef<HTMLInputElement>(null);

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") setIsDragActive(true);
    else if (e.type === "dragleave") setIsDragActive(false);
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragActive(false);
    if (e.dataTransfer.files?.[0]) await uploadDrawingFile(e.dataTransfer.files[0], side);
  };

  const handleFileInput = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files?.[0]) {
      await uploadDrawingFile(e.target.files[0], side);
      e.target.value = "";
    }
  };

  const triggerFileInput = () => fileInputRef.current?.click();
  const canInteract = uploadState === "idle" || uploadState === "failed";

  return (
    <div
      className={`upload-dropzone-container ${side} ${uploadState} ${isDragActive ? "dragging" : ""}`}
      onDragEnter={handleDrag}
      onDragOver={handleDrag}
      onDragLeave={handleDrag}
      onDrop={handleDrop}
      onClick={canInteract ? triggerFileInput : undefined}
      style={{ cursor: canInteract ? "pointer" : "default" }}
    >
      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,.dwg,.dxf"
        onChange={handleFileInput}
        style={{ display: "none" }}
      />

      {uploadState === "idle" && (
        <div className="dropzone-idle-view">
          <div className="dropzone-icon-circle">
            <Upload size={14} className="dropzone-upload-icon" />
          </div>
          <div className="dropzone-text-group">
            <p className="dropzone-main-text">
              Drag & drop or <span className="browse-link">browse</span>
            </p>
            <p className="dropzone-sub-text">
              DWG, DXF, PDF (max. 50MB)
            </p>
          </div>
        </div>
      )}

      {(uploadState === "validating" || uploadState === "uploading" || uploadState === "processing") && (
        <div className="dropzone-active-view">
          <div className="pulsing-loader-wrapper">
            <Loader size={14} className="loader-spin-icon spin-animation" />
          </div>
          <div className="active-details-wrapper">
            <span className="active-status-title">
              {uploadState === "validating" && "Scanning signature..."}
              {uploadState === "uploading" && `Uploading... ${progress}%`}
              {uploadState === "processing" && "Ingesting CAD layout..."}
            </span>
            <span className="active-filename-sub">{fileName}</span>
          </div>
          <div className="dropzone-progress-bar-bg">
            <div className="dropzone-progress-bar-fill" style={{ width: `${progress}%` }}></div>
          </div>
        </div>
      )}

      {uploadState === "failed" && (
        <div className="dropzone-failed-view" onClick={(e) => { e.stopPropagation(); triggerFileInput(); }}>
          <div className="failed-icon-circle">
            <AlertTriangle size={14} className="dropzone-error-icon" />
          </div>
          <div className="failed-text-group">
            <span className="failed-status-title">Ingestion Failure</span>
            <p className="failed-error-desc">{error || "Security/validation rejection."}</p>
          </div>
          <span className="retry-link-label">Retry browse</span>
        </div>
      )}
    </div>
  );
};

export const AuditWorkspace: React.FC = () => {
  const backendUrl = useConnectionStore((s) => s.backendUrl);
  const apiToken = useConnectionStore((s) => s.apiToken);

  // Selected workspace navigation sub-view from global workspaceStore
  const currentNav = useWorkspaceStore((s) => s.currentNav);
  const setCurrentNav = useWorkspaceStore((s) => s.setCurrentNav);
  const [isRightPanelCollapsed, setIsRightPanelCollapsed] = useState(false);
  const [isLeftPanelCollapsed, setIsLeftPanelCollapsed] = useState(false);
  // Local drawing catalog for selections
  const [drawings, setDrawings] = useState<DrawingItem[]>([]);

  // Sidebar drag-to-resize states
  const [leftSidebarWidth, setLeftSidebarWidth] = useState(400);
  const [rightSidebarWidth, setRightSidebarWidth] = useState(400);
  const [isResizingLeft, setIsResizingLeft] = useState(false);
  const [isResizingRight, setIsResizingRight] = useState(false);

  // Draggable Sidebar Panels resizing logic
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (isResizingLeft) {
        const newWidth = Math.max(250, Math.min(600, e.clientX));
        setLeftSidebarWidth(newWidth);
      }
      if (isResizingRight) {
        const newWidth = Math.max(250, Math.min(600, window.innerWidth - e.clientX));
        setRightSidebarWidth(newWidth);
      }
    };

    const handleMouseUp = () => {
      setIsResizingLeft(false);
      setIsResizingRight(false);
    };

    if (isResizingLeft || isResizingRight) {
      window.addEventListener("mousemove", handleMouseMove);
      window.addEventListener("mouseup", handleMouseUp);
    }

    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
  }, [isResizingLeft, isResizingRight]);

  // Canvas size and container references
  const containerRefOld = React.useRef<HTMLDivElement>(null);
  const containerRefNew = React.useRef<HTMLDivElement>(null);
  const drawingCanvasRefOld = React.useRef<DrawingCanvasRef>(null);
  const drawingCanvasRefNew = React.useRef<DrawingCanvasRef>(null);
  const [oldSize, setOldSize] = useState({ width: 480, height: 400 });
  const [newSize, setNewSize] = useState({ width: 480, height: 400 });

  useEffect(() => {
    console.log("Ingestion Sandbox: Loaded drawings database size:", drawings.length);
  }, [drawings]);
  useEffect(() => {
    const loadMetadata = async () => {
      try {
        const headers: Record<string, string> = { "Accept": "application/json" };
        if (apiToken) {
          headers["Authorization"] = `Bearer ${apiToken}`;
        }

        // Load drawings
        const dwgRes = await fetch(`${backendUrl}/api/v1/drawings`, { headers });
        const dwgData = await dwgRes.json();
        if (dwgRes.ok && dwgData.success) {
          // If no drawings returned, mock a standard list so the user is wowed immediately!
          if (dwgData.data && dwgData.data.length > 0) {
            setDrawings(dwgData.data);
          } else {
            setDrawings([
              {
                id: "dwg_01",
                file_name: "floor_layout_v1_reference.dwg",
                file_path: "uploads/dwg_01.dwg",
                format: "dwg",
                entity_counts: { LINE: 1204, CIRCLE: 480, TEXT: 125, DIMENSION: 94 },
                metadata: { extmin: [0, 0], extmax: [400, 300] },
                created_at: new Date(Date.now() - 3600 * 1000).toISOString()
              },
              {
                id: "dwg_02",
                file_name: "floor_layout_v2_revision.dwg",
                file_path: "uploads/dwg_02.dwg",
                format: "dwg",
                entity_counts: { LINE: 1225, CIRCLE: 478, TEXT: 132, DIMENSION: 95 },
                metadata: { extmin: [0, 0], extmax: [400, 300] },
                created_at: new Date().toISOString()
              }
            ]);
          }
        }

        // Load standards list
        const stdRes = await fetch(`${backendUrl}/api/v1/standards`, { headers });
        const stdData = await stdRes.json();
        if (stdRes.ok && stdData.success && stdData.data.length > 0) {
          // No longer assigning standards here
        } else {
          // No longer assigning mock standards here
        }
      } catch (err) {
        console.error("Failed to load metadata in auditor workspace:", err);
      }
    };
    loadMetadata();
  }, [backendUrl, apiToken]);

  // Connect to workspaceStore
  const {
    oldDrawing,
    newDrawing,
    oldLayers,
    newLayers,
    auditStatus,
    complianceScore,
    violations,
    selectedViolation,
    runAudit,
    selectViolation,
    // Stage 1 upload state machine values
    oldUploadState,
    newUploadState,
    oldUploadProgress,
    newUploadProgress,
    oldFileName,
    newFileName,
    oldFileSize,
    newFileSize,
    oldError,
    newError,
    compatibilityStatus,
    uploadDrawingFile,
    clearUpload,
    // Client selection state
    clients,
    selectedClient,
    setSelectedClient,
    fetchClients
  } = useWorkspaceStore();

  const {
    viewport: reviewViewport,
    setViewport: setReviewViewport
  } = useReviewStore();

  // Auth: read current user role to enforce access gates
  const user = useAuthStore((s) => s.user);
  const isAdmin = user?.role === "admin";

  const {
    sessions,
    fetchSessions,
    deleteSession,
    updateSession
  } = useAuditStore();

  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [selectedSessionForEdit, setSelectedSessionForEdit] = useState<any>(null);
  const [selectedSessionForDelete, setSelectedSessionForDelete] = useState<any>(null);
  const [remarksText, setRemarksText] = useState("");

  // Automated AI Physical Comparison State
  const [aiScanProgress, setAiScanProgress] = useState<"idle" | "scanning_ref" | "extracting" | "scanning_rev" | "comparing" | "completed">("idle");
  const [aiChecklistResults, setAiChecklistResults] = useState<Record<string, any>>({});
  const [expandedChecklistPanels, setExpandedChecklistPanels] = useState<Record<string, boolean>>({});
  const [aiScanError, setAiScanError] = useState<string | null>(null);

  const toggleChecklistPanel = (key: string) => {
    setExpandedChecklistPanels(prev => ({ ...prev, [key]: !prev[key] }));
  };

  const runPhysicalComparisonAI = async () => {
    if (!oldDrawing || !newDrawing) return;

    setAiScanProgress("comparing");
    setAiScanError(null); // Clear any previous error on new scan

    try {
      const headers: Record<string, string> = {
        "Content-Type": "application/json",
        "Accept": "application/json"
      };
      if (apiToken) {
        headers["Authorization"] = `Bearer ${apiToken}`;
      }

      const res = await fetch(`${backendUrl}/api/v1/audits/physical-comparison`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          reference_drawing_id: oldDrawing.id,
          drawing_id: newDrawing.id
        })
      });

      if (!res.ok) {
        let errMsg = `Comparison API returned status ${res.status}`;
        try {
          const errData = await res.json();
          if (errData && errData.detail) {
            errMsg = errData.detail;
          } else if (errData && errData.error && errData.error.message) {
            errMsg = errData.error.message;
          }
        } catch (_) { }
        throw new Error(errMsg);
      }

      const data = await res.json();
      if (!data.success || !data.data) {
        throw new Error(data.error?.message || "Comparison failed");
      }

      setAiChecklistResults(data.data);
      setAiScanProgress("completed");

      // Auto-expand all panels by default to show rich, visually appealing discrepancy metrics
      setExpandedChecklistPanels({
        drawing_views: true,
        notes_section: true,
        bill_of_materials: true,
        title_block: true,
        isometric_view: true,
        other_engineering_references: true
      });

      // DYNAMIC VISUAL MARKINGS DIRECTLY ON THE CANVAS!
      try {
        const cleanCadText = (text: string): string => {
          if (!text) return "";
          let clean = text;
          // Replace CP932 decoded multiplication sign "ラ" with standard lowercase "x"
          clean = clean.replace(/ラ/g, "x");
          clean = clean.replace(/[{}]/g, "");
          clean = clean.replace(/\\[A-Za-z][^;]*;/g, "");
          clean = clean.replace(/\\P/g, " ");
          return clean.trim();
        };

        const normalizeStr = (str: string) => {
          let s = str.toLowerCase().trim();
          // Replace CP932 decoded multiplication sign "ラ" with standard lowercase "x"
          s = s.replace(/ラ/g, "x");
          s = s.replace(/×/g, "x");
          s = s.replace(/:/g, "/");
          return s
            .replace(/[\s\(\)\[\]\{\}\:\;\,\-\_\.\/\引\（\）]/g, "")
            .trim();
        };

        // findFuzzyMatch removed to satisfy strict TypeScript unused variable compiler rules

        const findAllFuzzyMatches = (
          searchTerm: string,
          entities: { text: string; x: number; y: number; bbox?: any; height?: number; layoutSpace?: string; layer?: string }[],
          preferModelSpace: boolean = false,
          allowNumberMismatch: boolean = false
        ): { text: string; x: number; y: number; bbox?: any; height?: number; layoutSpace?: string; layer?: string }[] => {
          if (!searchTerm) return [];
          const normSearch = normalizeStr(searchTerm);
          if (!normSearch) return [];

          const matches: { ent: any; score: number }[] = [];
          const extractNumbers = (s: string) => {
            const m = s.match(/\d+/g);
            return m ? m.join("") : "";
          };
          const searchNumbers = extractNumbers(normSearch);

          for (const ent of entities) {
            const normEnt = normalizeStr(ent.text);
            if (!normEnt) continue;

            let score = 0;
            if (ent.text.trim() === searchTerm.trim()) {
              score = 105;
            } else if (normEnt === normSearch) {
              score = 100;
            } else if (
              normEnt.replace(/^[0-9]+-/, "") === normSearch ||
              normSearch.replace(/^[0-9]+-/, "") === normEnt ||
              normEnt.replace(/^[rmøø]/i, "") === normSearch ||
              normSearch.replace(/^[rmøø]/i, "") === normEnt
            ) {
              score = 90;
            } else {
              const stripLeadDigits = (s: string) => s.replace(/^\d+/, "");
              const strippedSearch = stripLeadDigits(normSearch);
              const strippedEnt = stripLeadDigits(normEnt);
              if (strippedSearch.length >= 2 && strippedSearch === strippedEnt) {
                score = 85;
              } else if (normSearch.includes(normEnt) || normEnt.includes(normSearch)) {
                const minLen = Math.min(normEnt.length, normSearch.length);
                const maxLen = Math.max(normEnt.length, normSearch.length);
                const ratio = minLen / maxLen;
                if (minLen >= 2) {
                  score = 50 + ratio * 30;
                }
              } else {
                const searchChars = new Set(normSearch.split(""));
                const entChars = new Set(normEnt.split(""));
                let intersection = 0;
                searchChars.forEach(c => { if (entChars.has(c)) intersection++; });
                const jaccard = intersection / Math.max(searchChars.size, entChars.size);
                if (jaccard > 0.60) {
                  score = jaccard * 70;
                }
              }
            }

            if (searchNumbers && !allowNumberMismatch) {
              const entNumbers = extractNumbers(normEnt);
              if (entNumbers && entNumbers !== searchNumbers) {
                score = 0;
              }
            }

            const spaceBonus = (preferModelSpace && ent.layoutSpace === 'Model') ? 5 : 0;
            const effectiveScore = score + spaceBonus;

            if (score > 40) {
              matches.push({ ent, score: effectiveScore });
            }
          }

          if (matches.length === 0) return [];
          const maxScore = Math.max(...matches.map(m => m.score));
          const threshold = maxScore >= 100 ? 100 : (maxScore - 5);
          return matches.filter(m => m.score >= threshold).map(m => m.ent);
        };

        const getRoiFallbackCoordinates = (
          regionKey: string,
          drawing: any,
          index: number
        ): [number, number] => {
          let xmin = 0, ymin = 0, xmax = 400, ymax = 300;
          if (drawing?.metadata?.render_bounds && Array.isArray(drawing.metadata.render_bounds) && drawing.metadata.render_bounds.length >= 4) {
            [xmin, ymin, xmax, ymax] = drawing.metadata.render_bounds;
          } else {
            const extmin = drawing?.metadata?.extmin || [0, 0];
            const extmax = drawing?.metadata?.extmax || [400, 300];
            xmin = extmin[0];
            ymin = extmin[1];
            xmax = extmax[0];
            ymax = extmax[1];
          }
          const width = xmax - xmin;
          const height = ymax - ymin;

          const regions: Record<string, { x: number; y: number }> = {
            notes_section: { x: 0.20, y: 0.40 },
            bill_of_materials: { x: 0.82, y: 0.25 },
            title_block: { x: 0.70, y: 0.85 },
            isometric_view: { x: 0.82, y: 0.60 },
            drawing_views: { x: 0.35, y: 0.50 }
          };

          const center = regions[regionKey] || { x: 0.5, y: 0.5 };
          const staggerX = ((index % 5) - 2) * (width * 0.03);
          const staggerY = ((index % 3) - 1) * (height * 0.03);

          return [
            xmin + (width * center.x) + staggerX,
            ymax - (height * center.y) + staggerY
          ];
        };

        const isTitleBlockLayer = (layerName: string): boolean => {
          const l = (layerName || "").toLowerCase();
          return ["title", "border", "stamp", "attr", "admin", "block", "header", "logo", "dwg", "rev", "approved", "checked", "designed", "drawn", "scale", "date", "waku", "frame"].some(x => l.includes(x));
        };

        const isCoordinateTick = (text: string): boolean => {
          const t = (text || "").trim().toUpperCase();
          if (!t) return true;
          // Single letters A-Z
          if (t.length === 1 && t >= 'A' && t <= 'Z') return true;
          // Simple numbers 1 to 24
          const num = parseInt(t, 10);
          if (!isNaN(num) && num.toString() === t && num >= 1 && num <= 24) return true;
          return false;
        };

        const isStaticLabelOrHeader = (text: string): boolean => {
          const t = (text || "").trim().toLowerCase();
          if (!t) return true;

          // Short terms requiring exact matches to avoid false positives inside regular values/words
          const exactStaticTerms = new Set([
            "no.", "no", "and.", "and", "g", "h", "a", "b", "c", "d", "e", "f", "例", "（例）", "こえ", "下", "符号"
          ]);
          if (exactStaticTerms.has(t)) return true;

          // Descriptive terms that safely support substring matching
          const staticTerms = [
            "tolerances", "unless", "otherwise", "specified", "drawings", "表示外公差",
            "finish", "symbol", "roughness", "range", "仕上げ記号", "面粗さ",
            "dimension", "parallelism", "squareness", "length", "寸法区分", "平行度", "直角度",
            "machining", "fabrication", "general", "over", "including",
            "example", "design chg", "chg no", "年月日", "訂正書", "担当", "name", "y/m/d",
            "material", "code", "材質", "寸法", "型式", "個数", "qty", "weight", "重量", "remark", "備考",
            "dwg no", "dwg. no", "図面番号", "title", "名称", "prev. dwg", "previous dwg",
            "scale", "尺度", "date", "日付", "approved", "承認", "checked", "検図", "designed", "設計", "drawn", "製図",
            "job no", "工事番号", "std no", "標準図番号", "mach. code", "機器記号", "unit no", "ユニット",
            "total quantity", "t. q'ty", "総製作個数", "common", "共通番号", "cross ref"
          ];

          return staticTerms.some(term => t.includes(term));
        };

        let newXMin = 0, newXMax = 1000, newYMin = 0, newYMax = 1000;
        let oldXMin = 0, oldXMax = 1000, oldYMin = 0, oldYMax = 1000;

        const isEngineeringDataEntity = (
          ent: { text: string; x: number; y: number; layer?: string },
          drawing: any
        ): boolean => {
          if (isStaticLabelOrHeader(ent.text)) {
            return false;
          }

          if (ent.layer && isTitleBlockLayer(ent.layer)) {
            return false;
          }

          const isOld = oldDrawing && drawing?.id === oldDrawing.id;
          const xmin = isOld ? oldXMin : newXMin;
          const xmax = isOld ? oldXMax : newXMax;
          const ymin = isOld ? oldYMin : newYMin;
          const ymax = isOld ? oldYMax : newYMax;

          const width = xmax - xmin;
          const height = ymax - ymin;
          if (width <= 0 || height <= 0) return true;

          const pctX = (ent.x - xmin) / width;
          const pctY = 1.0 - (ent.y - ymin) / height;

          // Margin/Tick filter: strictly exclude any text elements at the extreme edges
          if (pctX < 0.045 || pctX > 0.98 || pctY < 0.045 || pctY > 0.98) {
            return false;
          }

          // Strictly filter out any coordinate ticks located near margins
          const isNearMargin = pctX < 0.12 || pctX > 0.88 || pctY < 0.12 || pctY > 0.88;
          if (isNearMargin && isCoordinateTick(ent.text)) {
            return false;
          }

          // Strictly filter out waku / frame / grid / border layers to avoid ticks matches
          const layerStr = (ent.layer || "").toLowerCase();
          const isWakuLayer = ["waku", "border", "frame", "grid", "template", "form", "cosa", "tol", "std", "standard", "legend", "admin", "block", "table"].some(x => layerStr.includes(x));
          if (isWakuLayer) {
            return false;
          }

          // Exclude the entire bottom template footer (general tolerance tables and revision tables)
          // from baseline matched check markers.
          if (pctY >= 0.65) {
            return false;
          }

          // Strict boundary boxes for the 5 functional engineering regions:
          const regions = {
            views: { xMin: 0.04, xMax: 0.68, yMin: 0.12, yMax: 0.88 },
            notes: { xMin: 0.04, xMax: 0.38, yMin: 0.18, yMax: 0.62 },
            bom: { xMin: 0.62, xMax: 0.98, yMin: 0.04, yMax: 0.44 },
            title: { xMin: 0.38, xMax: 0.98, yMin: 0.72, yMax: 0.98 },
            titleUpperLeft: { xMin: 0.02, xMax: 0.35, yMin: 0.02, yMax: 0.35 },
            iso: { xMin: 0.62, xMax: 0.98, yMin: 0.42, yMax: 0.74 }
          };

          const inside = (px: number, py: number, box: { xMin: number; xMax: number; yMin: number; yMax: number }) => {
            return px >= box.xMin && px <= box.xMax && py >= box.yMin && py <= box.yMax;
          };

          const inViews = inside(pctX, pctY, regions.views);
          const inNotes = inside(pctX, pctY, regions.notes);
          const inBom = inside(pctX, pctY, regions.bom);
          const inIso = inside(pctX, pctY, regions.iso);
          const inTitle = inside(pctX, pctY, regions.title);
          const inTitleUL = inside(pctX, pctY, regions.titleUpperLeft);

          // Total Qty must be located only inside the Upper Left Title Block quadrant
          const isTotalQtyText = ["総製作個数", "t. q'ty", "t. qty", "total quantity"].some(x => ent.text.toLowerCase().includes(x));
          if (inTitleUL && isTotalQtyText) {
            return true;
          }

          return inViews || inNotes || inBom || inIso || inTitle;
        };

        const isDuplicateEntity = (
          list: { text: string; x: number; y: number }[],
          text: string,
          x: number,
          y: number
        ): boolean => {
          return list.some(ent => ent.text === text && Math.hypot(ent.x - x, ent.y - y) < 1.0);
        };

        const textEntities: { text: string; x: number; y: number; bbox?: any; height?: number; layoutSpace?: string; layer?: string }[] = [];
        if (newLayers) {
          Object.entries(newLayers).forEach(([layerName, entities]: any) => {
            if (Array.isArray(entities)) {
              entities.forEach((ent: any) => {
                if (ent.type === 'text') {
                  const geo = ent.geometry || {};
                  const rawText = geo.text || geo.content || ent.properties?.text || '';
                  const textVal = cleanCadText(rawText);
                  if (textVal && (geo.location || geo.insert)) {
                    const [tx, ty] = geo.location || geo.insert;
                    const cleanedText = textVal.trim();
                    if (!isDuplicateEntity(textEntities, cleanedText, tx, ty)) {
                      textEntities.push({
                        text: cleanedText,
                        x: tx,
                        y: ty,
                        bbox: ent.properties?.bbox,
                        height: ent.properties?.height,
                        layoutSpace: ent.properties?.layout_space || 'Model',
                        layer: layerName
                      });
                    }
                  }
                }
              });
            }
          });
        }

        const refTextEntities: { text: string; x: number; y: number; bbox?: any; height?: number; layoutSpace?: string; layer?: string }[] = [];
        if (oldLayers) {
          Object.entries(oldLayers).forEach(([layerName, entities]: any) => {
            if (Array.isArray(entities)) {
              entities.forEach((ent: any) => {
                if (ent.type === 'text') {
                  const geo = ent.geometry || {};
                  const rawText = geo.text || geo.content || ent.properties?.text || '';
                  const textVal = cleanCadText(rawText);
                  if (textVal && (geo.location || geo.insert)) {
                    const [tx, ty] = geo.location || geo.insert;
                    const cleanedText = textVal.trim();
                    if (!isDuplicateEntity(refTextEntities, cleanedText, tx, ty)) {
                      refTextEntities.push({
                        text: cleanedText,
                        x: tx,
                        y: ty,
                        bbox: ent.properties?.bbox,
                        height: ent.properties?.height,
                        layoutSpace: ent.properties?.layout_space || 'Model',
                        layer: layerName
                      });
                    }
                  }
                }
              });
            }
          });
        }

        if (textEntities.length > 0) {
          const xs = textEntities.map(t => t.x);
          const ys = textEntities.map(t => t.y);
          newXMin = Math.min(...xs);
          newXMax = Math.max(...xs);
          newYMin = Math.min(...ys);
          newYMax = Math.max(...ys);
        }

        if (refTextEntities.length > 0) {
          const xs = refTextEntities.map(t => t.x);
          const ys = refTextEntities.map(t => t.y);
          oldXMin = Math.min(...xs);
          oldXMax = Math.max(...xs);
          oldYMin = Math.min(...ys);
          oldYMax = Math.max(...ys);
        }

        const mappedMarkings: any[] = [];
        const rawMarkings = data.data.canvas_markings || [];

        const textEntitiesWithMarkers = new Set<string>();
        const refTextEntitiesWithMarkers = new Set<string>();
        const getCoordKey = (x: number, y: number) => `${x.toFixed(2)},${y.toFixed(2)}`;

        rawMarkings.forEach((marking: any, index: number) => {
          const preferModel = (marking.category === 'drawing_views' || !marking.category);

          let searchTerm = marking.text_content;
          if (searchTerm && searchTerm.includes("\n")) {
            const lines = searchTerm.split("\n");
            searchTerm = lines[lines.length - 1].trim();
          }

          let matches = findAllFuzzyMatches(searchTerm, textEntities, preferModel);
          let refMatches = findAllFuzzyMatches(searchTerm, refTextEntities, preferModel);

          // For CHANGED, REMOVED, or ADDED markings, if one of the drawings has zero matches, do a fallback fuzzy pass that ignores numbers!
          if (marking.status === 'CHANGED' || marking.status === 'REMOVED' || marking.status === 'ADDED') {
            if (matches.length === 0) {
              matches = findAllFuzzyMatches(searchTerm, textEntities, preferModel, true);
            }
            if (refMatches.length === 0) {
              refMatches = findAllFuzzyMatches(searchTerm, refTextEntities, preferModel, true);
            }
          }

          const rawMatchesCount = matches.length;
          const rawRefMatchesCount = refMatches.length;

          // Bypass strict spatial boundaries filters for Title Block and BOM markings
          if (marking.category !== "title_block" && marking.category !== "bill_of_materials") {
            matches = matches.filter(m => isEngineeringDataEntity(m, newDrawing));
            refMatches = refMatches.filter(m => isEngineeringDataEntity(m, oldDrawing));
          }

          const maxInstances = Math.max(matches.length, refMatches.length, 1);

          for (let i = 0; i < maxInstances; i++) {
            const match = matches[i] || matches[0];
            const refMatch = refMatches[i] || refMatches[0];

            let coordinates: [number, number] | undefined = undefined;
            if (match) {
              const h = match.height || 3.0;
              if (match.bbox && Array.isArray(match.bbox) && match.bbox.length >= 2) {
                try {
                  const [[, ymin], [xmax, ymax]] = match.bbox;
                  const hVal = match.height || (ymax - ymin) || 3.0;
                  // Shift to the RIGHT: xmax + hVal * 0.8
                  coordinates = [xmax + hVal * 0.8, ymin + ((ymax - ymin) / 2.0)] as [number, number];
                } catch (err) {
                  coordinates = [match.x + h * 0.8, match.y + h * 0.5] as [number, number];
                }
              } else {
                coordinates = [match.x + h * 0.8, match.y + h * 0.5] as [number, number];
              }
            } else if (marking.coordinates && i === 0 && Array.isArray(marking.coordinates) && marking.coordinates.length >= 2) {
              coordinates = [marking.coordinates[0], marking.coordinates[1]] as [number, number];
            }

            let ref_coordinates: [number, number] | undefined = undefined;
            if (refMatch) {
              const h = refMatch.height || 3.0;
              if (refMatch.bbox && Array.isArray(refMatch.bbox) && refMatch.bbox.length >= 2) {
                try {
                  const [[, ymin], [xmax, ymax]] = refMatch.bbox;
                  const hVal = refMatch.height || (ymax - ymin) || 3.0;
                  // Shift to the RIGHT: xmax + hVal * 0.8
                  ref_coordinates = [xmax + hVal * 0.8, ymin + ((ymax - ymin) / 2.0)] as [number, number];
                } catch (err) {
                  ref_coordinates = [refMatch.x + h * 0.8, refMatch.y + h * 0.5] as [number, number];
                }
              } else {
                ref_coordinates = [refMatch.x + h * 0.8, refMatch.y + h * 0.5] as [number, number];
              }
            } else if (marking.ref_coordinates && i === 0 && Array.isArray(marking.ref_coordinates) && marking.ref_coordinates.length >= 2) {
              ref_coordinates = [marking.ref_coordinates[0], marking.ref_coordinates[1]] as [number, number];
            }

            // Proximity counterpart coordinate calibration & exclusions lookup when a match is found on one drawing but not on the other due to spelling/number mismatches
            if (match && !refMatch) {
              let closestEnt: any = null;
              let minDistance = Infinity;
              refTextEntities.forEach(ent => {
                const dist = Math.hypot(ent.x - match.x, ent.y - match.y);
                if (dist < minDistance) {
                  minDistance = dist;
                  closestEnt = ent;
                }
              });
              if (closestEnt && minDistance < 50.0) {
                const rh = closestEnt.height || 3.0;
                ref_coordinates = [closestEnt.x + rh * 0.8, closestEnt.y + rh * 0.5] as [number, number];
                if (closestEnt.bbox && Array.isArray(closestEnt.bbox) && closestEnt.bbox.length >= 2) {
                  try {
                    const [[, bymin], [bxmax, bymax]] = closestEnt.bbox;
                    const hVal = closestEnt.height || (bymax - bymin) || 3.0;
                    ref_coordinates = [bxmax + hVal * 0.8, bymin + ((bymax - bymin) / 2.0)] as [number, number];
                  } catch { }
                }
                refTextEntitiesWithMarkers.add(getCoordKey(closestEnt.x, closestEnt.y));
              }
            }

            if (refMatch && !match) {
              let closestEnt: any = null;
              let minDistance = Infinity;
              textEntities.forEach(ent => {
                const dist = Math.hypot(ent.x - refMatch.x, ent.y - refMatch.y);
                if (dist < minDistance) {
                  minDistance = dist;
                  closestEnt = ent;
                }
              });
              if (closestEnt && minDistance < 50.0) {
                const rh = closestEnt.height || 3.0;
                coordinates = [closestEnt.x + rh * 0.8, closestEnt.y + rh * 0.5] as [number, number];
                if (closestEnt.bbox && Array.isArray(closestEnt.bbox) && closestEnt.bbox.length >= 2) {
                  try {
                    const [[, bymin], [bxmax, bymax]] = closestEnt.bbox;
                    const hVal = closestEnt.height || (bymax - bymin) || 3.0;
                    coordinates = [bxmax + hVal * 0.8, bymin + ((bymax - bymin) / 2.0)] as [number, number];
                  } catch { }
                }
                textEntitiesWithMarkers.add(getCoordKey(closestEnt.x, closestEnt.y));
              }
            }

            // Skip fallback coordinates if potential matches were strictly filtered out as margin ticks
            const isMatchFilteredTick = (rawMatchesCount > 0 && matches.length === 0) || (rawRefMatchesCount > 0 && refMatches.length === 0);

            if (!coordinates && newDrawing && !isMatchFilteredTick) {
              coordinates = getRoiFallbackCoordinates(marking.category || "drawing_views", newDrawing, index + i);
            }
            if (!ref_coordinates && oldDrawing && !isMatchFilteredTick) {
              ref_coordinates = getRoiFallbackCoordinates(marking.category || "drawing_views", oldDrawing, index + i);
            }

            if (match) {
              textEntitiesWithMarkers.add(getCoordKey(match.x, match.y));
              if (marking.text_content && marking.text_content.includes("\n")) {
                const lines = marking.text_content.split("\n");
                lines.forEach((line: string) => {
                  const lineMatches = findAllFuzzyMatches(line.trim(), textEntities, preferModel);
                  lineMatches.forEach((lm: any) => {
                    textEntitiesWithMarkers.add(getCoordKey(lm.x, lm.y));
                  });
                });
              }
            } else if (marking.coordinates && Array.isArray(marking.coordinates) && marking.coordinates.length >= 2) {
              let closestEnt: any = null;
              let minDistance = Infinity;
              textEntities.forEach(ent => {
                const dist = Math.hypot(ent.x - marking.coordinates[0], ent.y - marking.coordinates[1]);
                if (dist < minDistance) {
                  minDistance = dist;
                  closestEnt = ent;
                }
              });
              if (closestEnt && minDistance < 50.0) {
                textEntitiesWithMarkers.add(getCoordKey(closestEnt.x, closestEnt.y));
              }
            }

            if (refMatch) {
              refTextEntitiesWithMarkers.add(getCoordKey(refMatch.x, refMatch.y));
              if (marking.text_content && marking.text_content.includes("\n")) {
                const lines = marking.text_content.split("\n");
                lines.forEach((line: string) => {
                  const lineMatches = findAllFuzzyMatches(line.trim(), refTextEntities, preferModel);
                  lineMatches.forEach((lm: any) => {
                    refTextEntitiesWithMarkers.add(getCoordKey(lm.x, lm.y));
                  });
                });
              }
            } else if (marking.ref_coordinates && Array.isArray(marking.ref_coordinates) && marking.ref_coordinates.length >= 2) {
              let closestEnt: any = null;
              let minDistance = Infinity;
              refTextEntities.forEach(ent => {
                const dist = Math.hypot(ent.x - marking.ref_coordinates[0], ent.y - marking.ref_coordinates[1]);
                if (dist < minDistance) {
                  minDistance = dist;
                  closestEnt = ent;
                }
              });
              if (closestEnt && minDistance < 50.0) {
                refTextEntitiesWithMarkers.add(getCoordKey(closestEnt.x, closestEnt.y));
              }
            }

            let penType = "resolved_green";
            if (marking.status === "REMOVED") {
              penType = "ai_red";
            } else if (marking.status === "CHANGED") {
              penType = "ai_orange";
            } else if (marking.status === "ADDED") {
              penType = "checker_blue";
            }

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
              pen_type: penType,
              is_resolved: marking.status === "MATCHED"
            });
          }
        });

        // Ensure ALL remaining text structures on both drawings receive a Matched marker
        textEntities.forEach((ent, idx) => {
          if (ent.layer && isTitleBlockLayer(ent.layer)) return;
          if (!isEngineeringDataEntity(ent, newDrawing)) return;

          const xmin = newXMin;
          const xmax = newXMax;
          const ymin = newYMin;
          const ymax = newYMax;
          const width = xmax - xmin;
          const height = ymax - ymin;
          if (width > 0 && height > 0) {
            const pctX = (ent.x - xmin) / width;
            const pctY = 1.0 - (ent.y - ymin) / height;
            // Title Block bounding box: xMin: 0.38, xMax: 0.98, yMin: 0.72, yMax: 0.98
            if (pctX >= 0.38 && pctX <= 0.98 && pctY >= 0.72 && pctY <= 0.98) {
              return;
            }
            // Upper Left Title Block quadrant: xMin: 0.02, xMax: 0.35, yMin: 0.02, yMax: 0.35 (Total Qty check)
            const isTotalQtyText = ["総製作個数", "t. q'ty", "t. qty", "total quantity"].some(x => ent.text.toLowerCase().includes(x));
            if (pctX >= 0.02 && pctX <= 0.35 && pctY >= 0.02 && pctY <= 0.35 && isTotalQtyText) {
              return;
            }
          }

          const key = getCoordKey(ent.x, ent.y);
          if (!textEntitiesWithMarkers.has(key)) {
            const preferModel = (ent.layoutSpace === 'Model');
            const refMatches = findAllFuzzyMatches(ent.text, refTextEntities, preferModel);
            const refMatch = refMatches[0];

            if (refMatch) {
              const h = ent.height || 3.0;
              let coordinates: [number, number] = [ent.x + h * 0.8, ent.y + h * 0.5];
              if (ent.bbox && Array.isArray(ent.bbox) && ent.bbox.length >= 2) {
                try {
                  const [[, bymin], [bxmax, bymax]] = ent.bbox;
                  const hVal = ent.height || (bymax - bymin) || 3.0;
                  coordinates = [bxmax + hVal * 0.8, bymin + ((bymax - bymin) / 2.0)];
                } catch { }
              }

              const rh = refMatch.height || 3.0;
              let ref_coordinates: [number, number] = [refMatch.x + rh * 0.8, refMatch.y + rh * 0.5];
              if (refMatch.bbox && Array.isArray(refMatch.bbox) && refMatch.bbox.length >= 2) {
                try {
                  const [[, bymin], [bxmax, bymax]] = refMatch.bbox;
                  const hVal = refMatch.height || (bymax - bymin) || 3.0;
                  ref_coordinates = [bxmax + hVal * 0.8, bymin + ((bymax - bymin) / 2.0)];
                } catch { }
              }

              mappedMarkings.push({
                id: `auto_chk_rev_${idx}_${Date.now()}`,
                severity: "low",
                category: "drawing_views",
                description: ent.text,
                recommendation: "Perfect baseline match verification",
                affected_entities: [],
                confidence: 1.0,
                coordinates,
                ref_coordinates,
                pen_type: "resolved_green",
                is_resolved: true
              });
              textEntitiesWithMarkers.add(key);
              refTextEntitiesWithMarkers.add(getCoordKey(refMatch.x, refMatch.y));
            }
          }
        });

        refTextEntities.forEach((ent, idx) => {
          if (ent.layer && isTitleBlockLayer(ent.layer)) return;
          if (!isEngineeringDataEntity(ent, oldDrawing)) return;

          const xmin = oldXMin;
          const xmax = oldXMax;
          const ymin = oldYMin;
          const ymax = oldYMax;
          const width = xmax - xmin;
          const height = ymax - ymin;
          if (width > 0 && height > 0) {
            const pctX = (ent.x - xmin) / width;
            const pctY = 1.0 - (ent.y - ymin) / height;
            // Title Block bounding box: xMin: 0.38, xMax: 0.98, yMin: 0.72, yMax: 0.98
            if (pctX >= 0.38 && pctX <= 0.98 && pctY >= 0.72 && pctY <= 0.98) {
              return;
            }
            // Upper Left Title Block quadrant: xMin: 0.02, xMax: 0.35, yMin: 0.02, yMax: 0.35 (Total Qty check)
            const isTotalQtyText = ["総製作個数", "t. q'ty", "t. qty", "total quantity"].some(x => ent.text.toLowerCase().includes(x));
            if (pctX >= 0.02 && pctX <= 0.35 && pctY >= 0.02 && pctY <= 0.35 && isTotalQtyText) {
              return;
            }
          }

          const key = getCoordKey(ent.x, ent.y);
          if (!refTextEntitiesWithMarkers.has(key)) {
            const preferModel = (ent.layoutSpace === 'Model');
            const revMatches = findAllFuzzyMatches(ent.text, textEntities, preferModel);
            const revMatch = revMatches[0];

            if (revMatch) {
              const h = ent.height || 3.0;
              let ref_coordinates: [number, number] = [ent.x + h * 0.8, ent.y + h * 0.5];
              if (ent.bbox && Array.isArray(ent.bbox) && ent.bbox.length >= 2) {
                try {
                  const [[, bymin], [bxmax, bymax]] = ent.bbox;
                  const hVal = ent.height || (bymax - bymin) || 3.0;
                  ref_coordinates = [bxmax + hVal * 0.8, bymin + ((bymax - bymin) / 2.0)];
                } catch { }
              }

              const rh = revMatch.height || 3.0;
              let coordinates: [number, number] = [revMatch.x + rh * 0.8, revMatch.y + rh * 0.5];
              if (revMatch.bbox && Array.isArray(revMatch.bbox) && revMatch.bbox.length >= 2) {
                try {
                  const [[, bymin], [bxmax, bymax]] = revMatch.bbox;
                  const hVal = revMatch.height || (bymax - bymin) || 3.0;
                  coordinates = [bxmax + hVal * 0.8, bymin + ((bymax - bymin) / 2.0)];
                } catch { }
              }

              mappedMarkings.push({
                id: `auto_chk_ref_${idx}_${Date.now()}`,
                severity: "low",
                category: "drawing_views",
                description: ent.text,
                recommendation: "Perfect baseline match verification",
                affected_entities: [],
                confidence: 1.0,
                coordinates,
                ref_coordinates,
                pen_type: "resolved_green",
                is_resolved: true
              });
              refTextEntitiesWithMarkers.add(key);
              textEntitiesWithMarkers.add(getCoordKey(revMatch.x, revMatch.y));
            }
          }
        });

        // Set visual markings directly in useWorkspaceStore
        useWorkspaceStore.setState({ violations: mappedMarkings });
        // Enable violations layer visible on DrawingCanvas
        useReviewStore.setState({ showViolations: true, isPhysicalComparisonEnabled: true });

      } catch (err) {
        console.warn("Visual checklist canvas overlay loading failed:", err);
      }
    } catch (err: any) {
      console.error("AI Physical Comparison failed:", err);
      const rawMsg: string = err?.message || String(err);
      // Extract the human-readable part — strip JSON blobs and redundant tech noise
      const isOverload = rawMsg.includes('503') || rawMsg.includes('UNAVAILABLE') || rawMsg.includes('high demand') || rawMsg.includes('overloaded');
      const friendlyMsg = isOverload
        ? 'The Gemini AI service is temporarily overloaded (503). All model fallbacks were exhausted. Please wait 30–60 seconds and try again.'
        : rawMsg.replace(/\. Please verify.*$/i, '').trim();
      setAiScanError(friendlyMsg);
      setAiScanProgress("idle");
    }
  };


  // Interactive search & filter controls for premium History Archive
  const [historySearchQuery, setHistorySearchQuery] = useState("");
  const [historyStatusFilter, setHistoryStatusFilter] = useState<"all" | "completed" | "failed" | "auditing">("all");
  const [historyScoreFilter, setHistoryScoreFilter] = useState<"all" | "excellent" | "warning">("all");

  useEffect(() => {
    if (currentNav === "history") {
      fetchSessions();
    }
  }, [currentNav, fetchSessions]);

  const handleOpenSession = async (session: any) => {
    try {
      const headers: Record<string, string> = { "Accept": "application/json" };
      if (apiToken) {
        headers["Authorization"] = `Bearer ${apiToken}`;
      }

      // Fetch active drawing details (New drawing)
      const drawingRes = await fetch(`${backendUrl}/api/v1/drawings/${session.drawing_id}`, { headers });
      if (!drawingRes.ok) {
        throw new Error(`Drawing details could not be retrieved. The file may have been purged.`);
      }
      const drawingData = await drawingRes.json();
      if (!drawingData.success || !drawingData.data) {
        throw new Error("Failed to load drawing record.");
      }

      // Fetch reference drawing details (Old drawing, if present)
      let referenceDrawingData = null;
      if (session.reference_drawing_id) {
        try {
          const refRes = await fetch(`${backendUrl}/api/v1/drawings/${session.reference_drawing_id}`, { headers });
          if (refRes.ok) {
            const parsedRef = await refRes.json();
            if (parsedRef.success && parsedRef.data) {
              referenceDrawingData = parsedRef.data;
            }
          }
        } catch (refErr) {
          console.warn("Reference drawing failed to fetch or was deleted:", refErr);
        }
      }

      // Fetch violations
      const violationsRes = await fetch(`${backendUrl}/api/v1/audits/sessions/${session.id}/violations`, { headers });
      if (!violationsRes.ok) {
        throw new Error("Failed to retrieve violations logs.");
      }
      const violationsData = await violationsRes.json();
      if (!violationsData.success || !violationsData.data) {
        throw new Error("Failed to parse violations payload.");
      }

      // Load into workspaceStore
      const workspaceStore = useWorkspaceStore.getState();
      workspaceStore.setNewDrawing(drawingData.data);
      if (referenceDrawingData) {
        workspaceStore.setOldDrawing(referenceDrawingData);
      } else {
        workspaceStore.clearUpload("old");
      }

      useWorkspaceStore.setState({
        violations: violationsData.data.map((v: any) => ({
          id: v.id,
          severity: v.severity,
          category: v.category,
          description: v.description,
          recommendation: v.recommendation,
          affected_entities: v.affected_entities,
          confidence: v.confidence,
          coordinates: v.coordinates ? [v.coordinates[0], v.coordinates[1]] : undefined,
          standard_reference: v.standard_reference || undefined,
          pen_type: v.pen_type,
          is_resolved: v.is_resolved,
          resolved_at: v.resolved_at,
          checker_remarks: v.checker_remarks
        })),
        complianceScore: session.compliance_score,
        auditStatus: "completed",
        selectedClient: session.client_name || null
      });

      // Jump back to workspace view
      setCurrentNav("workspace");
    } catch (err: any) {
      alert(`Ingestion Warning: ${err.message}`);
    }
  };

  const handleSaveRemarks = async () => {
    if (!selectedSessionForEdit) return;
    const success = await updateSession(selectedSessionForEdit.id, remarksText);
    if (success) {
      setIsEditModalOpen(false);
      setSelectedSessionForEdit(null);
      setRemarksText("");
      fetchSessions();
    } else {
      alert("Failed to update remarks. Standalone API may be offline.");
    }
  };

  const handleDeleteConfirm = async () => {
    if (!selectedSessionForDelete) return;
    const success = await deleteSession(selectedSessionForDelete.id);
    if (success) {
      setIsDeleteModalOpen(false);
      setSelectedSessionForDelete(null);
      fetchSessions();
    } else {
      alert("Failed to delete session. Standalone API may be offline.");
    }
  };

  const getDrawingName = (drawingId: string) => {
    const drawing = drawings.find((d) => d.id === drawingId);
    return drawing ? drawing.file_name : `Drawing #${drawingId.substring(0, 6)}`;
  };

  useEffect(() => {
    fetchClients();
  }, [fetchClients]);

  useEffect(() => {
    const handleResize = () => {
      if (containerRefOld.current) {
        setOldSize({
          width: containerRefOld.current.clientWidth || 480,
          height: containerRefOld.current.clientHeight || 400,
        });
      }
      if (containerRefNew.current) {
        setNewSize({
          width: containerRefNew.current.clientWidth || 480,
          height: containerRefNew.current.clientHeight || 400,
        });
      }
    };

    // Use ResizeObserver for instant container-driven size updates
    const observer = new ResizeObserver(() => {
      // Use requestAnimationFrame to avoid "ResizeObserver loop limit exceeded" warnings
      window.requestAnimationFrame(() => {
        handleResize();
      });
    });

    if (containerRefOld.current) {
      observer.observe(containerRefOld.current);
    }
    if (containerRefNew.current) {
      observer.observe(containerRefNew.current);
    }

    // Call initially to ensure correct dimensions are set immediately
    handleResize();

    return () => {
      observer.disconnect();
    };
  }, [oldDrawing, newDrawing, currentNav, isRightPanelCollapsed]);



  const handleAuditTrigger = async () => {
    if (!newDrawing || !selectedClient) return;
    await runAudit(selectedClient);
  };

  const exportToPDF = async () => {
    try {
      const imgDataNew = drawingCanvasRefNew.current?.exportImage(7016, 4960);
      if (!imgDataNew) {
        alert("Drawing canvas elements not found or failed to render.");
        return;
      }

      const imgDataOld = oldDrawing ? drawingCanvasRefOld.current?.exportImage(7016, 4960) : null;

      // Create PDF in standard A4 landscape format
      const pdf = new jsPDF({
        orientation: "landscape",
        unit: "mm",
        format: "a4"
      });

      let pageAdded = false;

      if (imgDataOld) {
        pdf.addImage(imgDataOld, "PNG", 0, 0, 297, 210);
        pageAdded = true;
      }

      if (imgDataNew) {
        if (pageAdded) {
          pdf.addPage("a4", "landscape");
        }
        pdf.addImage(imgDataNew, "PNG", 0, 0, 297, 210);
      }

      const filename = `${newDrawing?.file_name.replace(/\.[^/.]+$/, "") || "drawing"}_compliance_report.pdf`;

      // Request user file target path using native save dialog
      const filePath = await save({
        filters: [{
          name: "PDF Document",
          extensions: ["pdf"]
        }],
        defaultPath: filename
      });

      if (filePath) {
        const pdfBuffer = pdf.output("arraybuffer");
        const uint8Array = new Uint8Array(pdfBuffer);
        await writeFile(filePath, uint8Array);
      }
    } catch (err: any) {
      console.error("PDF generation failed:", err);
      alert(`Export Failed: ${err.message || err}`);
    }
  };

  const criticalCount = violations.filter((v) => v.severity === "critical").length;
  const highCount = violations.filter((v) => v.severity === "high").length;
  const medCount = violations.filter((v) => v.severity === "medium").length;
  const lowCount = violations.filter((v) => v.severity === "low").length;

  const parseTabularContent = (content: string) => {
    if (!content) return [];
    const lines = content.split('\n').filter((l: string) => l.trim());
    const headerLine = lines.find((l: string) => l.includes('|') && (l.includes('FIELD') || l.includes('COLUMN') || l.includes('ORIGINAL') || l.includes('ITEM')));
    const dataLines = lines.filter((l: string) => l.includes('|') && !l.match(/^-+$/) && l !== headerLine);

    return dataLines.map((line: string) => {
      const parts = line.split('|').map((p: string) => p.trim());
      let cleanedParts = [...parts];
      if (cleanedParts[0] === '') cleanedParts.shift();
      if (cleanedParts[cleanedParts.length - 1] === '') cleanedParts.pop();

      const field = cleanedParts[0] || '';
      const original = cleanedParts[1] || '';
      const kmti = cleanedParts[2] || '';
      const status = cleanedParts[3] || '';

      const statusUpper = status.toUpperCase();
      const isMatch = statusUpper.includes('MATCHED') && !statusUpper.includes('MIS');

      return { field, original, kmti, status, isMatch };
    });
  };

  return (
    <div className="workspace-container">
      {/* 1. LEFT SIDEBAR: DOCKED PHYSICAL CHECKLIST DECK (Only when currentNav === "workspace" and drawing pair is uploaded) */}
      <style>{`
        .checklist-dock::-webkit-scrollbar,
        .checklist-dock *::-webkit-scrollbar {
          display: none !important;
        }
        .checklist-dock {
          scrollbar-width: none !important;
          -ms-overflow-style: none !important;
        }
        .panel-collapse-btn.left {
          left: auto;
          right: -18px;
          border-left: none;
          border-right: 1px solid var(--border-color);
          border-radius: 0 8px 8px 0;
          box-shadow: 3px 0 8px rgba(0,0,0,0.2);
        }
        .panel-collapse-btn.left:hover {
          left: auto;
          right: -24px;
          box-shadow: 3px 0 15px rgba(0, 229, 255, 0.25);
        }
      `}</style>
      <aside
        className={`workspace-sidebar checklist-dock ${isLeftPanelCollapsed ? 'collapsed' : ''} ${isResizingLeft ? 'resizing' : ''}`}
        style={{
          width: currentNav === "workspace" && oldDrawing && newDrawing ? (isLeftPanelCollapsed ? '0px' : `${leftSidebarWidth}px`) : '0px',
          minWidth: currentNav === "workspace" && oldDrawing && newDrawing ? (isLeftPanelCollapsed ? '0px' : `${leftSidebarWidth}px`) : '0px',
          flexShrink: 0,
          display: 'flex',
          flexDirection: 'column',
          background: 'rgba(9, 9, 11, 0.7)',
          borderRight: currentNav === "workspace" && oldDrawing && newDrawing && !isLeftPanelCollapsed ? '1px solid var(--border-color)' : 'none',
          zIndex: 10,
          overflow: 'visible',
          transition: isResizingLeft ? 'none' : 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
          backdropFilter: 'blur(20px)',
          boxShadow: '4px 0 24px rgba(0, 0, 0, 0.3)'
        }}
      >
        {currentNav === "workspace" && oldDrawing && newDrawing && (
          <>
            <button
              className="panel-collapse-btn left"
              onClick={() => setIsLeftPanelCollapsed(!isLeftPanelCollapsed)}
              title={isLeftPanelCollapsed ? "Expand Drawings Comparison Results" : "Collapse Drawings Comparison Results"}
            >
              {isLeftPanelCollapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
            </button>
            <div
              className="panel-content-wrapper"
              style={{
                display: "flex",
                flexDirection: "column",
                width: "100%",
                flex: 1,
                minHeight: 0,
                padding: "16px",
                opacity: isLeftPanelCollapsed ? 0 : 1,
                pointerEvents: isLeftPanelCollapsed ? "none" : "auto",
                transition: "opacity 0.2s ease",
                overflowY: "auto",
                boxSizing: "border-box"
              }}
            >
              {/* Checklist header */}
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "16px", paddingBottom: "12px", borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                  <Sparkles size={16} style={{ color: "var(--accent-cyan)", filter: "drop-shadow(0 0 4px rgba(0,229,255,0.4))" }} />
                  <span style={{ fontSize: "0.85rem", fontWeight: 500, letterSpacing: "0.05em", color: "#e4e4e7" }}>
                    DRAWINGS COMPARISON RESULTS
                  </span>
                </div>
                {aiScanProgress === "idle" && (
                  <div style={{ display: "flex", gap: "6px", alignItems: "center" }}>
                    <button
                      className="btn btn-primary"
                      onClick={runPhysicalComparisonAI}
                      style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "0.7rem", padding: "6px 12px", borderRadius: "6px" }}
                    >
                      <Play size={12} fill="currentColor" />
                      RUN COMPARISON
                    </button>
                  </div>
                )}
              </div>

              {/* AI Scan Progress Sequence */}
              {aiScanProgress !== "idle" && aiScanProgress !== "completed" && (
                <div style={{ display: "flex", flexDirection: "column", gap: "12px", margin: "16px 0" }}>
                  <div className="loader spin-animation" style={{ alignSelf: "center", marginBottom: "8px" }}></div>
                  <div style={{ display: "flex", flexDirection: "column", gap: "6px", fontSize: "0.65rem", fontWeight: 600, color: "var(--text-muted)", background: "rgba(255,255,255,0.02)", padding: "10px", borderRadius: "6px", border: "1px solid rgba(255,255,255,0.04)" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", color: aiScanProgress === "scanning_ref" || aiScanProgress === "extracting" || aiScanProgress === "scanning_rev" || aiScanProgress === "comparing" ? "var(--accent-cyan)" : "inherit" }}>
                      <span>1. SCAN ORIGINAL</span>
                      {aiScanProgress === "scanning_ref" && <span style={{ fontSize: "0.6rem" }}>SCANNING...</span>}
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between", color: aiScanProgress === "extracting" || aiScanProgress === "scanning_rev" || aiScanProgress === "comparing" ? "var(--accent-cyan)" : "inherit" }}>
                      <span>2. EXTRACT DATA</span>
                      {aiScanProgress === "extracting" && <span style={{ fontSize: "0.6rem" }}>EXTRACTING...</span>}
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between", color: aiScanProgress === "scanning_rev" || aiScanProgress === "comparing" ? "var(--accent-cyan)" : "inherit" }}>
                      <span>3. SCAN KMTI</span>
                      {aiScanProgress === "scanning_rev" && <span style={{ fontSize: "0.6rem" }}>SCANNING...</span>}
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between", color: aiScanProgress === "comparing" ? "var(--accent-cyan)" : "inherit" }}>
                      <span>4. COMPARE MATCHES</span>
                      {aiScanProgress === "comparing" && <span style={{ fontSize: "0.6rem" }}>COMPARING...</span>}
                    </div>
                  </div>
                  <div style={{ width: "100%", height: "4px", background: "rgba(255,255,255,0.1)", borderRadius: "2px", overflow: "hidden" }}>
                    <div style={{
                      height: "100%",
                      background: "var(--accent-cyan)",
                      width: aiScanProgress === "scanning_ref" ? "25%" : aiScanProgress === "extracting" ? "50%" : aiScanProgress === "scanning_rev" ? "75%" : "100%",
                      transition: "width 0.5s ease"
                    }}></div>
                  </div>
                </div>
              )}

              {/* AI Error Banner — shown when comparison fails (e.g. 503 overload) */}
              {aiScanError && aiScanProgress === "idle" && (
                <div style={{
                  display: "flex", alignItems: "flex-start", gap: "10px",
                  background: "rgba(245, 158, 11, 0.08)",
                  border: "1px solid rgba(245, 158, 11, 0.3)",
                  borderRadius: "8px", padding: "10px 12px", margin: "8px 0",
                  animation: "fadeIn 0.25s ease"
                }}>
                  <span style={{ fontSize: "1rem", flexShrink: 0, marginTop: "1px" }}>⚠️</span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: "0.65rem", fontWeight: 700, color: "#f59e0b", letterSpacing: "0.06em", marginBottom: "4px" }}>
                      AI COMPARISON FAILED
                    </div>
                    <div style={{ fontSize: "0.65rem", color: "#a1a1aa", lineHeight: 1.5 }}>
                      {aiScanError}
                    </div>
                    <button
                      onClick={() => { setAiScanError(null); runPhysicalComparisonAI(); }}
                      style={{
                        marginTop: "8px", padding: "4px 10px", fontSize: "0.6rem", fontWeight: 700,
                        letterSpacing: "0.06em", background: "rgba(245,158,11,0.15)",
                        border: "1px solid rgba(245,158,11,0.4)", borderRadius: "4px",
                        color: "#f59e0b", cursor: "pointer"
                      }}
                    >
                      ↺ RETRY
                    </button>
                  </div>
                  <button
                    onClick={() => setAiScanError(null)}
                    style={{ background: "none", border: "none", color: "#71717a", cursor: "pointer", fontSize: "1rem", padding: "0", flexShrink: 0 }}
                    title="Dismiss"
                  >×</button>
                </div>
              )}

              {/* AI Results Deck */}
              {aiScanProgress === "completed" && (
                <div style={{ display: "flex", flexDirection: "column", gap: "12px", flexGrow: 1, paddingBottom: "24px" }}>

                  {/* 1. SUMMARY REPORT */}
                  <div style={{
                    background: "linear-gradient(135deg, rgba(30,30,40,0.5) 0%, rgba(15,15,20,0.5) 100%)",
                    border: "1px solid rgba(255,255,255,0.06)",
                    borderRadius: "8px",
                    padding: "14px",
                    boxShadow: "0 4px 20px rgba(0,0,0,0.2)",
                    backdropFilter: "blur(15px)",
                    display: "flex",
                    flexDirection: "column",
                    gap: "10px"
                  }}>
                    <div style={{ fontSize: "0.8rem", fontWeight: 600, color: "var(--accent-cyan)", letterSpacing: "0.05em", textTransform: "uppercase" }}>
                      INSPECTION SUMMARY REPORT
                    </div>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px" }}>
                      {[
                        { key: "drawing_views", label: "Drawing Views" },
                        { key: "notes_section", label: "Notes" },
                        { key: "bill_of_materials", label: "BOM" },
                        { key: "title_block", label: "Title Block" },
                        { key: "isometric_view", label: "Isometric View" }
                      ].map(({ key, label }) => {
                        const res = aiChecklistResults[key];
                        if (!res) return null;
                        let color = "#10b981"; // MATCHED
                        if (res.status === "CHANGED") color = "#f59e0b";
                        else if (res.status === "ADDED") color = "#3b82f6";
                        else if (res.status === "REMOVED" || res.status === "MISSING") color = "#ef4444";
                        return (
                          <div key={key} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", background: "rgba(255,255,255,0.02)", padding: "5px 8px", borderRadius: "5px", border: "1px solid rgba(255,255,255,0.04)" }}>
                            <span style={{ fontSize: "0.72rem", color: "#a1a1aa", fontWeight: 400 }}>{label}</span>
                            <span style={{ fontSize: "0.68rem", fontWeight: 600, color, letterSpacing: "0.02em" }}>{res.status}</span>
                          </div>
                        );
                      })}
                    </div>
                    {(() => {
                      const keys = ["drawing_views", "notes_section", "bill_of_materials", "title_block", "isometric_view"];
                      const total = keys.filter(k => aiChecklistResults[k]).length;
                      const matched = keys.filter(k => aiChecklistResults[k]?.status === "MATCHED").length;
                      const pct = total > 0 ? Math.round((matched / total) * 100) : 0;
                      return (
                        <div style={{ marginTop: "4px" }}>
                          <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.72rem", color: "#e4e4e7", marginBottom: "5px", fontWeight: 500 }}>
                            <span>Completion Parity</span>
                            <span style={{ color: "var(--accent-cyan)", fontWeight: 600 }}>{pct}% MATCHED</span>
                          </div>
                          <div style={{ width: "100%", height: "4px", background: "rgba(255,255,255,0.08)", borderRadius: "2px", overflow: "hidden" }}>
                            <div style={{ height: "100%", background: "var(--accent-cyan)", width: `${pct}%`, transition: "width 0.5s ease" }}></div>
                          </div>
                        </div>
                      );
                    })()}
                  </div>

                  {[
                    { key: "drawing_views", label: "Drawing Views" },
                    { key: "notes_section", label: "Notes Section" },
                    { key: "bill_of_materials", label: "Bill of Materials" },
                    { key: "title_block", label: "Title Block" },
                    { key: "isometric_view", label: "Isometric View" },
                    { key: "other_engineering_references", label: "Other Engineering References" }
                  ].map(({ key, label }) => {
                    const result = aiChecklistResults[key];
                    if (!result) return null;

                    const isExpanded = expandedChecklistPanels[key];

                    let badgeColor = "#10b981"; // MATCHED
                    if (result.status === "ADDED") badgeColor = "#3b82f6";
                    else if (result.status === "CHANGED") badgeColor = "#f59e0b";
                    else if (result.status === "REMOVED" || result.status === "MISSING") badgeColor = "#ef4444";

                    return (
                      <div
                        key={key}
                        style={{
                          background: "rgba(22,22,26,0.7)",
                          border: "1px solid rgba(255,255,255,0.06)",
                          borderRadius: "8px",
                          overflow: "hidden",
                          transition: "all 0.2s ease-in-out",
                          boxShadow: "0 4px 12px rgba(0,0,0,0.15)"
                        }}
                      >
                        <div
                          onClick={() => toggleChecklistPanel(key)}
                          style={{
                            display: "flex",
                            justifyContent: "space-between",
                            alignItems: "center",
                            padding: "12px 14px",
                            cursor: "pointer",
                            userSelect: "none",
                            background: isExpanded ? "rgba(255,255,255,0.02)" : "transparent",
                            borderBottom: isExpanded ? "1px solid rgba(255,255,255,0.05)" : "none",
                            transition: "background 0.2s ease"
                          }}
                        >
                          <span style={{ fontSize: "0.92rem", fontWeight: 500, color: "#ffffff", letterSpacing: "0.03em", textTransform: "uppercase" }}>
                            {label}
                          </span>
                          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                            <span style={{
                              fontSize: "0.72rem", fontWeight: 500, padding: "3px 8px", borderRadius: "5px",
                              color: badgeColor, border: `1px solid ${badgeColor}40`, background: `${badgeColor}12`,
                              letterSpacing: "0.04em"
                            }}>
                              {result.status}
                            </span>
                            {isExpanded ? <ChevronDown size={14} color="#a1a1aa" /> : <ChevronRight size={14} color="#a1a1aa" />}
                          </div>
                        </div>

                        {/* Expanded Data Panel */}
                        {isExpanded && (
                          <div style={{ padding: "14px 16px", background: "rgba(0,0,0,0.25)", display: "flex", flexDirection: "column", gap: "14px" }}>

                            {/* Difference Summary */}
                            {result.difference_summary && (
                              <div>
                                <div style={{ fontSize: "0.8rem", fontWeight: 500, color: "var(--accent-cyan)", marginBottom: "6px", letterSpacing: "0.05em" }}>DIFFERENCE SUMMARY</div>
                                <div style={{ fontSize: "0.85rem", color: "#e4e4e7", lineHeight: "1.5", fontWeight: 100 }}>{result.difference_summary}</div>
                              </div>
                            )}

                            {/* Comparative Contents Box */}
                            {(result.reference_content || result.revision_content) && (() => {
                              const isTabular = (result.reference_content && result.reference_content.includes('|')) ||
                                (result.revision_content && result.revision_content.includes('|'));

                              if (isTabular) {
                                const tableRows = parseTabularContent(result.reference_content || result.revision_content);
                                const diffRows = tableRows.filter(row => !row.isMatch);

                                return (
                                  <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                                    <div style={{ fontSize: "0.8rem", fontWeight: 650, color: "var(--accent-cyan)", marginBottom: "4px", letterSpacing: "0.05em" }}>COMPARATIVE CONTENTS</div>
                                    {diffRows.length === 0 ? (
                                      <div style={{
                                        padding: "14px",
                                        textAlign: "center",
                                        color: "#10b981",
                                        background: "rgba(16, 185, 129, 0.06)",
                                        border: "1px dashed rgba(16, 185, 129, 0.25)",
                                        borderRadius: "8px",
                                        fontSize: "0.78rem",
                                        fontWeight: 500
                                      }}>
                                        ✨ Perfect Match! All fields are identical.
                                      </div>
                                    ) : (
                                      <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                                        {diffRows.map((row, idx) => {
                                          let badgeColor = "#ef4444"; // Mismatched / Removed
                                          let badgeBg = "rgba(239, 68, 68, 0.08)";
                                          let statusText = row.status || "MISMATCHED";

                                          if (statusText.toUpperCase().includes("CHANGE")) {
                                            badgeColor = "#f59e0b"; // Changed
                                            badgeBg = "rgba(245, 158, 11, 0.08)";
                                          } else if (statusText.toUpperCase().includes("ADD")) {
                                            badgeColor = "#3b82f6"; // Added
                                            badgeBg = "rgba(59, 130, 246, 0.08)";
                                          }

                                          const matchingViolation = violations.find(v => {
                                            const desc = v.description ? v.description.trim() : "";
                                            const matchesText = desc === row.kmti || desc === row.original;
                                            const vCat = v.category ? v.category.toLowerCase().replace(/_/g, "") : "";
                                            const pKey = key.toLowerCase().replace(/_/g, "");
                                            const matchesCategory = vCat === pKey || vCat.includes(pKey) || pKey.includes(vCat);
                                            return matchesText && matchesCategory;
                                          });

                                          const isSelected = !!(selectedViolation && matchingViolation && selectedViolation.id === matchingViolation.id);

                                          return (
                                            <div
                                              key={idx}
                                              onClick={() => {
                                                if (matchingViolation) {
                                                  selectViolation(matchingViolation);
                                                  const coords = matchingViolation.coordinates || matchingViolation.ref_coordinates;
                                                  if (coords) {
                                                    const [vx, vy] = coords;
                                                    setReviewViewport({
                                                      x: 240 - vx * 1.5,
                                                      y: 200 - vy * 1.5,
                                                      scale: 1.5
                                                    });
                                                  }
                                                }
                                              }}
                                              style={{
                                                background: isSelected ? "rgba(0, 229, 255, 0.06)" : "rgba(255,255,255,0.02)",
                                                border: isSelected ? "1px solid var(--accent-cyan)" : "1px solid rgba(255,255,255,0.06)",
                                                borderRadius: "8px",
                                                padding: "10px 12px",
                                                display: "flex",
                                                flexDirection: "column",
                                                gap: "8px",
                                                boxShadow: isSelected ? "0 0 10px rgba(0, 229, 255, 0.2)" : "0 2px 8px rgba(0,0,0,0.15)",
                                                cursor: matchingViolation ? "pointer" : "default",
                                                transition: "all 0.2s ease"
                                              }}
                                            >
                                              {/* Header row: Title + Status Tag */}
                                              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "10px" }}>
                                                <div style={{ display: "flex", alignItems: "center", gap: "6px", minWidth: 0, flex: 1 }}>
                                                  <span style={{
                                                    width: "7px",
                                                    height: "7px",
                                                    borderRadius: "50%",
                                                    backgroundColor: badgeColor,
                                                    boxShadow: `0 0 6px ${badgeColor}`,
                                                    flexShrink: 0
                                                  }} />
                                                  <span style={{ fontSize: "0.78rem", fontWeight: 650, color: "#ffffff", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                                                    {row.field}
                                                  </span>
                                                </div>
                                                <span style={{
                                                  fontSize: "0.62rem",
                                                  fontWeight: 700,
                                                  padding: "2px 6px",
                                                  borderRadius: "4px",
                                                  color: badgeColor,
                                                  background: badgeBg,
                                                  border: `1px solid ${badgeColor}33`,
                                                  letterSpacing: "0.04em",
                                                  textTransform: "uppercase",
                                                  flexShrink: 0
                                                }}>
                                                  {statusText}
                                                </span>
                                              </div>

                                              {/* Content row: Unified diff arrow view */}
                                              <div style={{ display: "flex", flexDirection: "column", gap: "6px", background: "rgba(0,0,0,0.15)", padding: "8px", borderRadius: "6px" }}>
                                                <div style={{ display: "grid", gridTemplateColumns: "1fr auto 1fr", alignItems: "center", gap: "8px" }}>
                                                  {/* Original */}
                                                  <div
                                                    title={row.original}
                                                    style={{
                                                      fontSize: "0.72rem",
                                                      color: "#94a3b8",
                                                      fontFamily: "'JetBrains Mono', monospace",
                                                      textDecoration: statusText.toUpperCase().includes("CHANGE") || statusText.toUpperCase().includes("REMOVE") || statusText.toUpperCase().includes("MIS") ? "line-through" : "none",
                                                      whiteSpace: "nowrap",
                                                      overflowX: "auto",
                                                      scrollbarWidth: "none",
                                                      padding: "2px 4px",
                                                      borderRadius: "3px",
                                                      background: statusText.toUpperCase().includes("REMOVE") || statusText.toUpperCase().includes("MIS") ? "rgba(239, 68, 68, 0.05)" : "transparent"
                                                    }}
                                                  >
                                                    {row.original || "-"}
                                                  </div>

                                                  {/* Arrow */}
                                                  <span style={{ color: "rgba(255,255,255,0.25)", fontSize: "0.75rem" }}>➔</span>

                                                  {/* KMTI */}
                                                  <div
                                                    title={row.kmti}
                                                    style={{
                                                      fontSize: "0.72rem",
                                                      color: "#e2e8f0",
                                                      fontFamily: "'JetBrains Mono', monospace",
                                                      fontWeight: 500,
                                                      whiteSpace: "nowrap",
                                                      overflowX: "auto",
                                                      scrollbarWidth: "none",
                                                      padding: "2px 4px",
                                                      borderRadius: "3px",
                                                      background: statusText.toUpperCase().includes("ADD") || statusText.toUpperCase().includes("CHANGE") ? "rgba(16, 185, 129, 0.08)" : "transparent"
                                                    }}
                                                  >
                                                    {row.kmti || "-"}
                                                  </div>
                                                </div>
                                              </div>
                                            </div>
                                          );
                                        })}
                                      </div>
                                    )}
                                  </div>
                                );
                              } else {
                                return (
                                  <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                                    <div style={{ fontSize: "0.8rem", fontWeight: 650, color: "var(--accent-cyan)", marginBottom: "4px", letterSpacing: "0.05em" }}>COMPARATIVE CONTENTS</div>
                                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px" }}>
                                      <div style={{ background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.06)", padding: "10px", borderRadius: "6px", display: "flex", flexDirection: "column", minWidth: 0 }}>
                                        <div style={{ fontSize: "0.65rem", fontWeight: 700, color: "var(--text-muted)", marginBottom: "6px", textTransform: "uppercase", letterSpacing: "0.02em" }}>Original Drawing</div>
                                        <div style={{ fontSize: "0.78rem", color: "#94a3b8", whiteSpace: "pre-wrap", maxHeight: "150px", overflowY: "auto", fontFamily: "'JetBrains Mono', monospace", lineHeight: "1.4", wordBreak: "break-all" }}>
                                          {result.reference_content || "-"}
                                        </div>
                                      </div>
                                      <div style={{ background: "rgba(0,229,255,0.01)", border: "1px solid rgba(0,229,255,0.1)", padding: "10px", borderRadius: "6px", display: "flex", flexDirection: "column", minWidth: 0 }}>
                                        <div style={{ fontSize: "0.65rem", fontWeight: 700, color: "var(--accent-cyan)", marginBottom: "6px", textTransform: "uppercase", letterSpacing: "0.02em" }}>KMTI Drawing</div>
                                        <div style={{ fontSize: "0.78rem", color: "#e2e8f0", whiteSpace: "pre-wrap", maxHeight: "150px", overflowY: "auto", fontFamily: "'JetBrains Mono', monospace", lineHeight: "1.4", wordBreak: "break-all" }}>
                                          {result.revision_content || "-"}
                                        </div>
                                      </div>
                                    </div>
                                  </div>
                                );
                              }
                            })()}

                            {/* Engineering Discrepancy Details */}
                            {result.engineering_discrepancy_details && (
                              <div>
                                <div style={{ fontSize: "0.8rem", fontWeight: 600, color: "var(--accent-cyan)", marginBottom: "6px", letterSpacing: "0.05em" }}>ENGINEERING DISCREPANCY DETAILS</div>
                                <div style={{
                                  fontSize: "0.85rem",
                                  color: result.status === "MATCHED" ? "#a7f3d0" : "#fecaca",
                                  background: result.status === "MATCHED" ? "rgba(16,185,129,0.06)" : "rgba(239,68,68,0.06)",
                                  borderLeft: `4px solid ${badgeColor}`,
                                  padding: "8px 12px",
                                  borderRadius: "0 6px 6px 0",
                                  lineHeight: "1.5",
                                  fontWeight: 400
                                }}>
                                  {result.engineering_discrepancy_details}
                                </div>
                              </div>
                            )}

                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </>
        )}
      </aside>

      {currentNav === "workspace" && oldDrawing && newDrawing && (
        <div
          className={`left-resize-divider ${isResizingLeft ? 'active' : ''}`}
          onMouseDown={(e) => {
            e.preventDefault();
            setIsResizingLeft(true);
          }}
          style={{
            width: '6px',
            cursor: 'ew-resize',
            background: isResizingLeft ? 'rgba(0, 229, 255, 0.4)' : 'rgba(255, 255, 255, 0.05)',
            borderLeft: '1px solid rgba(255, 255, 255, 0.05)',
            borderRight: '1px solid rgba(255, 255, 255, 0.05)',
            zIndex: 30,
            transition: 'background 0.2s ease',
            flexShrink: 0
          }}
        />
      )}

      {/* 2. DYNAMIC WORKSPACE PORT */}
      {/* Standards Manuals — admin-only panel */}
      {currentNav === "standards" && isAdmin && (
        <div className="viewport-standards-manager">
          <StandardsManager />
        </div>
      )}

      {currentNav === "history" && (() => {
        const completedSessionsCount = sessions ? sessions.filter(s => s.status === "completed" && s.compliance_score !== null).length : 0;
        const avgCompliance = completedSessionsCount > 0
          ? (sessions.filter(s => s.status === "completed" && s.compliance_score !== null).reduce((sum, s) => sum + s.compliance_score!, 0) / completedSessionsCount).toFixed(1) + "%"
          : "N/A";

        const completedCount = sessions ? sessions.filter(s => s.status === "completed").length : 0;
        const failedCount = sessions ? sessions.filter(s => s.status === "failed").length : 0;
        const successRate = (completedCount + failedCount) > 0
          ? ((completedCount / (completedCount + failedCount)) * 100).toFixed(0) + "%"
          : "100%";

        const filteredSessions = (sessions || []).filter((session) => {
          const refName = session.reference_drawing_id ? getDrawingName(session.reference_drawing_id) : "";
          const newName = getDrawingName(session.drawing_id);
          const client = session.client_name || "";
          const remarks = session.remarks || "";
          const matchesSearch =
            refName.toLowerCase().includes(historySearchQuery.toLowerCase()) ||
            newName.toLowerCase().includes(historySearchQuery.toLowerCase()) ||
            client.toLowerCase().includes(historySearchQuery.toLowerCase()) ||
            remarks.toLowerCase().includes(historySearchQuery.toLowerCase());

          const matchesStatus =
            historyStatusFilter === "all" ||
            (historyStatusFilter === "completed" && session.status === "completed") ||
            (historyStatusFilter === "failed" && session.status === "failed") ||
            (historyStatusFilter === "auditing" && session.status !== "completed" && session.status !== "failed");

          const matchesScore =
            historyScoreFilter === "all" ||
            (historyScoreFilter === "excellent" && session.status === "completed" && session.compliance_score !== null && session.compliance_score >= 85) ||
            (historyScoreFilter === "warning" && session.status === "completed" && session.compliance_score !== null && session.compliance_score < 85);

          return matchesSearch && matchesStatus && matchesScore;
        });

        return (
          <main className="workspace-main-viewport padded" style={{ display: "flex", flexDirection: "column", gap: "24px" }}>
            <div className="subpage-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", flexWrap: "wrap", gap: "16px" }}>
              <div>
                <h2 className="section-title">Audit History Archive</h2>
                <p className="section-desc">View historically logged revision comparison sessions and compliance reports.</p>
              </div>
              {sessions && sessions.length > 0 && (
                <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", background: "rgba(255,255,255,0.03)", padding: "4px 10px", borderRadius: "12px", border: "1px solid rgba(255,255,255,0.05)" }}>
                  Total sessions loaded: <strong style={{ color: "var(--text-primary)" }}>{sessions.length}</strong>
                </span>
              )}
            </div>

            {/* DYNAMIC STATISTICS SUMMARY DECK */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "16px" }}>
              {/* Card 1: Total Runs */}
              <div className="card" style={{ display: "flex", alignItems: "center", gap: "16px", padding: "16px 20px", background: "linear-gradient(135deg, rgba(255, 255, 255, 0.02) 0%, rgba(255, 255, 255, 0.005) 100%)", border: "1px solid rgba(255, 255, 255, 0.05)", borderRadius: "12px" }}>
                <div style={{ width: "42px", height: "42px", borderRadius: "10px", background: "rgba(59, 130, 246, 0.08)", border: "1px solid rgba(59, 130, 246, 0.15)", display: "flex", alignItems: "center", justifyContent: "center", color: "var(--accent-cyan)", boxShadow: "0 0 12px rgba(59, 130, 246, 0.05)" }}>
                  <Database size={18} />
                </div>
                <div>
                  <span style={{ fontSize: "0.72rem", textTransform: "uppercase", letterSpacing: "0.8px", color: "var(--text-muted)", fontWeight: "600" }}>Total Audit Runs</span>
                  <h3 style={{ fontSize: "1.4rem", fontWeight: "700", marginTop: "2px", color: "var(--text-primary)", fontFamily: "'JetBrains Mono', monospace" }}>
                    {sessions ? sessions.length : 0}
                  </h3>
                </div>
              </div>

              {/* Card 2: Average Compliance */}
              <div className="card" style={{ display: "flex", alignItems: "center", gap: "16px", padding: "16px 20px", background: "linear-gradient(135deg, rgba(255, 255, 255, 0.02) 0%, rgba(255, 255, 255, 0.005) 100%)", border: "1px solid rgba(255, 255, 255, 0.05)", borderRadius: "12px" }}>
                <div style={{ width: "42px", height: "42px", borderRadius: "10px", background: "rgba(16, 185, 129, 0.08)", border: "1px solid rgba(16, 185, 129, 0.15)", display: "flex", alignItems: "center", justifyContent: "center", color: "#10b981", boxShadow: "0 0 12px rgba(16, 185, 129, 0.05)" }}>
                  <BarChart2 size={18} />
                </div>
                <div>
                  <span style={{ fontSize: "0.72rem", textTransform: "uppercase", letterSpacing: "0.8px", color: "var(--text-muted)", fontWeight: "600" }}>Avg Compliance</span>
                  <h3 style={{ fontSize: "1.4rem", fontWeight: "700", marginTop: "2px", color: "#10b981", fontFamily: "'JetBrains Mono', monospace" }}>
                    {avgCompliance}
                  </h3>
                </div>
              </div>

              {/* Card 3: Success Rate */}
              <div className="card" style={{ display: "flex", alignItems: "center", gap: "16px", padding: "16px 20px", background: "linear-gradient(135deg, rgba(255, 255, 255, 0.02) 0%, rgba(255, 255, 255, 0.005) 100%)", border: "1px solid rgba(255, 255, 255, 0.05)", borderRadius: "12px" }}>
                <div style={{ width: "42px", height: "42px", borderRadius: "10px", background: "rgba(168, 85, 247, 0.08)", border: "1px solid rgba(168, 85, 247, 0.15)", display: "flex", alignItems: "center", justifyContent: "center", color: "#a855f7", boxShadow: "0 0 12px rgba(168, 85, 247, 0.05)" }}>
                  <TrendingUp size={18} />
                </div>
                <div>
                  <span style={{ fontSize: "0.72rem", textTransform: "uppercase", letterSpacing: "0.8px", color: "var(--text-muted)", fontWeight: "600" }}>Pipeline Success</span>
                  <h3 style={{ fontSize: "1.4rem", fontWeight: "700", marginTop: "2px", color: "#a855f7", fontFamily: "'JetBrains Mono', monospace" }}>
                    {successRate}
                  </h3>
                </div>
              </div>
            </div>

            {/* INTERACTIVE CONTROLS BAR: SEARCH & MULTI-CRITERIA FILTERS */}
            <div className="card" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: "16px", padding: "14px 20px", background: "rgba(255, 255, 255, 0.01)", border: "1px solid rgba(255, 255, 255, 0.04)", borderRadius: "12px" }}>
              <div style={{ display: "flex", flex: 1, gap: "12px", alignItems: "center", minWidth: "290px" }}>
                <div style={{ position: "relative", flex: 1 }}>
                  <Search size={16} style={{ position: "absolute", left: "12px", top: "50%", transform: "translateY(-50%)", color: "var(--text-muted)" }} />
                  <input
                    type="text"
                    placeholder="Search drawing name, remarks, or client context..."
                    value={historySearchQuery}
                    onChange={(e) => setHistorySearchQuery(e.target.value)}
                    className="form-input"
                    style={{ paddingLeft: "36px", height: "38px", background: "rgba(0, 0, 0, 0.25)", border: "1px solid rgba(255, 255, 255, 0.08)", borderRadius: "8px", fontSize: "0.85rem", width: "100%", transition: "all 0.2s ease" }}
                  />
                </div>
              </div>

              <div style={{ display: "flex", gap: "16px", alignItems: "center", flexWrap: "wrap" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                  <Filter size={13} style={{ color: "var(--text-muted)" }} />
                  <span style={{ fontSize: "0.8rem", color: "var(--text-muted)", fontWeight: "500" }}>Status:</span>
                  <select
                    value={historyStatusFilter}
                    onChange={(e) => setHistoryStatusFilter(e.target.value as any)}
                    className="form-input"
                    style={{ height: "38px", padding: "0 10px", background: "rgba(0,0,0,0.25)", border: "1px solid rgba(255, 255, 255, 0.08)", borderRadius: "8px", fontSize: "0.85rem", color: "var(--text-primary)", width: "140px", cursor: "pointer", outline: "none" }}
                  >
                    <option value="all">All Statuses</option>
                    <option value="completed">Completed</option>
                    <option value="failed">Failed</option>
                    <option value="auditing">Active Auditing</option>
                  </select>
                </div>

                <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                  <span style={{ fontSize: "0.8rem", color: "var(--text-muted)", fontWeight: "500" }}>Compliance:</span>
                  <select
                    value={historyScoreFilter}
                    onChange={(e) => setHistoryScoreFilter(e.target.value as any)}
                    className="form-input"
                    style={{ height: "38px", padding: "0 10px", background: "rgba(0,0,0,0.25)", border: "1px solid rgba(255, 255, 255, 0.08)", borderRadius: "8px", fontSize: "0.85rem", color: "var(--text-primary)", width: "155px", cursor: "pointer", outline: "none" }}
                  >
                    <option value="all">All Scores</option>
                    <option value="excellent">Excellent (≥ 85%)</option>
                    <option value="warning">Warning (&lt; 85%)</option>
                  </select>
                </div>
              </div>
            </div>

            {/* ARCHIVE GRID / RESULTS TABLE */}
            {filteredSessions.length > 0 ? (
              <div className="card settings-card" style={{ padding: "0px", overflow: "hidden", border: "1px solid rgba(255, 255, 255, 0.06)", borderRadius: "12px", background: "var(--bg-card)" }}>
                <table className="stats-table" style={{ width: "100%", borderCollapse: "collapse" }}>
                  <thead>
                    <tr className="stats-row" style={{ background: "rgba(255, 255, 255, 0.015)", borderBottom: "1px solid rgba(255, 255, 255, 0.06)" }}>
                      <th style={{ color: "var(--text-muted)", fontSize: "0.78rem", fontWeight: "600", textTransform: "uppercase", letterSpacing: "0.5px", textAlign: "left", padding: "14px 16px", verticalAlign: "middle", width: "90px" }}>ID</th>
                      <th style={{ color: "var(--text-muted)", fontSize: "0.78rem", fontWeight: "600", textTransform: "uppercase", letterSpacing: "0.5px", textAlign: "left", padding: "14px 16px", verticalAlign: "middle" }}>Original Drawing</th>
                      <th style={{ color: "var(--text-muted)", fontSize: "0.78rem", fontWeight: "600", textTransform: "uppercase", letterSpacing: "0.5px", textAlign: "left", padding: "14px 16px", verticalAlign: "middle" }}>KMTI Drawing</th>
                      <th style={{ color: "var(--text-muted)", fontSize: "0.78rem", fontWeight: "600", textTransform: "uppercase", letterSpacing: "0.5px", textAlign: "left", padding: "14px 16px", verticalAlign: "middle" }}>Client</th>
                      <th style={{ color: "var(--text-muted)", fontSize: "0.78rem", fontWeight: "600", textTransform: "uppercase", letterSpacing: "0.5px", textAlign: "left", padding: "14px 16px", verticalAlign: "middle" }}>Compliance Score</th>
                      <th style={{ color: "var(--text-muted)", fontSize: "0.78rem", fontWeight: "600", textTransform: "uppercase", letterSpacing: "0.5px", textAlign: "left", padding: "14px 16px", verticalAlign: "middle" }}>Session Date</th>
                      <th style={{ color: "var(--text-muted)", fontSize: "0.78rem", fontWeight: "600", textTransform: "uppercase", letterSpacing: "0.5px", textAlign: "left", padding: "14px 16px", verticalAlign: "middle" }}>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredSessions.map((session) => {
                      const isCompleted = session.status === "completed";
                      const isFailed = session.status === "failed";
                      const score = session.compliance_score;
                      let scoreColor = "var(--text-muted)";
                      let scoreBg = "rgba(255, 255, 255, 0.03)";
                      let scoreBorder = "rgba(255, 255, 255, 0.05)";
                      if (isCompleted && score !== null) {
                        if (score >= 85) {
                          scoreColor = "#10b981";
                          scoreBg = "rgba(16, 185, 129, 0.08)";
                          scoreBorder = "rgba(16, 185, 129, 0.15)";
                        } else if (score >= 70) {
                          scoreColor = "#f59e0b";
                          scoreBg = "rgba(245, 158, 11, 0.08)";
                          scoreBorder = "rgba(245, 158, 11, 0.15)";
                        } else {
                          scoreColor = "#ef4444";
                          scoreBg = "rgba(239, 68, 68, 0.08)";
                          scoreBorder = "rgba(239, 68, 68, 0.15)";
                        }
                      }

                      return (
                        <tr
                          key={session.id}
                          className="stats-row"
                          style={{
                            borderBottom: "1px solid rgba(255, 255, 255, 0.04)",
                            transition: "background-color 0.2s ease"
                          }}
                          onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = "rgba(255, 255, 255, 0.01)"; }}
                          onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = "transparent"; }}
                        >
                          {/* ID Column */}
                          <td className="stats-label" style={{ textAlign: "left", padding: "14px 12px", verticalAlign: "left" }}>
                            <span style={{ fontSize: "0.8rem", fontWeight: 500, color: "var(--accent-cyan)", background: "rgba(0, 229, 255, 0.05)", padding: "3px 5px", borderRadius: "6px", border: "1px solid rgba(0, 229, 255, 0.15)", letterSpacing: "0.05em", fontFamily: "'JetBrains Mono', monospace" }}>
                              {(() => {
                                const prefix = "SYS";
                                const absoluteIndex = sessions.findIndex(s => s.id === session.id);
                                const numStr = String(sessions.length - absoluteIndex).padStart(2, "0");
                                return `${prefix}${numStr}`;
                              })()}
                            </span>
                          </td>

                          {/* Reference File */}
                          <td className="stats-label" style={{ textAlign: "left", padding: "14px 16px", verticalAlign: "middle" }}>
                            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                              <FileText size={14} style={{ color: session.reference_drawing_id ? "var(--text-muted)" : "rgba(255,255,255,0.15)" }} />
                              <span style={{ color: session.reference_drawing_id ? "var(--text-primary)" : "var(--text-muted)", fontSize: "0.85rem" }}>
                                {session.reference_drawing_id ? getDrawingName(session.reference_drawing_id) : "—"}
                              </span>
                            </div>
                          </td>

                          {/* New File */}
                          <td className="stats-label" style={{ textAlign: "left", padding: "14px 16px", verticalAlign: "middle", fontWeight: "600" }}>
                            <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                                <FileText size={14} style={{ color: "var(--accent-cyan)" }} />
                                <span style={{ color: "var(--text-primary)", fontSize: "0.85rem" }}>
                                  {getDrawingName(session.drawing_id)}
                                </span>
                              </div>
                              {session.remarks && (
                                <span style={{ fontSize: "0.72rem", color: "var(--accent-cyan)", display: "inline-flex", alignItems: "center", gap: "4px", background: "rgba(0, 229, 255, 0.05)", border: "1px solid rgba(0, 229, 255, 0.1)", padding: "2px 8px", borderRadius: "4px", width: "fit-content", fontWeight: "normal" }}>
                                  <span style={{ width: "4px", height: "4px", borderRadius: "50%", background: "var(--accent-cyan)", display: "inline-block" }}></span>
                                  {session.remarks}
                                </span>
                              )}
                            </div>
                          </td>

                          {/* Client Context */}
                          <td className="stats-value" style={{ padding: "14px 16px", color: "var(--text-primary)", verticalAlign: "middle", textAlign: "left", fontFamily: "inherit" }}>
                            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                              <Briefcase size={14} style={{ color: "var(--text-muted)", opacity: 0.6 }} />
                              <span style={{ fontSize: "0.85rem", color: session.client_name ? "var(--text-primary)" : "var(--text-muted)" }}>
                                {session.client_name || "Universal Standard"}
                              </span>
                            </div>
                          </td>

                          {/* Compliance Score */}
                          <td className="stats-value" style={{ textAlign: "left", padding: "14px 55px", verticalAlign: "middle", fontFamily: "inherit" }}>
                            {isCompleted ? (
                              <span style={{ display: "inline-flex", alignItems: "center", padding: "3px 8px", borderRadius: "6px", background: scoreBg, border: `1px solid ${scoreBorder}`, color: scoreColor, fontWeight: "800", fontSize: "0.82rem" }}>
                                {score !== null ? `${score.toFixed(1)}%` : "N/A"}
                              </span>
                            ) : isFailed ? (
                              <span style={{ background: "rgba(239, 68, 68, 0.08)", border: "1px solid rgba(239, 68, 68, 0.15)", color: "#ef4444", fontSize: "0.75rem", display: "inline-flex", alignItems: "center", gap: "6px", padding: "3px 8px", borderRadius: "6px" }} title={session.error_message || "Audit pipeline failed"}>
                                <AlertTriangle size={12} /> Failed
                              </span>
                            ) : (
                              <span style={{ background: "rgba(0, 229, 255, 0.05)", border: "1px solid rgba(0, 229, 255, 0.12)", color: "var(--accent-cyan)", fontSize: "0.75rem", display: "inline-flex", alignItems: "center", gap: "6px", padding: "3px 8px", borderRadius: "6px" }}>
                                <Loader size={12} className="spin-animation" /> Auditing...
                              </span>
                            )}
                          </td>

                          {/* Session Date */}
                          <td className="stats-value" style={{ textAlign: "left", padding: "14px 16px", color: "var(--text-muted)", fontSize: "0.82rem", verticalAlign: "middle", fontFamily: "'JetBrains Mono', monospace" }}>
                            <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                              <Clock size={12} style={{ opacity: 0.6 }} />
                              <span>
                                {parseUtcDate(session.created_at).toLocaleString(undefined, {
                                  month: "short",
                                  day: "numeric",
                                  hour: "2-digit",
                                  minute: "2-digit"
                                })}
                              </span>
                            </div>
                          </td>

                          {/* Actions */}
                          <td className="stats-value" style={{ textAlign: "left", padding: "14px 16px", verticalAlign: "middle" }}>
                            <div style={{ display: "flex", justifyContent: "flex-start", gap: "8px" }}>
                              <button
                                onClick={() => handleOpenSession(session)}
                                disabled={session.status !== "completed"}
                                title="Open visual canvas review"
                                className="action-icon-btn"
                                style={{
                                  background: "rgba(128, 128, 128, 0.08)",
                                  border: "1px solid rgba(255, 255, 255, 0.05)",
                                  color: session.status === "completed" ? "var(--accent-cyan)" : "var(--text-muted)",
                                  padding: "7px",
                                  borderRadius: "6px",
                                  cursor: session.status === "completed" ? "pointer" : "not-allowed",
                                  display: "flex",
                                  alignItems: "center",
                                  justifyContent: "center",
                                  transition: "all 0.2s cubic-bezier(0.4, 0, 0.2, 1)"
                                }}
                                onMouseEnter={(e) => {
                                  if (session.status === "completed") {
                                    e.currentTarget.style.background = "rgba(0, 229, 255, 0.15)";
                                    e.currentTarget.style.borderColor = "var(--accent-cyan)";
                                    e.currentTarget.style.color = "var(--bg-dark)";
                                    e.currentTarget.style.transform = "scale(1.05)";
                                  }
                                }}
                                onMouseLeave={(e) => {
                                  if (session.status === "completed") {
                                    e.currentTarget.style.background = "rgba(128, 128, 128, 0.08)";
                                    e.currentTarget.style.borderColor = "rgba(255, 255, 255, 0.05)";
                                    e.currentTarget.style.color = "var(--accent-cyan)";
                                    e.currentTarget.style.transform = "scale(1)";
                                  }
                                }}
                              >
                                <FolderOpen size={14} />
                              </button>
                              <button
                                onClick={() => {
                                  setSelectedSessionForEdit(session);
                                  setRemarksText(session.remarks || "");
                                  setIsEditModalOpen(true);
                                }}
                                title="Edit custom remarks"
                                className="action-icon-btn"
                                style={{
                                  background: "rgba(128, 128, 128, 0.08)",
                                  border: "1px solid rgba(255, 255, 255, 0.05)",
                                  color: "var(--text-primary)",
                                  padding: "7px",
                                  borderRadius: "6px",
                                  cursor: "pointer",
                                  display: "flex",
                                  alignItems: "center",
                                  justifyContent: "center",
                                  transition: "all 0.2s cubic-bezier(0.4, 0, 0.2, 1)"
                                }}
                                onMouseEnter={(e) => {
                                  e.currentTarget.style.background = "rgba(245, 158, 11, 0.15)";
                                  e.currentTarget.style.borderColor = "#f59e0b";
                                  e.currentTarget.style.color = "var(--bg-dark)";
                                  e.currentTarget.style.transform = "scale(1.05)";
                                }}
                                onMouseLeave={(e) => {
                                  e.currentTarget.style.background = "rgba(128, 128, 128, 0.08)";
                                  e.currentTarget.style.borderColor = "rgba(255, 255, 255, 0.05)";
                                  e.currentTarget.style.color = "var(--text-primary)";
                                  e.currentTarget.style.transform = "scale(1)";
                                }}
                              >
                                <Edit size={14} />
                              </button>
                              <button
                                onClick={() => {
                                  setSelectedSessionForDelete(session);
                                  setIsDeleteModalOpen(true);
                                }}
                                title="Purge session record"
                                className="action-icon-btn destructive"
                                style={{
                                  background: "rgba(239, 68, 68, 0.05)",
                                  border: "1px solid rgba(239, 68, 68, 0.1)",
                                  color: "#ef4444",
                                  padding: "7px",
                                  borderRadius: "6px",
                                  cursor: "pointer",
                                  display: "flex",
                                  alignItems: "center",
                                  justifyContent: "center",
                                  transition: "all 0.2s cubic-bezier(0.4, 0, 0.2, 1)"
                                }}
                                onMouseEnter={(e) => {
                                  e.currentTarget.style.background = "rgba(239, 68, 68, 0.2)";
                                  e.currentTarget.style.borderColor = "#ef4444";
                                  e.currentTarget.style.transform = "scale(1.05)";
                                }}
                                onMouseLeave={(e) => {
                                  e.currentTarget.style.background = "rgba(239, 68, 68, 0.05)";
                                  e.currentTarget.style.borderColor = "rgba(239, 68, 68, 0.1)";
                                  e.currentTarget.style.transform = "scale(1)";
                                }}
                              >
                                <Trash2 size={14} />
                              </button>
                              {session.is_restored && (
                                <span style={{ fontSize: "0.65rem", fontWeight: 700, padding: "4px 8px", borderRadius: "6px", background: "rgba(16, 185, 129, 0.1)", color: "#10b981", border: "1px solid rgba(16, 185, 129, 0.25)", textTransform: "uppercase", letterSpacing: "0.05em", display: "flex", alignItems: "center", marginLeft: "4px", boxShadow: "0 2px 4px rgba(16, 185, 129, 0.1)" }}>
                                  Restored
                                </span>
                              )}
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              /* GLASSMORPHIC EMPTY STATE FALLBACK */
              <div className="card" style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "48px 24px", textAlign: "center", background: "rgba(255, 255, 255, 0.015)", border: "1px dashed rgba(255, 255, 255, 0.08)", borderRadius: "12px", marginTop: "12px", boxShadow: "inset 0 1px 3px rgba(255,255,255,0.02)" }}>
                <div style={{ width: "56px", height: "56px", borderRadius: "50%", background: "rgba(128, 128, 128, 0.08)", border: "1px solid rgba(255, 255, 255, 0.05)", display: "flex", alignItems: "center", justifyContent: "center", color: "var(--text-muted)", marginBottom: "18px" }}>
                  <Database size={24} />
                </div>
                <h4 style={{ fontWeight: "700", color: "var(--text-primary)", fontSize: "1.1rem", marginBottom: "8px" }}>No matching archives found</h4>
                <p style={{ color: "var(--text-muted)", fontSize: "0.85rem", maxWidth: "420px", marginBottom: "22px", lineHeight: "1.6" }}>
                  {sessions && sessions.length > 0
                    ? "No historical runs match your current query or filter selectors. Reset filters to view all sessions."
                    : "No CAD compliance runs have been archived yet. Go to the review workspace to launch your first compliance check!"}
                </p>
                {sessions && sessions.length > 0 ? (
                  <button
                    className="btn btn-secondary"
                    onClick={() => {
                      setHistorySearchQuery("");
                      setHistoryStatusFilter("all");
                      setHistoryScoreFilter("all");
                    }}
                    style={{ padding: "8px 24px", borderRadius: "8px", fontSize: "0.85rem", cursor: "pointer" }}
                  >
                    Clear all filters
                  </button>
                ) : (
                  <button
                    className="btn btn-primary"
                    onClick={() => setCurrentNav("workspace")}
                    style={{ padding: "10px 24px", borderRadius: "8px", fontSize: "0.85rem", cursor: "pointer", display: "inline-flex", gap: "8px", alignItems: "center" }}
                  >
                    <Play size={12} /> Launch Compliance Check
                  </button>
                )}
              </div>
            )}
          </main>
        );
      })()}

      {currentNav === "settings" && (
        <main className="workspace-main-viewport padded">
          <div className="subpage-header">
            <h2 className="section-title">Compliance Settings</h2>
            <p className="section-desc">Tune tolerances, geometrical checks, and AI reasoner boundaries.</p>
          </div>
          <div className="card settings-card" style={{ marginTop: "24px" }}>
            <h3 className="card-title">Geometrical Tolerances</h3>
            <div style={{ display: "flex", flexDirection: "column", gap: "16px", marginTop: "20px" }}>
              <div className="form-group">
                <label className="form-label">Coincidence Tolerance (mm)</label>
                <input type="number" className="form-input" defaultValue="0.05" />
              </div>
              <div className="form-group">
                <label className="form-label">Coplanar Angle Tolerance (degrees)</label>
                <input type="number" className="form-input" defaultValue="0.1" />
              </div>
            </div>
          </div>
        </main>
      )}

      {currentNav === "workspace" && (
        <div className="dual-stage-layout">
          {/* CENTER VIEWPORT (STAGE 1: COPY-TRACE COMPARISON ENGINE) */}
          <main className="stage1-center-panel">
            {/* Top Drawing Selection and Upload Box */}


            <div className="cad-viewer-container">
              {/* Toolbar */}
              <div className="viewer-toolbar" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", width: "100%", padding: "8px 16px" }}>
                {/* LEFT: Card Title */}
                <div style={{ display: "flex", alignItems: "center" }}>
                  <h3 className="card-title" style={{ margin: 0, fontSize: "0.85rem", color: "var(--accent-cyan)", borderLeft: "3px solid var(--accent-cyan)", paddingLeft: "8px" }}>
                    Stage 1: Drawing Pair Ingestion
                  </h3>
                </div>

                {/* RIGHT: Compatibility Badge & Zoom Controls side-by-side */}
                <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
                  <div className={`compatibility-badge-status ${compatibilityStatus.toLowerCase()}`} style={{ padding: "3px 8px", fontSize: "0.62rem" }}>
                    <span className="compatibility-indicator-dot"></span>
                    <span className="compatibility-text">
                      {compatibilityStatus === "Idle" && "Awaiting Pair Ingestion"}
                      {compatibilityStatus === "Compatible" && `COMPATIBLE: ${oldDrawing?.file_name.split(".").pop()?.toUpperCase()} ↔ ${newDrawing?.file_name.split(".").pop()?.toUpperCase()}`}
                      {compatibilityStatus === "Mismatch" && "FORMAT MISMATCH"}
                      {compatibilityStatus === "Unsupported" && "UNSUPPORTED EXTENSION"}
                    </span>
                  </div>

                  <div className="toolbar-group">
                    <button
                      className="toolbar-btn"
                      onClick={() => setReviewViewport({ ...reviewViewport, scale: Math.min(25, reviewViewport.scale * 1.25) })}
                      title="Zoom In"
                    >
                      <ZoomIn size={14} />
                    </button>
                    <button
                      className="toolbar-btn"
                      onClick={() => setReviewViewport({ ...reviewViewport, scale: Math.max(0.1, reviewViewport.scale / 1.25) })}
                      title="Zoom Out"
                    >
                      <ZoomOut size={14} />
                    </button>
                    <button
                      className="toolbar-btn"
                      onClick={() => setReviewViewport({ x: 0, y: 0, scale: 1 })}
                      title="Reset Viewport"
                    >
                      <Maximize size={14} />
                    </button>
                  </div>
                </div>
              </div>


              {/* Viewport Panels */}
              {/* ── STANDARD SPLIT-VIEW MODE ── */}
              <div className="split-viewports">
                {/* Left Viewport (Old) */}
                <div className="viewport-panel">
                  <div className="viewport-header">
                    <div className="viewport-label">Original Drawing</div>
                    {oldDrawing && (
                      <div className="ingested-file-pill ref">
                        <span className="pill-filename" title={oldDrawing.file_name}>
                          {oldDrawing.file_name}
                        </span>
                        <button className="pill-clear-btn" onClick={() => clearUpload("old")} title="Remove reference drawing">
                          <Trash2 size={10} />
                        </button>
                      </div>
                    )}
                  </div>
                  <div className="cad-canvas-mock" ref={containerRefOld}>
                    {oldDrawing ? (
                      <div style={{ position: "absolute", top: 0, left: 0, width: "100%", height: "100%", overflow: "hidden" }}>
                        <DrawingCanvas
                          ref={drawingCanvasRefOld}
                          layers={oldLayers}
                          width={oldSize.width}
                          height={oldSize.height}
                          drawing={oldDrawing}
                        />
                      </div>
                    ) : (
                      <UploadZone
                        side="old"
                        uploadState={oldUploadState}
                        progress={oldUploadProgress}
                        fileName={oldFileName}
                        fileSize={oldFileSize}
                        error={oldError}
                        activeDrawing={oldDrawing}
                        uploadDrawingFile={uploadDrawingFile}
                        clearUpload={clearUpload}
                      />
                    )}
                  </div>
                </div>

                {/* Right Viewport (New) */}
                <div className="viewport-panel">
                  <div className="viewport-header">
                    <div className="viewport-label">KMTI Drawing</div>
                    {newDrawing && (
                      <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                        <div className="ingested-file-pill rev">
                          <span className="pill-filename" title={newDrawing.file_name}>
                            {newDrawing.file_name}
                          </span>
                          <button className="pill-clear-btn" onClick={() => clearUpload("new")} title="Remove revision drawing">
                            <Trash2 size={10} />
                          </button>
                        </div>
                        <button
                          className="btn btn-primary"
                          onClick={exportToPDF}
                          title="Export drawing pair as PDF"
                          style={{
                            display: "flex",
                            alignItems: "center",
                            gap: "6px",
                            fontSize: "0.68rem",
                            padding: "3px 10px",
                            borderRadius: "6px",
                            background: "rgba(0, 229, 255, 0.1)",
                            border: "1px solid rgba(0, 229, 255, 0.3)",
                            color: "var(--accent-cyan)",
                            cursor: "pointer",
                            transition: "all 0.2s ease"
                          }}
                          onMouseEnter={(e) => {
                            e.currentTarget.style.background = "var(--accent-cyan)";
                            e.currentTarget.style.color = "#09090b";
                          }}
                          onMouseLeave={(e) => {
                            e.currentTarget.style.background = "rgba(0, 229, 255, 0.1)";
                            e.currentTarget.style.color = "var(--accent-cyan)";
                          }}
                        >
                          <Download size={10} />
                          <span>PDF</span>
                        </button>
                      </div>
                    )}
                  </div>
                  <div className="cad-canvas-mock" ref={containerRefNew}>
                    {newDrawing ? (
                      <div style={{ position: "absolute", top: 0, left: 0, width: "100%", height: "100%", overflow: "hidden" }}>
                        <DrawingCanvas
                          ref={drawingCanvasRefNew}
                          layers={newLayers}
                          width={newSize.width}
                          height={newSize.height}
                          drawing={newDrawing}
                        />
                      </div>
                    ) : (
                      <UploadZone
                        side="new"
                        uploadState={newUploadState}
                        progress={newUploadProgress}
                        fileName={newFileName}
                        fileSize={newFileSize}
                        error={newError}
                        activeDrawing={newDrawing}
                        uploadDrawingFile={uploadDrawingFile}
                        clearUpload={clearUpload}
                      />
                    )}
                  </div>
                </div>
              </div>
            </div>
          </main>

          {/* Right divider */}
          {!isRightPanelCollapsed && (
            <div
              className={`right-resize-divider ${isResizingRight ? 'active' : ''}`}
              onMouseDown={(e) => {
                e.preventDefault();
                setIsResizingRight(true);
              }}
              style={{
                width: '6px',
                cursor: 'ew-resize',
                background: isResizingRight ? 'rgba(0, 229, 255, 0.4)' : 'rgba(255, 255, 255, 0.05)',
                borderLeft: '1px solid rgba(255, 255, 255, 0.05)',
                borderRight: '1px solid rgba(255, 255, 255, 0.05)',
                zIndex: 30,
                transition: 'background 0.2s ease',
                flexShrink: 0
              }}
            />
          )}

          {/* RIGHT VIEWPORT (STAGE 2: AI COMPLIANCE AUDITOR) */}
          <aside
            className={`stage2-right-panel ${isRightPanelCollapsed ? "collapsed" : ""} ${isResizingRight ? "resizing" : ""}`}
            style={{
              width: isRightPanelCollapsed ? '0px' : `${rightSidebarWidth}px`,
              minWidth: isRightPanelCollapsed ? '0px' : `${rightSidebarWidth}px`,
              transition: isResizingRight ? 'none' : 'width 0.3s cubic-bezier(0.4, 0, 0.2, 1)'
            }}
          >
            <button
              className="panel-collapse-btn"
              onClick={() => setIsRightPanelCollapsed(!isRightPanelCollapsed)}
              title={isRightPanelCollapsed ? "Expand Stage 2 Panel" : "Collapse Stage 2 Panel"}
            >
              {isRightPanelCollapsed ? <ChevronLeft size={16} /> : <ChevronRight size={16} />}
            </button>
            <div className="panel-content-wrapper">
              {/* Top Auditor Launch controller */}
              <div className="card settings-card" style={{ marginBottom: "20px" }}>
                <h3 className="card-title" style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                  <Sparkles size={16} style={{ color: "var(--accent-cyan)" }} />
                  Stage 2 AI Compliance Auditor
                </h3>

                <div className="form-group" style={{ marginTop: "12px" }}>
                  <label className="form-label">Grounding Client Profile</label>
                  <select
                    className="form-input select-input"
                    value={selectedClient || ""}
                    onChange={(e) => setSelectedClient(e.target.value)}
                  >
                    <option value="" disabled>Select Target Client</option>
                    {clients.map((c) => (
                      <option key={c.id} value={c.name}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                </div>

                <button
                  className="btn btn-primary"
                  onClick={handleAuditTrigger}
                  disabled={!newDrawing || auditStatus === "queued" || auditStatus === "auditing"}
                  style={{
                    width: "100%",
                    marginTop: "16px",
                    display: "flex",
                    alignItems: "center",
                    gap: "8px",
                    justifyContent: "center",
                    padding: "10px 16px",
                    whiteSpace: "nowrap"
                  }}
                >
                  <Play size={14} fill="currentColor" />
                  <span>
                    {auditStatus === "queued" || auditStatus === "auditing" ? "Running AI Auditing Pipeline..." : "Execute Compliance Audit"}
                  </span>
                </button>
              </div>

              {/* Compliance gauge & status */}
              {auditStatus === "completed" && (
                <div className="card settings-card" style={{ marginBottom: "20px", display: "flex", flexDirection: "column", alignItems: "center", gap: "12px" }}>
                  <div className="compliance-circle" style={{ borderColor: complianceScore && complianceScore >= 80 ? "#10b981" : "#f59e0b" }}>
                    <span className="compliance-val">{complianceScore}%</span>
                    <span className="compliance-lbl">Compliance</span>
                  </div>

                  <div className="severity-bar-grid">
                    <div className="bar-card critical">
                      <span className="bar-val">{criticalCount}</span>
                      <span className="bar-lbl">Critical</span>
                    </div>
                    <div className="bar-card high">
                      <span className="bar-val">{highCount}</span>
                      <span className="bar-lbl">High</span>
                    </div>
                    <div className="bar-card medium">
                      <span className="bar-val">{medCount}</span>
                      <span className="bar-lbl">Med</span>
                    </div>
                    <div className="bar-card low">
                      <span className="bar-val">{lowCount}</span>
                      <span className="bar-lbl">Low</span>
                    </div>
                  </div>
                </div>
              )}

              {/* Violations feed container */}
              <div className="violations-feed-card card settings-card" style={{ flexGrow: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
                <h4 className="card-title">Infractions & Grounding Explanations</h4>

                <div className="violations-list" style={{ overflowY: "auto", flexGrow: 1, marginTop: "16px", display: "flex", flexDirection: "column", gap: "12px" }}>
                  {auditStatus === "idle" && (
                    <div className="empty-state">Trigger compliance run to scan revision drawing against engineering manuals.</div>
                  )}
                  {auditStatus === "queued" || auditStatus === "auditing" ? (
                    <div className="empty-state">
                      <div className="loader spin-animation"></div>
                      <span style={{ marginTop: "12px" }}>Reasoning over draft dimensions...</span>
                    </div>
                  ) : null}

                  {auditStatus === "completed" && violations.length === 0 ? (
                    <div className="empty-state success">
                      <CheckCircle2 size={36} style={{ color: "#10b981" }} />
                      <span style={{ marginTop: "12px", color: "#10b981" }}>No compliance infractions found! Drawing is perfectly grounded.</span>
                    </div>
                  ) : null}

                  {auditStatus === "completed" && violations.map((v) => (
                    <div
                      key={v.id}
                      className={`violation-card-item ${v.severity} ${selectedViolation?.id === v.id ? "selected" : ""}`}
                      onClick={() => selectViolation(v)}
                    >
                      <div className="card-header-row">
                        <span className={`sev-badge ${v.severity}`}>{v.severity.toUpperCase()}</span>
                        <span className="clause-lbl">{v.standard_reference || "General"}</span>
                      </div>

                      <h5 className="violation-title">{v.category}</h5>
                      <p className="violation-desc">{v.description}</p>

                      <div className="recommendation-box">
                        <strong>AI Suggestion:</strong> {v.recommendation}
                      </div>

                      <div className="card-footer-row">
                        <span className="confidence-badge">Confidence: {(v.confidence * 100).toFixed(0)}%</span>
                        <span className="focus-action-btn">Focus on Drawing →</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </aside>
        </div>
      )}

      {isEditModalOpen && selectedSessionForEdit && (
        <div className="frosted-glass-modal-overlay">
          <div className="frosted-modal-card">
            <div className="modal-header">
              <h3 className="modal-title">Edit Session Remarks</h3>
              <p className="modal-subtitle">Add custom notes or checker logs for this revision audit.</p>
            </div>
            <div className="modal-body" style={{ marginTop: "16px" }}>
              <div className="form-group" style={{ margin: 0 }}>
                <label className="form-label" style={{ marginBottom: "8px", display: "block", fontSize: "0.8rem", color: "var(--text-muted)" }}>Remarks / Notes</label>
                <textarea
                  className="form-input"
                  style={{
                    width: "100%",
                    height: "120px",
                    resize: "none",
                    padding: "10px",
                    fontSize: "0.85rem",
                    lineHeight: "1.4",
                    background: "rgba(0, 0, 0, 0.2)",
                    border: "1px solid rgba(255, 255, 255, 0.1)",
                    borderRadius: "6px",
                    color: "var(--text-primary)"
                  }}
                  value={remarksText}
                  onChange={(e) => setRemarksText(e.target.value)}
                  placeholder="Enter custom remarks for this session..."
                />
              </div>
            </div>
            <div className="modal-footer" style={{ display: "flex", justifyContent: "flex-end", gap: "10px", marginTop: "20px" }}>
              <button
                className="btn-neutral-outline"
                onClick={() => {
                  setIsEditModalOpen(false);
                  setSelectedSessionForEdit(null);
                  setRemarksText("");
                }}
              >
                Cancel
              </button>
              <button
                className="btn-gradient-submit"
                onClick={handleSaveRemarks}
              >
                Save Remarks
              </button>
            </div>
          </div>
        </div>
      )}

      {isDeleteModalOpen && selectedSessionForDelete && (
        <div className="frosted-glass-modal-overlay">
          <div className="frosted-modal-card destructive-card">
            <div className="modal-header">
              <div className="warning-icon-wrapper">
                <AlertTriangle size={24} className="destructive-warning-icon" />
              </div>
              <h3 className="modal-title destructive-title" style={{ marginTop: "12px" }}>Purge Session Record?</h3>
              <p className="modal-subtitle destructive-desc">
                You are about to permanently delete this audit session log and all associated violations from MongoDB. This action is irreversible.
              </p>
            </div>
            <div className="modal-body" style={{ marginTop: "16px", padding: "12px", background: "rgba(239, 68, 68, 0.05)", border: "1px solid rgba(239, 68, 68, 0.15)", borderRadius: "6px" }}>
              <div style={{ fontSize: "0.8rem", display: "flex", flexDirection: "column", gap: "6px" }}>
                <span style={{ color: "var(--text-muted)" }}>Target File: <strong style={{ color: "var(--text-primary)" }}>{getDrawingName(selectedSessionForDelete.drawing_id)}</strong></span>
                {selectedSessionForDelete.reference_drawing_id && (
                  <span style={{ color: "var(--text-muted)" }}>Reference File: <strong style={{ color: "var(--text-primary)" }}>{getDrawingName(selectedSessionForDelete.reference_drawing_id)}</strong></span>
                )}
                <span style={{ color: "var(--text-muted)" }}>Session Date: <strong style={{ color: "var(--text-primary)" }}>{parseUtcDate(selectedSessionForDelete.created_at).toLocaleString()}</strong></span>
              </div>
            </div>
            <div className="modal-footer" style={{ display: "flex", justifyContent: "flex-end", gap: "10px", marginTop: "24px" }}>
              <button
                className="btn-neutral-outline"
                onClick={() => {
                  setIsDeleteModalOpen(false);
                  setSelectedSessionForDelete(null);
                }}
              >
                Keep Record
              </button>
              <button
                className="btn-destructive-submit"
                onClick={handleDeleteConfirm}
              >
                Purge Record
              </button>
            </div>
          </div>
        </div>
      )}

      <style>{`
        .workspace-container {
          display: flex;
          width: 100vw;
          height: calc(100vh - 44px); /* Account for AppHeader height */
          background: var(--bg-dark);
          overflow: hidden;
          font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
          color: var(--text-primary);
        }

        .workspace-sidebar {
          height: 100%;
          background: var(--bg-sidebar);
          border-right: 1px solid var(--border-color);
          display: flex;
          flex-direction: column;
          flex-shrink: 0;
          transition: width 0.28s cubic-bezier(0.4, 0, 0.2, 1), box-shadow 0.28s ease;
          overflow: visible;
          position: relative;
          z-index: 10;
        }

        .workspace-sidebar.hover-expanded {
          box-shadow: 4px 0 24px rgba(0, 0, 0, 0.12);
        }
        [data-theme="hc-dark"] .workspace-sidebar.hover-expanded {
          box-shadow: 4px 0 30px rgba(0, 0, 0, 0.5);
        }

        .sidebar-branding {
          display: flex;
          align-items: center;
          gap: 10px;
          padding: 16px 12px;
          border-bottom: 1px solid var(--border-color);
          min-height: 60px;
        }

        .brand-logo {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 36px;
          height: 36px;
          border-radius: 10px;
          background: var(--primary-glow);
          box-shadow: 0 2px 10px rgba(37, 99, 235, 0.25);
          flex-shrink: 0;
        }
        [data-theme="hc-dark"] .brand-logo {
          box-shadow: 0 2px 10px rgba(0, 229, 255, 0.2);
        }

        .brand-title {
          font-size: 1rem;
          font-weight: 700;
          color: var(--text-primary);
          margin: 0;
          line-height: 1.2;
        }

        .brand-badge {
          font-size: 0.65rem;
          font-weight: 800;
          color: var(--accent-cyan);
          letter-spacing: 0.05em;
          text-transform: uppercase;
        }

        .sidebar-nav {
          padding: 20px 12px;
          display: flex;
          flex-direction: column;
          gap: 4px;
          flex-grow: 1;
        }

        .nav-item {
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 10px 16px;
          background: transparent;
          border: none;
          color: var(--text-muted);
          font-size: 0.85rem;
          font-weight: 550;
          text-align: left;
          cursor: pointer;
          border-radius: 6px;
          transition: all 0.2s ease;
          position: relative;
        }

        .nav-item::after {
          content: attr(data-tooltip);
          position: absolute;
          left: 100%;
          top: 50%;
          transform: translateY(-50%);
          margin-left: 8px;
          padding: 6px 10px;
          background: rgba(24, 24, 27, 0.95);
          border: 1px solid var(--border-color);
          color: var(--text-primary);
          font-size: 0.75rem;
          white-space: nowrap;
          border-radius: 6px;
          opacity: 0;
          visibility: hidden;
          transition: opacity 0.15s ease, margin-left 0.15s ease;
          pointer-events: none;
          z-index: 1000;
          box-shadow: 0 2px 10px rgba(0,0,0,0.3);
        }

        .nav-item:hover::after {
          opacity: 1;
          visibility: visible;
          margin-left: 12px;
        }

        .nav-item:hover {
          color: var(--text-primary);
          background: var(--sidebar-item-hover);
        }

        .nav-item.active {
          color: var(--accent-cyan);
          background: rgba(37, 99, 235, 0.07);
          border: 1px solid rgba(37, 99, 235, 0.18);
          border-left: 3px solid var(--accent-cyan);
          padding-left: 13px;
        }
        [data-theme="hc-dark"] .nav-item.active {
          background: rgba(0, 229, 255, 0.06);
          border: 1px solid rgba(0, 229, 255, 0.15);
          border-left: 3px solid var(--accent-cyan);
        }
        [data-theme="hc-light"] .nav-item.active {
          background: rgba(37, 99, 235, 0.08);
          border: 1px solid rgba(37, 99, 235, 0.15);
          border-left: 3px solid var(--accent-cyan);
        }

        .sidebar-footer {
          padding: 20px 16px;
          border-top: 1px solid var(--border-color);
          display: flex;
          flex-direction: column;
          gap: 12px;
        }

        .user-profile {
          display: flex;
          align-items: center;
          gap: 10px;
          background: var(--bg-dark);
          padding: 10px 12px;
          border-radius: 6px;
          border: 1px solid var(--border-color);
        }

        .profile-details {
          display: flex;
          flex-direction: column;
        }

        .profile-name {
          font-size: 0.8rem;
          font-weight: 600;
          color: var(--text-primary);
        }

        .profile-role {
          font-size: 0.65rem;
          color: var(--text-muted);
        }

        .btn-logout {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 9px 12px;
          background: transparent;
          border: 1px solid var(--border-color);
          border-radius: 8px;
          color: #ef4444;
          font-size: 0.8rem;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.2s ease;
          justify-content: flex-start;
          overflow: hidden;
          white-space: nowrap;
        }

        .btn-logout:hover {
          background: rgba(239, 68, 68, 0.05);
          border-color: rgba(239, 68, 68, 0.2);
        }

        .viewport-standards-manager {
          flex-grow: 1;
          height: 100%;
          overflow-y: auto;
          background: var(--bg-dark);
          padding: 30px 0;
        }

        .workspace-main-viewport.padded {
          flex-grow: 1;
          height: 100%;
          min-height: 0;
          overflow-y: auto;
          background: var(--bg-dark);
          padding: 30px 32px;
          box-sizing: border-box;
        }

        .dual-stage-layout {
          display: flex;
          flex-grow: 1;
          height: 100%;
          overflow: hidden;
        }

        .stage1-center-panel {
          flex-grow: 1;
          height: 100%;
          min-height: 0;
          min-width: 0;
          display: flex;
          flex-direction: column;
          padding: 20px;
          overflow: hidden;
          border-right: 1px solid var(--border-color);
          box-sizing: border-box;
        }

        .cad-viewer-container {
          flex-grow: 1;
          background: var(--bg-sidebar);
          border: 1px solid var(--border-color);
          border-radius: 12px;
          display: flex;
          flex-direction: column;
          overflow: hidden;
          min-height: 0;
          min-width: 0;
          box-shadow: 0 2px 12px rgba(0, 0, 0, 0.04);
        }
        [data-theme="hc-dark"] .cad-viewer-container {
          box-shadow: 0 2px 12px rgba(0, 0, 0, 0.3);
        }

        .viewer-toolbar {
          display: flex;
          align-items: center;
          background: var(--bg-dark);
          border-bottom: 1px solid var(--border-color);
          padding: 8px 16px;
          gap: 12px;
        }

        .toolbar-group {
          display: flex;
          align-items: center;
          gap: 6px;
        }

        .toolbar-btn {
          background: transparent;
          border: 1px solid var(--border-color);
          color: var(--text-muted);
          padding: 6px;
          border-radius: 4px;
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
        }

        .toolbar-btn:hover {
          color: var(--text-primary);
          border-color: #52525b;
        }

        .toolbar-divider {
          width: 1px;
          height: 16px;
          background: var(--border-color);
        }

        .toolbar-label {
          font-size: 0.7rem;
          font-weight: 700;
          color: var(--text-muted);
          text-transform: uppercase;
        }

        .toolbar-toggle-btn {
          background: transparent;
          border: 1px solid var(--border-color);
          color: var(--text-muted);
          font-size: 0.75rem;
          padding: 4px 10px;
          border-radius: 4px;
          cursor: pointer;
        }

        .toolbar-toggle-btn.active {
          color: var(--accent-cyan);
          border-color: rgba(37, 99, 235, 0.3);
          background: rgba(37, 99, 235, 0.06);
        }
        [data-theme="hc-dark"] .toolbar-toggle-btn.active {
          border-color: rgba(0, 229, 255, 0.3);
          background: rgba(0, 229, 255, 0.06);
        }

        .diff-legend-item {
          display: flex;
          align-items: center;
          gap: 6px;
          font-size: 0.75rem;
          color: var(--text-muted);
        }

        .legend-dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
        }

        .legend-dot.unchanged { background: #10b981; }
        .legend-dot.added { background: #3b82f6; }
        .legend-dot.removed { background: #ef4444; }
        .legend-dot.modified { background: #f59e0b; }

        .split-viewports {
          display: grid;
          grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
          flex-grow: 1;
          min-height: 0;
          min-width: 0;
          overflow: hidden;
        }

        .viewport-panel {
          display: flex;
          flex-direction: column;
          min-height: 0;
          min-width: 0;
          border-right: 1px solid var(--border-color);
        }

        .viewport-panel:last-child {
          border-right: none;
        }

        .viewport-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          background: var(--bg-dark);
          border-bottom: 1px solid var(--border-color);
          padding: 5px 10px 8px 0;
        }

        .viewport-header .viewport-label {
          border-bottom: none;
        }

        .viewport-label {
          font-size: 0.75rem;
          font-weight: 700;
          color: var(--text-primary);
          text-transform: uppercase;
          padding: 2px 16px;
          background: var(--bg-dark);
          border-bottom: 1px solid var(--border-color);
        }

        .cad-canvas-mock {
          flex-grow: 1;
          min-height: 0;
          min-width: 0;
          background: var(--bg-dark);
          position: relative;
          display: flex;
          align-items: center;
          justify-content: center;
          overflow: hidden;
        }

        .blueprint-overlay {
          width: 100%;
          height: 100%;
          position: relative;
          background-image: 
            radial-gradient(rgba(255,255,255,0.03) 1px, transparent 1px),
            radial-gradient(rgba(255,255,255,0.03) 1px, transparent 1px);
          background-size: 20px 20px;
          background-position: 0 0, 10px 10px;
        }

        .cad-element {
          position: absolute;
          background: #10b981; /* Default green unchanged */
        }

        .cad-element.unchanged-line {
          height: 1px;
          background: #10b981;
        }

        .cad-element.added-line {
          height: 1px;
          background: #3b82f6;
          box-shadow: 0 0 8px #3b82f6;
        }

        .cad-element.removed-line {
          height: 1px;
          background: #ef4444;
          box-shadow: 0 0 8px #ef4444;
          text-decoration: line-through;
        }

        .cad-element.circle {
          border: 1px solid #10b981;
          border-radius: 50%;
          background: transparent;
        }

        .cad-element.circle.modified {
          border-color: #f59e0b;
          box-shadow: 0 0 8px #f59e0b;
        }

        .cad-coordinate-axis {
          position: absolute;
          bottom: 12px;
          right: 12px;
          font-family: monospace;
          font-size: 0.7rem;
          color: #52525b;
        }

        .cad-highlight-reticle {
          position: absolute;
          width: 24px;
          height: 24px;
          border: 2px dashed #ef4444;
          border-radius: 50%;
          transform: translate(-50%, -50%);
          animation: pulse 1.5s infinite;
        }

        @keyframes pulse {
          0% { transform: translate(-50%, -50%) scale(1); opacity: 1; }
          100% { transform: translate(-50%, -50%) scale(1.8); opacity: 0; }
        }

        .canvas-empty {
          color: var(--text-muted);
          font-size: 0.85rem;
        }

        .stage2-right-panel {
          width: 400px;
          height: 100%;
          background: var(--bg-sidebar);
          display: flex;
          flex-direction: column;
          flex-shrink: 0;
          border-left: 1px solid var(--border-color);
          box-shadow: -4px 0 20px rgba(0, 0, 0, 0.04);
          position: relative;
          transition: width 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        [data-theme="hc-dark"] .stage2-right-panel {
          box-shadow: -4px 0 20px rgba(0, 0, 0, 0.3);
        }

        .stage2-right-panel.collapsed {
          width: 0px;
          overflow: visible;
        }

        .panel-content-wrapper {
          display: flex;
          flex-direction: column;
          width: 100%;
          flex: 1;
          min-height: 0;
          padding: 20px;
          opacity: 1;
          transition: opacity 0.2s ease;
          overflow-y: auto;
          box-sizing: border-box;
        }

        .stage2-right-panel.collapsed .panel-content-wrapper {
          opacity: 0;
          pointer-events: none;
        }

        .panel-collapse-btn {
          position: absolute;
          top: 50%;
          left: -18px;
          transform: translateY(-50%);
          width: 18px;
          height: 48px;
          background: rgba(24, 24, 27, 0.85);
          backdrop-filter: blur(6px);
          border: 1px solid var(--border-color);
          border-right: none;
          border-radius: 8px 0 0 8px;
          display: flex;
          align-items: center;
          justify-content: center;
          cursor: pointer;
          color: var(--text-muted);
          z-index: 50;
          transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
          box-shadow: -3px 0 8px rgba(0,0,0,0.2);
        }
        .panel-collapse-btn:hover {
          color: var(--accent-cyan);
          background: rgba(37, 99, 235, 0.15);
          width: 24px;
          left: -24px;
          border-color: var(--accent-cyan);
          box-shadow: -3px 0 15px rgba(0, 229, 255, 0.25);
        }

        .compliance-circle {
          width: 110px;
          height: 110px;
          border-radius: 50%;
          border: 4px solid #10b981;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          margin-top: 10px;
        }

        .compliance-val {
          font-size: 1.6rem;
          font-weight: 800;
          color: var(--text-primary);
          line-height: 1.1;
        }

        .compliance-lbl {
          font-size: 0.65rem;
          font-weight: 700;
          text-transform: uppercase;
          color: var(--text-muted);
        }

        .severity-bar-grid {
          display: grid;
          grid-template-columns: repeat(4, 1fr);
          gap: 10px;
          width: 100%;
          margin-top: 15px;
        }

        .bar-card {
          display: flex;
          flex-direction: column;
          align-items: center;
          background: var(--bg-dark);
          padding: 8px;
          border-radius: 6px;
          border: 1px solid var(--border-color);
        }

        .bar-val {
          font-size: 1.1rem;
          font-weight: 700;
        }

        .bar-lbl {
          font-size: 0.6rem;
          color: var(--text-muted);
          text-transform: uppercase;
        }

        .bar-card.critical { border-left: 3px solid #ef4444; }
        .bar-card.high { border-left: 3px solid #f97316; }
        .bar-card.medium { border-left: 3px solid #eab308; }
        .bar-card.low { border-left: 3px solid #3b82f6; }

        .violation-card-item {
          background: var(--bg-dark);
          border: 1px solid var(--border-color);
          border-left: 3px solid transparent;
          border-radius: 10px;
          padding: 14px;
          cursor: pointer;
          transition: all 0.22s cubic-bezier(0.4, 0, 0.2, 1);
        }

        .violation-card-item:hover {
          border-color: var(--border-color);
          border-left-color: var(--accent-cyan);
          transform: translateY(-2px);
          box-shadow: 0 6px 20px rgba(0, 0, 0, 0.12);
        }
        [data-theme="hc-dark"] .violation-card-item:hover {
          box-shadow: 0 6px 20px rgba(0, 0, 0, 0.4);
        }

        .violation-card-item.selected {
          border-color: var(--accent-cyan);
          border-left-color: var(--accent-cyan);
          box-shadow: 0 0 10px rgba(37, 99, 235, 0.18);
        }
        [data-theme="hc-dark"] .violation-card-item.selected {
          box-shadow: 0 0 12px rgba(0, 229, 255, 0.2);
        }

        .card-header-row {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 8px;
        }

        .sev-badge {
          font-size: 0.6rem;
          font-weight: 800;
          padding: 2px 6px;
          border-radius: 4px;
        }

        .sev-badge.critical { background: rgba(239, 68, 68, 0.15); color: #fca5a5; }
        .sev-badge.high { background: rgba(249, 73, 22, 0.15); color: #fed7aa; }
        .sev-badge.medium { background: rgba(234, 179, 8, 0.15); color: #fef08a; }
        .sev-badge.low { background: rgba(59, 130, 246, 0.15); color: #bfdbfe; }

        [data-theme="hc-light"] .sev-badge.critical { color: #b91c1c; background: rgba(239, 68, 68, 0.1); }
        [data-theme="hc-light"] .sev-badge.high { color: #c2410c; background: rgba(249, 115, 22, 0.1); }
        [data-theme="hc-light"] .sev-badge.medium { color: #a16207; background: rgba(234, 179, 8, 0.1); }
        [data-theme="hc-light"] .sev-badge.low { color: #1d4ed8; background: rgba(59, 130, 246, 0.1); }

        .clause-lbl {
          font-size: 0.7rem;
          font-family: monospace;
          color: var(--text-muted);
        }

        .violation-title {
          font-size: 0.85rem;
          font-weight: 700;
          color: var(--text-primary);
          margin: 0 0 6px 0;
        }

        .violation-desc {
          font-size: 0.75rem;
          color: var(--text-muted);
          margin: 0 0 10px 0;
          line-height: 1.4;
        }

        .recommendation-box {
          background: var(--bg-dark);
          border: 1px solid var(--border-color);
          padding: 8px 10px;
          border-radius: 4px;
          font-size: 0.7rem;
          color: var(--text-primary);
          line-height: 1.4;
          margin-bottom: 10px;
        }

        .card-footer-row {
          display: flex;
          justify-content: space-between;
          align-items: center;
          font-size: 0.65rem;
        }

        .confidence-badge {
          color: var(--text-muted);
        }

        .focus-action-btn {
          color: var(--accent-cyan);
          font-weight: 600;
          cursor: pointer;
          transition: opacity 0.2s ease;
        }
        .focus-action-btn:hover {
          opacity: 0.75;
        }

        .loader {
          border: 3px solid var(--border-color);
          border-top-color: var(--accent-cyan);
          border-radius: 50%;
          width: 24px;
          height: 24px;
        }

        /* ------------------------------------------------------------------------- */
        /* VERSION INGESTION STATION (STAGE 1 STYLING)                               */
        /* ------------------------------------------------------------------------- */
        .upload-station-card {
          border: 1px solid var(--border-color);
          background: var(--bg-card);
          padding: 10px 16px !important;
          margin-bottom: 12px !important;
        }

        .format-badge-pill {
          padding: 2px 6px;
          border-radius: 4px;
          font-size: 0.62rem;
          font-weight: 700;
          letter-spacing: 0.02em;
          background: rgba(255, 255, 255, 0.05);
          border: 1px solid rgba(255, 255, 255, 0.08);
          color: var(--text-muted);
        }
        .format-badge-pill.ref-format {
          color: var(--accent-cyan);
          background: rgba(0, 255, 204, 0.05);
          border-color: rgba(0, 255, 204, 0.15);
        }
        .format-badge-pill.rev-format {
          color: #a78bfa;
          background: rgba(139, 92, 246, 0.05);
          border-color: rgba(139, 92, 246, 0.15);
        }
        .complexity-delta-pill {
          padding: 3px 8px;
          border-radius: 20px;
          font-size: 0.65rem;
          font-weight: 600;
          color: var(--text-secondary);
          background: rgba(255, 255, 255, 0.03);
          border: 1px solid rgba(255, 255, 255, 0.08);
          display: inline-flex;
          align-items: center;
          gap: 6px;
          letter-spacing: 0.01em;
        }
        .alignment-mismatch-banner {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 8px 12px;
          border-radius: 6px;
          background: rgba(245, 158, 11, 0.06);
          border: 1px solid rgba(245, 158, 11, 0.2);
          margin-top: 4px;
          animation: banner-fade-in 0.3s ease;
        }
        .alignment-mismatch-banner .warning-icon {
          font-size: 0.85rem;
          filter: drop-shadow(0 0 4px rgba(245, 158, 11, 0.4));
        }
        .alignment-mismatch-banner .warning-text {
          font-size: 0.68rem;
          color: #f59e0b;
          font-weight: 500;
          line-height: 1.3;
        }
        @keyframes banner-fade-in {
          from { opacity: 0; transform: translateY(-4px); }
          to { opacity: 1; transform: translateY(0); }
        }

        .compatibility-badge-status {
          display: flex;
          align-items: center;
          gap: 6px;
          padding: 3px 8px;
          border-radius: 20px;
          font-size: 0.62rem;
          font-weight: 800;
          letter-spacing: 0.05em;
          text-transform: uppercase;
          background: var(--bg-dark);
          border: 1px solid var(--border-color);
          transition: all 0.3s ease;
        }

        .compatibility-badge-status.idle {
          color: #a1a1aa;
          border-color: #3f3f46;
        }

        .compatibility-badge-status.compatible {
          color: #10b981;
          background: rgba(16, 185, 129, 0.08);
          border-color: rgba(16, 185, 129, 0.25);
          box-shadow: 0 0 10px rgba(16, 185, 129, 0.1);
        }

        .compatibility-badge-status.mismatch {
          color: #f97316;
          background: rgba(249, 115, 22, 0.08);
          border-color: rgba(249, 115, 22, 0.25);
          animation: badge-pulse 2s infinite;
        }

        .compatibility-badge-status.unsupported {
          color: #ef4444;
          background: rgba(239, 68, 68, 0.08);
          border-color: rgba(239, 68, 68, 0.25);
        }

        .compatibility-indicator-dot {
          width: 5px;
          height: 5px;
          border-radius: 50%;
          background: currentColor;
        }

        @keyframes badge-pulse {
          0% { opacity: 0.85; }
          50% { opacity: 1; transform: scale(1.02); }
          100% { opacity: 0.85; }
        }

        .ingested-files-pills {
          display: flex;
          gap: 8px;
          align-items: center;
        }

        .ingested-file-pill {
          display: flex;
          align-items: center;
          gap: 6px;
          padding: 3px 8px;
          border-radius: 6px;
          background: var(--bg-dark);
          border: 1px solid var(--border-color);
          font-size: 0.68rem;
          color: var(--text-primary);
          transition: all 0.2s ease;
        }

        .ingested-file-pill.ref {
          border-left: 3px solid var(--accent-cyan);
        }

        .ingested-file-pill.rev {
          border-left: 3px solid #8b5cf6;
        }

        .ingested-file-pill .pill-label {
          font-weight: 800;
          font-size: 0.65rem;
          letter-spacing: 0.03em;
        }

        .ingested-file-pill.ref .pill-label {
          color: var(--accent-cyan);
        }

        .ingested-file-pill.rev .pill-label {
          color: #a78bfa;
        }

        .ingested-file-pill .pill-filename {
          font-weight: 500;
          max-width: 180px;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        .pill-clear-btn {
          background: transparent;
          border: none;
          color: var(--text-muted);
          cursor: pointer;
          padding: 2px;
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
          transition: all 0.2s ease;
        }

        .pill-clear-btn:hover {
          color: #ef4444;
          background: rgba(239, 68, 68, 0.1);
          transform: scale(1.1);
        }

        .upload-dropzone-container {
          position: relative;
          width: 100%;
          height: 100%;
          transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          padding: 20px;
          box-sizing: border-box;
          overflow: hidden;
          background: transparent;
          border: 1px dashed rgba(255, 255, 255, 0.05);
        }

        .upload-dropzone-container * {
          pointer-events: none;
        }

        [data-theme="hc-light"] .upload-dropzone-container {
          border-color: rgba(0, 0, 0, 0.05);
        }

        .upload-dropzone-container.old:hover {
          background: rgba(37, 99, 235, 0.01);
          border-color: rgba(37, 99, 235, 0.15);
        }

        .upload-dropzone-container.new:hover {
          background: rgba(139, 92, 246, 0.01);
          border-color: rgba(139, 92, 246, 0.15);
        }

        .upload-dropzone-container.old.dragging {
          border-color: var(--accent-cyan) !important;
          background: rgba(37, 99, 235, 0.05) !important;
          box-shadow: inset 0 0 10px rgba(37, 99, 235, 0.1) !important;
        }
        [data-theme="hc-dark"] .upload-dropzone-container.old.dragging {
          background: rgba(0, 229, 255, 0.06) !important;
        }

        .upload-dropzone-container.new.dragging {
          border-color: #8b5cf6 !important;
          background: rgba(139, 92, 246, 0.05) !important;
          box-shadow: inset 0 0 10px rgba(139, 92, 246, 0.1) !important;
        }
        [data-theme="hc-dark"] .upload-dropzone-container.new.dragging {
          border-color: #a78bfa !important;
          background: rgba(167, 139, 250, 0.06) !important;
        }

        .dropzone-idle-view {
          display: flex;
          flex-direction: column;
          align-items: center;
          text-align: center;
          gap: 12px;
        }

        .dropzone-icon-circle {
          width: 32px;
          height: 32px;
          border-radius: 50%;
          background: rgba(255, 255, 255, 0.02);
          border: 1px solid var(--border-color);
          display: flex;
          align-items: center;
          justify-content: center;
          color: var(--text-muted);
          transition: all 0.25s ease;
        }

        .upload-dropzone-container.old:hover .dropzone-icon-circle {
          transform: translateY(-2px);
          border-color: var(--accent-cyan);
          color: var(--accent-cyan);
          background: rgba(37, 99, 235, 0.06);
        }

        .upload-dropzone-container.new:hover .dropzone-icon-circle {
          transform: translateY(-2px);
          border-color: #8b5cf6;
          color: #a78bfa;
          background: rgba(139, 92, 246, 0.06);
        }

        .dropzone-main-text {
          font-size: 0.88rem;
          font-weight: 600;
          color: var(--text-primary);
          margin: 0;
        }

        .browse-link {
          color: var(--accent-cyan);
          text-decoration: underline;
          font-weight: 700;
        }

        .upload-dropzone-container.new .browse-link {
          color: #a78bfa;
        }

        .dropzone-sub-text {
          font-size: 0.72rem;
          color: var(--text-muted);
          margin: 4px 0 0 0;
        }

        /* Active Processing View */
        .dropzone-active-view {
          width: 100%;
          display: flex;
          flex-direction: column;
          align-items: center;
          text-align: center;
          padding: 10px;
        }

        .pulsing-loader-wrapper {
          width: 32px;
          height: 32px;
          border-radius: 50%;
          background: var(--bg-dark);
          border: 1px solid var(--border-color);
          display: flex;
          align-items: center;
          justify-content: center;
          margin-bottom: 10px;
          color: var(--accent-cyan);
          animation: pulse-glow 1.5s infinite;
        }

        @keyframes pulse-glow {
          0% { box-shadow: 0 0 0 0 rgba(37, 99, 235, 0.25); }
          70% { box-shadow: 0 0 0 8px rgba(37, 99, 235, 0); }
          100% { box-shadow: 0 0 0 0 rgba(37, 99, 235, 0); }
        }
        [data-theme="hc-dark"] .pulsing-loader-wrapper {
          animation-name: pulse-glow-dark;
        }
        @keyframes pulse-glow-dark {
          0% { box-shadow: 0 0 0 0 rgba(0, 229, 255, 0.25); }
          70% { box-shadow: 0 0 0 8px rgba(0, 229, 255, 0); }
          100% { box-shadow: 0 0 0 0 rgba(0, 229, 255, 0); }
        }

        .active-details-wrapper {
          display: flex;
          flex-direction: column;
          margin-bottom: 12px;
        }

        .active-status-title {
          font-size: 0.78rem;
          font-weight: 700;
          color: var(--text-primary, #f4f4f5);
        }

        .active-filename-sub {
          font-size: 0.65rem;
          color: var(--text-muted, #71717a);
          margin-top: 2px;
          max-width: 250px;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        .dropzone-progress-bar-bg {
          width: 80%;
          max-width: 240px;
          height: 4px;
          background: var(--border-color);
          border-radius: 2px;
          overflow: hidden;
        }

        .dropzone-progress-bar-fill {
          height: 100%;
          background: linear-gradient(90deg, var(--accent-cyan), #818cf8);
          border-radius: 2px;
          transition: width 0.2s ease;
        }

        /* Completed Ingestion View */
        .dropzone-completed-view {
          width: 100%;
          height: 100%;
          display: flex;
          flex-direction: column;
          justify-content: space-between;
        }

        .completed-card-header {
          display: flex;
          justify-content: space-between;
          align-items: flex-start;
          width: 100%;
        }

        .file-info-col {
          display: flex;
          align-items: center;
          gap: 10px;
          overflow: hidden;
        }

        .file-format-badge {
          font-size: 0.7rem;
          font-weight: 800;
          padding: 6px 8px;
          border-radius: 6px;
          letter-spacing: 0.02em;
        }

        .file-format-badge.badge-dwg { background: rgba(249, 115, 22, 0.15); color: #f97316; border: 1px solid rgba(249, 115, 22, 0.3); }
        .file-format-badge.badge-dxf { background: rgba(20, 184, 166, 0.15); color: #14b8a6; border: 1px solid rgba(20, 184, 166, 0.3); }
        .file-format-badge.badge-pdf { background: rgba(239, 68, 68, 0.15); color: #ef4444; border: 1px solid rgba(239, 68, 68, 0.3); }

        .completed-metadata {
          display: flex;
          flex-direction: column;
          overflow: hidden;
        }

        .completed-filename {
          font-size: 0.8rem;
          font-weight: 700;
          color: var(--text-primary, #f4f4f5);
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
          max-width: 180px;
        }

        .completed-filesize {
          font-size: 0.65rem;
          color: var(--text-muted, #71717a);
        }

        .btn-clear-upload {
          background: transparent;
          border: 1px solid var(--border-color, #27272a);
          color: var(--text-muted, #71717a);
          padding: 6px;
          border-radius: 6px;
          cursor: pointer;
          transition: all 0.2s ease;
          display: flex;
          align-items: center;
          justify-content: center;
        }

        .btn-clear-upload:hover {
          color: #ef4444;
          background: rgba(239, 68, 68, 0.05);
          border-color: rgba(239, 68, 68, 0.2);
          transform: scale(1.05);
        }

        .drawing-entities-stats-grid {
          display: grid;
          grid-template-columns: repeat(4, 1fr);
          gap: 4px;
          background: var(--bg-dark);
          border: 1px solid var(--border-color);
          padding: 4px 8px;
          border-radius: 6px;
          margin-top: 6px;
        }

        .stat-unit {
          display: flex;
          flex-direction: column;
          align-items: center;
        }

        .stat-unit-val {
          font-size: 0.72rem;
          font-weight: 800;
          color: var(--text-primary, #f4f4f5);
          font-family: monospace;
        }

        .stat-unit-lbl {
          font-size: 0.55rem;
          color: var(--text-muted, #71717a);
          text-transform: uppercase;
          margin-top: 1px;
        }

        .completed-status-badge {
          display: inline-flex;
          align-items: center;
          font-size: 0.62rem;
          font-weight: 700;
          color: #10b981;
          margin-top: 4px;
          background: rgba(16, 185, 129, 0.05);
          padding: 2px 8px;
          border-radius: 4px;
          border: 1px solid rgba(16, 185, 129, 0.15);
          align-self: flex-start;
        }

        /* Ingestion Failure View */
        .dropzone-failed-view {
          display: flex;
          flex-direction: column;
          align-items: center;
          text-align: center;
          padding: 4px;
        }

        .failed-icon-circle {
          width: 32px;
          height: 32px;
          border-radius: 50%;
          background: rgba(239, 68, 68, 0.08);
          border: 1px solid rgba(239, 68, 68, 0.2);
          display: flex;
          align-items: center;
          justify-content: center;
          margin-bottom: 6px;
          color: #ef4444;
        }

        .failed-status-title {
          font-size: 0.76rem;
          font-weight: 700;
          color: #ef4444;
        }

        .failed-error-desc {
          font-size: 0.66rem;
          color: var(--text-muted, #71717a);
          margin: 3px 0 8px 0;
          max-width: 250px;
          line-height: 1.3;
        }

        .retry-link-label {
          font-size: 0.68rem;
          color: var(--accent-cyan);
          text-decoration: underline;
          cursor: pointer;
          font-weight: 600;
          transition: opacity 0.2s ease;
        }
        .retry-link-label:hover {
          opacity: 0.75;
        }

        /* Frosted Glass Modals */
        .frosted-glass-modal-overlay {
          position: fixed;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          background: rgba(10, 10, 12, 0.6);
          backdrop-filter: blur(12px);
          display: flex;
          align-items: center;
          justify-content: center;
          z-index: 9999;
          animation: modal-fade-in 0.25s cubic-bezier(0.4, 0, 0.2, 1);
        }

        @keyframes modal-fade-in {
          from { opacity: 0; }
          to { opacity: 1; }
        }

        .frosted-modal-card {
          width: 100%;
          max-width: 460px;
          background: rgba(24, 24, 27, 0.75);
          border: 1px solid rgba(255, 255, 255, 0.08);
          box-shadow: 0 20px 40px rgba(0, 0, 0, 0.5), inset 0 1px 0 rgba(255, 255, 255, 0.1);
          backdrop-filter: blur(20px);
          border-radius: 12px;
          padding: 24px;
          animation: card-slide-up 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
        }

        .frosted-modal-card.destructive-card {
          border: 1px solid rgba(239, 68, 68, 0.2);
          background: rgba(24, 20, 20, 0.85);
        }

        @keyframes card-slide-up {
          from { transform: translateY(20px) scale(0.95); opacity: 0; }
          to { transform: translateY(0) scale(1); opacity: 1; }
        }

        .modal-title {
          font-size: 1.15rem;
          font-weight: 700;
          color: var(--text-primary);
          margin: 0;
        }

        .modal-title.destructive-title {
          color: #ef4444;
          text-align: center;
        }

        .modal-subtitle {
          font-size: 0.8rem;
          color: var(--text-muted);
          margin: 4px 0 0 0;
        }

        .modal-subtitle.destructive-desc {
          text-align: center;
          line-height: 1.4;
          margin-top: 8px;
        }

        .warning-icon-wrapper {
          display: flex;
          justify-content: center;
          margin-bottom: 8px;
        }

        .destructive-warning-icon {
          color: #ef4444;
          animation: pulse-alert 2s infinite ease-in-out;
        }

        @keyframes pulse-alert {
          0%, 100% { transform: scale(1); filter: drop-shadow(0 0 0 rgba(239, 68, 68, 0)); }
          50% { transform: scale(1.1); filter: drop-shadow(0 0 8px rgba(239, 68, 68, 0.4)); }
        }

        /* Buttons styles inside modals */
        .btn-neutral-outline {
          background: transparent;
          border: 1px solid rgba(255, 255, 255, 0.1);
          color: var(--text-muted);
          padding: 8px 16px;
          border-radius: 6px;
          cursor: pointer;
          font-size: 0.85rem;
          font-weight: 500;
          transition: all 0.2s ease;
        }
        .btn-neutral-outline:hover {
          background: rgba(255, 255, 255, 0.05);
          color: var(--text-primary);
          border-color: rgba(255, 255, 255, 0.2);
        }

        .btn-gradient-submit {
          background: linear-gradient(90deg, var(--accent-cyan), #818cf8);
          border: none;
          color: #0b0f19;
          padding: 8px 16px;
          border-radius: 6px;
          cursor: pointer;
          font-size: 0.85rem;
          font-weight: 600;
          transition: all 0.2s ease;
        }
        .btn-gradient-submit:hover {
          filter: brightness(1.15);
          transform: translateY(-1px);
          box-shadow: 0 4px 12px rgba(0, 255, 204, 0.35);
        }

        .btn-destructive-submit {
          background: #ef4444;
          border: none;
          color: #fff;
          padding: 8px 16px;
          border-radius: 6px;
          cursor: pointer;
          font-size: 0.85rem;
          font-weight: 600;
          transition: all 0.2s ease;
        }
        .btn-destructive-submit:hover {
          background: #dc2626;
          transform: translateY(-1px);
          box-shadow: 0 4px 12px rgba(239, 68, 68, 0.35);
        }

        .spin-animation {
          animation: spin-icon-anim 2s linear infinite;
        }

        @keyframes spin-icon-anim {
          0% { transform: rotate(0deg); }
          100% { transform: rotate(360deg); }
        }

        .left-resize-divider:hover,
        .left-resize-divider.active,
        .right-resize-divider:hover,
        .right-resize-divider.active {
          background: rgba(0, 229, 255, 0.4) !important;
          box-shadow: 0 0 8px rgba(0, 229, 255, 0.6);
        }
      `}</style>
    </div>
  );
};
