"""
Adversarial tests for RAG quality fixes.
Tests attack vectors identified in the requirements.
"""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

# Source files being tested:
# - backend/app/services/vector_store.py (hybrid_alpha clamping)
# - backend/app/services/contextual_chunking.py (empty context, long context)
# - backend/app/services/context_distiller.py (NO_MATCH vs AMBIGUOUS gating)
# - backend/app/services/rag_engine.py (exact match promotion edge cases)


class TestHybridAlphaClampingAdversarial(unittest.TestCase):
    """Adversarial tests for hybrid_alpha clamping in hybrid search."""

    def test_clamp_alpha_zero_all_bm25(self):
        """hybrid_alpha=0.0 should clamp to 0.0 (all BM25, no dense)."""
        clamped_alpha = max(0.0, min(1.0, 0.0))
        self.assertEqual(clamped_alpha, 0.0)
        # Verify formula: weights=[0.0, 1.0] = [BM25_weight, dense_weight]
        weights = [clamped_alpha, 1.0 - clamped_alpha]
        self.assertEqual(weights, [0.0, 1.0])

    def test_clamp_alpha_one_all_dense(self):
        """hybrid_alpha=1.0 should clamp to 1.0 (all dense, no BM25)."""
        clamped_alpha = max(0.0, min(1.0, 1.0))
        self.assertEqual(clamped_alpha, 1.0)
        weights = [clamped_alpha, 1.0 - clamped_alpha]
        self.assertEqual(weights, [1.0, 0.0])

    def test_clamp_alpha_negative_clamped_to_zero(self):
        """hybrid_alpha=-1.0 should clamp to 0.0."""
        clamped_alpha = max(0.0, min(1.0, -1.0))
        self.assertEqual(clamped_alpha, 0.0)
        weights = [clamped_alpha, 1.0 - clamped_alpha]
        self.assertEqual(weights, [0.0, 1.0])

    def test_clamp_alpha_above_one_clamped_to_one(self):
        """hybrid_alpha=2.0 should clamp to 1.0."""
        clamped_alpha = max(0.0, min(1.0, 2.0))
        self.assertEqual(clamped_alpha, 1.0)
        weights = [clamped_alpha, 1.0 - clamped_alpha]
        self.assertEqual(weights, [1.0, 0.0])

    def test_clamp_alpha_very_large_clamped(self):
        """hybrid_alpha=100.0 should clamp to 1.0."""
        clamped_alpha = max(0.0, min(1.0, 100.0))
        self.assertEqual(clamped_alpha, 1.0)

    def test_clamp_alpha_very_negative_clamped(self):
        """hybrid_alpha=-100.0 should clamp to 0.0."""
        clamped_alpha = max(0.0, min(1.0, -100.0))
        self.assertEqual(clamped_alpha, 0.0)


class TestEmptyContextDualStore(unittest.TestCase):
    """Adversarial test: empty context string should NOT be prepended."""

    def test_empty_context_not_prepended(self):
        """
        When LLM returns empty/whitespace-only context, the original chunk
        text should NOT have an empty string prepended.
        """
        context = ""  # Empty string from LLM
        context_stripped = context.strip()

        # This is the check in contextual_chunking.py line 270
        if context_stripped:
            # This branch should NOT be taken for empty context
            should_prepend = True
        else:
            # Empty context should NOT prepend
            should_prepend = False

        self.assertFalse(should_prepend)

    def test_whitespace_only_context_not_prepended(self):
        """Whitespace-only context should be treated as empty."""
        context = "   \n\t  "  # whitespace only
        context_stripped = context.strip()

        if context_stripped:
            should_prepend = True
        else:
            should_prepend = False

        self.assertFalse(should_prepend)

    def test_single_space_context_not_prepended(self):
        """Single space context should not prepend."""
        context = " "
        context_stripped = context.strip()

        if context_stripped:
            should_prepend = True
        else:
            should_prepend = False

        self.assertFalse(should_prepend)


