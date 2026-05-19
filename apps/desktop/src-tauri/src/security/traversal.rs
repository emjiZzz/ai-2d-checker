use std::path::{Path, PathBuf};
use std::fs;

/// Canonical path sandboxing validation in Rust.
/// Resolves paths, canonicalizes them, and ensures they reside strictly within the storage root
/// to block traversal attacks or symlink escapes.
pub fn validate_sandboxed_path(
    storage_root: &Path,
    user_path: &Path,
) -> Result<PathBuf, String> {
    // 1. Resolve canonical absolute path of storage_root (must exist, or default to current workspace)
    let canonical_root = fs::canonicalize(storage_root)
        .map_err(|e| format!("Failed to canonicalize storage root: {}", e))?;

    // Check if the user path exists. If it doesn't, check its parent directory for sandboxing.
    let absolute_user_path = if user_path.exists() {
        fs::canonicalize(user_path)
            .map_err(|e| format!("Failed to canonicalize user path: {}", e))?
    } else {
        // Resolve parent or ancestor path validation if new file is to be created
        let parent = user_path.parent()
            .ok_or_else(|| "User path has no parent directory".to_string())?;
        
        let canonical_parent = fs::canonicalize(parent)
            .map_err(|e| format!("Failed to canonicalize parent folder: {}", e))?;
            
        let file_name = user_path.file_name()
            .ok_or_else(|| "Invalid file name in path".to_string())?;
            
        canonical_parent.join(file_name)
    };

    // 2. Traversal validation check: absolute_user_path must start with canonical_root
    if !absolute_user_path.starts_with(&canonical_root) {
        return Err(format!(
            "Path Traversal Blocked: Resolved path '{:?}' escapes storage sandbox boundary '{:?}'",
            absolute_user_path, canonical_root
        ));
    }

    // 3. String-based traversal pattern matching check
    let path_str = user_path.to_string_lossy();
    if path_str.contains("..") {
        return Err("Path Traversal Blocked: Path contains invalid traversal operators".to_string());
    }

    Ok(absolute_user_path)
}
