import { invoke } from "@tauri-apps/api/core";

export interface CadToolsStatus {
  icad_dxf_available: boolean;
  icad_step_available: boolean;
  oda_available: boolean;
  icad_dir: string | null;
  oda_path: string | null;
}

export interface ConversionOutput {
  success: boolean;
  original_path: string;
  original_name: string;
  dxf_path: string | null;
  step_path: string | null;
  error: string | null;
}

export interface ConvertedFiles {
  dxfFile: File;
  companionStepFile?: File;
  originalName: string;
  sourceFormat: "icd" | "dwg";
}

export const isTauri = (): boolean =>
  typeof window !== "undefined" && !!(window as any).__TAURI_INTERNALS__;

export async function checkCadToolsAvailable(): Promise<CadToolsStatus | null> {
  if (!isTauri()) return null;
  try {
    return await invoke<CadToolsStatus>("check_cad_tools_available");
  } catch (err) {
    console.warn("Failed to check CAD tools status:", err);
    return null;
  }
}

/**
 * Converts a local .icd or .dwg file using workstation-installed iCAD SX / ODA tools.
 * Returns standard File instances ready for HTTP multipart upload to the backend.
 */
export async function convertLocalCadFile(
  input: string | File,
  onProgress?: (stage: string) => void
): Promise<ConvertedFiles> {
  if (!isTauri()) {
    throw new Error("Client-side CAD conversion is only available in the DraftCheck desktop application.");
  }

  let filePath = typeof input === "string" ? input : (input as any).path as string | undefined;
  let rawFileName = typeof input === "string" 
    ? input.replace(/\\/g, "/").split("/").pop() || "drawing"
    : input.name;
  const ext = rawFileName.split(".").pop()?.toLowerCase();
  const stem = rawFileName.substring(0, rawFileName.lastIndexOf(".")) || rawFileName;

  let result: ConversionOutput;

  if (filePath) {
    if (ext === "icd") {
      onProgress?.("Running local iCAD SX conversion...");
      result = await invoke<ConversionOutput>("convert_local_icd", { inputPath: filePath });
    } else if (ext === "dwg") {
      onProgress?.("Running local ODA DWG conversion...");
      result = await invoke<ConversionOutput>("convert_local_dwg", { inputPath: filePath });
    } else {
      throw new Error(`Unsupported CAD conversion format: .${ext}`);
    }
  } else if (typeof input !== "string") {
    // If no direct file path (e.g. dropped file in browser sandbox), pass bytes to staging
    onProgress?.("Staging file for local conversion...");
    const buffer = await input.arrayBuffer();
    const bytes = Array.from(new Uint8Array(buffer));
    result = await invoke<ConversionOutput>("convert_local_bytes", { fileName: rawFileName, bytes });
  } else {
    throw new Error("Invalid CAD file input for conversion.");
  }

  if (ext === "icd") {

    if (!result.success || !result.dxf_path) {
      throw new Error(result.error || "iCAD SX conversion produced no DXF drawing.");
    }

    onProgress?.("Reading converted 2D drawing linework...");
    const dxfBytes = await invoke<number[]>("read_converted_file", { path: result.dxf_path });
    const dxfFile = new File([new Uint8Array(dxfBytes)], `${stem}.dxf`, { type: "application/dxf" });

    let companionStepFile: File | undefined;
    if (result.step_path) {
      try {
        onProgress?.("Reading converted 3D model geometry...");
        const stepBytes = await invoke<number[]>("read_converted_file", { path: result.step_path });
        companionStepFile = new File([new Uint8Array(stepBytes)], `${stem}.stp`, { type: "application/step" });
      } catch (e) {
        console.warn("Failed to read companion STEP file:", e);
      }
    }

    // Clean up temporary local converted files asynchronously
    void invoke("cleanup_converted_file", { path: result.dxf_path }).catch(() => {});
    if (result.step_path) {
      void invoke("cleanup_converted_file", { path: result.step_path }).catch(() => {});
    }

    return {
      dxfFile,
      companionStepFile,
      originalName: rawFileName,
      sourceFormat: "icd",
    };

  } else if (ext === "dwg") {
    if (!result.success || !result.dxf_path) {
      throw new Error(result.error || "ODA File Converter produced no DXF drawing.");
    }

    onProgress?.("Reading converted DXF drawing...");
    const dxfBytes = await invoke<number[]>("read_converted_file", { path: result.dxf_path });
    const dxfFile = new File([new Uint8Array(dxfBytes)], `${stem}.dxf`, { type: "application/dxf" });

    void invoke("cleanup_converted_file", { path: result.dxf_path }).catch(() => {});

    return {
      dxfFile,
      originalName: rawFileName,
      sourceFormat: "dwg",
    };

  } else {
    throw new Error(`Unsupported CAD conversion format: .${ext}`);
  }
}
