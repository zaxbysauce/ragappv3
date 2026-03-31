"""Tests for org_membership helpers in deps.py."""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from app.api.deps import (
    get_user_orgs,
    get_user_primary_org,
    MultipleOrgError,
)
from app.models.database import _pool_cache, _pool_cache_lock


# Valid SQLite schema matching production structure
TEST_SCHEMA = """
-- Users table
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    hashed_password TEXT NOT NULL,
    full_name TEXT DEFAULT '',
    role TEXT NOT NULL DEFAULT 'member' CHECK (role IN ('superadmin','admin','member','viewer')),
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login_at TIMESTAMP,
    must_change_password INTEGER DEFAULT 0,
    failed_attempts INTEGER DEFAULT 0,
    locked_until TIMESTAMP
);

-- Organizations table
CREATE TABLE IF NOT EXISTS organizations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    description TEXT DEFAULT '',
    slug TEXT UNIQUE,
    created_by INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (created_by) REFERENCES users(id)
);

-- Organization members
CREATE TABLE IF NOT EXISTS org_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    org_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    role TEXT NOT NULL DEFAULT 'member' CHECK (role IN ('owner','admin','member')),
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (org_id) REFERENCES organizations(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE(org_id, user_id)
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

-- Group members
CREATE TABLE IF NOT EXISTS group_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE(group_id, user_id)
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
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (owner_id) REFERENCES users(id),
    FOREIGN KEY (org_id) REFERENCES organizations(id)
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

-- Indexes
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_org_members_org_id ON org_members(org_id);
CREATE INDEX IF NOT EXISTS idx_org_members_user_id ON org_members(user_id);
"""


