"""FastAPI dependency functions."""

from __future__ import annotations

import secrets
import sqlite3
from collections.abc import Callable
from enum import IntEnum
from typing import TYPE_CHECKING

from fastapi import Cookie, Depends, Header, HTTPException, Request

from app.config import Settings, settings
from app.models.database import SQLiteConnectionPool, get_pool
from app.security import get_csrf_manager  # noqa: F401
from app.services.auth_service import (
    TokenExpiredError,
    TokenInvalidError,
    decode_access_token,
)


class UserRole(IntEnum):
    """Canonical role hierarchy used for all authorization checks."""

    VIEWER = 1
    MEMBER = 2
    ADMIN = 3
    SUPERADMIN = 4

    @classmethod
    def level(cls, role_name: str) -> int:
        """Get numeric level for a role string, defaulting to 0 for unknown roles."""
        try:
            return cls[role_name.upper()].value
        except (KeyError, AttributeError):
            return 0


VAULT_PERMISSION_LEVELS = {"read": 1, "write": 2, "admin": 3}
VAULT_PERMISSION_NAMES = {0: None, 1: "read", 2: "write", 3: "admin"}
VAULT_ACTION_LEVELS = {"read": 1, "write": 2, "delete": 3, "admin": 3}


# Lazy imports — services are only loaded when their getter is actually called.
# This prevents heavy imports (unstructured, aioimaplib, torch, etc.) from
# blocking every request handler import chain.
if TYPE_CHECKING:
    from app.services.background_tasks import BackgroundProcessor
    from app.services.email_service import EmailIngestionService
    from app.services.embeddings import EmbeddingService
    from app.services.llm_client import LLMClient
    from app.services.llm_health import LLMHealthChecker
    from app.services.maintenance import MaintenanceService
    from app.services.memory_store import MemoryStore
    from app.services.model_checker import ModelChecker
    from app.services.rag_engine import RAGEngine
    from app.services.secret_manager import SecretManager
    from app.services.toggle_manager import ToggleManager
    from app.services.vector_store import VectorStore


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
    authorization: str | None = Header(None),
    access_token: str | None = Cookie(None),
    db: sqlite3.Connection = Depends(get_db),
) -> dict:
    """
    FastAPI dependency to get the current authenticated user.

    When users_enabled=False: Validates against admin_secret_token
    When users_enabled=True: Validates JWT token and fetches user from database
    """
    # Extract token from Authorization header or fall back to cookie
    if authorization and authorization.lower().startswith("bearer "):
        parts = authorization.split(" ", 1)
        if len(parts) >= 2 and parts[1].strip():
            token = parts[1].strip()
        else:
            token = access_token
    else:
        token = access_token

    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

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
            "must_change_password": False,
        }

    # User authentication enabled - validate JWT token
    try:
        payload = decode_access_token(token)
    except TokenExpiredError:
        raise HTTPException(
            status_code=401,
            detail="token_expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except TokenInvalidError:
        raise HTTPException(
            status_code=401,
            detail="token_invalid",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Enforce token type — reject refresh tokens used as access tokens
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=401,
            detail="token_invalid",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_id = int(payload.get("sub", 0))
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=401,
            detail="token_invalid",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="token_invalid",
            headers={"WWW-Authenticate": "Bearer"},
        )

    cursor = db.execute(
        "SELECT id, username, full_name, role, is_active, must_change_password FROM users WHERE id = ?",
        (user_id,),
    )
    row = cursor.fetchone()

    if not row:
        raise HTTPException(
            status_code=401,
            detail="token_invalid",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = {
        "id": row[0],
        "username": row[1],
        "full_name": row[2] or "",
        "role": row[3],
        "is_active": bool(row[4]),
        "must_change_password": bool(row[5])
        if len(row) > 5 and row[5] is not None
        else False,
    }

    if not user["is_active"]:
        raise HTTPException(
            status_code=401,
            detail="user_inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


def get_effective_vault_permission(
    db: sqlite3.Connection,
    principal: dict,
    vault_id: int | None,
) -> str | None:
    """Return the user's strongest effective permission on a vault."""
    user_id = principal.get("id")
    user_role = principal.get("role", "")

    if user_id is None or vault_id is None:
        return None

    if user_role == "superadmin":
        return "admin"

    effective_level = VAULT_PERMISSION_LEVELS["write"] if user_role == "admin" else 0

    cursor = db.execute(
        "SELECT permission FROM vault_members WHERE vault_id = ? AND user_id = ?",
        (vault_id, user_id),
    )
    row = cursor.fetchone()
    if row:
        effective_level = max(effective_level, VAULT_PERMISSION_LEVELS.get(row[0], 0))

    cursor = db.execute(
        """SELECT vga.permission FROM vault_group_access vga
           JOIN group_members gm ON vga.group_id = gm.group_id
           WHERE vga.vault_id = ? AND gm.user_id = ?""",
        (vault_id, user_id),
    )
    for row in cursor.fetchall():
        effective_level = max(effective_level, VAULT_PERMISSION_LEVELS.get(row[0], 0))

    cursor = db.execute("SELECT visibility FROM vaults WHERE id = ?", (vault_id,))
    row = cursor.fetchone()
    if row and row[0] == "public":
        effective_level = max(effective_level, VAULT_PERMISSION_LEVELS["read"])

    return VAULT_PERMISSION_NAMES.get(effective_level)


async def _evaluate_policy(
    db: sqlite3.Connection,
    principal: dict,
    resource_type: str,
    resource_id: int | None,
    action: str,
) -> bool:
    """Core policy evaluation logic with injected database connection."""
    user_id = principal.get("id")
    user_role = principal.get("role", "")

    if user_id is None:
        return False

    if resource_type not in ("vault", "group"):
        return user_role == "superadmin"

    # Group resources: admin and superadmin have full access
    if resource_type == "group":
        return user_role in ("superadmin", "admin")

    if resource_id is None:
        return False

    if user_role == "superadmin":
        return True

    effective_permission = get_effective_vault_permission(db, principal, resource_id)
    effective_level = VAULT_PERMISSION_LEVELS.get(effective_permission or "", 0)
    required_level = VAULT_ACTION_LEVELS.get(action, VAULT_ACTION_LEVELS["read"])
    return effective_level >= required_level


def get_evaluate_policy(
    db: sqlite3.Connection = Depends(get_db),
) -> Callable:
    """FastAPI dependency that returns an evaluate function with injected database.

    Usage:
        evaluate = Depends(get_evaluate_policy)
        if await evaluate(user, "vault", vault_id, "read"):
            # permission granted
    """

    async def _evaluate(
        principal: dict,
        resource_type: str,
        resource_id: int | None,
        action: str,
    ) -> bool:
        return await _evaluate_policy(db, principal, resource_type, resource_id, action)

    return _evaluate


async def evaluate_policy(
    principal: dict,
    resource_type: str,
    resource_id: int | None,
    action: str,
) -> bool:
    """
    Original evaluate_policy - creates pool for backward compatibility.

    Resolution order (vault resources):
    1. superadmin -> True for all actions
    2. admin -> True for read/write, False for vault delete
    3. vault_members row -> use permission column
    4. vault_group_access (user in group) -> highest permission wins
    5. vault.visibility == 'public' AND action == 'read' -> True
    6. Otherwise -> False
    """
    pool = get_pool(str(settings.sqlite_path))
    conn = pool.get_connection()
    try:
        return await _evaluate_policy(
            conn, principal, resource_type, resource_id, action
        )
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

    Uses UserRole enum for canonical hierarchy:
    superadmin(4) > admin(3) > member(2) > viewer(1)

    Usage: Depends(require_role("admin"))
    """
    required_level = UserRole.level(role)

    async def _check_role(user: dict = Depends(get_current_active_user)) -> dict:
        user_role = user.get("role", "viewer")
        user_level = UserRole.level(user_role)

        if user_level < required_level:
            raise HTTPException(
                status_code=403,
                detail=f"Insufficient privileges. Required role: {role}",
            )

        return user

    return _check_role


async def require_admin_role(user: dict = Depends(get_current_active_user)) -> dict:
    """
    Dependency that requires the user to have admin or superadmin role.
    Uses UserRole enum for canonical hierarchy check.
    """
    user_role = user.get("role", "")
    if UserRole.level(user_role) < UserRole.ADMIN:
        raise HTTPException(
            status_code=403,
            detail="Admin access required",
        )
    return user


def get_user_accessible_vault_ids(user: dict, db) -> list:
    """
    Get all vault IDs that a user has access to.

    Returns list of vault IDs based on:
    - Direct vault_members permissions
    - vault_group_access via group membership
    - For superadmin/admin: returns empty list (means "all vaults")
    """
    user_role = user.get("role", "")

    # superadmin/admin can access all vaults
    if user_role in ("superadmin", "admin"):
        return []  # Empty list means "all vaults"

    cursor = db.execute("SELECT id FROM vaults")
    return [
        row[0]
        for row in cursor.fetchall()
        if get_effective_vault_permission(db, user, row[0]) is not None
    ]


class MultipleOrgError(Exception):
    """Raised when a user belongs to multiple organizations."""

    pass


def get_user_orgs(user_id: int, db: sqlite3.Connection) -> list[int]:
    """Get all organization IDs for a user.

    Args:
        user_id: The user's ID
        db: Database connection

    Returns:
        List of organization IDs the user belongs to
    """
    cursor = db.execute("SELECT org_id FROM org_members WHERE user_id = ?", (user_id,))
    return [row[0] for row in cursor.fetchall()]


def get_user_primary_org(user_id: int, db: sqlite3.Connection) -> int | None:
    """Get the primary organization ID for a user.

    Args:
        user_id: The user's ID
        db: Database connection

    Returns:
        The organization ID if user belongs to exactly one org
        None if user belongs to no orgs

    Raises:
        MultipleOrgError: If user belongs to multiple organizations
    """
    orgs = get_user_orgs(user_id, db)
    if len(orgs) == 0:
        return None
    if len(orgs) == 1:
        return orgs[0]
    raise MultipleOrgError(f"User {user_id} belongs to multiple organizations: {orgs}")
