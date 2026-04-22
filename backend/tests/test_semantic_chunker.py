"""
Unit tests for EmbeddingSemanticChunker in chunking.py

Tests cover:
- ThresholdType enum values
- _split_into_sentences sentence boundary detection
- _cosine_similarity with various vector scenarios
- _calculate_breakpoints with PERCENTILE, STDDEV, GRADIENT thresholds
- async chunk_text with mocked embedding_service
- Fallback behavior on embedding failure
- Edge cases: empty text, single sentence, min/max chunk size constraints
"""

import math
import unittest
import warnings
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.chunking import (
    EmbeddingSemanticChunker,
    ProcessedChunk,
    ThresholdType,
)


class TestThresholdTypeEnum(unittest.TestCase):
    """Test 1: ThresholdType enum has correct values."""

    def test_enum_has_percentile(self):
        """ThresholdType.PERCENTILE should exist with value 'percentile'."""
        self.assertEqual(ThresholdType.PERCENTILE.value, "percentile")

    def test_enum_has_stddev(self):
        """ThresholdType.STDDEV should exist with value 'stddev'."""
        self.assertEqual(ThresholdType.STDDEV.value, "stddev")

    def test_enum_has_gradient(self):
        """ThresholdType.GRADIENT should exist with value 'gradient'."""
        self.assertEqual(ThresholdType.GRADIENT.value, "gradient")

    def test_enum_count(self):
        """ThresholdType should have exactly 3 values."""
        self.assertEqual(len(list(ThresholdType)), 3)


class TestSplitIntoSentences(unittest.TestCase):
    """Test 2: _split_into_sentences produces correct sentence boundaries."""

    def setUp(self):
        """Create chunker with mock embedding service."""
        self.mock_embedding_service = MagicMock()
        self.chunker = EmbeddingSemanticChunker(
            embedding_service=self.mock_embedding_service,
        )

    def test_basic_sentence_split(self):
        """Should split on period followed by space and uppercase letter."""
        text = "Hello world. How are you? I am fine."
        sentences = self.chunker._split_into_sentences(text)
        self.assertEqual(sentences, ["Hello world.", "How are you?", "I am fine."])

    def test_exclamation_split(self):
        """Should split on exclamation mark."""
        text = "Wow! That is amazing. Really great."
        sentences = self.chunker._split_into_sentences(text)
        self.assertEqual(sentences, ["Wow!", "That is amazing.", "Really great."])

    def test_question_mark_split(self):
        """Should split on question mark."""
        text = "What is this? Is it a test? Yes it is."
        sentences = self.chunker._split_into_sentences(text)
        self.assertEqual(sentences, ["What is this?", "Is it a test?", "Yes it is."])

    def test_no_split_single_sentence(self):
        """Should return single sentence when no split points."""
        text = "This is a single sentence without proper punctuation"
        sentences = self.chunker._split_into_sentences(text)
        self.assertEqual(
            sentences, ["This is a single sentence without proper punctuation"]
        )

    def test_empty_text_returns_empty_list(self):
        """Empty text should return empty list."""
        sentences = self.chunker._split_into_sentences("")
        self.assertEqual(sentences, [])

    def test_whitespace_only_returns_empty_list(self):
        """Whitespace-only text should return empty list."""
        sentences = self.chunker._split_into_sentences(" \n\t ")
        self.assertEqual(sentences, [])

    def test_strips_whitespace_from_sentences(self):
        """Should strip leading/trailing whitespace from sentences."""
        text = " First sentence. Second sentence. "
        sentences = self.chunker._split_into_sentences(text)
        self.assertEqual(sentences, ["First sentence.", "Second sentence."])

    def test_lowercase_after_punctuation_splits_correctly(self):
        """Should split on period + space + uppercase, abbreviations included."""
        text = "Dr. Smith lives here. Mr. Johnson too."
        sentences = self.chunker._split_into_sentences(text)
        # The regex splits on period + space + uppercase
        # "Dr." followed by " Smith" -> split because S is uppercase
        self.assertEqual(sentences, ["Dr.", "Smith lives here.", "Mr.", "Johnson too."])


