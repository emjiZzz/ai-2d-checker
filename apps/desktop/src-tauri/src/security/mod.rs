pub mod traversal;
pub mod encryption;
pub mod logging;
pub mod native;

use std::path::{Path, PathBuf};
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

    Err("Critical: Could not locate storage root folder. Ensure the services are operational.".to_string())
}
