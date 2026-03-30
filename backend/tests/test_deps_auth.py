"""
Tests for backend/app/api/deps.py — user auth and RBAC functions.

Tests cover:
- get_current_active_user: admin token auth, JWT auth, edge cases
- evaluate_policy: superadmin, admin, vault member, public vault RBAC
- require_vault_permission: dependency factory
- require_role: dependency factory
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi import HTTPException


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_settings_admin_mode():
    """Mock settings for users_enabled=False (admin token mode)."""
    mock = MagicMock()
    mock.users_enabled = False
    mock.admin_secret_token = "test-token"
    mock.jwt_secret_key = "test-secret-key"
    mock.jwt_algorithm = "HS256"
    mock.sqlite_path = "./test.db"
    with patch("app.api.deps.settings", mock, create=True):
        with patch("app.services.auth_service.settings", mock, create=True):
            with patch("app.config.settings", mock, create=True):
                yield mock


@pytest.fixture
def mock_settings_jwt_mode():
    """Mock settings for users_enabled=True (JWT auth mode)."""
    mock = MagicMock()
    mock.users_enabled = True
    mock.admin_secret_token = "test-token"
    mock.jwt_secret_key = "test-secret-key"
    mock.jwt_algorithm = "HS256"
    mock.sqlite_path = "./test.db"
    with patch("app.api.deps.settings", mock, create=True):
        with patch("app.services.auth_service.settings", mock, create=True):
            with patch("app.config.settings", mock, create=True):
                yield mock


@pytest.fixture
def mock_db():
    """Mock database connection."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.execute.return_value = mock_cursor
    return mock_conn, mock_cursor


# ─────────────────────────────────────────────────────────────────────────────
# Test get_current_active_user — Admin Token Mode (users_enabled=False)
# ─────────────────────────────────────────────────────────────────────────────


class TestGetCurrentUserAdminToken:
    """Tests for get_current_active_user with admin token auth."""

    @pytest.mark.asyncio
    async def test_get_current_user_with_admin_token(
        self, mock_settings_admin_mode, mock_db
    ):
        """users_enabled=False, valid admin token → returns superadmin dict."""
        from app.api.deps import get_current_active_user

        mock_conn, mock_cursor = mock_db

        result = await get_current_active_user(
            authorization="Bearer test-token",
            db=mock_conn,
        )

        assert result == {
            "id": 0,
            "username": "admin",
            "full_name": "Admin",
            "role": "superadmin",
            "is_active": True,
        }

    @pytest.mark.asyncio
    async def test_get_current_user_rejects_default_token(self, mock_db):
        """users_enabled=False, admin_secret_token='', token='admin-secret-token' → 403."""
        from app.api.deps import get_current_active_user

        mock = MagicMock()
        mock.users_enabled = False
        mock.admin_secret_token = ""  # Empty → default token is insecure
        mock.sqlite_path = "./test.db"

        mock_conn, mock_cursor = mock_db

        with patch("app.api.deps.settings", mock, create=True):
            with pytest.raises(HTTPException) as exc_info:
                await get_current_active_user(
                    authorization="Bearer admin-secret-token",
                    db=mock_conn,
                )

            assert exc_info.value.status_code == 403
            assert "change default admin token" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_get_current_user_accepts_explicit_default_token(self, mock_db):
        """users_enabled=False, admin_secret_token='admin-secret-token', token='admin-secret-token' → 200."""
        from app.api.deps import get_current_active_user

        mock = MagicMock()
        mock.users_enabled = False
        mock.admin_secret_token = "admin-secret-token"  # Explicit default token
        mock.sqlite_path = "./test.db"

        mock_conn, mock_cursor = mock_db

        with patch("app.api.deps.settings", mock, create=True):
            result = await get_current_active_user(
                authorization="Bearer admin-secret-token",
                db=mock_conn,
            )

            assert result == {
                "id": 0,
                "username": "admin",
                "full_name": "Admin",
                "role": "superadmin",
                "is_active": True,
            }

    @pytest.mark.asyncio
    async def test_get_current_user_missing_header(self, mock_settings_admin_mode):
        """No Authorization header → 401."""
        from app.api.deps import get_current_active_user

        with pytest.raises(HTTPException) as exc_info:
            await get_current_active_user(
                authorization=None,
                db=MagicMock(),
            )

        assert exc_info.value.status_code == 401
        assert "required" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_get_current_user_invalid_scheme(self, mock_settings_admin_mode):
        """'Basic xxx' → 401."""
        from app.api.deps import get_current_active_user

        with pytest.raises(HTTPException) as exc_info:
            await get_current_active_user(
                authorization="Basic dXNlcjpwYXNz",
                db=MagicMock(),
            )

        assert exc_info.value.status_code == 401
        assert "invalid authorization scheme" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_get_current_user_invalid_token(self, mock_settings_admin_mode):
        """Wrong token → 403."""
        from app.api.deps import get_current_active_user

        with pytest.raises(HTTPException) as exc_info:
            await get_current_active_user(
                authorization="Bearer wrong-token",
                db=MagicMock(),
            )

        assert exc_info.value.status_code == 403
        assert "invalid" in exc_info.value.detail.lower()


