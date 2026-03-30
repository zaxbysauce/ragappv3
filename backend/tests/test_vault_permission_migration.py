"""
Tests for vault permission migration functionality.

Verifies that the vault_members, vault_group_access tables are created correctly,
and that the migrate_add_vault_permission_columns() function properly adds
owner_id, org_id, and visibility columns to the vaults table.
"""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from app.models.database import (
    migrate_add_vault_permission_columns,
    run_migrations,
    SCHEMA,
)


class TestVaultMembersTableCreated:
    """Test suite for vault_members table creation."""

    def test_vault_members_table_created(self, tmp_path: Path) -> None:
        """Verify vault_members table exists with correct columns and constraints."""
        db_path = tmp_path / "test.db"

        # Create database with schema
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(SCHEMA)
        conn.close()

        # Verify table exists
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='vault_members'"
        )
        result = cursor.fetchone()
        assert result is not None, "vault_members table should exist"
        conn.close()

        # Verify columns
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute("PRAGMA table_info(vault_members)")
        columns = {row[1] for row in cursor.fetchall()}
        conn.close()

        expected_columns = {
            "id",
            "vault_id",
            "user_id",
            "permission",
            "granted_at",
            "granted_by",
        }
        assert expected_columns.issubset(columns), (
            f"Missing columns: {expected_columns - columns}"
        )

        # Verify UNIQUE constraint on (vault_id, user_id)
        # Check the table definition itself - UNIQUE is inline in CREATE TABLE
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='vault_members'"
        )
        table_sql = cursor.fetchone()[0]
        conn.close()

        # The UNIQUE constraint is defined inline as UNIQUE(vault_id, user_id)
        has_unique_constraint = "UNIQUE(vault_id, user_id)" in table_sql
        assert has_unique_constraint, (
            f"Should have UNIQUE constraint on (vault_id, user_id) in table definition: {table_sql}"
        )

        # Verify permission CHECK constraint
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute("PRAGMA table_info(vault_members)")
        permission_col = None
        for row in cursor.fetchall():
            if row[1] == "permission":
                permission_col = row
                break
        conn.close()

        assert permission_col is not None, "permission column should exist"
        assert permission_col[2] == "TEXT", "permission should be TEXT type"

        # Verify default permission is 'read'
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute("PRAGMA table_info(vault_members)")
        for row in cursor.fetchall():
            if row[1] == "permission":
                # Check default value (dflt_value is index 4)
                assert row[4] == "'read'", "Default permission should be 'read'"
                break
        conn.close()


class TestVaultGroupAccessTableCreated:
    """Test suite for vault_group_access table creation."""

    def test_vault_group_access_table_created(self, tmp_path: Path) -> None:
        """Verify vault_group_access table exists with correct columns and constraints."""
        db_path = tmp_path / "test.db"

        # Create database with schema
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(SCHEMA)
        conn.close()

        # Verify table exists
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='vault_group_access'"
        )
        result = cursor.fetchone()
        assert result is not None, "vault_group_access table should exist"
        conn.close()

        # Verify columns
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute("PRAGMA table_info(vault_group_access)")
        columns = {row[1] for row in cursor.fetchall()}
        conn.close()

        expected_columns = {
            "id",
            "vault_id",
            "group_id",
            "permission",
            "granted_at",
            "granted_by",
        }
        assert expected_columns.issubset(columns), (
            f"Missing columns: {expected_columns - columns}"
        )

        # Verify UNIQUE constraint on (vault_id, group_id)
        # Check the table definition itself - UNIQUE is inline in CREATE TABLE
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='vault_group_access'"
        )
        table_sql = cursor.fetchone()[0]
        conn.close()

        # The UNIQUE constraint is defined inline as UNIQUE(vault_id, group_id)
        has_unique_constraint = "UNIQUE(vault_id, group_id)" in table_sql
        assert has_unique_constraint, (
            f"Should have UNIQUE constraint on (vault_id, group_id) in table definition: {table_sql}"
        )


