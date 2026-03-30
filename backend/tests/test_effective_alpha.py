"""
Tests for effective_alpha computation in RAGEngine.query().

This module tests the per-request alpha computation:
1. When sparse embedding is None (tri_vector disabled or sparse fails) -> alpha=1.0
2. When sparse embedding succeeds -> alpha=self.hybrid_alpha
3. Settings.hybrid_alpha is never mutated
4. Engine.hybrid_alpha is never mutated
"""

import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestEffectiveAlpha(unittest.IsolatedAsyncioTestCase):
    """Test cases for effective_alpha computation in RAGEngine.query()."""

    def setUp(self):
        """Set up test fixtures."""
        # Store original settings values to verify no mutation
        self.original_alpha = None
        self.original_tri_vector = None

    def _create_mock_engine(self, hybrid_alpha=0.6):
        """Create a RAGEngine instance with mocked dependencies.

        Args:
            hybrid_alpha: The hybrid_alpha value to use for the engine

        Returns:
            Tuple of (engine, mock_vector_store, mock_llm_client, mock_memory_store)
        """
        from app.services.rag_engine import RAGEngine

        # Create mock embedding service
        mock_embedding_service = MagicMock()
        mock_embedding_service.embed_single = AsyncMock(return_value=[0.1, 0.2, 0.3])

        # Create mock vector store - returns empty results by default
        mock_vector_store = MagicMock()
        mock_vector_store.search = AsyncMock(return_value=[])
        mock_vector_store.is_connected = MagicMock(return_value=True)

        # Create mock LLM client
        mock_llm_client = MagicMock()
        mock_llm_client.chat_completion = AsyncMock(return_value="test response")
        mock_llm_client.chat_completion_stream = AsyncMock(return_value=iter([]))

        # Create mock memory store
        mock_memory_store = MagicMock()
        mock_memory_store.detect_memory_intent = MagicMock(return_value=None)
        mock_memory_store.search_memories = MagicMock(return_value=[])

        # Create mock document retrieval service
        mock_document_retrieval = MagicMock()
        mock_document_retrieval.filter_relevant = MagicMock(return_value=[])
        mock_document_retrieval.no_match = False

        # Create mock prompt builder
        mock_prompt_builder = MagicMock()
        mock_prompt_builder.build_messages = MagicMock(
            return_value=[{"role": "user", "content": "test"}]
        )

        # Create the engine with mocked dependencies
        engine = RAGEngine(
            embedding_service=mock_embedding_service,
            vector_store=mock_vector_store,
            memory_store=mock_memory_store,
            llm_client=mock_llm_client,
        )

        # Override hybrid_alpha
        engine.hybrid_alpha = hybrid_alpha

        # Override document_retrieval and prompt_builder
        engine.document_retrieval = mock_document_retrieval
        engine.prompt_builder = mock_prompt_builder

        return engine, mock_vector_store, mock_llm_client, mock_memory_store

    @pytest.mark.asyncio
    async def test_effective_alpha_1_when_sparse_is_none(self):
        """Test that effective_alpha=1.0 when query_sparse is None.

        When tri_vector_search_enabled=False (or sparse fails),
        query_sparse is None and alpha should be 1.0 (pure dense).
        """
        engine, mock_vector_store, mock_llm_client, mock_memory_store = (
            self._create_mock_engine(hybrid_alpha=0.6)
        )

        # Patch settings to disable tri_vector_search
        with patch("app.services.rag_engine.settings") as mock_settings:
            mock_settings.tri_vector_search_enabled = False
            mock_settings.query_transformation_enabled = False
            mock_settings.retrieval_top_k = 10
            mock_settings.hybrid_search_enabled = True
            mock_settings.retrieval_evaluation_enabled = False
            mock_settings.retrieval_recency_weight = 0.0
            mock_settings.context_max_tokens = 0
            mock_settings.reranking_enabled = False
            mock_settings.maintenance_mode = False

            # Execute the query - consume all results
            results = []
            async for chunk in engine.query("test query", [], stream=False):
                results.append(chunk)

        # Verify vector_store.search was called
        self.assertTrue(
            mock_vector_store.search.called,
            "vector_store.search should have been called",
        )

        # Get the hybrid_alpha argument passed to search
        call_kwargs = mock_vector_store.search.call_args
        actual_alpha = call_kwargs.kwargs.get("hybrid_alpha")

        # Verify effective_alpha=1.0 was passed
        self.assertEqual(
            actual_alpha,
            1.0,
            f"Expected effective_alpha=1.0 when sparse is None, got {actual_alpha}",
        )

    @pytest.mark.asyncio
    async def test_effective_alpha_uses_hybrid_alpha_when_sparse_succeeds(self):
        """Test that effective_alpha=self.hybrid_alpha when sparse embedding succeeds.

        When tri_vector_search_enabled=True and sparse embedding returns a dict,
        query_sparse is not None and alpha should be self.hybrid_alpha.
        """
        engine, mock_vector_store, mock_llm_client, mock_memory_store = (
            self._create_mock_engine(hybrid_alpha=0.7)
        )

        # Mock embed_query_sparse to return a valid sparse dict
        engine.embedding_service.embed_query_sparse = AsyncMock(
            return_value={"token1": 0.5, "token2": 0.3}
        )

        expected_alpha = 0.7  # Should match engine.hybrid_alpha

        with patch("app.services.rag_engine.settings") as mock_settings:
            mock_settings.tri_vector_search_enabled = True  # Enable tri-vector
            mock_settings.query_transformation_enabled = False
            mock_settings.retrieval_top_k = 10
            mock_settings.hybrid_search_enabled = True
            mock_settings.retrieval_evaluation_enabled = False
            mock_settings.retrieval_recency_weight = 0.0
            mock_settings.context_max_tokens = 0
            mock_settings.reranking_enabled = False
            mock_settings.maintenance_mode = False

            # Execute the query
            results = []
            async for chunk in engine.query("test query", [], stream=False):
                results.append(chunk)

        # Verify vector_store.search was called
        self.assertTrue(
            mock_vector_store.search.called,
            "vector_store.search should have been called",
        )

        # Get the hybrid_alpha argument passed to search
        call_kwargs = mock_vector_store.search.call_args
        actual_alpha = call_kwargs.kwargs.get("hybrid_alpha")

        # Verify effective_alpha=hybrid_alpha was passed
        self.assertEqual(
            actual_alpha,
            expected_alpha,
            f"Expected effective_alpha={expected_alpha} when sparse succeeds, got {actual_alpha}",
        )

    @pytest.mark.asyncio
    async def test_settings_hybrid_alpha_not_mutated(self):
        """Test that settings.hybrid_alpha is never mutated during query.

        This test verifies that even though we compute effective_alpha,
        the original settings.hybrid_alpha value remains unchanged.
        """
        from app.config import settings

        # Capture original value
        original_settings_alpha = settings.hybrid_alpha

        engine, mock_vector_store, mock_llm_client, mock_memory_store = (
            self._create_mock_engine(hybrid_alpha=0.55)
        )

        # Test with sparse disabled
        with patch("app.services.rag_engine.settings") as mock_settings:
            mock_settings.tri_vector_search_enabled = False
            mock_settings.query_transformation_enabled = False
            mock_settings.retrieval_top_k = 10
            mock_settings.hybrid_search_enabled = True
            mock_settings.retrieval_evaluation_enabled = False
            mock_settings.retrieval_recency_weight = 0.0
            mock_settings.context_max_tokens = 0
            mock_settings.reranking_enabled = False
            mock_settings.maintenance_mode = False

            async for _ in engine.query("test query", [], stream=False):
                pass

        # Verify settings.hybrid_alpha unchanged
        self.assertEqual(
            settings.hybrid_alpha,
            original_settings_alpha,
            f"settings.hybrid_alpha should not be mutated. Original: {original_settings_alpha}, After: {settings.hybrid_alpha}",
        )

    @pytest.mark.asyncio
    async def test_self_hybrid_alpha_not_mutated(self):
        """Test that engine.hybrid_alpha is never mutated during query.

        This test verifies that the engine's instance variable hybrid_alpha
        is not changed by the query execution.
        """
        engine, mock_vector_store, mock_llm_client, mock_memory_store = (
            self._create_mock_engine(hybrid_alpha=0.65)
        )

        original_engine_alpha = engine.hybrid_alpha

        # Test with sparse enabled and succeeding
        engine.embedding_service.embed_query_sparse = AsyncMock(
            return_value={"token1": 0.5}
        )

        with patch("app.services.rag_engine.settings") as mock_settings:
            mock_settings.tri_vector_search_enabled = True
            mock_settings.query_transformation_enabled = False
            mock_settings.retrieval_top_k = 10
            mock_settings.hybrid_search_enabled = True
            mock_settings.retrieval_evaluation_enabled = False
            mock_settings.retrieval_recency_weight = 0.0
            mock_settings.context_max_tokens = 0
            mock_settings.reranking_enabled = False
            mock_settings.maintenance_mode = False

            async for _ in engine.query("test query", [], stream=False):
                pass

        # Verify engine.hybrid_alpha unchanged
        self.assertEqual(
            engine.hybrid_alpha,
            original_engine_alpha,
            f"engine.hybrid_alpha should not be mutated. Original: {original_engine_alpha}, After: {engine.hybrid_alpha}",
        )

    @pytest.mark.asyncio
    async def test_sparse_failure_falls_back_to_alpha_1(self):
        """Test that sparse embedding failure results in effective_alpha=1.0.

        When embed_query_sparse raises an exception, query_sparse becomes None
        and effective_alpha should be 1.0 (pure dense fallback).
        """
        engine, mock_vector_store, mock_llm_client, mock_memory_store = (
            self._create_mock_engine(hybrid_alpha=0.8)
        )

        # Make embed_query_sparse raise an exception to simulate failure
        engine.embedding_service.embed_query_sparse = AsyncMock(
            side_effect=RuntimeError("Sparse service unavailable")
        )

        with patch("app.services.rag_engine.settings") as mock_settings:
            mock_settings.tri_vector_search_enabled = True  # Tri-vector enabled
            mock_settings.query_transformation_enabled = False
            mock_settings.retrieval_top_k = 10
            mock_settings.hybrid_search_enabled = True
            mock_settings.retrieval_evaluation_enabled = False
            mock_settings.retrieval_recency_weight = 0.0
            mock_settings.context_max_tokens = 0
            mock_settings.reranking_enabled = False
            mock_settings.maintenance_mode = False

            # Execute the query
            async for _ in engine.query("test query", [], stream=False):
                pass

        # Get the hybrid_alpha argument passed to search
        call_kwargs = mock_vector_store.search.call_args
        actual_alpha = call_kwargs.kwargs.get("hybrid_alpha")

        # Verify fallback to 1.0 when sparse fails
        self.assertEqual(
            actual_alpha,
            1.0,
            f"Expected effective_alpha=1.0 when sparse fails, got {actual_alpha}",
        )

    @pytest.mark.asyncio
    async def test_different_hybrid_alpha_values_preserved(self):
        """Test that different hybrid_alpha values are correctly passed through.

        Verify that the effective_alpha exactly matches engine.hybrid_alpha
        when sparse succeeds, not a hardcoded value.
        """
        # Test with a different hybrid_alpha value
        custom_alpha = 0.42
        engine, mock_vector_store, mock_llm_client, mock_memory_store = (
            self._create_mock_engine(hybrid_alpha=custom_alpha)
        )

        # Mock successful sparse embedding
        engine.embedding_service.embed_query_sparse = AsyncMock(
            return_value={"tokens": [1, 2, 3]}
        )

        with patch("app.services.rag_engine.settings") as mock_settings:
            mock_settings.tri_vector_search_enabled = True
            mock_settings.query_transformation_enabled = False
            mock_settings.retrieval_top_k = 10
            mock_settings.hybrid_search_enabled = True
            mock_settings.retrieval_evaluation_enabled = False
            mock_settings.retrieval_recency_weight = 0.0
            mock_settings.context_max_tokens = 0
            mock_settings.reranking_enabled = False
            mock_settings.maintenance_mode = False

            async for _ in engine.query("test query", [], stream=False):
                pass

        # Get the hybrid_alpha argument passed to search
        call_kwargs = mock_vector_store.search.call_args
        actual_alpha = call_kwargs.kwargs.get("hybrid_alpha")

        # Verify the exact custom_alpha was passed
        self.assertEqual(
            actual_alpha,
            custom_alpha,
            f"Expected effective_alpha={custom_alpha} to be preserved, got {actual_alpha}",
        )


if __name__ == "__main__":
    unittest.main()
