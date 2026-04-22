"""
Authentication routes verification tests.

Tests cover:
- User registration (first user as superadmin, second as member)
- Login with access token and refresh cookie
- Token refresh with rotation
- Logout and session revocation
- Setup status endpoint
- Profile get/update endpoints

Uses FastAPI TestClient with dependency overrides for isolated testing.
"""

import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Stub missing optional dependencies
try:
    import lancedb
except ImportError:
    import types

    sys.modules["lancedb"] = types.ModuleType("lancedb")

try:
    import pyarrow
except ImportError:
    import types

    sys.modules["pyarrow"] = types.ModuleType("pyarrow")

try:
    from unstructured.partition.auto import partition
except ImportError:
    import types

    _unstructured = types.ModuleType("unstructured")
    _unstructured.__path__ = []
    _unstructured.partition = types.ModuleType("unstructured.partition")
    _unstructured.partition.__path__ = []
    _unstructured.partition.auto = types.ModuleType("unstructured.partition.auto")
    _unstructured.partition.auto.partition = lambda *args, **kwargs: []
    _unstructured.chunking = types.ModuleType("unstructured.chunking")
    _unstructured.chunking.__path__ = []
    _unstructured.chunking.title = types.ModuleType("unstructured.chunking.title")
    _unstructured.chunking.title.chunk_by_title = lambda *args, **kwargs: []
    _unstructured.documents = types.ModuleType("unstructured.documents")
    _unstructured.documents.__path__ = []
    _unstructured.documents.elements = types.ModuleType(
        "unstructured.documents.elements"
    )
    _unstructured.documents.elements.Element = type("Element", (), {})
    sys.modules["unstructured"] = _unstructured
    sys.modules["unstructured.partition"] = _unstructured.partition
    sys.modules["unstructured.partition.auto"] = _unstructured.partition.auto
    sys.modules["unstructured.chunking"] = _unstructured.chunking
    sys.modules["unstructured.chunking.title"] = _unstructured.chunking.title
    sys.modules["unstructured.documents"] = _unstructured.documents
    sys.modules["unstructured.documents.elements"] = _unstructured.documents.elements

from fastapi.testclient import TestClient

from app.config import settings
from app.models.database import SQLiteConnectionPool, init_db, run_migrations