class TestVaultColumnsAdded:
    """Test suite for vault permission columns migration."""

    def test_vault_columns_added(self, tmp_path: Path) -> None:
        """Run migration on temp DB, verify vaults table has owner_id, org_id, visibility columns."""
        db_path = tmp_path / "test.db"

        # Create minimal database with just vaults table
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE vaults (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("INSERT INTO vaults (name) VALUES ('Test Vault')")
        conn.commit()
        conn.close()

        # Verify columns don't exist before migration
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute("PRAGMA table_info(vaults)")
        columns_before = {row[1] for row in cursor.fetchall()}
        conn.close()

        assert "owner_id" not in columns_before
        assert "org_id" not in columns_before
        assert "visibility" not in columns_before

        # Run migration
        migrate_add_vault_permission_columns(str(db_path))

        # Verify columns exist after migration
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute("PRAGMA table_info(vaults)")
        columns_after = {row[1] for row in cursor.fetchall()}
        conn.close()

        assert "owner_id" in columns_after, "owner_id column should be added"
        assert "org_id" in columns_after, "org_id column should be added"
        assert "visibility" in columns_after, "visibility column should be added"

    def test_vault_columns_idempotent(self, tmp_path: Path) -> None:
        """Run migration twice, verify no errors."""
        db_path = tmp_path / "test.db"

        # Create minimal database
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE vaults (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT DEFAULT ''
            )
        """)
        conn.execute("INSERT INTO vaults (name) VALUES ('Test Vault')")
        conn.commit()
        conn.close()

        # Run migration twice - should not raise any errors
        migrate_add_vault_permission_columns(str(db_path))
        migrate_add_vault_permission_columns(str(db_path))

        # Verify columns exist
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute("PRAGMA table_info(vaults)")
        columns = {row[1] for row in cursor.fetchall()}
        conn.close()

        assert "owner_id" in columns
        assert "org_id" in columns
        assert "visibility" in columns


class TestVisibilityCheckConstraint:
    """Test suite for visibility CHECK constraint."""

    def test_visibility_check_constraint(self, tmp_path: Path) -> None:
        """Verify CHECK(visibility IN ('private','org','public')) works."""
        db_path = tmp_path / "test.db"

        # Create database with the migration applied
        run_migrations(str(db_path))

        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA foreign_keys = ON")

        # Valid values should work
        for visibility in ("private", "org", "public"):
            conn.execute(
                "INSERT INTO vaults (name, visibility) VALUES (?, ?)",
                (f"vault_{visibility}", visibility),
            )

        conn.commit()
        conn.close()

        # Invalid value should fail
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA foreign_keys = ON")

        with pytest.raises(sqlite3.IntegrityError) as exc_info:
            conn.execute(
                "INSERT INTO vaults (name, visibility) VALUES (?, ?)",
                ("invalid_vault", "invalid_visibility"),
            )
            conn.commit()

        conn.close()

        assert (
            "CHECK constraint failed" in str(exc_info.value)
            or "constraint" in str(exc_info.value).lower()
        )

    def test_visibility_default(self, tmp_path: Path) -> None:
        """Verify new vaults get 'private' as default visibility."""
        db_path = tmp_path / "test.db"

        # Create database with the migration applied
        run_migrations(str(db_path))

        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA foreign_keys = ON")

        # Insert vault without specifying visibility
        conn.execute("INSERT INTO vaults (name) VALUES (?)", ("auto_vault",))
        conn.commit()

        # Check the default visibility
        cursor = conn.execute(
            "SELECT visibility FROM vaults WHERE name = ?", ("auto_vault",)
        )
        result = cursor.fetchone()
        conn.close()

        assert result is not None
        assert result[0] == "private", "Default visibility should be 'private'"


class TestVaultMembersPermissionCheck:
    """Test suite for vault_members permission CHECK constraint."""

    def test_vault_members_permission_check(self, tmp_path: Path) -> None:
        """Verify CHECK(permission IN ('read','write','admin')) works in vault_members."""
        db_path = tmp_path / "test.db"

        # Create database with full schema
        run_migrations(str(db_path))

        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA foreign_keys = ON")

        # Get a vault for testing
        cursor = conn.execute("SELECT id FROM vaults LIMIT 1")
        vault_id = cursor.fetchone()[0]

        # Create a test user first (needed for FK constraint)
        conn.execute(
            "INSERT INTO users (username, hashed_password, role) VALUES (?, ?, ?)",
            ("testuser", "hash123", "member"),
        )
        conn.commit()

        cursor = conn.execute("SELECT id FROM users WHERE username = ?", ("testuser",))
        user_id = cursor.fetchone()[0]

        # Create additional vaults for testing different permissions (UNIQUE constraint on vault_id, user_id)
        conn.execute("INSERT INTO vaults (name) VALUES ('vault_read')")
        conn.execute("INSERT INTO vaults (name) VALUES ('vault_write')")
        conn.execute("INSERT INTO vaults (name) VALUES ('vault_admin')")
        conn.commit()

        cursor = conn.execute("SELECT id FROM vaults WHERE name = 'vault_read'")
        vault_read_id = cursor.fetchone()[0]
        cursor = conn.execute("SELECT id FROM vaults WHERE name = 'vault_write'")
        vault_write_id = cursor.fetchone()[0]
        cursor = conn.execute("SELECT id FROM vaults WHERE name = 'vault_admin'")
        vault_admin_id = cursor.fetchone()[0]

        # Valid permissions should work
        conn.execute(
            "INSERT INTO vault_members (vault_id, user_id, permission) VALUES (?, ?, ?)",
            (vault_read_id, user_id, "read"),
        )
        conn.execute(
            "INSERT INTO vault_members (vault_id, user_id, permission) VALUES (?, ?, ?)",
            (vault_write_id, user_id, "write"),
        )
        conn.execute(
            "INSERT INTO vault_members (vault_id, user_id, permission) VALUES (?, ?, ?)",
            (vault_admin_id, user_id, "admin"),
        )

        conn.commit()
        conn.close()

        # Invalid permission should fail
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA foreign_keys = ON")

        # Create a new vault for the invalid test
        conn.execute("INSERT INTO vaults (name) VALUES ('vault_invalid')")
        conn.commit()
        cursor = conn.execute("SELECT id FROM vaults WHERE name = 'vault_invalid'")
        vault_invalid_id = cursor.fetchone()[0]

        with pytest.raises(sqlite3.IntegrityError) as exc_info:
            conn.execute(
                "INSERT INTO vault_members (vault_id, user_id, permission) VALUES (?, ?, ?)",
                (vault_invalid_id, user_id, "invalid_permission"),
            )
            conn.commit()

        conn.close()

        assert (
            "CHECK constraint failed" in str(exc_info.value)
            or "constraint" in str(exc_info.value).lower()
        )


class TestForeignKeysOnVaultMembers:
    """Test suite for vault_members foreign key constraints."""

    def test_foreign_keys_on_vault_members(self, tmp_path: Path) -> None:
        """Verify FK constraints work (INSERT with non-existent user_id should fail)."""
        db_path = tmp_path / "test.db"

        # Create database with full schema
        run_migrations(str(db_path))

        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA foreign_keys = ON")

        # Get a vault for testing
        cursor = conn.execute("SELECT id FROM vaults LIMIT 1")
        vault_id = cursor.fetchone()[0]
        conn.close()

        # Try to insert with non-existent user_id
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA foreign_keys = ON")

        with pytest.raises(sqlite3.IntegrityError) as exc_info:
            conn.execute(
                "INSERT INTO vault_members (vault_id, user_id, permission) VALUES (?, ?, ?)",
                (vault_id, 999999, "read"),  # 999999 doesn't exist
            )
            conn.commit()

        conn.close()

        # Should fail with foreign key constraint error
        assert "FOREIGN KEY constraint failed" in str(exc_info.value)

    def test_foreign_keys_on_vault_group_access(self, tmp_path: Path) -> None:
        """Verify FK constraints work for vault_group_access (non-existent group_id)."""
        db_path = tmp_path / "test.db"

        # Create database with full schema
        run_migrations(str(db_path))

        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA foreign_keys = ON")

        # Get a vault for testing
        cursor = conn.execute("SELECT id FROM vaults LIMIT 1")
        vault_id = cursor.fetchone()[0]
        conn.close()

        # Try to insert with non-existent group_id
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA foreign_keys = ON")

        with pytest.raises(sqlite3.IntegrityError) as exc_info:
            conn.execute(
                "INSERT INTO vault_group_access (vault_id, group_id, permission) VALUES (?, ?, ?)",
                (vault_id, 999999, "read"),  # 999999 doesn't exist
            )
            conn.commit()

        conn.close()

        # Should fail with foreign key constraint error
        assert "FOREIGN KEY constraint failed" in str(exc_info.value)


class TestRunMigrationsIntegration:
    """Integration tests for run_migrations function."""

    def test_run_migrations_creates_all_vault_permission_tables(
        self, tmp_path: Path
    ) -> None:
        """Verify run_migrations creates vault_members, vault_group_access, and permission columns."""
        db_path = tmp_path / "test.db"

        # Run full migrations
        run_migrations(str(db_path))

        # Verify vault_members table
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='vault_members'"
        )
        assert cursor.fetchone() is not None, "vault_members table should exist"

        # Verify vault_group_access table
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='vault_group_access'"
        )
        assert cursor.fetchone() is not None, "vault_group_access table should exist"

        # Verify permission columns on vaults
        cursor = conn.execute("PRAGMA table_info(vaults)")
        columns = {row[1] for row in cursor.fetchall()}
        conn.close()

        assert "owner_id" in columns
        assert "org_id" in columns
        assert "visibility" in columns

    def test_default_vault_has_private_visibility(self, tmp_path: Path) -> None:
        """Verify the default vault created by run_migrations has 'private' visibility."""
        db_path = tmp_path / "test.db"

        # Run full migrations
        run_migrations(str(db_path))

        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute("SELECT visibility FROM vaults WHERE id = 1")
        result = cursor.fetchone()
        conn.close()

        assert result is not None
        assert result[0] == "private", "Default vault should have 'private' visibility"
