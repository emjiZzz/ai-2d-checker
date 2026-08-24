import React from "react";
import { Loader, AlertTriangle } from "lucide-react";
import { DrawingItem, UploadState } from "../../stores/workspaceStore";

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
        <div className="w-full flex flex-col items-center text-center p-8">
          <div className="relative w-16 h-16 rounded-full bg-bg-dark border border-border-color flex items-center justify-center mb-6 shadow-lg">
            <Loader className="spin-animation text-accent-cyan" size={24} />
          </div>
          <div className="flex flex-col items-center gap-1.5 w-full max-w-[320px] mb-6">
            <span className="text-base font-bold text-zinc-100">Uploading CAD Draft...</span>
            <span className="text-sm text-zinc-400 truncate w-full">{fileName}</span>
          </div>
          
          <div className="w-full max-w-[320px]">
            <div className="flex justify-between items-center mb-2">
              <span className="text-xs font-bold text-zinc-500 uppercase tracking-widest">Network Transfer</span>
              <span className="text-xs font-mono font-bold text-accent-cyan">{progress}%</span>
            </div>
            <div className="w-full h-2 bg-sidebar-item-hover rounded-full overflow-hidden border border-border-color">
              <div
                className="h-full bg-accent-cyan transition-all duration-300 shadow-[0_0_10px_rgba(0,229,255,0.4)]"
                style={{ width: `${progress}%` }}
              ></div>
            </div>
          </div>
        </div>
      )}

      {(uploadState === "processing" || uploadState === "validating") && (
        <div className="w-full flex flex-col items-center text-center p-8">
          <div className="relative w-16 h-16 rounded-full bg-bg-dark border border-border-color flex items-center justify-center mb-6 shadow-lg">
            <Loader className="spin-animation text-accent-cyan" size={24} />
          </div>
          <div className="flex flex-col items-center gap-1.5 w-full max-w-[320px] mb-6">
            <span className="text-base font-bold text-zinc-100">
              {uploadState === "validating" ? "Validating Drawing..." : "Processing File..."}
            </span>
            <span className="text-sm text-zinc-400 truncate w-full">{fileName}</span>
          </div>
          
          <div className="w-full max-w-[320px]">
            <div className="flex justify-between items-center mb-2">
              <span className="text-xs font-bold text-zinc-500 uppercase tracking-widest">
                {uploadState === "validating" ? "Validating Output" : ingestSteps[tipIndex]}
              </span>
              <span className="text-xs font-mono font-bold text-accent-cyan">
                {Math.min(99, Math.floor(100 - (100 / (1 + elapsed * 0.1))))}%
              </span>
            </div>
            <div className="w-full h-2 bg-sidebar-item-hover rounded-full overflow-hidden border border-border-color">
              <div
                className="h-full bg-accent-cyan transition-all duration-1000 ease-linear shadow-[0_0_10px_rgba(0,229,255,0.4)]"
                style={{ width: `${Math.min(99, Math.floor(100 - (100 / (1 + elapsed * 0.1))))}%` }}
              ></div>
            </div>
          </div>
        </div>
      )}

      {uploadState === "failed" && (
        <div className="w-full flex flex-col items-center text-center p-8 relative">
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-48 h-48 bg-red-500/10 rounded-full blur-[60px] pointer-events-none"></div>
          
          <div className="relative w-16 h-16 rounded-full bg-bg-dark border border-red-500/30 flex items-center justify-center mb-5 shadow-lg text-red-500">
            <AlertTriangle size={28} />
          </div>
          
          <h3 className="text-xl font-bold text-zinc-100 tracking-tight mb-2 relative z-10">
            Ingestion Failed
          </h3>
          
          <div className="relative z-10 w-full max-w-[340px] bg-red-950/30 border border-red-500/20 rounded-xl p-4 shadow-xl backdrop-blur-sm mb-5">
            <p className="text-sm text-red-200 leading-relaxed m-0 font-medium">
              {error || "An unknown ingestion pipeline error occurred. Please verify your vector formats."}
            </p>
          </div>

          <div 
            className="relative z-10 text-sm font-bold bg-transparent border border-red-500/40 text-red-400 hover:bg-red-500 hover:border-red-500 hover:text-white px-6 py-2 rounded-md transition-all cursor-pointer shadow-lg"
            onClick={(e) => { e.stopPropagation(); triggerFileInput(); }}
          >
            Try Another File
          </div>
        </div>
      )}
    </div>
  );
};