# ─────────────────────────────────────────────────────────────────────────────
# Test get_current_active_user — JWT Mode (users_enabled=True)
# ─────────────────────────────────────────────────────────────────────────────


class TestGetCurrentUserJWT:
    """Tests for get_current_active_user with JWT auth."""

    @pytest.mark.asyncio
    async def test_get_current_user_with_jwt(self, mock_settings_jwt_mode, mock_db):
        """users_enabled=True, valid JWT → returns user dict from DB."""
        import jwt
        from datetime import datetime, timedelta, timezone
        from app.api.deps import get_current_active_user

        # Create a valid JWT token directly
        secret, algorithm = "test-secret-key", "HS256"
        payload = {
            "sub": "42",
            "username": "testuser",
            "role": "member",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        token = jwt.encode(payload, secret, algorithm=algorithm)

        mock_conn, mock_cursor = mock_db
        # Simulate DB returning user row: (id, username, full_name, role, is_active)
        mock_cursor.fetchone.return_value = (42, "testuser", "Test User", "member", 1)

        result = await get_current_active_user(
            authorization=f"Bearer {token}",
            db=mock_conn,
        )

        assert result == {
            "id": 42,
            "username": "testuser",
            "full_name": "Test User",
            "role": "member",
            "is_active": True,
        }

    @pytest.mark.asyncio
    async def test_get_current_user_inactive_user(
        self, mock_settings_jwt_mode, mock_db
    ):
        """users_enabled=True, JWT for inactive user → 403."""
        import jwt
        from datetime import datetime, timedelta, timezone
        from app.api.deps import get_current_active_user

        secret, algorithm = "test-secret-key", "HS256"
        payload = {
            "sub": "42",
            "username": "inactiveuser",
            "role": "member",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        token = jwt.encode(payload, secret, algorithm=algorithm)

        mock_conn, mock_cursor = mock_db
        # Simulate DB returning inactive user
        mock_cursor.fetchone.return_value = (
            42,
            "inactiveuser",
            "Inactive User",
            "member",
            0,
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_current_active_user(
                authorization=f"Bearer {token}",
                db=mock_conn,
            )

        assert exc_info.value.status_code == 403
        assert "inactive" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_get_current_user_not_found(self, mock_settings_jwt_mode, mock_db):
        """users_enabled=True, JWT for non-existent user → 403."""
        import jwt
        from datetime import datetime, timedelta, timezone
        from app.api.deps import get_current_active_user

        secret, algorithm = "test-secret-key", "HS256"
        payload = {
            "sub": "999",
            "username": "ghost",
            "role": "member",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        token = jwt.encode(payload, secret, algorithm=algorithm)

        mock_conn, mock_cursor = mock_db
        mock_cursor.fetchone.return_value = None  # User not found

        with pytest.raises(HTTPException) as exc_info:
            await get_current_active_user(
                authorization=f"Bearer {token}",
                db=mock_conn,
            )

        assert exc_info.value.status_code == 403
        assert "not found" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_get_current_user_expired_token(self, mock_settings_jwt_mode):
        """users_enabled=True, expired JWT → 403."""
        import jwt
        from datetime import datetime, timedelta, timezone
        from app.api.deps import get_current_active_user

        secret, algorithm = "test-secret-key", "HS256"
        expired_payload = {
            "sub": "42",
            "username": "testuser",
            "role": "member",
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),  # Expired
        }
        expired_token = jwt.encode(expired_payload, secret, algorithm=algorithm)

        with pytest.raises(HTTPException) as exc_info:
            await get_current_active_user(
                authorization=f"Bearer {expired_token}",
                db=MagicMock(),
            )

        assert exc_info.value.status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
# Test evaluate_policy — RBAC Engine
# ─────────────────────────────────────────────────────────────────────────────


class TestEvaluatePolicy:
    """Tests for evaluate_policy RBAC engine."""

    @pytest.mark.asyncio
    async def test_evaluate_policy_superadmin_grants_all(self):
        """Superadmin user → True for all actions."""
        from app.api.deps import evaluate_policy

        superadmin = {"id": 1, "role": "superadmin"}

        # Superadmin should have access to all vault actions
        assert await evaluate_policy(superadmin, "vault", 1, "read") is True
        assert await evaluate_policy(superadmin, "vault", 1, "write") is True
        assert await evaluate_policy(superadmin, "vault", 1, "delete") is True
        assert await evaluate_policy(superadmin, "vault", 1, "admin") is True

    @pytest.mark.asyncio
    async def test_evaluate_policy_admin_read_write(self):
        """Admin user → True for read/write, False for delete/admin."""
        from app.api.deps import evaluate_policy

        admin = {"id": 2, "role": "admin"}

        mock = MagicMock()
        mock.sqlite_path = "./test.db"
        pool = MagicMock()
        pool.get_connection.return_value.__enter__ = MagicMock(return_value=MagicMock())
        pool.get_connection.return_value.__exit__ = MagicMock(return_value=False)

        with patch("app.api.deps.settings", mock, create=True):
            with patch("app.api.deps.get_pool", return_value=pool):
                assert await evaluate_policy(admin, "vault", 1, "read") is True
                assert await evaluate_policy(admin, "vault", 1, "write") is True
                assert await evaluate_policy(admin, "vault", 1, "delete") is False
                assert await evaluate_policy(admin, "vault", 1, "admin") is False

    @pytest.mark.asyncio
    async def test_evaluate_policy_invalid_principal(self):
        """Principal without id → False."""
        from app.api.deps import evaluate_policy

        invalid_principal = {"role": "admin"}  # Missing id

        result = await evaluate_policy(invalid_principal, "vault", 1, "read")
        assert result is False

    @pytest.mark.asyncio
    async def test_evaluate_policy_none_resource_id(self):
        """resource_id=None → False."""
        from app.api.deps import evaluate_policy

        member = {"id": 3, "role": "member"}

        result = await evaluate_policy(member, "vault", None, "read")
        assert result is False

    @pytest.mark.asyncio
    async def test_evaluate_policy_non_vault_resource(self):
        """Non-vault resource type → only superadmin has access."""
        from app.api.deps import evaluate_policy

        # Superadmin can access any resource
        superadmin = {"id": 1, "role": "superadmin"}
        assert await evaluate_policy(superadmin, "document", 1, "read") is True

        # Admin cannot access non-vault resources
        admin = {"id": 2, "role": "admin"}
        assert await evaluate_policy(admin, "document", 1, "read") is False

        # Member cannot access non-vault resources
        member = {"id": 3, "role": "member"}
        assert await evaluate_policy(member, "document", 1, "read") is False


# ─────────────────────────────────────────────────────────────────────────────
# Test require_role — Dependency Factory
# ─────────────────────────────────────────────────────────────────────────────


class TestRequireRole:
    """Tests for require_role dependency factory."""

    @pytest.mark.asyncio
    async def test_require_role_admin_passes(self, mock_settings_jwt_mode):
        """Admin user passes require_role('admin')."""
        from app.api.deps import require_role

        check_role = require_role("admin")

        # Call the inner function directly with a user dict
        user = await check_role(
            user={"id": 2, "username": "adminuser", "role": "admin", "is_active": True}
        )
        assert user["role"] == "admin"

    @pytest.mark.asyncio
    async def test_require_role_viewer_fails_admin(self, mock_settings_jwt_mode):
        """Viewer user fails require_role('admin')."""
        from app.api.deps import require_role

        check_role = require_role("admin")

        with pytest.raises(HTTPException) as exc_info:
            await check_role(
                user={
                    "id": 5,
                    "username": "vieweruser",
                    "role": "viewer",
                    "is_active": True,
                }
            )

        assert exc_info.value.status_code == 403
        assert "insufficient" in exc_info.value.detail.lower()
        assert "admin" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_require_role_viewer_hierarchy(self, mock_settings_jwt_mode):
        """Viewer passes require_role('viewer'), fails require_role('member')."""
        from app.api.deps import require_role

        # Viewer should pass viewer role check
        check_viewer = require_role("viewer")
        user = await check_viewer(
            user={
                "id": 5,
                "username": "vieweruser",
                "role": "viewer",
                "is_active": True,
            }
        )
        assert user["role"] == "viewer"

        # Viewer should fail member role check
        check_member = require_role("member")
        with pytest.raises(HTTPException) as exc_info:
            await check_member(
                user={
                    "id": 5,
                    "username": "vieweruser",
                    "role": "viewer",
                    "is_active": True,
                }
            )

        assert exc_info.value.status_code == 403
        assert "member" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_require_role_superadmin_hierarchy(self, mock_settings_jwt_mode):
        """Superadmin passes all role checks."""
        from app.api.deps import require_role

        for role in ["viewer", "member", "admin", "superadmin"]:
            check_role = require_role(role)
            user = await check_role(
                user={
                    "id": 1,
                    "username": "super",
                    "role": "superadmin",
                    "is_active": True,
                }
            )
            assert user["role"] == "superadmin"


# ─────────────────────────────────────────────────────────────────────────────
# Test require_vault_permission — Dependency Factory
# ─────────────────────────────────────────────────────────────────────────────


class TestRequireVaultPermission:
    """Tests for require_vault_permission dependency factory."""

    @pytest.mark.asyncio
    async def test_require_role_factory_returns_callable(self, mock_settings_jwt_mode):
        """require_role returns a callable dependency."""
        from app.api.deps import require_role

        check_role = require_role("admin")
        assert callable(check_role)

    @pytest.mark.asyncio
    async def test_require_vault_permission_factory_returns_callable(self):
        """require_vault_permission returns a callable dependency."""
        from app.api.deps import require_vault_permission

        check_perm = require_vault_permission("read", "write")
        assert callable(check_perm)
