"""Tests for HyDE query transformation in query_transformer.py."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.query_transformer import QueryTransformer
from app.services.llm_client import LLMClient


class TestHyDE:
    """Tests for HyDE (Hypothetical Document Embeddings) feature."""

    @pytest.fixture
    def mock_llm_client(self):
        """Create a mock LLM client."""
        return MagicMock(spec=LLMClient)

    @pytest.mark.asyncio
    async def test_hyde_disabled_returns_step_back_only(self, mock_llm_client):
        """When hyde_enabled=False, transform returns [original, step_back] only."""
        # Setup mock for step-back
        mock_llm_client.chat_completion = AsyncMock(
            return_value="What are the general concepts in machine learning?"
        )

        with patch("app.config.settings") as mock_settings:
            mock_settings.hyde_enabled = False
            transformer = QueryTransformer(mock_llm_client)
            result = await transformer.transform(
                "What is gradient descent in neural networks?"
            )

        # Should return exactly 2 variants (no HyDE)
        assert len(result) == 2
        assert result[0] == "What is gradient descent in neural networks?"
        assert result[1] == "What are the general concepts in machine learning?"

    @pytest.mark.asyncio
    async def test_hyde_enabled_appends_passage(self, mock_llm_client):
        """When hyde_enabled=True, transform returns [original, step_back, hyde]."""
        # Setup mocks
        mock_llm_client.chat_completion = AsyncMock(
            side_effect=[
                # First call: step-back
                "What are the general concepts in machine learning?",
                # Second call: HyDE passage
                "Gradient descent is an optimization algorithm used to minimize loss functions in machine learning by iteratively moving toward the steepest descent direction.",
            ]
        )

        with patch("app.config.settings") as mock_settings:
            mock_settings.hyde_enabled = True
            transformer = QueryTransformer(mock_llm_client)
            result = await transformer.transform(
                "What is gradient descent in neural networks?"
            )

        # Should return 3 variants including HyDE
        assert len(result) == 3
        assert result[0] == "What is gradient descent in neural networks?"
        assert result[1] == "What are the general concepts in machine learning?"
        # The third should be the HyDE passage
        assert "Gradient descent" in result[2]

    @pytest.mark.asyncio
    async def test_hyde_generation_returns_passage(self, mock_llm_client):
        """Successful LLM call returns the passage string."""
        hyde_response = "Gradient descent is an optimization algorithm used to minimize loss functions in machine learning by iteratively moving toward the steepest descent direction."

        mock_llm_client.chat_completion = AsyncMock(return_value=hyde_response)

        transformer = QueryTransformer(mock_llm_client)
        result = await transformer.generate_hyde("What is gradient descent?")

        assert result == hyde_response
        assert len(result) >= 20

    @pytest.mark.asyncio
    async def test_hyde_generation_short_response(self, mock_llm_client):
        """Response shorter than 20 chars returns None."""
        # Short response (less than 20 chars)
        mock_llm_client.chat_completion = AsyncMock(return_value="Short.")

        transformer = QueryTransformer(mock_llm_client)
        result = await transformer.generate_hyde("What is AI?")

        assert result is None

    @pytest.mark.asyncio
    async def test_hyde_generation_llm_error(self, mock_llm_client):
        """LLM exception returns None."""
        mock_llm_client.chat_completion = AsyncMock(side_effect=Exception("API error"))

        transformer = QueryTransformer(mock_llm_client)
        result = await transformer.generate_hyde("What is gradient descent?")

        assert result is None

    @pytest.mark.asyncio
    async def test_hyde_failure_doesnt_break_step_back(self, mock_llm_client):
        """When HyDE fails, transform still returns [original, step_back]."""
        # First call succeeds (step-back), second fails (HyDE)
        mock_llm_client.chat_completion = AsyncMock(
            side_effect=[
                "What are the general concepts in machine learning?",  # step-back succeeds
                Exception("HyDE API error"),  # HyDE fails
            ]
        )

        with patch("app.config.settings") as mock_settings:
            mock_settings.hyde_enabled = True
            transformer = QueryTransformer(mock_llm_client)
            result = await transformer.transform(
                "What is gradient descent in neural networks?"
            )

        # Should still return step_back (2 variants)
        assert len(result) == 2
        assert result[0] == "What is gradient descent in neural networks?"
        assert result[1] == "What are the general concepts in machine learning?"

    @pytest.mark.asyncio
    async def test_hyde_disabled_no_llm_call(self, mock_llm_client):
        """When hyde_enabled=False, generate_hyde is never called."""
        mock_llm_client.chat_completion = AsyncMock(
            return_value="Step back query response"
        )

        with patch("app.config.settings") as mock_settings:
            mock_settings.hyde_enabled = False
            transformer = QueryTransformer(mock_llm_client)
            result = await transformer.transform("What is gradient descent?")

        # Only one call should have been made (step-back only)
        assert mock_llm_client.chat_completion.call_count == 1
        # Verify the call was for step-back, not HyDE
        call_args = mock_llm_client.chat_completion.call_args
        messages = call_args.kwargs.get("messages", [])
        # Step-back prompt contains "Step-back:"
        assert any(
            "Step-back:" in msg.get("content", "")
            for msg in messages
            if isinstance(msg, dict)
        )
