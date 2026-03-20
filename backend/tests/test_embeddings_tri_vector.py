"""
Tests for tri-vector embedding service functionality.

Tests cover:
1. Async tri-vector detection via detect_tri_vector_support() method
2. URL parsing using urljoin() (security fix)
3. Client reuse in embed_multi() (resource management)
4. embed_multi() method returning tri-vectors
"""
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Stub missing optional dependencies
try:
    import lancedb
except ImportError:
    import types
    sys.modules['lancedb'] = types.ModuleType('lancedb')

try:
    import pyarrow
except ImportError:
    import types
    sys.modules['pyarrow'] = types.ModuleType('pyarrow')

import pytest
from unittest.mock import AsyncMock, patch, MagicMock, PropertyMock
from httpx import HTTPError
from urllib.parse import urljoin

from app.services.embeddings import EmbeddingService, EmbeddingError


@pytest.fixture
def mock_settings():
    """Fixture to mock settings for embedding service."""
    with patch('app.services.embeddings.settings') as mock:
        mock.ollama_embedding_url = "http://localhost:11434/api/embeddings"
        mock.embedding_model = "nomic-embed-text"
        mock.embedding_doc_prefix = ""
        mock.embedding_query_prefix = ""
        mock.embedding_batch_size = 512
        mock.embedding_batch_max_retries = 3
        mock.embedding_batch_min_sub_size = 1
        mock.chunk_size_chars = 1200
        mock.chunk_overlap_chars = 120
        mock.tri_vector_search_enabled = False
        mock.flag_embedding_url = None
        yield mock


class TestDetectTriVectorSupport:
    """Test suite for async tri-vector detection via detect_tri_vector_support() method."""

    def test_supports_tri_vector_returns_false_when_disabled(self, mock_settings):
        """Test that supports_tri_vector returns False when tri_vector_search_enabled=False."""
        mock_settings.tri_vector_search_enabled = False

        service = EmbeddingService()

        assert service.supports_tri_vector is False

    def test_supports_tri_vector_returns_false_when_no_flag_base_url(self, mock_settings):
        """Test that supports_tri_vector returns False when flag_base_url is not set."""
        mock_settings.tri_vector_search_enabled = True
        mock_settings.flag_embedding_url = None

        service = EmbeddingService()

        # Even with tri_vector enabled, if flag_base_url is None, should return False
        assert service.supports_tri_vector is False

    @pytest.mark.asyncio
    async def test_detect_tri_vector_support_triggers_on_first_access(self, mock_settings):
        """Test that detect_tri_vector_support triggers detection on first access."""
        mock_settings.tri_vector_search_enabled = True
        mock_settings.flag_embedding_url = "http://localhost:8000"

        service = EmbeddingService()

        with patch.object(service._client, 'get', new_callable=AsyncMock) as mock_get:
            # Mock successful detection
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"supports_sparse": True}
            mock_get.return_value = mock_response

            # First access should trigger detection
            result = await service.detect_tri_vector_support()

            assert result is True
            # Verify detection was called
            mock_get.assert_called_once()
            # Get the URL that was passed to client.get
            call_args = mock_get.call_args
            assert 'health' in call_args[0][0]

    @pytest.mark.asyncio
    async def test_detect_tri_vector_support_caches_result(self, mock_settings):
        """Test that detect_tri_vector_support caches the result after first detection."""
        mock_settings.tri_vector_search_enabled = True
        mock_settings.flag_embedding_url = "http://localhost:8000"

        service = EmbeddingService()

        with patch.object(service._client, 'get', new_callable=AsyncMock) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"supports_sparse": True}
            mock_get.return_value = mock_response

            # First access
            _ = await service.detect_tri_vector_support()
            first_call_count = mock_get.call_count

            # Second access should use cached value
            result = await service.detect_tri_vector_support()

            assert result is True
            # Detection should only be called once
            assert mock_get.call_count == first_call_count

    @pytest.mark.asyncio
    async def test_detect_tri_vector_support_returns_false_on_failure(self, mock_settings):
        """Test that detect_tri_vector_support returns False when detection fails."""
        mock_settings.tri_vector_search_enabled = True
        mock_settings.flag_embedding_url = "http://localhost:8000"

        service = EmbeddingService()

        with patch.object(service._client, 'get', new_callable=AsyncMock) as mock_get:
            # Mock httpx error (which is caught by the code)
            import httpx
            mock_get.side_effect = httpx.ConnectError("Connection refused")

            result = await service.detect_tri_vector_support()

            assert result is False

    @pytest.mark.asyncio
    async def test_detect_tri_vector_support_returns_false_when_sparse_false(self, mock_settings):
        """Test that detect_tri_vector_support returns False when server reports no sparse support."""
        mock_settings.tri_vector_search_enabled = True
        mock_settings.flag_embedding_url = "http://localhost:8000"

        service = EmbeddingService()

        with patch.object(service._client, 'get', new_callable=AsyncMock) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"supports_sparse": False}
            mock_get.return_value = mock_response

            result = await service.detect_tri_vector_support()

            assert result is False


