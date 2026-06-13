"""
Tests for Issue #225 security hardening:
- CSRF protection on update_user_organizations and update_user_groups
- Caller-org scoping on update_user_organizations

These tests verify:
- PUT /users/{id}/organizations requires CSRF token
- PUT /users/{id}/groups requires CSRF token
- Non-superadmin admin cannot assign user to orgs they don't belong to
- Superadmin can assign user to any org (bypass scoping)
- Admin belonging to the org can assign user to that org
"""

import os
import sqlite3
import tempfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Set up test environment BEFORE importing app modules
os.environ["JWT_SECRET_KEY"] = (
    "test-jwt-secret-key-for-testing-only-12345678901234567890"
)
os.environ["USERS_ENABLED"] = "true"

from app.services.auth_service import create_access_token, hash_password


def setup_test_db(db_path: str) -> sqlite3.Connection:
    """Set up test database with schema and initial users."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE COLLATE NOCASE,
            hashed_password TEXT NOT NULL,
            full_name TEXT DEFAULT '',
            role TEXT NOT NULL DEFAULT 'member' CHECK (role IN ('superadmin','admin','member','viewer')),
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login_at TIMESTAMP,
            must_change_password INTEGER NOT NULL DEFAULT 0,
            failed_attempts INTEGER NOT NULL DEFAULT 0,
            locked_until TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS organizations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE COLLATE NOCASE,
            description TEXT DEFAULT '',
            slug TEXT UNIQUE,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (created_by) REFERENCES users(id)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS org_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            org_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            role TEXT NOT NULL DEFAULT 'member' CHECK (role IN ('owner','admin','member')),
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (org_id) REFERENCES organizations(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            UNIQUE(org_id, user_id)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            org_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (org_id) REFERENCES organizations(id) ON DELETE CASCADE,
            UNIQUE(org_id, name)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS group_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            UNIQUE(group_id, user_id)
        )
    """)

    conn.execute("CREATE INDEX IF NOT EXISTS idx_org_members_user_id ON org_members(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_org_members_org_id ON org_members(org_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_group_members_group_id ON group_members(group_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_group_members_user_id ON group_members(user_id)")

    conn.commit()
    return conn


def create_user(
    conn: sqlite3.Connection,
    username: str,
    password: str,
    role: str,
    full_name: str = "",
) -> int:
    """Create a test user and return its ID."""
    hashed = hash_password(password)
    cursor = conn.execute(
        """INSERT INTO users (username, hashed_password, full_name, role, is_active)
           VALUES (?, ?, ?, ?, 1)""",
        (username, hashed, full_name, role),
    )
    conn.commit()
    return cursor.lastrowid


def get_token(user_id: int, username: str, role: str) -> str:
    """Generate a JWT token for a test user."""
    return create_access_token(user_id, username, role)


