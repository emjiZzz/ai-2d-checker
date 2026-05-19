import asyncio
from typing import Optional
from ...logger import logger
from .audit_orchestrator import AuditOrchestrator

class BackgroundAuditQueue:
    """
    Asynchronous FIFO background task worker queue for managing Drawing compliance audits.
    """
    def __init__(self):
        self.queue: asyncio.Queue = asyncio.Queue()
        self.worker_task: Optional[asyncio.Task] = None
        self.orchestrator = AuditOrchestrator()

    def start(self, loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
        """
        Starts the background worker queue process loop.
        """
        if self.worker_task and not self.worker_task.done():
            return
            
        logger.info("Initializing Background Drawing Audit Queue worker...")
        loop = loop or asyncio.get_event_loop()
        self.worker_task = loop.create_task(self._worker())

    async def stop(self) -> None:
        """
        Stops the background worker loop gracefully.
        """
        if self.worker_task:
            logger.info("Stopping Background Drawing Audit Queue worker...")
            self.worker_task.cancel()
            try:
                await self.worker_task
            except asyncio.CancelledError:
                pass
            self.worker_task = None
            logger.info("Background Drawing Audit Queue worker stopped.")

    async def enqueue(self, drawing_id: str, standard_id: str, session_id: str) -> None:
        """
        Adds a standard compliance audit task to the background queue.
        """
        logger.info(f"Enqueuing compliance audit task - Drawing: {drawing_id}, Standard: {standard_id}, Session: {session_id}")
        await self.queue.put((drawing_id, standard_id, session_id))

    async def _worker(self) -> None:
        """
        Continuous worker loop processing enqueued compliance audits.
        """
        logger.info("Background Drawing Audit Queue worker is active and listening for tasks.")
        while True:
            try:
                drawing_id, standard_id, session_id = await self.queue.get()
                logger.info(f"Dequeued compliance audit task - Drawing ID: {drawing_id}, Standard ID: {standard_id}, Session ID: {session_id}. Running orchestrator...")
                
                try:
                    await self.orchestrator.run_audit(drawing_id, standard_id, session_id)
                except Exception as w_err:
                    logger.error(f"Worker failed to execute compliance audit for session {session_id}: {str(w_err)}")
                finally:
                    self.queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error inside background audit queue worker loop: {str(e)}")
                await asyncio.sleep(1.0)  # Avoid hyperactive loops on system/network level faults

# Global Singleton Queue Instance
audit_queue = BackgroundAuditQueue()
