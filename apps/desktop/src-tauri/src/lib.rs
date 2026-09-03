pub mod security;

#[tauri::command]
fn greet(name: &str) -> String {
    format!("Hello, {}! You've been greeted from Rust!", name)
}

/// Read the API token the running backend published.
///
/// ⚠ **Two directories can hold one, and reading the wrong one is not an error anywhere.** The
/// backend writes `<storage root>/secure/.api-token` and mirrors it to the per-user root
/// (`_mirror_token_for_installed_clients`, `core/security.py`). Both decrypt under the same
/// machine-bound key, so a token from a backend that stopped days ago is indistinguishable from
/// the live one until a request comes back 401 -- and `/health` needs no token, so the app still
/// reports itself CONNECTED while every authenticated call fails.
///
/// So this tries every candidate rather than the first, **newest file first**. The mirror is
/// rewritten on every backend startup while the storage-root copy is written once when the token
/// is generated, and only one backend can hold the port -- so "most recently published" is the
/// closest available proxy for "the backend that is actually answering". It is a proxy, not proof:
/// nothing here validates the token against the backend, and the frontend's 401 self-heal
/// (`parseOrThrow` clears `apiToken`, `checkHealth` re-reads it) can only re-read the same files.
///
/// The candidate that made this necessary was a stray `C:\storage`; that one is fixed at the
/// source in `security::looks_like_checkout`, which is where the reasoning lives.
#[tauri::command]
fn get_api_token() -> Result<String, String> {
    use crate::security::{find_storage_root, user_app_data_root, encryption, logging};
    
    logging::log("info", "TauriCommand", "Requesting local secure API token...");

    // Both known publication sites. In an installed build these resolve to the same path and
    // the dedup below collapses them; in a checkout they are the repo's storage and the mirror.
    let mut candidates = Vec::new();
    if let Ok(storage_root) = find_storage_root() {
        candidates.push(storage_root.join("secure").join(".api-token"));
    }
    if let Some(user_root) = user_app_data_root() {
        let user_token = user_root.join("secure").join(".api-token");
        if !candidates.contains(&user_token) {
            candidates.push(user_token);
        }
    }

    // Only files that exist, newest first -- see the doc comment for why mtime is the ordering
    let mut existing_candidates: Vec<std::path::PathBuf> = candidates
        .into_iter()
        .filter(|p| p.is_file())
        .collect();

    existing_candidates.sort_by(|a, b| {
        let mtime_a = std::fs::metadata(a).and_then(|m| m.modified()).ok();
        let mtime_b = std::fs::metadata(b).and_then(|m| m.modified()).ok();
        mtime_b.cmp(&mtime_a) // Newest first
    });

    if existing_candidates.is_empty() {
        logging::log("warn", "TauriCommand", "API token file does not exist yet.");
        return Err("API Token file does not exist yet. Please start the backend service first.".to_string());
    }

    let mut last_err = String::new();
    for token_file in existing_candidates {
        match std::fs::read_to_string(&token_file) {
            Ok(content) => match encryption::decrypt(content.trim()) {
                Ok(decrypted) => {
                    logging::log("info", "TauriCommand", &format!("Successfully loaded secure API token from {}", token_file.display()));
                    return Ok(decrypted);
                }
                Err(e) => {
                    let err_msg = format!("Failed to decrypt API token from {}: {}", token_file.display(), e);
                    logging::log("warn", "TauriCommand", &err_msg);
                    last_err = err_msg;
                }
            },
            Err(e) => {
                let err_msg = format!("Failed to read API token file from {}: {}", token_file.display(), e);
                logging::log("warn", "TauriCommand", &err_msg);
                last_err = err_msg;
            }
        }
    }

    logging::log("error", "TauriCommand", &last_err);
    Err(last_err)
}

