"""Tests for the calculate_primary_count helper function."""

import unittest
from unittest.mock import patch

from app.services.prompt_builder import calculate_primary_count


class TestCalculatePrimaryCount(unittest.TestCase):
    """Verify the primary/supporting evidence split logic.

    Formula: min(max(n - 2, 3), min(n, 5))
    Override: if settings.primary_evidence_count > 0, use that directly (capped by n).

    Sequence: 0→0, 1→1, 2→2, 3→3, 4→3, 5→3, 6→4, 7→5, 8→5, 9→5, 10→5, 20→5
    """

    def _count(self, n: int) -> int:
        """Call calculate_primary_count with override disabled."""
        with patch("app.services.prompt_builder.settings") as mock_settings:
            mock_settings.primary_evidence_count = 0
            mock_settings.anchor_best_chunk = False
            mock_settings.context_max_tokens = 6000
            return calculate_primary_count(n)

    def test_zero_chunks(self):
        """Zero chunks — returns 0 (edge case for empty retrieval)."""
        self.assertEqual(self._count(0), 0)

    def test_single_chunk(self):
        """One chunk available — it must be primary."""
        self.assertEqual(self._count(1), 1)

    def test_two_chunks(self):
        """Two chunks — min(max(0,3), min(2,5)) = min(3,2) = 2 → all primary."""
        self.assertEqual(self._count(2), 2)

    def test_three_chunks(self):
        """Three chunks — min(max(1,3), min(3,5)) = min(3,3) = 3 → all primary."""
        self.assertEqual(self._count(3), 3)

    def test_four_chunks(self):
        """Four chunks — min(max(2,3), min(4,5)) = min(3,4) = 3."""
        self.assertEqual(self._count(4), 3)

    def test_five_chunks(self):
        """Five chunks — min(max(3,3), min(5,5)) = min(3,5) = 3."""
        self.assertEqual(self._count(5), 3)

    def test_six_chunks(self):
        """Six chunks — min(max(4,3), min(6,5)) = min(4,5) = 4."""
        self.assertEqual(self._count(6), 4)

    def test_seven_chunks(self):
        """Seven chunks (reranker_top_n default) — should return 5, not 3."""
        self.assertEqual(self._count(7), 5)

    def test_eight_chunks(self):
        """Eight chunks — min(max(6,3), min(8,5)) = min(6,5) = 5."""
        self.assertEqual(self._count(8), 5)

    def test_ten_chunks(self):
        """Ten chunks — min(max(8,3), min(10,5)) = min(8,5) = 5."""
        self.assertEqual(self._count(10), 5)

    def test_twenty_chunks(self):
        """Twenty chunks — min(max(18,3), min(20,5)) = min(18,5) = 5 (hard cap at 5)."""
        self.assertEqual(self._count(20), 5)

    def test_override_nonzero(self):
        """PRIMARY_EVIDENCE_COUNT > 0 overrides formula."""
        with patch("app.services.prompt_builder.settings") as mock_settings:
            mock_settings.primary_evidence_count = 5
            mock_settings.anchor_best_chunk = False
            mock_settings.context_max_tokens = 6000
            self.assertEqual(calculate_primary_count(7), 5)
            self.assertEqual(calculate_primary_count(3), 3)  # capped by total_chunks

    def test_override_capped_by_total(self):
        """PRIMARY_EVIDENCE_COUNT override is capped by total_chunks."""
        with patch("app.services.prompt_builder.settings") as mock_settings:
            mock_settings.primary_evidence_count = 10
            mock_settings.anchor_best_chunk = False
            mock_settings.context_max_tokens = 6000
            self.assertEqual(calculate_primary_count(4), 4)  # 10 > 4, so returns 4

    def test_override_zero_uses_formula(self):
        """PRIMARY_EVIDENCE_COUNT = 0 falls through to formula."""
        with patch("app.services.prompt_builder.settings") as mock_settings:
            mock_settings.primary_evidence_count = 0
            mock_settings.anchor_best_chunk = False
            mock_settings.context_max_tokens = 6000
            self.assertEqual(calculate_primary_count(7), 5)


if __name__ == "__main__":
    unittest.main()
