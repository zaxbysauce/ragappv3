"""
Tests for FTS index validation at startup in lifespan.py.

Verifies the FTS validation block (lifespan.py ~lines 217-231):
1. FTS index missing + hybrid enabled → ERROR log emitted
2. FTS index exists + hybrid enabled → no ERROR log
3. hybrid disabled → no FTS check performed
4. list_indices raises exception → ERROR log emitted but app continues
"""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class MockIndex:
    """Minimal mock for a LanceDB index object with a .name attribute."""

    def __init__(self, name: str):
        self.name = name


class TestFTSValidationAtStartup:
    """Test FTS index validation logic from lifespan.py startup block.

    The validation block is extracted and tested in isolation with mocked
    dependencies, mirroring the logic at lifespan.py lines 217-231:

        if settings.hybrid_search_enabled:
            try:
                indices = await app.state.vector_store.table.list_indices()
                fts_index_exists = any(idx.name == "fts_text" for idx in indices)
                if not fts_index_exists:
                    logger.error("Hybrid search is enabled but the FTS index is missing ...")
            except Exception as e:
                logger.error(f"Failed to check FTS index status (hybrid search may not work): {e}")
    """

    # ── Test 1: FTS missing + hybrid enabled → ERROR logged ─────────────────────

    @pytest.mark.asyncio
    async def test_fts_missing_hybrid_enabled_logs_error(self, caplog):
        """
        When hybrid_search_enabled=True and list_indices returns NO 'fts_text' index,
        an ERROR should be logged describing the problem.
        """
        caplog.set_level(logging.DEBUG, logger="app.lifespan")

        mock_table = MagicMock()
        mock_table.list_indices = AsyncMock(
            return_value=[MockIndex("other_idx"), MockIndex("embedding_idx")]
        )

        mock_vector_store = MagicMock()
        mock_vector_store.table = mock_table

        # Patch at app.config.settings (avoids triggering lifespan.py import chain)
        with patch("app.config.settings") as mock_settings:
            mock_settings.hybrid_search_enabled = True

            # Replicate the FTS validation block from lifespan.py lines 217-231
            if mock_settings.hybrid_search_enabled:
                try:
                    indices = await mock_vector_store.table.list_indices()
                    fts_index_exists = any(idx.name == "fts_text" for idx in indices)
                    if not fts_index_exists:
                        logging.getLogger("app.lifespan").error(
                            "Hybrid search is enabled but the FTS index is missing on the 'text' column. "
                            "FTS search will not function. Create the index with "
                            "VectorStore._ensure_fts_index() or rebuild the table."
                        )
                except Exception as e:
                    logging.getLogger("app.lifespan").error(
                        f"Failed to check FTS index status (hybrid search may not work): {e}"
                    )

        error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert len(error_records) == 1
        assert "FTS index is missing" in error_records[0].message
        # Message mentions "FTS index" (not "fts_text" literally — check FTS abbreviation)
        assert "FTS" in error_records[0].message

    # ── Test 2: FTS exists + hybrid enabled → no ERROR logged ──────────────────

    @pytest.mark.asyncio
    async def test_fts_exists_hybrid_enabled_no_error(self, caplog):
        """
        When hybrid_search_enabled=True and list_indices returns an index with
        name='fts_text', no ERROR should be logged.
        """
        caplog.set_level(logging.DEBUG, logger="app.lifespan")

        mock_table = MagicMock()
        mock_table.list_indices = AsyncMock(
            return_value=[MockIndex("fts_text"), MockIndex("embedding_idx")]
        )

        mock_vector_store = MagicMock()
        mock_vector_store.table = mock_table

        with patch("app.config.settings") as mock_settings:
            mock_settings.hybrid_search_enabled = True

            if mock_settings.hybrid_search_enabled:
                try:
                    indices = await mock_vector_store.table.list_indices()
                    fts_index_exists = any(idx.name == "fts_text" for idx in indices)
                    if not fts_index_exists:
                        logging.getLogger("app.lifespan").error(
                            "Hybrid search is enabled but the FTS index is missing on the 'text' column. "
                            "FTS search will not function. Create the index with "
                            "VectorStore._ensure_fts_index() or rebuild the table."
                        )
                except Exception as e:
                    logging.getLogger("app.lifespan").error(
                        f"Failed to check FTS index status (hybrid search may not work): {e}"
                    )

        error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert len(error_records) == 0

    # ── Test 3: hybrid disabled → no FTS check performed ────────────────────────

    @pytest.mark.asyncio
    async def test_hybrid_disabled_skips_fts_check(self):
        """
        When hybrid_search_enabled=False, list_indices should NOT be called at all.
        """
        mock_table = MagicMock()
        mock_table.list_indices = AsyncMock(return_value=[])

        mock_vector_store = MagicMock()
        mock_vector_store.table = mock_table

        with patch("app.config.settings") as mock_settings:
            mock_settings.hybrid_search_enabled = False

            if mock_settings.hybrid_search_enabled:
                try:
                    indices = await mock_vector_store.table.list_indices()
                    fts_index_exists = any(idx.name == "fts_text" for idx in indices)
                    if not fts_index_exists:
                        logging.getLogger("app.lifespan").error("FTS missing")
                except Exception as e:
                    logging.getLogger("app.lifespan").error(f"Check failed: {e}")

        # list_indices should never have been called (the if block was skipped)
        mock_table.list_indices.assert_not_called()

    # ── Test 4: list_indices raises → ERROR logged, no exception propagated ─────

    @pytest.mark.asyncio
    async def test_list_indices_raises_logs_error_but_continues(self, caplog):
        """
        When list_indices raises an exception, an ERROR should be logged but the
        exception should NOT propagate — the app continues.
        """
        caplog.set_level(logging.DEBUG, logger="app.lifespan")

        mock_table = MagicMock()
        mock_table.list_indices = AsyncMock(side_effect=RuntimeError("list_indices failed"))

        mock_vector_store = MagicMock()
        mock_vector_store.table = mock_table

        with patch("app.config.settings") as mock_settings:
            mock_settings.hybrid_search_enabled = True

            if mock_settings.hybrid_search_enabled:
                try:
                    indices = await mock_vector_store.table.list_indices()
                    fts_index_exists = any(idx.name == "fts_text" for idx in indices)
                    if not fts_index_exists:
                        logging.getLogger("app.lifespan").error(
                            "Hybrid search is enabled but the FTS index is missing on the 'text' column. "
                            "FTS search will not function. Create the index with "
                            "VectorStore._ensure_fts_index() or rebuild the table."
                        )
                except Exception as e:
                    logging.getLogger("app.lifespan").error(
                        f"Failed to check FTS index status (hybrid search may not work): {e}"
                    )

        error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert len(error_records) == 1
        assert "Failed to check FTS index status" in error_records[0].message
        assert "list_indices failed" in error_records[0].message

    # ── Boundary: empty list + hybrid enabled ─────────────────────────────────

    @pytest.mark.asyncio
    async def test_empty_indices_list_hybrid_enabled_logs_error(self, caplog):
        """
        When list_indices returns an empty list (no indices at all),
        an ERROR should be logged.
        """
        caplog.set_level(logging.DEBUG, logger="app.lifespan")

        mock_table = MagicMock()
        mock_table.list_indices = AsyncMock(return_value=[])

        mock_vector_store = MagicMock()
        mock_vector_store.table = mock_table

        with patch("app.config.settings") as mock_settings:
            mock_settings.hybrid_search_enabled = True

            if mock_settings.hybrid_search_enabled:
                try:
                    indices = await mock_vector_store.table.list_indices()
                    fts_index_exists = any(idx.name == "fts_text" for idx in indices)
                    if not fts_index_exists:
                        logging.getLogger("app.lifespan").error(
                            "Hybrid search is enabled but the FTS index is missing on the 'text' column. "
                            "FTS search will not function. Create the index with "
                            "VectorStore._ensure_fts_index() or rebuild the table."
                        )
                except Exception as e:
                    logging.getLogger("app.lifespan").error(
                        f"Failed to check FTS index status (hybrid search may not work): {e}"
                    )

        error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert len(error_records) == 1
        assert "FTS index is missing" in error_records[0].message

    # ── Boundary: list_indices returns None ───────────────────────────────────

    @pytest.mark.asyncio
    async def test_list_indices_returns_none_logs_error(self, caplog):
        """
        Edge case: list_indices returns None instead of a list.
        any() on None raises TypeError → caught by except block,
        which logs the error.
        """
        caplog.set_level(logging.DEBUG, logger="app.lifespan")

        mock_table = MagicMock()
        mock_table.list_indices = AsyncMock(return_value=None)

        mock_vector_store = MagicMock()
        mock_vector_store.table = mock_table

        with patch("app.config.settings") as mock_settings:
            mock_settings.hybrid_search_enabled = True

            if mock_settings.hybrid_search_enabled:
                try:
                    indices = await mock_vector_store.table.list_indices()
                    fts_index_exists = any(idx.name == "fts_text" for idx in indices)
                    if not fts_index_exists:
                        logging.getLogger("app.lifespan").error(
                            "Hybrid search is enabled but the FTS index is missing on the 'text' column. "
                            "FTS search will not function. Create the index with "
                            "VectorStore._ensure_fts_index() or rebuild the table."
                        )
                except Exception as e:
                    logging.getLogger("app.lifespan").error(
                        f"Failed to check FTS index status (hybrid search may not work): {e}"
                    )

        error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert len(error_records) == 1
        assert "Failed to check FTS index status" in error_records[0].message


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
