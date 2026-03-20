"""Tests for RRF recency scoring in fusion.py."""

import pytest
from app.utils.fusion import rrf_fuse


class TestRRFRecency:
    """Tests for RRF recency scoring feature."""

    def test_rrf_fuse_basic_no_recency(self):
        """Existing behavior unchanged when no recency provided."""
        result_lists = [
            [{"id": "a", "text": "doc a"}, {"id": "b", "text": "doc b"}],
            [{"id": "b", "text": "doc b"}, {"id": "c", "text": "doc c"}],
        ]
        result = rrf_fuse(result_lists, k=60)

        # Should deduplicate and sort by RRF score
        ids = [r["id"] for r in result]
        assert ids == ["b", "a", "c"]
        # b appears in both lists, gets highest score
        assert result[0]["_rrf_score"] > result[1]["_rrf_score"]
        assert result[1]["_rrf_score"] > result[2]["_rrf_score"]

    def test_rrf_fuse_recency_boosts_recent(self):
        """Recent docs score higher when recency_weight > 0."""
        result_lists = [
            [{"id": "old", "text": "old doc"}, {"id": "new", "text": "new doc"}],
        ]
        # Old doc has low recency, new doc has high recency
        recency_scores = {"old": 0.1, "new": 0.9}
        result = rrf_fuse(
            result_lists, k=60, recency_scores=recency_scores, recency_weight=0.5
        )

        ids = [r["id"] for r in result]
        # New should rank higher due to recency boost
        assert ids.index("new") < ids.index("old")

    def test_rrf_fuse_recency_weight_zero_ignores_recency(self):
        """weight=0.0 ignores recency_scores completely."""
        result_lists = [
            [{"id": "a", "text": "doc a"}, {"id": "b", "text": "doc b"}],
        ]
        # recency_scores would boost 'a' if weight > 0
        recency_scores = {"a": 1.0, "b": 0.0}

        result_with_recency = rrf_fuse(
            result_lists, k=60, recency_scores=recency_scores, recency_weight=0.0
        )
        result_without_recency = rrf_fuse(result_lists, k=60)

        # Should be identical since weight=0
        ids_with = [r["id"] for r in result_with_recency]
        ids_without = [r["id"] for r in result_without_recency]
        assert ids_with == ids_without
        assert (
            result_with_recency[0]["_rrf_score"]
            == result_without_recency[0]["_rrf_score"]
        )

    def test_rrf_fuse_recency_weight_one_pure_recency(self):
        """weight=1.0 ignores RRF scores, uses pure recency."""
        result_lists = [
            [{"id": "old", "text": "old doc"}, {"id": "new", "text": "new doc"}],
        ]
        recency_scores = {"old": 0.1, "new": 0.9}

        result = rrf_fuse(
            result_lists, k=60, recency_scores=recency_scores, recency_weight=1.0
        )

        ids = [r["id"] for r in result]
        # Sorted purely by recency score
        assert ids == ["new", "old"]
        # Score should be exactly the recency score
        assert result[0]["_rrf_score"] == 0.9
        assert result[1]["_rrf_score"] == 0.1

    def test_rrf_fuse_missing_recency_gets_neutral(self):
        """Records not in recency_scores get neutral 0.5."""
        result_lists = [
            [{"id": "a", "text": "doc a"}, {"id": "b", "text": "doc b"}],
        ]
        recency_scores = {"a": 1.0}  # only 'a' has recency

        result = rrf_fuse(
            result_lists, k=60, recency_scores=recency_scores, recency_weight=1.0
        )

        # 'a' gets its recency score, 'b' gets neutral 0.5
        scores = {r["id"]: r["_rrf_score"] for r in result}
        assert scores["a"] == 1.0
        assert scores["b"] == 0.5

    def test_rrf_fuse_empty_recency_scores(self):
        """Empty dict behaves like no recency."""
        result_lists = [
            [{"id": "a", "text": "doc a"}],
        ]
        recency_scores = {}

        result_with_empty = rrf_fuse(
            result_lists, k=60, recency_scores=recency_scores, recency_weight=0.5
        )
        result_without = rrf_fuse(result_lists, k=60)

        # Should be identical - empty dict like no recency
        assert result_with_empty[0]["_rrf_score"] == result_without[0]["_rrf_score"]

    def test_rrf_fuse_recency_none_disabled(self):
        """recency_scores=None behaves like no recency."""
        result_lists = [
            [{"id": "a", "text": "doc a"}, {"id": "b", "text": "doc b"}],
        ]

        result_with_none = rrf_fuse(
            result_lists, k=60, recency_scores=None, recency_weight=0.5
        )
        result_without = rrf_fuse(result_lists, k=60)

        ids_with = [r["id"] for r in result_with_none]
        ids_without = [r["id"] for r in result_without]
        assert ids_with == ids_without
        assert result_with_none[0]["_rrf_score"] == result_without[0]["_rrf_score"]

    def test_rrf_fuse_recency_blend_correctness(self):
        """Verify exact formula with known values."""
        result_lists = [
            [{"id": "doc", "text": "test doc"}],  # rank 0 -> score = 1/61
        ]
        rrf_score = 1.0 / 61  # k=60, rank=0
        recency_score = 0.8
        recency_weight = 0.25

        expected_score = (
            rrf_score * (1 - recency_weight) + recency_score * recency_weight
        )

        result = rrf_fuse(
            result_lists,
            k=60,
            recency_scores={"doc": recency_score},
            recency_weight=recency_weight,
        )

        assert len(result) == 1
        assert result[0]["_rrf_score"] == pytest.approx(expected_score)

    def test_rrf_fuse_dedup_with_recency(self):
        """Same record across lists gets blended recency."""
        # 'a' appears in both lists at different ranks
        result_lists = [
            [{"id": "a", "text": "doc a"}],  # rank 0 -> 1/61
            [
                {"id": "a", "text": "doc a"},
                {"id": "b", "text": "doc b"},
            ],  # rank 0 -> 1/61, rank 1 -> 1/62
        ]

        # With recency, 'a' should be ranked by combined RRF + recency
        recency_scores = {"a": 0.9, "b": 0.5}
        result = rrf_fuse(
            result_lists, k=60, recency_scores=recency_scores, recency_weight=0.5
        )

        ids = [r["id"] for r in result]
        assert ids[0] == "a"  # 'a' has higher combined score
        assert ids[1] == "b"

        # Verify 'a' got blended score
        a_record = next(r for r in result if r["id"] == "a")
        expected_rrf = (1 / 61) + (1 / 61)  # sum from both lists
        expected_blended = expected_rrf * 0.5 + 0.9 * 0.5
        assert a_record["_rrf_score"] == pytest.approx(expected_blended)
