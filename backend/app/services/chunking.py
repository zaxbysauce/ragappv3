"""
Semantic chunking service using unstructured.chunking.title.chunk_by_title.
Preserves tables and code blocks while creating semantically meaningful chunks.
"""

from dataclasses import dataclass, field
from typing import List, Any, Optional
import math
import logging
import enum

logger = logging.getLogger(__name__)

from unstructured.chunking.title import chunk_by_title
from unstructured.documents.elements import Element


@dataclass
class ProcessedChunk:
    """
    Represents a processed chunk of document content.

    Attributes:
        text: The chunk text content
        metadata: Dictionary containing section title, element type, and other metadata
        chunk_index: Sequential index of this chunk in the document
        chunk_uid: Unique identifier for windowing (format: file_id_chunk_index)
        original_indices: List of original chunk indices if merged (for tracking)
    """

    text: str
    metadata: dict
    chunk_index: int
    chunk_uid: Optional[str] = None
    original_indices: List[int] = field(default_factory=list)


class SemanticChunker:
    """
    Semantic chunker using unstructured's title-based chunking.

    Uses character-based parameters directly for chunking.
    Preserves tables and code blocks by keeping element text intact.
    """

    def __init__(
        self,
        chunk_size_chars: int = 2000,
        chunk_overlap_chars: int = 200,
        max_merge_chars: int = 8192,
    ):
        """
        Initialize the semantic chunker.

        Args:
            chunk_size_chars: Target chunk size in characters
            chunk_overlap_chars: Overlap between chunks in characters
            max_merge_chars: Maximum characters when merging chunks (default 8192)
        """
        self.chunk_size = chunk_size_chars
        self.chunk_overlap = chunk_overlap_chars
        self.max_merge_chars = max_merge_chars

        # Use character counts directly
        self.max_characters = chunk_size_chars
        self.new_after_n_chars = chunk_size_chars
        self.overlap = chunk_overlap_chars

    def _get_element_text(self, element: Element) -> str:
        """
        Extract text from an element, preserving tables and code blocks.

        Args:
            element: Unstructured Element object

        Returns:
            String representation of the element's content
        """
        # Get the element text
        text = str(element)

        # For tables and code blocks, ensure we preserve the full content
        element_type = type(element).__name__
        if element_type in ("Table", "CodeSnippet"):
            # These elements should be kept intact
            return text

        return text

    def _get_element_metadata(self, element: Element) -> dict:
        """
        Extract metadata from an unstructured element.

        Args:
            element: Unstructured Element object

        Returns:
            Dictionary containing element metadata
        """
        metadata = {
            "element_type": type(element).__name__,
            "category": getattr(element, "category", None),
        }

        # Extract section title if available
        if hasattr(element, "metadata") and element.metadata:
            element_meta = element.metadata
            if hasattr(element_meta, "section") and element_meta.section:
                metadata["section_title"] = element_meta.section
            elif hasattr(element_meta, "page_name") and element_meta.page_name:
                metadata["section_title"] = element_meta.page_name
            elif hasattr(element_meta, "filename") and element_meta.filename:
                metadata["section_title"] = element_meta.filename

        # Try to get text as title if it's a Title element
        if metadata["element_type"] == "Title" and hasattr(element, "text"):
            metadata["section_title"] = element.text

        return metadata

    def _is_preserve_element(self, element: Element) -> bool:
        """
        Check if an element should be preserved intact (not split).

        Args:
            element: Unstructured Element object

        Returns:
            True if element should be preserved as-is
        """
        element_type = type(element).__name__
        return element_type in ("Table", "CodeSnippet", "TableChunk")

    def chunk_elements(self, elements: List[Element]) -> List[ProcessedChunk]:
        """
        Chunk document elements using title-based semantic chunking.

        Args:
            elements: List of unstructured document elements

        Returns:
            List of ProcessedChunk objects with text, metadata, and index
        """
        if not elements:
            return []

        # Use unstructured's chunk_by_title for semantic chunking
        # This respects document structure (titles, headers) when creating chunks
        chunks = chunk_by_title(
            elements,
            max_characters=self.max_characters,
            new_after_n_chars=self.new_after_n_chars,
            overlap=self.overlap,
            overlap_all=True,
        )

        processed_chunks = []

        for idx, chunk in enumerate(chunks):
            # Get chunk text
            chunk_text = str(chunk)

            # Extract metadata from the chunk
            metadata = self._get_element_metadata(chunk)
            metadata["chunk_index"] = idx
            metadata["total_chunks"] = len(chunks)

            # Add original element info if available
            if hasattr(chunk, "metadata") and chunk.metadata:
                orig_meta = chunk.metadata
                if hasattr(orig_meta, "page_number") and orig_meta.page_number:
                    metadata["page_number"] = orig_meta.page_number
                if hasattr(orig_meta, "filename") and orig_meta.filename:
                    metadata["source_file"] = orig_meta.filename

            processed_chunk = ProcessedChunk(
                text=chunk_text, metadata=metadata, chunk_index=idx
            )

            processed_chunks.append(processed_chunk)

        # Post-process chunks to merge those that split inside code blocks or tables
        processed_chunks = self._post_process_chunks(processed_chunks)

        return processed_chunks

    def _post_process_chunks(
        self, chunks: List[ProcessedChunk]
    ) -> List[ProcessedChunk]:
        """
        Merge chunks that split inside code blocks or tables.

        Args:
            chunks: List of ProcessedChunk objects from chunk_by_title

        Returns:
            List of ProcessedChunk objects with code blocks and tables preserved
        """
        merged = []
        pending = None

        for chunk in chunks:
            text = chunk.text

            if pending:
                # Try to merge pending with current
                merged_text = pending.text + "\n" + text
                if len(merged_text) <= self.max_merge_chars:
                    # Track original indices from both chunks
                    original_indices = list(pending.original_indices)
                    if chunk.original_indices:
                        original_indices.extend(chunk.original_indices)
                    else:
                        original_indices.append(chunk.chunk_index)

                    pending = ProcessedChunk(
                        text=merged_text,
                        metadata={**pending.metadata, "merged": True},
                        chunk_index=pending.chunk_index,
                        original_indices=original_indices,
                    )
                    text = pending.text
                else:
                    merged.append(pending)
                    pending = None

            # Check if this chunk ends inside code block or table
            code_fence_count = text.count("```")
            lines = text.split("\n")
            last_line = lines[-1] if lines else ""

            in_code_block = code_fence_count % 2 == 1
            in_table = last_line.strip().startswith("|")

            if in_code_block or in_table:
                # Store original indices for tracking
                if pending is None:
                    if chunk.original_indices:
                        original_indices = chunk.original_indices
                    else:
                        original_indices = [chunk.chunk_index]
                    pending = ProcessedChunk(
                        text=text,
                        metadata=dict(chunk.metadata),
                        chunk_index=chunk.chunk_index,
                        original_indices=original_indices,
                    )
                else:
                    # Continue building pending
                    pass
            else:
                if pending:
                    merged.append(pending)
                    pending = None
                else:
                    merged.append(chunk)

        if pending:
            merged.append(pending)

        # Re-index the merged chunks
        for idx, chunk in enumerate(merged):
            chunk.chunk_index = idx

        return merged

    def chunk_text(
        self, text: str, section_title: Optional[str] = None
    ) -> List[ProcessedChunk]:
        """
        Chunk plain text content.

        Args:
            text: Text content to chunk
            section_title: Optional section title for metadata

        Returns:
            List of ProcessedChunk objects
        """
        from unstructured.partition.text import partition_text

        # Partition the text into elements
        elements = partition_text(text=text)

        # Add section title to metadata if provided
        if section_title:
            for element in elements:
                if hasattr(element, "metadata") and element.metadata:
                    element.metadata.section = section_title

        return self.chunk_elements(elements)


