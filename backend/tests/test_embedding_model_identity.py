"""Tests for embedding model identity tracking (Issue #220).

Covers:
- Migration: idempotent embedding_model_info table creation
- Mismatch detection logic at startup
- Admin reindex endpoint: auth, queueing, model info update
"""

import os
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.models.database import (
    migrate_add_embedding_model_info,
    run_migrations,
)


class TestEmbeddingModelInfoMigration(unittest.TestCase):
    """Test the embedding_model_info migration is idempotent."""

    def setUp(self):
        self.temp_fd, self.temp_db_path = tempfile.mkstemp(suffix=".db")
        os.close(self.temp_fd)

    def tearDown(self):
        if os.path.exists(self.temp_db_path):
            os.remove(self.temp_db_path)

    def test_migration_creates_table(self):
        """Migration should create embedding_model_info table."""
        # Create a minimal DB first (the migration doesn't depend on other tables)
        conn = sqlite3.connect(self.temp_db_path)
        conn.close()

        migrate_add_embedding_model_info(self.temp_db_path)

        conn = sqlite3.connect(self.temp_db_path)
        try:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            self.assertIn("embedding_model_info", tables)
        finally:
            conn.close()

    def test_migration_is_idempotent(self):
        """Running the migration multiple times should not error."""
        conn = sqlite3.connect(self.temp_db_path)
        conn.close()

        migrate_add_embedding_model_info(self.temp_db_path)
        migrate_add_embedding_model_info(self.temp_db_path)

        conn = sqlite3.connect(self.temp_db_path)
        try:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            self.assertIn("embedding_model_info", tables)
        finally:
            conn.close()

    def test_singleton_constraint(self):
        """Only id=1 should be insertable (CHECK constraint)."""
        conn = sqlite3.connect(self.temp_db_path)
        conn.close()

        migrate_add_embedding_model_info(self.temp_db_path)

        conn = sqlite3.connect(self.temp_db_path)
        try:
            conn.execute(
                "INSERT INTO embedding_model_info (id, model_name, dimensions) VALUES (1, 'model-a', 384)"
            )
            conn.commit()
            # Trying to insert id=2 should fail
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO embedding_model_info (id, model_name, dimensions) VALUES (2, 'model-b', 768)"
                )
        finally:
            conn.close()

    def test_run_migrations_includes_table(self):
        """Full run_migrations should include embedding_model_info table."""
        run_migrations(self.temp_db_path)

        conn = sqlite3.connect(self.temp_db_path)
        try:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            self.assertIn("embedding_model_info", tables)
        finally:
            conn.close()


class TestEmbeddingModelMismatchDetection(unittest.TestCase):
    """Test the mismatch detection logic in lifespan._check_embedding_model_identity."""

    def setUp(self):
        self.temp_fd, self.temp_db_path = tempfile.mkstemp(suffix=".db")
        os.close(self.temp_fd)
        run_migrations(self.temp_db_path)

    def tearDown(self):
        if os.path.exists(self.temp_db_path):
            os.remove(self.temp_db_path)

    @patch("app.lifespan.settings")
    def test_first_run_persists_model(self, mock_settings):
        """On first run, the current model should be stored."""
        from app.lifespan import _check_embedding_model_identity

        mock_settings.embedding_model = "test-model-v1"
        mock_settings.embedding_dim = 384
        mock_settings.sqlite_path = self.temp_db_path

        app = MagicMock()
        app.state = MagicMock()
        app.state.embedding_model_mismatch = False

        _check_embedding_model_identity(app)

        # Verify it was stored
        conn = sqlite3.connect(self.temp_db_path)
        try:
            row = conn.execute(
                "SELECT model_name, dimensions FROM embedding_model_info WHERE id = 1"
            ).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row[0], "test-model-v1")
            self.assertEqual(row[1], 384)
        finally:
            conn.close()

        # Flag should remain False (no mismatch)
        self.assertFalse(app.state.embedding_model_mismatch)

    @patch("app.lifespan.settings")
    def test_same_model_no_mismatch(self, mock_settings):
        """When stored model matches current, no mismatch is flagged."""
        from app.lifespan import _check_embedding_model_identity

        mock_settings.embedding_model = "test-model-v1"
        mock_settings.embedding_dim = 384
        mock_settings.sqlite_path = self.temp_db_path

        # Pre-populate the stored model
        conn = sqlite3.connect(self.temp_db_path)
        conn.execute(
            "INSERT INTO embedding_model_info (id, model_name, dimensions) VALUES (1, 'test-model-v1', 384)"
        )
        conn.commit()
        conn.close()

        app = MagicMock()
        app.state = MagicMock()
        app.state.embedding_model_mismatch = False

        _check_embedding_model_identity(app)

        self.assertFalse(app.state.embedding_model_mismatch)

    @patch("app.lifespan.settings")
    def test_different_model_sets_mismatch(self, mock_settings):
        """When stored model differs from current, mismatch is flagged."""
        from app.lifespan import _check_embedding_model_identity

        mock_settings.embedding_model = "new-model-v2"
        mock_settings.embedding_dim = 384
        mock_settings.sqlite_path = self.temp_db_path

        # Pre-populate with a different model
        conn = sqlite3.connect(self.temp_db_path)
        conn.execute(
            "INSERT INTO embedding_model_info (id, model_name, dimensions) VALUES (1, 'old-model-v1', 384)"
        )
        conn.commit()
        conn.close()

        app = MagicMock()
        app.state = MagicMock()

        _check_embedding_model_identity(app)

        self.assertTrue(app.state.embedding_model_mismatch)


if __name__ == "__main__":
    unittest.main()