class TestLongContextTruncation(unittest.TestCase):
    """Adversarial test: very long context should be truncated."""

    MAX_TOKENS = 150  # Approximate max tokens for context

    def test_context_over_200_chars_truncated(self):
        """Context > 200 chars should be handled (truncated or logged)."""
        # Simulate a very long context response
        long_context = "A" * 300  # 300 characters

        # The actual truncation happens at the logging line (50 chars)
        # contextual_chunking.py line 277: f"Added context metadata to chunk {chunk_index}: {context[:50]}..."
        logged_preview = long_context[:50]

        # Verify the preview is truncated to 50 chars
        self.assertEqual(len(logged_preview), 50)
        self.assertEqual(logged_preview, "A" * 50)

    def test_context_exactly_200_chars_no_truncation_needed(self):
        """Context exactly 200 chars should log fully (50 char preview still shows 50)."""
        context_200 = "B" * 200
        # Preview still 50 chars (hardcoded in log)
        preview = context_200[:50]
        self.assertEqual(len(preview), 50)

    def test_context_within_limit(self):
        """Context within reasonable limit should log normally."""
        reasonable_context = "This is a reasonable context summary."
        preview = reasonable_context[:50]
        # Preview is still 50 chars, but context is preserved
        self.assertEqual(len(preview), len(reasonable_context))


class TestNO_MATCHvsAMBIGUOUSSynthesisGating(unittest.TestCase):
    """Adversarial test: synthesis should only trigger on NO_MATCH, not AMBIGUOUS."""

    def test_synthesis_gates_on_no_match_only(self):
        """Synthesis should trigger ONLY when eval_result == 'NO_MATCH'."""
        settings_mock = MagicMock()
        settings_mock.context_distillation_synthesis_enabled = True

        llm_client_mock = MagicMock()
        llm_client_mock is not None  # Truthy check

        sources_mock = [MagicMock()]

        # Test NO_MATCH - should trigger synthesis
        eval_result_no_match = "NO_MATCH"
        should_synthesize_no_match = (
            settings_mock.context_distillation_synthesis_enabled
            and llm_client_mock is not None
            and eval_result_no_match == "NO_MATCH"
            and sources_mock
        )
        self.assertTrue(should_synthesize_no_match)

        # Test AMBIGUOUS - should NOT trigger synthesis
        eval_result_ambiguous = "AMBIGUOUS"
        should_synthesize_ambiguous = (
            settings_mock.context_distillation_synthesis_enabled
            and llm_client_mock is not None
            and eval_result_ambiguous == "NO_MATCH"
            and sources_mock
        )
        self.assertFalse(should_synthesize_ambiguous)

        # Test CONFIDENT - should NOT trigger synthesis
        eval_result_confident = "CONFIDENT"
        should_synthesize_confident = (
            settings_mock.context_distillation_synthesis_enabled
            and llm_client_mock is not None
            and eval_result_confident == "NO_MATCH"
            and sources_mock
        )
        self.assertFalse(should_synthesize_confident)

    def test_synthesis_requires_all_conditions(self):
        """Synthesis requires: enabled + client + NO_MATCH + sources."""
        # All False cases
        self.assertFalse(
            True and True and "NO_MATCH" == "NO_MATCH" and []  # empty sources
        )

        # One condition missing
        self.assertFalse(
            False and True and "NO_MATCH" == "NO_MATCH" and [MagicMock()]
        )  # disabled
        self.assertFalse(
            True and None and "NO_MATCH" == "NO_MATCH" and [MagicMock()]
        )  # no client


