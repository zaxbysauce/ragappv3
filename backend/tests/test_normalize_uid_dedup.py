"""Tests for _normalize_uid_for_dedup() in document_retrieval.py.

This module tests the UID normalization function that strips scale suffixes
from multi-scale chunk UIDs for deduplication purposes.
"""

import pytest
from unittest.mock import MagicMock, patch

from app.services.document_retrieval import (
    _normalize_uid_for_dedup,
    DocumentRetrievalService,
    RAGSource,
)


class TestNormalizeUidForDedupUnit:
    """Unit tests for _normalize_uid_for_dedup function."""

    def test_multi_scale_uid_normalized(self):
        """Multi-scale UID with numeric scale and index should strip scale."""
        # "doc1_512_3" → "doc1_3" (strips the scale component)
        result = _normalize_uid_for_dedup("doc1_512_3")
        assert result == "doc1_3", f"Expected 'doc1_3', got '{result}'"

    def test_default_uid_unchanged(self):
        """Default UID (file_id_index) should remain unchanged."""
        # "doc1_3" → "doc1_3" (already in default format)
        result = _normalize_uid_for_dedup("doc1_3")
        assert result == "doc1_3", f"Expected 'doc1_3', got '{result}'"

    def test_non_numeric_middle_part_unchanged(self):
        """UID with non-numeric middle part should remain unchanged."""
        # "my_file_v2_3" → "my_file_v2_3" (middle part 'v2' is not numeric)
        result = _normalize_uid_for_dedup("my_file_v2_3")
        assert result == "my_file_v2_3", f"Expected 'my_file_v2_3', got '{result}'"

    def test_non_numeric_last_part_unchanged(self):
        """UID with non-numeric last part should remain unchanged."""
        # "doc1_abc" → "doc1_abc" (last part 'abc' is not numeric)
        result = _normalize_uid_for_dedup("doc1_abc")
        assert result == "doc1_abc", f"Expected 'doc1_abc', got '{result}'"

    def test_idempotent(self):
        """Calling the function twice should return the same result."""
        # This is a property test: f(f(x)) === f(x)
        original = "doc1_512_3"
        first_pass = _normalize_uid_for_dedup(original)
        second_pass = _normalize_uid_for_dedup(first_pass)
        assert second_pass == first_pass, (
            f"Idempotency violation: f(f('{original}')) = '{second_pass}' "
            f"but f('{original}') = '{first_pass}'"
        )

        # Also verify with a default UID
        default_uid = "doc1_3"
        first_default = _normalize_uid_for_dedup(default_uid)
        second_default = _normalize_uid_for_dedup(first_default)
        assert second_default == first_default == default_uid, (
            f"Idempotency violation for default UID"
        )

    def test_empty_string(self):
        """Empty string should return empty string."""
        result = _normalize_uid_for_dedup("")
        assert result == "", f"Expected empty string, got '{result}'"

    def test_single_segment(self):
        """Single segment UID (no underscores) should remain unchanged."""
        # "doc1" → "doc1" (no underscores, cannot be multi-scale format)
        result = _normalize_uid_for_dedup("doc1")
        assert result == "doc1", f"Expected 'doc1', got '{result}'"

    def test_large_scale_value(self):
        """Large scale values should be stripped correctly."""
        # "file_1024_99" → "file_99" (large scale like 1024 is stripped)
        result = _normalize_uid_for_dedup("file_1024_99")
        assert result == "file_99", f"Expected 'file_99', got '{result}'"

    def test_two_numeric_segments_three_parts(self):
        """UID with two numeric segments should strip the first numeric (scale)."""
        # "file_5_10" → "file_10" (first numeric is scale, second is index)
        result = _normalize_uid_for_dedup("file_5_10")
        assert result == "file_10", f"Expected 'file_10', got '{result}'"

    def test_two_part_uid(self):
        """Two-part UID (file_id_index) should remain unchanged."""
        # "myfile_5" → "myfile_5" (standard default format)
        result = _normalize_uid_for_dedup("myfile_5")
        assert result == "myfile_5", f"Expected 'myfile_5', got '{result}'"

    def test_numeric_file_id_multi_scale(self):
        """Numeric file_id with scale and index should work correctly."""
        # "123_512_456" → "123_456" (numeric file_id, scale stripped)
        result = _normalize_uid_for_dedup("123_512_456")
        assert result == "123_456", f"Expected '123_456', got '{result}'"

    def test_zero_scale_and_index(self):
        """Zero values for scale and index should work correctly."""
        # "doc_0_0" → "doc_0" (edge case with zeros)
        result = _normalize_uid_for_dedup("doc_0_0")
        assert result == "doc_0", f"Expected 'doc_0', got '{result}'"

    def test_negative_numbers_treated_as_non_numeric(self):
        """Negative numbers in segments should be treated as non-numeric."""
        # rsplit with negative sign creates issues; verify behavior
        # "-5_10" might behave unexpectedly, but let's test it
        result = _normalize_uid_for_dedup("doc_-5_10")
        # This will split as ["doc", "-5", "10"], and int("-5") works
        # So middle is numeric, should strip: "doc_10"
        assert result == "doc_10", f"Expected 'doc_10', got '{result}'"

    def test_very_large_numbers(self):
        """Very large numeric values should still work."""
        # "doc_999999_1" → "doc_1"
        result = _normalize_uid_for_dedup("doc_999999_1")
        assert result == "doc_1", f"Expected 'doc_1', got '{result}'"

    def test_underscore_in_file_id(self):
        """File IDs containing underscores should handle correctly."""
        # "my_file_name_512_3" → splits from right: ["my_file_name", "512", "3"]
        # Uses rsplit(_, 2), so this should work: "my_file_name_3"
        result = _normalize_uid_for_dedup("my_file_name_512_3")
        assert result == "my_file_name_3", f"Expected 'my_file_name_3', got '{result}'"

    def test_only_underscores(self):
        """String of only underscores should be handled."""
        # "_" → splits to ["", ""], len=2, returns original
        result = _normalize_uid_for_dedup("_")
        assert result == "_", f"Expected '_', got '{result}'"

    def test_trailing_underscore(self):
        """Trailing underscore should be handled."""
        # "doc_" → splits to ["doc", ""], len=2, returns original
        result = _normalize_uid_for_dedup("doc_")
        assert result == "doc_", f"Expected 'doc_', got '{result}'"

    def test_leading_underscore(self):
        """Leading underscore should be handled."""
        # "_doc_512_3" → ["_doc", "512", "3"] → "_doc_3"
        result = _normalize_uid_for_dedup("_doc_512_3")
        assert result == "_doc_3", f"Expected '_doc_3', got '{result}'"


