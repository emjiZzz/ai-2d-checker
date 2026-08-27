pub mod traversal;
pub mod encryption;
pub mod logging;
pub mod native;

use std::path::PathBuf;
use std::env;

/// Traverses directories upward from the execution context to discover the 'storage' root path.
/// This prevents brittle hardcoded paths across development, staging, and production.
pub fn find_storage_root() -> Result<PathBuf, String> {
    // 1. Explicit environment check
    if let Ok(val) = env::var("STORAGE_ROOT") {
        let path = PathBuf::from(val);
        if path.is_dir() {
            return Ok(path);
        }
    }

    // 2. Ascending search up to 6 parents from current working directory
    if let Ok(mut current) = env::current_dir() {
        for _ in 0..6 {
            let test_path = current.join("storage");
            if test_path.is_dir() {
                return Ok(test_path);
            }
            if let Some(parent) = current.parent() {
                current = parent.to_path_buf();
            } else {
                break;
            }
        }
    }

    // 3. Ascending search from the executable's directory
    if let Ok(exe_path) = env::current_exe() {
        let mut current = exe_path.parent().map(|p| p.to_path_buf()).unwrap_or_default();
        for _ in 0..6 {
            if current.as_os_str().is_empty() {
                break;
            }
            let test_path = current.join("storage");
            if test_path.is_dir() {
                return Ok(test_path);
            }
            if let Some(parent) = current.parent() {
                current = parent.to_path_buf();
            } else {
                break;
            }
        }
    }

    // 4. Default standard fallback relative structures
    let fallback_paths = ["../../storage", "./storage", "../storage", "../../../storage"];
    for p in &fallback_paths {
        let path = PathBuf::from(p);
        if path.is_dir() {
            return Ok(path);
        }
    }

    // 5. Per-user application data -- the only branch an INSTALLED build can reach.
    //
    // Every search above walks outward from the working directory or the executable looking for a
    // `storage` folder, which only exists inside a source checkout. An app installed to
    // `C:\Program Files\KMTI Checker\` has none anywhere up its tree, so this returned Err, the
    // token could not be read, and every authenticated request answered 401 -- while `/health`
    // needs no token and returned 200, so the app reported itself CONNECTED. Rooms came back
    // empty and "Create Room" did nothing, with no error shown anywhere.
    //
    // The backend publishes the token here on startup (`_mirror_token_for_installed_clients` in
    // `core/security.py`), so this is a real storage root with a `secure/` inside it, not a
    // special case for one file -- which also restores session save/load for an installed build.
    //
    // Last on purpose: a source checkout must keep resolving to its own `storage`, so that
    // development behaviour is byte-identical to what it was before this branch existed.
    if let Some(user_root) = user_app_data_root() {
        if user_root.is_dir() {
            return Ok(user_root);
        }
    }

    Err("Critical: Could not locate storage root folder. Ensure the services are operational.".to_string())
}

/// Per-user directory the backend publishes the API token to, or `None` if the OS gives us nowhere.
///
/// ⚠ Mirrors `user_storage_root()` in `services/backend/core/security.py`. Two declarations in two
/// languages with no shared constant, so `tests/test_user_token_dir.py` parses this file and fails
/// if they drift -- the failure mode otherwise is an app that authenticates in dev and silently
/// 401s once installed.
///
/// ⚠ **Not the `tauri.conf.json` identifier**, and the test asserts that too. See the constant
/// below for what putting it there cost.
///
/// **Local, not roaming**: the encryption key is derived from machine identity, so a roamed copy
/// would not decrypt on the machine it roamed to.
pub fn user_app_data_root() -> Option<PathBuf> {
    // 🔴 Deliberately NOT the bundle identifier `com.kmti.checker`, which this was until
    // 2026-08-27. That directory is this app's OWN data directory -- WebView2 keeps its profile
    // there and the uninstaller deletes it -- so an uninstall/reinstall cycle removed the token
    // the backend had published, and every authenticated request 401'd until the backend was
    // restarted. Observed in the access log: 401 on POST and GET /api/v1/rooms at 05:16, healthy
    // again at 05:18 only because a diagnostic re-ran token initialisation. A sibling directory
    // survives the uninstall and does not collide with the webview's storage.
    //
    // Mirrors TOKEN_DIR_NAME in services/backend/core/security.py; pinned by
    // tests/test_user_token_dir.py.
    const TOKEN_DIR_NAME: &str = "kmti-2d-checker";

    #[cfg(target_os = "windows")]
    let base = env::var("LOCALAPPDATA").ok().or_else(|| env::var("APPDATA").ok());

    #[cfg(target_os = "macos")]
    let base = env::var("HOME")
        .ok()
        .map(|h| format!("{}/Library/Application Support", h));

    #[cfg(not(any(target_os = "windows", target_os = "macos")))]
    let base = env::var("XDG_DATA_HOME")
        .ok()
        .or_else(|| env::var("HOME").ok().map(|h| format!("{}/.local/share", h)));

    base.map(|b| PathBuf::from(b).join(TOKEN_DIR_NAME))
}
