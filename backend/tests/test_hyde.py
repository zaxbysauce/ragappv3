"""Tests for HyDE query transformation in query_transformer.py."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.query_transformer import QueryTransformer, _is_exact_or_document_query
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

        with patch("app.services.query_transformer.settings") as mock_settings:
            mock_settings.hyde_enabled = False
            mock_settings.stepback_enabled = True
            mock_settings.query_transform_temperature = 0.0
            mock_settings.redis_url = None
            mock_settings.chat_model = "test-model"
            transformer = QueryTransformer(mock_llm_client)
            result = await transformer.transform(
                "What is gradient descent in neural networks?"
            )

        # Should return exactly 2 variants (no HyDE)
        assert len(result) == 2
        assert result[0] == ("original", "What is gradient descent in neural networks?")
        assert result[1] == ("step_back", "What are the general concepts in machine learning?")

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

        with patch("app.services.query_transformer.settings") as mock_settings:
            mock_settings.hyde_enabled = True
            mock_settings.stepback_enabled = True
            mock_settings.query_transform_temperature = 0.0
            mock_settings.redis_url = None
            mock_settings.chat_model = "test-model"
            transformer = QueryTransformer(mock_llm_client)
            result = await transformer.transform(
                "What is gradient descent in neural networks?"
            )

        # Should return 3 variants including HyDE
        assert len(result) == 3
        assert result[0] == ("original", "What is gradient descent in neural networks?")
        assert result[1] == ("step_back", "What are the general concepts in machine learning?")
        # The third should be the HyDE passage
        assert result[2][0] == "hyde"
        assert "Gradient descent" in result[2][1]

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

        with patch("app.services.query_transformer.settings") as mock_settings:
            mock_settings.hyde_enabled = True
            mock_settings.stepback_enabled = True
            mock_settings.query_transform_temperature = 0.0
            mock_settings.redis_url = None
            mock_settings.chat_model = "test-model"
            transformer = QueryTransformer(mock_llm_client)
            result = await transformer.transform(
                "What is gradient descent in neural networks?"
            )

        # Should still return step_back (2 variants)
        assert len(result) == 2
        assert result[0] == ("original", "What is gradient descent in neural networks?")
        assert result[1] == ("step_back", "What are the general concepts in machine learning?")

    @pytest.mark.asyncio
    async def test_hyde_disabled_no_llm_call(self, mock_llm_client):
        """When hyde_enabled=False, generate_hyde is never called."""
        mock_llm_client.chat_completion = AsyncMock(
            return_value="Step back query response"
        )

        with patch("app.services.query_transformer.settings") as mock_settings:
            mock_settings.hyde_enabled = False
            mock_settings.stepback_enabled = True
            mock_settings.query_transform_temperature = 0.0
            mock_settings.redis_url = None
            mock_settings.chat_model = "test-model"
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

    @pytest.mark.asyncio
    async def test_transform_deterministic_with_zero_temp(self, mock_llm_client):
        """With temperature=0, same query produces identical results."""
        # Setup mock to return fixed text
        mock_llm_client.chat_completion = AsyncMock(
            return_value="What are the general concepts in machine learning?"
        )
        
        with patch("app.services.query_transformer.settings") as mock_settings:
            mock_settings.hyde_enabled = True
            mock_settings.stepback_enabled = True
            mock_settings.query_transform_temperature = 0.0
            mock_settings.redis_url = None
            mock_settings.chat_model = "test-model"
            mock_settings.hyde_enabled = False
            transformer = QueryTransformer(mock_llm_client)
            
            # Call transform 5 times
            results = []
            for _ in range(5):
                result = await transformer.transform("What is gradient descent?")
                results.append(result)
            
            # All results should be identical
            for r in results:
                assert r == results[0], "Transform should be deterministic with temperature=0"

    @pytest.mark.asyncio
    async def test_stepback_disabled_returns_original_only(self, mock_llm_client):
        """When stepback_enabled=False, transform returns [(original, ...)] only."""
        mock_llm_client.chat_completion = AsyncMock(
            return_value="General concepts in ML"
        )

        with patch("app.services.query_transformer.settings") as mock_settings:
            mock_settings.hyde_enabled = True
            mock_settings.stepback_enabled = False
            mock_settings.query_transform_temperature = 0.0
            mock_settings.redis_url = None
            mock_settings.chat_model = "test-model"
            transformer = QueryTransformer(mock_llm_client)
            result = await transformer.transform("What is gradient descent?")

        # Should return exactly 1 variant (original only)
        assert len(result) == 1
        assert result[0] == ("original", "What is gradient descent?")
        # LLM should not have been called
        assert mock_llm_client.chat_completion.call_count == 0

    @pytest.mark.asyncio
    async def test_transform_cache_hit_skips_llm(self, mock_llm_client):
        """Second call with same (model, type, query) should hit cache and skip LLM."""
        mock_llm_client.chat_completion = AsyncMock(
            return_value="What are the general concepts?"
        )

        with patch("app.services.query_transformer.settings") as mock_settings:
            mock_settings.hyde_enabled = True
            mock_settings.stepback_enabled = True
            mock_settings.query_transform_temperature = 0.0
            mock_settings.redis_url = None
            mock_settings.chat_model = "test-model"
            mock_settings.hyde_enabled = False
            transformer = QueryTransformer(mock_llm_client)
            
            # First call - should hit LLM
            result1 = await transformer.transform("What is gradient descent?")
            assert mock_llm_client.chat_completion.call_count == 1
            
            # Second call with same query - should hit cache
            result2 = await transformer.transform("What is gradient descent?")
            # LLM should NOT have been called again
            assert mock_llm_client.chat_completion.call_count == 1
            assert result1 == result2

    @pytest.mark.asyncio
    async def test_transform_different_query_different_cache_entry(self, mock_llm_client):
        """Different queries should produce different cache entries and call LLM for each."""
        mock_llm_client.chat_completion = AsyncMock(
            return_value="General concepts response"
        )

        with patch("app.services.query_transformer.settings") as mock_settings:
            mock_settings.hyde_enabled = True
            mock_settings.stepback_enabled = True
            mock_settings.query_transform_temperature = 0.0
            mock_settings.redis_url = None
            mock_settings.chat_model = "test-model"
            mock_settings.hyde_enabled = False
            transformer = QueryTransformer(mock_llm_client)
            
            # First query - should hit LLM
            result1 = await transformer.transform("What is gradient descent?")
            assert mock_llm_client.chat_completion.call_count == 1
            
            # Different query - should NOT use cache, should call LLM again
            result2 = await transformer.transform("What is backpropagation?")
            assert mock_llm_client.chat_completion.call_count == 2
            
            # Results should be different (different queries)
            assert result1 != result2

    @pytest.mark.asyncio
    async def test_transform_same_query_different_transformer_calls_llm_twice(self):
        """Each QueryTransformer instance has its own cache; same query on different instances calls LLM each time."""
        mock_settings = MagicMock()
        mock_settings.hyde_enabled = True
        mock_settings.stepback_enabled = True
        mock_settings.query_transform_temperature = 0.0
        mock_settings.redis_url = None
        mock_settings.chat_model = "test-model"
        mock_settings.hyde_enabled = False

        # Create two different LLM clients (simulating different models)
        mock_llm_client1 = MagicMock(spec=LLMClient)
        mock_llm_client1.chat_completion = AsyncMock(return_value="Response from model 1")
        
        mock_llm_client2 = MagicMock(spec=LLMClient)
        mock_llm_client2.chat_completion = AsyncMock(return_value="Response from model 2")

        with patch("app.services.query_transformer.settings", mock_settings):
            transformer1 = QueryTransformer(mock_llm_client1)
            transformer2 = QueryTransformer(mock_llm_client2)
            
            # Same query on transformer1 - should call LLM
            result1 = await transformer1.transform("What is gradient descent?")
            assert mock_llm_client1.chat_completion.call_count == 1
            
            # Same query on transformer2 (different model) - should call its own LLM
            # Note: Each transformer has its own cache, so transformer2 won't use transformer1's cache
            result2 = await transformer2.transform("What is gradient descent?")
            assert mock_llm_client2.chat_completion.call_count == 1
            
            # Results could be the same or different depending on LLM responses
            # But the important thing is each transformer called its own LLM


class TestIsExactOrDocumentQuery:
    """Tests for _is_exact_or_document_query function."""

    def test_quoted_phrase_returns_true(self):
        """Quoted exact phrase returns True."""
        assert _is_exact_or_document_query('Tell me about "machine learning"') is True

    def test_filename_pdf_returns_true(self):
        """Filename with .pdf extension returns True."""
        assert _is_exact_or_document_query("What is in report.pdf") is True

    def test_filename_yaml_returns_true(self):
        """Filename with .yaml extension returns True."""
        assert _is_exact_or_document_query("Check config.yaml for settings") is True

    def test_filename_csv_returns_true(self):
        """Filename with .csv extension returns True."""
        assert _is_exact_or_document_query("Read data.csv") is True

    def test_short_non_question_returns_true(self):
        """Short (3 words or fewer) non-question returns True."""
        assert _is_exact_or_document_query("Python tutorial") is True

    def test_normal_question_returns_false(self):
        """Normal question returns False."""
        assert _is_exact_or_document_query("What is gradient descent") is False

    def test_long_question_returns_false(self):
        """Long question returns False."""
        assert _is_exact_or_document_query("Can you explain how neural networks learn through backpropagation") is False

    def test_question_with_what_returns_false(self):
        """Question starting with 'What' returns False."""
        assert _is_exact_or_document_query("What is AI") is False

    def test_question_with_how_returns_false(self):
        """Question starting with 'How' returns False."""
        assert _is_exact_or_document_query("How does it work") is False
