"""Verification tests for vault_id schema changes (Task 1.1).

These tests verify that vault_id columns in files and chat_sessions tables
do NOT have a DEFAULT 1 clause in the SCHEMA definition.

ACCEPTANCE CRITERIA:
1. SCHEMA string no longer contains `DEFAULT 1` for vault_id in files table
2. SCHEMA string no longer contains `DEFAULT 1` for vault_id in chat_sessions table
3. Fresh in-memory database created with SCHEMA has vault_id as NOT NULL with no default
"""

import re
import sqlite3
import sys
import unittest
from pathlib import Path

# Ensure app module is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.models.database import SCHEMA


class TestVaultIdSchemaChange(unittest.TestCase):
    """Test vault_id schema compliance with DEFAULT 1 removal."""

    def test_schema_files_table_vault_id_has_no_default(self):
        """SCHEMA for files.vault_id must NOT contain DEFAULT 1."""
        # Extract the files table CREATE TABLE statement
        files_table_match = re.search(
            r'CREATE TABLE IF NOT EXISTS files\s*\((.*?)\);',
            SCHEMA,
            re.DOTALL | re.IGNORECASE,
        )
        self.assertIsNotNone(files_table_match, "files table not found in SCHEMA")

        files_table_ddl = files_table_match.group(1)

        # Check that vault_id line exists and does NOT have DEFAULT 1
        vault_id_pattern = re.search(
            r'vault_id\s+INTEGER\s+NOT\s+NULL',
            files_table_ddl,
            re.IGNORECASE,
        )
        self.assertIsNotNone(
            vault_id_pattern,
            "vault_id INTEGER NOT NULL not found in files table definition",
        )

        # Verify DEFAULT 1 is NOT present for vault_id
        vault_id_full = re.search(
            r'vault_id\s+INTEGER\s+NOT\s+NULL\s+DEFAULT\s+1',
            files_table_ddl,
            re.IGNORECASE,
        )
        self.assertIsNone(
            vault_id_full,
            "files.vault_id should NOT have DEFAULT 1 clause. "
            "Found: vault_id INTEGER NOT NULL DEFAULT 1",
        )

    def test_schema_chat_sessions_table_vault_id_has_no_default(self):
        """SCHEMA for chat_sessions.vault_id must NOT contain DEFAULT 1."""
        # Extract the chat_sessions table CREATE TABLE statement
        chat_table_match = re.search(
            r'CREATE TABLE IF NOT EXISTS chat_sessions\s*\((.*?)\);',
            SCHEMA,
            re.DOTALL | re.IGNORECASE,
        )
        self.assertIsNotNone(chat_table_match, "chat_sessions table not found in SCHEMA")

        chat_table_ddl = chat_table_match.group(1)

        # Check that vault_id line exists and does NOT have DEFAULT 1
        vault_id_pattern = re.search(
            r'vault_id\s+INTEGER\s+NOT\s+NULL',
            chat_table_ddl,
            re.IGNORECASE,
        )
        self.assertIsNotNone(
            vault_id_pattern,
            "vault_id INTEGER NOT NULL not found in chat_sessions table definition",
        )

        # Verify DEFAULT 1 is NOT present for vault_id
        vault_id_full = re.search(
            r'vault_id\s+INTEGER\s+NOT\s+NULL\s+DEFAULT\s+1',
            chat_table_ddl,
            re.IGNORECASE,
        )
        self.assertIsNone(
            vault_id_full,
            "chat_sessions.vault_id should NOT have DEFAULT 1 clause. "
            "Found: vault_id INTEGER NOT NULL DEFAULT 1",
        )

    def test_fresh_db_files_vault_id_not_null_no_default(self):
        """Fresh DB created from SCHEMA has files.vault_id as NOT NULL with no default."""
        conn = sqlite3.connect(":memory:")
        try:
            conn.executescript(SCHEMA)

            # Check files.vault_id column definition
            cursor = conn.execute("PRAGMA table_info(files)")
            columns = {row[1]: row for row in cursor.fetchall()}

            self.assertIn("vault_id", columns, "vault_id column not found in files table")
            vault_id_info = columns["vault_id"]
            # PRAGMA table_info returns: (cid, name, type, notnull, dflt_value, pk)
            # notnull = 1 means NOT NULL constraint exists
            # dflt_value = None means no default
            col_notnull = vault_id_info[3]
            col_default = vault_id_info[4]

            self.assertEqual(
                col_notnull,
                1,
                f"files.vault_id must be NOT NULL, but notnull={col_notnull}",
            )
            self.assertIsNone(
                col_default,
                f"files.vault_id must have no default value, but dflt_value={col_default!r}",
            )
        finally:
            conn.close()

    def test_fresh_db_chat_sessions_vault_id_not_null_no_default(self):
        """Fresh DB created from SCHEMA has chat_sessions.vault_id as NOT NULL with no default."""
        conn = sqlite3.connect(":memory:")
        try:
            conn.executescript(SCHEMA)

            # Check chat_sessions.vault_id column definition
            cursor = conn.execute("PRAGMA table_info(chat_sessions)")
            columns = {row[1]: row for row in cursor.fetchall()}

            self.assertIn(
                "vault_id", columns, "vault_id column not found in chat_sessions table"
            )
            vault_id_info = columns["vault_id"]
            col_notnull = vault_id_info[3]
            col_default = vault_id_info[4]

            self.assertEqual(
                col_notnull,
                1,
                f"chat_sessions.vault_id must be NOT NULL, but notnull={col_notnull}",
            )
            self.assertIsNone(
                col_default,
                f"chat_sessions.vault_id must have no default value, but dflt_value={col_default!r}",
            )
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
