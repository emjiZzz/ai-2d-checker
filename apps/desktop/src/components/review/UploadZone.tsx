import React from "react";
import { AlertTriangle } from "lucide-react";
import { DrawingItem, UploadState } from "../../stores/workspaceStore";
import { SquareAccordion } from "../ui/LoadingOverlay";
import { DRAWING_FORMATS, MODEL_3D_FORMATS } from "../../config/drawingFormats";

export interface UploadZoneProps {
  side: "old" | "new";
  uploadState: UploadState;
  progress: number;
  fileName: string | null;
  fileSize: number | null;
  error: string | null;
  activeDrawing: DrawingItem | null;
  /** The drawing to re-extract, when the row exists and only its extraction failed. */
  failedDrawingId?: string | null;
  retryExtraction?: (side: "old" | "new") => Promise<boolean>;
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
  failedDrawingId,
  retryExtraction,
  uploadDrawingFile,
  currentNav,
}) => {
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

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      await uploadDrawingFile(e.target.files[0], side);
    }
  };

  const canInteract = uploadState === "idle" || uploadState === "failed";
  const isTauri = typeof window !== "undefined" && !!(window as any).__TAURI_INTERNALS__;

  const triggerFileInput = async () => {
    if (!canInteract) return;
    if (isTauri) {
      try {
        const { open } = await import("@tauri-apps/plugin-dialog");
        const selected = await open({
          multiple: false,
          directory: false,
          filters: [
            {
              name: "CAD Drawings",
              extensions: [
                ...(currentNav === "3d-workspace"
                  ? [...MODEL_3D_FORMATS, "icd"]
                  : DRAWING_FORMATS),
              ],
            },
          ],
        });
        if (selected && typeof selected === "string") {
          const rawFileName = selected.replace(/\\/g, "/").split("/").pop() || "drawing";
          const fileObj = new File([], rawFileName);
          Object.defineProperty(fileObj, "path", { value: selected });
          await uploadDrawingFile(fileObj, side);
          return;
        }
      } catch (err) {
        console.warn("Native file dialog failed, falling back to input:", err);
      }
    }
    fileInputRef.current?.click();
  };

  const containerClass = `relative w-full h-full flex flex-col items-center justify-center p-5 box-border overflow-hidden bg-transparent`;

  return (
    <div
      className={containerClass}
      data-tour={side === "old" ? "upload-reference" : "upload-revision"}
      role="region"
      aria-label="Upload Drawing"
    >
      <input
        ref={fileInputRef}
        type="file"
        style={{ display: "none" }}
        onChange={handleFileChange}
        accept={
          // From the shared lists, so the picker cannot drift from what upload validation
          // accepts. It only filtered to `.dxf` here, which hid every `.icd` in the dialog
          // and left drag-and-drop as the only way to put one in a room.
          currentNav === "3d-workspace"
            ? [...MODEL_3D_FORMATS, "icd"].map((f) => `.${f}`).join(",")
            : DRAWING_FORMATS.map((f) => `.${f}`).join(",")
        }
      />

      {uploadState === "idle" && (
        <div className="flex flex-col items-center text-center gap-4 w-full max-w-[380px]">
          <div
            className="w-full flex flex-col items-center text-center gap-3 py-6 px-4 rounded-sm border border-dashed border-text-muted/70 hover:border-text-primary hover:bg-sidebar-item-hover/40 transition-all duration-150 cursor-pointer select-none"
            onClick={triggerFileInput}
            role="button"
            tabIndex={0}
            aria-label="Browse and upload CAD file"
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                triggerFileInput();
              }
            }}
          >
            <svg
              className="w-7 h-7 text-text-primary transition-transform duration-150"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.75"
            >
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12" />
            </svg>
            <p className="text-xs font-semibold text-text-primary m-0">
              Browse and upload
            </p>
            <p className="text-xs text-text-muted font-medium m-0">
              {currentNav === "3d-workspace"
                ? "STEP · IGES · ICD · SolidWorks"
                : "DXF"}
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

          <div className="flex items-center gap-2 mt-1">
            {/*
              Retry before re-upload, and only when there is a row to retry. Re-uploading the
              same file makes a SECOND drawing -- dedupe is deliberately gone -- which is how one
              sheet became four rows with its markings split across them. `/reextract` keeps the
              id, the room slot and the history.
            */}
            {failedDrawingId && retryExtraction && (
              <button
                type="button"
                className="text-[11px] font-semibold px-3 py-1 rounded-sm border border-accent-cyan/50 bg-accent-cyan/10 text-accent-cyan hover:bg-accent-cyan/20 transition-all cursor-pointer"
                onClick={(e) => {
                  e.stopPropagation();
                  void retryExtraction(side);
                }}
              >
                Retry Extraction
              </button>
            )}
            <button
              type="button"
              className="text-[11px] font-semibold px-3 py-1 rounded-sm border border-border-color bg-bg-sidebar text-text-primary hover:border-accent-cyan hover:text-accent-cyan transition-all cursor-pointer"
              onClick={(e) => {
                e.stopPropagation();
                triggerFileInput();
              }}
            >
              Try Another File
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
