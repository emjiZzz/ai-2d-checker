from pathlib import Path
from .path_resolver import get_storage_root, is_nas_storage, check_storage_reachability

def get_storage_diagnostics() -> dict:
    storage_root = Path(get_storage_root())
    is_nas = is_nas_storage()
    reachable = check_storage_reachability()
    write_permission = reachable

    return {
        "write_permission": write_permission,
        "reachable": reachable,
        "is_nas": is_nas,
        "fallback_target": "client_pc",
        "root_path": str(storage_root)
    }

