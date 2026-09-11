import { describe, it, expect, vi, beforeEach } from "vitest";
import { checkCadToolsAvailable, convertLocalCadFile } from "./localCadConverter";

const mockInvoke = vi.fn();
vi.mock("@tauri-apps/api/core", () => ({
  invoke: (...args: any[]) => mockInvoke(...args),
}));

describe("localCadConverter", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (window as any).__TAURI_INTERNALS__ = {};
  });

  it("checks CAD tools status via Tauri command", async () => {
    mockInvoke.mockResolvedValueOnce({
      icad_dxf_available: true,
      icad_step_available: true,
      oda_available: true,
      icad_dir: "C:\\ICADSX",
      oda_path: "C:\\Program Files\\ODA\\ODAFileConverter.exe",
    });

    const status = await checkCadToolsAvailable();
    expect(status).not.toBeNull();
    expect(status?.icad_dxf_available).toBe(true);
    expect(status?.oda_available).toBe(true);
    expect(mockInvoke).toHaveBeenCalledWith("check_cad_tools_available");
  });

  it("converts local .icd file into DXF and companion STEP File instances", async () => {
    mockInvoke
      .mockResolvedValueOnce({
        success: true,
        original_path: "C:\\drawings\\bracket.icd",
        original_name: "bracket.icd",
        dxf_path: "C:\\temp\\bracket.dxf",
        step_path: "C:\\temp\\bracket.stp",
        error: null,
      })
      .mockResolvedValueOnce([1, 2, 3, 4]) // read_converted_file DXF
      .mockResolvedValueOnce([5, 6, 7, 8]) // read_converted_file STP
      .mockResolvedValue(undefined); // cleanup

    const result = await convertLocalCadFile("C:\\drawings\\bracket.icd");

    expect(result.sourceFormat).toBe("icd");
    expect(result.dxfFile.name).toBe("bracket.dxf");
    expect(result.companionStepFile?.name).toBe("bracket.stp");
    expect(mockInvoke).toHaveBeenCalledWith("convert_local_icd", { inputPath: "C:\\drawings\\bracket.icd" });
  });

  it("converts local .dwg file into DXF File instance", async () => {
    mockInvoke
      .mockResolvedValueOnce({
        success: true,
        original_path: "C:\\drawings\\sheet.dwg",
        original_name: "sheet.dwg",
        dxf_path: "C:\\temp\\sheet.dxf",
        step_path: null,
        error: null,
      })
      .mockResolvedValueOnce([10, 20, 30]) // read_converted_file DXF
      .mockResolvedValue(undefined); // cleanup

    const result = await convertLocalCadFile("C:\\drawings\\sheet.dwg");

    expect(result.sourceFormat).toBe("dwg");
    expect(result.dxfFile.name).toBe("sheet.dxf");
    expect(result.companionStepFile).toBeUndefined();
    expect(mockInvoke).toHaveBeenCalledWith("convert_local_dwg", { inputPath: "C:\\drawings\\sheet.dwg" });
  });
});
