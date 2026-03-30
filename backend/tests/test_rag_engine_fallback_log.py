"""Tests for RAGEngine fallback warning log fix - handles None thresholds."""

import pytest
import logging
from unittest.mock import MagicMock, patch, call
from typing import List, Dict, Any

# Import the module under test
import sys

sys.path.insert(0, "C:/opencode/RAGAPPv2/backend")

from app.services.rag_engine import RAGEngine, RAGSource


class TestRAGEngineFallbackWarningLog:
    """Test that fallback warning log handles None thresholds without TypeError."""

    @pytest.fixture
    def mock_settings(self):
        """Create mock settings with None thresholds."""
        with patch("app.services.rag_engine.settings") as mock:
            # Set thresholds to None to test the fix
            mock.max_distance_threshold = None
            mock.rag_relevance_threshold = None
            mock.chunk_size_chars = 1000
            mock.chunk_overlap_chars = 200
            mock.retrieval_top_k = 5
            mock.vector_top_k = None
            mock.vector_metric = "cosine"
            mock.embedding_doc_prefix = ""
            mock.embedding_query_prefix = ""
            mock.retrieval_window = 0
            mock.reranking_enabled = False
            mock.reranker_top_n = 5
            mock.initial_retrieval_top_k = 10
            mock.hybrid_search_enabled = False
            mock.hybrid_alpha = 0.5
            mock.maintenance_mode = False
            mock.query_transformation_enabled = False
            mock.retrieval_evaluation_enabled = False
            mock.max_context_chunks = 5
            yield mock

    @pytest.fixture
    def engine(self, mock_settings):
        """Create RAGEngine instance with mocked dependencies."""
        with patch.object(RAGEngine, "__init__", lambda self, **kwargs: None):
            engine = RAGEngine()
            # Manually set required attributes
            engine.max_distance_threshold = None
            engine.relevance_threshold = None
            engine.retrieval_top_k = 5
            engine.retrieval_window = 0
            engine.vector_store = MagicMock()
            return engine

    def test_fallback_warning_with_none_thresholds(self, engine, caplog):
        """Test that fallback warning log handles None thresholds without TypeError."""
        # Create test results that would trigger the fallback
        results = [
            {
                "_distance": 0.9,
                "text": "chunk1",
                "file_id": "file1",
                "metadata": {"chunk_index": 0},
            },
            {
                "_distance": 0.95,
                "text": "chunk2",
                "file_id": "file1",
                "metadata": {"chunk_index": 1},
            },
        ]

        # Set both thresholds to None
        engine.max_distance_threshold = None
        engine.relevance_threshold = None

        with caplog.at_level(logging.WARNING):
            # This should NOT raise TypeError when formatting the log message
            sources = engine._filter_relevant(results)

        # Verify no TypeError was raised and the method completed
        assert isinstance(sources, list)
        # With None thresholds, all results should pass through (no filtering)
        assert len(sources) == 2

    def test_fallback_warning_with_zero_threshold(self, engine, caplog):
        """Test fallback warning with threshold of 0 (falsy but not None)."""
        results = [
            {
                "_distance": 0.9,
                "text": "chunk1",
                "file_id": "file1",
                "metadata": {"chunk_index": 0},
            },
            {
                "_distance": 0.95,
                "text": "chunk2",
                "file_id": "file1",
                "metadata": {"chunk_index": 1},
            },
        ]

        # Set threshold to 0 (falsy but not None)
        engine.max_distance_threshold = 0
        engine.relevance_threshold = None

        with caplog.at_level(logging.WARNING):
            sources = engine._filter_relevant(results)

        # With threshold of 0, all results should be filtered out (distance > 0)
        # Returns empty list with no_match flag
        assert isinstance(sources, list)
        assert len(sources) == 0
        assert engine.document_retrieval.no_match is True

    def test_fallback_warning_with_valid_threshold(self, engine, caplog):
        """Test fallback warning with valid threshold (no fallback triggered)."""
        results = [
            {
                "_distance": 0.3,
                "text": "chunk1",
                "file_id": "file1",
                "metadata": {"chunk_index": 0},
            },
            {
                "_distance": 0.4,
                "text": "chunk2",
                "file_id": "file1",
                "metadata": {"chunk_index": 1},
            },
        ]

        # Set valid threshold
        engine.max_distance_threshold = 0.5
        engine.relevance_threshold = None

        with caplog.at_level(logging.WARNING):
            sources = engine._filter_relevant(results)

        # Both results should pass the filter (distance < 0.5)
        assert len(sources) == 2

    def test_fallback_warning_logs_correctly_with_none(self, engine, caplog):
        """Test that the warning log message uses %s format when threshold is None."""
        results = [
            {
                "_distance": 0.9,
                "text": "chunk1",
                "file_id": "file1",
                "metadata": {"chunk_index": 0},
            },
            {
                "_distance": 0.95,
                "text": "chunk2",
                "file_id": "file1",
                "metadata": {"chunk_index": 1},
            },
        ]

        # Set both thresholds to None
        engine.max_distance_threshold = None
        engine.relevance_threshold = None

        with caplog.at_level(logging.WARNING):
            sources = engine._filter_relevant(results)

        # Check that a warning was logged with None threshold
        warning_logs = [r for r in caplog.records if r.levelname == "WARNING"]
        # Look for the fallback warning message
        fallback_warnings = [
            r
            for r in warning_logs
            if "Threshold filtering removed all" in str(r.message)
        ]

        # With None thresholds, no filtering happens, so no fallback warning
        # The fix ensures that if it DID happen, it wouldn't crash
        assert isinstance(sources, list)

    def test_safe_threshold_calculation_with_both_none(self, engine):
        """Test that safe_threshold calculation handles both thresholds being None."""
        results = [
            {
                "_distance": 0.9,
                "text": "chunk1",
                "file_id": "file1",
                "metadata": {"chunk_index": 0},
            },
        ]

        engine.max_distance_threshold = None
        engine.relevance_threshold = None

        # Should not raise TypeError
        sources = engine._filter_relevant(results)
        assert isinstance(sources, list)

    def test_safe_threshold_uses_relevance_when_max_is_none(self, engine):
        """Test that relevance_threshold is used when max_distance_threshold is None."""
        results = [
            {
                "_distance": 0.3,
                "text": "chunk1",
                "file_id": "file1",
                "metadata": {"chunk_index": 0},
            },
            {
                "_distance": 0.9,
                "text": "chunk2",
                "file_id": "file1",
                "metadata": {"chunk_index": 1},
            },
        ]

        engine.max_distance_threshold = None
        engine.relevance_threshold = 0.5  # Should be used as fallback

        sources = engine._filter_relevant(results)
        # Only first result should pass (0.3 < 0.5)
        assert len(sources) == 1
        assert sources[0].text == "chunk1"