class TestUserOrgsCsrfAndScoping:
    """Tests for CSRF + caller-org scoping on user org/group routes."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test database for each test."""
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test.db")

        from app.models.database import _pool_cache

        _pool_cache.clear()

        self.conn = setup_test_db(self.db_path)

        # Create test users
        self.superadmin_id = create_user(
            self.conn, "superadmin", "pass123", "superadmin", "Super Admin"
        )
        self.admin_id = create_user(
            self.conn, "admin", "pass123", "admin", "Admin User"
        )
        self.member_id = create_user(
            self.conn, "member", "pass123", "member", "Regular Member"
        )

        # Create organizations
        cursor = self.conn.execute(
            "INSERT INTO organizations (name, description) VALUES (?, ?)",
            ("Org Alpha", "Alpha org"),
        )
        self.org_alpha_id = cursor.lastrowid

        cursor = self.conn.execute(
            "INSERT INTO organizations (name, description) VALUES (?, ?)",
            ("Org Beta", "Beta org"),
        )
        self.org_beta_id = cursor.lastrowid

        cursor = self.conn.execute(
            "INSERT INTO organizations (name, description) VALUES (?, ?)",
            ("Org Gamma", "Gamma org"),
        )
        self.org_gamma_id = cursor.lastrowid

        # Admin belongs to Alpha and Beta only
        self.conn.execute(
            "INSERT INTO org_members (org_id, user_id, role) VALUES (?, ?, ?)",
            (self.org_alpha_id, self.admin_id, "admin"),
        )
        self.conn.execute(
            "INSERT INTO org_members (org_id, user_id, role) VALUES (?, ?, ?)",
            (self.org_beta_id, self.admin_id, "member"),
        )

        # Create a group in Alpha
        cursor = self.conn.execute(
            "INSERT INTO groups (org_id, name, description) VALUES (?, ?, ?)",
            (self.org_alpha_id, "Group A1", "Group in Alpha"),
        )
        self.group_a1_id = cursor.lastrowid

        # Member is in Alpha so group membership is valid
        self.conn.execute(
            "INSERT INTO org_members (org_id, user_id, role) VALUES (?, ?, ?)",
            (self.org_alpha_id, self.member_id, "member"),
        )

        self.conn.commit()

        # Create app with users router
        from app.api.routes.users import router as users_router

        self.app = FastAPI()
        self.app.include_router(users_router)

        from app.api import deps
        from app.models.database import SQLiteConnectionPool

        test_pool = SQLiteConnectionPool(self.db_path, max_size=3)

        def override_get_db():
            conn = test_pool.get_connection()
            try:
                yield conn
            finally:
                test_pool.release_connection(conn)

        from app.api.routes import users

        original_get_pool = users.get_pool
        users.get_pool = lambda path: test_pool

        self.app.dependency_overrides[deps.get_db] = override_get_db

        self.test_pool = test_pool
        self.original_get_pool = original_get_pool

        from app.config import settings

        self._orig_users_enabled = settings.users_enabled
        self._orig_jwt_secret = settings.jwt_secret_key
        settings.users_enabled = True
        settings.jwt_secret_key = os.environ["JWT_SECRET_KEY"]

        self.client = TestClient(self.app)

        yield

        self.client.close()
        _pool_cache.clear()
        self.conn.close()

        from app.api.routes import users

        users.get_pool = self.original_get_pool
        self.test_pool.close_all()
        settings.users_enabled = self._orig_users_enabled
        settings.jwt_secret_key = self._orig_jwt_secret

        import shutil

        try:
            shutil.rmtree(self.tmpdir, ignore_errors=True)
        except Exception:
            pass

    def _override_csrf(self):
        """Override csrf_protect to pass-through for non-CSRF tests."""
        from app.security import csrf_protect

        self.app.dependency_overrides[csrf_protect] = lambda: "test-csrf-token"

    # ─── CSRF tests ──────────────────────────────────────────────

    def test_put_user_organizations_without_csrf_rejected(self):
        """PUT /users/{id}/organizations without CSRF override is rejected.

        Without a csrf_manager on app.state the csrf_protect dependency
        returns 503 (service unavailable) rather than 403, but either proves
        the dependency is wired — the route does NOT succeed (200).
        """
        token = get_token(self.admin_id, "admin", "admin")
        response = self.client.put(
            f"/users/{self.member_id}/organizations",
            json={"org_ids": [self.org_alpha_id]},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code in (403, 503)

    def test_put_user_groups_without_csrf_rejected(self):
        """PUT /users/{id}/groups without CSRF override is rejected."""
        token = get_token(self.admin_id, "admin", "admin")
        response = self.client.put(
            f"/users/{self.member_id}/groups",
            json={"group_ids": [self.group_a1_id]},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code in (403, 503)

    def test_put_user_organizations_with_csrf_succeeds(self):
        """PUT /users/{id}/organizations with CSRF override succeeds."""
        self._override_csrf()
        token = get_token(self.admin_id, "admin", "admin")
        response = self.client.put(
            f"/users/{self.member_id}/organizations",
            json={"org_ids": [self.org_alpha_id]},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200

    def test_put_user_groups_with_csrf_succeeds(self):
        """PUT /users/{id}/groups with CSRF override succeeds."""
        self._override_csrf()
        token = get_token(self.admin_id, "admin", "admin")
        response = self.client.put(
            f"/users/{self.member_id}/groups",
            json={"group_ids": [self.group_a1_id]},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200

    # ─── Caller-org scoping tests ────────────────────────────────

    def test_admin_cannot_assign_user_to_org_they_dont_belong_to(self):
        """Admin not in Gamma cannot assign member to Gamma."""
        self._override_csrf()
        token = get_token(self.admin_id, "admin", "admin")
        response = self.client.put(
            f"/users/{self.member_id}/organizations",
            json={"org_ids": [self.org_gamma_id]},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 403
        assert "do not belong to" in response.json()["detail"]

    def test_admin_can_assign_user_to_org_they_belong_to(self):
        """Admin in Alpha can assign member to Alpha."""
        self._override_csrf()
        token = get_token(self.admin_id, "admin", "admin")
        response = self.client.put(
            f"/users/{self.member_id}/organizations",
            json={"org_ids": [self.org_alpha_id, self.org_beta_id]},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        orgs = response.json()["organizations"]
        org_ids = {o["id"] for o in orgs}
        assert self.org_alpha_id in org_ids
        assert self.org_beta_id in org_ids

    def test_admin_partial_unauthorized_orgs_rejected(self):
        """Admin in Alpha+Beta but not Gamma: assigning all three is rejected."""
        self._override_csrf()
        token = get_token(self.admin_id, "admin", "admin")
        response = self.client.put(
            f"/users/{self.member_id}/organizations",
            json={"org_ids": [self.org_alpha_id, self.org_gamma_id]},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 403
        detail = response.json()["detail"]
        assert "do not belong to" in detail
        assert str(self.org_gamma_id) in detail

    def test_superadmin_bypasses_org_scoping(self):
        """Superadmin can assign user to any org regardless of membership."""
        self._override_csrf()
        token = get_token(self.superadmin_id, "superadmin", "superadmin")
        response = self.client.put(
            f"/users/{self.member_id}/organizations",
            json={"org_ids": [self.org_gamma_id]},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        orgs = response.json()["organizations"]
        org_ids = {o["id"] for o in orgs}
        assert self.org_gamma_id in org_ids

    def test_empty_org_list_allowed_for_admin(self):
        """Admin can clear memberships (empty org list) without scoping issues."""
        self._override_csrf()
        token = get_token(self.admin_id, "admin", "admin")
        response = self.client.put(
            f"/users/{self.member_id}/organizations",
            json={"org_ids": []},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
