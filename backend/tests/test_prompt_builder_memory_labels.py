"""Tests for [M#] labeling and system prompt updates in prompt_builder."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.document_retrieval import RAGSource
from app.services.memory_store import MemoryRecord
from app.services.prompt_builder import PromptBuilderService


def _record(idx: int, content: str) -> MemoryRecord:
    return MemoryRecord(
        id=idx,
        content=content,
        category=None,
        tags=None,
        source=None,
        vault_id=1,
    )


class TestMemoryLabelsInPrompt(unittest.TestCase):
    def test_memories_get_m_labels(self):
        builder = PromptBuilderService()
        memories = [
            _record(1, "User prefers concise reports."),
            _record(2, "User likes citations."),
        ]
        messages = builder.build_messages(
            user_input="How should I write the report?",
            chat_history=[],
            chunks=[],
            memories=memories,
        )
        # Last message is the user content with embedded context.
        user_content = messages[-1]["content"]
        self.assertIn("[M1]", user_content)
        self.assertIn("[M2]", user_content)
        self.assertIn("User prefers concise reports.", user_content)
        self.assertIn("User likes citations.", user_content)

    def test_no_memory_labels_when_no_memories(self):
        builder = PromptBuilderService()
        messages = builder.build_messages(
            user_input="hello",
            chat_history=[],
            chunks=[],
            memories=[],
        )
        user_content = messages[-1]["content"]
        self.assertNotIn("[M1]", user_content)

    def test_system_prompt_explains_separate_label_spaces(self):
        builder = PromptBuilderService()
        sp = builder.build_system_prompt()
        self.assertIn("[S1]", sp)
        self.assertIn("[M1]", sp)
        # Must explicitly tell the model NOT to cite memories as [S#].
        self.assertIn("never cite a memory as [S#]", sp.replace("\n", " "))

    def test_memory_labels_independent_of_source_count(self):
        """Memory [M1] starts at 1 even when there are document sources S1, S2."""
        builder = PromptBuilderService()
        chunks = [
            RAGSource(text="doc1", file_id="f1", score=0.1, metadata={"filename": "a"}),
            RAGSource(text="doc2", file_id="f2", score=0.2, metadata={"filename": "b"}),
        ]
        memories = [_record(10, "User X.")]
        messages = builder.build_messages(
            user_input="Q",
            chat_history=[],
            chunks=chunks,
            memories=memories,
        )
        user_content = messages[-1]["content"]
        self.assertIn("[M1]", user_content)
        # Sources still get [S#] labels — independent namespace.
        self.assertIn("[S1]", user_content)


if __name__ == "__main__":
    unittest.main()
