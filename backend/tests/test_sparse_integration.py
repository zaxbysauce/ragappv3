"""Unit tests for sparse search integration in RAGEngine (task 3.7)."""

import os
import sys
import unittest
from typing import Dict, List, Optional, cast
from unittest.mock import AsyncMock, MagicMock, patch

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Note: Optional dependencies (lancedb, pyarrow, unstructured) are stubbed in conftest.py
# to prevent import errors when running tests.

from app.services.embeddings import EmbeddingService, EmbeddingError
from app.services.llm_client import LLMClient
from app.services.memory_store import MemoryRecord, MemoryStore
from app.services.rag_engine import RAGEngine
from app.services.vector_store import VectorStore


class FakeEmbeddingService:
    """Fake embedding service for testing."""

    def __init__(
        self,
        embedding: List[float],
        sparse_result: Optional[dict] = None,
        sparse_error: Optional[Exception] = None,
    ):
        self.embedding = embedding
        self.sparse_result = sparse_result
        self.sparse_error = sparse_error
        self.embed_query_sparse_called = False

    async def embed_single(self, text: str) -> List[float]:
        return self.embedding

    async def embed_query_sparse(self, text: str) -> dict:
        """Mock sparse embedding method."""
        self.embed_query_sparse_called = True
        if self.sparse_error:
            raise self.sparse_error
        return self.sparse_result or {"1": 0.5, "2": 0.3}


class FakeVectorStore:
    """Fake vector store for testing."""

    def __init__(self, results: List[Dict]):
        self._results = results
        self.is_connected = MagicMock(return_value=True)

    def search(
        self,
        embedding: List[float],
        limit: int = 10,
        filter_expr=None,
        vault_id=None,
        query_text=None,
        hybrid=None,
        hybrid_alpha=None,
    ):
        return self._results[:limit]

    def get_chunks_by_uid(self, chunk_uids: List[str]):
        return []


class FakeMemoryStore:
    """Fake memory store for testing."""

    def __init__(
        self,
        intent: Optional[str] = None,
        memories: Optional[List[MemoryRecord]] = None,
    ):
        self.intent = intent
        self._memories = memories or []
        self.added: List[str] = []

    def detect_memory_intent(self, text: str):
        return self.intent

    def add_memory(
        self, content: str, category=None, tags=None, source=None, vault_id=None
    ):
        self.added.append(content)
        return MemoryRecord(
            id=1,
            content=content,
            category=category,
            tags=tags,
            source=source,
            created_at=None,
            updated_at=None,
        )

    def search_memories(self, query: str, limit: int = 5, vault_id=None):
        return self._memories[:limit]


class FakeLLMClient:
    """Fake LLM client for testing."""

    def __init__(self, response: str):
        self._response = response

    async def chat_completion(self, messages):
        return self._response

    async def chat_completion_stream(self, messages):
        yield {"type": "content", "content": self._response}


