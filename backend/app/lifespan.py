"""
Lifespan context manager for FastAPI application startup and shutdown.
"""

import asyncio
import logging
import sqlite3
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.models.database import run_migrations, get_pool
from app.services.llm_client import LLMClient
from app.services.vector_store import VectorStore, VectorStoreError
from app.services.memory_store import MemoryStore
from app.services.embeddings import EmbeddingService
from app.services.reranking import RerankingService
from app.services.secret_manager import SecretManager
from app.services.toggle_manager import ToggleManager
from app.services.maintenance import MaintenanceService
from app.services.background_tasks import get_background_processor
from app.services.file_watcher import FileWatcher
from app.services.llm_health import LLMHealthChecker
from app.services.model_checker import ModelChecker
from app.services.email_service import EmailIngestionService
from app.services.rag_engine import RAGEngine
from app.security import CSRFManager

logger = logging.getLogger(__name__)


async def _llm_keepalive_task(llm_client: LLMClient, interval: int = 30):
    """
    Background task to keep LLM model loaded in LM Studio.

    LM Studio unloads models when clients disconnect. This task periodically
    sends a ping request to keep the model in memory.

    Args:
        llm_client: The LLM client instance
        interval: Seconds between keep-alive pings (default: 30)
    """
    logger.info("Starting LLM keep-alive task (interval: %ds)", interval)

    while True:
        try:
            await asyncio.sleep(interval)
            # Send a simple completion to keep model loaded
            messages = [{"role": "user", "content": "ping"}]
            await llm_client.chat_completion(messages, max_tokens=1)
            logger.debug("LLM keep-alive ping sent successfully")
        except asyncio.CancelledError:
            logger.info("LLM keep-alive task cancelled")
            break
        except Exception as e:
            # Log but don't crash - model might just be unloaded
            logger.debug("LLM keep-alive ping failed (model may be unloaded): %s", e)


def _validate_setting_value(key: str, value) -> bool:
    """Validate a single setting value through Pydantic field validation.

    Returns True if the value is valid, False otherwise.
    """
    try:
        current = settings.model_dump()
        current[key] = value
        type(settings).model_validate(current)
        return True
    except Exception as e:
        logger.warning("Persisted setting %s=%r failed validation: %s", key, value, e)
        return False


def _load_persisted_settings(sqlite_path: str) -> None:
    """Load user-configurable settings from DB if they were previously saved."""
    import json

    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.execute("SELECT key, value FROM settings_kv")
        # Build persisted dict from all rows
        persisted = {row["key"]: row["value"] for row in cursor.fetchall()}

        # Legacy keys — require JSON parsing and type conversion
        legacy_keys = {
            "chunk_size": int,
            "chunk_overlap": int,
            "max_context_chunks": int,
            "auto_scan_interval_minutes": int,
            "auto_scan_enabled": bool,
            "rag_relevance_threshold": float,
        }
        for key, expected_type in legacy_keys.items():
            if key in persisted:
                try:
                    if expected_type == bool:
                        converted = bool(json.loads(persisted[key]))
                    elif expected_type == int:
                        converted = int(json.loads(persisted[key]))
                    elif expected_type == float:
                        converted = float(json.loads(persisted[key]))
                    else:
                        converted = persisted[key]
                    if _validate_setting_value(key, converted):
                        setattr(settings, key, converted)
                except Exception as e:
                    logger.warning(f"Failed to restore persisted setting {key}: {e}")

        # New fields — load directly without legacy conversion
        NEW_DIRECT_KEYS = [
            "chunk_size_chars",
            "chunk_overlap_chars",
            "retrieval_top_k",
            "retrieval_window",
            "max_distance_threshold",
            "vector_metric",
            "embedding_doc_prefix",
            "embedding_query_prefix",
            "embedding_batch_size",
            "reranking_enabled",
            "reranker_top_n",
            "initial_retrieval_top_k",
            "hybrid_search_enabled",
            "hybrid_alpha",
            "reranker_url",
            "reranker_model",
            "embedding_model",
            "chat_model",
            "vector_top_k",
        ]
        for key in NEW_DIRECT_KEYS:
            if key in persisted:
                try:
                    if not hasattr(settings, key):
                        logger.warning(f"Unknown persisted setting {key}, skipping")
                        continue
                    expected_type = type(getattr(settings, key))
                    raw = persisted[key]
                    if expected_type == type(None):  # NoneType - just set as string
                        converted = raw
                    elif expected_type == bool:
                        converted = str(raw).lower() in ("true", "1", "yes", "on")
                    elif expected_type == int:
                        converted = int(raw)
                    elif expected_type == float:
                        converted = float(raw)
                    else:
                        converted = raw
                    if _validate_setting_value(key, converted):
                        setattr(settings, key, converted)
                except Exception as e:
                    logger.warning(f"Failed to restore persisted setting {key}: {e}")
    except sqlite3.OperationalError:
        logger.debug(
            "Settings table not yet created; skipping persisted settings load (expected on first startup)"
        )
    finally:
        conn.close()