class TestAuthRoutes(unittest.TestCase):
    """Test suite for authentication routes."""

    def setUp(self):
        """Set up test client with temporary database."""
        # Create temporary database
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test.db")

        # Initialize database with schema
        init_db(self.db_path)
        run_migrations(self.db_path)

        # Store original settings to restore later
        self._original_jwt_secret = settings.jwt_secret_key
        self._original_users_enabled = settings.users_enabled

        # Override JWT secret for testing
        settings.jwt_secret_key = "test-secret-key-for-testing-at-least-32-chars-long"
        settings.users_enabled = True

        # Create a test pool for the temporary database
        self.test_pool = SQLiteConnectionPool(self.db_path, max_size=5)

        # Create FastAPI app and configure dependency overrides
        from app.api.deps import get_db
        from app.main import app as main_app

        # Override the get_db dependency to use our test pool
        def get_test_db():
            conn = self.test_pool.get_connection()
            try:
                yield conn
            finally:
                self.test_pool.release_connection(conn)

        main_app.dependency_overrides[get_db] = get_test_db

        # Create test client with dependency overrides
        self.client = TestClient(main_app)
        self.app = main_app

    def tearDown(self):
        """Clean up after each test."""
        # Restore original settings
        settings.jwt_secret_key = self._original_jwt_secret
        settings.users_enabled = self._original_users_enabled

        # Clear dependency overrides

        self.app.dependency_overrides.clear()

        # Close the test pool
        self.test_pool.close_all()

        # Clean up temp directory
        import shutil

        try:
            shutil.rmtree(self.temp_dir)
        except Exception:
            pass

    def test_register_first_user_is_superadmin(self):
        """Register first user and verify role is superadmin."""
        response = self.client.post(
            "/api/auth/register", json={"username": "admin", "password": "password123"}
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["role"], "superadmin")
        self.assertEqual(data["username"], "admin")

    def test_register_second_user_is_member(self):
        """Register second user and verify role is member."""
        # First register a superadmin
        self.client.post(
            "/api/auth/register", json={"username": "admin", "password": "password123"}
        )

        # Then register a second user
        response = self.client.post(
            "/api/auth/register", json={"username": "user2", "password": "password456"}
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["role"], "member")
        self.assertEqual(data["username"], "user2")

    def test_register_duplicate_username(self):
        """Register same username twice should return 409."""
        self.client.post(
            "/api/auth/register",
            json={"username": "duplicate", "password": "password123"},
        )

        response = self.client.post(
            "/api/auth/register",
            json={"username": "duplicate", "password": "password456"},
        )

        self.assertEqual(response.status_code, 409)

    def test_register_short_username(self):
        """Register with username < 3 chars should return 400."""
        response = self.client.post(
            "/api/auth/register", json={"username": "ab", "password": "password123"}
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("3 characters", response.json()["detail"])

    def test_register_short_password(self):
        """Register with password < 8 chars should return 400."""
        response = self.client.post(
            "/api/auth/register", json={"username": "validuser", "password": "pass"}
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("8 characters", response.json()["detail"])

    def test_login_success(self):
        """Register then login, verify access_token returned."""
        # First register
        self.client.post(
            "/api/auth/register",
            json={"username": "logintest", "password": "password123"},
        )

        # Then login
        response = self.client.post(
            "/api/auth/login", json={"username": "logintest", "password": "password123"}
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("access_token", data)
        self.assertEqual(data["token_type"], "bearer")
        self.assertEqual(data["user"]["username"], "logintest")

    def test_login_wrong_password(self):
        """Login with wrong password should return 401."""
        # First register
        self.client.post(
            "/api/auth/register",
            json={"username": "wrongpw", "password": "password123"},
        )

        # Try login with wrong password
        response = self.client.post(
            "/api/auth/login", json={"username": "wrongpw", "password": "wrongpassword"}
        )

        self.assertEqual(response.status_code, 401)
        self.assertIn("Invalid username or password", response.json()["detail"])

    def test_login_inactive_user(self):
        """Login with inactive user should return 403."""
        # First register user
        self.client.post(
            "/api/auth/register",
            json={"username": "inactiveuser", "password": "password123"},
        )

        # Deactivate user using the test pool
        conn = self.test_pool.get_connection()
        try:
            conn.execute(
                "UPDATE users SET is_active = 0 WHERE username = ?", ("inactiveuser",)
            )
            conn.commit()
        finally:
            self.test_pool.release_connection(conn)

        # Try login
        response = self.client.post(
            "/api/auth/login",
            json={"username": "inactiveuser", "password": "password123"},
        )

        self.assertEqual(response.status_code, 403)
        self.assertIn("inactive", response.json()["detail"])

    def test_refresh_success(self):
        """Login to get cookie, then refresh should return new access_token."""
        # First register and login
        self.client.post(
            "/api/auth/register",
            json={"username": "refreshuser", "password": "password123"},
        )

        login_response = self.client.post(
            "/api/auth/login",
            json={"username": "refreshuser", "password": "password123"},
        )
        self.assertEqual(login_response.status_code, 200)

        # Extract cookie from login response
        cookies = login_response.cookies

        # Call refresh endpoint with cookie
        response = self.client.post(
            "/api/auth/refresh", cookies={"refresh_token": cookies.get("refresh_token")}
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("access_token", data)
        self.assertEqual(data["token_type"], "bearer")

    def test_refresh_expired_token(self):
        """Insert expired session manually, try refresh should return 401."""
        import hashlib
        import secrets

        # First register a user
        self.client.post(
            "/api/auth/register",
            json={"username": "expireduser", "password": "password123"},
        )

        # Create an expired refresh token session using the test pool
        conn = self.test_pool.get_connection()
        try:
            # Create expired token hash (1 day ago)
            expired_token = secrets.token_urlsafe(32)
            token_hash = hashlib.sha256(expired_token.encode()).hexdigest()
            expired_time = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()

            conn.execute(
                "INSERT INTO user_sessions (user_id, refresh_token_hash, expires_at) VALUES (?, ?, ?)",
                (1, token_hash, expired_time),
            )
            conn.commit()
        finally:
            self.test_pool.release_connection(conn)

        # Try refresh with expired token
        response = self.client.post(
            "/api/auth/refresh", cookies={"refresh_token": expired_token}
        )

        self.assertEqual(response.status_code, 401)

    def test_logout_success(self):
        """Login, logout, verify cookie cleared."""
        # Register and login
        self.client.post(
            "/api/auth/register",
            json={"username": "logoutuser", "password": "password123"},
        )

        login_response = self.client.post(
            "/api/auth/login",
            json={"username": "logoutuser", "password": "password123"},
        )

        # Get the refresh token cookie
        cookies = login_response.cookies

        # Logout
        response = self.client.post(
            "/api/auth/logout", cookies={"refresh_token": cookies.get("refresh_token")}
        )

        self.assertEqual(response.status_code, 200)

        # Verify cookie is cleared in response (cookie cleared with empty value and expires)
        set_cookie = response.headers.get("set-cookie", "")
        self.assertIn("refresh_token", set_cookie)
        self.assertIn("Max-Age=0", set_cookie)

    def test_setup_status_no_users(self):
        """Fresh DB should return needs_setup=True."""
        response = self.client.get("/api/auth/setup-status")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["needs_setup"], True)

    def test_setup_status_with_user(self):
        """After register, needs_setup should be False."""
        self.client.post(
            "/api/auth/register",
            json={"username": "someuser", "password": "password123"},
        )

        response = self.client.get("/api/auth/setup-status")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["needs_setup"], False)

    def test_update_me_full_name(self):
        """Update full_name, verify returned."""
        # Register and login
        self.client.post(
            "/api/auth/register",
            json={"username": "updateuser", "password": "password123"},
        )

        login_response = self.client.post(
            "/api/auth/login",
            json={"username": "updateuser", "password": "password123"},
        )

        access_token = login_response.json()["access_token"]

        # Update full_name
        response = self.client.patch(
            "/api/auth/me",
            json={"full_name": "Updated Name"},
            headers={"Authorization": f"Bearer {access_token}"},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["full_name"], "Updated Name")

    def test_update_me_password(self):
        """Update password, verify old sessions deleted."""
        # Register and login first time
        self.client.post(
            "/api/auth/register",
            json={"username": "passupdateuser", "password": "password123"},
        )

        login_response1 = self.client.post(
            "/api/auth/login",
            json={"username": "passupdateuser", "password": "password123"},
        )

        # Get first session token
        cookies1 = login_response1.cookies
        token1 = cookies1.get("refresh_token")

        # Update password
        access_token = login_response1.json()["access_token"]
        response = self.client.patch(
            "/api/auth/me",
            json={"password": "newpassword456"},
            headers={"Authorization": f"Bearer {access_token}"},
        )

        self.assertEqual(response.status_code, 200)

        # Old session should be deleted - trying to use old refresh token should fail
        refresh_response = self.client.post(
            "/api/auth/refresh", cookies={"refresh_token": token1}
        )

        # Should fail because session was deleted
        self.assertEqual(refresh_response.status_code, 401)

    def test_case_insensitive_username(self):
        """Username uniqueness should be case-insensitive."""
        # Register with lowercase
        self.client.post(
            "/api/auth/register",
            json={"username": "caseuser", "password": "password123"},
        )

        # Try to register with same name in different case
        response = self.client.post(
            "/api/auth/register",
            json={"username": "CASEUSER", "password": "password456"},
        )

        self.assertEqual(response.status_code, 409)

    def test_login_nonexistent_user(self):
        """Login with nonexistent user should return 401."""
        response = self.client.post(
            "/api/auth/login",
            json={"username": "nonexistent", "password": "password123"},
        )

        self.assertEqual(response.status_code, 401)

    def test_get_me_requires_auth(self):
        """GET /auth/me without auth should return 401."""
        response = self.client.get("/api/auth/me")

        self.assertEqual(response.status_code, 401)

    def test_get_me_returns_profile(self):
        """GET /auth/me with valid token returns user profile."""
        # Register and login
        self.client.post(
            "/api/auth/register",
            json={
                "username": "profileuser",
                "password": "password123",
                "full_name": "Test User",
            },
        )

        login_response = self.client.post(
            "/api/auth/login",
            json={"username": "profileuser", "password": "password123"},
        )

        access_token = login_response.json()["access_token"]

        response = self.client.get(
            "/api/auth/me", headers={"Authorization": f"Bearer {access_token}"}
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["username"], "profileuser")
        self.assertEqual(data["full_name"], "Test User")


if __name__ == "__main__":
    unittest.main()