class TestEmbedMultiFallback:
    """Test suite for embed_multi fallback behavior when tri-vector not supported."""

    @pytest.mark.asyncio
    async def test_embed_multi_falls_back_to_dense_only_when_not_supported(self, mock_settings):
        """Test that embed_multi falls back to dense-only when tri-vector not supported."""
        mock_settings.tri_vector_search_enabled = False
        
        service = EmbeddingService()
        
        # Mock the embed_batch method to return known embeddings
        mock_embeddings = [[0.1] * 768, [0.2] * 768]
        
        with patch.object(service, 'embed_batch', new_callable=AsyncMock) as mock_embed_batch:
            mock_embed_batch.return_value = mock_embeddings
            
            texts = ["text1", "text2"]
            result = await service.embed_multi(texts)
            
            # Verify embed_batch was called with the texts
            mock_embed_batch.assert_called_once_with(texts)
            
            # Verify result format
            assert len(result) == 2
            assert result[0]["dense"] == mock_embeddings[0]
            assert result[0]["sparse"] is None
            assert result[0]["colbert"] is None
            assert result[1]["dense"] == mock_embeddings[1]
            assert result[1]["sparse"] is None
            assert result[1]["colbert"] is None

    @pytest.mark.asyncio
    async def test_embed_multi_empty_input(self, mock_settings):
        """Test embed_multi with empty input list."""
        mock_settings.tri_vector_search_enabled = False
        
        service = EmbeddingService()
        
        with patch.object(service, 'embed_batch', new_callable=AsyncMock) as mock_embed_batch:
            mock_embed_batch.return_value = []
            
            result = await service.embed_multi([])
            
            assert result == []
            mock_embed_batch.assert_called_once_with([])