async def _safe_await(coro, name, timeout=10):
    """Await a coroutine with a timeout, logging warnings on failure."""
    try:
        await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning(f"{name} timed out after {timeout}s (continuing)")
    except Exception as e:
        logger.warning(f"{name} failed: {e} (continuing)")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events."""
    # Startup: Initialize database and services
    try:
        run_migrations(str(settings.sqlite_path))
    except Exception as e:
        logger.error(
            "Database migration failed: %s — app will start with degraded database state",
            e,
        )
    _load_persisted_settings(str(settings.sqlite_path))

    # Migrate uploads to per-vault directories (run before accepting requests)
    try:
        from app.services.upload_path import migrate_uploads

        logger.info("Checking for upload migration...")
        await asyncio.wait_for(asyncio.to_thread(migrate_uploads, False), timeout=15)
    except Exception as e:
        logger.warning(f"Upload migration failed (continuing anyway): {e}")

    app.state.db_pool = get_pool(str(settings.sqlite_path), max_size=10)
    app.state.llm_client = LLMClient()
    await _safe_await(app.state.llm_client.start(), "LLM client start", timeout=10)
    app.state.embedding_service = EmbeddingService()
    app.state.vector_store = VectorStore()
    await _safe_await(
        app.state.vector_store.connect(), "Vector store connect", timeout=15
    )
    await _safe_await(
        app.state.vector_store.migrate_add_vault_id(),
        "Vector store migrate vault_id",
        timeout=10,
    )
    await _safe_await(
        app.state.vector_store.migrate_add_chunk_scale(),
        "Vector store migrate chunk_scale",
        timeout=10,
    )
    await _safe_await(
        app.state.vector_store.migrate_add_sparse_embedding(),
        "Vector store migrate sparse",
        timeout=10,
    )

    # Initialize RerankingService
    app.state.reranking_service = RerankingService(
        reranker_url=settings.reranker_url,
        reranker_model=settings.reranker_model,
        top_n=settings.reranker_top_n,
    )

    # Validate schema at startup
    try:
        embedding_model_id = settings.embedding_model
        embedding_dim = settings.embedding_dim
        validation_result = app.state.vector_store.validate_schema(
            embedding_model_id, embedding_dim
        )
        logger.info(f"Vector store schema validation completed: {validation_result}")
    except VectorStoreError as e:
        logger.error("=" * 60)
        logger.error("VECTOR STORE SCHEMA VALIDATION FAILED")
        logger.error("=" * 60)
        logger.error(f"Error: {e}")
        logger.error("The embedding dimension has changed. A full reindex is required.")
        logger.error("Please run the reindex process or delete the LanceDB database.")
        logger.error("=" * 60)
        # Continue startup but warn that reindex is needed
    app.state.memory_store = MemoryStore(app.state.db_pool)
    app.state.secret_manager = SecretManager()
    app.state.toggle_manager = ToggleManager(app.state.db_pool)
    try:
        app.state.csrf_manager = CSRFManager(
            settings.redis_url, settings.csrf_token_ttl
        )
    except Exception as e:
        logger.warning(f"CSRF manager init failed (continuing): {e}")
        app.state.csrf_manager = None
    app.state.maintenance_service = MaintenanceService(app.state.db_pool)
    app.state.llm_health_checker = LLMHealthChecker(
        embedding_service=app.state.embedding_service,
        llm_client=app.state.llm_client,
    )
    app.state.model_checker = ModelChecker()
    app.state.model_validation = (
        settings.enable_model_validation
        or app.state.toggle_manager.get_toggle(
            "model_validation", settings.enable_model_validation
        )
    )
    # Initialize background processor as singleton (runs continuously)
    try:
        app.state.background_processor = get_background_processor(
            max_retries=3,
            retry_delay=1.0,
            chunk_size_chars=settings.chunk_size_chars or 2000,
            chunk_overlap_chars=settings.chunk_overlap_chars or 200,
            vector_store=app.state.vector_store,
            embedding_service=app.state.embedding_service,
            maintenance_service=app.state.maintenance_service,
            pool=app.state.db_pool,
            llm_client=app.state.llm_client,
        )
        await _safe_await(
            app.state.background_processor.start(),
            "Background processor start",
            timeout=10,
        )
    except Exception as e:
        logger.warning(f"Background processor start failed (continuing): {e}")
        app.state.background_processor = None

    # Initialize email ingestion service if enabled
    try:
        app.state.email_service = EmailIngestionService(
            settings=settings,
            pool=app.state.db_pool,
            background_processor=app.state.background_processor,
        )
        await _safe_await(
            app.state.email_service.start_polling(), "Email service start", timeout=10
        )
    except Exception as e:
        logger.warning(f"Email service start failed (continuing): {e}")
        app.state.email_service = None

    # Start FileWatcher for auto-scanning directories
    try:
        app.state.file_watcher = FileWatcher(
            app.state.background_processor, pool=app.state.db_pool
        )
        await _safe_await(
            app.state.file_watcher.start(), "FileWatcher start", timeout=10
        )
    except Exception as e:
        logger.warning(f"FileWatcher start failed (continuing): {e}")
        app.state.file_watcher = None

    # Initialize RAGEngine singleton with cached services
    app.state.rag_engine = RAGEngine(
        embedding_service=app.state.embedding_service,
        vector_store=app.state.vector_store,
        memory_store=app.state.memory_store,
        llm_client=app.state.llm_client,
        reranking_service=app.state.reranking_service,
    )
    logger.info("RAGEngine singleton initialized")

    # Start LLM keep-alive task to prevent LM Studio from unloading model
    keepalive_task = None
    try:
        keepalive_task = asyncio.create_task(_llm_keepalive_task(app.state.llm_client))
    except Exception as e:
        logger.warning(f"LLM keepalive task failed (continuing): {e}")

    yield

    # Shutdown: Cancel keepalive, stop file watcher, and close services
    # Stop email ingestion service
    if app.state.email_service:
        app.state.email_service.stop_polling()
    if keepalive_task:
        keepalive_task.cancel()
        try:
            await keepalive_task
        except asyncio.CancelledError:
            pass
    if app.state.file_watcher:
        await app.state.file_watcher.stop()
    if app.state.background_processor:
        await app.state.background_processor.stop()
    try:
        await app.state.llm_client.close()
    except Exception:
        pass
    try:
        await app.state.embedding_service.close()
    except Exception:
        pass
    try:
        await app.state.reranking_service.close()
    except Exception:
        pass
    try:
        app.state.vector_store.close()
    except Exception:
        pass
    try:
        app.state.db_pool.close_all()
    except Exception:
        pass
