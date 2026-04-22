"""Tests for weighted RRF fusion with configurable k (Issue #10).

Tests 4 scenarios:
1. Sharp k with weights amplifies top-1 advantage (original wins)
2. k=60 uniform weights baseline (consistent mid-range beats single #1)
3. Zero-weight arms are excluded from fusion
4. Fusion preserves _distance and _rerank_score fields on records
"""

import pytest

from app.utils.fusion import rrf_fuse


class TestRRFFusionConfig:
    """Tests for weighted RRF fusion with configurable k."""

    def test_sharp_k_with_weights_original_wins(self):
        """Sharp k=20 with weights=[1.0, 0.5, 0.5]: doc A (#1 original) beats doc B (#15 all).

        Doc A: #1 on original (position 0), #51 on step-back and HyDE (position 50)
        Doc B: #15 on all variants consistently (position 14)
        With k=20 + weights [1.0, 0.5, 0.5]: doc A should win due to top-1 advantage amplified by weight.

        Expected RRF scores:
        - Doc A: 1.0/(20+1) + 0.5/(20+51) + 0.5/(20+51)
               = 1/21 + 0.5/71 + 0.5/71
               = 0.04762 + 0.00704 + 0.00704
               = 0.06170
        - Doc B: (1.0 + 0.5 + 0.5)/(20+15)
               = 2.0/35
               = 0.05714
        Doc A wins (0.06170 > 0.05714).
        """
        # Doc A: rank 0 on original (position 0), rank 49 on step-back and HyDE (position 49)
        # Doc B: rank 14 on all variants (position 14 in 0-indexed)
        original_results = [
            {"id": "doc_A", "text": "Doc A content"},  # rank 0
        ] + [
            {"id": f"other_original_{i}", "text": f"Other {i}"}
            for i in range(13)
        ] + [
            {"id": "doc_B", "text": "Doc B content"},  # rank 14 (position 14)
        ]
        # In stepback/hyde: doc_B at position 14 (rank 15), doc_A at position 49 (rank 50)
        stepback_results = [
            {"id": f"other_sb_{i}", "text": f"Other {i}"}
            for i in range(14)
        ] + [
            {"id": "doc_B", "text": "Doc B content"},  # rank 14 (position 14)
        ] + [
            {"id": f"other_sb_{i}", "text": f"Other {i}"}
            for i in range(14, 49)
        ] + [
            {"id": "doc_A", "text": "Doc A content"},  # rank 49 (position 49)
        ]
        hyde_results = list(stepback_results)

        result_lists = [original_results, stepback_results, hyde_results]
        weights = [1.0, 0.5, 0.5]
        k = 20

        result = rrf_fuse(result_lists, k=k, weights=weights)

        ids = [r["id"] for r in result]
        # Doc A should be first due to sharp k + high original weight amplifying #1 advantage
        assert ids[0] == "doc_A", f"Expected doc_A first, got order: {ids[:5]}"

        # Verify exact scores
        doc_a_record = next(r for r in result if r["id"] == "doc_A")
        doc_b_record = next(r for r in result if r["id"] == "doc_B")

        # doc_A is at rank 0 in original (position 0), but rank 50 in stepback/hyde (position 50)
        # doc_B is at rank 14 in all lists (position 14)
        expected_doc_a = 1.0 / (k + 0 + 1) + 0.5 / (k + 50 + 1) + 0.5 / (k + 50 + 1)
        expected_doc_b = (1.0 + 0.5 + 0.5) / (k + 14 + 1)

        assert doc_a_record["_rrf_score"] == pytest.approx(expected_doc_a, rel=1e-9)
        assert doc_b_record["_rrf_score"] == pytest.approx(expected_doc_b, rel=1e-9)
        assert doc_a_record["_rrf_score"] > doc_b_record["_rrf_score"]

    def test_k60_uniform_b_wins(self):
        """Regression baseline: k=60 with uniform weights (None) - doc B (#15 all) beats doc A (#1 + #51).

        This is the backward-compatible default behavior.
        With k=60 uniform, consistent mid-range rankings (#15 on all) beat single #1 + poor rankings.

        Expected RRF scores:
        - Doc A: 1/(60+1) + 1/(60+51) + 1/(60+51)
               = 1/61 + 1/111 + 1/111
               = 0.01639 + 0.00901 + 0.00901
               = 0.03441
        - Doc B: 3/(60+15)
               = 3/75
               = 0.04
        Doc B wins (0.04 > 0.03441).
        """
        # Same structure as sharp k test - doc_A at rank 0 in original, rank 49 in others
        # doc_B at rank 14 consistently
        original_results = [
            {"id": "doc_A", "text": "Doc A content"},  # rank 0
        ] + [
            {"id": f"other_original_{i}", "text": f"Other {i}"}
            for i in range(13)
        ] + [
            {"id": "doc_B", "text": "Doc B content"},  # rank 14
        ]
        stepback_results = [
            {"id": f"other_sb_{i}", "text": f"Other {i}"}
            for i in range(14)
        ] + [
            {"id": "doc_B", "text": "Doc B content"},  # rank 14
        ] + [
            {"id": f"other_sb_{i}", "text": f"Other {i}"}
            for i in range(14, 49)
        ] + [
            {"id": "doc_A", "text": "Doc A content"},  # rank 49
        ]
        hyde_results = list(stepback_results)

        result_lists = [original_results, stepback_results, hyde_results]
        k = 60
        weights = None  # Uniform weights (backward compatible default)

        result = rrf_fuse(result_lists, k=k, weights=weights)

        ids = [r["id"] for r in result]
        # Doc B should win due to consistent mid-range rankings beating single #1
        assert ids[0] == "doc_B", f"Expected doc_B first, got order: {ids[:5]}"

        # Verify exact scores
        doc_a_record = next(r for r in result if r["id"] == "doc_A")
        doc_b_record = next(r for r in result if r["id"] == "doc_B")

        # doc_A is at rank 0 in original (position 0), but rank 50 in stepback/hyde (position 50)
        # doc_B is at rank 14 in all lists (position 14)
        expected_doc_a = 1.0 / (k + 0 + 1) + 1.0 / (k + 50 + 1) + 1.0 / (k + 50 + 1)
        expected_doc_b = 3.0 / (k + 14 + 1)

        assert doc_a_record["_rrf_score"] == pytest.approx(expected_doc_a, rel=1e-9)
        assert doc_b_record["_rrf_score"] == pytest.approx(expected_doc_b, rel=1e-9)
        assert doc_b_record["_rrf_score"] > doc_a_record["_rrf_score"]

    def test_zero_weight_arms_excluded(self):
        """weights=[1.0, 0.0, 0.0] means only original query arm contributes.

        Step-back and HyDE arms produce zero contribution to RRF scores.
        Result should match fusion of original arm alone.
        """
        # original_results: doc_A at rank 0, doc_B at rank 14, doc_C at rank 15
        original_results = [
            {"id": "doc_A", "text": "Doc A content"},
        ] + [
            {"id": f"other_{i}", "text": f"Other {i}"}
            for i in range(13)
        ] + [
            {"id": "doc_B", "text": "Doc B content"},  # rank 14
            {"id": "doc_C", "text": "Doc C content"},  # rank 15
        ]
        # stepback_results: doc_B at rank 0 (position 0), doc_X at rank 1
        stepback_results = [
            {"id": "doc_B", "text": "Doc B content"},  # rank 0
            {"id": "doc_X", "text": "Doc X content"},  # rank 1
        ]
        # hyde_results: doc_B at rank 0 (position 0), doc_Y at rank 1
        hyde_results = [
            {"id": "doc_B", "text": "Doc B content"},  # rank 0
            {"id": "doc_Y", "text": "Doc Y content"},  # rank 1
        ]

        # Fusion with all three arms but weights=[1.0, 0.0, 0.0]
        result_lists_weighted = [original_results, stepback_results, hyde_results]
        result_weighted = rrf_fuse(
            result_lists_weighted,
            k=60,
            weights=[1.0, 0.0, 0.0]
        )

        # Fusion with only original arm (should produce same ordering and scores)
        result_original_only = rrf_fuse(
            [original_results],
            k=60,
            weights=[1.0]
        )

        # Verify same ordering for docs in original
        ids_original = [r["id"] for r in result_original_only]
        ids_weighted = [r["id"] for r in result_weighted]
        # The weighted result includes doc_X and doc_Y with score 0, so ordering differs
        # But the top portion (docs from original) should match
        assert ids_original == [r["id"] for r in result_weighted if r["id"] in ids_original], (
            f"Top docs should match: got {ids_weighted}"
        )

        # Verify same scores for docs present in original
        for doc_id in ["doc_A", "doc_B", "doc_C"]:
            weighted_record = next(
                (r for r in result_weighted if r["id"] == doc_id),
                None
            )
            original_record = next(
                (r for r in result_original_only if r["id"] == doc_id),
                None
            )
            assert weighted_record is not None, f"Missing {doc_id} in weighted result"
            assert original_record is not None, f"Missing {doc_id} in original result"
            assert weighted_record["_rrf_score"] == original_record["_rrf_score"], (
                f"Scores mismatch for {doc_id}: {weighted_record['_rrf_score']} vs {original_record['_rrf_score']}"
            )

        # Verify docs only in zero-weighted arms have score 0
        doc_x_score = next(r["_rrf_score"] for r in result_weighted if r["id"] == "doc_X")
        doc_y_score = next(r["_rrf_score"] for r in result_weighted if r["id"] == "doc_Y")
        assert doc_x_score == 0.0, "Doc only in step-back (zero weight) should have score 0"
        assert doc_y_score == 0.0, "Doc only in HyDE (zero weight) should have score 0"

    def test_fusion_preserves_distance_and_rerank_score(self):
        """Fusion output records preserve _distance and _rerank_score fields.

        Input records have _distance and _rerank_score fields.
        After fusion, output records must preserve these fields on each record.
        Also verify _rrf_score is added.
        """
        result_lists = [
            [
                {
                    "id": "doc_A",
                    "text": "Doc A content",
                    "_distance": 0.15,
                    "_rerank_score": 0.95,
                },
                {
                    "id": "doc_B",
                    "text": "Doc B content",
                    "_distance": 0.35,
                    "_rerank_score": 0.72,
                },
            ],
            [
                {
                    "id": "doc_B",
                    "text": "Doc B content",
                    "_distance": 0.42,
                    "_rerank_score": 0.68,
                },
                {
                    "id": "doc_C",
                    "text": "Doc C content",
                    "_distance": 0.28,
                    "_rerank_score": 0.81,
                },
            ],
        ]

        result = rrf_fuse(result_lists, k=60)

        # Verify _rrf_score is added to all records
        for record in result:
            assert "_rrf_score" in record, f"Record {record['id']} missing _rrf_score"
            assert isinstance(record["_rrf_score"], float), (
                f"Record {record['id']} _rrf_score should be float"
            )

        # Verify _distance and _rerank_score are preserved for doc_A
        doc_a = next(r for r in result if r["id"] == "doc_A")
        assert "_distance" in doc_a, "doc_A missing _distance after fusion"
        assert doc_a["_distance"] == 0.15, "doc_A _distance not preserved"
        assert "_rerank_score" in doc_a, "doc_A missing _rerank_score after fusion"
        assert doc_a["_rerank_score"] == 0.95, "doc_A _rerank_score not preserved"

        # Verify _distance and _rerank_score are preserved for doc_B (from list 0)
        doc_b = next(r for r in result if r["id"] == "doc_B")
        assert "_distance" in doc_b, "doc_B missing _distance after fusion"
        assert doc_b["_distance"] == 0.35, "doc_B _distance should be from first list"
        assert "_rerank_score" in doc_b, "doc_B missing _rerank_score after fusion"
        assert doc_b["_rerank_score"] == 0.72, "doc_B _rerank_score should be from first list"

        # Verify doc_C from second list
        doc_c = next(r for r in result if r["id"] == "doc_C")
        assert "_distance" in doc_c, "doc_C missing _distance after fusion"
        assert doc_c["_distance"] == 0.28, "doc_C _distance not preserved"
        assert "_rerank_score" in doc_c, "doc_C missing _rerank_score after fusion"
        assert doc_c["_rerank_score"] == 0.81, "doc_C _rerank_score not preserved"

    def test_rrf_score_added_to_all_fused_records(self):
        """Every record in the fused output must have _rrf_score field."""
        result_lists = [
            [{"id": "a", "text": "a only"}],
            [{"id": "b", "text": "b only"}],
            [{"id": "c", "text": "c only"}],
        ]
        result = rrf_fuse(result_lists, k=60, weights=[1.0, 0.5, 2.0])

        assert len(result) == 3
        for record in result:
            assert "_rrf_score" in record
            assert record["_rrf_score"] >= 0.0

    def test_limit_applies_after_fusion(self):
        """limit parameter restricts output to top N results."""
        result_lists = [
            [{"id": f"doc_{i}", "text": f"Doc {i}"} for i in range(10)],
            [{"id": f"doc_{i}", "text": f"Doc {i}"} for i in range(5, 15)],
        ]
        result = rrf_fuse(result_lists, k=60, limit=5)

        assert len(result) == 5
        # Verify all 5 records have _rrf_score
        for record in result:
            assert "_rrf_score" in record
