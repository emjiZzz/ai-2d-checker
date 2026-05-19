use std::fs;
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};
use std::process::Command;
use crate::security::{traversal::validate_sandboxed_path, logging};

/// Safe native temporary directory cleaner.
/// Deletes expired temporary DXF files inside the secure 'temp/' sandbox folder.
pub fn clean_temp_directory(storage_root: &Path, max_age_secs: u64) -> Result<u32, String> {
    let temp_dir = storage_root.join("temp");
    
    // 1. Enforce path traversal protection on temp folder itself
    let canonical_temp = validate_sandboxed_path(storage_root, &temp_dir)?;
    
    if !canonical_temp.exists() || !canonical_temp.is_dir() {
        return Ok(0);
    }

    let mut deleted_count = 0;
    let now = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|e| e.to_string())?
        .as_secs();

    if let Ok(entries) = fs::read_dir(&canonical_temp) {
        for entry in entries.flatten() {
            let path = entry.path();
            
            // Re-validate each child file resides within the sandbox
            if validate_sandboxed_path(storage_root, &path).is_err() {
                continue;
            }

            if let Ok(metadata) = fs::metadata(&path) {
                if metadata.is_file() {
                    if let Ok(modified) = metadata.modified() {
                        if let Ok(mod_time) = modified.duration_since(UNIX_EPOCH) {
                            let age = now.saturating_sub(mod_time.as_secs());
                            if age >= max_age_secs {
                                if fs::remove_file(&path).is_ok() {
                                    deleted_count += 1;
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    logging::log(
        "info",
        "TempCleaner",
        &format!("Cleaned {} expired temporary files from sandbox.", deleted_count)
    );
    Ok(deleted_count)
}

/// Native file validation helper that reads the header bytes of drawing files.
/// Verifies true DWG signature headers ("AC" format markers) to block malicious executables disguised with CAD extensions.
pub fn validate_file_signature(file_path: &Path) -> Result<String, String> {
    if !file_path.exists() || !file_path.is_file() {
        return Err("Target drawing file does not exist.".to_string());
    }

    // Read first 6 bytes
    let bytes = fs::read(file_path)
        .map_err(|e| format!("Failed to read file header signature: {}", e))?;

    if bytes.len() < 6 {
        return Err("File is too small to contain a valid CAD drawing header signature.".to_string());
    }

    // 1. Detect DWG: Autocad DWG files always start with ASCII "AC" followed by format version
    // e.g. AC1015 (AutoCAD 2000), AC1027 (AutoCAD 2013), AC1032 (AutoCAD 2018)
    if bytes[0] == b'A' && bytes[1] == b'C' {
        let version = String::from_utf8_lossy(&bytes[0..6]).to_string();
        logging::log(
            "info",
            "FileValidator",
            &format!("Validated authentic DWG drawing signature: {}", version)
        );
        return Ok("dwg".to_string());
    }

    // 2. Detect DXF: DXF files are text files starting with standard group codes or section tags.
    // Standard ASCII DXF usually starts with "  0\nSECTION" or "  0\r\nSECTION"
    let header_sample = String::from_utf8_lossy(&bytes[0..std::cmp::min(bytes.len(), 50)]);
    let sample_upper = header_sample.to_uppercase();
    if sample_upper.contains("SECTION") || sample_upper.contains("HEADER") || sample_upper.trim_start().starts_with('0') {
        logging::log("info", "FileValidator", "Validated DXF ASCII header signature.");
        return Ok("dxf".to_string());
    }

    Err("Invalid CAD Drawing: File header does not match a valid DWG or DXF signature.".to_string())
}

/// Safe native ODA executable subprocess launcher.
/// Invokes ODAFileConverter without arbitrary shell execution, enforcing strict allowlists and sandbox validations.
pub async fn launch_oda_converter(
    converter_exe: &Path,
    storage_root: &Path,
    dwg_path: &Path,
    output_dir: &Path,
) -> Result<(), String> {
    // 1. Enforce strict executable allowlist
    let exe_name = converter_exe
        .file_name()
        .ok_or_else(|| "Invalid ODA executable name".to_string())?
        .to_string_lossy()
        .to_lowercase();

    if exe_name != "odafileconverter.exe" && exe_name != "odafileconverter" {
        return Err("Security Blocked: Arbitrary process launch rejected. Executable name must be ODAFileConverter".to_string());
    }

    // 2. Enforce sandbox traversal limits on all arguments
    let canonical_dwg = validate_sandboxed_path(storage_root, dwg_path)?;
    let canonical_out = validate_sandboxed_path(storage_root, output_dir)?;

    let input_dir = canonical_dwg
        .parent()
        .ok_or_else(|| "Input file has no parent".to_string())?;
        
    let file_name = canonical_dwg
        .file_name()
        .ok_or_else(|| "Invalid input filename".to_string())?;

    // Log the process launch
    logging::log(
        "info",
        "NativeProcess",
        &format!(
            "Launching authorized process: {:?} for conversion file: {:?}",
            converter_exe, file_name
        )
    );

    // 3. Spawns process asynchronously without using a shell to block argument injection attacks
    let mut child = Command::new(converter_exe)
        .arg(input_dir)
        .arg(canonical_out)
        .arg("ACAD2018")
        .arg("DXF")
        .arg("0")
        .arg("1")
        .arg(file_name)
        .spawn()
        .map_err(|e| format!("Failed to spawn ODA Converter subprocess: {}", e))?;

    let status = child
        .wait()
        .map_err(|e| format!("Error waiting for ODA Converter subprocess: {}", e))?;

    if !status.success() {
        return Err(format!(
            "ODA File Converter exited with non-zero status code: {}",
            status
        ));
    }

    logging::log(
        "info",
        "NativeProcess",
        "ODA Converter subprocess completed execution successfully."
    );
    Ok(())
}
