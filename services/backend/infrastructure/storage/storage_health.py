from pathlib import Path
from .path_resolver import get_storage_root

def get_storage_diagnostics() -> dict:
    storage_root = Path(get_storage_root())
    write_permission = True
    try:
        test_file = storage_root / ".write_test_diag"
        test_file.write_text("test")
        test_file.unlink()
    except Exception:
        write_permission = False

    return {
        "write_permission": write_permission,
        "root_path": str(storage_root)
    }
