import asyncio
from typing import Optional
from ...logger import logger
from .extraction_pipeline import ExtractionPipeline

class BackgroundProcessingQueue:
    """
    Asynchronous FIFO background task worker queue for managing CAD drawing ingestion tasks.
    """
    def __init__(self):
        self.queue: asyncio.Queue = asyncio.Queue()
        self.worker_task: Optional[asyncio.Task] = None
        self.pipeline = ExtractionPipeline()

    def start(self, loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
        """
        Starts the background worker queue process loop.
        """
        if self.worker_task and not self.worker_task.done():
            return
            
        logger.info("Initializing Background CAD Processing Queue worker...")
        loop = loop or asyncio.get_event_loop()
        self.worker_task = loop.create_task(self._worker())

    async def stop(self) -> None:
        """
        Stops the background worker loop gracefully.
        """
        if self.worker_task:
            logger.info("Stopping Background CAD Processing Queue worker...")
            self.worker_task.cancel()
            try:
                await self.worker_task
            except asyncio.CancelledError:
                pass
            self.worker_task = None
            logger.info("Background CAD Processing Queue worker stopped.")

    async def enqueue(self, drawing_id: str, job_id: str) -> None:
        """
        Adds a CAD drawing extraction task to the background queue.
        """
        logger.info(f"Enqueuing processing task - Drawing: {drawing_id}, Job: {job_id}")
        await self.queue.put((drawing_id, job_id))

    async def _worker(self) -> None:
        """
        Continuous worker loop processing enqueued CAD extraction tasks.
        """
        logger.info("Background CAD Processing Queue worker is active and listening for tasks.")
        while True:
            try:
                drawing_id, job_id = await self.queue.get()
                logger.info(f"Dequeued task: Drawing ID: {drawing_id}, Job ID: {job_id}. Running pipeline...")
                
                try:
                    await self.pipeline.run(drawing_id, job_id)
                except Exception as w_err:
                    logger.error(f"Worker failed to execute extraction pipeline for drawing {drawing_id}: {str(w_err)}")
                finally:
                    self.queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error inside background queue worker loop: {str(e)}")
                await asyncio.sleep(1.0)  # Avoid hyperactive loops on system/network level faults

# Global Singleton Queue Instance
processing_queue = BackgroundProcessingQueue()
