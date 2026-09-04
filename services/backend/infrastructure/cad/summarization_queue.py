import asyncio

from ...logger import logger
from .summarization_pipeline import SummarizationPipeline


class BackgroundSummarizationQueue:
    """
    Asynchronous FIFO background task worker queue for managing AI drawing summarization tasks.
    """
    def __init__(self):
        self.queue: asyncio.Queue = asyncio.Queue()
        self.worker_task: asyncio.Task | None = None
        self.pipeline = SummarizationPipeline()

    def start(self, loop: asyncio.AbstractEventLoop | None = None) -> None:
        """
        Starts the background worker queue process loop.
        """
        if self.worker_task and not self.worker_task.done():
            return
            
        logger.info("Initializing Background AI Summarization Queue worker...")
        loop = loop or asyncio.get_event_loop()
        self.worker_task = loop.create_task(self._worker())

    async def stop(self) -> None:
        """
        Stops the background worker loop gracefully.
        """
        if self.worker_task:
            logger.info("Stopping Background AI Summarization Queue worker...")
            self.worker_task.cancel()
            try:
                await self.worker_task
            except asyncio.CancelledError:
                pass
            self.worker_task = None
            logger.info("Background AI Summarization Queue worker stopped.")

    async def enqueue(self, drawing_id: str) -> None:
        """
        Adds a CAD drawing AI summarization task to the background queue.
        """
        logger.info(f"Enqueuing summarization task - Drawing: {drawing_id}")
        await self.queue.put(drawing_id)

    async def _worker(self) -> None:
        """
        Continuous worker loop processing enqueued CAD summarization tasks.
        """
        logger.info("Background AI Summarization Queue worker is active and listening for tasks.")
        while True:
            try:
                drawing_id = await self.queue.get()
                logger.info(f"Dequeued summarization task: Drawing ID: {drawing_id}. Running pipeline...")
                
                try:
                    await self.pipeline.run(drawing_id)
                except Exception as w_err:
                    logger.error(f"Worker failed to execute summarization pipeline for drawing {drawing_id}: {str(w_err)}")
                finally:
                    self.queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error inside background summarization queue worker loop: {str(e)}")
                await asyncio.sleep(1.0)  # Avoid hyperactive loops on system/network level faults

# Global Singleton Queue Instance
summarization_queue = BackgroundSummarizationQueue()