/// Start the bundled backend, if it is installed beside this executable and not already running.
///
/// The installer registers a logon Scheduled Task, which covers the normal case. This covers the
/// rest: the task not firing, the backend having crashed, or a machine where the post-install hook
/// failed. Without it the app sits on "Connection Lost" forever with no way forward that does not
/// involve an engineer opening Task Scheduler.
///
/// ⚠ **Does not wait, and does not report success.** Startup takes tens of seconds (Atlas
/// connection plus index bootstrap), far longer than any sensible command timeout. The app already
/// polls `/health` every few seconds and recovers on its own, so this returns as soon as the
/// process is spawned and lets the existing polling notice.
///
/// ⚠ **CREATE_NO_WINDOW.** The backend is a console application on purpose, so an operator can run
/// it by hand and read the banner. Spawned from a GUI app without this flag it pops a console
/// window over the user's workspace every time.
#[tauri::command]
fn start_backend() -> Result<String, String> {
    use crate::security::logging;

    // In a development build, the backend is run from source by the developer (or launcher script).
    // Never attempt to launch a stale bundled binary that may linger in target/ or cache.
    #[cfg(debug_assertions)]
    {
        let msg = "Dev build: skipping bundled backend launch (backend is managed from source)".to_string();
        logging::log("info", "StartBackend", &msg);
        return Ok(msg);
    }

    #[cfg(not(debug_assertions))]
    {
        // Avoid socket collisions and token overwrites if a backend is already running on 127.0.0.1:8080.
        if std::net::TcpStream::connect("127.0.0.1:8080").is_ok() {
            let msg = "Backend is already listening on 127.0.0.1:8080".to_string();
            logging::log("info", "StartBackend", &msg);
            return Ok(msg);
        }

        let exe = std::env::current_exe()
            .map_err(|e| format!("Cannot locate the app executable: {e}"))?
            .parent()
            .map(|dir| dir.join("server").join("DraftCheck_Server.exe"))
            .ok_or_else(|| "App executable has no parent directory".to_string())?;

        if !exe.exists() {
            // A build with no bundled server; not an error.
            let msg = format!("No bundled backend at {}", exe.display());
            logging::log("info", "StartBackend", &msg);
            return Ok(msg);
        }

        let mut command = std::process::Command::new(&exe);
        // Working directory is the server folder so relative paths land beside the executable.
        if let Some(dir) = exe.parent() {
            command.current_dir(dir);
        }

        #[cfg(target_os = "windows")]
        {
            use std::os::windows::process::CommandExt;
            const CREATE_NO_WINDOW: u32 = 0x0800_0000;
            command.creation_flags(CREATE_NO_WINDOW);
        }

        match command.spawn() {
            Ok(child) => {
                let msg = format!("Backend starting (pid {})", child.id());
                logging::log("info", "StartBackend", &msg);
                Ok(msg)
            }
            Err(e) => {
                let msg = format!("Failed to start backend: {e}");
                logging::log("error", "StartBackend", &msg);
                Err(msg)
            }
        }
    }
}

#[derive(serde::Serialize, serde::Deserialize)]
struct SessionPayload {
    token: String,
    username: String,
    role: String,
}

/// Persists the active login session (token + username + role) as a single
/// AES-256-GCM encrypted file under storage/secure/, replacing the three
/// plaintext localStorage keys the frontend used previously (Phase 10,
/// frontend remediation plan). Reuses the same device-bound key and file
/// layout convention as get_api_token above.
#[tauri::command]
fn save_session(token: String, username: String, role: String) -> Result<(), String> {
    use crate::security::{find_storage_root, encryption, logging};

    let storage_root = find_storage_root()?;
    let secure_dir = storage_root.join("secure");
    std::fs::create_dir_all(&secure_dir)
        .map_err(|e| format!("Failed to create secure storage directory: {}", e))?;

    let payload = SessionPayload { token, username, role };
    let json = serde_json::to_string(&payload)
        .map_err(|e| format!("Failed to serialize session payload: {}", e))?;
    let encrypted = encryption::encrypt(&json)
        .map_err(|e| format!("Failed to encrypt session payload: {}", e))?;

    let session_file = secure_dir.join(".session-token");
    std::fs::write(&session_file, encrypted)
        .map_err(|e| format!("Failed to write session file: {}", e))?;

    logging::log("info", "TauriCommand", "Session persisted to secure storage.");
    Ok(())
}

/// Loads the persisted session, if any. Returns Ok(None) when no session file
/// exists yet (fresh install / never logged in) rather than an error, so the
/// frontend can distinguish "not logged in" from an actual failure.
#[tauri::command]
fn load_session() -> Result<Option<SessionPayload>, String> {
    use crate::security::{find_storage_root, encryption, logging};

    let storage_root = find_storage_root()?;
    let session_file = storage_root.join("secure").join(".session-token");

    if !session_file.exists() {
        return Ok(None);
    }

    let encrypted_content = std::fs::read_to_string(&session_file)
        .map_err(|e| format!("Failed to read session file: {}", e))?;

    if encrypted_content.trim().is_empty() {
        return Ok(None);
    }

    let decrypted = encryption::decrypt(encrypted_content.trim())
        .map_err(|e| {
            let err_msg = format!("Failed to decrypt session file: {}", e);
            logging::log("warn", "TauriCommand", &err_msg);
            err_msg
        })?;

    let payload: SessionPayload = serde_json::from_str(&decrypted)
        .map_err(|e| format!("Failed to parse decrypted session payload: {}", e))?;

    Ok(Some(payload))
}

/// Deletes the persisted session file on logout.
#[tauri::command]
fn clear_session() -> Result<(), String> {
    use crate::security::find_storage_root;

    let storage_root = find_storage_root()?;
    let session_file = storage_root.join("secure").join(".session-token");
    if session_file.exists() {
        std::fs::remove_file(&session_file)
            .map_err(|e| format!("Failed to remove session file: {}", e))?;
    }
    Ok(())
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
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .invoke_handler(tauri::generate_handler![greet, get_api_token, start_backend, save_session, load_session, clear_session, log_from_frontend])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
