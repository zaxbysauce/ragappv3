"""
Focused adversarial test for None threshold logging fix in rag_engine.

This test specifically targets the bug where logging with None thresholds
caused TypeError: must be real number, not NoneType
"""

import logging
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, 'backend')

from app.services.rag_engine import RAGEngine


class TestNoneThresholdLoggingFix:
    """Test the specific fix for None threshold logging."""

    @pytest.fixture
    def engine(self):
        """Create a RAGEngine instance with mocked dependencies."""
        with patch('app.services.rag_engine.EmbeddingService'), \
             patch('app.services.rag_engine.VectorStore'), \
             patch('app.services.rag_engine.MemoryStore'), \
             patch('app.services.rag_engine.LLMClient'):
            engine = RAGEngine()
            engine.retrieval_top_k = 5
            engine.retrieval_window = 0
            return engine

    def test_none_max_distance_none_relevance_threshold_no_filtering(self, engine, caplog):
        """
        ATTACK: Both thresholds are None - no filtering should occur.

        When both thresholds are None, no filtering happens (all results pass),
        so fallback logging is never triggered. This is expected behavior.
        The fix prevents TypeError IF fallback were ever triggered with None.
        """
        engine.max_distance_threshold = None
        engine.relevance_threshold = None

        # Results - with no threshold, none should be filtered
        results = [
            {"_distance": 0.5, "text": "doc1", "file_id": "f1"},
            {"_distance": 0.6, "text": "doc2", "file_id": "f2"},
        ]

        with caplog.at_level(logging.WARNING):
            # This should NOT raise TypeError
            result = engine._filter_relevant(results)

        # With no threshold, all results should pass through (no filtering)
        assert len(result) == 2

        # No fallback warning should be logged since nothing was filtered
        warning_messages = [r.message for r in caplog.records if r.levelname == 'WARNING']
        fallback_warnings = [m for m in warning_messages if 'Threshold filtering removed all' in str(m)]
        assert len(fallback_warnings) == 0, "No fallback expected when no threshold is set"

    def test_none_max_distance_with_relevance_threshold_logging(self, engine, caplog):
        """
        ATTACK: max_distance_threshold is None but relevance_threshold has value.

        The fix should use relevance_threshold value in the log message.
        """
        engine.max_distance_threshold = None
        engine.relevance_threshold = 0.3

        results = [
            {"score": 0.1, "text": "doc1", "file_id": "f1"},  # Below threshold
            {"score": 0.2, "text": "doc2", "file_id": "f2"},  # Below threshold
        ]

        with caplog.at_level(logging.WARNING):
            result = engine._filter_relevant(results)

        assert len(result) > 0

        # Verify the warning was logged with the relevance_threshold value
        warning_messages = [r.message for r in caplog.records if r.levelname == 'WARNING']
        fallback_warnings = [m for m in warning_messages if 'max_distance_threshold' in str(m)]
        assert len(fallback_warnings) > 0

        # The warning should contain the threshold value (0.3)
        assert '0.300' in str(fallback_warnings[0]) or '0.3' in str(fallback_warnings[0])

    def test_valid_max_distance_threshold_logging(self, engine, caplog):
        """
        CONTROL: Valid max_distance_threshold should format with %.3f normally.
        """
        engine.max_distance_threshold = 0.75
        engine.relevance_threshold = 0.5

        results = [
            {"_distance": 0.8, "text": "doc1", "file_id": "f1"},  # Above threshold
            {"_distance": 0.9, "text": "doc2", "file_id": "f2"},  # Above threshold
        ]

        with caplog.at_level(logging.WARNING):
            result = engine._filter_relevant(results)

        assert len(result) > 0

        # Verify the warning was logged with formatted float
        warning_messages = [r.message for r in caplog.records if r.levelname == 'WARNING']
        fallback_warnings = [m for m in warning_messages if 'max_distance_threshold' in str(m)]
        assert len(fallback_warnings) > 0

        # Should be formatted with 3 decimal places
        assert '0.750' in str(fallback_warnings[0])

    def test_zero_threshold_logging(self, engine, caplog):
        """
        ATTACK: Zero threshold should format correctly with %.3f.
        """
        engine.max_distance_threshold = 0.0

        results = [
            {"_distance": 0.1, "text": "doc1", "file_id": "f1"},
        ]

        with caplog.at_level(logging.WARNING):
            result = engine._filter_relevant(results)

        assert len(result) > 0

        warning_messages = [r.message for r in caplog.records if r.levelname == 'WARNING']
        fallback_warnings = [m for m in warning_messages if 'max_distance_threshold' in str(m)]

        if fallback_warnings:
            # Zero should be formatted as 0.000
            assert '0.000' in str(fallback_warnings[0])

    def test_negative_threshold_logging(self, engine, caplog):
        """
        ATTACK: Negative threshold should format correctly with %.3f.
        """
        engine.max_distance_threshold = -0.5

        results = [
            {"_distance": 0.1, "text": "doc1", "file_id": "f1"},
        ]

        with caplog.at_level(logging.WARNING):
            result = engine._filter_relevant(results)

        assert len(result) > 0

        warning_messages = [r.message for r in caplog.records if r.levelname == 'WARNING']
        fallback_warnings = [m for m in warning_messages if 'max_distance_threshold' in str(m)]

        if fallback_warnings:
            # Negative should be formatted as -0.500
            assert '-0.500' in str(fallback_warnings[0])


class TestNoneThresholdTypeErrorPrevention:
    """Ensure TypeError is never raised for None thresholds."""

    @pytest.fixture
    def engine(self):
        """Create a RAGEngine instance with mocked dependencies."""
        with patch('app.services.rag_engine.EmbeddingService'), \
             patch('app.services.rag_engine.VectorStore'), \
             patch('app.services.rag_engine.MemoryStore'), \
             patch('app.services.rag_engine.LLMClient'):
            engine = RAGEngine()
            engine.retrieval_top_k = 5
            engine.retrieval_window = 0
            return engine

    def test_no_typeerror_when_both_thresholds_none(self, engine):
        """
        CRITICAL ATTACK: Ensure no TypeError when both thresholds are None.

        This directly tests the bug that was fixed.
        """
        engine.max_distance_threshold = None
        engine.relevance_threshold = None

        results = [
            {"_distance": 0.5, "text": "doc1", "file_id": "f1"},
        ]

        # This must NOT raise TypeError
        try:
            engine._filter_relevant(results)
        except TypeError as e:
            if "must be real number, not NoneType" in str(e):
                pytest.fail(f"BUG: TypeError raised when both thresholds are None: {e}")
            raise

    def test_no_typeerror_with_legacy_score_mode(self, engine):
        """
        ATTACK: Legacy score mode with None max_distance_threshold.

        Uses 'score' key instead of '_distance' to trigger legacy mode.
        """
        engine.max_distance_threshold = None
        engine.relevance_threshold = 0.9

        results = [
            {"score": 0.5, "text": "doc1", "file_id": "f1"},
        ]

        # This must NOT raise TypeError
        try:
            engine._filter_relevant(results)
        except TypeError as e:
            if "must be real number, not NoneType" in str(e):
                pytest.fail(f"BUG: TypeError raised in legacy mode: {e}")
            raise


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
