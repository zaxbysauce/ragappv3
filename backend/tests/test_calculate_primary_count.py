"""Tests for the calculate_primary_count helper function."""

import unittest

from app.services.prompt_builder import calculate_primary_count


class TestCalculatePrimaryCount(unittest.TestCase):
    """Verify the primary/supporting evidence split logic."""

    def test_single_chunk(self):
        """One chunk available — it must be primary."""
        self.assertEqual(calculate_primary_count(1), 1)

    def test_two_chunks(self):
        """Two chunks — floor(2/2)=1, max(1,3)=3, min(3,2)=2 → all primary."""
        self.assertEqual(calculate_primary_count(2), 2)

    def test_three_chunks(self):
        """Three chunks — floor(3/2)=1, max(1,3)=3, min(3,3)=3 → all primary."""
        self.assertEqual(calculate_primary_count(3), 3)

    def test_five_chunks(self):
        """Five chunks — floor(5/2)=2, max(2,3)=3, min(3,5)=3."""
        self.assertEqual(calculate_primary_count(5), 3)

    def test_six_chunks(self):
        """Six chunks — floor(6/2)=3, max(3,3)=3, min(3,6)=3."""
        self.assertEqual(calculate_primary_count(6), 3)

    def test_ten_chunks(self):
        """Ten chunks — floor(10/2)=5, max(5,3)=5, min(5,10)=5."""
        self.assertEqual(calculate_primary_count(10), 5)

    def test_twenty_chunks(self):
        """Twenty chunks — floor(20/2)=10, max(10,3)=10, min(10,20)=10."""
        self.assertEqual(calculate_primary_count(20), 10)

    def test_zero_chunks(self):
        """Zero chunks — returns 0 (edge case for empty retrieval)."""
        self.assertEqual(calculate_primary_count(0), 0)


if __name__ == "__main__":
    unittest.main()
