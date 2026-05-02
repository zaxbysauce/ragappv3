"""Tests for the chat_messages thinking-content cleanup migration (P4)."""

import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.models.database import (
    init_db,
    migrate_sanitize_existing_chat_messages,
    run_migrations,
)


class TestCleanupMigration(unittest.TestCase):
    def setUp(self) -> None:
        self.fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(self.fd)
        init_db(self.path)
        run_migrations(self.path)

    def tearDown(self) -> None:
        try:
            os.remove(self.path)
        except OSError:
            pass

    def _seed(self, *rows: tuple[str, str]) -> list[int]:
        ids: list[int] = []
        with sqlite3.connect(self.path) as conn:
            conn.execute("INSERT INTO chat_sessions (id, vault_id) VALUES (1, 1)")
            for role, content in rows:
                cursor = conn.execute(
                    "INSERT INTO chat_messages (session_id, role, content) VALUES (?, ?, ?)",
                    (1, role, content),
                )
                ids.append(cursor.lastrowid)
            conn.commit()
        return ids

    def test_cleanup_strips_assistant_thinking_blocks(self):
        ids = self._seed(
            ("user", "<think>NOT user content</think> stays as-is"),
            ("assistant", "<think>secret plan</think>Visible answer."),
            ("assistant", "_lhsfooter_rhsClean answer."),
            ("assistant", "Already clean."),
        )

        migrate_sanitize_existing_chat_messages(self.path)

        with sqlite3.connect(self.path) as conn:
            rows = {
                row[0]: row[1]
                for row in conn.execute(
                    "SELECT id, content FROM chat_messages"
                )
            }
        # User content untouched even when it contains a <think> tag —
        # the migration only sanitizes assistant rows.
        self.assertIn("<think>", rows[ids[0]])
        # Assistant rows scrubbed.
        self.assertEqual(rows[ids[1]], "Visible answer.")
        self.assertEqual(rows[ids[2]], "Clean answer.")
        self.assertEqual(rows[ids[3]], "Already clean.")

    def test_cleanup_idempotent(self):
        self._seed(("assistant", "<think>x</think>final"))
        migrate_sanitize_existing_chat_messages(self.path)
        # Snapshot post-first-pass.
        with sqlite3.connect(self.path) as conn:
            first = [
                row[1]
                for row in conn.execute("SELECT id, content FROM chat_messages")
            ]
        # Second run is a no-op.
        migrate_sanitize_existing_chat_messages(self.path)
        with sqlite3.connect(self.path) as conn:
            second = [
                row[1]
                for row in conn.execute("SELECT id, content FROM chat_messages")
            ]
        self.assertEqual(first, second)

    def test_runs_in_full_migrations_pipeline(self):
        # Exercise the cleanup as part of run_migrations() so we know the
        # sequencing in models.database is correct.
        self._seed(("assistant", "<think>x</think>visible"))
        run_migrations(self.path)
        with sqlite3.connect(self.path) as conn:
            content = conn.execute(
                "SELECT content FROM chat_messages WHERE role = 'assistant'"
            ).fetchone()[0]
        self.assertEqual(content, "visible")


if __name__ == "__main__":
    unittest.main()