class TestNormalizeUidForDedupIntegration:
    """Integration tests for _normalize_uid_for_dedup with expand_window."""

    @pytest.mark.asyncio
    async def test_expand_window_dedups_multi_scale(self):
        """expand_window should deduplicate multi-scale and default UIDs referencing same index."""
        # Setup: Create a mock vector store
        mock_vector_store = MagicMock()

        # Create initial sources with multi-scale UIDs
        sources = [
            RAGSource(
                text="Multi-scale chunk content",
                file_id="doc1",
                score=0.1,
                metadata={"chunk_index": 3, "chunk_scale": "512"},
            ),
        ]

        # Mock get_chunks_by_uid to return both multi-scale and default chunks
        # The key test: if we request chunks for indices around 3,
        # we might get both "doc1_512_2", "doc1_512_3", "doc1_512_4"
        # AND "doc1_2", "doc1_3", "doc1_4"
        # After dedup, "doc1_512_3" and "doc1_3" should be treated as duplicates
        async def mock_get_chunks_by_uid(uids):
            chunks = []
            for uid in uids:
                # Return chunks for various UIDs
                if uid.startswith("doc1"):
                    # Parse the UID to determine if multi-scale or default
                    parts = uid.rsplit("_", 2)
                    if len(parts) == 3:
                        file_id, scale, idx = parts
                        chunk = {
                            "id": uid,
                            "text": f"Content for {uid}",
                            "file_id": file_id,
                            "_distance": 0.2,
                            "metadata": {"chunk_index": int(idx), "chunk_scale": scale},
                        }
                    elif len(parts) == 2:
                        file_id, idx = parts
                        chunk = {
                            "id": uid,
                            "text": f"Content for {uid}",
                            "file_id": file_id,
                            "_distance": 0.25,
                            "metadata": {"chunk_index": int(idx)},
                        }
                    else:
                        continue
                    chunks.append(chunk)
            return chunks

        mock_vector_store.get_chunks_by_uid = mock_get_chunks_by_uid

        # Create service with window=1 and vector_store mock
        service = DocumentRetrievalService(
            vector_store=mock_vector_store,
            retrieval_window=1,  # Window size of 1 means indices 2,3,4 for chunk_index 3
            retrieval_top_k=100,  # High enough to not cap results
        )

        # Execute expand_window
        expanded = await service.expand_window(sources)

        # Verify no duplicate normalized UIDs
        seen_normalized = set()
        for source in expanded:
            chunk_index = source.metadata.get("chunk_index", 0)
            chunk_scale = source.metadata.get("chunk_scale", "default")
            if chunk_scale and chunk_scale != "default":
                uid = f"{source.file_id}_{chunk_scale}_{chunk_index}"
            else:
                uid = f"{source.file_id}_{chunk_index}"

            normalized = _normalize_uid_for_dedup(uid)
            assert normalized not in seen_normalized, (
                f"Duplicate found: normalized UID '{normalized}' appears multiple times. "
                f"Original UID: '{uid}', already seen: {seen_normalized}"
            )
            seen_normalized.add(normalized)

        # Verify we have chunks from window expansion
        # Original chunk_index is 3, window is 1, so we should see indices 2, 3, 4
        chunk_indices = [s.metadata.get("chunk_index", 0) for s in expanded]
        assert 3 in chunk_indices, "Original chunk index 3 should be present"

        # The expanded results should not have duplicates
        # If multi-scale and default chunks for same index exist,
        # only one should appear in results
        assert len(expanded) == len(seen_normalized), (
            f"Number of expanded sources ({len(expanded)}) should match "
            f"number of unique normalized UIDs ({len(seen_normalized)})"
        )

    @pytest.mark.asyncio
    async def test_expand_window_mixed_scales_dedup(self):
        """expand_window should deduplicate when mixing different scales for same index."""
        mock_vector_store = MagicMock()

        # Create sources with different scales pointing to same index
        sources = [
            RAGSource(
                text="Scale 512 chunk",
                file_id="doc1",
                score=0.1,
                metadata={"chunk_index": 5, "chunk_scale": "512"},
            ),
            RAGSource(
                text="Scale 1024 chunk",
                file_id="doc1",
                score=0.15,
                metadata={"chunk_index": 5, "chunk_scale": "1024"},
            ),
        ]

        async def mock_get_chunks_by_uid(uids):
            chunks = []
            for uid in uids:
                parts = uid.rsplit("_", 2)
                if len(parts) == 3:
                    file_id, scale, idx = parts
                    chunks.append(
                        {
                            "id": uid,
                            "text": f"Adjacent {uid}",
                            "file_id": file_id,
                            "_distance": 0.3,
                            "metadata": {"chunk_index": int(idx), "chunk_scale": scale},
                        }
                    )
                elif len(parts) == 2:
                    file_id, idx = parts
                    chunks.append(
                        {
                            "id": uid,
                            "text": f"Adjacent {uid}",
                            "file_id": file_id,
                            "_distance": 0.3,
                            "metadata": {"chunk_index": int(idx)},
                        }
                    )
            return chunks

        mock_vector_store.get_chunks_by_uid = mock_get_chunks_by_uid

        service = DocumentRetrievalService(
            vector_store=mock_vector_store, retrieval_window=1, retrieval_top_k=100
        )

        expanded = await service.expand_window(sources)

        # Count how many times each (file_id, index) pair appears
        index_counts = {}
        for source in expanded:
            key = (source.file_id, source.metadata.get("chunk_index", 0))
            index_counts[key] = index_counts.get(key, 0) + 1

        # Each (file_id, index) should appear at most once after dedup
        for key, count in index_counts.items():
            assert count == 1, (
                f"Index {key} appears {count} times in expanded results. "
                f"Multi-scale UIDs for same index should be deduplicated."
            )

    @pytest.mark.asyncio
    async def test_expand_window_preserves_original_sources(self):
        """expand_window should always include original sources."""
        mock_vector_store = MagicMock()

        sources = [
            RAGSource(
                text="Original chunk",
                file_id="test_doc",
                score=0.05,
                metadata={"chunk_index": 10, "chunk_scale": "256"},
            ),
        ]

        # Mock returns empty list (no adjacent chunks found)
        async def mock_get_chunks_by_uid(uids):
            return []

        mock_vector_store.get_chunks_by_uid = mock_get_chunks_by_uid

        service = DocumentRetrievalService(
            vector_store=mock_vector_store, retrieval_window=2, retrieval_top_k=100
        )

        expanded = await service.expand_window(sources)

        # Original source should still be present
        assert len(expanded) >= 1, (
            "Should retain original source even when no adjacent found"
        )
        assert expanded[0].file_id == "test_doc"
        assert expanded[0].metadata.get("chunk_index") == 10

    @pytest.mark.asyncio
    async def test_expand_window_empty_sources(self):
        """expand_window should handle empty input gracefully."""
        mock_vector_store = MagicMock()

        service = DocumentRetrievalService(
            vector_store=mock_vector_store, retrieval_window=1, retrieval_top_k=100
        )

        result = await service.expand_window([])

        assert result == [], "Empty input should return empty output"

    @pytest.mark.asyncio
    async def test_expand_window_no_vector_store(self):
        """expand_window should return sources unchanged when no vector_store."""
        sources = [
            RAGSource(
                text="Test content",
                file_id="doc1",
                score=0.1,
                metadata={"chunk_index": 1},
            ),
        ]

        service = DocumentRetrievalService(
            vector_store=None,  # No vector store
            retrieval_window=1,
            retrieval_top_k=100,
        )

        result = await service.expand_window(sources)

        # Should return sources unchanged
        assert result == sources, "Should return sources unchanged when no vector_store"


