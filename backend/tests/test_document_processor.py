"""Unit tests for DocumentProcessor using SQL file path."""

import asyncio
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Stub missing optional dependencies
try:
    import lancedb
except ImportError:
    import types
    sys.modules['lancedb'] = types.ModuleType('lancedb')

try:
    import pyarrow
except ImportError:
    import types
    sys.modules['pyarrow'] = types.ModuleType('pyarrow')

try:
    from unstructured.partition.auto import partition
except ImportError:
    import types
    _unstructured = types.ModuleType('unstructured')
    _unstructured.__path__ = []
    _unstructured.partition = types.ModuleType('unstructured.partition')
    _unstructured.partition.__path__ = []
    _unstructured.partition.auto = types.ModuleType('unstructured.partition.auto')
    _unstructured.partition.auto.partition = lambda *args, **kwargs: []
    _unstructured.chunking = types.ModuleType('unstructured.chunking')
    _unstructured.chunking.__path__ = []
    _unstructured.chunking.title = types.ModuleType('unstructured.chunking.title')
    _unstructured.chunking.title.chunk_by_title = lambda *args, **kwargs: []
    _unstructured.documents = types.ModuleType('unstructured.documents')
    _unstructured.documents.__path__ = []
    _unstructured.documents.elements = types.ModuleType('unstructured.documents.elements')
    _unstructured.documents.elements.Element = type('Element', (), {})
    sys.modules['unstructured'] = _unstructured
    sys.modules['unstructured.partition'] = _unstructured.partition
    sys.modules['unstructured.partition.auto'] = _unstructured.partition.auto
    sys.modules['unstructured.chunking'] = _unstructured.chunking
    sys.modules['unstructured.chunking.title'] = _unstructured.chunking.title
    sys.modules['unstructured.documents'] = _unstructured.documents
    sys.modules['unstructured.documents.elements'] = _unstructured.documents.elements

from app.models.database import init_db, SQLiteConnectionPool
from app.services.document_processor import (
    DocumentProcessor,
    DuplicateFileError,
    ProcessedDocument
)
from app.config import settings


class TestDocumentProcessor(unittest.TestCase):
    """Test cases for DocumentProcessor with SQL file processing."""

    def setUp(self):
        """Create temporary database and SQL file for each test."""
        # Create temp directory for all test files
        self.temp_dir = tempfile.mkdtemp()

        # Create temp sqlite file
        self.temp_db_path = os.path.join(self.temp_dir, 'test.db')

        # Initialize the database
        init_db(self.temp_db_path)

        # Create temp .sql file with CREATE TABLE statement
        self.sql_file_path = os.path.join(self.temp_dir, 'test_schema.sql')
        sql_content = """
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    content TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
"""
        with open(self.sql_file_path, 'w', encoding='utf-8') as f:
            f.write(sql_content)

        # Monkeypatch settings.data_dir so sqlite_path resolves to temp path
        self._original_data_dir = settings.data_dir
        settings.data_dir = Path(self.temp_dir)

        # Create test pool
        self.test_pool = SQLiteConnectionPool(self.temp_db_path, max_size=2)

        # Create DocumentProcessor instance with pool
        self.processor = DocumentProcessor(chunk_size_chars=2000, chunk_overlap_chars=200, pool=self.test_pool)

    def tearDown(self):
        """Clean up temporary files."""
        settings.data_dir = self._original_data_dir

        # Close test pool
        self.test_pool.close_all()

        # Remove temp files
        if os.path.exists(self.sql_file_path):
            os.remove(self.sql_file_path)
        if os.path.exists(self.temp_db_path):
            os.remove(self.temp_db_path)
        if os.path.exists(self.temp_dir):
            os.rmdir(self.temp_dir)

    def test_process_file_returns_valid_result(self):
        """Test that process_file returns valid ProcessedDocument with SQL file."""
        # Process the SQL file
        result = asyncio.run(self.processor.process_file(self.sql_file_path))

        # Assert result is ProcessedDocument
        self.assertIsInstance(result, ProcessedDocument)

        # Assert file_id is int
        self.assertIsInstance(result.file_id, int)
        self.assertGreater(result.file_id, 0)

        # Assert chunks list is not empty
        self.assertIsInstance(result.chunks, list)
        self.assertGreater(len(result.chunks), 0)

    def test_process_file_updates_db_status(self):
        """Test that process_file updates DB status to indexed with chunk_count."""
        # Process the SQL file
        result = asyncio.run(self.processor.process_file(self.sql_file_path))

        # Query database to verify status
        conn = sqlite3.connect(self.temp_db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "SELECT status, chunk_count FROM files WHERE id = ?",
            (result.file_id,)
        )
        row = cursor.fetchone()
        conn.close()

        # Assert status is 'indexed'
        self.assertIsNotNone(row)
        self.assertEqual(row['status'], 'indexed')

        # Assert chunk_count matches number of chunks
        self.assertEqual(row['chunk_count'], len(result.chunks))

    def test_process_file_raises_duplicate_error_on_second_call(self):
        """Test that second call with same file raises DuplicateFileError."""
        # Process the SQL file first time
        asyncio.run(self.processor.process_file(self.sql_file_path))

        # Second call should raise DuplicateFileError
        with self.assertRaises(DuplicateFileError):
            asyncio.run(self.processor.process_file(self.sql_file_path))

    def test_process_file_extracts_correct_chunks(self):
        """Test that SQL file is correctly parsed into chunks."""
        # Process the SQL file
        result = asyncio.run(self.processor.process_file(self.sql_file_path))

        # Should have 2 chunks (users table and posts table)
        self.assertEqual(len(result.chunks), 2)

        # Verify chunk content contains expected table names
        chunk_texts = [chunk.text for chunk in result.chunks]
        self.assertTrue(
            any('users' in text for text in chunk_texts),
            "Expected one chunk to contain 'users' table"
        )
        self.assertTrue(
            any('posts' in text for text in chunk_texts),
            "Expected one chunk to contain 'posts' table"
        )


