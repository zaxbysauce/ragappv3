"""FastAPI dependency functions."""

import secrets
import sqlite3
from contextlib import contextmanager

from fastapi import Request, Depends, Header, HTTPException

from app.config import Settings, settings
from app.services.auth_service import decode_access_token
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


async def get_current_active_user(
    authorization: str = Header(None),
    db: sqlite3.Connection = Depends(get_db),
) -> dict:
    """
    FastAPI dependency to get the current authenticated user.

    When users_enabled=False: Validates against admin_secret_token
    When users_enabled=True: Validates JWT token and fetches user from database
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")

    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization scheme")

    parts = authorization.split(" ", 1)
    if len(parts) < 2 or not parts[1].strip():
        raise HTTPException(status_code=401, detail="Token missing")

    token = parts[1].strip()

    # When users are disabled, fall back to admin token authentication
    if not settings.users_enabled:
        DEFAULT_TOKEN = "admin-secret-token"

        if not settings.admin_secret_token and secrets.compare_digest(
            token, DEFAULT_TOKEN
        ):
            raise HTTPException(
                status_code=403,
                detail="Invalid credentials - change default admin token",
            )

        if not secrets.compare_digest(token, settings.admin_secret_token):
            raise HTTPException(status_code=403, detail="Invalid credentials")

        return {
            "id": 0,
            "username": "admin",
            "full_name": "Admin",
            "role": "superadmin",
            "is_active": True,
        }

    # User authentication enabled - validate JWT token
    payload = decode_access_token(token)

    if not payload:
        raise HTTPException(status_code=403, detail="Invalid or expired token")

    user_id = int(payload.get("sub", 0))
    if not user_id:
        raise HTTPException(status_code=403, detail="Invalid token payload")

    cursor = db.execute(
        "SELECT id, username, full_name, role, is_active FROM users WHERE id = ?",
        (user_id,),
    )
    row = cursor.fetchone()

    if not row:
        raise HTTPException(status_code=403, detail="User not found")

    user = {
        "id": row[0],
        "username": row[1],
        "full_name": row[2] or "",
        "role": row[3],
        "is_active": bool(row[4]),
    }

    if not user["is_active"]:
        raise HTTPException(status_code=403, detail="User account is inactive")

    return user


async def evaluate_policy(
    principal: dict,
    resource_type: str,
    resource_id: int | None,
    action: str,
) -> bool:
    """
    Centralized policy evaluation for RBAC.

    Resolution order (vault resources):
    1. superadmin -> True for all actions
    2. admin -> True for read/write, False for vault delete
    3. vault_members row -> use permission column
    4. vault_group_access (user in group) -> highest permission wins
    5. vault.visibility == 'public' AND action == 'read' -> True
    6. Otherwise -> False
    """
    user_id = principal.get("id")
    user_role = principal.get("role", "")

    if user_id is None:
        return False

    if resource_type != "vault":
        return user_role == "superadmin"

    if resource_id is None:
        return False

    if user_role == "superadmin":
        return True

    if user_role == "admin":
        if action in ("read", "write"):
            return True
        return False

    pool = get_pool(str(settings.sqlite_path))
    conn = pool.get_connection()

    try:
        # Check vault_members for direct user permission
        cursor = conn.execute(
            "SELECT permission FROM vault_members WHERE vault_id = ? AND user_id = ?",
            (resource_id, user_id),
        )
        row = cursor.fetchone()

        if row:
            permission_levels = {"read": 1, "write": 2, "admin": 3}
            action_levels = {"read": 1, "write": 2, "delete": 3, "admin": 3}

            required_level = action_levels.get(action, 1)
            user_level = permission_levels.get(row[0], 0)

            if user_level >= required_level:
                return True

        # Check vault_group_access for group-based permissions
        cursor = conn.execute(
            """SELECT vga.permission FROM vault_group_access vga
               JOIN group_members gm ON vga.group_id = gm.group_id
               WHERE vga.vault_id = ? AND gm.user_id = ?""",
            (resource_id, user_id),
        )
        group_permissions = cursor.fetchall()

        if group_permissions:
            permission_levels = {"read": 1, "write": 2, "admin": 3}
            action_levels = {"read": 1, "write": 2, "delete": 3, "admin": 3}

            highest_level = max(
                permission_levels.get(p[0], 0) for p in group_permissions
            )
            required_level = action_levels.get(action, 1)

            if highest_level >= required_level:
                return True

        # Check vault visibility for public read access
        if action == "read":
            cursor = conn.execute(
                "SELECT visibility FROM vaults WHERE id = ?", (resource_id,)
            )
            row = cursor.fetchone()

            if row and row[0] == "public":
                return True

        return False

    finally:
        pool.release_connection(conn)


def require_vault_permission(*actions: str):
    """
    FastAPI dependency for vault permission checks.

    Creates a dependency that validates the current user has at least
    one of the specified permissions on the given vault.

    Usage: Depends(require_vault_permission("read", "admin"))
    """

    async def _check(vault_id: int, user: dict = Depends(get_current_active_user)):
        for action in actions:
            if await evaluate_policy(user, "vault", vault_id, action):
                return user
        raise HTTPException(status_code=403, detail="Insufficient vault permissions")

    return _check


def require_role(role: str):
    """
    FastAPI dependency to require a specific role or higher.

    Role hierarchy: superadmin(4) > admin(3) > member(2) > viewer(1)

    Usage: Depends(require_role("admin"))
    """
    role_hierarchy = {
        "superadmin": 4,
        "admin": 3,
        "member": 2,
        "viewer": 1,
    }

    required_level = role_hierarchy.get(role, 0)

    async def _check_role(user: dict = Depends(get_current_active_user)) -> dict:
        user_role = user.get("role", "viewer")
        user_level = role_hierarchy.get(user_role, 0)

        if user_level < required_level:
            raise HTTPException(
                status_code=403,
                detail=f"Insufficient privileges. Required role: {role}",
            )

        return user

    return _check_role