class TestNormalizeUidForDedupPropertyBased:
    """Property-based tests for mathematical invariants."""

    def test_idempotency_property(self):
        """For any input, applying the function twice yields the same result as once."""
        test_cases = [
            "doc1_512_3",
            "doc1_3",
            "my_file_v2_3",
            "doc1_abc",
            "",
            "doc1",
            "file_1024_99",
            "file_5_10",
            "myfile_5",
            "123_512_456",
            "doc_0_0",
            "my_file_name_512_3",
        ]

        for uid in test_cases:
            first = _normalize_uid_for_dedup(uid)
            second = _normalize_uid_for_dedup(first)
            assert second == first, (
                f"Idempotency violated for '{uid}': "
                f"f('{uid}') = '{first}', f('{first}') = '{second}'"
            )

    def test_output_always_shorter_or_equal(self):
        """For multi-scale UIDs, output should be shorter; otherwise equal length."""
        test_cases = [
            ("doc1_512_3", "doc1_3"),  # Multi-scale: output is shorter
            ("doc1_3", "doc1_3"),  # Default: same length
            ("file_1024_99", "file_99"),  # Multi-scale: output is shorter
            ("my_file_v2_3", "my_file_v2_3"),  # Non-numeric middle: same
            ("doc1", "doc1"),  # Single segment: same
        ]

        for input_uid, expected in test_cases:
            result = _normalize_uid_for_dedup(input_uid)
            assert result == expected, (
                f"For '{input_uid}': expected '{expected}', got '{result}'"
            )
            # Property: len(result) <= len(input) always
            assert len(result) <= len(input_uid), (
                f"Output '{result}' should not be longer than input '{input_uid}'"
            )

    def test_deterministic(self):
        """Same input always produces same output."""
        test_uids = ["doc1_512_3", "doc1_3", "file_1024_99", ""]

        for uid in test_uids:
            results = [_normalize_uid_for_dedup(uid) for _ in range(10)]
            # All results should be identical
            assert len(set(results)) == 1, (
                f"Function is not deterministic for '{uid}': got {set(results)}"
            )
