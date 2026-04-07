"""
Tests for EmbeddingService.embed_query_sparse method.
"""

import sys
import os
import asyncio

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Stub missing optional dependencies
try:
    import lancedb
except ImportError:
    import types

    sys.modules["lancedb"] = types.ModuleType("lancedb")

try:
    import pyarrow
except ImportError:
    import types

    sys.modules["pyarrow"] = types.ModuleType("pyarrow")

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx

from app.services.embeddings import EmbeddingService, EmbeddingError


@pytest.mark.asyncio
class TestEmbedQuerySparse:
    """Test suite for embed_query_sparse method."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test fixtures."""
        self.mock_settings_patcher = patch("app.services.embeddings.settings")
        self.mock_settings = self.mock_settings_patcher.start()

        # Configure mock settings
        self.mock_settings.ollama_embedding_url = (
            "http://localhost:11434/api/embeddings"
        )
        self.mock_settings.embedding_model = "nomic-embed-text"
        self.mock_settings.embedding_doc_prefix = ""
        self.mock_settings.embedding_query_prefix = ""
        self.mock_settings.embedding_batch_size = 512
        self.mock_settings.embedding_batch_max_retries = 3
        self.mock_settings.embedding_batch_min_sub_size = 1
        self.mock_settings.chunk_size_chars = 1200
        self.mock_settings.chunk_overlap_chars = 120
        self.mock_settings.tri_vector_search_enabled = True
        self.mock_settings.flag_embedding_url = "http://embedding-server:18080"

    @pytest.fixture(autouse=True)
    def teardown(self):
        """Tear down test fixtures."""
        yield
        self.mock_settings_patcher.stop()

    def _create_service_with_flag_url(
        self, flag_url: str = "http://embedding-server:18080"
    ) -> EmbeddingService:
        """Create EmbeddingService and set the flag_base_url directly."""
        service = EmbeddingService()
        service._flag_base_url = flag_url
        return service

    def _create_mock_response(self, sparse_data: dict, status_code: int = 200):
        """Create a mock HTTP response with sparse embedding data.

        sparse_data is the sparse token-weight dict (e.g. {"123": 0.5}),
        matching the production flag-embed-server response format.
        """
        response = MagicMock()
        response.status_code = status_code
        response.json.return_value = {
            "sparse_embeddings": [sparse_data],
            "dense_embeddings": None,
            "colbert_vecs": None,
        }
        response.raise_for_status = (
            MagicMock()
            if status_code == 200
            else MagicMock(
                side_effect=httpx.HTTPStatusError(
                    "Server Error", request=MagicMock(), response=response
                )
            )
        )
        return response

    async def test_sparse_embedding_success(self):
        """Test that sparse embedding returns sparse dict from API."""
        # Create service with flag URL set
        service = self._create_service_with_flag_url()

        # Mock the client
        mock_client = MagicMock()
        expected_sparse = {"123": 0.5, "456": 0.3, "789": 0.2}
        mock_client.post = AsyncMock(
            return_value=self._create_mock_response(expected_sparse)
        )

        service._client = mock_client

        # Call the method
        result = await service.embed_query_sparse("test query")

        # Verify the result
        assert result == expected_sparse
        assert isinstance(result, dict)

        # Verify the API was called with correct URL
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert "/embed" in call_args[0][0]

    async def test_sparse_embedding_timeout(self):
        """Test that asyncio.timeout raises EmbeddingError when request exceeds sparse_embedding_timeout."""
        service = self._create_service_with_flag_url()

        # Create a mock that takes longer than the configured timeout
        async def slow_post(*args, **kwargs):
            await asyncio.sleep(10)  # Much longer than any configured timeout
            return self._create_mock_response({"1": 0.5})

        mock_client = MagicMock()
        mock_client.post = slow_post

        service._client = mock_client

        # Should raise EmbeddingError due to timeout
        with pytest.raises(EmbeddingError) as context:
            await service.embed_query_sparse("test query")

        assert "timed out" in str(context.value).lower()

    async def test_sparse_embedding_no_flag_url(self):
        """Test that empty flag_embedding_url raises EmbeddingError."""
        service = self._create_service_with_flag_url(flag_url="")

        # Should raise EmbeddingError because _flag_base_url is empty
        with pytest.raises(EmbeddingError) as context:
            await service.embed_query_sparse("test query")

        assert (
            "flag" in str(context.value).lower()
            or "not configured" in str(context.value).lower()
        )

    async def test_sparse_embedding_missing_sparse_in_response(self):
        """Test that missing sparse in response raises EmbeddingError."""
        service = self._create_service_with_flag_url()

        # Mock response without sparse field
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=self._create_mock_response({}))

        service._client = mock_client

        # Should raise EmbeddingError
        with pytest.raises(EmbeddingError) as context:
            await service.embed_query_sparse("test query")

        assert "sparse" in str(context.value).lower()

    async def test_sparse_embedding_empty_results(self):
        """Test that empty results list raises EmbeddingError."""
        service = self._create_service_with_flag_url()

        # Mock response with empty results
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        service._client = mock_client

        # Should raise EmbeddingError
        with pytest.raises(EmbeddingError) as context:
            await service.embed_query_sparse("test query")

        assert "sparse" in str(context.value).lower()

    async def test_sparse_embedding_server_error(self):
        """Test that HTTP 500 raises EmbeddingError."""
        service = self._create_service_with_flag_url()

        # Mock response with 500 error
        mock_client = MagicMock()
        mock_client.post = AsyncMock(
            return_value=self._create_mock_response(
                {"1": 0.5}, status_code=500
            )
        )

        service._client = mock_client

        # Should raise EmbeddingError
        with pytest.raises(EmbeddingError):
            await service.embed_query_sparse("test query")

    async def test_sparse_embedding_applies_query_prefix(self):
        """Test that query prefix is prepended to the input text."""
        # Create service with a query prefix
        service = self._create_service_with_flag_url()
        service.embedding_query_prefix = "search: "

        captured_payload = None

        async def capture_post(*args, **kwargs):
            nonlocal captured_payload
            captured_payload = kwargs.get("json", args[1] if len(args) > 1 else {})
            return self._create_mock_response({"1": 0.5})

        mock_client = MagicMock()
        mock_client.post = capture_post

        service._client = mock_client

        # Call with a test query
        await service.embed_query_sparse("my search term")

        # Verify the prefix was applied
        assert captured_payload is not None
        assert "texts" in captured_payload
        input_text = captured_payload["texts"][0]
        assert input_text.startswith("search: ")
        assert "my search term" in input_text

    async def test_sparse_embedding_no_prefix(self):
        """Test that sparse embedding works without query prefix."""
        service = self._create_service_with_flag_url()
        service.embedding_query_prefix = ""

        captured_payload = None

        async def capture_post(*args, **kwargs):
            nonlocal captured_payload
            captured_payload = kwargs.get("json", args[1] if len(args) > 1 else {})
            return self._create_mock_response({"1": 0.5})

        mock_client = MagicMock()
        mock_client.post = capture_post

        service._client = mock_client

        # Call with a test query
        await service.embed_query_sparse("my search term")

        # Verify the prefix was NOT applied
        assert captured_payload is not None
        assert "texts" in captured_payload
        input_text = captured_payload["texts"][0]
        assert input_text == "my search term"

    async def test_sparse_embedding_uses_correct_endpoint(self):
        """Test that sparse embedding uses /embed endpoint (not /v1/embeddings)."""
        service = self._create_service_with_flag_url("http://embedding-server:18080")

        captured_url = None

        async def capture_post(url, **kwargs):
            nonlocal captured_url
            captured_url = url
            return self._create_mock_response({"1": 0.5})

        mock_client = MagicMock()
        mock_client.post = capture_post

        service._client = mock_client

        await service.embed_query_sparse("test")

        # Verify it uses /embed endpoint
        assert captured_url is not None
        assert "/embed" in captured_url
        assert "/v1/embeddings" not in captured_url
