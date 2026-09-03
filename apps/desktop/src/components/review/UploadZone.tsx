import React from "react";
import { AlertTriangle } from "lucide-react";
import { DrawingItem, UploadState } from "../../stores/workspaceStore";
import { SquareAccordion } from "../ui/LoadingOverlay";

export interface UploadZoneProps {
  side: "old" | "new";
  uploadState: UploadState;
  progress: number;
  fileName: string | null;
  fileSize: number | null;
  error: string | null;
  activeDrawing: DrawingItem | null;
  uploadDrawingFile: (file: File, side: "old" | "new") => Promise<boolean>;
  clearUpload: (side: "old" | "new") => void;
  currentNav: string;
}

export const UploadZone: React.FC<UploadZoneProps> = ({
  side,
  uploadState,
  progress,
  fileName,
  error,
  uploadDrawingFile,
  currentNav,
}) => {
  const [isDragActive, setIsDragActive] = React.useState(false);
  const fileInputRef = React.useRef<HTMLInputElement>(null);

  const [elapsed, setElapsed] = React.useState(0);
  const [tipIndex, setTipIndex] = React.useState(0);

  const ingestSteps = [
    "Parsing File Structure",
    "Extracting Vector Entities",
    "Normalizing Coordinates",
    "Building Spatial Index",
    "Finalizing Ingestion",
  ];

  React.useEffect(() => {
    let elapsedInterval: any;
    let tipInterval: any;
    if (uploadState === "processing") {
      elapsedInterval = setInterval(() => {
        setElapsed((prev) => prev + 1);
      }, 1000);
      tipInterval = setInterval(() => {
        setTipIndex((prev) => (prev + 1) % ingestSteps.length);
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

  const borderHover =
    side === "old"
      ? "hover:bg-blue-500/1 hover:border-blue-500/15"
      : "hover:bg-purple-500/1 hover:border-purple-500/15";

  let draggingStyles = "";
  if (isDragActive) {
    draggingStyles =
      side === "old"
        ? "border-accent-cyan bg-blue-500/5 shadow-[inset_0_0_10px_rgba(37,99,235,0.1)] data-[theme=hc-dark]:bg-accent-cyan/6"
        : "border-purple-500 bg-purple-500/5 shadow-[inset_0_0_10px_rgba(139,92,246,0.1)] data-[theme=hc-dark]:border-purple-400 data-[theme=hc-dark]:bg-purple-500/6";
  }

  const containerClass = `relative w-full h-full transition-all duration-250 ease-out flex flex-col items-center justify-center p-5 box-border overflow-hidden bg-transparent group ${borderHover}`;

  const dropzoneBoxClass = `w-full flex flex-col items-center text-center gap-2.5 py-6 px-4 rounded-sm border border-dashed border-border-color transition-all duration-150 ${draggingStyles}`;

  return (
    <div
      className={containerClass}
      data-tour={side === "old" ? "upload-reference" : "upload-revision"}
      role="button"
      tabIndex={0}
      aria-label="File Upload Dropzone"
      onDragEnter={handleDrag}
      onDragOver={handleDrag}
      onDragLeave={handleDrag}
      onDrop={handleDrop}
      onClick={canInteract ? triggerFileInput : undefined}
      onKeyDown={canInteract ? (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          triggerFileInput();
        }
      } : undefined}
      style={{ cursor: canInteract ? "pointer" : "default" }}
    >
      <input
        ref={fileInputRef}
        type="file"
        style={{ display: "none" }}
        onChange={handleFileChange}
        accept={
          currentNav === "3d-workspace"
            ? ".step,.stp,.iges,.igs,.icd,.sldprt,.sldasm"
            : ".pdf,.dwg,.dxf"
        }
      />

      {uploadState === "idle" && (
        <div className="flex flex-col items-center text-center gap-4 w-full max-w-[380px]">
          <div className={dropzoneBoxClass}>
            <div
              className={`w-9 h-9 rounded-full bg-sidebar-item-hover border border-border-color flex items-center justify-center text-text-muted transition-all duration-250 group-hover:-translate-y-0.5 ${
                side === "old"
                  ? "group-hover:border-accent-cyan group-hover:text-accent-cyan group-hover:bg-blue-600/6"
                  : "group-hover:border-purple-500 group-hover:text-purple-400 group-hover:bg-purple-500/6"
              }`}
            >
              <svg
                style={{ width: "14px", height: "14px" }}
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
              >
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12" />
              </svg>
            </div>
            <p className="text-xs font-semibold text-text-primary m-0">
              Drag & drop or{" "}
              <span
                className={
                  side === "old"
                    ? "text-accent-cyan underline font-bold"
                    : "text-purple-400 underline font-bold"
                }
              >
                browse
              </span>
            </p>
            <p className="text-xs text-text-muted font-medium">
              {currentNav === "3d-workspace"
                ? "STEP · IGES · ICD · SolidWorks"
                : "DWG · DXF · PDF"}
            </p>
          </div>
        </div>
      )}

      {uploadState === "uploading" && (
        <div className="flex flex-col items-center text-center gap-3.5 w-full max-w-[320px]">
          <div className="flex items-center justify-center">
            <SquareAccordion size={4} cellSize={18} />
          </div>

          <div className="flex flex-col items-center gap-1 w-full">
            <span className="text-xs font-bold text-text-primary uppercase tracking-wider">
              Uploading Drawing…
            </span>
            {fileName && (
              <span className="text-xs font-mono text-text-muted truncate max-w-[280px]">
                {fileName}
              </span>
            )}
          </div>

          <div className="w-full max-w-[280px] flex flex-col gap-1.5 mt-1">
            <div className="flex justify-between items-center text-[11px] font-mono">
              <span className="text-text-muted uppercase tracking-wider">Network Transfer</span>
              <span className="font-bold text-accent-cyan ml-2 shrink-0">{progress}%</span>
            </div>
            <div className="w-full h-1 bg-border-color/60 rounded-xs overflow-hidden">
              <div
                className="h-full bg-accent-cyan transition-all duration-300 ease-out"
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>
        </div>
      )}

      {(uploadState === "processing" || uploadState === "validating") && (
        <div className="flex flex-col items-center text-center gap-3.5 w-full max-w-[320px]">
          <div className="flex items-center justify-center">
            <SquareAccordion size={4} cellSize={18} />
          </div>

          <div className="flex flex-col items-center gap-1 w-full">
            <span className="text-xs font-bold text-text-primary uppercase tracking-wider">
              {uploadState === "validating" ? "Validating Drawing…" : "Processing Drawing…"}
            </span>
            {fileName && (
              <span className="text-xs font-mono text-text-muted truncate max-w-[280px]">
                {fileName}
              </span>
            )}
          </div>

          <div className="w-full max-w-[280px] flex flex-col gap-1.5 mt-1">
            <div className="flex justify-between items-center text-[11px] font-mono">
              <span className="text-text-muted uppercase tracking-wider truncate">
                {uploadState === "validating" ? "Validating Output" : ingestSteps[tipIndex]}
              </span>
              <span className="font-bold text-accent-cyan ml-2 shrink-0">
                {Math.min(99, Math.floor(100 - (100 / (1 + elapsed * 0.1))))}%
              </span>
            </div>
            <div className="w-full h-1 bg-border-color/60 rounded-xs overflow-hidden">
              <div
                className="h-full bg-accent-cyan transition-all duration-500 ease-out"
                style={{ width: `${Math.min(99, Math.floor(100 - (100 / (1 + elapsed * 0.1))))}%` }}
              />
            </div>
          </div>
        </div>
      )}

      {uploadState === "failed" && (
        <div className="flex flex-col items-center text-center gap-3 w-full max-w-[320px]">
          <div className="w-8 h-8 rounded-sm bg-red-500/10 border border-red-500/30 flex items-center justify-center text-red-500">
            <AlertTriangle size={18} />
          </div>

          <div className="flex flex-col items-center gap-1 w-full">
            <span className="text-xs font-bold text-text-primary uppercase tracking-wider">
              Ingestion Failed
            </span>
            <p className="text-xs text-red-500/90 leading-relaxed m-0 max-w-[280px]">
              {error || "An unknown error occurred while parsing vector entities."}
            </p>
          </div>

          <button
            type="button"
            className="mt-1 text-[11px] font-semibold px-3 py-1 rounded-sm border border-border-color bg-bg-sidebar text-text-primary hover:border-accent-cyan hover:text-accent-cyan transition-all cursor-pointer"
            onClick={(e) => {
              e.stopPropagation();
              triggerFileInput();
            }}
          >
            Try Another File
          </button>
        </div>
      )}
    </div>
  );
};
