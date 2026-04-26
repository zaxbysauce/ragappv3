"""
Tests for backend/app/api/deps.py — user auth and RBAC functions.

Tests cover:
- get_current_active_user: admin token auth, JWT auth, cookie fallback, token type enforcement, must_change_password
- evaluate_policy: superadmin, admin, vault member, public vault RBAC
- require_vault_permission: dependency factory
- require_role: dependency factory
- require_admin_role: standalone admin role check
- get_user_accessible_vault_ids: vault access enumeration for regular users
"""

from unittest.mock import MagicMock, patch

import pytest
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
        """users_enabled=False, valid admin token → returns superadmin dict with must_change_password=False."""
        from app.api.deps import get_current_active_user

        mock_conn, mock_cursor = mock_db

        result = await get_current_active_user(
            authorization="Bearer test-token",
            access_token=None,
            db=mock_conn,
        )

        assert result == {
            "id": 0,
            "username": "admin",
            "full_name": "Admin",
            "role": "superadmin",
            "is_active": True,
            "must_change_password": False,
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
                    access_token=None,
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
                access_token=None,
                db=mock_conn,
            )

            assert result == {
                "id": 0,
                "username": "admin",
                "full_name": "Admin",
                "role": "superadmin",
                "is_active": True,
                "must_change_password": False,
            }

    @pytest.mark.asyncio
    async def test_get_current_user_missing_header(self, mock_settings_admin_mode):
        """No Authorization header and no cookie → 401."""
        from app.api.deps import get_current_active_user

        with pytest.raises(HTTPException) as exc_info:
            await get_current_active_user(
                authorization=None,
                access_token=None,
                db=MagicMock(),
            )

        assert exc_info.value.status_code == 401
        assert "not authenticated" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_get_current_user_invalid_token(self, mock_settings_admin_mode):
        """Wrong token → 403."""
        from app.api.deps import get_current_active_user

        with pytest.raises(HTTPException) as exc_info:
            await get_current_active_user(
                authorization="Bearer wrong-token",
                access_token=None,
                db=MagicMock(),
            )

        assert exc_info.value.status_code == 403
        assert "invalid" in exc_info.value.detail.lower()


# ─────────────────────────────────────────────────────────────────────────────
# Test get_current_active_user — Cookie Fallback
# ─────────────────────────────────────────────────────────────────────────────


class TestGetCurrentUserCookieFallback:
    """Tests for get_current_active_user cookie fallback authentication."""

    @pytest.mark.asyncio
    async def test_auth_via_authorization_header_returns_user(
        self, mock_settings_jwt_mode, mock_db
    ):
        """Auth via Authorization header → returns user dict."""
        from datetime import datetime, timedelta, timezone

        import jwt

        from app.api.deps import get_current_active_user

        secret, algorithm = "test-secret-key", "HS256"
        payload = {
            "sub": "42",
            "username": "testuser",
            "role": "member",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
            "type": "access",
        }
        token = jwt.encode(payload, secret, algorithm=algorithm)

        mock_conn, mock_cursor = mock_db
        mock_cursor.fetchone.return_value = (
            42,
            "testuser",
            "Test User",
            "member",
            1,
            0,
        )

        result = await get_current_active_user(
            authorization=f"Bearer {token}",
            access_token=None,
            db=mock_conn,
        )

        assert result["id"] == 42
        assert result["username"] == "testuser"
        assert result["role"] == "member"

    @pytest.mark.asyncio
    async def test_auth_via_cookie_returns_user(self, mock_settings_jwt_mode, mock_db):
        """Auth via cookie (access_token) → returns user dict."""
        from datetime import datetime, timedelta, timezone

        import jwt

        from app.api.deps import get_current_active_user

        secret, algorithm = "test-secret-key", "HS256"
        payload = {
            "sub": "42",
            "username": "testuser",
            "role": "member",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
            "type": "access",
        }
        token = jwt.encode(payload, secret, algorithm=algorithm)

        mock_conn, mock_cursor = mock_db
        mock_cursor.fetchone.return_value = (
            42,
            "testuser",
            "Test User",
            "member",
            1,
            0,
        )

        result = await get_current_active_user(
            authorization=None,
            access_token=token,
            db=mock_conn,
        )

        assert result["id"] == 42
        assert result["username"] == "testuser"
        assert result["role"] == "member"

    @pytest.mark.asyncio
    async def test_no_header_no_cookie_returns_401(self, mock_settings_jwt_mode):
        """No header, no cookie → 401."""
        from app.api.deps import get_current_active_user

        with pytest.raises(HTTPException) as exc_info:
            await get_current_active_user(
                authorization=None,
                access_token=None,
                db=MagicMock(),
            )

        assert exc_info.value.status_code == 401
        assert "not authenticated" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_invalid_token_in_header_returns_403(self, mock_settings_jwt_mode):
        """Invalid token in header → 401."""
        from app.api.deps import get_current_active_user

        with pytest.raises(HTTPException) as exc_info:
            await get_current_active_user(
                authorization="Bearer invalid-token",
                access_token=None,
                db=MagicMock(),
            )

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_token_in_cookie_returns_403(self, mock_settings_jwt_mode):
        """Invalid token in cookie → 401."""
        from app.api.deps import get_current_active_user

        with pytest.raises(HTTPException) as exc_info:
            await get_current_active_user(
                authorization=None,
                access_token="invalid-token",
                db=MagicMock(),
            )

        assert exc_info.value.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# Test JWT Type Enforcement