class TestSpreadsheetAdaptiveChunking(unittest.TestCase):
    """Test cases for adaptive spreadsheet chunking."""

    def setUp(self):
        """Create temporary directory for test files."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temp files."""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_wide_spreadsheet_chunks_respect_max_size(self):
        """
        Test that wide spreadsheets (100+ columns) produce chunks
        under the 8192 char embedding limit.
        """
        try:
            import pandas as pd
        except ImportError:
            self.skipTest("pandas not available")

        # Create a wide spreadsheet: 100 columns × 50 rows
        # Each cell has ~20 chars, so estimated chunk size would be huge
        # without adaptive chunking
        num_cols = 100
        num_rows = 50
        data = {
            f"col_{i}": [f"value_{i}_{j}" for j in range(num_rows)]
            for i in range(num_cols)
        }
        df = pd.DataFrame(data)

        csv_path = os.path.join(self.temp_dir, "wide_sheet.csv")
        df.to_csv(csv_path, index=False)

        from app.services.document_processor import SpreadsheetParser
        parser = SpreadsheetParser()
        chunks = parser.parse(csv_path)

        # Verify chunks were produced
        self.assertGreater(len(chunks), 0, "Expected at least one chunk")

        # Verify all chunks are under the max size
        max_chunk_chars = parser.MAX_CHUNK_CHARS
        for i, chunk in enumerate(chunks):
            chunk_size = len(chunk["text"])
            self.assertLessEqual(
                chunk_size,
                max_chunk_chars,
                f"Chunk {i} exceeds max size: {chunk_size} > {max_chunk_chars}",
            )

        # Verify adaptive chunking reduced row count from 50
        # (With 100 columns, 50 rows would be ~20000+ chars)
        # If chunks respect max, row count must have been reduced
        total_rows = sum(
            chunk["metadata"]["row_end"] - chunk["metadata"]["row_start"] + 1
            for chunk in chunks
        )
        self.assertEqual(
            total_rows,
            num_rows,
            f"Expected {num_rows} total rows across chunks, got {total_rows}",
        )

    def test_narrow_spreadsheet_uses_default_rows_per_chunk(self):
        """
        Test that narrow spreadsheets (few columns) still use the default
        ROWS_PER_CHUNK value for efficiency.
        """
        try:
            import pandas as pd
        except ImportError:
            self.skipTest("pandas not available")

        # Create a narrow spreadsheet: 5 columns × 100 rows
        # This should fit many rows per chunk
        num_cols = 5
        num_rows = 100
        data = {
            f"col_{i}": [f"val_{i}_{j}" for j in range(num_rows)]
            for i in range(num_cols)
        }
        df = pd.DataFrame(data)

        csv_path = os.path.join(self.temp_dir, "narrow_sheet.csv")
        df.to_csv(csv_path, index=False)

        from app.services.document_processor import SpreadsheetParser
        parser = SpreadsheetParser()
        chunks = parser.parse(csv_path)

        # Verify chunks were produced
        self.assertGreater(len(chunks), 0, "Expected at least one chunk")

        # With narrow columns, should have fewer chunks (more rows per chunk)
        # 100 rows / 50 rows_per_chunk = 2 chunks (approximately)
        # Due to header overhead and filtering, might be 2-3 chunks
        self.assertLessEqual(
            len(chunks),
            3,
            f"Narrow spreadsheet should have ~2 chunks, got {len(chunks)}",
        )

        # Verify all chunks respect max size
        for i, chunk in enumerate(chunks):
            chunk_size = len(chunk["text"])
            self.assertLessEqual(
                chunk_size,
                parser.MAX_CHUNK_CHARS,
                f"Chunk {i} exceeds max size: {chunk_size}",
            )

    def test_single_row_with_long_cell_values_no_data_loss(self):
        """
        Test that a single row with extremely long cell values is split
        into multiple column-group chunks without data loss.
        """
        try:
            import pandas as pd
        except ImportError:
            self.skipTest("pandas not available")

        # Create a spreadsheet with 1 row and 10 columns, each with a 1000-char value
        # Total row would be ~15,000 chars (exceeds 8192)
        num_cols = 10
        long_val = "x" * 1000
        data = {f"col_{i}": [long_val] for i in range(num_cols)}
        df = pd.DataFrame(data)

        csv_path = os.path.join(self.temp_dir, "long_cells.csv")
        df.to_csv(csv_path, index=False)

        from app.services.document_processor import SpreadsheetParser
        parser = SpreadsheetParser()
        chunks = parser.parse(csv_path)

        # Should produce multiple column-group chunks
        self.assertGreater(
            len(chunks),
            1,
            "Long cell values should trigger column-group splitting",
        )

        # Verify all chunks respect max size
        for i, chunk in enumerate(chunks):
            chunk_size = len(chunk["text"])
            self.assertLessEqual(
                chunk_size,
                parser.MAX_CHUNK_CHARS,
                f"Chunk {i} exceeds max size: {chunk_size}",
            )

        # Verify no data loss: all column names should appear in at least one chunk
        all_chunk_text = " ".join(chunk["text"] for chunk in chunks)
        for col_idx in range(num_cols):
            col_name = f"col_{col_idx}"
            self.assertIn(
                col_name,
                all_chunk_text,
                f"Column '{col_name}' missing from all chunks",
            )

        # Verify column-group metadata is present (proves column splitting happened)
        col_group_chunks = [c for c in chunks if c["metadata"].get("col_group") is not None]
        self.assertGreaterEqual(
            len(col_group_chunks),
            1,
            "Column-group chunks not found; splitting may not have occurred",
        )

    def test_mixed_row_sizes_with_column_splitting(self):
        """
        Test a spreadsheet where some rows are normal and one row is very wide,
        triggering column splitting only for the wide row.
        """
        try:
            import pandas as pd
        except ImportError:
            self.skipTest("pandas not available")

        # Create a spreadsheet:
        # - Row 0: 50 columns with short values (fits in one chunk)
        # - Row 1: 50 columns with 500-char values each (will trigger column splitting)
        # - Row 2: 50 columns with short values (fits in one chunk)
        num_cols = 50
        short_val = "s"
        long_val = "x" * 500

        data = {
            f"col_{i}": [short_val, long_val, short_val] for i in range(num_cols)
        }
        df = pd.DataFrame(data)

        csv_path = os.path.join(self.temp_dir, "mixed_rows.csv")
        df.to_csv(csv_path, index=False)

        from app.services.document_processor import SpreadsheetParser
        parser = SpreadsheetParser()
        chunks = parser.parse(csv_path)

        # Should produce multiple chunks due to row 1 column splitting
        self.assertGreater(len(chunks), 1, "Expected multiple chunks due to column splitting")

        # Verify all chunks respect max size
        for i, chunk in enumerate(chunks):
            chunk_size = len(chunk["text"])
            self.assertLessEqual(
                chunk_size,
                parser.MAX_CHUNK_CHARS,
                f"Chunk {i} exceeds max size: {chunk_size}",
            )

    def test_non_uniform_column_sizes_triggers_validation(self):
        """
        Test that non-uniform column sizes (some moderate, some huge) correctly
        trigger the validation check that prevents oversized columns from being
        flushed as single-column chunks.

        This test specifically catches the bug where a column that fits alone
        (1035 chars) is followed by one that exceeds alone (8193 chars).
        """
        try:
            import pandas as pd
        except ImportError:
            self.skipTest("pandas not available")

        # Create a row with:
        # - col_0 to col_4: moderate values that fit together
        # - col_5: huge value that exceeds 8192 when rendered alone
        data = {
            "col_0": ["moderate_0" * 50],  # ~500 chars
            "col_1": ["moderate_1" * 50],  # ~500 chars
            "col_2": ["moderate_2" * 50],  # ~500 chars
            "col_3": ["moderate_3" * 50],  # ~500 chars
            "col_4": ["moderate_4" * 50],  # ~500 chars
            "col_5": ["huge" * 2500],  # ~10,000 chars (exceeds 8192 alone)
        }
        df = pd.DataFrame(data)

        csv_path = os.path.join(self.temp_dir, "non_uniform_cols.csv")
        df.to_csv(csv_path, index=False)

        from app.services.document_processor import SpreadsheetParser
        parser = SpreadsheetParser()
        chunks = parser.parse(csv_path)

        # Should produce multiple chunks (normal cols + split huge col)
        self.assertGreater(len(chunks), 1, "Expected multiple chunks")

        # Verify ALL chunks respect max size (the critical check)
        for i, chunk in enumerate(chunks):
            chunk_size = len(chunk["text"])
            self.assertLessEqual(
                chunk_size,
                parser.MAX_CHUNK_CHARS,
                f"Chunk {i} EXCEEDS max size: {chunk_size} > {parser.MAX_CHUNK_CHARS}. "
                f"This indicates the validation check failed.",
            )

        # Verify column data is present (no complete loss)
        all_text = " ".join(c["text"] for c in chunks)
        self.assertIn("col_0", all_text, "col_0 missing")
        self.assertIn("col_5", all_text, "col_5 missing")
        self.assertIn("huge", all_text, "col_5 value data missing — may have been dropped instead of truncated")

    def test_single_column_overflow_truncation(self):
        """
        Test that a single column with a value exceeding MAX_CHUNK_CHARS is
        truncated rather than dropped. Exercises lines 224-244 (the truncation
        path). Requires a value >= 8156 chars to trigger it.
        """
        try:
            import pandas as pd
        except ImportError:
            self.skipTest("pandas not available")

        long_val = "overflow" * 1125  # 9000 chars, exceeds 8192 alone
        data = {"col_overflow": [long_val]}
        df = pd.DataFrame(data)

        csv_path = os.path.join(self.temp_dir, "single_col_overflow.csv")
        df.to_csv(csv_path, index=False)

        from app.services.document_processor import SpreadsheetParser
        parser = SpreadsheetParser()
        chunks = parser.parse(csv_path)

        self.assertEqual(len(chunks), 1, "Expected exactly 1 chunk for single-column overflow")

        chunk = chunks[0]
        self.assertLessEqual(
            len(chunk["text"]),
            parser.MAX_CHUNK_CHARS,
            f"Chunk size {len(chunk['text'])} exceeds MAX_CHUNK_CHARS {parser.MAX_CHUNK_CHARS}",
        )
        self.assertIn("col_overflow", chunk["text"], "Column name missing from truncated chunk")
        self.assertIn("overflow", chunk["text"], "Cell data missing — value may have been dropped instead of truncated")
        self.assertIsNotNone(
            chunk["metadata"].get("col_group"),
            "col_group metadata missing — column-split path was not taken",
        )


if __name__ == '__main__':
    unittest.main()
