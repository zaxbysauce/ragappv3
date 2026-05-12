"""Tests for vault_members API routes."""

import sqlite3
import tempfile
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.auth import router as auth_router
from app.api.routes.vault_members import router as vault_members_router
from app.services.auth_service import create_access_token, hash_password

# Valid SQLite schema (avoiding UNIQUE NOCASE syntax issue in source)
TEST_SCHEMA = """
-- Users table
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    hashed_password TEXT NOT NULL,
    full_name TEXT DEFAULT '',
    role TEXT NOT NULL DEFAULT 'member' CHECK (role IN ('superadmin','admin','member','viewer')),
    is_active INTEGER NOT NULL DEFAULT 1,
    must_change_password INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login_at TIMESTAMP
);

-- Vaults table
CREATE TABLE IF NOT EXISTS vaults (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT DEFAULT '',
    owner_id INTEGER,
    org_id INTEGER,
    visibility TEXT DEFAULT 'private' CHECK (visibility IN ('private', 'org', 'public')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Vault members table
CREATE TABLE IF NOT EXISTS vault_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vault_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    permission TEXT NOT NULL DEFAULT 'read' CHECK (permission IN ('read','write','admin')),
    granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    granted_by INTEGER,
    FOREIGN KEY (vault_id) REFERENCES vaults(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (granted_by) REFERENCES users(id) ON DELETE SET NULL,
    UNIQUE(vault_id, user_id)
);

-- Groups table
CREATE TABLE IF NOT EXISTS groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    org_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (org_id) REFERENCES organizations(id) ON DELETE CASCADE,
    UNIQUE(org_id, name)
);

-- Group members table
CREATE TABLE IF NOT EXISTS group_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE(group_id, user_id)
);

-- Vault group access table
CREATE TABLE IF NOT EXISTS vault_group_access (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vault_id INTEGER NOT NULL,
    group_id INTEGER NOT NULL,
    permission TEXT NOT NULL DEFAULT 'read' CHECK (permission IN ('read','write','admin')),
    granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    granted_by INTEGER,
    FOREIGN KEY (vault_id) REFERENCES vaults(id) ON DELETE CASCADE,
    FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE,
    FOREIGN KEY (granted_by) REFERENCES users(id) ON DELETE SET NULL,
    UNIQUE(vault_id, group_id)
);

-- Org members table (used by org-scoped public vault visibility)
CREATE TABLE IF NOT EXISTS org_members (
    org_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    UNIQUE(org_id, user_id)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
CREATE INDEX IF NOT EXISTS idx_vault_members_vault_id ON vault_members(vault_id);
CREATE INDEX IF NOT EXISTS idx_vault_members_user_id ON vault_members(user_id);
CREATE INDEX IF NOT EXISTS idx_groups_org_id ON groups(org_id);
CREATE INDEX IF NOT EXISTS idx_group_members_group_id ON group_members(group_id);
CREATE INDEX IF NOT EXISTS idx_group_members_user_id ON group_members(user_id);
CREATE INDEX IF NOT EXISTS idx_vault_group_access_vault_id ON vault_group_access(vault_id);
CREATE INDEX IF NOT EXISTS idx_vault_group_access_group_id ON vault_group_access(group_id);
"""


