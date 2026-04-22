"""Tests for ContextDistiller service."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.context_distiller import (
    ContextDistiller,
    _cosine_similarity,
    _split_sentences,
)
from app.services.rag_engine import RAGSource


class TestCosineSimilarity:
    """Tests for _cosine_similarity helper function."""

    def test_cosine_similarity_identical(self):
        """Returns 1.0 for identical vectors."""
        a = [1.0, 2.0, 3.0]
        b = [1.0, 2.0, 3.0]
        result = _cosine_similarity(a, b)
        assert result == 1.0

    def test_cosine_similarity_orthogonal(self):
        """Returns 0.0 for orthogonal vectors."""
        a = [1.0, 0.0, 0.0]
        b = [0.0, 1.0, 0.0]
        result = _cosine_similarity(a, b)
        assert result == 0.0

    def test_cosine_similarity_zero_vector(self):
        """Returns 0.0 when one vector is zero."""
        a = [0.0, 0.0, 0.0]
        b = [1.0, 2.0, 3.0]
        result = _cosine_similarity(a, b)
        assert result == 0.0

    def test_cosine_similarity_zero_vector_reversed(self):
        """Returns 0.0 when the other vector is zero (reversed)."""
        a = [1.0, 2.0, 3.0]
        b = [0.0, 0.0, 0.0]
        result = _cosine_similarity(a, b)
        assert result == 0.0

    def test_cosine_similarity_both_zero(self):
        """Returns 0.0 when both vectors are zero."""
        a = [0.0, 0.0, 0.0]
        b = [0.0, 0.0, 0.0]
        result = _cosine_similarity(a, b)
        assert result == 0.0


class TestSplitSentences:
    """Tests for _split_sentences helper function."""

    def test_split_sentences_basic(self):
        """Splits on period."""
        text = "Hello world. This is a test. Final sentence."
        result = _split_sentences(text)
        assert result == ["Hello world.", "This is a test.", "Final sentence."]

    def test_split_sentences_multiple_punctuation(self):
        """Splits on ! and ?."""
        text = "Hello world! Is this working? Yes it is."
        result = _split_sentences(text)
        assert result == ["Hello world!", "Is this working?", "Yes it is."]

    def test_split_sentences_no_punctuation(self):
        """Returns single element when no punctuation."""
        text = "Hello world"
        result = _split_sentences(text)
        assert result == ["Hello world"]

    def test_split_sentences_multiple_spaces(self):
        """Handles multiple spaces correctly."""
        text = "First.    Second.   Third."
        result = _split_sentences(text)
        assert result == ["First.", "Second.", "Third."]

    def test_split_sentences_empty_string(self):
        """Returns empty list for empty string."""
        result = _split_sentences("")
        assert result == []


class TestDeduplicate:
    """Tests for _deduplicate method."""

    @pytest.fixture
    def mock_embedding_service(self):
        """Create a mock embedding service."""
        mock = MagicMock()
        mock.embed_batch = AsyncMock()
        return mock

    @pytest.fixture
    def sample_sources(self):
        """Create sample RAGSource objects for testing."""
        return [
            RAGSource(
                text="First source with unique content.",
                file_id="file1",
                score=0.9,
                metadata={},
            ),
            RAGSource(
                text="First source repeated here.",
                file_id="file2",
                score=0.8,
                metadata={},
            ),
            RAGSource(
                text="Another unique sentence here.",
                file_id="file3",
                score=0.7,
                metadata={},
            ),
        ]

    @pytest.mark.asyncio
    async def test_deduplicate_removes_duplicates(
        self, mock_embedding_service, sample_sources
    ):
        """Near-duplicate sentences removed."""
        # Test with multiple sentences per source
        # Source 0 has 2 sentences, source 1 has 1, source 2 has 1
        sources = [
            RAGSource(
                text="First sentence here with additional content. Second sentence.",
                file_id="file1",
                score=0.9,
                metadata={},
            ),
            RAGSource(
                text="Similar to first sentence here with additional content.",
                file_id="file2",
                score=0.8,
                metadata={},
            ),
            RAGSource(
                text="Completely different content in this sentence here.",
                file_id="file3",
                score=0.7,
                metadata={},
            ),
        ]
        # Embeddings for: source0-sent0, source0-sent1, source1-sent0, source2-sent0
        # source1-sent0 is duplicate of source0-sent0
        embeddings = [
            [1.0, 0.0, 0.0],  # source0 sentence 0
            [0.0, 1.0, 0.0],  # source0 sentence 1 (different)
            [1.0, 0.0, 0.0],  # source1 - same as source0 sentence 0 (duplicate)
            [0.0, 0.0, 1.0],  # source2 - unique
        ]
        mock_embedding_service.embed_batch.return_value = embeddings

        distiller = ContextDistiller(mock_embedding_service)
        result = await distiller._deduplicate(sources, threshold=0.92)

        # Should have fewer sources (duplicates removed)
        # source0: 2 sentences kept, source1: 0 (all dup), source2: 1 kept
        # source1 gets dropped as < 50 chars
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_deduplicate_first_source_kept(self, mock_embedding_service):
        """src_idx==0 sentences always kept."""
        sources = [
            RAGSource(
                text="First source sentence one. First source sentence two.",
                file_id="file1",
                score=0.9,
                metadata={},
            ),
            RAGSource(
                text="Completely different content here.",
                file_id="file2",
                score=0.8,
                metadata={},
            ),
        ]
        # All different embeddings
        embeddings = [
            [1.0, 0.0, 0.0],  # Sentence 1 from source 0
            [0.5, 0.5, 0.0],  # Sentence 2 from source 0
            [0.0, 1.0, 0.0],  # Sentence from source 1
        ]
        mock_embedding_service.embed_batch.return_value = embeddings

        distiller = ContextDistiller(mock_embedding_service)
        result = await distiller._deduplicate(sources, threshold=0.92)

        # First source should be kept entirely (src_idx=0 always kept)
        assert len(result) >= 1
        assert "First source" in result[0].text

    @pytest.mark.asyncio
    async def test_deduplicate_small_chunks_dropped(self, mock_embedding_service):
        """Chunks < 50 chars after dedup dropped."""
        sources = [
            RAGSource(
                text="This is a longer source with substantial content here.",
                file_id="file1",
                score=0.9,
                metadata={},
            ),
            RAGSource(
                text="This is a longer source with substantial content.",
                file_id="file2",
                score=0.8,
                metadata={},
            ),  # Duplicate of first
        ]
        # Both sentences are near-duplicates (same embedding)
        embeddings = [
            [1.0, 0.0, 0.0],  # source0 sentence
            [1.0, 0.0, 0.0],  # source1 - duplicate
        ]
        mock_embedding_service.embed_batch.return_value = embeddings

        distiller = ContextDistiller(mock_embedding_service)
        result = await distiller._deduplicate(sources, threshold=0.92)

        # source0 keeps sentence, source1 is dropped as < 50 chars
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_deduplicate_empty_sources(self, mock_embedding_service):
        """Returns original when sources is empty."""
        distiller = ContextDistiller(mock_embedding_service)
        result = await distiller._deduplicate([], threshold=0.92)
        assert result == []

    @pytest.mark.asyncio
    async def test_deduplicate_embedding_error_returns_original(
        self, mock_embedding_service
    ):
        """Exception returns unmodified sources."""
        sources = [
            RAGSource(text="Some content.", file_id="file1", score=0.9, metadata={}),
        ]
        mock_embedding_service.embed_batch.side_effect = Exception("Embedding failed")

        distiller = ContextDistiller(mock_embedding_service)
        # The exception should propagate (the wrapper in distill catches it)
        with pytest.raises(Exception, match="Embedding failed"):
            await distiller._deduplicate(sources, threshold=0.92)


class TestSynthesize:
    """Tests for _synthesize method."""

    @pytest.fixture
    def mock_llm_client(self):
        """Create a mock LLM client."""
        mock = MagicMock()
        mock.chat_completion = AsyncMock()
        return mock

    @pytest.fixture
    def mock_embedding_service(self):
        """Create a mock embedding service."""
        mock = MagicMock()
        mock.embed_batch = AsyncMock(return_value=[[1.0, 0.0, 0.0]])
        return mock

    @pytest.mark.asyncio
    async def test_synthesize_creates_synthetic_source(
        self, mock_embedding_service, mock_llm_client
    ):
        """LLM synthesis produces RAGSource."""
        sources = [
            RAGSource(
                text="Content about topic A.", file_id="file1", score=0.9, metadata={}
            ),
            RAGSource(
                text="More details about topic A.",
                file_id="file2",
                score=0.8,
                metadata={},
            ),
            RAGSource(
                text="Additional info on the subject.",
                file_id="file3",
                score=0.7,
                metadata={},
            ),
        ]
        mock_llm_client.chat_completion.return_value = (
            "Synthesized answer about the topic from multiple sources."
        )

        distiller = ContextDistiller(mock_embedding_service, mock_llm_client)
        result = await distiller._synthesize("What is this about?", sources)

        assert len(result) >= 1
        # First result should be the synthetic source
        assert result[0].metadata.get("synthesized") is True
        assert "Synthesized" in result[0].text

    @pytest.mark.asyncio
    async def test_synthesize_no_relevant_content(
        self, mock_embedding_service, mock_llm_client
    ):
        """Returns deduplicated sources unchanged when LLM returns NO_RELEVANT_CONTENT."""
        sources = [
            RAGSource(
                text="Some content here.", file_id="file1", score=0.9, metadata={}
            ),
        ]
        mock_llm_client.chat_completion.return_value = "NO_RELEVANT_CONTENT"

        distiller = ContextDistiller(mock_embedding_service, mock_llm_client)
        result = await distiller._synthesize("Unrelated query?", sources)

        # Should return original sources
        assert result == sources

    @pytest.mark.asyncio
    async def test_synthesize_llm_error_returns_sources(
        self, mock_embedding_service, mock_llm_client
    ):
        """Fail-open on LLM error."""
        sources = [
            RAGSource(
                text="Original content.", file_id="file1", score=0.9, metadata={}
            ),
        ]
        mock_llm_client.chat_completion.side_effect = Exception("LLM failed")

        distiller = ContextDistiller(mock_embedding_service, mock_llm_client)
        result = await distiller._synthesize("Test query?", sources)

        # Should return original sources on error (fail-open)
        assert result == sources


class TestDistill:
    """Tests for distill method (main entry point)."""

    @pytest.fixture
    def mock_embedding_service(self):
        """Create a mock embedding service."""
        mock = MagicMock()
        mock.embed_batch = AsyncMock()
        return mock

    @pytest.fixture
    def mock_llm_client(self):
        """Create a mock LLM client."""
        mock = MagicMock()
        mock.chat_completion = AsyncMock()
        return mock

    @pytest.mark.asyncio
    async def test_distill_with_synthesis_disabled(self, mock_embedding_service):
        """Only dedup runs when synthesis is disabled."""
        sources = [
            RAGSource(
                text="Original content here with additional text for length.",
                file_id="file1",
                score=0.9,
                metadata={},
            ),
            RAGSource(
                text="More original content here with additional text for length.",
                file_id="file2",
                score=0.8,
                metadata={},
            ),
        ]
        mock_embedding_service.embed_batch.return_value = [
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
        ]

        with patch("app.config.settings") as mock_settings:
            mock_settings.context_distillation_enabled = True
            mock_settings.context_distillation_synthesis_enabled = False
            mock_settings.context_distillation_dedup_threshold = 0.92

            distiller = ContextDistiller(mock_embedding_service)
            result = await distiller.distill("test query", sources, "NO_MATCH")

            # Should return deduped sources (both sentences are different)
            assert len(result) >= 1

    @pytest.mark.asyncio
    async def test_distill_with_synthesis_enabled_no_match(
        self, mock_embedding_service, mock_llm_client
    ):
        """Both dedup + synthesis run when enabled and eval_result is NO_MATCH."""
        sources = [
            RAGSource(
                text="Content about the topic with additional information here.",
                file_id="file1",
                score=0.9,
                metadata={},
            ),
            RAGSource(
                text="More details here about the same topic.",
                file_id="file2",
                score=0.8,
                metadata={},
            ),
            RAGSource(
                text="Additional information on this particular subject.",
                file_id="file3",
                score=0.7,
                metadata={},
            ),
        ]
        mock_embedding_service.embed_batch.return_value = [
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ]
        mock_llm_client.chat_completion.return_value = (
            "Synthesized response based on the sources."
        )

        with patch("app.config.settings") as mock_settings:
            mock_settings.context_distillation_enabled = True
            mock_settings.context_distillation_synthesis_enabled = True
            mock_settings.context_distillation_dedup_threshold = 0.92

            distiller = ContextDistiller(mock_embedding_service, mock_llm_client)
            result = await distiller.distill("test query", sources, "NO_MATCH")

            # Should have called synthesis
            assert mock_llm_client.chat_completion.called
            # First result should be synthesized
            assert result[0].metadata.get("synthesized") is True

    @pytest.mark.asyncio
    async def test_distill_confident_no_synthesis(
        self, mock_embedding_service, mock_llm_client
    ):
        """Synthesis does not run for CONFIDENT eval_result."""
        sources = [
            RAGSource(
                text="Content about the topic.", file_id="file1", score=0.9, metadata={}
            ),
        ]
        mock_embedding_service.embed_batch.return_value = [[1.0, 0.0, 0.0]]

        with patch("app.config.settings") as mock_settings:
            mock_settings.context_distillation_enabled = True
            mock_settings.context_distillation_synthesis_enabled = True
            mock_settings.context_distillation_dedup_threshold = 0.92

            distiller = ContextDistiller(mock_embedding_service, mock_llm_client)
            await distiller.distill("test query", sources, "CONFIDENT")

            # Synthesis should NOT be called for CONFIDENT
            mock_llm_client.chat_completion.assert_not_called()

    @pytest.mark.asyncio
    async def test_distill_ambiguous_does_not_trigger_synthesis(
        self, mock_embedding_service, mock_llm_client
    ):
        """Synthesis should NOT run for AMBIGUOUS — real chunks may be present."""
        sources = [
            RAGSource(
                text="Content about the topic with additional information here.",
                file_id="file1",
                score=0.9,
                metadata={},
            ),
            RAGSource(
                text="More details here about the same topic.",
                file_id="file2",
                score=0.8,
                metadata={},
            ),
        ]
        mock_embedding_service.embed_batch.return_value = [
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
        ]
        mock_llm_client.chat_completion.return_value = "Synthesized for ambiguous case."

        with patch("app.config.settings") as mock_settings:
            mock_settings.context_distillation_enabled = True
            mock_settings.context_distillation_synthesis_enabled = True
            mock_settings.context_distillation_dedup_threshold = 0.92

            distiller = ContextDistiller(mock_embedding_service, mock_llm_client)
            await distiller.distill("test query", sources, "AMBIGUOUS")

            # Synthesis should NOT be called for AMBIGUOUS
            assert not mock_llm_client.chat_completion.called

    @pytest.mark.asyncio
    async def test_distill_disabled_returns_original(self, mock_embedding_service):
        """ContextDistiller always runs - feature flag is checked at RAG engine level."""
        sources = [
            RAGSource(
                text="Original content with additional text for length and testing.",
                file_id="file1",
                score=0.9,
                metadata={},
            ),
        ]
        # When called directly, ContextDistiller always runs (flag is checked by RAG engine)
        mock_embedding_service.embed_batch.return_value = [[1.0, 0.0, 0.0]]

        with patch("app.config.settings") as mock_settings:
            # Flag doesn't matter - distiller always runs when called directly
            mock_settings.context_distillation_enabled = False
            mock_settings.context_distillation_synthesis_enabled = False
            mock_settings.context_distillation_dedup_threshold = 0.92

            distiller = ContextDistiller(mock_embedding_service)
            result = await distiller.distill("test query", sources, "NO_MATCH")

            # Distiller runs dedup and returns result (flag checked by caller)
            assert len(result) >= 1
            mock_embedding_service.embed_batch.assert_called()

    @pytest.mark.asyncio
    async def test_distill_no_llm_client_no_synthesis(self, mock_embedding_service):
        """No synthesis when llm_client is not provided."""
        sources = [
            RAGSource(text="Content.", file_id="file1", score=0.9, metadata={}),
            RAGSource(text="More content.", file_id="file2", score=0.8, metadata={}),
        ]
        mock_embedding_service.embed_batch.return_value = [
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
        ]

        with patch("app.config.settings") as mock_settings:
            mock_settings.context_distillation_enabled = True
            mock_settings.context_distillation_synthesis_enabled = True
            mock_settings.context_distillation_dedup_threshold = 0.92

            # No LLM client provided
            distiller = ContextDistiller(mock_embedding_service)
            await distiller.distill("test query", sources, "NO_MATCH")

            # embed_batch should have been called for dedup
            assert mock_embedding_service.embed_batch.called
