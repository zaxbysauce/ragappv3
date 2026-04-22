"""Tests for the prompt builder's stable source label citation contract.

Validates that:
- Prompt builder emits stable source labels [S1], [S2], etc.
- Context is structured into primary/supporting evidence
- Duplicate filenames do not break citation mapping
"""

import unittest
from dataclasses import dataclass, field
from typing import Any, Dict
from unittest.mock import patch


@dataclass
class MockRAGSource:
    text: str
    file_id: str
    score: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MockMemory:
    content: str


class TestPromptBuilderCitations(unittest.TestCase):
    """Test stable source label citation contract."""

    def setUp(self):
        # Mock settings to avoid env dependencies
        with patch("app.config.settings") as mock_settings:
            mock_settings.max_context_chunks = 10
            from app.services.prompt_builder import PromptBuilderService
            self.builder = PromptBuilderService()

    def test_format_chunk_produces_stable_label(self):
        """format_chunk should produce [S1], [S2] labels."""
        chunk = MockRAGSource(
            text="Some document text here.",
            file_id="doc123",
            score=0.85,
            metadata={"source_file": "report.pdf"},
        )
        result = self.builder.format_chunk(chunk, source_index=1)
        self.assertIn("[S1]", result)
        self.assertIn("report.pdf", result)
        self.assertIn("score: 0.85", result)
        self.assertIn("Some document text here.", result)

    def test_format_chunk_includes_section(self):
        """format_chunk should include section info when available."""
        chunk = MockRAGSource(
            text="Introduction text.",
            file_id="doc456",
            score=0.72,
            metadata={
                "source_file": "manual.pdf",
                "section_title": "Chapter 1: Introduction",
            },
        )
        result = self.builder.format_chunk(chunk, source_index=3)
        self.assertIn("[S3]", result)
        self.assertIn("Section: Chapter 1: Introduction", result)

    def test_build_messages_splits_primary_and_supporting(self):
        """build_messages should structure context into primary/supporting evidence."""
        chunks = [
            MockRAGSource(
                text=f"Chunk {i} text.",
                file_id=f"file{i}",
                score=0.9 - i * 0.1,
                metadata={"source_file": f"doc{i}.pdf"},
            )
            for i in range(6)
        ]
        memories = []
        messages = self.builder.build_messages(
            "What is X?", [], chunks, memories
        )
        user_msg = messages[-1]["content"]
        self.assertIn("Primary Evidence:", user_msg)
        self.assertIn("Supporting Evidence:", user_msg)
        self.assertIn("[S1]", user_msg)
        self.assertIn("[S6]", user_msg)

    def test_build_messages_no_context(self):
        """build_messages should handle empty chunks gracefully."""
        messages = self.builder.build_messages("What is X?", [], [], [])
        user_msg = messages[-1]["content"]
        self.assertIn("No relevant documents found", user_msg)

    def test_system_prompt_uses_stable_labels(self):
        """System prompt should instruct model to use [S#] labels, not filenames."""
        system_msg = self.builder.build_system_prompt()
        self.assertIn("[S1]", system_msg)
        self.assertNotIn("[Source: filename]", system_msg)

    def test_duplicate_filenames_get_distinct_labels(self):
        """Chunks with the same filename should get distinct [S#] labels."""
        chunks = [
            MockRAGSource(
                text="First chunk from report.",
                file_id="file1",
                score=0.9,
                metadata={"source_file": "report.pdf"},
            ),
            MockRAGSource(
                text="Second chunk from same file.",
                file_id="file1",
                score=0.8,
                metadata={"source_file": "report.pdf"},
            ),
            MockRAGSource(
                text="Third chunk from different file with same name.",
                file_id="file2",
                score=0.7,
                metadata={"source_file": "report.pdf"},
            ),
        ]
        messages = self.builder.build_messages("Tell me about reports", [], chunks, [])
        user_msg = messages[-1]["content"]
        self.assertIn("[S1]", user_msg)
        self.assertIn("[S2]", user_msg)
        self.assertIn("[S3]", user_msg)