class ThresholdType(enum.Enum):
    PERCENTILE = "percentile"
    STDDEV = "stddev"
    GRADIENT = "gradient"


class EmbeddingSemanticChunker:
    """
    Semantic chunker using embeddings and similarity-based breakpoints.

    Uses sentence embeddings to detect semantic boundaries based on
    similarity thresholds (percentile, standard deviation, or gradient).
    """

    def __init__(
        self,
        embedding_service: Any,
        threshold_type: ThresholdType = ThresholdType.PERCENTILE,
        threshold_value: float = 0.8,
        min_chunk_size: int = 100,
        max_chunk_size: int = 2000,
        window_size: int = 2,
    ):
        """
        Initialize the embedding-based semantic chunker.

        Args:
            embedding_service: Embedding service to use for generating embeddings
            threshold_type: Method for determining breakpoints (percentile, stddev, gradient)
            threshold_value: Threshold value for breakpoint detection
            min_chunk_size: Minimum number of characters for a chunk
            max_chunk_size: Maximum number of characters for a chunk
            window_size: Window size for comparing sentence embeddings
        """
        self.embedding_service = embedding_service
        self.threshold_type = threshold_type
        self.threshold_value = threshold_value
        self.min_chunk_size = min_chunk_size
        self.max_chunk_size = max_chunk_size
        self.window_size = window_size

        # Fallback chunker for text that exceeds max_chunk_size
        self._fallback_chunker = SemanticChunker(
            chunk_size_chars=max_chunk_size, chunk_overlap_chars=min_chunk_size // 2
        )

    def _split_into_sentences(self, text: str) -> List[str]:
        """
        Split text into sentences using simple rules.

        Args:
            text: Text to split into sentences

        Returns:
            List of sentences
        """
        import re

        # Simple sentence splitting on period, exclamation, question mark
        # followed by space and uppercase letter
        sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text.strip())

        # Clean up and filter empty sentences
        sentences = [s.strip() for s in sentences if s.strip()]

        return sentences

    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """
        Calculate cosine similarity between two vectors.

        Args:
            vec1: First vector
            vec2: Second vector

        Returns:
            Cosine similarity value between -1 and 1
        """
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = math.sqrt(sum(a * a for a in vec1))
        norm2 = math.sqrt(sum(b * b for b in vec2))

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return dot_product / (norm1 * norm2)

    def _calculate_breakpoints(self, similarities: List[float]) -> List[int]:
        """
        Calculate breakpoint indices based on similarity drops.

        Args:
            similarities: List of cosine similarities between consecutive sentences

        Returns:
            List of breakpoint indices
        """
        if not similarities:
            return []

        breakpoints = []

        if self.threshold_type == ThresholdType.PERCENTILE:
            # Use percentile-based threshold
            sorted_sims = sorted(similarities)
            idx = int((1 - self.threshold_value) * len(sorted_sims))
            idx = max(0, min(idx, len(sorted_sims) - 1))
            threshold = sorted_sims[idx]

            for i, sim in enumerate(similarities):
                if sim < threshold:
                    breakpoints.append(i)

        elif self.threshold_type == ThresholdType.STDDEV:
            # Use mean - (threshold_value * stddev) as threshold
            mean_sim = sum(similarities) / len(similarities)
            variance = sum((s - mean_sim) ** 2 for s in similarities) / len(
                similarities
            )
            stddev = math.sqrt(variance)
            threshold = mean_sim - (self.threshold_value * stddev)

            for i, sim in enumerate(similarities):
                if sim < threshold:
                    breakpoints.append(i)

        elif self.threshold_type == ThresholdType.GRADIENT:
            # Use gradient-based breakpoint detection
            # Find points where similarity drops significantly compared to neighbors
            for i in range(len(similarities)):
                # Calculate local gradient
                prev_sim = similarities[i - 1] if i > 0 else similarities[i]
                curr_sim = similarities[i]

                gradient = prev_sim - curr_sim

                if gradient > self.threshold_value:
                    breakpoints.append(i)

        return breakpoints

    async def chunk_text(
        self, text: str, section_title: Optional[str] = None
    ) -> List[ProcessedChunk]:
        """
        Chunk plain text content using embeddings-based semantic chunking.

        Args:
            text: Text content to chunk
            section_title: Optional section title for metadata

        Returns:
            List of ProcessedChunk objects
        """
        # Split text into sentences
        sentences = self._split_into_sentences(text)

        if len(sentences) <= 1:
            # Not enough sentences for semantic chunking, use fallback
            return self._fallback_chunk_text(text, section_title)

        # Create windows of sentences for embedding
        windows = []
        for i in range(len(sentences)):
            start = max(0, i - self.window_size + 1)
            end = min(len(sentences), i + self.window_size)
            window = " ".join(sentences[start:end])
            windows.append(window)

        # Get embeddings for all windows
        try:
            embeddings = []
            for window in windows:
                embedding = await self.embedding_service.embed_single(window)
                embeddings.append(embedding)
        except Exception as e:
            logger.warning(
                f"Failed to generate embeddings for semantic chunking: {e}. Using fallback chunker."
            )
            return self._fallback_chunk_text(text, section_title)

        # Calculate similarities between consecutive windows
        similarities = []
        for i in range(len(embeddings) - 1):
            sim = self._cosine_similarity(embeddings[i], embeddings[i + 1])
            similarities.append(sim)

        # Calculate breakpoints
        breakpoints = self._calculate_breakpoints(similarities)

        # Create chunks based on breakpoints
        chunks = []
        current_chunk_sentences = []
        current_chunk_length = 0
        chunk_idx = 0

        for i, sentence in enumerate(sentences):
            sentence_length = len(sentence)

            # Check if we need to start a new chunk
            should_break = (
                i - 1 in breakpoints  # Natural semantic breakpoint
                or (
                    current_chunk_length > 0
                    and current_chunk_length + sentence_length > self.max_chunk_size
                )
            )

            if should_break and current_chunk_sentences:
                # Start a new chunk
                chunk_text = " ".join(current_chunk_sentences)

                # Only create chunk if it meets minimum size
                if len(chunk_text) >= self.min_chunk_size:
                    metadata = {
                        "section_title": section_title,
                        "chunk_index": chunk_idx,
                        "total_chunks": 0,  # Will be updated later
                        "element_type": "SemanticChunk",
                    }

                    chunk = ProcessedChunk(
                        text=chunk_text, metadata=metadata, chunk_index=chunk_idx
                    )
                    chunks.append(chunk)
                    chunk_idx += 1

                current_chunk_sentences = [sentence]
                current_chunk_length = sentence_length
            else:
                current_chunk_sentences.append(sentence)
                current_chunk_length += sentence_length

        # Add remaining sentences as final chunk
        if current_chunk_sentences:
            chunk_text = " ".join(current_chunk_sentences)

            if len(chunk_text) >= self.min_chunk_size:
                metadata = {
                    "section_title": section_title,
                    "chunk_index": chunk_idx,
                    "total_chunks": 0,
                    "element_type": "SemanticChunk",
                }

                chunk = ProcessedChunk(
                    text=chunk_text, metadata=metadata, chunk_index=chunk_idx
                )
                chunks.append(chunk)

        # Update total_chunks in metadata
        for chunk in chunks:
            chunk.metadata["total_chunks"] = len(chunks)

        # If no chunks were created, use fallback
        if not chunks:
            return self._fallback_chunk_text(text, section_title)

        return chunks

    def _fallback_chunk_text(
        self, text: str, section_title: Optional[str] = None
    ) -> List[ProcessedChunk]:
        """
        Fallback chunking using SemanticChunker.

        Args:
            text: Text content to chunk
            section_title: Optional section title for metadata

        Returns:
            List of ProcessedChunk objects
        """
        chunks = self._fallback_chunker.chunk_text(text, section_title)

        # Update metadata to indicate fallback was used
        for chunk in chunks:
            chunk.metadata["semantic_chunk_fallback"] = True

        return chunks

    def chunk_elements(self, elements: List[Element]) -> List[ProcessedChunk]:
        """
        Chunk document elements using embedding-based semantic chunking.

        Note: This method requires async context to run properly.
        For sync contexts, use chunk_text or SemanticChunker.chunk_elements.

        Args:
            elements: List of unstructured document elements

        Returns:
            List of ProcessedChunk objects (requires await to populate)
        """
        # Combine all element text
        all_text = "\n\n".join(str(el) for el in elements if str(el).strip())

        # This is a sync method, so we can't await chunk_text
        # Return empty list to indicate this needs async handling
        logger.warning(
            "chunk_elements requires async context. Use chunk_text instead or run in async context."
        )
        return []
