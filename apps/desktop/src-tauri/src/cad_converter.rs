use std::ffi::{OsStr, OsString};
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CadToolsStatus {
    pub icad_dxf_available: bool,
    pub icad_step_available: bool,
    pub oda_available: bool,
    pub icad_dir: Option<String>,
    pub oda_path: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConversionOutput {
    pub success: bool,
    pub original_path: String,
    pub original_name: String,
    pub dxf_path: Option<String>,
    pub step_path: Option<String>,
    pub error: Option<String>,
}

#[cfg(target_os = "windows")]
extern "system" {
    fn GetShortPathNameW(
        lpszLongPath: *const u16,
        lpszShortPath: *mut u16,
        cchBuffer: u32,
    ) -> u32;

    fn WideCharToMultiByte(
        code_page: u32,
        flags: u32,
        lp_wide_char_str: *const u16,
        cch_wide_char: i32,
        lp_multi_byte_str: *mut u8,
        cb_multi_byte: i32,
        lp_default_char: *const u8,
        lp_used_default_char: *mut i32,
    ) -> i32;
}

#[cfg(target_os = "windows")]
fn get_short_path(path: &Path) -> PathBuf {
    use std::os::windows::ffi::{OsStrExt, OsStringExt};
    let wide: Vec<u16> = path.as_os_str().encode_wide().chain(std::iter::once(0)).collect();
    let mut buffer: Vec<u16> = vec![0; 1024];
    let len = unsafe {
        GetShortPathNameW(wide.as_ptr(), buffer.as_mut_ptr(), buffer.len() as u32)
    };
    if len > 0 && (len as usize) < buffer.len() {
        buffer.truncate(len as usize);
        PathBuf::from(OsString::from_wide(&buffer))
    } else {
        path.to_path_buf()
    }
}

#[cfg(not(target_os = "windows"))]
fn get_short_path(path: &Path) -> PathBuf {
    path.to_path_buf()
}

fn to_cp932_bytes(s: &str) -> Vec<u8> {
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::ffi::OsStrExt;
        let wide: Vec<u16> = OsStr::new(s).encode_wide().collect();
        unsafe {
            let len = WideCharToMultiByte(
                932,
                0,
                wide.as_ptr(),
                wide.len() as i32,
                std::ptr::null_mut(),
                0,
                std::ptr::null(),
                std::ptr::null_mut(),
            );
            if len > 0 {
                let mut buf = vec![0u8; len as usize];
                WideCharToMultiByte(
                    932,
                    0,
                    wide.as_ptr(),
                    wide.len() as i32,
                    buf.as_mut_ptr(),
                    len,
                    std::ptr::null(),
                    std::ptr::null_mut(),
                );
                return buf;
            }
        }
    }
    s.as_bytes().to_vec()
}

pub fn find_icad_dir() -> Option<PathBuf> {
    let candidate = PathBuf::from("C:\\ICADSX");
    if candidate.is_dir() {
        Some(candidate)
    } else {
        None
    }
}

pub fn find_oda_converter() -> Option<PathBuf> {
    let common_paths = [
        "C:\\Program Files\\ODA\\ODAFileConverter 27.1.0\\ODAFileConverter.exe",
        "C:\\Program Files\\ODA\\ODAFileConverter 26.1.0\\ODAFileConverter.exe",
        "C:\\Program Files\\ODA\\ODAFileConverter 25.1.0\\ODAFileConverter.exe",
        "C:\\Program Files\\ODA\\ODAFileConverter 24.1.0\\ODAFileConverter.exe",
    ];
    for p in common_paths {
        let path = PathBuf::from(p);
        if path.is_file() {
            return Some(path);
        }
    }

    // Dynamic scan in C:\Program Files\ODA
    for base in ["C:\\Program Files\\ODA", "C:\\Program Files (x86)\\ODA"] {
        let base_path = PathBuf::from(base);
        if let Ok(entries) = fs::read_dir(base_path) {
            for entry in entries.flatten() {
                let exe = entry.path().join("ODAFileConverter.exe");
                if exe.is_file() {
                    return Some(exe);
                }
            }
        }
    }
    None
}

#[tauri::command]
pub fn check_cad_tools_available() -> CadToolsStatus {
    let icad = find_icad_dir();
    let icad_dxf = icad.as_ref().map(|dir| {
        dir.join("TR2").join("DXFDWG").join("bin").join("TR2_DExp.exe").is_file()
    }).unwrap_or(false);

    let icad_step = icad.as_ref().map(|dir| {
        dir.join("bin").join("ICD2STP.exe").is_file()
    }).unwrap_or(false);

    let oda = find_oda_converter();
    let oda_available = oda.is_some();

    CadToolsStatus {
        icad_dxf_available: icad_dxf,
        icad_step_available: icad_step,
        oda_available,
        icad_dir: icad.map(|p| p.to_string_lossy().to_string()),
        oda_path: oda.map(|p| p.to_string_lossy().to_string()),
    }
}

