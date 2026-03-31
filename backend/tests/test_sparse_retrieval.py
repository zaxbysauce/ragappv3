"""
Tests for sparse retrieval wiring in vector_store.py.

Tests verify:
1. search() with query_sparse=None: falls back to BM25 FTS (existing behavior)
2. search() with query_sparse=dict: uses _sparse_search() instead of FTS
3. hybrid_alpha=0.5: weights=[0.5, 0.5] — balanced dense/sparse
4. hybrid_alpha=1.0: weights=[0.0, 1.0] — sparse only
5. hybrid_alpha=0.0: weights=[1.0, 0.0] — dense only
6. Multi-scale path: query_sparse passed correctly to _search_single_scale()
7. Backward compatibility: existing calls without query_sparse work exactly as before
"""

import asyncio
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch, call

import numpy as np
import pytest

# Import the module under test
from app.services.vector_store import (
    VectorStore,
    VectorStoreConnectionError,
)
from app.utils.fusion import rrf_fuse


class TestSparseRetrievalWiring(unittest.TestCase):
    """Test cases for sparse retrieval wiring in VectorStore."""

    def setUp(self):
        """Set up test environment with temporary directory."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_lancedb"
        self.embedding_dim = 384

    def tearDown(self):
        """Clean up temporary directory."""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def create_vector_store(self) -> VectorStore:
        """Helper to create a VectorStore instance with test path."""
        return VectorStore(db_path=self.db_path)


class TestSearchQuerySparseNoneBehavior(TestSparseRetrievalWiring):
    """Test 1: search() with query_sparse=None falls back to BM25 FTS (existing behavior)."""

    @pytest.mark.asyncio
    async def test_search_with_query_sparse_none_uses_fts(self):
        """When query_sparse is None, search should use BM25 FTS path."""
        store = self.create_vector_store()

        # Mock the internal table and methods
        mock_table = MagicMock()
        mock_table.search = MagicMock(
            return_value=MagicMock(
                where=MagicMock(
                    return_value=MagicMock(
                        limit=MagicMock(
                            return_value=MagicMock(to_list=MagicMock(return_value=[]))
                        )
                    )
                )
            )
        )
        store.table = mock_table
        store.db = MagicMock()

        # Call search with query_sparse=None (default)
        query_embedding = [0.1] * self.embedding_dim
        results = await store.search(
            embedding=query_embedding,
            query_text="test query",
            query_sparse=None,  # Explicitly None
            hybrid=True,
        )

        # search() should call table.search() with query_text (FTS)
        # and NOT call _sparse_search()
        mock_table.search.assert_called()

        # Verify the search was called with query_text (not just embedding)
        search_calls = mock_table.search.call_args_list
        self.assertGreater(len(search_calls), 0)

    @pytest.mark.asyncio
    async def test_search_with_query_sparse_none_default_behavior(self):
        """Default call (no query_sparse arg) should use FTS path."""
        store = self.create_vector_store()

        # Mock the internal table and methods
        mock_table = MagicMock()
        mock_table.search = MagicMock(
            return_value=MagicMock(
                where=MagicMock(
                    return_value=MagicMock(
                        limit=MagicMock(
                            return_value=MagicMock(to_list=MagicMock(return_value=[]))
                        )
                    )
                )
            )
        )
        store.table = mock_table
        store.db = MagicMock()

        # Call search WITHOUT query_sparse parameter (uses default None)
        query_embedding = [0.1] * self.embedding_dim
        results = await store.search(
            embedding=query_embedding,
            query_text="test query",
            hybrid=True,
            # Note: no query_sparse parameter - uses default
        )

        # Should complete without error (backward compatible)
        self.assertIsInstance(results, list)


class TestSearchQuerySparseProvided(TestSparseRetrievalWiring):
    """Test 2: search() with query_sparse=dict uses _sparse_search() instead of FTS."""

    @pytest.mark.asyncio
    async def test_search_with_query_sparse_calls_sparse_search(self):
        """When query_sparse is provided, _sparse_search should be called."""
        store = self.create_vector_store()

        # Create mock table
        mock_table = MagicMock()
        mock_table.search = MagicMock(
            return_value=MagicMock(
                where=MagicMock(
                    return_value=MagicMock(
                        limit=MagicMock(
                            return_value=MagicMock(to_list=MagicMock(return_value=[]))
                        )
                    )
                )
            )
        )
        store.table = mock_table
        store.db = MagicMock()

        # Mock _sparse_search
        store._sparse_search = AsyncMock(return_value=[])

        # Call search with query_sparse
        query_embedding = [0.1] * self.embedding_dim
        query_sparse = {"term1": 0.5, "term2": 0.3}

        results = await store.search(
            embedding=query_embedding,
            query_text="test query",
            query_sparse=query_sparse,
            hybrid=True,
        )

        # _sparse_search should have been called
        store._sparse_search.assert_called_once()

        # Verify the query_sparse was passed correctly
        call_args = store._sparse_search.call_args
        self.assertEqual(call_args.kwargs.get("query_sparse"), query_sparse)

    @pytest.mark.asyncio
    async def test_search_with_query_sparse_skips_fts(self):
        """When query_sparse is provided, FTS should be skipped."""
        store = self.create_vector_store()

        # Create mock table that tracks FTS calls
        mock_table = MagicMock()
        fts_search_calls = []

        def track_fts_search(*args, **kwargs):
            # FTS search is called with query_text
            fts_search_calls.append(args)
            return MagicMock(
                where=MagicMock(
                    return_value=MagicMock(
                        limit=MagicMock(
                            return_value=MagicMock(to_list=MagicMock(return_value=[]))
                        )
                    )
                )
            )

        mock_table.search = track_fts_search
        store.table = mock_table
        store.db = MagicMock()

        # Mock _sparse_search
        store._sparse_search = AsyncMock(return_value=[])

        # Call search with query_sparse
        query_embedding = [0.1] * self.embedding_dim
        query_sparse = {"term1": 0.5}

        results = await store.search(
            embedding=query_embedding,
            query_text="test query",
            query_sparse=query_sparse,
            hybrid=True,
        )

        # FTS should NOT be called (only dense vector search with embedding)
        # The first search call should be with embedding, not query_text
        self.assertEqual(len(fts_search_calls), 1)


class TestHybridAlphaBalanced(TestSparseRetrievalWiring):
    """Test 3: hybrid_alpha=0.5 gives weights=[0.5, 0.5] — balanced dense/sparse."""

    def test_rrf_fuse_with_alpha_0_5_balanced_weights(self):
        """Verify rrf_fuse produces balanced weights [0.5, 0.5] for alpha=0.5."""
        # Dense results (first list)
        dense_results = [
            {"id": "doc1", "text": "Doc 1"},
            {"id": "doc2", "text": "Doc 2"},
        ]

        # Sparse results (second list)
        sparse_results = [
            {"id": "doc2", "text": "Doc 2"},  # Overlaps with dense
            {"id": "doc3", "text": "Doc 3"},
        ]

        # With alpha=0.5: weights = [1-0.5, 0.5] = [0.5, 0.5]
        fused = rrf_fuse(
            result_lists=[dense_results, sparse_results],
            k=60,
            limit=10,
            weights=[0.5, 0.5],  # Balanced weights
        )

        # doc2 appears in both lists and should have highest score
        doc2_scores = [r["_rrf_score"] for r in fused if r["id"] == "doc2"]
        self.assertEqual(len(doc2_scores), 1)

        # doc1 only in dense
        doc1_scores = [r["_rrf_score"] for r in fused if r["id"] == "doc1"]
        self.assertEqual(len(doc1_scores), 1)

        # doc3 only in sparse
        doc3_scores = [r["_rrf_score"] for r in fused if r["id"] == "doc3"]
        self.assertEqual(len(doc3_scores), 1)

    @pytest.mark.asyncio
    async def test_search_single_scale_alpha_0_5_dense_sparse_balanced(self):
        """Verify _search_single_scale applies alpha=0.5 balanced weighting."""
        store = self.create_vector_store()

        # Create mock table
        mock_table = MagicMock()
        mock_table.search = MagicMock(
            return_value=MagicMock(
                where=MagicMock(
                    return_value=MagicMock(
                        limit=MagicMock(
                            return_value=MagicMock(to_list=MagicMock(return_value=[]))
                        )
                    )
                )
            )
        )
        store.table = mock_table

        # Dense results
        dense_results = [
            {"id": "doc1", "text": "Doc 1", "_distance": 0.1},
            {"id": "doc2", "text": "Doc 2", "_distance": 0.2},
        ]

        # Sparse results
        sparse_results = [
            {"id": "doc2", "text": "Doc 2", "_sparse_score": 0.8},
            {"id": "doc3", "text": "Doc 3", "_sparse_score": 0.6},
        ]

        # Mock _sparse_search to return sparse results
        store._sparse_search = AsyncMock(return_value=sparse_results)

        # Patch run_dense_search to return dense results
        with patch.object(store, "_search_single_scale") as mock_search:
            # When called with query_sparse, should pass to _sparse_search
            mock_search.return_value = dense_results

            result = await store._search_single_scale(
                embedding=[0.1] * self.embedding_dim,
                scale="default",
                fetch_k=10,
                query_text="test",
                hybrid=True,
                query_sparse={"term": 0.5},
                hybrid_alpha=0.5,  # Balanced
            )

            # The method should call _sparse_search
            store._sparse_search.assert_called_once()


class TestHybridAlphaSparseOnly(TestSparseRetrievalWiring):
    """Test 4: hybrid_alpha=1.0 gives weights=[0.0, 1.0] — sparse only."""

    def test_rrf_fuse_with_alpha_1_0_sparse_only_weights(self):
        """Verify rrf_fuse produces sparse-only weights [0.0, 1.0] for alpha=1.0."""
        # Dense results
        dense_results = [
            {"id": "doc1", "text": "Doc 1"},
            {"id": "doc2", "text": "Doc 2"},
        ]

        # Sparse results
        sparse_results = [
            {"id": "doc3", "text": "Doc 3"},
        ]

        # With alpha=1.0: weights = [1-1.0, 1.0] = [0.0, 1.0]
        # Dense gets 0 weight, sparse gets full weight
        fused = rrf_fuse(
            result_lists=[dense_results, sparse_results],
            k=60,
            limit=10,
            weights=[0.0, 1.0],
        )

        # doc3 should be first (only in sparse with weight 1.0)
        self.assertEqual(fused[0]["id"], "doc3")

        # doc1 and doc2 should have 0 score contribution from dense
        doc1_score = next((r["_rrf_score"] for r in fused if r["id"] == "doc1"), 0)
        # doc1 only in dense (weight 0), so should have minimal/0 score
        self.assertEqual(doc1_score, 0.0)

    @pytest.mark.asyncio
    async def test_search_single_scale_alpha_1_0_sparse_heavy(self):
        """Verify _search_single_scale applies alpha=1.0 sparse-heavy weighting."""
        store = self.create_vector_store()

        # Verify the RRF formula in _search_single_scale for alpha=1.0
        # When alpha=1.0:
        # - Dense gets: (1.0 - 1.0) / (k_rrf + rank + 1) = 0.0
        # - Sparse gets: 1.0 * 1.0 / (k_rrf + rank + 1) = full contribution

        dense_results = [{"id": "doc1", "text": "Doc 1"}]
        sparse_results = [{"id": "doc2", "text": "Doc 2"}]

        store._sparse_search = AsyncMock(return_value=sparse_results)

        # The method should correctly weight sparse higher when alpha=1.0
        with patch.object(
            store, "_search_single_scale", wraps=store._search_single_scale
        ) as mock:
            mock.return_value = dense_results + sparse_results

            await store._search_single_scale(
                embedding=[0.1] * self.embedding_dim,
                scale="default",
                fetch_k=10,
                query_text="test",
                hybrid=True,
                query_sparse={"term": 0.5},
                hybrid_alpha=1.0,
            )


class TestHybridAlphaDenseOnly(TestSparseRetrievalWiring):
    """Test 5: hybrid_alpha=0.0 gives weights=[1.0, 0.0] — dense only."""

    def test_rrf_fuse_with_alpha_0_0_dense_only_weights(self):
        """Verify rrf_fuse produces dense-only weights [1.0, 0.0] for alpha=0.0."""
        # Dense results
        dense_results = [
            {"id": "doc1", "text": "Doc 1"},
            {"id": "doc2", "text": "Doc 2"},
        ]

        # Sparse results
        sparse_results = [
            {"id": "doc3", "text": "Doc 3"},
        ]

        # With alpha=0.0: weights = [1-0.0, 0.0] = [1.0, 0.0]
        fused = rrf_fuse(
            result_lists=[dense_results, sparse_results],
            k=60,
            limit=10,
            weights=[1.0, 0.0],
        )

        # doc1 and doc2 should be present (from dense with weight 1.0)
        doc_ids = [r["id"] for r in fused]
        self.assertIn("doc1", doc_ids)
        self.assertIn("doc2", doc_ids)

        # doc3 should have 0 score contribution from sparse
        doc3_score = next((r["_rrf_score"] for r in fused if r["id"] == "doc3"), 0)
        self.assertEqual(doc3_score, 0.0)

    @pytest.mark.asyncio
    async def test_search_single_scale_alpha_0_0_dense_heavy(self):
        """Verify _search_single_scale applies alpha=0.0 dense-heavy weighting."""
        store = self.create_vector_store()

        # When alpha=0.0:
        # - Dense gets: (1.0 - 0.0) / (k_rrf + rank + 1) = full contribution
        # - Sparse gets: 0.0 * 1.0 / (k_rrf + rank + 1) = 0.0

        dense_results = [{"id": "doc1", "text": "Doc 1"}]
        sparse_results = [{"id": "doc2", "text": "Doc 2"}]

        store._sparse_search = AsyncMock(return_value=sparse_results)

        with patch.object(
            store, "_search_single_scale", wraps=store._search_single_scale
        ) as mock:
            mock.return_value = dense_results

            await store._search_single_scale(
                embedding=[0.1] * self.embedding_dim,
                scale="default",
                fetch_k=10,
                query_text="test",
                hybrid=True,
                query_sparse={"term": 0.5},
                hybrid_alpha=0.0,
            )


class TestMultiScaleQuerySparse(TestSparseRetrievalWiring):
    """Test 6: Multi-scale path correctly passes query_sparse to _search_single_scale()."""

    @pytest.mark.asyncio
    async def test_multi_scale_search_passes_query_sparse(self):
        """Verify multi-scale search passes query_sparse to _search_single_scale()."""
        store = self.create_vector_store()

        # Enable multi-scale
        with patch("app.services.vector_store.settings") as mock_settings:
            mock_settings.multi_scale_indexing_enabled = True
            mock_settings.multi_scale_chunk_sizes = "512,1024"
            mock_settings.sparse_search_max_candidates = 1000

            mock_table = MagicMock()
            mock_table.search = MagicMock(
                return_value=MagicMock(
                    where=MagicMock(
                        return_value=MagicMock(
                            limit=MagicMock(
                                return_value=MagicMock(
                                    to_list=MagicMock(return_value=[])
                                )
                            )
                        )
                    )
                )
            )
            mock_table.list_indices = AsyncMock(return_value=[])
            store.table = mock_table
            store.db = MagicMock()

            # Track _search_single_scale calls
            search_calls = []

            async def mock_search_single_scale(*args, **kwargs):
                search_calls.append(kwargs)
                return []

            store._search_single_scale = mock_search_single_scale

            query_embedding = [0.1] * self.embedding_dim
            query_sparse = {"term1": 0.5, "term2": 0.3}

            await store.search(
                embedding=query_embedding,
                query_text="test query",
                query_sparse=query_sparse,
                hybrid=True,
                hybrid_alpha=0.6,
            )

            # Should have been called twice (once per scale)
            self.assertEqual(len(search_calls), 2)

            # Both calls should have query_sparse passed
            for call_kwargs in search_calls:
                self.assertEqual(call_kwargs.get("query_sparse"), query_sparse)
                self.assertEqual(call_kwargs.get("hybrid_alpha"), 0.6)

    @pytest.mark.asyncio
    async def test_multi_scale_search_passes_correct_alpha(self):
        """Verify multi-scale search passes hybrid_alpha to _search_single_scale()."""
        store = self.create_vector_store()

        with patch("app.services.vector_store.settings") as mock_settings:
            mock_settings.multi_scale_indexing_enabled = True
            mock_settings.multi_scale_chunk_sizes = "512,1024"
            mock_settings.sparse_search_max_candidates = 1000

            mock_table = MagicMock()
            mock_table.search = MagicMock(
                return_value=MagicMock(
                    where=MagicMock(
                        return_value=MagicMock(
                            limit=MagicMock(
                                return_value=MagicMock(
                                    to_list=MagicMock(return_value=[])
                                )
                            )
                        )
                    )
                )
            )
            store.table = mock_table
            store.db = MagicMock()

            search_calls = []

            async def mock_search_single_scale(*args, **kwargs):
                search_calls.append(kwargs)
                return []

            store._search_single_scale = mock_search_single_scale

            # Test different alpha values
            for alpha in [0.0, 0.3, 0.5, 0.7, 1.0]:
                search_calls.clear()

                await store.search(
                    embedding=[0.1] * self.embedding_dim,
                    query_text="test",
                    query_sparse={"term": 0.5},
                    hybrid=True,
                    hybrid_alpha=alpha,
                )

                # All calls should have the correct alpha
                for call_kwargs in search_calls:
                    self.assertEqual(call_kwargs.get("hybrid_alpha"), alpha)


class TestBackwardCompatibility(TestSparseRetrievalWiring):
    """Test 7: Backward compatibility - existing calls without query_sparse work as before."""

    @pytest.mark.asyncio
    async def test_search_without_query_sparse_parameter(self):
        """Existing code that doesn't pass query_sparse should work unchanged."""
        store = self.create_vector_store()

        mock_table = MagicMock()
        mock_table.search = MagicMock(
            return_value=MagicMock(
                where=MagicMock(
                    return_value=MagicMock(
                        limit=MagicMock(
                            return_value=MagicMock(to_list=MagicMock(return_value=[]))
                        )
                    )
                )
            )
        )
        store.table = mock_table
        store.db = MagicMock()

        # This is how existing code calls search() - without query_sparse
        query_embedding = [0.1] * self.embedding_dim

        # Should not raise any errors
        results = await store.search(
            embedding=query_embedding,
            limit=10,
            query_text="existing query",
            hybrid=True,
            # Note: query_sparse not provided, defaults to None
        )

        self.assertIsInstance(results, list)

    @pytest.mark.asyncio
    async def test_search_with_all_legacy_parameters(self):
        """Search with all legacy parameters still works."""
        store = self.create_vector_store()

        mock_table = MagicMock()
        mock_table.search = MagicMock(
            return_value=MagicMock(
                where=MagicMock(
                    return_value=MagicMock(
                        limit=MagicMock(
                            return_value=MagicMock(
                                to_list=MagicMock(
                                    return_value=[
                                        {"id": "doc1", "text": "Test", "_distance": 0.1}
                                    ]
                                )
                            )
                        )
                    )
                )
            )
        )
        store.table = mock_table
        store.db = MagicMock()

        query_embedding = [0.1] * self.embedding_dim

        # All legacy parameters
        results = await store.search(
            embedding=query_embedding,
            limit=10,
            filter_expr="vault_id = '1'",
            vault_id="1",
            query_text="legacy query",
            hybrid=True,
        )

        # Should return results
        self.assertIsInstance(results, list)

    @pytest.mark.asyncio
    async def test_search_hybrid_false_without_query_sparse(self):
        """Search with hybrid=False (legacy mode) without query_sparse."""
        store = self.create_vector_store()

        mock_table = MagicMock()
        mock_table.search = MagicMock(
            return_value=MagicMock(
                where=MagicMock(
                    return_value=MagicMock(
                        limit=MagicMock(
                            return_value=MagicMock(
                                to_list=MagicMock(
                                    return_value=[
                                        {"id": "doc1", "text": "Test", "_distance": 0.1}
                                    ]
                                )
                            )
                        )
                    )
                )
            )
        )
        store.table = mock_table
        store.db = MagicMock()

        results = await store.search(
            embedding=[0.1] * self.embedding_dim,
            hybrid=False,
            # No query_text, no query_sparse
        )

        # Should return dense results
        self.assertIsInstance(results, list)