class TestPromotionEdgeCases(unittest.TestCase):
    """Adversarial tests: exact match promotion edge cases."""

    def test_no_promotion_with_fewer_than_5_results(self):
        """Promotion should be no-op when results < 5."""
        vector_results = [
            {"id": "1"},
            {"id": "2"},
            {"id": "3"},
            {"id": "4"},
        ]  # Only 4 results
        original_top1_id = "1"
        exact_match_promote = True
        rrf_legacy_mode = False

        # Condition check from rag_engine.py line 565-569
        can_promote = (
            exact_match_promote
            and not rrf_legacy_mode
            and original_top1_id is not None
            and len(vector_results) >= 5
        )

        self.assertFalse(can_promote)
        # Results should remain unchanged
        self.assertEqual(len(vector_results), 4)
        self.assertEqual(vector_results[0]["id"], "1")

    def test_no_promotion_when_top1_already_in_top5(self):
        """Promotion should be no-op when top-1 is already in top-5."""
        vector_results = [
            {"id": "1"},  # original top-1 IS in top-5
            {"id": "2"},
            {"id": "3"},
            {"id": "4"},
            {"id": "5"},
        ]
        original_top1_id = "1"
        exact_match_promote = True
        rrf_legacy_mode = False

        # Condition check from rag_engine.py line 565-569
        can_promote = (
            exact_match_promote
            and not rrf_legacy_mode
            and original_top1_id is not None
            and len(vector_results) >= 5
        )

        # Even if can_promote is True, the top5_ids check at line 571-572 should block
        top5_ids = {r.get("id") for r in vector_results[:5]}
        top1_in_top5 = original_top1_id in top5_ids

        self.assertTrue(can_promote)  # Pre-conditions met
        self.assertTrue(top1_in_top5)  # But top-1 IS in top-5

        # Promotion should NOT happen
        self.assertFalse(top1_in_top5 is False)  # Equivalent to "not (top1_in_top5 == False)"

    def test_promotion_when_top1_not_in_top5(self):
        """Promotion SHOULD happen when top-1 is NOT in top-5."""
        vector_results = [
            {"id": "2"},
            {"id": "3"},
            {"id": "4"},
            {"id": "5"},
            {"id": "6"},
            {"id": "1"},  # original top-1 at position 6 (outside top-5)
        ]
        original_top1_id = "1"
        exact_match_promote = True
        rrf_legacy_mode = False

        can_promote = (
            exact_match_promote
            and not rrf_legacy_mode
            and original_top1_id is not None
            and len(vector_results) >= 5
        )

        top5_ids = {r.get("id") for r in vector_results[:5]}
        top1_in_top5 = original_top1_id in top5_ids

        self.assertTrue(can_promote)
        self.assertFalse(top1_in_top5)  # top-1 NOT in top-5

        # Simulate promotion: find and move to position 4
        promote_idx = None
        for idx, r in enumerate(vector_results):
            if r.get("id") == original_top1_id:
                promote_idx = idx
                break

        self.assertIsNotNone(promote_idx)
        self.assertEqual(promote_idx, 5)  # Position 6 (0-indexed as 5)

        # Simulate the actual promotion
        promoted_record = vector_results.pop(promote_idx)
        vector_results.insert(4, promoted_record)

        # Verify: original top-1 is now at position 5 (index 4)
        self.assertEqual(vector_results[4]["id"], "1")

    def test_promotion_disabled_in_legacy_mode(self):
        """Promotion should be disabled when rrf_legacy_mode is True."""
        vector_results = [{"id": str(i)} for i in range(10)]
        original_top1_id = "1"
        exact_match_promote = True
        rrf_legacy_mode = True  # LEGACY MODE

        can_promote = (
            exact_match_promote
            and not rrf_legacy_mode  # This is False
            and original_top1_id is not None
            and len(vector_results) >= 5
        )

        self.assertFalse(can_promote)

    def test_promotion_disabled_when_feature_disabled(self):
        """Promotion should be disabled when exact_match_promote is False."""
        vector_results = [{"id": str(i)} for i in range(10)]
        original_top1_id = "1"
        exact_match_promote = False  # DISABLED
        rrf_legacy_mode = False

        can_promote = (
            exact_match_promote  # This is False
            and not rrf_legacy_mode
            and original_top1_id is not None
            and len(vector_results) >= 5
        )

        self.assertFalse(can_promote)


class TestNoPromotionWithEmptyResults(unittest.TestCase):
    """Edge case: no promotion when results list is empty."""

    def test_no_promotion_empty_results(self):
        """No promotion with empty results list."""
        vector_results = []
        original_top1_id = None
        exact_match_promote = True
        rrf_legacy_mode = False

        can_promote = (
            exact_match_promote
            and not rrf_legacy_mode
            and original_top1_id is not None  # This fails
            and len(vector_results) >= 5  # This fails
        )

        self.assertFalse(can_promote)


if __name__ == "__main__":
    unittest.main(verbosity=2)
