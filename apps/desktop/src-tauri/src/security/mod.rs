pub mod traversal;
pub mod encryption;
pub mod logging;
pub mod native;

use std::path::{Path, PathBuf};
use std::env;

/// Does this directory hold a source checkout of THIS project?
///
/// The searches in `find_storage_root` accept any directory named `storage`, and from an
/// installed build they ascend all the way to the drive root: an app at
/// `C:\Users\<user>\AppData\Local\DraftCheck\` is five parents below `C:\`, inside the
/// six-parent budget. So a stray `C:\storage` is found first and the per-user branch below --
/// whose comment claims to be "the only branch an INSTALLED build can reach" -- is never reached.
///
/// 🔴 Not hypothetical. The frozen backend launched from `C:\` created exactly that directory
/// (see 27fb0ab, which fixed the backend half and left this one), and on 2026-08-28 the installed
/// 0.1.8 build read `C:\storage\secure\.api-token`: a token published the previous day, which
/// decrypts perfectly under the same machine-bound key and which the running backend has never
/// issued. Every authenticated request answered 401 "Access Denied: Invalid security API Token"
/// while `/health` stayed 200, so the app reported itself CONNECTED and the tour's "Enter Tutorial
/// Room" failed with no clue why.
///
/// ⚠ **A wrong token fails differently from a missing one, which is why this hid.** A missing file
/// is an error the app reports; a stale file that decrypts is a plausible credential, and the
/// frontend's self-heal (clear `apiToken` on 401, re-read on the next 5-second poll) then re-reads
/// the *same* stale file forever. The app log showed that loop running every five seconds.
///
/// Requiring a project marker beside it is what makes "a `storage` directory" mean "this
/// project's storage directory".
fn looks_like_checkout(root: &Path) -> bool {
    root.join("pyproject.toml").is_file()
        || (root.join("services").join("backend").is_dir()
            && root.join("apps").join("desktop").is_dir())
}

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
            if test_path.is_dir() && looks_like_checkout(&current) {
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
            if test_path.is_dir() && looks_like_checkout(&current) {
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
        // Same gate as the loops above: these are that ascent unrolled against the working
        // directory, so an ungated `./storage` reintroduces the escape one line below the fix.
        let beside_a_checkout = path.parent().map(looks_like_checkout).unwrap_or(false);
        if path.is_dir() && beside_a_checkout {
            return Ok(path);
        }
    }

    // 5. Per-user application data -- the only branch an INSTALLED build can reach.
    //
    // ⚠ That sentence was FALSE from the day it was written until 2026-08-28, and the app shipped
    // on it. The searches above accept any directory named `storage`, so an installed build bound
    // to a stray `C:\storage` and read a token the running backend had never issued. It is true
    // again only because `looks_like_checkout` now gates them -- a claim, not a fact, until
    // something checks it, which is `tests/test_storage_root_resolution.py`.
    //
    // Every search above walks outward from the working directory or the executable looking for a
    // `storage` folder, which only exists inside a source checkout. An app installed to
    // `C:\Program Files\DraftCheck\` has none anywhere up its tree, so this returned Err, the
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
        // Created when missing rather than falling through to Err. The backend makes this
        // directory when it publishes the token, so it exists wherever a backend has ever run --
        // but an app opened BEFORE its first backend start would otherwise have no storage root at
        // all, and therefore nowhere to write the log that says so.
        if !user_root.is_dir() {
            let _ = std::fs::create_dir_all(&user_root);
        }
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
    // 🔴 Deliberately NOT the bundle identifier `com.kmti.draftcheck`, which this was until
    // 2026-08-27. That directory is this app's OWN data directory -- WebView2 keeps its profile
    // there and the uninstaller deletes it -- so an uninstall/reinstall cycle removed the token
    // the backend had published, and every authenticated request 401'd until the backend was
    // restarted. Observed in the access log: 401 on POST and GET /api/v1/rooms at 05:16, healthy
    // again at 05:18 only because a diagnostic re-ran token initialisation. A sibling directory
    // survives the uninstall and does not collide with the webview's storage.
    //
    // Mirrors TOKEN_DIR_NAME in services/backend/core/security.py; pinned by
    // tests/test_user_token_dir.py.
    const TOKEN_DIR_NAME: &str = "draftcheck";

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

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::sync::Mutex;

    /// A unique scratch directory. `env::temp_dir()` is shared, and these tests create sibling
    /// trees with the same shape, so a fixed name makes them fail only when run together.
    fn scratch(tag: &str) -> PathBuf {
        let unique = format!(
            "draftcheck-storage-root-{}-{}-{:?}",
            tag,
            std::process::id(),
            std::thread::current().id()
        );
        let dir = env::temp_dir().join(unique);
        let _ = fs::remove_dir_all(&dir);
        fs::create_dir_all(&dir).expect("could not create scratch directory");
        dir
    }

    #[test]
    fn a_bare_storage_directory_is_not_this_projects_storage() {
        // 🔴 The 2026-08-28 defect in one assertion: `C:\storage` is a directory named `storage`
        // with a `secure/.api-token` inside it, and nothing else about it says this project.
        let root = scratch("bare");
        fs::create_dir_all(root.join("storage").join("secure")).unwrap();

        assert!(
            !looks_like_checkout(&root),
            "a directory is being treated as a checkout on the strength of a `storage` child"
        );

        let _ = fs::remove_dir_all(&root);
    }

    /// `find_storage_root` reads the process working directory, which is global. Only the test
    /// below touches it, but it holds this while it does so a future one cannot interleave.
    static CWD_LOCK: Mutex<()> = Mutex::new(());

    #[test]
    fn the_ascent_does_not_bind_to_a_storage_directory_outside_the_project() {
        // The shipped defect, reproduced: an install five directories deep, with a `storage` at
        // the top of the tree that belongs to nothing. Before the marker check this returned that
        // directory, and the app read a token from it that the running backend had never issued.
        let _guard = CWD_LOCK.lock().unwrap_or_else(|poisoned| poisoned.into_inner());

        let root = scratch("escape");
        let stray = root.join("storage");
        fs::create_dir_all(stray.join("secure")).unwrap();

        let install = root
            .join("Users")
            .join("someone")
            .join("AppData")
            .join("Local")
            .join("DraftCheck");
        fs::create_dir_all(&install).unwrap();

        let previous = env::current_dir().unwrap();
        env::set_current_dir(&install).unwrap();
        let resolved = find_storage_root();
        env::set_current_dir(previous).unwrap();

        if let Ok(found) = resolved {
            assert_ne!(
                found.canonicalize().ok(),
                stray.canonicalize().ok(),
                "the search escaped the install and bound to an unrelated `storage` directory"
            );
        }

        let _ = fs::remove_dir_all(&root);
    }

    #[test]
    fn the_ascent_still_finds_the_storage_of_a_real_checkout() {
        // The other half: gating the search must not stop a developer's app resolving to the
        // repository's own storage, which is what every non-installed run depends on.
        let _guard = CWD_LOCK.lock().unwrap_or_else(|poisoned| poisoned.into_inner());

        let checkout = scratch("checkout");
        fs::write(checkout.join("pyproject.toml"), "").unwrap();
        fs::create_dir_all(checkout.join("storage").join("secure")).unwrap();
        let nested = checkout.join("apps").join("desktop").join("src-tauri");
        fs::create_dir_all(&nested).unwrap();

        let previous = env::current_dir().unwrap();
        env::set_current_dir(&nested).unwrap();
        let resolved = find_storage_root();
        env::set_current_dir(previous).unwrap();

        assert_eq!(
            resolved.unwrap().canonicalize().unwrap(),
            checkout.join("storage").canonicalize().unwrap()
        );

        let _ = fs::remove_dir_all(&checkout);
    }

    #[test]
    fn a_python_project_root_is_a_checkout() {
        let root = scratch("pyproject");
        fs::write(root.join("pyproject.toml"), "[tool.pytest.ini_options]\n").unwrap();

        assert!(looks_like_checkout(&root));

        let _ = fs::remove_dir_all(&root);
    }

    #[test]
    fn the_two_service_directories_also_identify_a_checkout() {
        // The second marker exists because `pyproject.toml` is one deletion away from turning
        // every developer's checkout into an installed build.
        let root = scratch("services");
        fs::create_dir_all(root.join("services").join("backend")).unwrap();
        fs::create_dir_all(root.join("apps").join("desktop")).unwrap();

        assert!(looks_like_checkout(&root));

        let _ = fs::remove_dir_all(&root);
    }

    #[test]
    fn one_marker_alone_is_not_enough_for_the_pair() {
        let root = scratch("half");
        fs::create_dir_all(root.join("services").join("backend")).unwrap();

        assert!(
            !looks_like_checkout(&root),
            "`services/backend` alone matches any Python service tree, not this repository"
        );

        let _ = fs::remove_dir_all(&root);
    }

    #[test]
    fn a_file_named_storage_is_not_a_storage_root() {
        let root = scratch("file");
        fs::write(root.join("pyproject.toml"), "").unwrap();
        fs::write(root.join("storage"), "not a directory").unwrap();

        // `looks_like_checkout` says yes; `is_dir()` in the caller is what rejects it. Pinned so
        // the two halves of the condition are not collapsed into one.
        assert!(looks_like_checkout(&root));
        assert!(!root.join("storage").is_dir());

        let _ = fs::remove_dir_all(&root);
    }

    #[test]
    fn the_user_data_root_ends_with_the_published_token_directory() {
        // Mirrors tests/test_user_token_dir.py, which parses this file. Asserted here too so a
        // `cargo test` run catches a drift without the Python suite.
        //
        // ⚠ Deliberately does NOT spell out the bundle identifier to assert inequality against
        // it: that Python test fails if this file mentions the identifier at all, since the
        // previous defect was joining a path from it. Naming it here to prove it is unused is
        // indistinguishable, to a grep, from using it.
        if let Some(root) = user_app_data_root() {
            assert_eq!(root.file_name().unwrap(), "draftcheck");
        }
    }
}
