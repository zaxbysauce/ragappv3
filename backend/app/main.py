"""
FastAPI application with lifespan context manager.
"""
import asyncio
import logging
import sqlite3
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

logger = logging.getLogger(__name__)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi.middleware import SlowAPIMiddleware
from starlette.responses import Response, FileResponse

from app.api.routes.admin import router as admin_router
from app.api.routes.chat import router as chat_router
from app.api.routes.documents import router as documents_router
from app.api.routes.email import router as email_router
from app.api.routes.health import router as health_router
from app.api.routes.memories import router as memories_router
from app.api.routes.search import router as search_router
from app.api.routes.settings import router as settings_router
from app.api.routes.vaults import router as vaults_router
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
from app.limiter import limiter
from app.middleware.logging import LoggingMiddleware
from app.middleware.maintenance import MaintenanceMiddleware
from app.security import CSRFManager
from fastapi.exceptions import RequestValidationError
from app.api.routes.documents import validation_exception_handler


async def _llm_keepalive_task(llm_client: LLMClient, interval: int = 30):
    """
    Background task to keep LLM model loaded in LM Studio.
    
    LM Studio unloads models when clients disconnect. This task periodically
    sends a ping request to keep the model in memory.
    
    Args:
        llm_client: The LLM client instance
        interval: Seconds between keep-alive pings (default: 30)
    """
    import logging
    logger = logging.getLogger(__name__)
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
                        setattr(settings, key, bool(json.loads(persisted[key])))
                    elif expected_type == int:
                        setattr(settings, key, int(json.loads(persisted[key])))
                    elif expected_type == float:
                        setattr(settings, key, float(json.loads(persisted[key])))
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
                        setattr(settings, key, raw)
                    elif expected_type == bool:
                        setattr(settings, key, str(raw).lower() in ("true", "1", "yes", "on"))
                    elif expected_type == int:
                        setattr(settings, key, int(raw))
                    elif expected_type == float:
                        setattr(settings, key, float(raw))
                    else:
                        setattr(settings, key, raw)
                except Exception as e:
                    logger.warning(f"Failed to restore persisted setting {key}: {e}")
    except sqlite3.OperationalError:
        pass  # Table doesn't exist yet on first run
    finally:
        conn.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events."""
    # Startup: Initialize database and services
    run_migrations(str(settings.sqlite_path))
    _load_persisted_settings(str(settings.sqlite_path))

    # Migrate uploads to per-vault directories (run before accepting requests)
    try:
        from app.services.upload_path import migrate_uploads
        import asyncio
        logger.info("Checking for upload migration...")
        await asyncio.to_thread(migrate_uploads, False)
    except Exception as e:
        logger.warning(f"Upload migration failed (continuing anyway): {e}")

    app.state.db_pool = get_pool(str(settings.sqlite_path), max_size=10)
    app.state.llm_client = LLMClient()
    await app.state.llm_client.start()
    app.state.embedding_service = EmbeddingService()
    app.state.vector_store = VectorStore()
    app.state.vector_store.connect()
    app.state.vector_store.migrate_add_vault_id()

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
        validation_result = app.state.vector_store.validate_schema(embedding_model_id, embedding_dim)
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
    app.state.csrf_manager = CSRFManager(settings.redis_url, settings.csrf_token_ttl)
    app.state.maintenance_service = MaintenanceService(app.state.db_pool)
    app.state.llm_health_checker = LLMHealthChecker(
        embedding_service=app.state.embedding_service,
        llm_client=app.state.llm_client,
    )
    app.state.model_checker = ModelChecker()
    app.state.model_validation = (
        settings.enable_model_validation
        or app.state.toggle_manager.get_toggle("model_validation", settings.enable_model_validation)
    )
    # Initialize background processor as singleton (runs continuously)
    app.state.background_processor = get_background_processor(
        max_retries=3,
        retry_delay=1.0,
        chunk_size_chars=settings.chunk_size_chars,
        chunk_overlap_chars=settings.chunk_overlap_chars,
        vector_store=app.state.vector_store,
        embedding_service=app.state.embedding_service,
        maintenance_service=app.state.maintenance_service,
        pool=app.state.db_pool,
        llm_client=app.state.llm_client,
    )
    await app.state.background_processor.start()
    
    # Initialize email ingestion service if enabled
    app.state.email_service = EmailIngestionService(
        settings=settings,
        pool=app.state.db_pool,
        background_processor=app.state.background_processor,
    )
    await app.state.email_service.start_polling()
    
    # Start FileWatcher for auto-scanning directories
    app.state.file_watcher = FileWatcher(app.state.background_processor, pool=app.state.db_pool)
    await app.state.file_watcher.start()
    
    # Start LLM keep-alive task to prevent LM Studio from unloading model
    keepalive_task = asyncio.create_task(_llm_keepalive_task(app.state.llm_client))
    
    yield
    
    # Shutdown: Cancel keepalive, stop file watcher, and close services
    # Stop email ingestion service
    app.state.email_service.stop_polling()
    keepalive_task.cancel()
    try:
        await keepalive_task
    except asyncio.CancelledError:
        pass
    await app.state.file_watcher.stop()
    await app.state.background_processor.stop()
    await app.state.llm_client.close()
    await app.state.embedding_service.close()
    app.state.vector_store.close()
    app.state.db_pool.close_all()


app = FastAPI(
    title="KnowledgeVault API",
    version="0.1.0",
    description="Self-hosted RAG Knowledge Base API",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(LoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.backend_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Set up rate limiting
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)
# Note: MaintenanceMiddleware is initialized with a lazy getter since
# maintenance_service is only available after lifespan startup
app.state._maintenance_service_getter = lambda: getattr(app.state, 'maintenance_service', None)
app.add_middleware(MaintenanceMiddleware, service_getter=app.state._maintenance_service_getter)

app.include_router(health_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(search_router, prefix="/api")
app.include_router(memories_router, prefix="/api")
app.include_router(documents_router, prefix="/api")
app.include_router(settings_router, prefix="/api")
app.include_router(vaults_router, prefix="/api")
app.include_router(admin_router, prefix="/api")
app.include_router(email_router, prefix="/api")

# Register exception handler for validation errors (empty filename)
app.add_exception_handler(RequestValidationError, validation_exception_handler)


@app.get("/health")
async def health_check():
    """Simple health check endpoint for Docker/tooling."""
    return {"status": "ok"}


# Serve frontend static files
from pathlib import Path
static_dir = Path("/app/static")
logger.info(f"Checking for static files at: {static_dir} (exists: {static_dir.exists()})")
if static_dir.exists():
    try:
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
        logger.info(f"Static files mounted successfully from {static_dir}")
    except Exception as e:
        logger.error(f"Failed to mount static files: {e}")
else:
    logger.warning(f"Static directory {static_dir} does not exist - frontend will not be served")
    # List what's in /app to help debug
    try:
        app_contents = list(Path("/app").iterdir()) if Path("/app").exists() else []
        logger.info(f"Contents of /app: {[p.name for p in app_contents]}")
    except Exception as e:
        logger.error(f"Could not list /app contents: {e}")


# Catch-all route for SPA client-side routing
# Serves index.html for any unmatched frontend routes (not API routes)
@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    return FileResponse(str(static_dir / "index.html"))
