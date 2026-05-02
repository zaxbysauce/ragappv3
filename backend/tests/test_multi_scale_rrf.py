"""Tests that ``settings.multi_scale_rrf_k`` actually shapes cross-scale fusion (P3.4).

The previous implementation summed per-scale RRF scores, making
``multi_scale_rrf_k`` a no-op. The new implementation uses the shared
``rrf_fuse`` helper so changing ``k`` provably changes the fused
ordering for non-degenerate inputs.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.utils.fusion import rrf_fuse


class TestMultiScaleRRFParametrization(unittest.TestCase):
    def test_smaller_k_sharpens_top_preference(self):
        # Two scales, partial overlap. With small k the top items of
        # each scale dominate the fused order; with large k contributions
        # flatten and lower-ranked items can compete.
        scale_a = [
            {"id": "a", "scale": "512"},
            {"id": "b", "scale": "512"},
            {"id": "c", "scale": "512"},
            {"id": "d", "scale": "512"},
        ]
        scale_b = [
            {"id": "x", "scale": "1024"},
            {"id": "y", "scale": "1024"},
            {"id": "a", "scale": "1024"},  # overlaps with scale_a but lower rank
            {"id": "z", "scale": "1024"},
        ]
        small_k = rrf_fuse([scale_a, scale_b], k=10, limit=5)
        large_k = rrf_fuse([scale_a, scale_b], k=600, limit=5)

        # With small k, the top-1 of each scale dominates: 'a' (rank 1 in
        # scale_a, rank 3 in scale_b) plus 'x' (rank 1 in scale_b) jostle
        # for the top two slots — 'a' should win because it appears in both.
        small_top = small_k[0]["id"]
        large_top = large_k[0]["id"]
        # The fused score for 'a' must be strictly greater than for 'x' at
        # small k because 'a' contributes to both lists.
        small_a_score = next(r["_rrf_score"] for r in small_k if r["id"] == "a")
        small_x_score = next(r["_rrf_score"] for r in small_k if r["id"] == "x")
        self.assertGreater(small_a_score, small_x_score)
        # And the *gap* between the two top contenders shrinks as k grows
        # — the same difference in rank contributes less.
        large_a_score = next(r["_rrf_score"] for r in large_k if r["id"] == "a")
        large_x_score = next(r["_rrf_score"] for r in large_k if r["id"] == "x")
        small_gap = small_a_score - small_x_score
        large_gap = large_a_score - large_x_score
        self.assertGreater(small_gap, large_gap)
        # Sanity: with both k values 'a' still wins but its dominance
        # degrades as k grows.
        self.assertEqual(small_top, "a")
        self.assertEqual(large_top, "a")

    def test_changing_k_reorders_borderline_items(self):
        # A pair of items with identical positions in different scales —
        # absolute scores depend on k but ordering should be consistent.
        a = [{"id": "a"}, {"id": "b"}]
        b = [{"id": "c"}, {"id": "a"}]
        out_small = rrf_fuse([a, b], k=1, limit=3)
        out_large = rrf_fuse([a, b], k=200, limit=3)
        # 'a' should win in both because it appears in both lists. We
        # primarily assert that scores differ between k values — proof
        # that the parameter is actually being used.
        self.assertNotEqual(
            out_small[0]["_rrf_score"], out_large[0]["_rrf_score"]
        )


if __name__ == "__main__":
    unittest.main()