#[tauri::command]
pub fn convert_local_icd(input_path: String) -> Result<ConversionOutput, String> {
    let input = PathBuf::from(&input_path);
    if !input.is_file() {
        return Err(format!("Input iCAD file does not exist: {}", input_path));
    }

    let file_name = input.file_name().unwrap_or_default().to_string_lossy().to_string();
    let stem = input.file_stem().unwrap_or_default().to_string_lossy().to_string();

    let icad_dir = find_icad_dir().ok_or_else(|| {
        "iCAD SX directory not found at C:\\ICADSX. Please verify iCAD SX is installed.".to_string()
    })?;

    let tr2_dexp = icad_dir.join("TR2").join("DXFDWG").join("bin").join("TR2_DExp.exe");
    if !tr2_dexp.is_file() {
        return Err(format!("iCAD DXF translator not found at: {}", tr2_dexp.display()));
    }

    // Prepare clean unique output directory in system temp
    let unique_id = format!("icd2dxf_{}_{}", std::process::id(), chrono::Utc::now().timestamp_millis());
    let out_dir = std::env::temp_dir().join("draftcheck_converted").join(&unique_id);
    fs::create_dir_all(&out_dir).map_err(|e| format!("Failed to create temp output directory: {e}"))?;

    let expected_dxf = out_dir.join(format!("{}.dxf", stem));

    // 1. Convert 2D DXF using TR2_DExp.exe
    let drawlist_path = out_dir.join("drawlist.txt");
    let drawlist_content = format!("{}\n\n", input.display());
    let drawlist_bytes = to_cp932_bytes(&drawlist_content);
    fs::write(&drawlist_path, drawlist_bytes)
        .map_err(|e| format!("Failed to write drawlist.txt: {e}"))?;

    let mut cmd = Command::new(&tr2_dexp);
    cmd.arg("-RN").arg(&drawlist_path)
        .arg("-dxf").arg("R2018")
        .arg("-o").arg(&out_dir)
        .arg("-msg").arg("0")
        .current_dir(&out_dir);

    // Set vendor-required environment variables
    cmd.env("ICADDIR", &icad_dir)
        .env("IUSRHOME", &out_dir)
        .env("BATCHMODE", "1")
        .env("MDL00", icad_dir.join("parts").join("部品フォルダ１"))
        .env("LIB00", &icad_dir)
        .env("LIB01", icad_dir.join("mmf").join("図面フォルダ"))
        .env("LIB02", icad_dir.join("parts").join("部品フォルダ２"))
        .env("LIB05", icad_dir.join("parts").join("部品フォルダ３"))
        .env("LIB08", icad_dir.join("sysmmf").join("システムフォルダ"))
        .env("ILOGFN", out_dir.join("cmdlog"))
        .env("IMACDN", icad_dir.join("macro"))
        .env("IMSGIDX", icad_dir.join("msg").join("msgidx_J"))
        .env("IMSGF0", icad_dir.join("msg").join("sdsmsg_J"))
        .env("IMSGF1", icad_dir.join("msg").join("usrmsg1"))
        .env("KGSV", icad_dir.join("kgs"))
        .env("RESFILE", out_dir.join("res00"))
        .env("ROLFILE", out_dir.join("rol00"));

    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }

    let output = cmd.output().map_err(|e| format!("Failed to execute TR2_DExp.exe: {e}"))?;
    
    let dxf_path_res = if expected_dxf.is_file() {
        Some(expected_dxf.to_string_lossy().to_string())
    } else {
        None
    };

    // 2. Also attempt 3D STEP conversion via ICD2STP.exe if present
    let mut step_path_res: Option<String> = None;
    let icd2stp = icad_dir.join("bin").join("ICD2STP.exe");
    if icd2stp.is_file() {
        let step_output_stem = out_dir.join(&stem);
        let expected_stp = out_dir.join(format!("{}.stp", stem));

        let mut step_cmd = Command::new(&icd2stp);
        step_cmd.arg("-ls")
            .arg(format!("-i{}", input.display()))
            .arg(format!("-o{}", step_output_stem.display()))
            .current_dir(icad_dir.join("bin"));

        #[cfg(target_os = "windows")]
        {
            use std::os::windows::process::CommandExt;
            const CREATE_NO_WINDOW: u32 = 0x0800_0000;
            step_cmd.creation_flags(CREATE_NO_WINDOW);
        }

        if let Ok(step_res) = step_cmd.output() {
            // Exit code 0 is normal, 4 is partial conversion with geometry still output
            if (step_res.status.code() == Some(0) || step_res.status.code() == Some(4)) && expected_stp.is_file() {
                step_path_res = Some(expected_stp.to_string_lossy().to_string());
            }
        }
    }

    if dxf_path_res.is_none() && step_path_res.is_none() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        let stdout = String::from_utf8_lossy(&output.stdout);
        return Ok(ConversionOutput {
            success: false,
            original_path: input_path,
            original_name: file_name,
            dxf_path: None,
            step_path: None,
            error: Some(format!("iCAD translation produced no DXF or STEP output. Stdout: {} | Stderr: {}", stdout, stderr)),
        });
    }

    Ok(ConversionOutput {
        success: true,
        original_path: input_path,
        original_name: file_name,
        dxf_path: dxf_path_res,
        step_path: step_path_res,
        error: None,
    })
}

