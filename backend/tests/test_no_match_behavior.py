"""Tests for the no_match fallback behavior in DocumentRetrievalService.

Verifies that:
- When some results pass threshold -> no_match is False, results returned
- When ALL results exceed threshold -> no_match is True, empty list returned
- When input is empty -> no_match is False (no results to filter)
- no_match resets to False on each call (idempotent)
- The no_match flag is accessible on the service instance after filter_relevant() call
"""

import pytest
from unittest.mock import MagicMock, patch

from app.services.document_retrieval import DocumentRetrievalService, RAGSource


class TestNoMatchBehavior:
    """Test suite for no_match flag behavior in filter_relevant()."""

    @pytest.fixture
    def mock_settings(self):
        """Mock settings with default values."""
        mock = MagicMock()
        mock.max_distance_threshold = 0.5
        mock.retrieval_top_k = 10
        mock.retrieval_window = 0
        mock.rag_relevance_threshold = 0.5
        return mock

    @pytest.fixture
    def retrieval_service(self, mock_settings):
        """Create a DocumentRetrievalService with mocked settings."""
        with patch("app.services.document_retrieval.settings", mock_settings):
            service = DocumentRetrievalService(
                max_distance_threshold=0.5,
                retrieval_top_k=10,
                retrieval_window=0,
            )
            return service

    def test_some_results_pass_threshold_no_match_is_false(self, retrieval_service):
        """When some results pass threshold, no_match is False and results are returned."""
        # Input: 3 results, 2 pass threshold (distance < 0.5)
        results = [
            {"text": "relevant doc 1", "file_id": "file1", "_distance": 0.3},
            {"text": "relevant doc 2", "file_id": "file2", "_distance": 0.4},
            {
                "text": "irrelevant doc",
                "file_id": "file3",
                "_distance": 0.8,
            },  # exceeds threshold
        ]

        output = retrieval_service.filter_relevant(results)

        # ASSERTION: no_match is False
        assert retrieval_service.no_match is False, (
            f"Expected no_match=False when results pass threshold, got {retrieval_service.no_match}"
        )
        # ASSERTION: Exactly 2 results returned (the ones that passed)
        assert len(output) == 2, f"Expected 2 results, got {len(output)}"
        # ASSERTION: Returned objects are RAGSource instances
        assert all(isinstance(r, RAGSource) for r in output), (
            "All results should be RAGSource instances"
        )
        # ASSERTION: Correct texts returned
        returned_texts = {r.text for r in output}
        assert returned_texts == {"relevant doc 1", "relevant doc 2"}, (
            f"Expected correct texts, got {returned_texts}"
        )

    def test_all_results_exceed_threshold_no_match_is_true(self, retrieval_service):
        """When ALL results exceed threshold, no_match is True and empty list returned."""
        # Input: 3 results, ALL exceed threshold (distance > 0.5)
        results = [
            {"text": "irrelevant doc 1", "file_id": "file1", "_distance": 0.7},
            {"text": "irrelevant doc 2", "file_id": "file2", "_distance": 0.8},
            {"text": "irrelevant doc 3", "file_id": "file3", "_distance": 0.9},
        ]

        output = retrieval_service.filter_relevant(results)

        # ASSERTION: no_match is True
        assert retrieval_service.no_match is True, (
            f"Expected no_match=True when all results exceed threshold, got {retrieval_service.no_match}"
        )
        # ASSERTION: Empty list returned (not top-k fallback)
        assert output == [], f"Expected empty list, got {output}"
        assert len(output) == 0, f"Expected 0 results, got {len(output)}"

    def test_empty_input_no_match_is_false(self, retrieval_service):
        """When input is empty, no_match is False (no results to filter)."""
        # Input: Empty list
        results = []

        output = retrieval_service.filter_relevant(results)

        # ASSERTION: no_match is False (no results to filter)
        assert retrieval_service.no_match is False, (
            f"Expected no_match=False for empty input, got {retrieval_service.no_match}"
        )
        # ASSERTION: Empty list returned
        assert output == [], f"Expected empty list, got {output}"

    def test_no_match_resets_to_false_on_each_call(self, retrieval_service):
        """no_match resets to False at the start of each call (idempotent)."""
        # First call: all results exceed threshold -> no_match=True
        results_all_exceed = [
            {"text": "irrelevant", "file_id": "file1", "_distance": 0.9},
        ]
        output1 = retrieval_service.filter_relevant(results_all_exceed)

        # VERIFY: no_match is True after first call
        assert retrieval_service.no_match is True, (
            "Expected no_match=True after first call"
        )

        # Second call: some results pass threshold -> no_match should be False
        results_some_pass = [
            {"text": "relevant", "file_id": "file2", "_distance": 0.3},
            {"text": "irrelevant", "file_id": "file3", "_distance": 0.9},
        ]
        output2 = retrieval_service.filter_relevant(results_some_pass)

        # ASSERTION: no_match is False after second call (was reset)
        assert retrieval_service.no_match is False, (
            f"Expected no_match=False after second call (reset behavior), got {retrieval_service.no_match}"
        )
        # ASSERTION: One result returned from second call
        assert len(output2) == 1, f"Expected 1 result, got {len(output2)}"

    def test_no_match_flag_accessible_on_service_instance(self, retrieval_service):
        """The no_match flag is accessible on the service instance after filter_relevant() call."""
        # Verify initial state
        assert hasattr(retrieval_service, "no_match"), (
            "Service should have no_match attribute"
        )
        assert retrieval_service.no_match is False, "Initial no_match should be False"

        # Call with all exceeding threshold
        results = [{"text": "doc", "file_id": "file1", "_distance": 0.9}]
        retrieval_service.filter_relevant(results)

        # ASSERTION: Can read no_match from instance
        assert retrieval_service.no_match is True, (
            "no_match should be True and accessible"
        )

    def test_no_match_false_when_zero_distance_results(self, retrieval_service):
        """Results with distance=0 should pass threshold and no_match should be False."""
        results = [
            {"text": "perfect match", "file_id": "file1", "_distance": 0.0},
        ]

        output = retrieval_service.filter_relevant(results)

        assert retrieval_service.no_match is False, (
            f"Expected no_match=False for distance=0, got {retrieval_service.no_match}"
        )
        assert len(output) == 1, f"Expected 1 result, got {len(output)}"

    def test_no_match_true_at_threshold_boundary(self, retrieval_service):
        """When distance exactly equals threshold, result is filtered out (distance > threshold)."""
        # Using threshold of 0.5, distance of 0.5 exactly should be filtered out
        results = [
            {
                "text": "boundary doc",
                "file_id": "file1",
                "_distance": 0.5,
            },  # exactly at threshold
        ]

        output = retrieval_service.filter_relevant(results)

        # At threshold (0.5) with threshold 0.5: 0.5 > 0.5 is False, so it passes
        # Actually checking: should_skip = distance > threshold = 0.5 > 0.5 = False
        # So this result should PASS the filter
        assert retrieval_service.no_match is False, (
            f"Expected no_match=False when distance equals threshold, got {retrieval_service.no_match}"
        )

    def test_no_match_true_just_above_threshold(self, retrieval_service):
        """When distance is just above threshold, result is filtered and no_match=True if all filtered."""
        results = [
            {
                "text": "just above",
                "file_id": "file1",
                "_distance": 0.5001,
            },  # just above 0.5
        ]

        output = retrieval_service.filter_relevant(results)

        # should_skip = distance > threshold = 0.5001 > 0.5 = True -> filtered out
        assert retrieval_service.no_match is True, (
            f"Expected no_match=True when all results just above threshold, got {retrieval_service.no_match}"
        )
        assert output == [], f"Expected empty list, got {output}"

    def test_single_result_below_threshold_no_match_false(self, retrieval_service):
        """Single result below threshold should return it and no_match=False."""
        results = [
            {"text": "only result", "file_id": "file1", "_distance": 0.1},
        ]

        output = retrieval_service.filter_relevant(results)

        assert retrieval_service.no_match is False, (
            f"Expected no_match=False for single passing result, got {retrieval_service.no_match}"
        )
        assert len(output) == 1, f"Expected 1 result, got {len(output)}"
        assert output[0].text == "only result"

    def test_single_result_above_threshold_no_match_true(self, retrieval_service):
        """Single result above threshold should return empty and no_match=True."""
        results = [
            {"text": "only result", "file_id": "file1", "_distance": 0.9},
        ]

        output = retrieval_service.filter_relevant(results)

        assert retrieval_service.no_match is True, (
            f"Expected no_match=True for single failing result, got {retrieval_service.no_match}"
        )
        assert output == [], f"Expected empty list, got {output}"

    def test_score_field_instead_of_distance(self, retrieval_service):
        """Results using 'score' field instead of '_distance' should work correctly."""
        # When has_distance is False (no _distance key), score is used
        # and the comparison is flipped (score < threshold for skip)
        results = [
            {
                "text": "low score",
                "file_id": "file1",
                "score": 0.1,
            },  # passes (score >= threshold)
            {
                "text": "high score",
                "file_id": "file2",
                "score": 0.9,
            },  # filtered (score < threshold is False, so passes)
        ]

        output = retrieval_service.filter_relevant(results)

        # With score field and no _distance: should_skip = score < threshold
        # 0.1 < 0.5 = True -> should_skip = True (filtered)
        # 0.9 < 0.5 = False -> should_skip = False (passes)
        # So we expect 1 result (the 0.9 score) and no_match=False
        assert len(output) == 1, (
            f"Expected 1 result with score field, got {len(output)}"
        )
        assert retrieval_service.no_match is False, (
            f"Expected no_match=False with score field results, got {retrieval_service.no_match}"
        )

    def test_no_match_resets_false_to_false(self, retrieval_service):
        """Calling with empty list after empty list keeps no_match as False."""
        # First call: empty input
        retrieval_service.filter_relevant([])
        assert retrieval_service.no_match is False, (
            "Expected no_match=False after first empty call"
        )

        # Second call: empty input again
        retrieval_service.filter_relevant([])
        assert retrieval_service.no_match is False, (
            f"Expected no_match=False after second empty call, got {retrieval_service.no_match}"
        )

    def test_consecutive_calls_with_varying_inputs(self, retrieval_service):
        """Multiple consecutive calls with different inputs properly update no_match."""
        # Call 1: all exceed -> no_match=True
        retrieval_service.filter_relevant(
            [{"text": "a", "file_id": "f1", "_distance": 0.9}]
        )
        assert retrieval_service.no_match is True, "Call 1: expected no_match=True"

        # Call 2: some pass -> no_match=False
        retrieval_service.filter_relevant(
            [
                {"text": "a", "file_id": "f1", "_distance": 0.3},
                {"text": "b", "file_id": "f2", "_distance": 0.9},
            ]
        )
        assert retrieval_service.no_match is False, "Call 2: expected no_match=False"

        # Call 3: empty -> no_match=False
        retrieval_service.filter_relevant([])
        assert retrieval_service.no_match is False, "Call 3: expected no_match=False"

        # Call 4: all exceed -> no_match=True
        retrieval_service.filter_relevant(
            [
                {"text": "a", "file_id": "f1", "_distance": 0.7},
                {"text": "b", "file_id": "f2", "_distance": 0.8},
            ]
        )
        assert retrieval_service.no_match is True, "Call 4: expected no_match=True"
