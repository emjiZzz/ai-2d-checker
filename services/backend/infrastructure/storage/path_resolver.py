import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Resolve root to: ai-2d-checker/storage -- or, in a frozen build, beside the executable.
#
# 🔴 This counted five `.parent`s from `__file__`, which lands inside PyInstaller's temp unpack
# directory once frozen. The OS deletes that on exit, so every uploaded drawing and rendering
# would have been written to a folder that vanishes at shutdown, with no error anywhere.
# STORAGE_ROOT is still honoured first, so an operator can point it at a NAS share.
from ...runtime_paths import app_root

ROOT_DIR = app_root()
def _resolve_storage_root() -> Path:
    r"""`STORAGE_ROOT` if set, anchored to the app root when it is relative.

    ⚠ A RELATIVE override must not be resolved against the working directory. `.env` ships
    `STORAGE_ROOT=./storage`, and the frozen server is launched by an operator from whatever
    directory they happen to be in -- launched from `C:\`, a bare `Path("./storage")` put the
    entire data root, API token included, in `C:\storage`. Observed on the first frozen boot:
    the banner read `Storage: storage` and the token was written to `storage\secure\.api-token`.

    An ABSOLUTE override is honoured as given, which is what lets the server point at
    `\KMTI-NAS\Shared\...` without a rebuild.
    """
    override = os.getenv("STORAGE_ROOT")
    if not override:
        return ROOT_DIR / "storage"
    candidate = Path(override)
    return candidate if candidate.is_absolute() else (ROOT_DIR / candidate).resolve()


STORAGE_ROOT = _resolve_storage_root()

def get_storage_root() -> Path:
    return STORAGE_ROOT

def bootstrap_storage() -> bool:
    folders = [
        "secure",
        "uploads",
        "cache",
        "temp",
        "quarantine",
        "redlines",
        "reports",
        "logs/backend",
        "logs/app",
    ]  
    
    try:
        STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
        for folder in folders:
            folder_path = STORAGE_ROOT / folder
            folder_path.mkdir(parents=True, exist_ok=True)
            
            # Write permission validation
            test_file = folder_path / ".write_test"
            test_file.write_text("test")
            test_file.unlink()
            
        return True
    except Exception as e:
        logger.critical(f"Storage bootstrap failed: {e}")
        return False