# ─────────────────────────────────────────────────────────────────────────────


class TestJWTTypeEnforcement:
    """Tests for JWT token type enforcement in get_current_active_user."""

    @pytest.mark.asyncio
    async def test_access_token_with_type_access_accepted(
        self, mock_settings_jwt_mode, mock_db
    ):
        """Access token with type='access' → accepted."""
        from datetime import datetime, timedelta, timezone

        import jwt

        from app.api.deps import get_current_active_user

        secret, algorithm = "test-secret-key", "HS256"
        payload = {
            "sub": "42",
            "username": "testuser",
            "role": "member",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
            "type": "access",
        }
        token = jwt.encode(payload, secret, algorithm=algorithm)

        mock_conn, mock_cursor = mock_db
        mock_cursor.fetchone.return_value = (
            42,
            "testuser",
            "Test User",
            "member",
            1,
            0,
        )

        result = await get_current_active_user(
            authorization=f"Bearer {token}",
            access_token=None,
            db=mock_conn,
        )

        assert result["id"] == 42

    @pytest.mark.asyncio
    async def test_token_without_type_field_returns_401(
        self, mock_settings_jwt_mode, mock_db
    ):
        """Token without type field → 401 'Invalid token type'."""
        from datetime import datetime, timedelta, timezone

        import jwt

        from app.api.deps import get_current_active_user

        secret, algorithm = "test-secret-key", "HS256"
        payload = {
            "sub": "42",
            "username": "testuser",
            "role": "member",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
            # No 'type' field
        }
        token = jwt.encode(payload, secret, algorithm=algorithm)

        mock_conn, mock_cursor = mock_db

        with pytest.raises(HTTPException) as exc_info:
            await get_current_active_user(
                authorization=f"Bearer {token}",
                access_token=None,
                db=mock_conn,
            )

        assert exc_info.value.status_code == 401
        assert "token_invalid" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_token_with_type_refresh_returns_401(
        self, mock_settings_jwt_mode, mock_db
    ):
        """Token with type='refresh' → 401 'Invalid token type'."""
        from datetime import datetime, timedelta, timezone

        import jwt

        from app.api.deps import get_current_active_user

        secret, algorithm = "test-secret-key", "HS256"
        payload = {
            "sub": "42",
            "username": "testuser",
            "role": "member",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
            "type": "refresh",
        }
        token = jwt.encode(payload, secret, algorithm=algorithm)

        mock_conn, mock_cursor = mock_db

        with pytest.raises(HTTPException) as exc_info:
            await get_current_active_user(
                authorization=f"Bearer {token}",
                access_token=None,
                db=mock_conn,
            )

        assert exc_info.value.status_code == 401
        assert "token_invalid" in exc_info.value.detail.lower()


