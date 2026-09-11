use std::path::{Path, PathBuf};
use crate::security::logging;

pub const DEFAULT_NAS_STORAGE: &str = r"\\KMTI-NAS\Shared\data\ai_checker\storage";

fn get_client_offline_dir() -> PathBuf {
    if let Some(appdata) = std::env::var_os("APPDATA") {
        PathBuf::from(appdata).join("draftcheck").join("offline_storage")
    } else {
        std::env::temp_dir().join("draftcheck_offline_storage")
    }
}

/// Checks if the configured NAS directory is reachable and writable from this Client PC.
#[tauri::command]
pub fn check_nas_reachable(custom_path: Option<String>) -> bool {
    let target = custom_path.unwrap_or_else(|| DEFAULT_NAS_STORAGE.to_string());
    let path = Path::new(&target);
    if !path.exists() {
        return false;
    }

    let probe = path.join(".client_probe");
    match std::fs::write(&probe, b"probe") {
        Ok(_) => {
            let _ = std::fs::remove_file(&probe);
            true
        }
        Err(e) => {
            logging::log("debug", "NasSync", &format!("NAS probe check failed: {}", e));
            false
        }
    }
}

/// Syncs a file directly to the NAS network share from the Client PC.
/// Verifies the written file size before returning Ok(true).
#[tauri::command]
pub fn sync_file_to_nas(
    subfolder: String,
    file_name: String,
    data: Vec<u8>,
    custom_path: Option<String>,
) -> Result<bool, String> {
    let target = custom_path.unwrap_or_else(|| DEFAULT_NAS_STORAGE.to_string());
    let base_path = Path::new(&target);
    let target_dir = base_path.join(&subfolder);

    std::fs::create_dir_all(&target_dir)
        .map_err(|e| format!("Failed to create destination dir on NAS: {}", e))?;

    let target_file = target_dir.join(&file_name);
    std::fs::write(&target_file, &data)
        .map_err(|e| format!("Failed to write file to NAS: {}", e))?;

    let meta = std::fs::metadata(&target_file)
        .map_err(|e| format!("Failed to verify file on NAS: {}", e))?;

    if meta.len() as usize != data.len() {
        let _ = std::fs::remove_file(&target_file);
        return Err(format!(
            "NAS file verification failed: byte mismatch (expected {}, got {})",
            data.len(),
            meta.len()
        ));
    }

    logging::log(
        "info",
        "NasSync",
        &format!("Successfully synced {} ({} bytes) to NAS {}", file_name, data.len(), target_file.display()),
    );
    Ok(true)
}

/// Saves an offline fallback file into the Client PC's local storage directory (%APPDATA%\draftcheck\offline_storage\).
#[tauri::command]
pub fn save_client_local_file(
    subfolder: String,
    file_name: String,
    data: Vec<u8>,
) -> Result<String, String> {
    let base = get_client_offline_dir().join(&subfolder);
    std::fs::create_dir_all(&base)
        .map_err(|e| format!("Failed to create client offline dir: {}", e))?;

    let file_path = base.join(&file_name);
    std::fs::write(&file_path, &data)
        .map_err(|e| format!("Failed to save client offline file: {}", e))?;

    logging::log(
        "info",
        "NasSync",
        &format!("Saved fallback file on Client PC: {}", file_path.display()),
    );
    Ok(file_path.to_string_lossy().to_string())
}

/// Reads a fallback file from the Client PC's local storage directory.
#[tauri::command]
pub fn read_client_local_file(
    subfolder: String,
    file_name: String,
) -> Result<Vec<u8>, String> {
    let file_path = get_client_offline_dir().join(&subfolder).join(&file_name);
    std::fs::read(&file_path)
        .map_err(|e| format!("Failed to read client offline file: {}", e))
}

/// Deletes a synced fallback file from the Client PC's local storage directory.
#[tauri::command]
pub fn delete_client_local_file(
    subfolder: String,
    file_name: String,
) -> Result<(), String> {
    let file_path = get_client_offline_dir().join(&subfolder).join(&file_name);
    if file_path.exists() {
        std::fs::remove_file(&file_path)
            .map_err(|e| format!("Failed to delete client offline file: {}", e))?;
        logging::log(
            "info",
            "NasSync",
            &format!("Cleaned up client fallback file: {}", file_path.display()),
        );
    }
    Ok(())
}