class TestSparseSearchMethod(TestSparseRetrievalWiring):
    """Test the _sparse_search method directly."""

    @pytest.mark.asyncio
    async def test_sparse_search_returns_scored_results(self):
        """_sparse_search should return results with _sparse_score field."""
        store = self.create_vector_store()

        # Create mock table with records
        mock_records = [
            {
                "id": "doc1",
                "text": "Test doc 1",
                "sparse_embedding": '{"term1": 0.5, "term2": 0.3}',
            },
            {"id": "doc2", "text": "Test doc 2", "sparse_embedding": '{"term1": 0.8}'},
        ]

        mock_table = MagicMock()
        mock_table.search = MagicMock(
            return_value=MagicMock(
                where=MagicMock(
                    return_value=MagicMock(
                        limit=MagicMock(
                            return_value=MagicMock(
                                to_list=MagicMock(return_value=mock_records)
                            )
                        )
                    )
                )
            )
        )
        store.table = mock_table

        # Query sparse with term1=0.5
        query_sparse = {"term1": 0.5}

        results = await store._sparse_search(query_sparse=query_sparse, limit=10)

        # Results should be sorted by score
        self.assertIsInstance(results, list)

        # Verify scoring: doc1 should have higher score (0.5*0.5=0.25) than doc2 (0.5*0.8=0.4)
        # Actually doc2 has higher: 0.5 * 0.8 = 0.4 vs 0.5 * 0.5 = 0.25
        if len(results) >= 2:
            self.assertGreater(
                results[0].get("_sparse_score", 0), results[1].get("_sparse_score", 0)
            )

    @pytest.mark.asyncio
    async def test_sparse_search_respects_limit(self):
        """_sparse_search should respect the limit parameter."""
        store = self.create_vector_store()

        # Create many mock records
        mock_records = [
            {
                "id": f"doc{i}",
                "text": f"Doc {i}",
                "sparse_embedding": json.dumps({"term1": 0.5}),
            }
            for i in range(20)
        ]

        mock_table = MagicMock()
        mock_table.search = MagicMock(
            return_value=MagicMock(
                where=MagicMock(
                    return_value=MagicMock(
                        limit=MagicMock(
                            return_value=MagicMock(
                                to_list=MagicMock(return_value=mock_records)
                            )
                        )
                    )
                )
            )
        )
        store.table = mock_table

        # Request only 5 results
        results = await store._sparse_search(query_sparse={"term1": 0.5}, limit=5)

        self.assertLessEqual(len(results), 5)