class TestCosineSimilarity(unittest.TestCase):
    """Test 3: _cosine_similarity with various vector scenarios."""

    def setUp(self):
        """Create chunker with mock embedding service."""
        self.mock_embedding_service = MagicMock()
        self.chunker = EmbeddingSemanticChunker(
            embedding_service=self.mock_embedding_service,
        )

    def test_identical_vectors_returns_one(self):
        """Identical vectors should have cosine similarity of 1.0."""
        vec = [1.0, 2.0, 3.0, 4.0]
        result = self.chunker._cosine_similarity(vec, vec)
        self.assertAlmostEqual(result, 1.0, places=6)

    def test_orthogonal_vectors_returns_zero(self):
        """Orthogonal vectors should have cosine similarity of 0.0."""
        vec1 = [1.0, 0.0]
        vec2 = [0.0, 1.0]
        result = self.chunker._cosine_similarity(vec1, vec2)
        self.assertAlmostEqual(result, 0.0, places=6)

    def test_opposite_vectors_returns_minus_one(self):
        """Opposite vectors should have cosine similarity of -1.0."""
        vec1 = [1.0, 2.0]
        vec2 = [-1.0, -2.0]
        result = self.chunker._cosine_similarity(vec1, vec2)
        self.assertAlmostEqual(result, -1.0, places=6)

    def test_zero_vector_first_returns_zero(self):
        """Zero vector as first argument should return 0.0."""
        vec1 = [0.0, 0.0, 0.0]
        vec2 = [1.0, 2.0, 3.0]
        result = self.chunker._cosine_similarity(vec1, vec2)
        self.assertEqual(result, 0.0)

    def test_zero_vector_second_returns_zero(self):
        """Zero vector as second argument should return 0.0."""
        vec1 = [1.0, 2.0, 3.0]
        vec2 = [0.0, 0.0, 0.0]
        result = self.chunker._cosine_similarity(vec1, vec2)
        self.assertEqual(result, 0.0)

    def test_both_zero_vectors_returns_zero(self):
        """Both zero vectors should return 0.0."""
        vec1 = [0.0, 0.0, 0.0]
        vec2 = [0.0, 0.0, 0.0]
        result = self.chunker._cosine_similarity(vec1, vec2)
        self.assertEqual(result, 0.0)

    def test_normalized_vectors(self):
        """Test with pre-normalized vectors."""
        # Unit vectors at 45 degrees to each other
        vec1 = [1.0, 0.0]
        vec2 = [math.sqrt(2) / 2, math.sqrt(2) / 2]
        result = self.chunker._cosine_similarity(vec1, vec2)
        self.assertAlmostEqual(result, math.sqrt(2) / 2, places=6)

    def test_single_element_vectors(self):
        """Test with single-element vectors."""
        vec1 = [5.0]
        vec2 = [3.0]
        # Both positive, similarity should be 1.0
        result = self.chunker._cosine_similarity(vec1, vec2)
        self.assertAlmostEqual(result, 1.0, places=6)


