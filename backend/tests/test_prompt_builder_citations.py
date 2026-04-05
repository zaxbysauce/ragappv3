"""Tests for the prompt builder's stable source label citation contract.

Validates that:
- Prompt builder emits stable source labels [S1], [S2], etc.
- Context is structured into primary/supporting evidence
- Duplicate filenames do not break citation mapping
"""

import unittest
from unittest.mock import patch, MagicMock
from dataclasses import dataclass, field
from typing import Any, Dict


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


if __name__ == "__main__":
    unittest.main()