@pytest.fixture(autouse=True)
def setup_db(monkeypatch):
    """Set up test database with schema and seed data."""
    temp_dir = tempfile.mkdtemp()
    db_path = str(Path(temp_dir) / "app.db")

    # Clear pool cache BEFORE setting up new database
    from app.models.database import _pool_cache, _pool_cache_lock

    with _pool_cache_lock:
        for path, pool in list(_pool_cache.items()):
            pool.close_all()
        _pool_cache.clear()

    # Initialize schema manually with valid SQL
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.executescript(TEST_SCHEMA)
    conn.commit()
    conn.close()

    # Patch settings
    monkeypatch.setattr("app.config.settings.data_dir", Path(temp_dir))
    monkeypatch.setattr(
        "app.config.settings.jwt_secret_key",
        "test-secret-key-for-testing-only-min-32-chars!!",
    )
    monkeypatch.setattr("app.config.settings.users_enabled", True)

    # Seed test users
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    pw = hash_password("testpass")
    conn.execute(
        "INSERT INTO users (id, username, hashed_password, full_name, role, is_active) VALUES (?, ?, ?, ?, ?, 1)",
        (1, "superadmin", pw, "Super Admin", "superadmin"),
    )
    conn.execute(
        "INSERT INTO users (id, username, hashed_password, full_name, role, is_active) VALUES (?, ?, ?, ?, ?, 1)",
        (2, "admin1", pw, "Admin One", "admin"),
    )
    conn.execute(
        "INSERT INTO users (id, username, hashed_password, full_name, role, is_active) VALUES (?, ?, ?, ?, ?, 1)",
        (3, "member1", pw, "Member One", "member"),
    )
    conn.execute(
        "INSERT INTO users (id, username, hashed_password, full_name, role, is_active) VALUES (?, ?, ?, ?, ?, 1)",
        (4, "member2", pw, "Member Two", "member"),
    )
    # Seed test vault
    conn.execute("INSERT INTO vaults (id, name) VALUES (1, 'Test Vault')")
    # Seed admin user as vault admin (needed for vault_members routes)
    conn.execute(
        "INSERT INTO vault_members (vault_id, user_id, permission, granted_by) VALUES (?, ?, ?, ?)",
        (1, 2, "admin", 1),
    )
    conn.commit()
    conn.close()

    yield db_path

    # Cleanup
    with _pool_cache_lock:
        if db_path in _pool_cache:
            _pool_cache[db_path].close_all()
            del _pool_cache[db_path]

    import shutil

    shutil.rmtree(temp_dir, ignore_errors=True)


def _get_db_conn():
    """Get a direct connection to the test database for setup."""
    from app.config import settings

    return sqlite3.connect(str(settings.sqlite_path))


def superadmin_token():
    return create_access_token(1, "superadmin", "superadmin")


def admin_token():
    return create_access_token(2, "admin1", "admin")


def member_token():
    return create_access_token(3, "member1", "member")


def auth_headers(token_fn):
    return {"Authorization": f"Bearer {token_fn()}"}


@pytest.fixture
def client():
    """Create test client with routers."""
    app = FastAPI()
    app.include_router(auth_router, prefix="/api")
    app.include_router(vault_members_router, prefix="/api")
    return TestClient(app)


class TestListVaultMembers:
    """Tests for GET /vaults/{vault_id}/members endpoint."""

    def test_admin_can_list_members(self, client):
        """Admin can list vault members (200)."""
        response = client.get(
            "/api/vaults/1/members", headers=auth_headers(admin_token)
        )
        assert response.status_code == 200
        data = response.json()
        assert "members" in data
        assert "total" in data
        member_ids = [m["user_id"] for m in data["members"]]
        assert 2 in member_ids  # admin1 is user_id 2

    def test_non_member_rejected(self, client):
        """Non-member is rejected with 403."""
        # member1 is NOT in vault - they should get 403
        response = client.get(
            "/api/vaults/1/members", headers=auth_headers(member_token)
        )
        assert response.status_code == 403

    def test_returns_total_count(self, client):
        """Returns total count accurately."""
        # Add member1 to vault
        conn = _get_db_conn()
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            "INSERT INTO vault_members (vault_id, user_id, permission, granted_by) VALUES (?, ?, ?, ?)",
            (1, 3, "read", 1),
        )
        conn.commit()
        conn.close()

        response = client.get(
            "/api/vaults/1/members", headers=auth_headers(admin_token)
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2

    def test_unauthenticated_returns_401(self, client):
        """No token returns 401."""
        response = client.get("/api/vaults/1/members")
        assert response.status_code == 401


class TestAddVaultMember:
    """Tests for POST /vaults/{vault_id}/members endpoint."""

    def test_admin_adds_member_with_read_permission(self, client):
        """Admin adds member with read permission (200)."""
        response = client.post(
            "/api/vaults/1/members",
            json={"member_user_id": 3, "permission": "read"},
            headers=auth_headers(
                superadmin_token
            ),  # superadmin bypasses permission check
        )
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == 3
        assert data["permission"] == "read"

    def test_duplicate_member_rejected(self, client):
        """Duplicate member is rejected (409)."""
        # member1 already added in fixture via vault_members table
        conn = _get_db_conn()
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            "INSERT INTO vault_members (vault_id, user_id, permission, granted_by) VALUES (?, ?, ?, ?)",
            (1, 3, "read", 1),
        )
        conn.commit()
        conn.close()

        response = client.post(
            "/api/vaults/1/members",
            json={"member_user_id": 3, "permission": "read"},
            headers=auth_headers(superadmin_token),
        )
        assert response.status_code == 409

    def test_nonexistent_user_rejected(self, client):
        """Non-existent user is rejected with 409 (FK constraint violation)."""
        response = client.post(
            "/api/vaults/1/members",
            json={"member_user_id": 999, "permission": "read"},
            headers=auth_headers(superadmin_token),
        )
        # Foreign key constraint fails, returns 409 Conflict
        assert response.status_code == 409

    def test_invalid_permission_rejected(self, client):
        """Invalid permission is rejected with 422 from Pydantic."""
        response = client.post(
            "/api/vaults/1/members",
            json={"member_user_id": 3, "permission": "invalid_permission"},
            headers=auth_headers(superadmin_token),
        )
        assert response.status_code == 422

    def test_read_permission_user_cannot_add(self, client):
        """User with read permission cannot add members (403)."""
        # Add member1 with read permission
        conn = _get_db_conn()
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            "INSERT OR IGNORE INTO vault_members (vault_id, user_id, permission, granted_by) VALUES (?, ?, ?, ?)",
            (1, 3, "read", 1),
        )
        conn.commit()
        conn.close()

        response = client.post(
            "/api/vaults/1/members",
            json={"member_user_id": 4, "permission": "read"},
            headers=auth_headers(member_token),
        )
        assert response.status_code == 403