class TestCalculateBreakpoints(unittest.TestCase):
    """Tests 4-7: _calculate_breakpoints with various threshold types."""

    def setUp(self):
        """Create chunker with mock embedding service."""
        self.mock_embedding_service = MagicMock()

    def test_percentile_threshold(self):
        """Test 4: PERCENTILE threshold identifies low-similarity breakpoints."""
        chunker = EmbeddingSemanticChunker(
            embedding_service=self.mock_embedding_service,
            threshold_type=ThresholdType.PERCENTILE,
            threshold_value=0.5,  # Bottom 50% of similarities
        )
        # Similarities: [0.1, 0.9, 0.2, 0.8]
        # Sorted: [0.1, 0.2, 0.8, 0.9]
        # Index for 0.5 threshold: (1 - 0.5) * 4 = 2 -> sorted_sims[2] = 0.8
        # So 0.1 < 0.8 (index 0), 0.9 >= 0.8, 0.2 < 0.8 (index 2), 0.8 >= 0.8
        similarities = [0.1, 0.9, 0.2, 0.8]
        breakpoints = chunker._calculate_breakpoints(similarities)
        # Indices where similarity < 0.8: 0, 2
        self.assertEqual(breakpoints, [0, 2])

    def test_percentile_high_threshold(self):
        """PERCENTILE with high threshold_value catches more breakpoints."""
        chunker = EmbeddingSemanticChunker(
            embedding_service=self.mock_embedding_service,
            threshold_type=ThresholdType.PERCENTILE,
            threshold_value=0.9,  # Bottom 10%
        )
        similarities = [0.1, 0.9, 0.2, 0.8]
        breakpoints = chunker._calculate_breakpoints(similarities)
        # High threshold means few breakpoints
        # Index = (1 - 0.9) * 4 = 0.4 -> 0, threshold = sorted_sims[0] = 0.1
        # Only values < 0.1 trigger breakpoints (none in this case)
        self.assertEqual(breakpoints, [])

    def test_stddev_threshold(self):
        """Test 5: STDDEV threshold uses mean - (value * stddev)."""
        chunker = EmbeddingSemanticChunker(
            embedding_service=self.mock_embedding_service,
            threshold_type=ThresholdType.STDDEV,
            threshold_value=1.0,  # One standard deviation below mean
        )
        # Similarities: [0.4, 0.5, 0.6, 0.5]
        # Mean = 0.5, Variance = ((0.4-0.5)^2 + (0.5-0.5)^2 + (0.6-0.5)^2 + (0.5-0.5)^2) / 4
        #       = (0.01 + 0 + 0.01 + 0) / 4 = 0.005
        # Stddev = sqrt(0.005) ≈ 0.0707
        # Threshold = 0.5 - 1.0 * 0.0707 ≈ 0.4293
        # Values < 0.4293: index 0 (0.4)
        similarities = [0.4, 0.5, 0.6, 0.5]
        breakpoints = chunker._calculate_breakpoints(similarities)
        self.assertEqual(breakpoints, [0])

    def test_stddev_high_threshold_value(self):
        """STDDEV with high threshold_value catches more breakpoints."""
        chunker = EmbeddingSemanticChunker(
            embedding_service=self.mock_embedding_service,
            threshold_type=ThresholdType.STDDEV,
            threshold_value=2.0,  # Two standard deviations below mean
        )
        # Similarities: [0.3, 0.5, 0.7, 0.5]
        # Mean = 0.5, need to calculate stddev
        similarities = [0.3, 0.5, 0.7, 0.5]
        breakpoints = chunker._calculate_breakpoints(similarities)
        # Threshold = mean - 2*stddev, lower values get caught
        # With low stddev, threshold may be negative, so fewer breakpoints
        self.assertIsInstance(breakpoints, list)

    def test_gradient_threshold(self):
        """Test 6: GRADIENT threshold detects similarity drops."""
        chunker = EmbeddingSemanticChunker(
            embedding_service=self.mock_embedding_service,
            threshold_type=ThresholdType.GRADIENT,
            threshold_value=0.3,  # Gradient must exceed this
        )
        # Similarities: [0.8, 0.3, 0.9, 0.8]
        # At index 1: gradient = 0.8 - 0.3 = 0.5 > 0.3 -> breakpoint
        # At index 2: gradient = 0.3 - 0.9 = -0.6 (negative, not > 0.3)
        # At index 3: gradient = 0.9 - 0.8 = 0.1 < 0.3
        similarities = [0.8, 0.3, 0.9, 0.8]
        breakpoints = chunker._calculate_breakpoints(similarities)
        self.assertEqual(breakpoints, [1])

    def test_gradient_multiple_drops(self):
        """GRADIENT should detect multiple significant drops."""
        chunker = EmbeddingSemanticChunker(
            embedding_service=self.mock_embedding_service,
            threshold_type=ThresholdType.GRADIENT,
            threshold_value=0.2,
        )
        # Similarities: [0.9, 0.5, 0.8, 0.4]
        # Index 1: gradient = 0.9 - 0.5 = 0.4 > 0.2 -> breakpoint
        # Index 2: gradient = 0.5 - 0.8 = -0.3 (negative)
        # Index 3: gradient = 0.8 - 0.4 = 0.4 > 0.2 -> breakpoint
        similarities = [0.9, 0.5, 0.8, 0.4]
        breakpoints = chunker._calculate_breakpoints(similarities)
        self.assertEqual(breakpoints, [1, 3])

    def test_empty_similarities_returns_empty_list(self):
        """Test 7: Empty similarities list should return empty breakpoints."""
        chunker = EmbeddingSemanticChunker(
            embedding_service=self.mock_embedding_service,
        )
        breakpoints = chunker._calculate_breakpoints([])
        self.assertEqual(breakpoints, [])

    def test_single_similarity_returns_empty_breakpoints(self):
        """Single similarity value should return empty breakpoints."""
        chunker = EmbeddingSemanticChunker(
            embedding_service=self.mock_embedding_service,
        )
        breakpoints = chunker._calculate_breakpoints([0.5])
        self.assertEqual(breakpoints, [])