class TestMustChangePassword:
    """Tests for must_change_password field in user dict."""

    @pytest.mark.asyncio
    async def test_user_with_must_change_password_true(
        self, mock_settings_jwt_mode, mock_db
    ):
        """User with must_change_password=True in DB → user dict has must_change_password=True."""
        from datetime import datetime, timedelta, timezone

        import jwt

        from app.api.deps import get_current_active_user

        secret, algorithm = "test-secret-key", "HS256"
        payload = {
            "sub": "42",
            "username": "testuser",
            "role": "member",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
            "type": "access",
        }
        token = jwt.encode(payload, secret, algorithm=algorithm)

        mock_conn, mock_cursor = mock_db
        # DB returns must_change_password=1 (True)
        mock_cursor.fetchone.return_value = (
            42,
            "testuser",
            "Test User",
            "member",
            1,
            1,
        )

        result = await get_current_active_user(
            authorization=f"Bearer {token}",
            access_token=None,
            db=mock_conn,
        )

        assert result["must_change_password"] is True

    @pytest.mark.asyncio
    async def test_user_with_must_change_password_false(
        self, mock_settings_jwt_mode, mock_db
    ):
        """User with must_change_password=False in DB → user dict has must_change_password=False."""
        from datetime import datetime, timedelta, timezone

        import jwt

        from app.api.deps import get_current_active_user

        secret, algorithm = "test-secret-key", "HS256"
        payload = {
            "sub": "42",
            "username": "testuser",
            "role": "member",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
            "type": "access",
        }
        token = jwt.encode(payload, secret, algorithm=algorithm)

        mock_conn, mock_cursor = mock_db
        # DB returns must_change_password=0 (False)
        mock_cursor.fetchone.return_value = (
            42,
            "testuser",
            "Test User",
            "member",
            1,
            0,
        )

        result = await get_current_active_user(
            authorization=f"Bearer {token}",
            access_token=None,
            db=mock_conn,
        )

        assert result["must_change_password"] is False

    @pytest.mark.asyncio
    async def test_user_with_must_change_password_null(
        self, mock_settings_jwt_mode, mock_db
    ):
        """User with must_change_password=NULL in DB → user dict has must_change_password=False."""
        from datetime import datetime, timedelta, timezone

        import jwt

        from app.api.deps import get_current_active_user

        secret, algorithm = "test-secret-key", "HS256"
        payload = {
            "sub": "42",
            "username": "testuser",
            "role": "member",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
            "type": "access",
        }
        token = jwt.encode(payload, secret, algorithm=algorithm)

        mock_conn, mock_cursor = mock_db
        # DB returns must_change_password=None (column not populated)
        mock_cursor.fetchone.return_value = (
            42,
            "testuser",
            "Test User",
            "member",
            1,
            None,
        )

        result = await get_current_active_user(
            authorization=f"Bearer {token}",
            access_token=None,
            db=mock_conn,
        )

        assert result["must_change_password"] is False

    @pytest.mark.asyncio
    async def test_admin_token_fallback_must_change_password_false(
        self, mock_settings_admin_mode, mock_db
    ):
        """Admin token fallback → user dict has must_change_password=False."""
        from app.api.deps import get_current_active_user

        mock_conn, mock_cursor = mock_db

        result = await get_current_active_user(
            authorization="Bearer test-token",
            access_token=None,
            db=mock_conn,
        )

        assert result["must_change_password"] is False


# ─────────────────────────────────────────────────────────────────────────────
# Test require_admin_role
# ─────────────────────────────────────────────────────────────────────────────


class TestRequireAdminRole:
    """Tests for require_admin_role dependency function."""

    @pytest.mark.asyncio
    async def test_superadmin_user_passes(self):
        """Superadmin user → passes."""
        from app.api.deps import require_admin_role

        user = {"id": 1, "username": "super", "role": "superadmin", "is_active": True}
        result = await require_admin_role(user)

        assert result == user

    @pytest.mark.asyncio
    async def test_admin_user_passes(self):
        """Admin user → passes."""
        from app.api.deps import require_admin_role

        user = {"id": 2, "username": "admin", "role": "admin", "is_active": True}
        result = await require_admin_role(user)

        assert result == user

    @pytest.mark.asyncio
    async def test_member_user_returns_403(self):
        """Member user → 403."""
        from app.api.deps import require_admin_role

        user = {"id": 3, "username": "member", "role": "member", "is_active": True}

        with pytest.raises(HTTPException) as exc_info:
            await require_admin_role(user)

        assert exc_info.value.status_code == 403
        assert "admin access required" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_viewer_user_returns_403(self):
        """Viewer user → 403."""
        from app.api.deps import require_admin_role

        user = {"id": 4, "username": "viewer", "role": "viewer", "is_active": True}

        with pytest.raises(HTTPException) as exc_info:
            await require_admin_role(user)

        assert exc_info.value.status_code == 403
        assert "admin access required" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_unauthenticated_user_raises_from_get_current_user(self):
        """Unauthenticated user → 401 (from get_current_active_user dependency)."""
        from app.api.deps import get_current_active_user

        with pytest.raises(HTTPException) as exc_info:
            await get_current_active_user(
                authorization=None,
                access_token=None,
                db=MagicMock(),
            )

        assert exc_info.value.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# Test get_user_accessible_vault_ids