class TestUpdateVaultMember:
    """Tests for PATCH /vaults/{vault_id}/members/{member_user_id} endpoint."""

    def test_admin_updates_permission(self, client):
        """Admin updates member permission (200)."""
        # Add member1 to vault
        conn = _get_db_conn()
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            "INSERT INTO vault_members (vault_id, user_id, permission, granted_by) VALUES (?, ?, ?, ?)",
            (1, 3, "read", 1),
        )
        conn.commit()
        conn.close()

        response = client.patch(
            "/api/vaults/1/members/3",
            json={"permission": "write"},
            headers=auth_headers(superadmin_token),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["permission"] == "write"

    def test_nonexistent_member_rejected(self, client):
        """Non-existent member is rejected with 404."""
        response = client.patch(
            "/api/vaults/1/members/999",
            json={"permission": "write"},
            headers=auth_headers(superadmin_token),
        )
        assert response.status_code == 404


class TestRemoveVaultMember:
    """Tests for DELETE /vaults/{vault_id}/members/{member_user_id} endpoint."""

    def test_admin_removes_member(self, client):
        """Admin removes member (200)."""
        # Add member1 to vault first
        conn = _get_db_conn()
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            "INSERT INTO vault_members (vault_id, user_id, permission, granted_by) VALUES (?, ?, ?, ?)",
            (1, 3, "read", 1),
        )
        conn.commit()
        conn.close()

        response = client.delete(
            "/api/vaults/1/members/3", headers=auth_headers(superadmin_token)
        )
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Member removed"

    def test_nonexistent_member_rejected(self, client):
        """Non-existent member is rejected with 404."""
        response = client.delete(
            "/api/vaults/1/members/999", headers=auth_headers(superadmin_token)
        )
        assert response.status_code == 404

    def test_self_removal_rejected(self, client):
        """Self-removal is rejected with 400."""
        # Note: The evaluate_policy function checks admin role before vault_members.
        # Admin role only has read/write access, not admin. So we use superadmin
        # who bypasses the permission check entirely.
        # But superadmin is not in vault_members, so we add them first
        conn = _get_db_conn()
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            "INSERT INTO vault_members (vault_id, user_id, permission, granted_by) VALUES (?, ?, ?, ?)",
            (1, 1, "admin", 1),  # superadmin as admin in vault
        )
        conn.commit()
        conn.close()

        response = client.delete(
            "/api/vaults/1/members/1", headers=auth_headers(superadmin_token)
        )
        # superadmin (user_id=1) tries to remove themselves - should fail
        assert response.status_code == 400
        assert "Cannot remove yourself" in response.json()["detail"]