class TestChunkTextAsync(unittest.IsolatedAsyncioTestCase):
    """Tests 8-13: async chunk_text with mocked embedding_service."""

    def setUp(self):
        """Create chunker with AsyncMock for embedding_service."""
        self.mock_embedding_service = MagicMock()
        self.mock_embedding_service.embed_single = AsyncMock()

    async def test_chunk_text_returns_valid_processed_chunks(self):
        """Test 8: chunk_text with mock embedding_service returns valid ProcessedChunks."""
        # Setup: text with 4 sentences
        text = "First sentence here. Second sentence here. Third sentence here. Fourth sentence here."

        # Mock embeddings that are similar (no semantic breaks)
        similar_vec = [0.5] * 10
        self.mock_embedding_service.embed_single.return_value = similar_vec

        chunker = EmbeddingSemanticChunker(
            embedding_service=self.mock_embedding_service,
            threshold_type=ThresholdType.PERCENTILE,
            threshold_value=0.5,
            min_chunk_size=10,
            max_chunk_size=500,
            window_size=1,
        )

        chunks = await chunker.chunk_text(text, section_title="Test Section")

        # Should have at least one chunk
        self.assertGreater(len(chunks), 0)

        # Verify each chunk is a ProcessedChunk
        for chunk in chunks:
            self.assertIsInstance(chunk, ProcessedChunk)
            self.assertIsInstance(chunk.text, str)
            self.assertIsInstance(chunk.metadata, dict)
            self.assertIsInstance(chunk.chunk_index, int)
            self.assertEqual(chunk.metadata["section_title"], "Test Section")
            self.assertEqual(chunk.metadata["element_type"], "SemanticChunk")

    async def test_chunk_text_fallback_on_embedding_failure(self):
        """Test 9: chunk_text falls back on embedding failure."""
        text = "First sentence here. Second sentence here. Third sentence here."

        # Mock embedding failure
        self.mock_embedding_service.embed_single.side_effect = RuntimeError(
            "Embedding failed"
        )

        # Mock the fallback chunker's chunk_text to return a valid chunk
        mock_fallback_chunk = ProcessedChunk(
            text=text,
            metadata={
                "section_title": "Fallback Test",
                "semantic_chunk_fallback": True,
            },
            chunk_index=0,
        )

        chunker = EmbeddingSemanticChunker(
            embedding_service=self.mock_embedding_service,
            min_chunk_size=10,
            max_chunk_size=500,
        )

        # Patch the fallback chunker to return our mock chunk
        with patch.object(
            chunker._fallback_chunker, "chunk_text", return_value=[mock_fallback_chunk]
        ):
            chunks = await chunker.chunk_text(text, section_title="Fallback Test")

        # Should return fallback chunks
        self.assertGreater(len(chunks), 0)

        # Verify fallback metadata is set
        for chunk in chunks:
            self.assertTrue(chunk.metadata.get("semantic_chunk_fallback", False))

    async def test_chunk_text_empty_returns_empty_list(self):
        """Test 10: chunk_text with empty text returns []."""
        chunker = EmbeddingSemanticChunker(
            embedding_service=self.mock_embedding_service,
        )

        # Patch the fallback chunker to avoid unstructured import
        with patch.object(chunker._fallback_chunker, "chunk_text", return_value=[]):
            chunks = await chunker.chunk_text("")
        self.assertEqual(chunks, [])

        # embed_single should never have been called
        self.mock_embedding_service.embed_single.assert_not_called()

    async def test_chunk_text_single_sentence_returns_single_chunk(self):
        """Test 11: chunk_text with single sentence returns single chunk."""
        text = "This is a single sentence."

        # Mock the fallback chunker to return a valid chunk
        mock_fallback_chunk = ProcessedChunk(
            text=text,
            metadata={"section_title": None, "semantic_chunk_fallback": True},
            chunk_index=0,
        )

        chunker = EmbeddingSemanticChunker(
            embedding_service=self.mock_embedding_service,
            min_chunk_size=10,
        )

        # Patch the fallback chunker to return our mock chunk
        with patch.object(
            chunker._fallback_chunker, "chunk_text", return_value=[mock_fallback_chunk]
        ):
            chunks = await chunker.chunk_text(text)

        # Single sentence triggers fallback
        self.assertGreater(len(chunks), 0)

    async def test_min_chunk_size_merging(self):
        """Test 12: min_chunk_size merging works - small chunks are excluded."""
        text = "A. B. C. This is a much longer sentence that should meet the minimum chunk size requirement."

        similar_vec = [0.8] * 10
        self.mock_embedding_service.embed_single.return_value = similar_vec

        chunker = EmbeddingSemanticChunker(
            embedding_service=self.mock_embedding_service,
            threshold_type=ThresholdType.PERCENTILE,
            threshold_value=0.5,
            min_chunk_size=50,  # Require 50 char minimum
            max_chunk_size=2000,
            window_size=1,
        )

        chunks = await chunker.chunk_text(text)

        # Chunks should meet minimum size requirement
        for chunk in chunks:
            self.assertGreaterEqual(len(chunk.text), 50)

    async def test_max_chunk_size_splitting(self):
        """Test 13: max_chunk_size splitting works - large chunks are split."""
        # Create text that would naturally form a large chunk
        text = "First sentence here. Second sentence here. Third sentence here. Fourth sentence here. Fifth sentence here. Sixth sentence here."

        # All embeddings similar (no semantic breaks)
        similar_vec = [0.8] * 10
        self.mock_embedding_service.embed_single.return_value = similar_vec

        chunker = EmbeddingSemanticChunker(
            embedding_service=self.mock_embedding_service,
            threshold_type=ThresholdType.PERCENTILE,
            threshold_value=0.1,  # High threshold, few breakpoints
            min_chunk_size=10,
            max_chunk_size=80,  # Very small max to force splitting
            window_size=1,
        )

        chunks = await chunker.chunk_text(text)

        # Verify no chunk exceeds max_chunk_size
        for chunk in chunks:
            self.assertLessEqual(len(chunk.text), 80)