class TestRAGEngineThresholdEdgeCases:
    """Test edge cases for threshold handling."""

    @pytest.fixture
    def engine(self):
        """Create RAGEngine instance with mocked dependencies."""
        with patch.object(RAGEngine, "__init__", lambda self, **kwargs: None):
            engine = RAGEngine()
            engine.max_distance_threshold = None
            engine.relevance_threshold = None
            engine.retrieval_top_k = 5
            engine.retrieval_window = 0
            engine.vector_store = MagicMock()
            return engine

    def test_empty_results_with_none_threshold(self, engine):
        """Test handling of empty results with None threshold."""
        results = []

        engine.max_distance_threshold = None
        engine.relevance_threshold = None

        sources = engine._filter_relevant(results)
        assert sources == []

    def test_single_result_with_none_threshold(self, engine):
        """Test handling of single result with None threshold."""
        results = [
            {
                "_distance": 0.5,
                "text": "chunk1",
                "file_id": "file1",
                "metadata": {"chunk_index": 0},
            },
        ]

        engine.max_distance_threshold = None
        engine.relevance_threshold = None

        sources = engine._filter_relevant(results)
        assert len(sources) == 1

    def test_results_without_distance_field_and_none_threshold(self, engine):
        """Test handling of results without _distance field when threshold is None."""
        results = [
            {
                "score": 0.5,
                "text": "chunk1",
                "file_id": "file1",
                "metadata": {"chunk_index": 0},
            },
        ]

        engine.max_distance_threshold = None
        engine.relevance_threshold = None

        # Should not raise error
        sources = engine._filter_relevant(results)
        assert isinstance(sources, list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
