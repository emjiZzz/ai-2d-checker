pub mod security;

#[tauri::command]
fn greet(name: &str) -> String {
    format!("Hello, {}! You've been greeted from Rust!", name)
}

#[tauri::command]
fn get_api_token() -> Result<String, String> {
    use crate::security::{find_storage_root, encryption, logging};
    
    logging::log("info", "TauriCommand", "Requesting local secure API token...");
    let storage_root = find_storage_root()?;
    let token_file = storage_root.join("secure").join(".api-token");
    
    if !token_file.exists() {
        logging::log("warn", "TauriCommand", "API token file does not exist yet.");
        return Err("API Token file does not exist yet. Please start the backend service first.".to_string());
    }
    
    let encrypted_content = std::fs::read_to_string(&token_file)
        .map_err(|e| {
            let err_msg = format!("Failed to read API token file: {}", e);
            logging::log("error", "TauriCommand", &err_msg);
            err_msg
        })?;
        
    let decrypted = encryption::decrypt(encrypted_content.trim())
        .map_err(|e| {
            let err_msg = format!("Failed to decrypt API token: {}", e);
            logging::log("error", "TauriCommand", &err_msg);
            err_msg
        })?;
        
    logging::log("info", "TauriCommand", "Successfully loaded secure API token in-memory.");
    Ok(decrypted)
}

#[tauri::command]
fn log_from_frontend(level: &str, message: &str) {
    use crate::security::logging;
    logging::log(level, "Frontend", message);
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    // A. Locate storage root and initialize Rust-side logging
    if let Ok(storage_root) = security::find_storage_root() {
        let log_dir = storage_root.join("logs").join("app");
        let token_path = storage_root.join("secure").join(".api-token");
        security::logging::init_logger(log_dir, Some(token_path));
        security::logging::log("info", "TauriInit", "Rust-side logging and panic hooks initialized successfully.");
    } else {
        eprintln!("Warning: Could not locate storage root for logger initialization.");
    }

    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![greet, get_api_token, log_from_frontend])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