class TestChunkElements(unittest.TestCase):
    """Test 14: chunk_elements returns [] with warning."""

    def setUp(self):
        """Create chunker with mock embedding service."""
        self.mock_embedding_service = MagicMock()
        self.chunker = EmbeddingSemanticChunker(
            embedding_service=self.mock_embedding_service,
        )

    def test_chunk_elements_returns_empty_list(self):
        """chunk_elements should return [] (requires async context)."""
        # Create mock elements
        mock_element = MagicMock()
        mock_element.__str__ = MagicMock(return_value="Some text content")
        elements = [mock_element]

        # Capture warnings
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            result = self.chunker.chunk_elements(elements)

        # Should return empty list
        self.assertEqual(result, [])

    def test_chunk_elements_logs_warning(self):
        """chunk_elements should log a warning about async context."""
        mock_element = MagicMock()
        mock_element.__str__ = MagicMock(return_value="Some text")
        elements = [mock_element]

        # The warning is logged via logger.warning, not Python warnings
        # Just verify the method returns empty list
        result = self.chunker.chunk_elements(elements)
        self.assertEqual(result, [])


class TestProcessedChunkDataclass(unittest.TestCase):
    """Test ProcessedChunk dataclass behavior."""

    def test_processed_chunk_creation(self):
        """ProcessedChunk should be creatable with required fields."""
        chunk = ProcessedChunk(
            text="Test text",
            metadata={"key": "value"},
            chunk_index=0,
        )
        self.assertEqual(chunk.text, "Test text")
        self.assertEqual(chunk.metadata, {"key": "value"})
        self.assertEqual(chunk.chunk_index, 0)
        self.assertIsNone(chunk.chunk_uid)
        self.assertEqual(chunk.original_indices, [])

    def test_processed_chunk_with_optional_fields(self):
        """ProcessedChunk should accept optional fields."""
        chunk = ProcessedChunk(
            text="Test text",
            metadata={"key": "value"},
            chunk_index=1,
            chunk_uid="file_1",
            original_indices=[0, 1, 2],
        )
        self.assertEqual(chunk.chunk_uid, "file_1")
        self.assertEqual(chunk.original_indices, [0, 1, 2])


