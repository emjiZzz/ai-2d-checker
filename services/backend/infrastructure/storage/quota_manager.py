"""
Storage quota management.

Calculates storage consumption and enforces local database and filesystem limits.
"""

import os
from pathlib import Path
from services.backend.config import settings
from services.backend.logger import logger
from .path_resolver import get_storage_root

# Default quota limit: 5 GB
DEFAULT_QUOTA_LIMIT_BYTES = 5 * 1024 * 1024 * 1024

class QuotaManager:
    """
    Tracks and enforces storage usage limits on the engineering design reviewer local filesystems.
    """

    @staticmethod
    def get_storage_usage() -> dict:
        """
        Calculates current directory storage consumption in bytes.

        Returns a dictionary:
            used_bytes         - total bytes used in storage directory
            quota_limit_bytes  - maximum permitted bytes
            usage_percentage   - float percentage of quota used
        """
        root = get_storage_root()
        used_bytes = 0
        quota_limit_bytes = DEFAULT_QUOTA_LIMIT_BYTES

        if root.exists():
            try:
                # Walk the storage directory to compute total size
                used_bytes = sum(f.stat().st_size for f in root.rglob("*") if f.is_file())
            except OSError as exc:
                logger.error(f"Error calculating storage size: {exc}")
                # Fallback to 0 if directory reading fails
                used_bytes = 0

        # Calculate percentage
        if quota_limit_bytes > 0:
            usage_percentage = round((used_bytes / quota_limit_bytes) * 100, 2)
        else:
            usage_percentage = 0.0

        return {
            "used_bytes": used_bytes,
            "quota_limit_bytes": quota_limit_bytes,
            "usage_percentage": usage_percentage
        }

    @staticmethod
    def enforce_limits() -> bool:
        """
        Verifies if storage usage is within limits.
        
        Returns:
            True if we are within the quota limit and operations are safe to proceed.
            False if we have exceeded the quota limit.
        """
        usage = QuotaManager.get_storage_usage()
        if usage["used_bytes"] >= usage["quota_limit_bytes"]:
            logger.warning(
                f"Storage limit exceeded! Used: {usage['used_bytes']} bytes, "
                f"Limit: {usage['quota_limit_bytes']} bytes."
            )
            return False
        return True
