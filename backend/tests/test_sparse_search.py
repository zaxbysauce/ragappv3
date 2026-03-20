"""
Tests for _sparse_search() method in VectorStore.

This module tests the sparse vector dot-product similarity search:
1. Table is None returns empty list
2. Correct dot-product computation (verify _sparse_score values)
3. Results sorted by score descending
4. Limit parameter respected (returns top N)
5. JSON parse failure on sparse_embedding skipped gracefully
6. Missing sparse_embedding column (exception caught, returns [])
7. Vault filter applied correctly
8. Scale filter applied correctly
9. SQL injection prevention (vault_id with special characters)
10. Empty candidates returns empty list
"""

import asyncio
import json
import unittest
from unittest.mock import MagicMock, patch
import pytest

from app.services.vector_store import VectorStore


class TestSparseSearch(unittest.IsolatedAsyncioTestCase):
    """Test cases for _sparse_search method."""

    def setUp(self):
        """Set up test fixtures."""
        self.store = VectorStore.__new__(VectorStore)
        self.store.table = None

    def _create_mock_search_builder(self, results):
        """Create a mock search builder chain that returns given results."""
        mock_builder = MagicMock()
        mock_builder.where.return_value = mock_builder
        mock_builder.limit.return_value = mock_builder
        mock_builder.to_list.return_value = results
        return mock_builder

    # Test 1: Table is None returns empty list
    @pytest.mark.asyncio
    async def test_none_table_returns_empty_list(self):
        """Test that _sparse_search returns [] when self.table is None."""
        self.store.table = None

        result = await self.store._sparse_search(
            query_sparse={"term1": 0.5, "term2": 0.3},
            limit=10,
        )

        self.assertEqual(result, [])

    # Test 2: Correct dot-product computation
    @pytest.mark.asyncio
    async def test_dot_product_computation(self):
        """Test that _sparse_score is computed correctly as dot-product."""
        self.store.table = MagicMock()

        # Query sparse vector
        query_sparse = {"term1": 0.5, "term2": 0.8, "term3": 0.2}

        # Candidate with sparse_embedding JSON string
        # doc_sparse = {"term1": 0.6, "term2": 0.4, "term4": 0.9}
        # Expected score = 0.5*0.6 + 0.8*0.4 + 0.2*0.0 = 0.30 + 0.32 + 0.0 = 0.62
        doc_sparse = {"term1": 0.6, "term2": 0.4, "term4": 0.9}
        candidate = {
            "id": "doc1",
            "text": "sample text",
            "sparse_embedding": json.dumps(doc_sparse),
        }

        mock_builder = self._create_mock_search_builder([candidate])
        self.store.table.search.return_value = mock_builder

        with patch("app.services.vector_store.settings") as mock_settings:
            mock_settings.sparse_search_max_candidates = 1000

            result = await self.store._sparse_search(
                query_sparse=query_sparse,
                limit=10,
            )

        # Verify exact dot-product score
        expected_score = 0.5 * 0.6 + 0.8 * 0.4  # 0.62
        self.assertEqual(len(result), 1)
        self.assertAlmostEqual(result[0]["_sparse_score"], expected_score, places=6)

    # Test 3: Results sorted by score descending
    @pytest.mark.asyncio
    async def test_results_sorted_by_score_descending(self):
        """Test that results are sorted by _sparse_score in descending order."""
        self.store.table = MagicMock()

        query_sparse = {"term1": 1.0}

        # Create candidates with different scores
        candidates = [
            {"id": "low", "sparse_embedding": json.dumps({"term1": 0.3})},  # score 0.3
            {"id": "high", "sparse_embedding": json.dumps({"term1": 0.9})},  # score 0.9
            {"id": "mid", "sparse_embedding": json.dumps({"term1": 0.5})},  # score 0.5
        ]

        mock_builder = self._create_mock_search_builder(candidates)
        self.store.table.search.return_value = mock_builder

        with patch("app.services.vector_store.settings") as mock_settings:
            mock_settings.sparse_search_max_candidates = 1000

            result = await self.store._sparse_search(
                query_sparse=query_sparse,
                limit=10,
            )

        # Verify descending order: high, mid, low
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]["id"], "high")
        self.assertEqual(result[1]["id"], "mid")
        self.assertEqual(result[2]["id"], "low")
        # Verify scores are descending
        self.assertGreater(result[0]["_sparse_score"], result[1]["_sparse_score"])
        self.assertGreater(result[1]["_sparse_score"], result[2]["_sparse_score"])

    # Test 4: Limit parameter respected
    @pytest.mark.asyncio
    async def test_limit_parameter_respected(self):
        """Test that only top N results are returned based on limit."""
        self.store.table = MagicMock()

        query_sparse = {"term1": 1.0}

        # Create 5 candidates
        candidates = [
            {"id": f"doc{i}", "sparse_embedding": json.dumps({"term1": i * 0.1})}
            for i in range(1, 6)
        ]

        mock_builder = self._create_mock_search_builder(candidates)
        self.store.table.search.return_value = mock_builder

        with patch("app.services.vector_store.settings") as mock_settings:
            mock_settings.sparse_search_max_candidates = 1000

            result = await self.store._sparse_search(
                query_sparse=query_sparse,
                limit=2,  # Only return top 2
            )

        # Verify only 2 results returned
        self.assertEqual(len(result), 2)
        # Verify they are the top scoring ones (doc5=0.5, doc4=0.4)
        self.assertEqual(result[0]["id"], "doc5")
        self.assertEqual(result[1]["id"], "doc4")

    # Test 5: JSON parse failure skipped gracefully
    @pytest.mark.asyncio
    async def test_json_parse_failure_skipped_gracefully(self):
        """Test that malformed JSON in sparse_embedding is skipped without error."""
        self.store.table = MagicMock()

        query_sparse = {"term1": 1.0}

        candidates = [
            {"id": "valid", "sparse_embedding": json.dumps({"term1": 0.5})},
            {"id": "invalid_json", "sparse_embedding": "{not valid json"},
            {"id": "also_valid", "sparse_embedding": json.dumps({"term1": 0.3})},
        ]

        mock_builder = self._create_mock_search_builder(candidates)
        self.store.table.search.return_value = mock_builder

        with patch("app.services.vector_store.settings") as mock_settings:
            mock_settings.sparse_search_max_candidates = 1000

            result = await self.store._sparse_search(
                query_sparse=query_sparse,
                limit=10,
            )

        # Should only return 2 valid results
        self.assertEqual(len(result), 2)
        ids = [r["id"] for r in result]
        self.assertIn("valid", ids)
        self.assertIn("also_valid", ids)
        self.assertNotIn("invalid_json", ids)

    # Test 6: Missing sparse_embedding column (exception caught)
    @pytest.mark.asyncio
    async def test_missing_sparse_embedding_column_returns_empty(self):
        """Test that missing sparse_embedding column returns empty list."""
        self.store.table = MagicMock()

        # Make search() raise an exception (simulating missing column)
        self.store.table.search.side_effect = RuntimeError(
            "column 'sparse_embedding' does not exist"
        )

        with patch("app.services.vector_store.settings") as mock_settings:
            mock_settings.sparse_search_max_candidates = 1000

            result = await self.store._sparse_search(
                query_sparse={"term1": 1.0},
                limit=10,
            )

        # Should return empty list on exception
        self.assertEqual(result, [])

    # Test 7: Vault filter applied correctly
    @pytest.mark.asyncio
    async def test_vault_filter_applied(self):
        """Test that vault_id filter is correctly applied in the query."""
        self.store.table = MagicMock()

        query_sparse = {"term1": 1.0}
        vault_id = "my_vault_123"

        candidate = {"id": "doc1", "sparse_embedding": json.dumps({"term1": 0.5})}
        mock_builder = self._create_mock_search_builder([candidate])
        self.store.table.search.return_value = mock_builder

        with patch("app.services.vector_store.settings") as mock_settings:
            mock_settings.sparse_search_max_candidates = 1000

            await self.store._sparse_search(
                query_sparse=query_sparse,
                limit=10,
                vault_id=vault_id,
            )

        # Verify the filter was called with vault_id
        mock_builder.where.assert_called_once()
        filter_arg = mock_builder.where.call_args[0][0]
        self.assertIn("sparse_embedding IS NOT NULL", filter_arg)
        self.assertIn("vault_id = 'my_vault_123'", filter_arg)

    # Test 8: Scale filter applied correctly
    @pytest.mark.asyncio
    async def test_scale_filter_applied(self):
        """Test that scale (chunk_scale) filter is correctly applied."""
        self.store.table = MagicMock()

        query_sparse = {"term1": 1.0}
        scale = "large"

        candidate = {"id": "doc1", "sparse_embedding": json.dumps({"term1": 0.5})}
        mock_builder = self._create_mock_search_builder([candidate])
        self.store.table.search.return_value = mock_builder

        with patch("app.services.vector_store.settings") as mock_settings:
            mock_settings.sparse_search_max_candidates = 1000

            await self.store._sparse_search(
                query_sparse=query_sparse,
                limit=10,
                scale=scale,
            )

        # Verify the filter includes chunk_scale
        mock_builder.where.assert_called_once()
        filter_arg = mock_builder.where.call_args[0][0]
        self.assertIn("chunk_scale = 'large'", filter_arg)

    # Test 9: SQL injection prevention
    @pytest.mark.asyncio
    async def test_sql_injection_prevention_vault_id(self):
        """Test that SQL injection via vault_id is prevented (quote doubling)."""
        self.store.table = MagicMock()

        query_sparse = {"term1": 1.0}
        # Attempt SQL injection with single quote
        malicious_vault_id = "vault'; DROP TABLE chunks; --"

        candidate = {"id": "doc1", "sparse_embedding": json.dumps({"term1": 0.5})}
        mock_builder = self._create_mock_search_builder([candidate])
        self.store.table.search.return_value = mock_builder

        with patch("app.services.vector_store.settings") as mock_settings:
            mock_settings.sparse_search_max_candidates = 1000

            await self.store._sparse_search(
                query_sparse=query_sparse,
                limit=10,
                vault_id=malicious_vault_id,
            )

        # Verify the quote is escaped (doubled)
        mock_builder.where.assert_called_once()
        filter_arg = mock_builder.where.call_args[0][0]
        # Single quote should be doubled: "vault''; DROP TABLE..."
        self.assertIn("vault''; DROP TABLE", filter_arg)

    @pytest.mark.asyncio
    async def test_sql_injection_prevention_scale(self):
        """Test that SQL injection via scale is prevented (quote doubling)."""
        self.store.table = MagicMock()

        query_sparse = {"term1": 1.0}
        malicious_scale = "large'; DELETE FROM chunks; --"

        candidate = {"id": "doc1", "sparse_embedding": json.dumps({"term1": 0.5})}
        mock_builder = self._create_mock_search_builder([candidate])
        self.store.table.search.return_value = mock_builder

        with patch("app.services.vector_store.settings") as mock_settings:
            mock_settings.sparse_search_max_candidates = 1000

            await self.store._sparse_search(
                query_sparse=query_sparse,
                limit=10,
                scale=malicious_scale,
            )

        # Verify the quote is escaped
        mock_builder.where.assert_called_once()
        filter_arg = mock_builder.where.call_args[0][0]
        self.assertIn("large''; DELETE FROM", filter_arg)

    # Test 10: Empty candidates returns empty list
    @pytest.mark.asyncio
    async def test_empty_candidates_returns_empty_list(self):
        """Test that empty candidates list results in empty result."""
        self.store.table = MagicMock()

        query_sparse = {"term1": 1.0}

        # Return empty list from search
        mock_builder = self._create_mock_search_builder([])
        self.store.table.search.return_value = mock_builder

        with patch("app.services.vector_store.settings") as mock_settings:
            mock_settings.sparse_search_max_candidates = 1000

            result = await self.store._sparse_search(
                query_sparse=query_sparse,
                limit=10,
            )

        self.assertEqual(result, [])

    # Additional test: Missing sparse_embedding field in record
    @pytest.mark.asyncio
    async def test_missing_sparse_embedding_field_skipped(self):
        """Test that records without sparse_embedding field are skipped."""
        self.store.table = MagicMock()

        query_sparse = {"term1": 1.0}

        candidates = [
            {"id": "with_sparse", "sparse_embedding": json.dumps({"term1": 0.5})},
            {"id": "no_sparse_field"},  # Missing sparse_embedding
            {"id": "null_sparse", "sparse_embedding": None},
            {"id": "empty_sparse", "sparse_embedding": ""},
        ]

        mock_builder = self._create_mock_search_builder(candidates)
        self.store.table.search.return_value = mock_builder

        with patch("app.services.vector_store.settings") as mock_settings:
            mock_settings.sparse_search_max_candidates = 1000

            result = await self.store._sparse_search(
                query_sparse=query_sparse,
                limit=10,
            )

        # Should only return the valid one
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], "with_sparse")

    # Additional test: Custom filter_expr is appended
    @pytest.mark.asyncio
    async def test_custom_filter_expr_applied(self):
        """Test that custom filter_expr is included in the combined filter."""
        self.store.table = MagicMock()

        query_sparse = {"term1": 1.0}
        filter_expr = "metadata LIKE '%test%'"

        candidate = {"id": "doc1", "sparse_embedding": json.dumps({"term1": 0.5})}
        mock_builder = self._create_mock_search_builder([candidate])
        self.store.table.search.return_value = mock_builder

        with patch("app.services.vector_store.settings") as mock_settings:
            mock_settings.sparse_search_max_candidates = 1000

            await self.store._sparse_search(
                query_sparse=query_sparse,
                limit=10,
                filter_expr=filter_expr,
            )

        mock_builder.where.assert_called_once()
        filter_arg = mock_builder.where.call_args[0][0]
        self.assertIn("(metadata LIKE '%test%')", filter_arg)

    # Additional test: Combined filters (vault + scale + filter_expr)
    @pytest.mark.asyncio
    async def test_combined_filters(self):
        """Test that vault_id, scale, and filter_expr are all combined correctly."""
        self.store.table = MagicMock()

        query_sparse = {"term1": 1.0}

        candidate = {"id": "doc1", "sparse_embedding": json.dumps({"term1": 0.5})}
        mock_builder = self._create_mock_search_builder([candidate])
        self.store.table.search.return_value = mock_builder

        with patch("app.services.vector_store.settings") as mock_settings:
            mock_settings.sparse_search_max_candidates = 1000

            await self.store._sparse_search(
                query_sparse=query_sparse,
                limit=10,
                vault_id="vault1",
                scale="large",
                filter_expr="file_id = 'file123'",
            )

        mock_builder.where.assert_called_once()
        filter_arg = mock_builder.where.call_args[0][0]
        self.assertIn("sparse_embedding IS NOT NULL", filter_arg)
        self.assertIn("vault_id = 'vault1'", filter_arg)
        self.assertIn("chunk_scale = 'large'", filter_arg)
        self.assertIn("(file_id = 'file123')", filter_arg)
        # Verify they're joined with AND
        self.assertIn(" AND ", filter_arg)

    # Additional test: Sparse search max_candidates used
    @pytest.mark.asyncio
    async def test_max_candidates_setting_used(self):
        """Test that sparse_search_max_candidates setting is used for limit."""
        self.store.table = MagicMock()

        query_sparse = {"term1": 1.0}

        candidate = {"id": "doc1", "sparse_embedding": json.dumps({"term1": 0.5})}
        mock_builder = self._create_mock_search_builder([candidate])
        self.store.table.search.return_value = mock_builder

        with patch("app.services.vector_store.settings") as mock_settings:
            mock_settings.sparse_search_max_candidates = 500

            await self.store._sparse_search(
                query_sparse=query_sparse,
                limit=10,
            )

        # Verify limit was called with max_candidates value
        mock_builder.limit.assert_called_once_with(500)

    # Additional test: _sparse_score field added to result records
    @pytest.mark.asyncio
    async def test_sparse_score_field_added(self):
        """Test that _sparse_score field is added to each result record."""
        self.store.table = MagicMock()

        query_sparse = {"term1": 1.0, "term2": 0.5}

        doc_sparse = {"term1": 0.7, "term2": 0.3}
        expected_score = 1.0 * 0.7 + 0.5 * 0.3  # 0.85

        candidate = {
            "id": "doc1",
            "text": "test",
            "sparse_embedding": json.dumps(doc_sparse),
        }

        mock_builder = self._create_mock_search_builder([candidate])
        self.store.table.search.return_value = mock_builder

        with patch("app.services.vector_store.settings") as mock_settings:
            mock_settings.sparse_search_max_candidates = 1000

            result = await self.store._sparse_search(
                query_sparse=query_sparse,
                limit=10,
            )

        self.assertEqual(len(result), 1)
        self.assertIn("_sparse_score", result[0])
        self.assertAlmostEqual(result[0]["_sparse_score"], expected_score, places=6)


if __name__ == "__main__":
    unittest.main()
