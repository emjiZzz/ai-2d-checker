import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Resolve root to: ai-2d-checker/storage
ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent
STORAGE_ROOT = ROOT_DIR / "storage"

def get_storage_root() -> Path:
    return STORAGE_ROOT

def bootstrap_storage() -> bool:
    folders = [
        "secure",
        "uploads",
        "cache",
        "temp",
        "quarantine",
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