class TestURLConstructionSecurity:
    """Test suite for URL construction using urljoin (security fix)."""

    @pytest.mark.asyncio
    async def test_urljoin_used_for_health_endpoint(self, mock_settings):
        """Test that URL construction uses urljoin for health endpoint."""
        mock_settings.tri_vector_search_enabled = True
        mock_settings.flag_embedding_url = "http://localhost:8000"

        service = EmbeddingService()

        with patch.object(service._client, 'get', new_callable=AsyncMock) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"supports_sparse": True}
            mock_get.return_value = mock_response

            _ = await service.detect_tri_vector_support()

            # Verify URL was constructed correctly with urljoin
            call_args = mock_get.call_args
            called_url = call_args[0][0]

            # Should be http://localhost:8000/health (properly joined)
            assert called_url == "http://localhost:8000/health"

    @pytest.mark.asyncio
    async def test_urljoin_handles_trailing_slash(self, mock_settings):
        """Test that urljoin handles base URLs with trailing slash."""
        mock_settings.tri_vector_search_enabled = True
        mock_settings.flag_embedding_url = "http://localhost:8000/"

        service = EmbeddingService()

        with patch.object(service._client, 'get', new_callable=AsyncMock) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"supports_sparse": True}
            mock_get.return_value = mock_response

            _ = await service.detect_tri_vector_support()

            call_args = mock_get.call_args
            called_url = call_args[0][0]

            # urljoin should handle trailing slash correctly
            assert called_url == "http://localhost:8000/health"

    @pytest.mark.asyncio
    async def test_urljoin_used_for_embed_endpoint(self, mock_settings):
        """Test that embed_multi uses urljoin for /embed endpoint."""
        mock_settings.tri_vector_search_enabled = True
        mock_settings.flag_embedding_url = "http://localhost:8000"

        service = EmbeddingService()

        with patch.object(service._client, 'get', new_callable=AsyncMock) as mock_get:
            # Mock successful detection
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"supports_sparse": True}
            mock_get.return_value = mock_response

            _ = await service.detect_tri_vector_support()  # Trigger detection

        # Now test embed_multi with tri-vector support
        with patch.object(service._client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post_response = MagicMock()
            mock_post_response.raise_for_status = MagicMock()
            mock_post_response.json.return_value = [
                {"dense": [0.1] * 768, "sparse": {"indices": [1, 2], "values": [0.5, 0.3]}, "colbert": None}
            ]
            mock_post.return_value = mock_post_response

            texts = ["test text"]
            await service.embed_multi(texts)

            # Verify URL was constructed with urljoin
            call_args = mock_post.call_args
            called_url = call_args[0][0]

            # Should be http://localhost:8000/embed (properly joined)
            assert called_url == "http://localhost:8000/embed"

    def test_urljoin_prevents_path_traversal(self, mock_settings):
        """Test that urljoin prevents path traversal attacks."""
        # urljoin should normalize paths and prevent traversal
        base_url = "http://localhost:8000/api"
        
        # Test that urljoin handles various edge cases properly
        # Absolute path replaces the entire path
        health_url = urljoin(base_url, '/health')
        assert health_url == "http://localhost:8000/health"
        
        # Double slash handling with absolute path
        embed_url = urljoin(base_url + "/", '/embed')
        assert embed_url == "http://localhost:8000/embed"
        
        # Relative path appends to current path (expected behavior)
        relative_url = urljoin(base_url + "/", 'embed')
        assert relative_url == "http://localhost:8000/api/embed"
        
        # Security: urljoin properly handles URLs without path injection
        # Even if base_url has unexpected characters, urljoin normalizes
        safe_url = urljoin("http://localhost:8000", "/health")
        assert safe_url == "http://localhost:8000/health"
        
        # Verify path traversal attempt is neutralized by urljoin
        # An absolute path (/) replaces any path in the base
        traversal_attempt = urljoin("http://localhost:8000/../../etc/passwd", "/health")
        assert traversal_attempt == "http://localhost:8000/health"


class TestClientReuse:
    """Test suite for client reuse in embedding methods."""

    @pytest.mark.asyncio
    async def test_embed_single_uses_persistent_client(self, mock_settings):
        """Test that embed_single uses self._client (persistent client)."""
        service = EmbeddingService()
        
        # Get the client instance
        client = service._client
        
        # Mock the post method on the persistent client
        with patch.object(client, 'post', new_callable=AsyncMock) as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"embedding": [0.1] * 768}
            mock_post.return_value = mock_response
            
            result = await service.embed_single("test text")
            
            # Verify the persistent client's post was called
            mock_post.assert_called_once()
            assert result == [0.1] * 768

    @pytest.mark.asyncio
    async def test_embed_batch_uses_persistent_client(self, mock_settings):
        """Test that embed_batch uses self._client (persistent client)."""
        service = EmbeddingService()
        
        client = service._client
        
        with patch.object(client, 'post', new_callable=AsyncMock) as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"embeddings": [[0.1] * 768, [0.2] * 768]}
            mock_post.return_value = mock_response
            
            result = await service.embed_batch(["text1", "text2"])
            
            mock_post.assert_called_once()
            assert len(result) == 2

    @pytest.mark.asyncio
    async def test_embed_multi_uses_persistent_client_when_tri_vector_supported(self, mock_settings):
        """Test that embed_multi uses self._client when tri-vector is supported."""
        mock_settings.tri_vector_search_enabled = True
        mock_settings.flag_embedding_url = "http://localhost:8000"

        service = EmbeddingService()

        with patch.object(service._client, 'get', new_callable=AsyncMock) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"supports_sparse": True}
            mock_get.return_value = mock_response

            _ = await service.detect_tri_vector_support()

        client = service._client

        with patch.object(client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post_response = MagicMock()
            mock_post_response.raise_for_status = MagicMock()
            mock_post_response.json.return_value = [
                {"dense": [0.1] * 768, "sparse": {"indices": [1], "values": [0.5]}, "colbert": None}
            ]
            mock_post.return_value = mock_post_response

            result = await service.embed_multi(["test text"])

            mock_post.assert_called_once()

    @pytest.mark.asyncio
    async def test_all_methods_reuse_same_client_instance(self, mock_settings):
        """Test that embed_single, embed_batch, embed_multi all reuse self._client."""
        mock_settings.tri_vector_search_enabled = False
        
        service = EmbeddingService()
        
        # Capture the client reference
        original_client = service._client
        client_id = id(original_client)
        
        # Test embed_single
        with patch.object(original_client, 'post', new_callable=AsyncMock) as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"embedding": [0.1] * 768}
            mock_post.return_value = mock_response
            
            await service.embed_single("test")
        
        # Test embed_batch  
        with patch.object(original_client, 'post', new_callable=AsyncMock) as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"embeddings": [[0.1] * 768]}
            mock_post.return_value = mock_response
            
            await service.embed_batch(["test"])
        
        # Test embed_multi (falls back to embed_batch which uses same client)
        with patch.object(original_client, 'post', new_callable=AsyncMock) as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"embeddings": [[0.1] * 768]}
            mock_post.return_value = mock_response
            
            await service.embed_multi(["test"])
        
        # Verify the client is still the same instance
        assert id(service._client) == client_id

    def test_client_created_once_in_init(self, mock_settings):
        """Test that _client is created once during __init__."""
        service = EmbeddingService()
        
        # Client should be created and be an httpx.AsyncClient
        assert service._client is not None
        assert hasattr(service._client, 'post')
        assert hasattr(service._client, 'aclose')


