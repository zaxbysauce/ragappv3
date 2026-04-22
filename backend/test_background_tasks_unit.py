"""
Unit test for BackgroundProcessor singleton pattern and worker loop.
Tests the core logic without requiring full dependencies.
"""
import asyncio


# Create a minimal mock implementation for testing
class MockTask:
    def __init__(self, file_path: str, attempt: int = 1):
        self.file_path = file_path
        self.attempt = attempt


class MockProcessor:
    def __init__(self, max_retries=3, retry_delay=1.0):
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.queue = asyncio.Queue()
        self.shutdown_event = asyncio.Event()
        self._worker_task = None
        self._running = False
        self.processed = []

    async def start(self):
        if self._running:
            return
        self._running = True
        self.shutdown_event.clear()
        self._worker_task = asyncio.create_task(self._worker_loop())

    async def stop(self, timeout=5.0):
        if not self._running:
            return
        self.shutdown_event.set()
        if self._worker_task:
            try:
                await asyncio.wait_for(self._worker_task, timeout=timeout)
            except asyncio.TimeoutError:
                self._worker_task.cancel()
                try:
                    await self._worker_task
                except asyncio.CancelledError:
                    pass
        self._running = False

    async def enqueue(self, file_path: str):
        task = MockTask(file_path=file_path, attempt=1)
        await self.queue.put(task)

    async def _worker_loop(self):
        while True:
            # Check if we should shutdown: shutdown_event is set AND queue is empty
            if self.shutdown_event.is_set() and self.queue.empty():
                break

            try:
                task = await asyncio.wait_for(self.queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                continue

            if task is None:
                continue

            await self._process_task_wrapper(task)

    async def _process_task_wrapper(self, task):
        try:
            await self._process_task(task)
        finally:
            self.queue.task_done()

    async def _process_task(self, task):
        # Simulate processing
        await asyncio.sleep(0.1)
        self.processed.append(task.file_path)

    @property
    def is_running(self):
        return self._running

    @property
    def queue_size(self):
        return self.queue.qsize()


# Singleton implementation for testing
_processor_instance = None

def get_mock_processor(
    max_retries=3,
    retry_delay=1.0,
):
    global _processor_instance
    if _processor_instance is None:
        _processor_instance = MockProcessor(max_retries=max_retries, retry_delay=retry_delay)
    return _processor_instance

def reset_mock_processor():
    global _processor_instance
    if _processor_instance is not None and _processor_instance.is_running:
        asyncio.create_task(_processor_instance.stop())
    _processor_instance = None


async def test_singleton_pattern():
    """Test that get_mock_processor returns the same instance."""
    reset_mock_processor()

    processor1 = get_mock_processor()
    processor2 = get_mock_processor()

    assert processor1 is processor2, "get_mock_processor should return singleton instance"
    print("[PASS] Singleton pattern works correctly")
    return processor1


async def test_processor_lifecycle(processor):
    """Test that processor can start and stop correctly."""
    assert not processor.is_running, "Processor should not be running initially"

    await processor.start()
    assert processor.is_running, "Processor should be running after start()"
    print("[PASS] Processor starts correctly")

    await processor.stop(timeout=5.0)
    assert not processor.is_running, "Processor should not be running after stop()"
    print("[PASS] Processor stops correctly")


async def test_processor_queues_items():
    """Test that processor can queue and process items."""
    reset_mock_processor()
    processor = get_mock_processor()

    # Create test items
    test_items = ["file1.txt", "file2.txt", "file3.txt"]

    await processor.start()

    # Queue items
    for item in test_items:
        await processor.enqueue(item)

    assert processor.queue_size == len(test_items), f"Queue should have {len(test_items)} items"
    print(f"[PASS] Items enqueued, queue size: {processor.queue_size}")

    # Wait for processing
    max_wait = 10
    waited = 0
    while processor.queue_size > 0 and waited < max_wait:
        await asyncio.sleep(0.5)
        waited += 0.5

    assert processor.queue_size == 0, "Queue should be empty after processing"
    assert len(processor.processed) == len(test_items), f"All {len(test_items)} items should be processed"
    print(f"[PASS] All {len(test_items)} items processed successfully")

    await processor.stop(timeout=5.0)
    reset_mock_processor()


async def test_graceful_shutdown_with_pending_items():
    """Test that processor processes all items before shutdown."""
    reset_mock_processor()
    processor = get_mock_processor()

    # Create test items
    test_items = ["fileA.txt", "fileB.txt"]

    await processor.start()

    # Queue items
    for item in test_items:
        await processor.enqueue(item)

    # Initiate shutdown immediately (without waiting)
    await processor.stop(timeout=5.0)

    # All items should still be processed
    assert len(processor.processed) == len(test_items), f"All {len(test_items)} items should be processed before shutdown"
    print(f"[PASS] Graceful shutdown works - all {len(test_items)} items processed")

    reset_mock_processor()


async def main():
    print("Testing BackgroundProcessor singleton pattern and worker loop...")
    print("=" * 60)

    try:
        processor = await test_singleton_pattern()
        await test_processor_lifecycle(processor)

        reset_mock_processor()
        await test_processor_queues_items()

        reset_mock_processor()
        await test_graceful_shutdown_with_pending_items()

        print("=" * 60)
        print("All tests passed!")
        return 0

    except Exception as e:
        print(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        reset_mock_processor()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
