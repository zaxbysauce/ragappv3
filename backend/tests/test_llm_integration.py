"""
Unit tests for LLM integration services.

Tests EmbeddingService, ModelChecker, and LLMClient with mocked httpx.AsyncClient.
"""

import asyncio
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.services.embeddings import EmbeddingError, EmbeddingService
from app.services.llm_client import LLMClient, LLMError
from app.services.model_checker import ModelChecker


class TestEmbeddingService(unittest.TestCase):
    """Test cases for EmbeddingService."""

    def setUp(self):
        """Set up test fixtures."""
        self.settings_patcher = patch("app.services.embeddings.settings")
        self.mock_settings = self.settings_patcher.start()
        self.mock_settings.ollama_embedding_url = "http://localhost:11434"
        self.mock_settings.embedding_model = "nomic-embed-text"

    def tearDown(self):
        """Clean up test fixtures."""
        self.settings_patcher.stop()

    def test_embed_single_returns_embedding_list(self):
        """Test embed_single returns a list of floats on successful response."""
        async def run_test():
            service = EmbeddingService()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"embedding": [0.1, 0.2, 0.3]}
            mock_response.raise_for_status = MagicMock()

            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.post = AsyncMock(return_value=mock_response)

            with patch("httpx.AsyncClient", return_value=mock_client):
                result = await service.embed_single("test text")

            self.assertEqual(result, [0.1, 0.2, 0.3])
            mock_client.post.assert_called_once()
            call_args = mock_client.post.call_args
            self.assertEqual(call_args[0][0], "http://localhost:11434/api/embeddings")

        asyncio.run(run_test())

    def test_embed_single_handles_non_200_status(self):
        """Test embed_single raises EmbeddingError on non-200 status."""
        async def run_test():
            service = EmbeddingService()
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.text = "Internal Server Error"

            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.post = AsyncMock(return_value=mock_response)

            with patch("httpx.AsyncClient", return_value=mock_client):
                with self.assertRaises(EmbeddingError) as context:
                    await service.embed_single("test text")

            self.assertIn("500", str(context.exception))
            self.assertIn("Internal Server Error", str(context.exception))

        asyncio.run(run_test())

    def test_embed_single_handles_json_parse_error(self):
        """Test embed_single raises EmbeddingError on invalid JSON response."""
        async def run_test():
            service = EmbeddingService()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.side_effect = ValueError("Invalid JSON")
            mock_response.raise_for_status = MagicMock()

            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.post = AsyncMock(return_value=mock_response)

            with patch("httpx.AsyncClient", return_value=mock_client):
                with self.assertRaises(EmbeddingError) as context:
                    await service.embed_single("test text")

            self.assertIn("Invalid JSON", str(context.exception))

        asyncio.run(run_test())


class TestModelChecker(unittest.TestCase):
    """Test cases for ModelChecker."""

    def setUp(self):
        """Set up test fixtures."""
        self.settings_patcher = patch("app.services.model_checker.settings")
        self.mock_settings = self.settings_patcher.start()
        self.mock_settings.ollama_embedding_url = "http://localhost:11434"
        self.mock_settings.ollama_chat_url = "http://localhost:11434"
        self.mock_settings.embedding_model = "nomic-embed-text"
        self.mock_settings.chat_model = "qwen2.5:32b"

    def tearDown(self):
        """Clean up test fixtures."""
        self.settings_patcher.stop()

    def test_check_model_availability_available_model(self):
        """Test _check_model_availability returns available=True when model exists."""
        async def run_test():
            checker = ModelChecker()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "models": [
                    {"name": "nomic-embed-text:latest"},
                    {"name": "qwen2.5:32b"}
                ]
            }

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)

            result = await checker._check_model_availability(
                mock_client,
                "http://localhost:11434",
                "nomic-embed-text"
            )

            self.assertTrue(result["available"])
            self.assertIsNone(result["error"])
            mock_client.get.assert_called_once()
            call_args = mock_client.get.call_args
            self.assertEqual(call_args[0][0], "http://localhost:11434/api/tags")

        asyncio.run(run_test())

    def test_check_model_availability_missing_model(self):
        """Test _check_model_availability returns available=False when model not found."""
        async def run_test():
            checker = ModelChecker()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "models": [
                    {"name": "llama2:latest"},
                    {"name": "mistral:7b"}
                ]
            }

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)

            result = await checker._check_model_availability(
                mock_client,
                "http://localhost:11434",
                "nomic-embed-text"
            )

            self.assertFalse(result["available"])
            self.assertIn("not found", result["error"])
            self.assertIn("nomic-embed-text", result["error"])
            mock_client.get.assert_called_once()
            call_args = mock_client.get.call_args
            self.assertEqual(call_args[0][0], "http://localhost:11434/api/tags")

        asyncio.run(run_test())


class TestLLMClient(unittest.TestCase):
    """Test cases for LLMClient."""

    def setUp(self):
        """Set up test fixtures."""
        self.settings_patcher = patch("app.services.llm_client.settings")
        self.mock_settings = self.settings_patcher.start()
        self.mock_settings.ollama_chat_url = "http://localhost:11434"
        self.mock_settings.chat_model = "qwen2.5:32b"

    def tearDown(self):
        """Clean up test fixtures."""
        self.settings_patcher.stop()

    def test_chat_completion_extracts_content(self):
        """Test chat_completion extracts content from successful response."""
        async def run_test():
            # Create mock response
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "choices": [
                    {"message": {"content": "Hello, world!"}}
                ]
            }
            mock_response.raise_for_status = MagicMock()

            # Create mock client
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)

            # Create LLMClient and patch its _client
            client = LLMClient()
            client._client = mock_client

            messages = [{"role": "user", "content": "Hello"}]
            result = await client.chat_completion(messages)

            self.assertEqual(result, "Hello, world!")
            mock_client.post.assert_called_once()
            call_args = mock_client.post.call_args
            self.assertEqual(call_args[0][0], "http://localhost:11434/v1/chat/completions")
            self.assertEqual(call_args[1]["json"]["model"], "qwen2.5:32b")
            self.assertEqual(call_args[1]["json"]["messages"], messages)
            self.assertEqual(call_args[1]["json"]["stream"], False)
            self.assertEqual(call_args[1]["json"]["temperature"], 0.7)
            self.assertEqual(call_args[1]["json"]["max_tokens"], 2048)

        asyncio.run(run_test())

    def test_chat_completion_handles_non_200_status(self):
        """Test chat_completion raises LLMError on non-200 status."""
        async def run_test():
            # Create mock response with 503 status
            mock_response = MagicMock()
            mock_response.status_code = 503
            mock_response.text = "Service Unavailable"
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "Server error",
                request=MagicMock(),
                response=mock_response
            )

            # Create mock client
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)

            # Create LLMClient and patch its _client
            client = LLMClient()
            client._client = mock_client

            messages = [{"role": "user", "content": "Hello"}]

            with self.assertRaises(LLMError) as context:
                await client.chat_completion(messages)

            self.assertIn("503", str(context.exception))
            self.assertIn("Service Unavailable", str(context.exception))

        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()
