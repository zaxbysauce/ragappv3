"""
Test script to verify the singleton BackgroundProcessor works correctly.
"""
import asyncio
import os
import tempfile
from pathlib import Path

# Set up test environment
temp_dir = tempfile.mkdtemp()
os.environ["DATA_DIR"] = temp_dir
os.environ["UPLOADS_DIR"] = os.path.join(temp_dir, "uploads")
os.environ["VECTOR_DB_DIR"] = os.path.join(temp_dir, "lancedb")
os.makedirs(os.path.join(temp_dir, "uploads"), exist_ok=True)
os.makedirs(os.path.join(temp_dir, "lancedb"), exist_ok=True)

from app.config import settings
from app.services.background_tasks import (
    get_background_processor,
    reset_background_processor,
)


def test_singleton_pattern():
    """Test that get_background_processor returns the same instance."""
    # Reset any existing instance
    reset_background_processor()

    # Get first instance
    processor1 = get_background_processor(
        chunk_size_chars=settings.chunk_size_chars,
        chunk_overlap_chars=settings.chunk_overlap_chars,
    )

    # Get second instance
    processor2 = get_background_processor(
        chunk_size_chars=settings.chunk_size_chars,
        chunk_overlap_chars=settings.chunk_overlap_chars,
    )

    # They should be the same instance
    assert processor1 is processor2, "get_background_processor should return singleton instance"
    print("✓ Singleton pattern works correctly")

    return processor1


async def test_processor_lifecycle(processor):
    """Test that processor can start and stop correctly."""
    # Processor should not be running yet
    assert not processor.is_running, "Processor should not be running initially"

    # Start the processor
    await processor.start()
    assert processor.is_running, "Processor should be running after start()"
    print("✓ Processor starts correctly")

    # Stop the processor
    await processor.stop(timeout=5.0)
    assert not processor.is_running, "Processor should not be running after stop()"
    print("✓ Processor stops correctly")

    # Clean up
    reset_background_processor()


async def test_processor_queues_items(processor):
    """Test that processor can queue and process items."""
    # Create a test file
    test_file = Path(settings.uploads_dir) / "test_document.txt"
    test_file.write_text("This is a test document for background processing.\n" * 10)

    # Start the processor
    await processor.start()

    # Queue the file
    await processor.enqueue(str(test_file))

    # Check queue size
    queue_size = processor.queue_size
    print(f"✓ File enqueued, queue size: {queue_size}")

    # Wait for processing (with timeout)
    max_wait = 10  # seconds
    waited = 0
    while processor.queue_size > 0 and waited < max_wait:
        await asyncio.sleep(0.5)
        waited += 0.5

    # Check queue is empty
    assert processor.queue_size == 0, "Queue should be empty after processing"
    print("✓ File processed successfully")

    # Stop the processor
    await processor.stop(timeout=5.0)

    # Clean up
    reset_background_processor()
    test_file.unlink(missing_ok=True)


async def main():
    print("Testing BackgroundProcessor singleton pattern...")
    print("=" * 50)

    try:
        processor = test_singleton_pattern()
        await test_processor_lifecycle(processor)

        # Reset for queue test
        reset_background_processor()
        processor = get_background_processor(
            chunk_size_chars=settings.chunk_size_chars,
            chunk_overlap_chars=settings.chunk_overlap_chars,
        )
        await test_processor_queues_items(processor)

        print("=" * 50)
        print("All tests passed! ✓")
        return 0

    except Exception as e:
        print(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        # Cleanup
        reset_background_processor()
        try:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
        except:
            pass


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