class TestAnchorBestChunk(unittest.TestCase):
    """Tests for the ANCHOR_BEST_CHUNK lost-in-the-middle mitigation."""

    def _builder_with_settings(self, anchor_best_chunk=True, context_max_tokens=6000, primary_evidence_count=0):
        """Create a PromptBuilderService with mocked settings."""
        with patch("app.services.prompt_builder.settings") as mock_settings:
            mock_settings.max_context_chunks = 10
            mock_settings.anchor_best_chunk = anchor_best_chunk
            mock_settings.context_max_tokens = context_max_tokens
            mock_settings.primary_evidence_count = primary_evidence_count
            from app.services.prompt_builder import PromptBuilderService
            return PromptBuilderService()

    def _build_messages(self, builder, chunks, anchor_best_chunk=True, context_max_tokens=6000, primary_evidence_count=0):
        """Call build_messages with mocked settings."""
        with patch("app.services.prompt_builder.settings") as mock_settings:
            mock_settings.anchor_best_chunk = anchor_best_chunk
            mock_settings.context_max_tokens = context_max_tokens
            mock_settings.primary_evidence_count = primary_evidence_count
            return builder.build_messages("What is X?", [], chunks, [])

    def test_anchor_enabled_top_chunk_appears_at_end(self):
        """When ANCHOR_BEST_CHUNK=True, top-ranked chunk is repeated at end of context."""
        chunks = [
            MockRAGSource(
                text="The definitive answer to everything.",
                file_id="doc1",
                score=0.99,
                metadata={"source_file": "top.pdf"},
            ),
            MockRAGSource(
                text="Secondary context.",
                file_id="doc2",
                score=0.7,
                metadata={"source_file": "other.pdf"},
            ),
        ]
        builder = self._builder_with_settings(anchor_best_chunk=True)
        messages = self._build_messages(builder, chunks, anchor_best_chunk=True)
        user_msg = messages[-1]["content"]
        # Top chunk text must appear at least twice (once in Primary Evidence, once anchored)
        assert user_msg.count("The definitive answer to everything.") == 2, (
            "Top chunk should appear twice when anchor is enabled"
        )
        # The anchor label must be present
        assert "[BEST MATCH — repeated for emphasis]" in user_msg

    def test_anchor_disabled_top_chunk_appears_once(self):
        """When ANCHOR_BEST_CHUNK=False, top-ranked chunk appears exactly once."""
        chunks = [
            MockRAGSource(
                text="The definitive answer.",
                file_id="doc1",
                score=0.99,
                metadata={"source_file": "top.pdf"},
            ),
            MockRAGSource(
                text="Secondary context.",
                file_id="doc2",
                score=0.7,
                metadata={"source_file": "other.pdf"},
            ),
        ]
        builder = self._builder_with_settings(anchor_best_chunk=False)
        messages = self._build_messages(builder, chunks, anchor_best_chunk=False)
        user_msg = messages[-1]["content"]
        assert user_msg.count("The definitive answer.") == 1
        assert "[BEST MATCH — repeated for emphasis]" not in user_msg

    def test_anchor_skipped_for_oversized_top_chunk(self):
        """Anchor is skipped when top chunk exceeds 50% of context_max_tokens."""
        # context_max_tokens = 100; top chunk ~ 60 tokens = > 50%
        large_text = "X" * 250  # ~71 tokens (> 100 * 0.5 = 50)
        chunks = [
            MockRAGSource(
                text=large_text,
                file_id="doc1",
                score=0.99,
                metadata={"source_file": "big.pdf"},
            ),
            MockRAGSource(
                text="Small context.",
                file_id="doc2",
                score=0.6,
                metadata={"source_file": "small.pdf"},
            ),
        ]
        builder = self._builder_with_settings(anchor_best_chunk=True, context_max_tokens=100)
        messages = self._build_messages(
            builder, chunks, anchor_best_chunk=True, context_max_tokens=100
        )
        user_msg = messages[-1]["content"]
        # Top chunk should appear only once (anchor skipped due to size)
        assert user_msg.count(large_text) == 1
        assert "[BEST MATCH — repeated for emphasis]" not in user_msg

    def test_anchor_not_added_when_no_chunks(self):
        """Anchor is not added when there are no chunks."""
        builder = self._builder_with_settings(anchor_best_chunk=True)
        messages = self._build_messages(builder, [], anchor_best_chunk=True)
        user_msg = messages[-1]["content"]
        assert "[BEST MATCH — repeated for emphasis]" not in user_msg

    def test_anchor_top_chunk_uses_s1_label(self):
        """Anchored chunk uses the [S1] label (same source index as original)."""
        chunks = [
            MockRAGSource(
                text="Answer here.",
                file_id="doc1",
                score=0.9,
                metadata={"source_file": "doc.pdf"},
            ),
        ]
        builder = self._builder_with_settings(anchor_best_chunk=True)
        messages = self._build_messages(builder, chunks, anchor_best_chunk=True)
        user_msg = messages[-1]["content"]
        # [S1] label should appear at least twice (original + anchor)
        assert user_msg.count("[S1]") >= 2


if __name__ == "__main__":
    unittest.main()
