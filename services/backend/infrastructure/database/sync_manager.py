import asyncio
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pymongo import MongoClient, ReplaceOne
from ...config import settings
from ...logger import logger

SYNC_COLLECTIONS = [
    "clients",
    "zone_templates",
    "audit_feedback",
    "standard_documents",
    "standard_chunks",
    "user_accounts",
    "rooms",
    "drawing_documents",
    "audit_sessions",
    "extraction_jobs",
    "annotations",
    "audit_violations",
    "extracted_entities",
]


class DatabaseSyncManager:
    """
    Handles bidirectional synchronization between Local MongoDB and Cloud MongoDB Atlas.
    Provides automatic fallback, offline queuing, background sync worker, and manual triggers.
    """

    def __init__(self):
        self._is_running = False
        self._task: Optional[asyncio.Task] = None
        self._last_sync_time: Optional[float] = None
        self._last_sync_status: str = "never_run"
        self._last_sync_metrics: Dict[str, Any] = {}
        self._lock = asyncio.Lock()

    def test_connection(self, uri: str, timeout_ms: int = 4000) -> bool:
        """Test if a MongoDB URI is reachable and responds to a ping."""
        try:
            client = MongoClient(uri, serverSelectionTimeoutMS=timeout_ms)
            client.admin.command("ping")
            client.close()
            return True
        except Exception:
            return False

    def is_cloud_configured(self) -> bool:
        """Returns True if MONGO_URI is a cloud connection string and differs from fallback."""
        primary = settings.MONGO_URI.strip()
        fallback = getattr(settings, "MONGO_FALLBACK_URI", "mongodb://127.0.0.1:27017").strip()
        return bool(primary and ("mongodb+srv://" in primary or primary != fallback))

    async def sync_all(self, force: bool = False) -> Dict[str, Any]:
        """
        Perform a full bidirectional sync between Local MongoDB and Cloud MongoDB.
        Uses non-blocking thread execution to avoid stalling the async event loop.
        """
        async with self._lock:
            if not self.is_cloud_configured():
                return {
                    "success": False,
                    "message": "Cloud MongoDB URI is not configured or identical to local URI.",
                    "timestamp": time.time(),
                }

            start_time = time.time()
            try:
                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(None, self._sync_sync_worker)
                self._last_sync_time = time.time()
                self._last_sync_status = "success"
                self._last_sync_metrics = result
                duration_sec = round(time.time() - start_time, 2)
                result["duration_seconds"] = duration_sec
                logger.info(f"[DB Sync] Synchronization completed successfully in {duration_sec}s.")
                return {"success": True, "data": result, "timestamp": self._last_sync_time}
            except Exception as e:
                self._last_sync_status = f"failed: {str(e)}"
                logger.warning(f"[DB Sync] Synchronization failed: {str(e)}")
                return {
                    "success": False,
                    "error": str(e),
                    "timestamp": time.time(),
                }

    def _sync_sync_worker(self) -> Dict[str, Any]:
        """Synchronous worker that performs the bidirectional document replication."""
        local_uri = getattr(settings, "MONGO_FALLBACK_URI", "mongodb://127.0.0.1:27017")
        cloud_uri = settings.MONGO_URI

        local_client = MongoClient(local_uri, serverSelectionTimeoutMS=4000)
        cloud_client = MongoClient(cloud_uri, serverSelectionTimeoutMS=6000)

        # Confirm connectivity
        local_client.admin.command("ping")
        cloud_client.admin.command("ping")

        local_db = local_client[settings.MONGO_DB_NAME]
        cloud_db = cloud_client[settings.MONGO_DB_NAME]

        stats: Dict[str, Any] = {}
        total_pushed = 0
        total_pulled = 0

        for col_name in SYNC_COLLECTIONS:
            local_col = local_db[col_name]
            cloud_col = cloud_db[col_name]

            pushed, pulled = self._sync_single_collection(local_col, cloud_col)
            total_pushed += pushed
            total_pulled += pulled
            stats[col_name] = {"pushed_to_cloud": pushed, "pulled_from_cloud": pulled}

        local_client.close()
        cloud_client.close()

        return {
            "collections": stats,
            "total_pushed_to_cloud": total_pushed,
            "total_pulled_from_cloud": total_pulled,
        }

    def _sync_single_collection(self, local_col, cloud_col) -> tuple[int, int]:
        """
        Bidirectionally synchronize a single collection by document _id and timestamp.
        """
        # Fetch all ids and updated timestamps
        local_docs = {d["_id"]: d for d in local_col.find()}
        cloud_docs = {d["_id"]: d for d in cloud_col.find()}

        to_push = []
        to_pull = []

        # 1. Check local docs against cloud
        for doc_id, l_doc in local_docs.items():
            if doc_id not in cloud_docs:
                to_push.append(l_doc)
            else:
                c_doc = cloud_docs[doc_id]
                l_time = self._extract_doc_time(l_doc)
                c_time = self._extract_doc_time(c_doc)
                if l_time > c_time:
                    to_push.append(l_doc)

        # 2. Check cloud docs against local
        for doc_id, c_doc in cloud_docs.items():
            if doc_id not in local_docs:
                to_pull.append(c_doc)
            else:
                l_doc = local_docs[doc_id]
                l_time = self._extract_doc_time(l_doc)
                c_time = self._extract_doc_time(c_doc)
                if c_time > l_time:
                    to_pull.append(c_doc)

        # Execute push batch
        if to_push:
            ops = [ReplaceOne({"_id": d["_id"]}, d, upsert=True) for d in to_push]
            # Execute in chunks of 500
            for i in range(0, len(ops), 500):
                cloud_col.bulk_write(ops[i:i + 500], ordered=False)

        # Execute pull batch
        if to_pull:
            ops = [ReplaceOne({"_id": d["_id"]}, d, upsert=True) for d in to_pull]
            for i in range(0, len(ops), 500):
                local_col.bulk_write(ops[i:i + 500], ordered=False)

        return len(to_push), len(to_pull)

    def _extract_doc_time(self, doc: Dict[str, Any]) -> float:
        """Extract sortable timestamp from document fields or _id generation time."""
        for field in ("updated_at", "last_updated", "timestamp", "created_at", "annotated_at"):
            val = doc.get(field)
            if isinstance(val, datetime):
                return val.replace(tzinfo=timezone.utc).timestamp()
            if isinstance(val, (int, float)):
                return float(val)
            if isinstance(val, str):
                try:
                    return datetime.fromisoformat(val.replace("Z", "+00:00")).timestamp()
                except Exception:
                    pass

        # Fallback to ObjectId timestamp
        obj_id = doc.get("_id")
        if hasattr(obj_id, "generation_time"):
            return obj_id.generation_time.replace(tzinfo=timezone.utc).timestamp()

        return 0.0

    def start(self) -> None:
        """Start the background periodic auto-sync worker task."""
        if not getattr(settings, "ENABLE_DB_AUTO_SYNC", True) or not self.is_cloud_configured():
            logger.info("[DB Sync] Background auto-sync is disabled or cloud URI not configured.")
            return

        if self._is_running:
            return

        self._is_running = True
        self._task = asyncio.create_task(self._background_loop())
        logger.info("[DB Sync] Background database auto-sync worker started.")

    async def stop(self) -> None:
        """Stop the background auto-sync worker task."""
        self._is_running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("[DB Sync] Background database auto-sync worker stopped.")

    async def _background_loop(self) -> None:
        """Background loop executing periodic sync."""
        interval = getattr(settings, "DB_AUTO_SYNC_INTERVAL_SEC", 60)
        # Initial wait before first background sync
        await asyncio.sleep(5)

        while self._is_running:
            try:
                # Run sync quietly
                await self.sync_all()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"[DB Sync] Background loop encountered error: {e}")

            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break

    def get_status(self) -> Dict[str, Any]:
        """Return diagnostic status of sync manager."""
        return {
            "cloud_configured": self.is_cloud_configured(),
            "auto_sync_enabled": getattr(settings, "ENABLE_DB_AUTO_SYNC", True),
            "sync_interval_seconds": getattr(settings, "DB_AUTO_SYNC_INTERVAL_SEC", 60),
            "is_worker_running": self._is_running,
            "last_sync_time": self._last_sync_time,
            "last_sync_status": self._last_sync_status,
            "last_sync_metrics": self._last_sync_metrics,
        }


sync_manager = DatabaseSyncManager()