# ─────────────────────────────────────────────────────────────────────────────


class TestGetUserAccessibleVaultIds:
    """Tests for get_user_accessible_vault_ids helper function."""

    @pytest.mark.asyncio
    async def test_superadmin_returns_empty_list(self, mock_db):
        """Superadmin user → returns [] (means 'all vaults')."""
        from app.api.deps import get_user_accessible_vault_ids

        user = {"id": 1, "role": "superadmin"}
        mock_conn, mock_cursor = mock_db

        result = get_user_accessible_vault_ids(user, mock_conn)

        assert result == []

    @pytest.mark.asyncio
    async def test_admin_returns_empty_list(self, mock_db):
        """Admin user → returns [] (means 'all vaults')."""
        from app.api.deps import get_user_accessible_vault_ids

        user = {"id": 2, "role": "admin"}
        mock_conn, mock_cursor = mock_db

        result = get_user_accessible_vault_ids(user, mock_conn)

        assert result == []

    @pytest.mark.asyncio
    async def test_regular_user_with_direct_membership(self, mock_db):
        """Regular user with direct vault membership → returns vault IDs."""
        from app.api.deps import get_user_accessible_vault_ids

        user = {"id": 3, "role": "member"}
        mock_conn, mock_cursor = mock_db

        # Direct membership query returns vault IDs 10, 20
        mock_cursor.fetchall.side_effect = [
            [(10,), (20,)],
            [],
        ]  # First for members, second for groups

        result = get_user_accessible_vault_ids(user, mock_conn)

        assert sorted(result) == [10, 20]

    @pytest.mark.asyncio
    async def test_regular_user_with_group_access(self, mock_db):
        """Regular user with group-based vault access → returns vault IDs."""
        from app.api.deps import get_user_accessible_vault_ids

        user = {"id": 3, "role": "member"}
        mock_conn, mock_cursor = mock_db

        # Direct membership returns empty, group access returns vault IDs 30, 40
        mock_cursor.fetchall.side_effect = [[], [(30,), (40,)]]

        result = get_user_accessible_vault_ids(user, mock_conn)

        assert sorted(result) == [30, 40]

    @pytest.mark.asyncio
    async def test_regular_user_with_direct_and_group_access_deduplicated(
        self, mock_db
    ):
        """Regular user with both direct and group access → deduplicated list."""
        from app.api.deps import get_user_accessible_vault_ids

        user = {"id": 3, "role": "member"}
        mock_conn, mock_cursor = mock_db

        # Direct membership returns 10, 20; group access returns 20, 30 (overlap: 20)
        mock_cursor.fetchall.side_effect = [[(10,), (20,)], [(20,), (30,)]]

        result = get_user_accessible_vault_ids(user, mock_conn)

        # Should be deduplicated and sorted
        assert sorted(result) == [10, 20, 30]

    @pytest.mark.asyncio
    async def test_regular_user_with_no_access(self, mock_db):
        """Regular user with no vault access → returns empty list."""
        from app.api.deps import get_user_accessible_vault_ids

        user = {"id": 3, "role": "member"}
        mock_conn, mock_cursor = mock_db

        # Both queries return empty
        mock_cursor.fetchall.side_effect = [[], []]

        result = get_user_accessible_vault_ids(user, mock_conn)

        assert result == []


# ─────────────────────────────────────────────────────────────────────────────
# Test get_current_active_user — JWT Mode (users_enabled=True)
# ─────────────────────────────────────────────────────────────────────────────


