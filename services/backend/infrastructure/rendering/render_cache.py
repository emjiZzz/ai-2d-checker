import hashlib
import json
from pathlib import Path
from typing import Any

from ...config import settings
from ...logger import logger


class RenderCache:
    """
    Manages local file-based caching for heavy geometry serialization payloads.
    Prevents re-processing DXF entities on every frontend load.
    """
    
    @staticmethod
    def _get_cache_path(drawing_id: str) -> Path:
        cache_dir = Path(settings.STORAGE_ROOT) / "cache" / "render"
        cache_dir.mkdir(parents=True, exist_ok=True)
        # Use simple hash of ID to prevent path traversal
        safe_hash = hashlib.md5(drawing_id.encode()).hexdigest()
        return cache_dir / f"{safe_hash}.json"

    @staticmethod
    def get_cached_payload(drawing_id: str) -> dict[str, Any] | None:
        cache_file = RenderCache._get_cache_path(drawing_id)
        if cache_file.exists():
            try:
                with open(cache_file) as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Render cache read failed: {e}")
        return None

    @staticmethod
    def set_cached_payload(drawing_id: str, payload: dict[str, Any]) -> None:
        cache_file = RenderCache._get_cache_path(drawing_id)
        try:
            with open(cache_file, "w") as f:
                json.dump(payload, f)
            logger.debug(f"Saved render cache for drawing {drawing_id}")
        except Exception as e:
            logger.error(f"Render cache write failed: {e}")
            
    @staticmethod
    def invalidate(drawing_id: str) -> None:
        cache_file = RenderCache._get_cache_path(drawing_id)
        if cache_file.exists():
            cache_file.unlink()
            logger.info(f"Invalidated render cache for drawing {drawing_id}")