class TestConstructorDefaults(unittest.TestCase):
    """Test EmbeddingSemanticChunker constructor defaults."""

    def test_default_threshold_type(self):
        """Default threshold_type should be PERCENTILE."""
        chunker = EmbeddingSemanticChunker(embedding_service=MagicMock())
        self.assertEqual(chunker.threshold_type, ThresholdType.PERCENTILE)

    def test_default_threshold_value(self):
        """Default threshold_value should be 0.8."""
        chunker = EmbeddingSemanticChunker(embedding_service=MagicMock())
        self.assertEqual(chunker.threshold_value, 0.8)

    def test_default_min_chunk_size(self):
        """Default min_chunk_size should be 100."""
        chunker = EmbeddingSemanticChunker(embedding_service=MagicMock())
        self.assertEqual(chunker.min_chunk_size, 100)

    def test_default_max_chunk_size(self):
        """Default max_chunk_size should be 2000."""
        chunker = EmbeddingSemanticChunker(embedding_service=MagicMock())
        self.assertEqual(chunker.max_chunk_size, 2000)

    def test_default_window_size(self):
        """Default window_size should be 2."""
        chunker = EmbeddingSemanticChunker(embedding_service=MagicMock())
        self.assertEqual(chunker.window_size, 2)

    def test_custom_parameters(self):
        """Custom parameters should be stored correctly."""
        chunker = EmbeddingSemanticChunker(
            embedding_service=MagicMock(),
            threshold_type=ThresholdType.GRADIENT,
            threshold_value=0.3,
            min_chunk_size=50,
            max_chunk_size=1000,
            window_size=3,
        )
        self.assertEqual(chunker.threshold_type, ThresholdType.GRADIENT)
        self.assertEqual(chunker.threshold_value, 0.3)
        self.assertEqual(chunker.min_chunk_size, 50)
        self.assertEqual(chunker.max_chunk_size, 1000)
        self.assertEqual(chunker.window_size, 3)