class TestEmbedMultiTriVector:
    """Test suite for embed_multi returning tri-vectors."""

    @pytest.mark.asyncio
    async def test_embed_multi_returns_tri_vector_format(self, mock_settings):
        """Test that embed_multi returns tri-vector format when supported."""
        mock_settings.tri_vector_search_enabled = True
        mock_settings.flag_embedding_url = "http://localhost:8000"

        service = EmbeddingService()

        with patch.object(service._client, 'get', new_callable=AsyncMock) as mock_get:
            mock_detection_response = MagicMock()
            mock_detection_response.status_code = 200
            mock_detection_response.json.return_value = {"supports_sparse": True}
            mock_get.return_value = mock_detection_response

            _ = await service.detect_tri_vector_support()

        # Mock the tri-vector response
        expected_response = [
            {
                "dense": [0.1] * 768,
                "sparse": {"indices": [1, 5, 10], "values": [0.5, 0.3, 0.2]},
                "colbert": None
            },
            {
                "dense": [0.2] * 768,
                "sparse": {"indices": [2, 6, 11], "values": [0.4, 0.3, 0.3]},
                "colbert": None
            }
        ]
        
        with patch.object(service._client, 'post', new_callable=AsyncMock) as mock_post:
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = expected_response
            mock_post.return_value = mock_response
            
            texts = ["text1", "text2"]
            result = await service.embed_multi(texts)
            
            # Verify result format matches expected tri-vector format
            assert len(result) == 2
            assert result == expected_response
            
            # Verify each item has the expected keys
            for item in result:
                assert "dense" in item
                assert "sparse" in item
                assert "colbert" in item

    @pytest.mark.asyncio
    async def test_embed_multi_raises_on_error(self, mock_settings):
        """Test that embed_multi raises EmbeddingError on HTTP error."""
        mock_settings.tri_vector_search_enabled = True
        mock_settings.flag_embedding_url = "http://localhost:8000"

        service = EmbeddingService()

        with patch.object(service._client, 'get', new_callable=AsyncMock) as mock_get:
            mock_detection_response = MagicMock()
            mock_detection_response.status_code = 200
            mock_detection_response.json.return_value = {"supports_sparse": True}
            mock_get.return_value = mock_detection_response

            _ = await service.detect_tri_vector_support()

        with patch.object(service._client, 'post', new_callable=AsyncMock) as mock_post:
            # Mock httpx error (which triggers EmbeddingError conversion)
            import httpx
            mock_post.side_effect = httpx.ConnectError("Network error")

            with pytest.raises(EmbeddingError) as context:
                await service.embed_multi(["test"])

            assert "tri-vector" in str(context.value).lower()

    @pytest.mark.asyncio
    async def test_embed_multi_posts_to_embed_endpoint(self, mock_settings):
        """Test that embed_multi posts to the /embed endpoint with correct payload."""
        mock_settings.tri_vector_search_enabled = True
        mock_settings.flag_embedding_url = "http://localhost:8000"

        service = EmbeddingService()

        with patch.object(service._client, 'get', new_callable=AsyncMock) as mock_get:
            mock_detection_response = MagicMock()
            mock_detection_response.status_code = 200
            mock_detection_response.json.return_value = {"supports_sparse": True}
            mock_get.return_value = mock_detection_response

            _ = await service.detect_tri_vector_support()

        with patch.object(service._client, 'post', new_callable=AsyncMock) as mock_post:
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = [{"dense": [0.1] * 768, "sparse": None, "colbert": None}]
            mock_post.return_value = mock_response

            texts = ["hello world"]
            await service.embed_multi(texts)

            # Verify the request was made correctly
            call_args = mock_post.call_args
            called_url = call_args[0][0]
            called_json = call_args[1]['json']
            called_headers = call_args[1]['headers']

            assert "/embed" in called_url
            assert called_json == {"input": texts}
            assert called_headers["Content-Type"] == "application/json"


class TestEmbeddingServiceClose:
    """Test suite for proper cleanup via close method."""

    @pytest.mark.asyncio
    async def test_close_releases_client(self, mock_settings):
        """Test that close() properly releases the HTTP client."""
        service = EmbeddingService()
        
        # Verify client exists
        assert service._client is not None
        assert not service._client.is_closed
        
        # Close the service
        await service.close()
        
        # Verify client is closed
        assert service._client.is_closed

    @pytest.mark.asyncio
    async def test_close_is_idempotent(self, mock_settings):
        """Test that close() can be called multiple times safely."""
        service = EmbeddingService()
        
        await service.close()
        await service.close()  # Should not raise
        
        assert service._client.is_closed

    @pytest.mark.asyncio
    async def test_close_handles_missing_client(self, mock_settings):
        """Test that close() handles case where _client was never created."""
        service = EmbeddingService()
        # Manually delete the client to simulate init failure
        delattr(service, '_client')
        
        # Should not raise
        await service.close()