class TestSparseSearchIntegration(unittest.IsolatedAsyncioTestCase):
    """Test suite for sparse search integration in RAGEngine."""

    async def test_sparse_enabled_generates_vector(self):
        """Test that sparse query vector is generated when tri_vector_search_enabled=True."""
        # Setup: create fake services with sparse enabled
        fake_embedding = FakeEmbeddingService(
            embedding=[0.1, 0.2], sparse_result={"10": 0.8, "20": 0.6}
        )
        vector_results = [
            {"text": "result", "file_id": "f1", "metadata": {}, "_distance": 0.1},
        ]

        # Patch settings to enable tri_vector_search
        with patch("app.services.rag_engine.settings") as mock_settings:
            # Set all required settings
            mock_settings.tri_vector_search_enabled = True
            mock_settings.query_transformation_enabled = False
            mock_settings.hybrid_search_enabled = False
            mock_settings.hybrid_alpha = 0.5
            mock_settings.reranking_enabled = False
            mock_settings.reranker_top_n = 3
            mock_settings.initial_retrieval_top_k = 10
            mock_settings.retrieval_top_k = 10
            mock_settings.context_max_tokens = 0
            mock_settings.retrieval_evaluation_enabled = False
            mock_settings.max_context_chunks = 5
            mock_settings.chunk_size_chars = 1200
            mock_settings.chunk_overlap_chars = 120
            mock_settings.vector_metric = "cosine"
            mock_settings.max_distance_threshold = 1.0
            mock_settings.embedding_doc_prefix = ""
            mock_settings.embedding_query_prefix = ""
            mock_settings.retrieval_window = 0
            mock_settings.rag_relevance_threshold = 0.5
            mock_settings.vector_top_k = 10
            mock_settings.maintenance_mode = False
            mock_settings.sqlite_path = ":memory:"

            # Create engine and inject fake services
            engine = RAGEngine()
            engine.embedding_service = cast(EmbeddingService, fake_embedding)
            engine.vector_store = cast(VectorStore, FakeVectorStore(vector_results))
            engine.memory_store = cast(MemoryStore, FakeMemoryStore())
            engine.llm_client = cast(LLMClient, FakeLLMClient(response="test response"))

            # Execute query
            results = [
                msg async for msg in engine.query("test query", [], stream=False)
            ]

            # Verify embed_query_sparse was called
            self.assertTrue(
                fake_embedding.embed_query_sparse_called,
                "embed_query_sparse should be called when tri_vector_search_enabled=True",
            )

            # Verify query completed (at least done message)
            done_messages = [m for m in results if m.get("type") == "done"]
            self.assertEqual(1, len(done_messages), "Should have a done message")

    async def test_sparse_enabled_embedding_fails_gracefully(self):
        """Test that sparse embedding failure falls back to None gracefully."""
        # Setup: create fake service that raises EmbeddingError
        fake_embedding = FakeEmbeddingService(
            embedding=[0.1, 0.2], sparse_error=EmbeddingError("Sparse embedding failed")
        )
        vector_results = [
            {"text": "result", "file_id": "f1", "metadata": {}, "_distance": 0.1},
        ]

        # Patch settings to enable tri_vector_search
        with patch("app.services.rag_engine.settings") as mock_settings:
            # Set all required settings
            mock_settings.tri_vector_search_enabled = True
            mock_settings.query_transformation_enabled = False
            mock_settings.hybrid_search_enabled = False
            mock_settings.hybrid_alpha = 0.5
            mock_settings.reranking_enabled = False
            mock_settings.reranker_top_n = 3
            mock_settings.initial_retrieval_top_k = 10
            mock_settings.retrieval_top_k = 10
            mock_settings.context_max_tokens = 0
            mock_settings.retrieval_evaluation_enabled = False
            mock_settings.max_context_chunks = 5
            mock_settings.chunk_size_chars = 1200
            mock_settings.chunk_overlap_chars = 120
            mock_settings.vector_metric = "cosine"
            mock_settings.max_distance_threshold = 1.0
            mock_settings.embedding_doc_prefix = ""
            mock_settings.embedding_query_prefix = ""
            mock_settings.retrieval_window = 0
            mock_settings.rag_relevance_threshold = 0.5
            mock_settings.vector_top_k = 10
            mock_settings.maintenance_mode = False
            mock_settings.sqlite_path = ":memory:"

            # Create engine and inject fake services
            engine = RAGEngine()
            engine.embedding_service = cast(EmbeddingService, fake_embedding)
            engine.vector_store = cast(VectorStore, FakeVectorStore(vector_results))
            engine.memory_store = cast(MemoryStore, FakeMemoryStore())
            engine.llm_client = cast(LLMClient, FakeLLMClient(response="test response"))

            # Execute query - should not raise, should fall back gracefully
            results = [
                msg async for msg in engine.query("test query", [], stream=False)
            ]

            # Verify embed_query_sparse was called (and failed)
            self.assertTrue(
                fake_embedding.embed_query_sparse_called,
                "embed_query_sparse should be called even when it fails",
            )

            # Verify query still completes (falls back gracefully)
            done_messages = [m for m in results if m.get("type") == "done"]
            self.assertEqual(
                1, len(done_messages), "Should still complete with done message"
            )

    async def test_sparse_disabled_no_generation(self):
        """Test that sparse query is NOT generated when tri_vector_search_enabled=False."""
        # Setup: fake embedding service with sparse result (should NOT be called)
        fake_embedding = FakeEmbeddingService(
            embedding=[0.1, 0.2], sparse_result={"10": 0.8, "20": 0.6}
        )
        vector_results = [
            {"text": "result", "file_id": "f1", "metadata": {}, "_distance": 0.1},
        ]

        # Patch settings to disable tri_vector_search
        with patch("app.services.rag_engine.settings") as mock_settings:
            # Set all required settings
            mock_settings.tri_vector_search_enabled = False
            mock_settings.query_transformation_enabled = False
            mock_settings.hybrid_search_enabled = False
            mock_settings.hybrid_alpha = 0.5
            mock_settings.reranking_enabled = False
            mock_settings.reranker_top_n = 3
            mock_settings.initial_retrieval_top_k = 10
            mock_settings.retrieval_top_k = 10
            mock_settings.context_max_tokens = 0
            mock_settings.retrieval_evaluation_enabled = False
            mock_settings.max_context_chunks = 5
            mock_settings.chunk_size_chars = 1200
            mock_settings.chunk_overlap_chars = 120
            mock_settings.vector_metric = "cosine"
            mock_settings.max_distance_threshold = 1.0
            mock_settings.embedding_doc_prefix = ""
            mock_settings.embedding_query_prefix = ""
            mock_settings.retrieval_window = 0
            mock_settings.rag_relevance_threshold = 0.5
            mock_settings.vector_top_k = 10
            mock_settings.maintenance_mode = False
            mock_settings.sqlite_path = ":memory:"

            # Create engine and inject fake services
            engine = RAGEngine()
            engine.embedding_service = cast(EmbeddingService, fake_embedding)
            engine.vector_store = cast(VectorStore, FakeVectorStore(vector_results))
            engine.memory_store = cast(MemoryStore, FakeMemoryStore())
            engine.llm_client = cast(LLMClient, FakeLLMClient(response="test response"))

            # Execute query
            results = [
                msg async for msg in engine.query("test query", [], stream=False)
            ]

            # Verify embed_query_sparse was NOT called
            self.assertFalse(
                fake_embedding.embed_query_sparse_called,
                "embed_query_sparse should NOT be called when tri_vector_search_enabled=False",
            )

            # Verify query completed normally
            done_messages = [m for m in results if m.get("type") == "done"]
            self.assertEqual(1, len(done_messages), "Should have a done message")

    async def test_sparse_passed_to_execute_retrieval(self):
        """Test that query_sparse is passed to _execute_retrieval method."""
        # Track what gets passed to _execute_retrieval
        retrieval_call_args = {}

        # Original _execute_retrieval wrapper
        original_execute_retrieval = RAGEngine._execute_retrieval

        async def mock_execute_retrieval(
            self, query_embeddings, user_input, vault_id, query_sparse=None
        ):
            # Capture the query_sparse argument
            retrieval_call_args["query_sparse"] = query_sparse
            retrieval_call_args["query_embeddings"] = query_embeddings
            # Call original method
            return await original_execute_retrieval(
                self, query_embeddings, user_input, vault_id, query_sparse
            )

        # Setup
        sparse_result = {"10": 0.8, "20": 0.6}
        fake_embedding = FakeEmbeddingService(
            embedding=[0.1, 0.2], sparse_result=sparse_result
        )
        vector_results = [
            {"text": "result", "file_id": "f1", "metadata": {}, "_distance": 0.1},
        ]

        with patch("app.services.rag_engine.settings") as mock_settings:
            # Set all required settings
            mock_settings.tri_vector_search_enabled = True
            mock_settings.query_transformation_enabled = False
            mock_settings.hybrid_search_enabled = False
            mock_settings.hybrid_alpha = 0.5
            mock_settings.reranking_enabled = False
            mock_settings.reranker_top_n = 3
            mock_settings.initial_retrieval_top_k = 10
            mock_settings.retrieval_top_k = 10
            mock_settings.context_max_tokens = 0
            mock_settings.retrieval_evaluation_enabled = False
            mock_settings.max_context_chunks = 5
            mock_settings.chunk_size_chars = 1200
            mock_settings.chunk_overlap_chars = 120
            mock_settings.vector_metric = "cosine"
            mock_settings.max_distance_threshold = 1.0
            mock_settings.embedding_doc_prefix = ""
            mock_settings.embedding_query_prefix = ""
            mock_settings.retrieval_window = 0
            mock_settings.rag_relevance_threshold = 0.5
            mock_settings.vector_top_k = 10
            mock_settings.maintenance_mode = False
            mock_settings.sqlite_path = ":memory:"

            # Create engine and inject fake services
            engine = RAGEngine()
            engine.embedding_service = cast(EmbeddingService, fake_embedding)
            engine.vector_store = cast(VectorStore, FakeVectorStore(vector_results))
            engine.memory_store = cast(MemoryStore, FakeMemoryStore())
            engine.llm_client = cast(LLMClient, FakeLLMClient(response="test response"))

            # Patch _execute_retrieval to capture arguments
            with patch.object(RAGEngine, "_execute_retrieval", mock_execute_retrieval):
                results = [
                    msg async for msg in engine.query("test query", [], stream=False)
                ]

            # Verify query_sparse was passed to _execute_retrieval
            self.assertIn(
                "query_sparse",
                retrieval_call_args,
                "query_sparse should be passed to _execute_retrieval",
            )
            self.assertIsNotNone(
                retrieval_call_args["query_sparse"],
                "query_sparse should not be None when tri_vector_search_enabled=True and sparse generation succeeds",
            )
            self.assertEqual(
                sparse_result,
                retrieval_call_args["query_sparse"],
                "query_sparse should equal the result from embed_query_sparse",
            )


if __name__ == "__main__":
    unittest.main()