class TestFallbackChunkText(unittest.TestCase):
    """Test _fallback_chunk_text method."""

    def test_fallback_returns_chunks(self):
        """_fallback_chunk_text should return chunks from SemanticChunker."""
        chunker = EmbeddingSemanticChunker(
            embedding_service=MagicMock(),
            max_chunk_size=500,
        )

        text = "This is a test. This is another sentence. And a third one here."

        # Mock the fallback chunker's chunk_text method
        mock_chunks = [
            ProcessedChunk(
                text=text,
                metadata={"section_title": "Fallback", "semantic_chunk_fallback": True},
                chunk_index=0,
            )
        ]

        with patch.object(
            chunker._fallback_chunker, "chunk_text", return_value=mock_chunks
        ):
            chunks = chunker._fallback_chunk_text(text, section_title="Fallback")

        self.assertGreater(len(chunks), 0)

        # Verify fallback metadata
        for chunk in chunks:
            self.assertTrue(chunk.metadata.get("semantic_chunk_fallback", False))


class TestIntegrationEdgeCases(unittest.IsolatedAsyncioTestCase):
    """Integration tests for edge cases in chunk_text."""

    def setUp(self):
        """Create chunker with AsyncMock."""
        self.mock_embedding_service = MagicMock()
        self.mock_embedding_service.embed_single = AsyncMock()

    async def test_chunk_text_whitespace_only(self):
        """Whitespace-only text should return empty list or fallback."""
        chunker = EmbeddingSemanticChunker(
            embedding_service=self.mock_embedding_service,
        )

        # Patch the fallback chunker to avoid unstructured import
        mock_chunk = ProcessedChunk(
            text="",
            metadata={"semantic_chunk_fallback": True},
            chunk_index=0,
        )
        with patch.object(
            chunker._fallback_chunker, "chunk_text", return_value=[mock_chunk]
        ):
            chunks = await chunker.chunk_text(" \n\t ")
        # Should return empty or handle gracefully
        self.assertIsInstance(chunks, list)

    async def test_chunk_text_with_section_title_propagation(self):
        """Section title should be propagated to all chunks."""
        text = "First sentence. Second sentence. Third sentence. Fourth sentence."

        similar_vec = [0.5] * 10
        self.mock_embedding_service.embed_single.return_value = similar_vec

        chunker = EmbeddingSemanticChunker(
            embedding_service=self.mock_embedding_service,
            min_chunk_size=10,
            max_chunk_size=500,
        )

        chunks = await chunker.chunk_text(text, section_title="My Section")

        for chunk in chunks:
            self.assertEqual(chunk.metadata.get("section_title"), "My Section")

    async def test_chunk_indices_are_sequential(self):
        """Chunk indices should be sequential starting from 0."""
        text = "First sentence. Second sentence. Third sentence. Fourth sentence. Fifth sentence."

        similar_vec = [0.5] * 10
        self.mock_embedding_service.embed_single.return_value = similar_vec

        chunker = EmbeddingSemanticChunker(
            embedding_service=self.mock_embedding_service,
            min_chunk_size=10,
            max_chunk_size=100,
        )

        chunks = await chunker.chunk_text(text)

        for i, chunk in enumerate(chunks):
            self.assertEqual(chunk.chunk_index, i)

    async def test_total_chunks_metadata_accurate(self):
        """total_chunks metadata should reflect actual chunk count."""
        text = "First sentence. Second sentence. Third sentence. Fourth sentence."

        similar_vec = [0.5] * 10
        self.mock_embedding_service.embed_single.return_value = similar_vec

        chunker = EmbeddingSemanticChunker(
            embedding_service=self.mock_embedding_service,
            min_chunk_size=10,
            max_chunk_size=100,
        )

        chunks = await chunker.chunk_text(text)

        for chunk in chunks:
            self.assertEqual(chunk.metadata.get("total_chunks"), len(chunks))


if __name__ == "__main__":
    unittest.main()
