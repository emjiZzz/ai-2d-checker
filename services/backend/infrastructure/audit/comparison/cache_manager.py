import json
from pathlib import Path
from typing import Optional, Dict, Any
from ...storage.path_resolver import get_storage_root
from ....logger import logger

class ComparisonCacheManager:
    """Manages serialization and invalidation of structured visual drawing comparisons."""

    @staticmethod
    def _get_cache_path(
        ref_drawing_id: str,
        rev_drawing_id: str,
        ref_hash: str,
        rev_hash: str,
        method: str = "deterministic"
    ) -> Path:
        cache_dir = get_storage_root() / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        # Naming format: gemini_comparison_{method}_{ref_drawing_id}_{rev_drawing_id}_{ref_hash}_{rev_hash}.json
        # `method` distinguishes deterministic vs full_ai results for the same drawing pair so
        # switching a room's comparison_method can't silently serve the other method's cached output.
        # This aligns with api/routers/drawings.py cache invalidation glob/string check, which only
        # substring-matches on drawing_id and doesn't care about the extra segment.
        filename = f"gemini_comparison_{method}_{ref_drawing_id}_{rev_drawing_id}_{ref_hash}_{rev_hash}.json"
        return cache_dir / filename

    @classmethod
    def get_cached_comparison(
        cls,
        ref_drawing_id: str,
        rev_drawing_id: str,
        ref_hash: str,
        rev_hash: str,
        method: str = "deterministic"
    ) -> Optional[Dict[str, Any]]:
        """Retrieves comparison payload if a valid cache hit exists."""
        cache_file = cls._get_cache_path(ref_drawing_id, rev_drawing_id, ref_hash, rev_hash, method)
        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    payload = json.load(f)
                logger.info(f"Comparison cache hit ({method}) for reference {ref_drawing_id} and revision {rev_drawing_id}")
                return payload
            except Exception as e:
                logger.error(f"Failed to read comparison cache: {e}")
        return None

    @classmethod
    def set_cached_comparison(
        cls,
        ref_drawing_id: str,
        rev_drawing_id: str,
        ref_hash: str,
        rev_hash: str,
        payload: Dict[str, Any],
        method: str = "deterministic"
    ) -> None:
        """Saves comparison payload to cache."""
        cache_file = cls._get_cache_path(ref_drawing_id, rev_drawing_id, ref_hash, rev_hash, method)
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            logger.debug(f"Comparison cache stored ({method}) at: {cache_file.name}")
        except Exception as e:
            logger.error(f"Failed to write comparison cache: {e}")

    OCR_CACHE_VERSION = "v1"

    @staticmethod
    def _get_ocr_cache_path(drawing_id: str, file_hash: str) -> Path:
        cache_dir = get_storage_root() / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        # Naming format: title_block_ocr_{OCR_CACHE_VERSION}_{drawing_id}_{file_hash}.json
        filename = f"title_block_ocr_{ComparisonCacheManager.OCR_CACHE_VERSION}_{drawing_id}_{file_hash}.json"
        return cache_dir / filename

    @classmethod
    def get_cached_ocr(cls, drawing_id: str, file_hash: str) -> Optional[Dict[str, Any]]:
        """Retrieves single-drawing OCR key-value payloads if cache exists."""
        cache_file = cls._get_ocr_cache_path(drawing_id, file_hash)
        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    payload = json.load(f)
                logger.info(f"Title block OCR cache hit for drawing {drawing_id}")
                return payload
            except Exception as e:
                logger.error(f"Failed to read title block OCR cache: {e}")
        return None

    @classmethod
    def set_cached_ocr(cls, drawing_id: str, file_hash: str, payload: Dict[str, Any]) -> None:
        """Stores single-drawing OCR findings to cache."""
        cache_file = cls._get_ocr_cache_path(drawing_id, file_hash)
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            logger.debug(f"Title block OCR cache stored at: {cache_file.name}")
        except Exception as e:
            logger.error(f"Failed to write title block OCR cache: {e}")

    @classmethod
    def clear_cache_for_drawing(cls, drawing_id: str) -> None:
        """Removes all cache files associated with a specific drawing."""
        cache_dir = get_storage_root() / "cache"
        if not cache_dir.exists():
            return
            
        count = 0
        try:
            for cache_file in cache_dir.glob("*.json"):
                if drawing_id in cache_file.name:
                    cache_file.unlink()
                    count += 1
            if count > 0:
                logger.info(f"Cleared {count} cache files for drawing {drawing_id}")
        except Exception as e:
            logger.error(f"Failed to clear cache for drawing {drawing_id}: {e}")