#[tauri::command]
pub fn convert_local_dwg(input_path: String) -> Result<ConversionOutput, String> {
    let input = PathBuf::from(&input_path);
    if !input.is_file() {
        return Err(format!("Input DWG file does not exist: {}", input_path));
    }

    let file_name = input.file_name().unwrap_or_default().to_string_lossy().to_string();
    let stem = input.file_stem().unwrap_or_default().to_string_lossy().to_string();

    let oda_exe = find_oda_converter().ok_or_else(|| {
        "ODA File Converter not found. Please install ODA File Converter on this PC.".to_string()
    })?;

    let unique_id = format!("dwg2dxf_{}_{}", std::process::id(), chrono::Utc::now().timestamp_millis());
    let out_dir = std::env::temp_dir().join("draftcheck_converted").join(&unique_id);
    fs::create_dir_all(&out_dir).map_err(|e| format!("Failed to create temp output directory: {e}"))?;

    let expected_dxf = out_dir.join(format!("{}.dxf", stem));

    let input_dir = input.parent().unwrap_or_else(|| Path::new("."));

    let short_oda = get_short_path(&oda_exe);
    let short_in_dir = get_short_path(input_dir);
    let short_out_dir = get_short_path(&out_dir);

    let mut cmd = Command::new(&short_oda);
    cmd.arg(&short_in_dir)
        .arg(&short_out_dir)
        .arg("ACAD2018")
        .arg("DXF")
        .arg("0")
        .arg("1")
        .arg(&file_name)
        .current_dir(&out_dir);

    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }

    let output = cmd.output().map_err(|e| format!("Failed to execute ODAFileConverter: {e}"))?;

    if !expected_dxf.is_file() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        let stdout = String::from_utf8_lossy(&output.stdout);
        return Ok(ConversionOutput {
            success: false,
            original_path: input_path,
            original_name: file_name,
            dxf_path: None,
            step_path: None,
            error: Some(format!("ODA File Converter produced no DXF file. Status: {:?} | Stdout: {} | Stderr: {}", output.status.code(), stdout, stderr)),
        });
    }

    Ok(ConversionOutput {
        success: true,
        original_path: input_path,
        original_name: file_name,
        dxf_path: Some(expected_dxf.to_string_lossy().to_string()),
        step_path: None,
        error: None,
    })
}

#[tauri::command]
pub fn read_converted_file(path: String) -> Result<Vec<u8>, String> {
    let p = PathBuf::from(&path);
    fs::read(&p).map_err(|e| format!("Failed to read converted file {}: {e}", path))
}

#[tauri::command]
pub fn convert_local_bytes(file_name: String, bytes: Vec<u8>) -> Result<ConversionOutput, String> {
    let ext = file_name.split('.').last().unwrap_or("").to_lowercase();
    let unique_id = format!("bytes2cad_{}_{}", std::process::id(), chrono::Utc::now().timestamp_millis());
    let staging_dir = std::env::temp_dir().join("draftcheck_converted").join(&unique_id);
    fs::create_dir_all(&staging_dir).map_err(|e| format!("Failed to create staging directory: {e}"))?;

    let staging_file = staging_dir.join(&file_name);
    fs::write(&staging_file, bytes).map_err(|e| format!("Failed to write staging file: {e}"))?;

    let staging_path = staging_file.to_string_lossy().to_string();

    if ext == "icd" {
        convert_local_icd(staging_path)
    } else if ext == "dwg" {
        convert_local_dwg(staging_path)
    } else {
        Err(format!("Unsupported format for local conversion: .{}", ext))
    }
}

#[tauri::command]
pub fn cleanup_converted_file(path: String) -> Result<(), String> {
    let p = PathBuf::from(&path);
    if p.is_file() {
        let _ = fs::remove_file(&p);
    }
    if let Some(parent) = p.parent() {
        // Remove parent directory if it's within draftcheck_converted
        if parent.to_string_lossy().contains("draftcheck_converted") {
            let _ = fs::remove_dir_all(parent);
        }
    }
    Ok(())
}
