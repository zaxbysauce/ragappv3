"""Unit tests for supersession detection in RAGEngine."""

import unittest
from unittest.mock import MagicMock, patch
from typing import List

from app.services.document_retrieval import RAGSource
from app.services.rag_engine import RAGEngine


def make_source(file_id: str) -> RAGSource:
    """Helper to create a RAGSource with a file_id."""
    return RAGSource(
        text=f"content from {file_id}", file_id=file_id, score=0.9, metadata={}
    )


class TestSupersessionDetection(unittest.IsolatedAsyncioTestCase):
    """Test suite for _check_supersession method."""

    @patch("app.services.rag_engine._get_pool")
    async def test_supersession_no_sources(self, mock_get_pool):
        """Empty sources returns None."""
        engine = RAGEngine()
        result = await engine._check_supersession([])
        self.assertIsNone(result)
        mock_get_pool.assert_not_called()

    @patch("app.services.rag_engine._get_pool")
    async def test_supersession_column_missing(self, mock_get_pool):
        """When PRAGMA returns no supersedes_file_id, returns None."""
        # Mock the pool and connection
        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_pool.connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_pool.connection.return_value.__exit__ = MagicMock(return_value=False)
        mock_get_pool.return_value = mock_pool

        # Mock PRAGMA result with NO supersedes_file_id column
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            (0, "id", "TEXT", 0, None, 0),
            (1, "file_name", "TEXT", 0, None, 0),
            (2, "status", "TEXT", 0, None, 0),
        ]
        mock_conn.execute.return_value = mock_cursor

        engine = RAGEngine()
        sources = [make_source("file123")]
        result = await engine._check_supersession(sources)

        self.assertIsNone(result)
        # Verify PRAGMA was called
        mock_conn.execute.assert_called()

    @patch("app.services.rag_engine._get_pool")
    async def test_supersession_no_superseded_files(self, mock_get_pool):
        """Column exists but no matching rows - returns None."""
        # Mock the pool and connection
        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_pool.connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_pool.connection.return_value.__exit__ = MagicMock(return_value=False)
        mock_get_pool.return_value = mock_pool

        # Mock PRAGMA result WITH supersedes_file_id column
        mock_cursor_pragma = MagicMock()
        mock_cursor_pragma.fetchall.return_value = [
            (0, "id", "TEXT", 0, None, 0),
            (1, "file_name", "TEXT", 0, None, 0),
            (2, "supersedes_file_id", "TEXT", 0, None, 0),
            (3, "status", "TEXT", 0, None, 0),
        ]

        # Mock query returning empty results
        mock_cursor_query = MagicMock()
        mock_cursor_query.fetchall.return_value = []

        # First call is PRAGMA, second is the actual query
        mock_conn.execute.side_effect = [mock_cursor_pragma, mock_cursor_query]

        engine = RAGEngine()
        sources = [make_source("file123")]
        result = await engine._check_supersession(sources)

        self.assertIsNone(result)

    @patch("app.services.rag_engine._get_pool")
    async def test_supersession_has_superseded_files(self, mock_get_pool):
        """Returns warning string when files are superseded."""
        # Mock the pool and connection
        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_pool.connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_pool.connection.return_value.__exit__ = MagicMock(return_value=False)
        mock_get_pool.return_value = mock_pool

        # Mock PRAGMA result WITH supersedes_file_id column
        mock_cursor_pragma = MagicMock()
        mock_cursor_pragma.fetchall.return_value = [
            (0, "id", "TEXT", 0, None, 0),
            (1, "file_name", "TEXT", 0, None, 0),
            (2, "supersedes_file_id", "TEXT", 0, None, 0),
            (3, "status", "TEXT", 0, None, 0),
        ]

        # Mock query returning superseded files
        mock_cursor_query = MagicMock()
        mock_cursor_query.fetchall.return_value = [
            ("superseding_document_v2.pdf",),
        ]

        mock_conn.execute.side_effect = [mock_cursor_pragma, mock_cursor_query]

        engine = RAGEngine()
        sources = [make_source("file123")]
        result = await engine._check_supersession(sources)

        self.assertIsNotNone(result)
        self.assertIn("superseded", result.lower())
        self.assertIn("\u26a0\ufe0f", result)  # Warning emoji

    @patch("app.services.rag_engine._get_pool")
    async def test_supersession_db_error(self, mock_get_pool):
        """Exception returns None (suppressed)."""
        # Mock the pool to raise an exception
        mock_pool = MagicMock()
        mock_pool.connection.side_effect = Exception("Database connection failed")
        mock_get_pool.return_value = mock_pool

        engine = RAGEngine()
        sources = [make_source("file123")]
        result = await engine._check_supersession(sources)

        self.assertIsNone(result)

    @patch("app.services.rag_engine._get_pool")
    async def test_supersession_sources_no_file_id(self, mock_get_pool):
        """Sources with empty file_ids returns None."""
        # Create sources without file_id (empty string)
        sources = [
            RAGSource(text="content 1", file_id="", score=0.9, metadata={}),
            RAGSource(text="content 2", file_id="", score=0.8, metadata={}),
        ]

        engine = RAGEngine()
        result = await engine._check_supersession(sources)

        self.assertIsNone(result)
        mock_get_pool.assert_not_called()


if __name__ == "__main__":
    unittest.main()
