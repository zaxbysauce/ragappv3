"""FastAPI dependency functions."""

import sqlite3
from contextlib import contextmanager

from fastapi import Request

from app.config import Settings, settings
from app.models.database import get_pool, SQLiteConnectionPool
from app.services.llm_client import LLMClient
from app.services.embeddings import EmbeddingService
from app.services.vector_store import VectorStore
from app.services.memory_store import MemoryStore
from app.services.reranking import RerankingService
from app.services.rag_engine import RAGEngine
from app.services.secret_manager import SecretManager
from app.services.toggle_manager import ToggleManager
from app.services.background_tasks import BackgroundProcessor
from app.services.maintenance import MaintenanceService
from app.services.llm_health import LLMHealthChecker
from app.services.model_checker import ModelChecker
from app.services.email_service import EmailIngestionService
from app.security import get_csrf_manager


def get_db():
    """Yield a database connection from the pool, releasing it when done."""
    pool = get_pool(str(settings.sqlite_path))
    conn = pool.get_connection()
    try:
        yield conn
    finally:
        pool.release_connection(conn)


def get_db_pool(request: Request) -> SQLiteConnectionPool:
    """Return the database pool from app state."""
    return request.app.state.db_pool


def get_settings() -> Settings:
    """Return the application settings."""
    return settings


def get_llm_client(request: Request) -> LLMClient:
    """Return the LLM client from app state."""
    return request.app.state.llm_client


def get_embedding_service(request: Request) -> EmbeddingService:
    """Return the embedding service from app state."""
    return request.app.state.embedding_service


def get_vector_store(request: Request) -> VectorStore:
    """Return the vector store from app state."""
    return request.app.state.vector_store


def get_memory_store(request: Request) -> MemoryStore:
    """Return the memory store from app state."""
    return request.app.state.memory_store


def get_reranking_service(request: Request):
    """Return the RerankingService from app state."""
    return request.app.state.reranking_service


def get_rag_engine(request: Request) -> RAGEngine:
    """Return the cached RAGEngine singleton from app state."""
    return request.app.state.rag_engine


def get_toggle_manager(request: Request) -> ToggleManager:
    """Return the toggle manager from app state."""
    return request.app.state.toggle_manager


def get_secret_manager(request: Request) -> SecretManager:
    """Return the secret manager from app state."""
    return request.app.state.secret_manager


def get_background_processor(request: Request) -> BackgroundProcessor:
    """Return the background processor from app state."""
    return request.app.state.background_processor


def get_maintenance_service(request: Request) -> MaintenanceService:
    """Return the maintenance service from app state."""
    return request.app.state.maintenance_service


def get_llm_health_checker(request: Request) -> LLMHealthChecker:
    """Return the LLM health checker from app state."""
    return request.app.state.llm_health_checker


def get_model_checker(request: Request) -> ModelChecker:
    """Return the model checker from app state."""
    return request.app.state.model_checker


def get_email_service(request: Request) -> EmailIngestionService:
    """Return the email ingestion service from app state."""
    return request.app.state.email_service
