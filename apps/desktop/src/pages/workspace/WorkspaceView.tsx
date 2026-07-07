import React, { useState, useEffect, useRef } from "react";
import {
  CheckCircle2,
  Play,
  Sparkles,
  ZoomIn,
  ZoomOut,
  Maximize,
  Loader,
  Trash2,
  ChevronRight,
  ChevronLeft,
  Download,
  RotateCcw,
  ChevronDown
} from "lucide-react";
import { jsPDF } from "jspdf";
import { save } from "@tauri-apps/plugin-dialog";
import { writeFile } from "@tauri-apps/plugin-fs";
import { useWorkspaceStore, DrawingItem } from "../../stores/workspaceStore";
import { useConnectionStore } from "../../stores/connectionStore";
import { useReviewStore } from "../../stores/reviewStore";
import { DrawingCanvas } from "../../components/review/DrawingCanvas";
import { ThreeDViewer } from "../../components/review/ThreeDViewer";

// ─── UPLOAD ZONE ─────────────────────────────────────────────────────────────
interface UploadZoneProps {
  side: "old" | "new";
  uploadState: import("../../stores/workspaceStore").UploadState;
  progress: number;
  fileName: string | null;
  fileSize: number | null;
  error: string | null;
  activeDrawing: DrawingItem | null;
  uploadDrawingFile: (file: File, side: "old" | "new") => Promise<boolean>;
  clearUpload: (side: "old" | "new") => void;
  currentNav: string;
}

const UploadZone: React.FC<UploadZoneProps> = ({
  side, uploadState, progress, fileName, error,
  uploadDrawingFile, currentNav
}) => {
  const [isDragActive, setIsDragActive] = React.useState(false);
  const fileInputRef = React.useRef<HTMLInputElement>(null);

  const [elapsed, setElapsed] = React.useState(0);
  const [tipIndex, setTipIndex] = React.useState(0);

  const tips = [
    "Delaunay Mesher: Generating 3D surface mesh nodes...",
    "Stitching B-Rep boundary curves & topological vertices...",
    "Mapping harmonize color groups and materials...",
    "Integrating solid body volume & mass attributes...",
    "Deducing geometric tolerances from model structure..."
  ];

  React.useEffect(() => {
    let elapsedInterval: any;
    let tipInterval: any;
    if (uploadState === "processing") {
      elapsedInterval = setInterval(() => {
        setElapsed(prev => prev + 1);
      }, 1000);
      tipInterval = setInterval(() => {
        setTipIndex(prev => (prev + 1) % tips.length);
      }, 4000);
    } else {
      setElapsed(0);
      setTipIndex(0);
    }
    return () => {
      clearInterval(elapsedInterval);
      clearInterval(tipInterval);
    };
  }, [uploadState]);

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setIsDragActive(true);
    } else if (e.type === "dragleave") {
      setIsDragActive(false);
    }
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      await uploadDrawingFile(e.dataTransfer.files[0], side);
    }
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      await uploadDrawingFile(e.target.files[0], side);
    }
  };

  const triggerFileInput = () => {
    fileInputRef.current?.click();
  };

  const canInteract = uploadState === "idle" || uploadState === "failed";

  return (
    <div
      className={`upload-zone-wrapper ${isDragActive ? "drag-active" : ""} ${uploadState}`}
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
        style={{ display: "none" }}
        onChange={handleFileChange}
        accept={currentNav === "3d-workspace" ? ".step,.stp,.iges,.igs,.icd,.sldprt,.sldasm" : ".pdf,.dwg,.dxf"}
      />

      {uploadState === "idle" && (
        <div className="upload-idle-state" onClick={triggerFileInput}>
          <div className="upload-icon-circle">
            <svg style={{ width: "22px", height: "22px" }} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12"/>
            </svg>
          </div>
          <span className="upload-primary-text">Drag & drop CAD file here</span>
          <span className="upload-secondary-text">or <span className="browse-link">browse file system</span></span>
          <span className="upload-formats-text">
            Supports {currentNav === "3d-workspace" ? "STEP, IGES, ICD, SolidWorks" : "DWG, DXF, PDF"}
          </span>
        </div>
      )}

      {uploadState === "uploading" && (
        <div className="upload-processing-state">
          <Loader className="spin-animation loader-icon" />
          <span className="progress-percentage-label">{progress}%</span>
          <span className="upload-status-primary">Uploading CAD Draft...</span>
          <span className="upload-status-secondary">{fileName}</span>
          <div className="progress-bar-track">
            <div className="progress-bar-fill" style={{ width: `${progress}%` }}></div>
          </div>
        </div>
      )}

      {(uploadState === "processing" || uploadState === "validating") && (
        <div className="upload-processing-state ingesting">
          <div className="loader spin-animation"></div>
          <span className="upload-status-primary">
            {uploadState === "validating" ? "Reconstructing Vector Entities..." : "Aligning Geometrical Checkpoints..."}
          </span>
          <span className="upload-status-secondary">{fileName}</span>
          <span className="elapsed-timer">Elapsed: {elapsed}s</span>
          <div className="tip-carousel-card">
            <Sparkles size={11} className="tip-sparkle-icon" />
            <span className="tip-carousel-text">{tips[tipIndex]}</span>
          </div>
        </div>
      )}

      {uploadState === "failed" && (
        <div className="upload-error-state">
          <div className="error-icon-circle">!</div>
          <span className="error-primary-text">Pipeline Processing Failure</span>
          <p className="error-description-box">{error || "An unknown ingestion pipeline error occurred. Please verify your vector formats."}</p>
          <span className="retry-link-label" onClick={triggerFileInput}>Retry browse</span>
        </div>
      )}
    </div>
  );

};

