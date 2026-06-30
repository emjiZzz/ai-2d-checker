import os
import time
from pathlib import Path
from .path_resolver import get_storage_root

def purge_temp_files(max_age_seconds: int = 3600) -> int:
    temp_dir = get_storage_root() / "temp"
    if not temp_dir.exists():
        return 0
    count = 0
    now = time.time()
    for item in temp_dir.iterdir():
        if item.is_file() and (now - item.stat().st_mtime) > max_age_seconds:
            try:
                item.unlink()
                count += 1
            except Exception:
                pass
    return count

def purge_cache_files() -> int:
    cache_dir = get_storage_root() / "cache"
    if not cache_dir.exists():
        return 0
    count = 0
    for item in cache_dir.iterdir():
        if item.is_file():
            try:
                item.unlink()
                count += 1
            except Exception:
                pass
    return count