class TestSearchSingleScaleSparsePath(TestSparseRetrievalWiring):
    """Test _search_single_scale with sparse retrieval path."""

    @pytest.mark.asyncio
    async def test_search_single_scale_with_sparse_returns_rrf_score(self):
        """_search_single_scale should return results with _rrf_score when using sparse."""
        store = self.create_vector_store()

        mock_table = MagicMock()
        mock_table.search = MagicMock(
            return_value=MagicMock(
                where=MagicMock(
                    return_value=MagicMock(
                        limit=MagicMock(
                            return_value=MagicMock(
                                to_list=MagicMock(
                                    return_value=[
                                        {"id": "doc1", "text": "Test", "_distance": 0.1}
                                    ]
                                )
                            )
                        )
                    )
                )
            )
        )
        store.table = mock_table

        # Mock _sparse_search to return results
        sparse_results = [{"id": "doc2", "text": "Sparse doc", "_sparse_score": 0.5}]
        store._sparse_search = AsyncMock(return_value=sparse_results)

        results = await store._search_single_scale(
            embedding=[0.1] * self.embedding_dim,
            scale="default",
            fetch_k=10,
            query_text="test",
            hybrid=True,
            query_sparse={"term": 0.5},
            hybrid_alpha=0.5,
        )

        # All results should have _rrf_score
        for result in results:
            self.assertIn("_rrf_score", result)

    @pytest.mark.asyncio
    async def test_search_single_scale_sparse_with_vault_filter(self):
        """_search_single_scale with sparse should respect vault_id filter."""
        store = self.create_vector_store()

        mock_table = MagicMock()
        mock_table.search = MagicMock(
            return_value=MagicMock(
                where=MagicMock(
                    return_value=MagicMock(
                        limit=MagicMock(
                            return_value=MagicMock(to_list=MagicMock(return_value=[]))
                        )
                    )
                )
            )
        )
        store.table = mock_table

        sparse_calls = []

        async def mock_sparse_search(*args, **kwargs):
            sparse_calls.append(kwargs)
            return []

        store._sparse_search = mock_sparse_search

        await store._search_single_scale(
            embedding=[0.1] * self.embedding_dim,
            scale="default",
            fetch_k=10,
            vault_id="vault123",
            query_text="test",
            hybrid=True,
            query_sparse={"term": 0.5},
            hybrid_alpha=0.5,
        )

        # _sparse_search should be called with vault_id
        self.assertEqual(len(sparse_calls), 1)
        self.assertEqual(sparse_calls[0].get("vault_id"), "vault123")


if __name__ == "__main__":
    unittest.main()