class TestGetCurrentUserJWT:
    """Tests for get_current_active_user with JWT auth."""

    @pytest.mark.asyncio
    async def test_get_current_user_with_jwt(self, mock_settings_jwt_mode, mock_db):
        """users_enabled=True, valid JWT → returns user dict from DB."""
        from datetime import datetime, timedelta, timezone

        import jwt

        from app.api.deps import get_current_active_user

        # Create a valid JWT token directly
        secret, algorithm = "test-secret-key", "HS256"
        payload = {
            "sub": "42",
            "username": "testuser",
            "role": "member",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
            "type": "access",
        }
        token = jwt.encode(payload, secret, algorithm=algorithm)

        mock_conn, mock_cursor = mock_db
        # Simulate DB returning user row: (id, username, full_name, role, is_active, must_change_password)
        mock_cursor.fetchone.return_value = (
            42,
            "testuser",
            "Test User",
            "member",
            1,
            0,
        )

        result = await get_current_active_user(
            authorization=f"Bearer {token}",
            access_token=None,
            db=mock_conn,
        )

        assert result == {
            "id": 42,
            "username": "testuser",
            "full_name": "Test User",
            "role": "member",
            "is_active": True,
            "must_change_password": False,
        }

    @pytest.mark.asyncio
    async def test_get_current_user_inactive_user(
        self, mock_settings_jwt_mode, mock_db
    ):
        """users_enabled=True, JWT for inactive user → 401 user_inactive."""
        from datetime import datetime, timedelta, timezone

        import jwt

        from app.api.deps import get_current_active_user

        secret, algorithm = "test-secret-key", "HS256"
        payload = {
            "sub": "42",
            "username": "inactiveuser",
            "role": "member",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
            "type": "access",
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
            0,
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_current_active_user(
                authorization=f"Bearer {token}",
                access_token=None,
                db=mock_conn,
            )

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "user_inactive"

    @pytest.mark.asyncio
    async def test_get_current_user_not_found(self, mock_settings_jwt_mode, mock_db):
        """users_enabled=True, JWT for non-existent user → 401."""
        from datetime import datetime, timedelta, timezone

        import jwt

        from app.api.deps import get_current_active_user

        secret, algorithm = "test-secret-key", "HS256"
        payload = {
            "sub": "999",
            "username": "ghost",
            "role": "member",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
            "type": "access",
        }
        token = jwt.encode(payload, secret, algorithm=algorithm)

        mock_conn, mock_cursor = mock_db
        mock_cursor.fetchone.return_value = None  # User not found

        with pytest.raises(HTTPException) as exc_info:
            await get_current_active_user(
                authorization=f"Bearer {token}",
                access_token=None,
                db=mock_conn,
            )

        assert exc_info.value.status_code == 401
        assert "token_invalid" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_get_current_user_expired_token(self, mock_settings_jwt_mode):
        """users_enabled=True, expired JWT → 401."""
        from datetime import datetime, timedelta, timezone

        import jwt

        from app.api.deps import get_current_active_user

        secret, algorithm = "test-secret-key", "HS256"
        expired_payload = {
            "sub": "42",
            "username": "testuser",
            "role": "member",
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),  # Expired
            "type": "access",
        }
        expired_token = jwt.encode(expired_payload, secret, algorithm=algorithm)

        with pytest.raises(HTTPException) as exc_info:
            await get_current_active_user(
                authorization=f"Bearer {expired_token}",
                access_token=None,
                db=MagicMock(),
            )

        assert exc_info.value.status_code == 401


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

    @pytest.mark.asyncio
    async def test_evaluate_policy_group_resource_allows_admin(self):
        """Group resource type → superadmin and admin have access, member does not."""
        from app.api.deps import evaluate_policy

        # Superadmin can access group resources
        superadmin = {"id": 1, "role": "superadmin"}
        assert await evaluate_policy(superadmin, "group", 1, "read") is True

        # Admin can access group resources (whitelisted alongside vault)
        admin = {"id": 2, "role": "admin"}
        assert await evaluate_policy(admin, "group", 1, "read") is True

        # Member cannot access group resources
        member = {"id": 3, "role": "member"}
        assert await evaluate_policy(member, "group", 1, "read") is False


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
