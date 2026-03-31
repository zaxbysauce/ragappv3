"""Tests for RRF weights parameter in fusion.py."""

import pytest
from app.utils.fusion import rrf_fuse


class TestRRFWeights:
    """Tests for RRF weights feature."""

    def test_rrf_fuse_without_weights_backward_compatible(self):
        """Without weights, behavior is identical to original RRF."""
        result_lists = [
            [{"id": "a", "text": "doc a"}, {"id": "b", "text": "doc b"}],
            [{"id": "b", "text": "doc b"}, {"id": "c", "text": "doc c"}],
        ]
        # With weights=None (default), all lists get weight 1.0
        result = rrf_fuse(result_lists, k=60, weights=None)

        ids = [r["id"] for r in result]
        assert ids == ["b", "a", "c"]
        # b appears in both lists, gets highest score
        assert result[0]["_rrf_score"] > result[1]["_rrf_score"]
        assert result[1]["_rrf_score"] > result[2]["_rrf_score"]

    def test_rrf_fuse_weights_affects_ranking(self):
        """Weights change the ranking - higher weight list gets priority."""
        result_lists = [
            [{"id": "a", "text": "doc a"}, {"id": "b", "text": "doc b"}],
            [{"id": "b", "text": "doc b"}, {"id": "c", "text": "doc c"}],
        ]
        # List 0 gets weight 2.0, list 1 gets weight 1.0
        # 'a' is only in list 0 (rank 0): score = 2.0 * 1/61
        # 'b' is in both lists: score = 2.0 * 1/61 + 1.0 * 1/61 = 3/61
        # 'c' is only in list 1 (rank 1): score = 1.0 * 1/62
        result = rrf_fuse(result_lists, k=60, weights=[2.0, 1.0])

        ids = [r["id"] for r in result]
        # 'b' should still be first (in both lists)
        # 'a' vs 'c': 'a' gets 2.0 * 1/61 ≈ 0.0328, 'c' gets 1/62 ≈ 0.0161
        assert ids[0] == "b"
        assert ids.index("a") < ids.index("c")  # 'a' ranks higher than 'c'

    def test_rrf_fuse_weights_2x_first_list(self):
        """weights=[1.0, 0.5] makes first list weighted 2x second."""
        result_lists = [
            [{"id": "x", "text": "x only in first"}],
            [{"id": "y", "text": "y only in second"}],
        ]
        result = rrf_fuse(result_lists, k=60, weights=[1.0, 0.5])

        ids = [r["id"] for r in result]
        # 'x' gets 1.0 * 1/61 ≈ 0.0164, 'y' gets 0.5 * 1/61 ≈ 0.0082
        # 'x' should rank higher
        assert ids == ["x", "y"]

    def test_rrf_fuse_weights_exact_score_calculation(self):
        """Verify exact score formula: weight * 1/(k + rank + 1)."""
        result_lists = [
            [{"id": "doc", "text": "test doc"}],  # rank 0
        ]
        weight = 3.0
        k = 60
        expected_score = weight * 1.0 / (k + 0 + 1)  # 3.0 / 61

        result = rrf_fuse(result_lists, k=k, weights=[weight])

        assert len(result) == 1
        assert result[0]["_rrf_score"] == pytest.approx(expected_score)

    def test_rrf_fuse_weights_equal_weights_same_as_no_weights(self):
        """weights=[1.0, 1.0] produces same result as weights=None."""
        result_lists = [
            [{"id": "a", "text": "doc a"}, {"id": "b", "text": "doc b"}],
            [{"id": "b", "text": "doc b"}, {"id": "c", "text": "doc c"}],
        ]

        result_no_weights = rrf_fuse(result_lists, k=60)
        result_equal_weights = rrf_fuse(result_lists, k=60, weights=[1.0, 1.0])

        # Same ordering
        ids_no = [r["id"] for r in result_no_weights]
        ids_equal = [r["id"] for r in result_equal_weights]
        assert ids_no == ids_equal

        # Same scores
        for r1, r2 in zip(result_no_weights, result_equal_weights):
            assert r1["_rrf_score"] == pytest.approx(r2["_rrf_score"])

    def test_rrf_fuse_weights_three_lists(self):
        """Weights work with three or more lists."""
        result_lists = [
            [{"id": "a", "text": "only in first"}],
            [{"id": "b", "text": "only in second"}],
            [{"id": "c", "text": "only in third"}],
        ]
        # 'a' gets weight 1.0, 'b' gets weight 0.5, 'c' gets weight 2.0
        # 'c' should rank first (highest weight)
        result = rrf_fuse(result_lists, k=60, weights=[1.0, 0.5, 2.0])

        ids = [r["id"] for r in result]
        assert ids == ["c", "a", "b"]

    def test_rrf_fuse_weights_too_short_raises_error(self):
        """ValueError raised when weights list is shorter than result_lists."""
        result_lists = [
            [{"id": "a", "text": "doc a"}],
            [{"id": "b", "text": "doc b"}],
        ]
        # Only 1 weight for 2 lists
        with pytest.raises(
            ValueError, match="weights list has 1 items but 2 result lists"
        ):
            rrf_fuse(result_lists, k=60, weights=[1.0])

    def test_rrf_fuse_weights_exact_length_succeeds(self):
        """Exactly matching length works."""
        result_lists = [
            [{"id": "a", "text": "doc a"}],
            [{"id": "b", "text": "doc b"}],
        ]
        # Length matches exactly
        result = rrf_fuse(result_lists, k=60, weights=[1.0, 1.0])
        assert len(result) == 2

    def test_rrf_fuse_weights_zero_weight(self):
        """Zero weight effectively disables that list."""
        result_lists = [
            [{"id": "a", "text": "in first"}],
            [{"id": "b", "text": "in second"}],
        ]
        # List 0 has weight 0, list 1 has weight 1.0
        result = rrf_fuse(result_lists, k=60, weights=[0.0, 1.0])

        ids = [r["id"] for r in result]
        # Only 'b' contributes (weight 0 for 'a'), but deduplication keeps both
        # 'a' gets score 0, 'b' gets 1/61
        assert ids == ["b", "a"]
        # 'a' has zero contribution
        a_record = next(r for r in result if r["id"] == "a")
        assert a_record["_rrf_score"] == 0.0

    def test_rrf_fuse_weights_with_recency_combined(self):
        """Weights work together with recency scores."""
        result_lists = [
            [{"id": "old", "text": "old doc"}],
            [{"id": "new", "text": "new doc"}],
        ]
        # 'old' in list 0 (weight 2.0), 'new' in list 1 (weight 1.0)
        # Without recency: old gets 2/61 ≈ 0.0328, new gets 1/61 ≈ 0.0164
        # But with recency boosting 'new': new gets recency advantage
        recency_scores = {"old": 0.1, "new": 0.9}

        result = rrf_fuse(
            result_lists,
            k=60,
            weights=[2.0, 1.0],
            recency_scores=recency_scores,
            recency_weight=0.5,
        )

        ids = [r["id"] for r in result]
        # 'new' should rank first due to recency boost outweighing weight difference
        assert ids[0] == "new"

    def test_rrf_fuse_weights_duplicate_id_different_ranks(self):
        """Duplicate IDs across weighted lists accumulate weighted scores."""
        result_lists = [
            [{"id": "doc", "text": "at rank 0"}],  # rank 0 -> 1.0 * 1/61
            [
                {"id": "doc", "text": "at rank 0"},
                {"id": "other", "text": "other"},
            ],  # rank 0 -> 0.5 * 1/61
        ]
        weights = [1.0, 0.5]

        result = rrf_fuse(result_lists, k=60, weights=weights)

        # 'doc' appears in both lists, gets weighted sum
        doc_record = next(r for r in result if r["id"] == "doc")
        expected_score = 1.0 * (1 / 61) + 0.5 * (1 / 61)
        assert doc_record["_rrf_score"] == pytest.approx(expected_score)

    def test_rrf_fuse_weights_default_k_with_weights(self):
        """Default k=60 works with weights."""
        result_lists = [
            [{"id": "a", "text": "doc a"}],
        ]
        result = rrf_fuse(result_lists, weights=[2.0])

        # Default k=60, rank 0: 2.0 / 61
        assert result[0]["_rrf_score"] == pytest.approx(2.0 / 61)
