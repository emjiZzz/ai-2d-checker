import React from "react";
import { Loader, Sparkles, BookOpen } from "lucide-react";
import { DrawingItem, UploadState } from "../../stores/workspaceStore";
import { DrawingLibraryPicker } from "./DrawingLibraryPicker";

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
  const [showLibraryPicker, setShowLibraryPicker] = React.useState(false);
  const fileInputRef = React.useRef<HTMLInputElement>(null);

  const [elapsed, setElapsed] = React.useState(0);
  const [tipIndex, setTipIndex] = React.useState(0);

  const tips = [
    "Delaunay Mesher: Generating 3D surface mesh nodes...",
    "Stitching B-Rep boundary curves & topological vertices...",
    "Mapping harmonize color groups and materials...",
    "Integrating solid body volume & mass attributes...",
    "Deducing geometric tolerances from model structure...",
  ];

  React.useEffect(() => {
    let elapsedInterval: any;
    let tipInterval: any;
    if (uploadState === "processing") {
      elapsedInterval = setInterval(() => {
        setElapsed((prev) => prev + 1);
      }, 1000);
      tipInterval = setInterval(() => {
        setTipIndex((prev) => (prev + 1) % tips.length);
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

  const containerClass = `relative w-full h-full transition-all duration-250 ease-out flex flex-col items-center justify-center p-5 box-border overflow-hidden bg-transparent border border-dashed border-white/5 data-[theme=hc-light]:border-black/5 group ${borderHover} ${draggingStyles}`;

  return (
    <div
      className={containerClass}
      role="button"
      tabIndex={0}
      aria-label="File Upload Dropzone"
      onDragEnter={handleDrag}
      onDragOver={handleDrag}
      onDragLeave={handleDrag}
      onDrop={handleDrop}
      onClick={canInteract ? (e) => {
        if ((e.target as HTMLElement).closest('[data-no-file-trigger]')) return;
        triggerFileInput();
      } : undefined}
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
        <div className="flex flex-col items-center text-center gap-3">
          <div
            className={`w-8 h-8 rounded-full bg-white/2 border border-border-color flex items-center justify-center text-text-muted transition-all duration-250 group-hover:-translate-y-0.5 ${
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
          <p className="text-xs text-text-muted mt-1">
            {currentNav === "3d-workspace"
              ? "STEP, IGES, ICD, SolidWorks (No size limit)"
              : "DWG, DXF, PDF (No size limit)"}
          </p>
          <div 
            data-no-file-trigger
            className="mt-2 text-xs flex items-center justify-center gap-1.5 py-1.5 px-3 rounded-full border border-border-color bg-bg-sidebar text-text-primary hover:border-accent-cyan hover:text-accent-cyan transition-colors"
            onClick={(e) => {
              e.stopPropagation();
              setShowLibraryPicker(true);
            }}
          >
            <BookOpen size={12} /> Select from Library
          </div>
        </div>
      )}

      {showLibraryPicker && (
        <DrawingLibraryPicker 
          side={side} 
          onClose={() => setShowLibraryPicker(false)} 
        />
      )}

      {uploadState === "uploading" && (
        <div className="w-full flex flex-col items-center text-center p-2.5">
          <div className="w-8 h-8 rounded-full bg-bg-dark border border-border-color flex items-center justify-center mb-2.5 text-accent-cyan animate-pulse shadow-[0_0_12px_rgba(0,229,255,0.25)]">
            <Loader className="spin-animation loader-icon" size={14} />
          </div>
          <div className="flex flex-col mb-3">
            <span className="text-xs font-bold text-text-primary">
              Uploading CAD Draft ({progress}%)
            </span>
            <span className="text-xs text-text-muted truncate max-w-[240px]">
              {fileName}
            </span>
          </div>
          <div className="w-full h-1 bg-white/5 rounded-full overflow-hidden">
            <div
              className="h-full bg-accent-cyan rounded-full transition-all duration-300"
              style={{ width: `${progress}%` }}
            ></div>
          </div>
        </div>
      )}

      {(uploadState === "processing" || uploadState === "validating") && (
        <div className="w-full flex flex-col items-center text-center p-2.5">
          <div className="w-8 h-8 rounded-full bg-bg-dark border border-border-color flex items-center justify-center mb-2.5 text-accent-cyan animate-pulse shadow-[0_0_12px_rgba(0,229,255,0.25)]">
            <Loader className="spin-animation loader-icon" size={14} />
          </div>
          <div className="flex flex-col mb-3">
            <span className="text-xs font-bold text-text-primary">
              {uploadState === "validating"
                ? "Reconstructing Vector Entities..."
                : "Aligning Geometrical Checkpoints..."}
            </span>
            <span className="text-xs text-text-muted truncate max-w-[240px]">
              {fileName}
            </span>
            <span
              className="text-xs text-text-muted truncate max-w-[240px]"
              style={{ marginTop: "4px", opacity: 0.8 }}
            >
              Elapsed: {elapsed}s
            </span>
          </div>
          <div className="mt-2.5 bg-white/2 py-1.5 px-3 rounded-md border border-border-color flex items-center gap-1.5">
            <Sparkles size={11} className="tip-sparkle-icon" />
            <span className="text-[11px] text-text-muted">{tips[tipIndex]}</span>
          </div>
        </div>
      )}

      {uploadState === "failed" && (
        <div className="flex flex-col items-center text-center p-2.5 gap-2.5">
          <div className="w-8 h-8 rounded-full bg-red-500/10 border border-red-500/30 flex items-center justify-center text-red-500 font-extrabold text-sm animate-bounce">
            !
          </div>
          <span className="text-xs font-bold text-red-400">
            Pipeline Processing Failure
          </span>
          <p className="text-[11px] text-text-muted max-w-[280px] leading-relaxed m-0">
            {error ||
              "An unknown ingestion pipeline error occurred. Please verify your vector formats."}
          </p>
          <span
            className="text-accent-cyan underline font-bold cursor-pointer hover:brightness-110 text-[11px] mt-1"
            onClick={triggerFileInput}
          >
            Retry browse
          </span>
        </div>
      )}
    </div>
  );
};