interface WorkspaceViewProps {
  currentNav: string;
}

export const WorkspaceView: React.FC<WorkspaceViewProps> = ({ currentNav }) => {
  const backendUrl = useConnectionStore((s) => s.backendUrl);
  const apiToken = useConnectionStore((s) => s.apiToken);

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
    clients,
    selectedClient,
    setSelectedClient
  } = useWorkspaceStore();

  const {
    viewport: reviewViewport,
    setViewport: setReviewViewport
  } = useReviewStore();

  const [isLeftPanelCollapsed, setIsLeftPanelCollapsed] = useState(false);
  const [isRightPanelCollapsed, setIsRightPanelCollapsed] = useState(false);
  const [leftSidebarWidth, setLeftSidebarWidth] = useState(400);
  const [rightSidebarWidth, setRightSidebarWidth] = useState(400);
  const [isResizingLeft, setIsResizingLeft] = useState(false);
  const [isResizingRight, setIsResizingRight] = useState(false);

  // Resize Left
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (isResizingLeft) {
        const newWidth = Math.max(250, Math.min(600, e.clientX));
        setLeftSidebarWidth(newWidth);
      }
    };
    const handleMouseUp = () => {
      setIsResizingLeft(false);
    };
    if (isResizingLeft) {
      window.addEventListener("mousemove", handleMouseMove);
      window.addEventListener("mouseup", handleMouseUp);
    }
    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
  }, [isResizingLeft]);

  // Resize Right
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (isResizingRight) {
        const newWidth = Math.max(250, Math.min(600, window.innerWidth - e.clientX));
        setRightSidebarWidth(newWidth);
      }
    };
    const handleMouseUp = () => {
      setIsResizingRight(false);
    };
    if (isResizingRight) {
      window.addEventListener("mousemove", handleMouseMove);
      window.addEventListener("mouseup", handleMouseUp);
    }
    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
  }, [isResizingRight]);

  const containerRefOld = useRef<HTMLDivElement>(null);
  const containerRefNew = useRef<HTMLDivElement>(null);
  const drawingCanvasRefOld = useRef<any>(null);
  const drawingCanvasRefNew = useRef<any>(null);
  const [oldSize, setOldSize] = useState({ width: 480, height: 400 });
  const [newSize, setNewSize] = useState({ width: 480, height: 400 });

  // Update sizes when containers resize
  useEffect(() => {
    const resizeObserver = new ResizeObserver((entries) => {
      for (let entry of entries) {
        if (entry.target === containerRefOld.current) {
          setOldSize({ width: entry.contentRect.width, height: entry.contentRect.height });
        }
        if (entry.target === containerRefNew.current) {
          setNewSize({ width: entry.contentRect.width, height: entry.contentRect.height });
        }
      }
    });

    if (containerRefOld.current) resizeObserver.observe(containerRefOld.current);
    if (containerRefNew.current) resizeObserver.observe(containerRefNew.current);

    return () => {
      resizeObserver.disconnect();
    };
  }, [oldDrawing, newDrawing]);

  // Automated AI Physical Comparison State (moved from shell)
  const [aiScanProgress, setAiScanProgress] = useState<"idle" | "scanning_ref" | "extracting" | "scanning_rev" | "comparing" | "completed">("idle");
  const [aiChecklistResults, setAiChecklistResults] = useState<Record<string, any>>({});
  const [expandedChecklistPanels, setExpandedChecklistPanels] = useState<Record<string, boolean>>({});
  const [aiScanError, setAiScanError] = useState<string | null>(null);

  // Reset comparison state when drawings are cleared or changed
  useEffect(() => {
    if (!oldDrawing || !newDrawing) {
      setAiChecklistResults({});
      setAiScanProgress("idle");
      setAiScanError(null);
    }
  }, [oldDrawing, newDrawing]);

  const toggleChecklistPanel = (key: string) => {
    setExpandedChecklistPanels(prev => ({ ...prev, [key]: !prev[key] }));
  };

  const handleAuditTrigger = async () => {
    if (!newDrawing || !selectedClient) return;
    await runAudit(selectedClient);
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
          // Replace CP932 decoded multiplication sign "×" with standard lowercase "x"
          clean = clean.replace(/×/g, "x");
          clean = clean.replace(/[{}]/g, "");
          // Aggressively strip ALL AutoCAD MTEXT formatting codes (fonts, colors, alignment, etc.)
          clean = clean.replace(/\\[A-Za-z0-9\-~|.]+;/g, "");
          clean = clean.replace(/\\P/g, " ");
          // Fallback strip for any remaining \L or \l formatting tags
          clean = clean.replace(/\\[LlOo]/g, "");
          return clean.trim();
        };

        const normalizeStr = (str: string) => {
          let s = str.toLowerCase().trim();
          s = s.replace(/%%c/g, "⌀").replace(/%%d/g, "°").replace(/%%p/g, "±");
          s = s.replace(/ラ/g, "x");
          s = s.replace(/×/g, "x");
          s = s.replace(/:/g, "/");
          return s
            .replace(/[\s\(\)\[\]\{\}\:\;\,\-\_\.\/\引\（\）－−–—―〜～]/g, "")
            .trim();
        };

        const findAllFuzzyMatches = (
          searchTerm: string,
          entities: { text: string; x: number; y: number; bbox?: any; height?: number; layoutSpace?: string; layer?: string }[],
          preferModelSpace: boolean = false,
          allowNumberMismatch: boolean = false,
          minScore: number = 0
        ): { text: string; x: number; y: number; bbox?: any; height?: number; layoutSpace?: string; layer?: string }[] => {
          if (!searchTerm) return [];

          if (searchTerm.includes('\n')) {
            const lines = searchTerm.split('\n').map(l => l.trim()).filter(l => l.length > 1);
            const seen = new Set<string>();
            const combined: { text: string; x: number; y: number; bbox?: any; height?: number; layoutSpace?: string; layer?: string }[] = [];
            for (const line of lines) {
              const lineMatches = findAllFuzzyMatches(line, entities, preferModelSpace, true, minScore);
              for (const m of lineMatches) {
                const key = `${m.x.toFixed(2)},${m.y.toFixed(2)}`;
                if (!seen.has(key)) {
                  seen.add(key);
                  combined.push(m);
                }
              }
            }
            return combined;
          }

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
              normEnt.replace(/^[crmoo⌀]/i, "") === normSearch ||
              normSearch.replace(/^[crmoo⌀]/i, "") === normEnt
            ) {
              score = 90;
            } else {
              const cleanSearchNum = normSearch.replace(/^[0-9]+-/, "").replace(/^[crmoo⌀]/i, "");
              const cleanEntNum = normEnt.replace(/^[0-9]+-/, "").replace(/^[crmoo⌀]/i, "");
              const fSearch = parseFloat(cleanSearchNum);
              const fEnt = parseFloat(cleanEntNum);
              if (!isNaN(fSearch) && !isNaN(fEnt) && fSearch === fEnt) {
                score = 90;
              } else if (!isNaN(fSearch) && !isNaN(parseFloat(normEnt)) && fSearch === parseFloat(normEnt)) {
                score = 90;
              }
            }

            if (score < 90) {
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
                } else if (allowNumberMismatch && jaccard > 0.40) {
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
          const finalThreshold = Math.max(threshold, minScore);
          return matches.filter(m => m.score >= finalThreshold).map(m => m.ent);
        };

        const isCoordinateTick = (text: string): boolean => {
          const t = (text || "").trim().toUpperCase();
          if (!t) return true;
          if (t.length === 1 && t >= 'A' && t <= 'Z') return true;
          const num = parseInt(t, 10);
          if (!isNaN(num) && num.toString() === t && num >= 1 && num <= 24) return true;
          return false;
        };

        const isStaticLabelOrHeader = (text: string): boolean => {
          const t = (text || "").trim().toLowerCase();
          if (!t) return true;

          const exactStaticTerms = new Set([
            "no.", "no", "and.", "and", "g", "h", "a", "b", "c", "d", "e", "f", "例", "（例）", "こえ", "下", "符号"
          ]);
          if (exactStaticTerms.has(t)) return true;

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
          ent: { text: string; x: number; y: number; layer?: string; eType?: string },
          drawing: any
        ): boolean => {
          const isStructuralAnnotation = ent.eType === 'tolerance' || ent.eType === 'leader' || ent.eType === 'multileader' || ent.eType === 'attrib' || ent.eType === 'insert' || ent.eType === 'mtext' || ent.eType === 'block' || ent.eType === 'dimension' ||
            /^\d*[-]?[CR]\d+(\.\d+)?$/i.test(ent.text.trim().replace(/\s/g, '')) ||
            /^[\u2460-\u2473\u3251-\u325f\u32b1-\u32bf]$/.test(ent.text.trim()) ||
            /^\(\d{1,2}\)$/.test(ent.text.trim()) ||
            /^[\u25bd\u25bf\u25b3\u25b2\u2299\u25ef\u25a1]$/.test(ent.text.trim());

          if (!isStructuralAnnotation) {
            if (isStaticLabelOrHeader(ent.text)) return false;

            const tClean = ent.text.trim().replace(/\s/g, '').toLowerCase();
            const isToleranceRange = /^\d+(\.\d+)?[sS]?(~|〜|-)\d+(\.\d+)?[sS]?$/.test(tClean);
            const isSurfaceFinish = /^\d+(\.\d+)?[sS]$/.test(tClean);
            if (isToleranceRange || isSurfaceFinish || ["表示外公差", "寸法区分", "平行度", "直角度", "許容差", "仕上ゲ記号", "表面粗さ", "普通寸法許容差", "角度", "長さ", "表示外"].some(kw => ent.text.includes(kw)) || ["~", "〜", "±"].includes(tClean)) return false;
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

          if (pctX < 0.045 || pctX > 0.98 || pctY < 0.045 || pctY > 0.98) return false;

          const isNearMargin = pctX < 0.12 || pctX > 0.88 || pctY < 0.12 || pctY > 0.88;
          if (!isStructuralAnnotation && isNearMargin && isCoordinateTick(ent.text)) return false;

          if (pctX >= 0.04 && pctX <= 0.42 && pctY >= 0.70 && pctY <= 1.02) return false;

          return true;
        };

        const isDuplicateEntity = (
          list: { text: string; x: number; y: number }[],
          text: string,
          x: number,
          y: number
        ): boolean => {
          return list.some(ent => ent.text === text && Math.hypot(ent.x - x, ent.y - y) < 1.0);
        };

        const textEntities: { text: string; x: number; y: number; handle?: string; bbox?: any; height?: number; layoutSpace?: string; layer?: string; eType?: string }[] = [];
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

        const refTextEntities: { text: string; x: number; y: number; handle?: string; bbox?: any; height?: number; layoutSpace?: string; layer?: string; eType?: string }[] = [];
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

        const computeBounds = (entities: { text: string; x: number; y: number; layer?: string }[]) => {
          if (entities.length === 0) return { xMin: 0, xMax: 1000, yMin: 0, yMax: 1000 };
          const xs = entities.map(e => e.x);
          const ys = entities.map(e => e.y);
          return { xMin: Math.min(...xs), xMax: Math.max(...xs), yMin: Math.min(...ys), yMax: Math.max(...ys) };
        };

        if (textEntities.length > 0) {
          const bounds = computeBounds(textEntities);
          newXMin = bounds.xMin; newXMax = bounds.xMax; newYMin = bounds.yMin; newYMax = bounds.yMax;
        }
        if (refTextEntities.length > 0) {
          const bounds = computeBounds(refTextEntities);
          oldXMin = bounds.xMin; oldXMax = bounds.xMax; oldYMin = bounds.yMin; oldYMax = bounds.yMax;
        }

        const mappedMarkings: any[] = [];
        const rawMarkings = data.data.canvas_markings || [];

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
            matches = matches.filter(m => isEngineeringDataEntity(m, newDrawing));
            refMatches = refMatches.filter(m => isEngineeringDataEntity(m, oldDrawing));
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

        useWorkspaceStore.setState({ violations: mappedMarkings });
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

  const parseTabularContent = (content: string) => {
    if (!content) return [];
    const lines = content.split('\n').filter((l: string) => l.trim());
    const headerLine = lines.find((l: string) => l.includes('|'));
    const dataLines = lines.filter((l: string) => l.includes('|') && !l.match(/^-+$/) && l !== headerLine);

    return dataLines.map((line: string) => {
      const parts = line.split('|').map((p: string) => p.trim());
      let cleanedParts = [...parts];
      if (cleanedParts[0] === '') cleanedParts.shift();
      if (cleanedParts[cleanedParts.length - 1] === '') cleanedParts.pop();

      const field = cleanedParts[0] || '';
      const original = cleanedParts[1] || '';
      const kmti = cleanedParts[2] || '';
      const rawStatus = cleanedParts[3] || '';

      const normalizeStatus = (s: string): string => {
        const u = s?.toUpperCase().trim() || "";
        if (["MISMATCHED", "MISMATCH", "DIFFER", "DIFFERENT"].includes(u)) return "CHANGED";
        return s?.trim() || "";
      };
      const status = normalizeStatus(rawStatus);
      const isMatch = status.toUpperCase().includes('MATCHED') && !status.toUpperCase().includes('MIS');

      return { field, original, kmti, status, isMatch };
    });
  };

  const criticalCount = violations.filter((v) => v.severity === "critical").length;
  const highCount = violations.filter((v) => v.severity === "high").length;
  const medCount = violations.filter((v) => v.severity === "medium").length;
  const lowCount = violations.filter((v) => v.severity === "low").length;

  const exportToPDF = async () => {
    try {
      const imgDataNew = drawingCanvasRefNew.current?.exportImage(7016, 4960);
      if (!imgDataNew) {
        alert("Drawing canvas elements not found or failed to render.");
        return;
      }

      const imgDataOld = oldDrawing ? drawingCanvasRefOld.current?.exportImage(7016, 4960) : null;

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
      const savePath = await save({
        defaultPath: filename,
        filters: [{ name: "PDF Files", extensions: ["pdf"] }]
      });

      if (savePath) {
        const pdfOutput = pdf.output("arraybuffer");
        await writeFile(savePath, new Uint8Array(pdfOutput));
      }
    } catch (err: any) {
      console.error(err);
      alert(`Export Failed: ${err.message || err}`);
    }
  };

  return (
    <div className="workspace-container">
      {/* 1. LEFT SIDEBAR: DOCKED PHYSICAL CHECKLIST DECK */}
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

              {aiScanError && aiScanProgress === "idle" && (
                <div style={{
                  display: "flex", alignItems: "flex-start", gap: "10px",
                  background: "rgba(245, 158, 11, 0.08)",
                  border: "1px solid rgba(245, 158, 11, 0.3)",
                  borderRadius: "8px", padding: "10px 12px", margin: "8px 0"
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
                  >×</button>
                </div>
              )}

              {aiScanProgress === "completed" && (
                <div style={{ display: "flex", flexDirection: "column", gap: "12px", flexGrow: 1, paddingBottom: "24px" }}>
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
                        let color = "#10b981";
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

                    let badgeColor = "#10b981";
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
                            borderBottom: isExpanded ? "1px solid rgba(255,255,255,0.05)" : "none"
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

                        {isExpanded && (
                          <div style={{ padding: "14px 16px", background: "rgba(0,0,0,0.25)", display: "flex", flexDirection: "column", gap: "14px" }}>
                            {result.difference_summary && (
                              <div>
                                <div style={{ fontSize: "0.8rem", fontWeight: 500, color: "var(--accent-cyan)", marginBottom: "6px", letterSpacing: "0.05em" }}>DIFFERENCE SUMMARY</div>
                                <div style={{ fontSize: "0.85rem", color: "#e4e4e7", lineHeight: "1.5", fontWeight: 100 }}>{result.difference_summary}</div>
                              </div>
                            )}

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
                                          let cellBadgeColor = "#ef4444";
                                          let cellBadgeBg = "rgba(239, 68, 68, 0.08)";
                                          let statusText = row.status || "MISMATCHED";

                                          const matchingViolation = violations.find(v => {
                                            const desc = v.description ? v.description.trim() : "";
                                            const matchesText = desc === row.kmti || desc === row.original ||
                                              desc.toLowerCase().includes((row.kmti || "").toLowerCase()) ||
                                              (row.kmti || "").toLowerCase().includes(desc.toLowerCase());
                                            const vCat = v.category ? v.category.toLowerCase().replace(/_/g, "") : "";
                                            const pKey = key.toLowerCase().replace(/_/g, "");
                                            const matchesCategory = vCat === pKey || vCat.includes(pKey) || pKey.includes(vCat);
                                            return matchesText && matchesCategory;
                                          });

                                          if (matchingViolation) {
                                            const pt = matchingViolation.pen_type || "";
                                            if (pt === "ai_orange") {
                                              cellBadgeColor = "#f97316"; statusText = "CHANGED"; cellBadgeBg = "rgba(249, 115, 22, 0.08)";
                                            } else if (pt === "checker_blue") {
                                              cellBadgeColor = "#3b82f6"; statusText = "ADDED"; cellBadgeBg = "rgba(59, 130, 246, 0.08)";
                                            } else if (pt === "ai_red") {
                                              cellBadgeColor = "#ef4444"; statusText = "REMOVED"; cellBadgeBg = "rgba(239, 68, 68, 0.08)";
                                            } else if (pt === "resolved_green" || pt === "ai_green") {
                                              cellBadgeColor = "#10b981"; statusText = "MATCHED"; cellBadgeBg = "rgba(16, 185, 129, 0.08)";
                                            }
                                          } else {
                                            if (statusText.toUpperCase().includes("CHANGE")) {
                                              cellBadgeColor = "#f97316"; cellBadgeBg = "rgba(249, 115, 22, 0.08)";
                                            } else if (statusText.toUpperCase().includes("ADD")) {
                                              cellBadgeColor = "#3b82f6"; cellBadgeBg = "rgba(59, 130, 246, 0.08)";
                                            }
                                          }

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
                                                cursor: matchingViolation ? "pointer" : "default"
                                              }}
                                            >
                                              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "10px" }}>
                                                <div style={{ display: "flex", alignItems: "center", gap: "6px", minWidth: 0, flex: 1 }}>
                                                  <span style={{
                                                    width: "7px", height: "7px", borderRadius: "50%",
                                                    backgroundColor: cellBadgeColor, flexShrink: 0
                                                  }} />
                                                  <span style={{ fontSize: "0.78rem", fontWeight: 650, color: "#ffffff", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                                                    {row.field}
                                                  </span>
                                                </div>
                                                <span style={{
                                                  fontSize: "0.62rem", fontWeight: 700, padding: "2px 6px", borderRadius: "4px",
                                                  color: cellBadgeColor, background: cellBadgeBg, border: `1px solid ${cellBadgeColor}33`,
                                                  textTransform: "uppercase", flexShrink: 0
                                                }}>
                                                  {statusText}
                                                </span>
                                              </div>

                                              <div style={{ display: "flex", flexDirection: "column", gap: "6px", background: "rgba(0,0,0,0.15)", padding: "8px", borderRadius: "6px" }}>
                                                <div style={{ display: "grid", gridTemplateColumns: "1fr auto 1fr", alignItems: "center", gap: "8px" }}>
                                                  <div style={{
                                                    fontSize: "0.72rem", color: "#94a3b8", fontFamily: "'JetBrains Mono', monospace",
                                                    textDecoration: statusText.toUpperCase().includes("CHANGE") || statusText.toUpperCase().includes("REMOVE") || statusText.toUpperCase().includes("MIS") ? "line-through" : "none",
                                                    whiteSpace: "nowrap", overflowX: "hidden", textOverflow: "ellipsis"
                                                  }}>
                                                    {row.original || "-"}
                                                  </div>
                                                  <span style={{ color: "rgba(255,255,255,0.25)", fontSize: "0.75rem" }}>➔</span>
                                                  <div style={{
                                                    fontSize: "0.72rem", color: "#e2e8f0", fontFamily: "'JetBrains Mono', monospace",
                                                    fontWeight: 500, whiteSpace: "nowrap", overflowX: "hidden", textOverflow: "ellipsis"
                                                  }}>
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
                                      <div style={{ background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.06)", padding: "10px", borderRadius: "6px" }}>
                                        <div style={{ fontSize: "0.65rem", fontWeight: 700, color: "var(--text-muted)", marginBottom: "6px" }}>Original Drawing</div>
                                        <div style={{ fontSize: "0.78rem", color: "#94a3b8", whiteSpace: "pre-wrap", maxHeight: "150px", overflowY: "auto", fontFamily: "monospace" }}>
                                          {result.reference_content || "-"}
                                        </div>
                                      </div>
                                      <div style={{ background: "rgba(0,229,255,0.01)", border: "1px solid rgba(0,229,255,0.1)", padding: "10px", borderRadius: "6px" }}>
                                        <div style={{ fontSize: "0.65rem", fontWeight: 700, color: "var(--accent-cyan)", marginBottom: "6px" }}>KMTI Drawing</div>
                                        <div style={{ fontSize: "0.78rem", color: "#e2e8f0", whiteSpace: "pre-wrap", maxHeight: "150px", overflowY: "auto", fontFamily: "monospace" }}>
                                          {result.revision_content || "-"}
                                        </div>
                                      </div>
                                    </div>
                                  </div>
                                );
                              }
                            })()}

                            {result.engineering_discrepancy_details && (
                              <div>
                                <div style={{ fontSize: "0.8rem", fontWeight: 600, color: "var(--accent-cyan)", marginBottom: "6px" }}>ENGINEERING DISCREPANCY DETAILS</div>
                                <div style={{
                                  fontSize: "0.85rem",
                                  color: result.status === "MATCHED" ? "#a7f3d0" : "#fecaca",
                                  background: result.status === "MATCHED" ? "rgba(16,185,129,0.06)" : "rgba(239,68,68,0.06)",
                                  borderLeft: `4px solid ${badgeColor}`,
                                  padding: "8px 12px",
                                  borderRadius: "0 6px 6px 0",
                                  lineHeight: "1.5"
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

      {/* 2. CENTER STAGE AND DUAL stage */}
      {currentNav === "workspace" && (
        <div className="dual-stage-layout" style={{ flexGrow: 1, minWidth: 0 }}>
          {/* CENTER VIEWPORT (STAGE 1: COPY-TRACE COMPARISON ENGINE) */}
          <main className="stage1-center-panel" style={{ flexGrow: 1 }}>
            <div className="cad-viewer-container">
              <div className="viewer-toolbar" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", width: "100%", padding: "8px 16px" }}>
                <div style={{ display: "flex", alignItems: "center" }}>
                  <h3 className="card-title" style={{ margin: 0, fontSize: "0.85rem", color: "var(--accent-cyan)", borderLeft: "3px solid var(--accent-cyan)", paddingLeft: "8px" }}>
                    Stage 1: Drawing Pair Ingestion
                  </h3>
                </div>

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

              <div className="split-viewports">
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
                        currentNav={currentNav}
                      />
                    )}
                  </div>
                </div>

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
                        currentNav={currentNav}
                      />
                    )}
                  </div>
                </div>
              </div>
            </div>
          </main>

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

      {currentNav === "3d-workspace" && (
        <div className="dual-stage-layout 3d-layout" style={{ flexGrow: 1, minWidth: 0 }}>
          <main className="stage1-center-panel" style={{ display: "flex", flexDirection: "column", position: "relative" }}>
            <div className="card settings-card upload-station-card" style={{ marginBottom: "12px", padding: "10px 16px", zIndex: 10 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", width: "100%", gap: "16px", flexWrap: "wrap" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
                  <h3 className="card-title" style={{ margin: 0, fontSize: "0.85rem", borderLeft: "3px solid var(--accent-cyan)", paddingLeft: "8px" }}>
                    Stage 1: 3D Model Checking Ingestion
                  </h3>
                  
                  {newDrawing && (
                    <span className="format-badge-pill rev-format" style={{ background: "rgba(168, 85, 247, 0.15)", border: "1px solid rgba(168, 85, 247, 0.3)", color: "#c084fc", fontSize: "0.75rem", padding: "4px 8px", borderRadius: "6px" }}>
                      ACTIVE 3D: {newDrawing.file_name}
                    </span>
                  )}
                </div>
              </div>
            </div>

            <div className="cad-viewer-container" style={{ flexGrow: 1, display: "flex", flexDirection: "column", minHeight: "500px", position: "relative", borderRadius: "12px", overflow: "hidden", border: "1px solid rgba(255,255,255,0.05)" }}>
              <div style={{ position: "absolute", top: 0, left: 0, width: "100%", height: "100%", zIndex: 1 }} ref={containerRefNew}>
                <ThreeDViewer
                  drawing={newDrawing}
                  width={newSize.width}
                  height={newSize.height}
                />
              </div>

              {(!newDrawing || !["step", "stp", "iges", "igs", "icd", "sldprt", "sldasm"].includes(newDrawing?.format?.toLowerCase() || "")) && (
                <div style={{
                  position: "absolute",
                  top: 0, left: 0, width: "100%", height: "100%",
                  zIndex: 5,
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  justifyContent: "center",
                  background: "rgba(9, 9, 11, 0.65)",
                  backdropFilter: "blur(8px)"
                }}>
                  <div style={{ width: "400px", background: "rgba(255,255,255,0.03)", padding: "30px", borderRadius: "16px", border: "1px solid rgba(255,255,255,0.08)", boxShadow: "0 20px 40px rgba(0,0,0,0.4)" }}>
                    <h2 style={{ textAlign: "center", color: "#e4e4e7", fontSize: "1.2rem", marginBottom: "20px" }}>3D Model Ingestion</h2>
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
                      currentNav={currentNav}
                    />
                    
                    <div style={{ marginTop: "20px", display: "flex", justifyContent: "center" }}>
                      <button
                        onClick={() => {
                          const store = useWorkspaceStore.getState();
                          store.setNewDrawing({
                            id: "demo_step_3d",
                            file_name: "bracket_v2_machined.step",
                            format: "step",
                            file_path: "uploads/demo_step_3d.step",
                            entity_counts: { FACE: 42, SOLID: 1 },
                            metadata: { face_count: 42, volume_mm3: 27100, surface_area_mm2: 6500, bounds_min: [-40, -40, -40], bounds_max: [40, 40, 40] },
                            created_at: new Date().toISOString()
                          });
                          useWorkspaceStore.setState({
                            compatibilityStatus: "Compatible",
                            violations: [
                              {
                                id: "v_3d_01",
                                severity: "high",
                                category: "Dimensional Tolerance",
                                description: "Pillar height exceeds maximum mounting footprint by 1.2mm in Z-axis.",
                                recommendation: "Reduce vertical pillar extrusion to match bracket specification standard.",
                                confidence: 0.94,
                                standard_reference: "ISO-2768-m",
                                affected_entities: []
                              },
                              {
                                id: "v_3d_02",
                                severity: "medium",
                                category: "Feature Clearance",
                                description: "Counterbore depth leaves thin wall thickness of 0.85mm at bottom face.",
                                recommendation: "Increase bottom pocket wall thickness to at least 1.50mm to prevent shear cracking.",
                                confidence: 0.87,
                                standard_reference: "ASME Y14.5",
                                affected_entities: []
                              }
                            ],
                            complianceScore: 85,
                            auditStatus: "completed"
                          });
                        }}
                        className="btn btn-secondary"
                        style={{
                          padding: "8px 16px",
                          fontSize: "0.85rem",
                          background: "rgba(168, 85, 247, 0.15)",
                          border: "1px solid rgba(168, 85, 247, 0.3)",
                          color: "#c084fc",
                          cursor: "pointer",
                          borderRadius: "8px",
                          display: "flex",
                          alignItems: "center",
                          gap: "6px",
                          width: "100%",
                          justifyContent: "center",
                          transition: "all 0.2s"
                        }}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.background = "rgba(168, 85, 247, 0.25)";
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.background = "rgba(168, 85, 247, 0.15)";
                        }}
                      >
                        <RotateCcw size={14} />
                        Load 3D STEP Demo
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </main>

          <aside className={`stage2-right-panel ${isRightPanelCollapsed ? "collapsed" : ""}`}>
            <button
              className="panel-collapse-btn"
              onClick={() => setIsRightPanelCollapsed(!isRightPanelCollapsed)}
              title={isRightPanelCollapsed ? "Expand AI Explanations" : "Collapse AI Explanations"}
            >
              {isRightPanelCollapsed ? <ChevronLeft size={16} /> : <ChevronRight size={16} />}
            </button>
            <div className="panel-content-wrapper" style={{ display: "flex", flexDirection: "column", height: "100%" }}>
              <div className="card settings-card" style={{ marginBottom: "20px" }}>
                <h3 className="card-title" style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                  <Sparkles size={16} style={{ color: "var(--accent-cyan)" }} />
                  Stage 2 AI 3D Compliance Auditor
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
                    padding: "10px 16px"
                  }}
                >
                  <Play size={14} fill="currentColor" />
                  <span>
                    {auditStatus === "queued" || auditStatus === "auditing" ? "Analyzing 3D Topology..." : "Execute 3D Compliance Audit"}
                  </span>
                </button>
              </div>

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

              <div className="violations-feed-card card settings-card" style={{ flexGrow: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
                <h4 className="card-title">AI Geometrical Infractions & peer checking</h4>
                
                <div className="violations-list" style={{ overflowY: "auto", flexGrow: 1, marginTop: "16px", display: "flex", flexDirection: "column", gap: "12px" }}>
                  {auditStatus === "idle" && (
                    <div className="empty-state">Trigger 3D compliance run to check mechanical alignment against manufacturing standards.</div>
                  )}
                  
                  {auditStatus === "queued" || auditStatus === "auditing" ? (
                    <div className="empty-state">
                      <div className="loader spin-animation"></div>
                      <span style={{ marginTop: "12px" }}>Evaluating counterbore & step tolerances...</span>
                    </div>
                  ) : null}

                  {auditStatus === "completed" && violations.length === 0 ? (
                    <div className="empty-state success">
                      <CheckCircle2 size={36} style={{ color: "#10b981" }} />
                      <span style={{ marginTop: "12px", color: "#10b981" }}>No compliance infractions found in 3D model!</span>
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
                        <strong>AI Fix Chip:</strong> {v.recommendation}
                      </div>

                      <div className="card-footer-row">
                        <span className="confidence-badge">Confidence: {(v.confidence * 100).toFixed(0)}%</span>
                        <span className="focus-action-btn">Highlight coordinates →</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </aside>
        </div>
      )}
    </div>
  );
};
