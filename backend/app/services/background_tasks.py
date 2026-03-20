"""
Background task processor for document ingestion.

Provides BackgroundProcessor class that manages an asyncio queue for processing
documents with retry logic and graceful shutdown.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

from .document_processor import DocumentProcessor, DocumentProcessingError
from .llm_client import LLMClient
from .vector_store import VectorStore
from .embeddings import EmbeddingService
from .maintenance import MaintenanceService
from ..models.database import SQLiteConnectionPool


logger = logging.getLogger(__name__)

# Singleton instance
_processor_instance: Optional["BackgroundProcessor"] = None


def get_background_processor(
    max_retries: int = 3,
    retry_delay: float = 1.0,
    chunk_size_chars: int = 2000,
    chunk_overlap_chars: int = 200,
    vector_store: Optional[VectorStore] = None,
    embedding_service: Optional[EmbeddingService] = None,
    maintenance_service: Optional[MaintenanceService] = None,
    pool: Optional["SQLiteConnectionPool"] = None,
    llm_client: Optional[LLMClient] = None,
) -> "BackgroundProcessor":
    """
    Get or create the singleton BackgroundProcessor instance.

    This factory function ensures that only one BackgroundProcessor exists
    across the entire application lifecycle, preventing the issue where
    local instances are created and destroyed in request handlers.

    Args:
        max_retries: Maximum retry attempts for failed tasks (default: 3)
        retry_delay: Base delay in seconds between retries (default: 1.0)
        chunk_size_chars: Target chunk size in characters for DocumentProcessor
        chunk_overlap_chars: Overlap between chunks in characters for DocumentProcessor
        vector_store: VectorStore instance for document storage
        embedding_service: EmbeddingService instance for generating embeddings
        maintenance_service: MaintenanceService instance for maintenance mode checks
        pool: SQLiteConnectionPool instance for database connections
        llm_client: LLMClient instance for contextual chunking

    Returns:
        The singleton BackgroundProcessor instance
    """
    global _processor_instance
    if _processor_instance is None:
        _processor_instance = BackgroundProcessor(
            max_retries=max_retries,
            retry_delay=retry_delay,
            chunk_size_chars=chunk_size_chars,
            chunk_overlap_chars=chunk_overlap_chars,
            vector_store=vector_store,
            embedding_service=embedding_service,
            maintenance_service=maintenance_service,
            pool=pool,
            llm_client=llm_client,
        )
        logger.info("Created singleton BackgroundProcessor instance")
    return _processor_instance


def reset_background_processor() -> None:
    """Reset the singleton instance (for testing purposes)."""
    global _processor_instance
    if _processor_instance is not None and _processor_instance.is_running:
        import asyncio
        asyncio.create_task(_processor_instance.stop())
    _processor_instance = None


@dataclass
class TaskItem:
    """
    Represents a task item in the background queue.

    Attributes:
        file_path: Path to the file to process
        attempt: Current attempt count (starts at 1)
        source: Source of the file ('upload', 'scan', 'email')
        email_subject: Subject line for email-sourced files
        email_sender: Sender address for email-sourced files
    """
    file_path: str
    attempt: int = 1
    source: str = 'upload'
    email_subject: Optional[str] = None
    email_sender: Optional[str] = None


class BackgroundProcessor:
    """
    Background task processor using asyncio.Queue for document ingestion.

    Manages a worker loop that processes files using DocumentProcessor with
    retry logic (max 3 attempts). Failed tasks are requeued with exponential
    backoff delay. Provides graceful shutdown via asyncio.Event.

    Attributes:
        max_retries: Maximum number of retry attempts per task
        retry_delay: Base delay in seconds between retries (doubles each attempt)
        queue: asyncio.Queue holding TaskItem objects
        shutdown_event: asyncio.Event for graceful shutdown
        processor: DocumentProcessor instance for file processing
        _worker_task: Reference to the worker coroutine
        _running: Boolean indicating if processor is active
    """

    def __init__(
        self,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        chunk_size_chars: int = 2000,
        chunk_overlap_chars: int = 200,
        vector_store: Optional[VectorStore] = None,
        embedding_service: Optional[EmbeddingService] = None,
        maintenance_service: Optional[MaintenanceService] = None,
        pool: Optional["SQLiteConnectionPool"] = None,
        llm_client: Optional[LLMClient] = None,
    ):
        """
        Initialize the background processor.

        Args:
            max_retries: Maximum retry attempts for failed tasks (default: 3)
            retry_delay: Base delay in seconds between retries (default: 1.0)
            chunk_size_chars: Target chunk size in characters for DocumentProcessor
            chunk_overlap_chars: Overlap between chunks in characters for DocumentProcessor
            vector_store: VectorStore instance for document storage
            embedding_service: EmbeddingService instance for generating embeddings
            maintenance_service: MaintenanceService instance for maintenance mode
            pool: SQLiteConnectionPool instance for database connections
            llm_client: LLMClient instance for contextual chunking
        """
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.queue: asyncio.Queue[TaskItem] = asyncio.Queue()
        self.shutdown_event = asyncio.Event()
        self.processor = DocumentProcessor(
            chunk_size_chars=chunk_size_chars,
            chunk_overlap_chars=chunk_overlap_chars,
            vector_store=vector_store,
            embedding_service=embedding_service,
            pool=pool,
            llm_client=llm_client,
        )
        self._worker_task: Optional[asyncio.Task] = None
        self._running = False
        self.maintenance_service = maintenance_service

    async def start(self) -> None:
        """
        Start the background processor worker loop.

        Creates and starts the worker task that processes items from the queue.
        Safe to call multiple times - will not create duplicate workers.
        """
        if self._running:
            logger.warning("Background processor is already running")
            return

        self._running = True
        self.shutdown_event.clear()
        self._worker_task = asyncio.create_task(self._worker_loop())
        logger.info("Background processor started")

    async def stop(self, timeout: float = 60.0) -> None:
        """
        Stop the background processor gracefully.

        Signals the worker to shut down and waits for it to complete.
        Pending queue items ARE processed before shutdown (up to timeout).

        Args:
            timeout: Maximum time to wait for graceful shutdown (default: 60 seconds)
        """
        if not self._running:
            logger.warning("Background processor is not running")
            return

        logger.info("Stopping background processor...")
        self.shutdown_event.set()

        if self._worker_task:
            try:
                await asyncio.wait_for(self._worker_task, timeout=timeout)
            except asyncio.TimeoutError:
                logger.warning("Worker task did not stop gracefully within timeout, cancelling...")
                self._worker_task.cancel()
                try:
                    await self._worker_task
                except asyncio.CancelledError:
                    pass

        self._running = False
        logger.info("Background processor stopped")

    async def enqueue(
        self,
        file_path: str,
        source: str = 'upload',
        email_subject: Optional[str] = None,
        email_sender: Optional[str] = None,
    ) -> None:
        """
        Add a file to the processing queue.

        Args:
            file_path: Path to the file to process
            source: Source of the file ('upload', 'scan', 'email')
            email_subject: Subject line for email-sourced files
            email_sender: Sender address for email-sourced files

        Note:
            If the processor is not running, the item will still be queued
            and processed when start() is called.
        """
        if self.maintenance_service:
            flag = self.maintenance_service.get_flag()
            if flag and flag.enabled:
                raise DocumentProcessingError("Maintenance mode prevents enqueueing")
        task = TaskItem(
            file_path=file_path,
            attempt=1,
            source=source,
            email_subject=email_subject,
            email_sender=email_sender,
        )
        await self.queue.put(task)
        logger.debug(f"Enqueued file: {file_path}")

    async def _worker_loop(self) -> None:
        """
        Main worker loop that processes items from the queue.

        Continuously processes tasks until shutdown_event is set AND queue is empty.
        Ensures all pending tasks are processed before shutdown.
        Handles retries with exponential backoff on failure.
        """
        while True:
            # Check if we should shutdown: shutdown_event is set AND queue is empty
            if self.shutdown_event.is_set() and self.queue.empty():
                break

            try:
                # Wait for task with timeout to check shutdown periodically
                task = await asyncio.wait_for(
                    self.queue.get(),
                    timeout=0.5
                )
            except asyncio.TimeoutError:
                continue

            if task is None:
                continue

            await self._process_task_wrapper(task)

    async def _process_task_wrapper(self, task: TaskItem) -> None:
        """
        Wrapper for _process_task that ensures task_done() is always called.
        
        This wrapper guarantees queue.task_done() is called even if _process_task
        raises an exception or continues early.
        """
        try:
            await self._process_task(task)
        finally:
            self.queue.task_done()

    async def _process_task(self, task: TaskItem) -> None:
        """
        Process a single task with retry logic.

        Args:
            task: TaskItem containing file path, attempt count, and optional email metadata

        On failure, requeues the task with incremented attempt count
        and exponential backoff delay if retries remain.
        """
        logger.info(f"Processing file: {task.file_path} (attempt {task.attempt})")

        try:
            await self.processor.process_file(
                task.file_path,
                source=task.source,
                email_subject=task.email_subject,
                email_sender=task.email_sender,
            )
            logger.info(f"Successfully processed: {task.file_path}")

        except DocumentProcessingError as e:
            logger.error(f"Processing error for {task.file_path}: {e}")
            await self._handle_failure(task, str(e))

        except Exception as e:
            logger.error(f"Unexpected error processing {task.file_path}: {e}")
            await self._handle_failure(task, str(e))

    async def _handle_failure(self, task: TaskItem, error_message: str) -> None:
        """
        Handle task failure with retry logic.

        Args:
            task: The failed task
            error_message: Error message from the failure

        Requeues the task with incremented attempt count if retries remain,
        otherwise logs the permanent failure.
        """
        if task.attempt < self.max_retries:
            # Calculate exponential backoff delay
            delay = self.retry_delay * (2 ** (task.attempt - 1))
            logger.warning(
                f"Task failed for {task.file_path}, "
                f"retrying in {delay}s (attempt {task.attempt + 1}/{self.max_retries})"
            )

            # Wait before requeuing
            await asyncio.sleep(delay)

            # Requeue with incremented attempt count, preserving metadata
            new_task = TaskItem(
                file_path=task.file_path,
                attempt=task.attempt + 1,
                source=task.source,
                email_subject=task.email_subject,
                email_sender=task.email_sender,
            )
            await self.queue.put(new_task)
        else:
            logger.error(
                f"Task permanently failed for {task.file_path} "
                f"after {self.max_retries} attempts: {error_message}"
            )

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def queue_size(self) -> int:
        return self.queue.qsize()
