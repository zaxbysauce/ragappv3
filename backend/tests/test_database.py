"""Unit tests for database schema initialization."""

import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.models.database import init_db, migrate_add_fork_columns


class TestDatabaseSchema(unittest.TestCase):
    """Test cases for database schema initialization."""

    def setUp(self):
        """Create a temporary database file for each test."""
        self.temp_fd, self.temp_db_path = tempfile.mkstemp(suffix='.db')
        os.close(self.temp_fd)

    def tearDown(self):
        """Clean up the temporary database file."""
        if os.path.exists(self.temp_db_path):
            os.remove(self.temp_db_path)

    def test_init_db_creates_required_tables(self):
        """Test that init_db creates all required tables and FTS virtual table."""
        # Initialize the database
        init_db(self.temp_db_path)

        # Connect and query sqlite_master for tables
        conn = sqlite3.connect(self.temp_db_path)
        cursor = conn.cursor()

        # Get all tables and virtual tables
        cursor.execute(
            "SELECT name, type FROM sqlite_master WHERE type IN ('table', 'virtual table')"
        )
        results = cursor.fetchall()
        conn.close()

        # Extract table names
        table_names = {name for name, _ in results}

        # Assert all required tables exist
        required_tables = {
            'files',
            'memories',
            'memories_fts',
            'chat_sessions',
            'chat_messages'
        }

        for table in required_tables:
            self.assertIn(
                table,
                table_names,
                f"Required table '{table}' was not created by init_db()"
            )

    def test_init_db_is_idempotent(self):
        """Test that init_db can be called multiple times without error."""
        # Initialize twice
        init_db(self.temp_db_path)
        init_db(self.temp_db_path)

        # Verify tables still exist (query both table and virtual table types)
        conn = sqlite3.connect(self.temp_db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name, type FROM sqlite_master WHERE type IN ('table', 'virtual table')"
        )
        results = cursor.fetchall()
        conn.close()

        # Extract table names
        table_names = {name for name, _ in results}

        # Assert all required tables exist
        required_tables = {
            'files',
            'memories',
            'memories_fts',
            'chat_sessions',
            'chat_messages'
        }

        for table in required_tables:
            self.assertIn(
                table,
                table_names,
                f"Required table '{table}' was not found after idempotent init_db() calls"
            )

    def test_init_db_creates_fork_columns_on_chat_sessions(self):
        """Fresh databases should include fork metadata without migrations."""
        init_db(self.temp_db_path)

        conn = sqlite3.connect(self.temp_db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(chat_sessions)")
        columns = {row[1] for row in cursor.fetchall()}
        conn.close()

        self.assertIn("forked_from_session_id", columns)
        self.assertIn("fork_message_index", columns)

    def test_migrate_add_fork_columns_preserves_existing_sessions(self):
        """Legacy chat_sessions tables should get nullable fork metadata."""
        conn = sqlite3.connect(self.temp_db_path)
        conn.execute("""
            CREATE TABLE chat_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                vault_id INTEGER NOT NULL DEFAULT 1,
                user_id INTEGER,
                title TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute(
            "INSERT INTO chat_sessions (vault_id, user_id, title) VALUES (?, ?, ?)",
            (1, 1, "Legacy"),
        )
        conn.commit()
        conn.close()

        migrate_add_fork_columns(self.temp_db_path)

        conn = sqlite3.connect(self.temp_db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(chat_sessions)")
        columns = {row[1] for row in cursor.fetchall()}
        cursor.execute(
            "SELECT title, forked_from_session_id, fork_message_index FROM chat_sessions"
        )
        row = cursor.fetchone()
        conn.close()

        self.assertIn("forked_from_session_id", columns)
        self.assertIn("fork_message_index", columns)
        self.assertEqual(row, ("Legacy", None, None))


if __name__ == '__main__':
    unittest.main()