@pytest.fixture(autouse=True)
def setup_db(monkeypatch):
    """Set up test database with schema and seed data."""
    temp_dir = tempfile.mkdtemp()
    db_path = str(Path(temp_dir) / "app.db")

    # Clear pool cache BEFORE setting up new database
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
    conn.execute(
        "INSERT INTO users (id, username, hashed_password, full_name, role, is_active) VALUES (?, ?, ?, ?, ?, 1)",
        (1, "user_one", "hash1", "User One", "member"),
    )
    conn.execute(
        "INSERT INTO users (id, username, hashed_password, full_name, role, is_active) VALUES (?, ?, ?, ?, ?, 1)",
        (2, "user_two", "hash2", "User Two", "member"),
    )
    conn.execute(
        "INSERT INTO users (id, username, hashed_password, full_name, role, is_active) VALUES (?, ?, ?, ?, ?, 1)",
        (3, "user_three", "hash3", "User Three", "member"),
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
    """Get a direct connection to the test database."""
    from app.config import settings

    return sqlite3.connect(str(settings.sqlite_path))


def _create_org(name: str, owner_user_id: int):
    """Create an organization and add owner as owner."""
    conn = _get_db_conn()
    conn.execute("PRAGMA foreign_keys = ON")
    cursor = conn.execute(
        "INSERT INTO organizations (name, description, slug, created_by) VALUES (?, ?, ?, ?)",
        (name, f"{name} description", name.lower().replace(" ", "-"), owner_user_id),
    )
    org_id = cursor.lastrowid
    conn.execute(
        "INSERT INTO org_members (org_id, user_id, role) VALUES (?, ?, 'owner')",
        (org_id, owner_user_id),
    )
    conn.commit()
    conn.close()
    return org_id


def _add_org_member(org_id: int, user_id: int, role: str = "member"):
    """Add a member to an organization."""
    conn = _get_db_conn()
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(
        "INSERT OR IGNORE INTO org_members (org_id, user_id, role) VALUES (?, ?, ?)",
        (org_id, user_id, role),
    )
    conn.commit()
    conn.close()


# =============================================================================
# Tests for get_user_orgs
# =============================================================================


class TestGetUserOrgs:
    """Tests for get_user_orgs function."""

    def test_get_user_orgs_returns_empty_list_for_user_with_no_orgs(self):
        """get_user_orgs returns empty list for user with no org memberships."""
        conn = _get_db_conn()
        try:
            # User 1 has no org memberships
            result = get_user_orgs(1, conn)
            assert result == []
        finally:
            conn.close()

    def test_get_user_orgs_returns_single_org_id_for_user_with_one_org(self):
        """get_user_orgs returns list with single org ID for user in one org."""
        conn = _get_db_conn()
        try:
            # Create org and add user 1 as member
            org_id = _create_org("Single Org", 1)

            result = get_user_orgs(1, conn)
            assert result == [org_id]
        finally:
            conn.close()

    def test_get_user_orgs_returns_multiple_org_ids_for_user_with_multiple_orgs(self):
        """get_user_orgs returns list of all org IDs for user in multiple orgs."""
        conn = _get_db_conn()
        try:
            # Create multiple orgs and add user 1 to all of them
            org1_id = _create_org("Multi Org One", 1)
            org2_id = _create_org("Multi Org Two", 2)
            org3_id = _create_org("Multi Org Three", 3)

            # Add user 1 to org2 and org3 (user 1 is already in org1 as owner)
            _add_org_member(org2_id, 1, "member")
            _add_org_member(org3_id, 1, "member")

            result = get_user_orgs(1, conn)
            assert len(result) == 3
            assert set(result) == {org1_id, org2_id, org3_id}
        finally:
            conn.close()

    def test_get_user_orgs_returns_empty_list_for_nonexistent_user(self):
        """get_user_orgs returns empty list for non-existent user ID."""
        conn = _get_db_conn()
        try:
            result = get_user_orgs(9999, conn)
            assert result == []
        finally:
            conn.close()


# =============================================================================
# Tests for get_user_primary_org
# =============================================================================


class TestGetUserPrimaryOrg:
    """Tests for get_user_primary_org function."""

    def test_get_user_primary_org_returns_none_for_user_with_no_orgs(self):
        """get_user_primary_org returns None for user with no org memberships."""
        conn = _get_db_conn()
        try:
            # User 1 has no org memberships
            result = get_user_primary_org(1, conn)
            assert result is None
        finally:
            conn.close()

    def test_get_user_primary_org_returns_org_id_for_user_with_one_org(self):
        """get_user_primary_org returns org ID for user in exactly one org."""
        conn = _get_db_conn()
        try:
            # Create org and add user 1 as member
            org_id = _create_org("Primary Org Test", 1)

            result = get_user_primary_org(1, conn)
            assert result == org_id
        finally:
            conn.close()

    def test_get_user_primary_org_raises_multiple_org_error_for_user_with_multiple_orgs(
        self,
    ):
        """get_user_primary_org raises MultipleOrgError for user in multiple orgs."""
        conn = _get_db_conn()
        try:
            # Create multiple orgs and add user 1 to all of them
            org1_id = _create_org("Error Org One", 1)
            org2_id = _create_org("Error Org Two", 2)

            # Add user 1 to org2 (user 1 is already in org1 as owner)
            _add_org_member(org2_id, 1, "member")

            with pytest.raises(MultipleOrgError) as exc_info:
                get_user_primary_org(1, conn)

            # Verify error message contains user ID and org IDs
            assert "User 1" in str(exc_info.value)
            assert "multiple organizations" in str(exc_info.value)
        finally:
            conn.close()

    def test_get_user_primary_org_returns_none_for_nonexistent_user(self):
        """get_user_primary_org returns None for non-existent user ID."""
        conn = _get_db_conn()
        try:
            result = get_user_primary_org(9999, conn)
            assert result is None
        finally:
            conn.close()


# =============================================================================
# Tests for MultipleOrgError
# =============================================================================


class TestMultipleOrgError:
    """Tests for MultipleOrgError exception."""

    def test_multiple_org_error_is_raised_with_message(self):
        """MultipleOrgError is raised with descriptive message."""
        conn = _get_db_conn()
        try:
            # Create multiple orgs and add user 1 to all of them
            org1_id = _create_org("Error Message Org One", 1)
            org2_id = _create_org("Error Message Org Two", 2)
            org3_id = _create_org("Error Message Org Three", 3)

            _add_org_member(org2_id, 1, "member")
            _add_org_member(org3_id, 1, "member")

            with pytest.raises(MultipleOrgError) as exc_info:
                get_user_primary_org(1, conn)

            error_message = str(exc_info.value)
            assert "User 1" in error_message
            assert "multiple organizations" in error_message
            # Verify all org IDs are mentioned in the error
            assert str(org1_id) in error_message
            assert str(org2_id) in error_message
            assert str(org3_id) in error_message
        finally:
            conn.close()

    def test_multiple_org_error_inheritance(self):
        """MultipleOrgError is a subclass of Exception."""
        assert issubclass(MultipleOrgError, Exception)

    def test_multiple_org_error_can_be_caught_as_exception(self):
        """MultipleOrgError can be caught as general Exception."""
        conn = _get_db_conn()
        try:
            org1_id = _create_org("Catch Test Org One", 1)
            org2_id = _create_org("Catch Test Org Two", 2)

            _add_org_member(org2_id, 1, "member")

            # Catch as general Exception
            try:
                get_user_primary_org(1, conn)
                assert False, "Should have raised MultipleOrgError"
            except Exception as e:
                assert isinstance(e, MultipleOrgError)
        finally:
            conn.close()
