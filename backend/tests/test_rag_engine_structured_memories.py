"""Tests for structured memories_used in RAGEngine done event.

Verifies that ``_build_done_message`` returns memories as structured dicts
with ``memory_label``, ``id``, ``content``, etc., instead of bare strings.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.memory_store import MemoryRecord
from app.services.rag_engine import RAGEngine


class TestStructuredMemoriesUsed(unittest.TestCase):
    def test_memories_used_is_structured(self):
        # Build a minimal RAGEngine without the heavy services — only
        # ``_build_done_message`` is exercised, which doesn't touch the
        # network-dependent components.
        engine = RAGEngine.__new__(RAGEngine)
        engine.max_distance_threshold = 0.5
        engine.vector_metric = "cosine"
        engine.retrieval_top_k = 10
        # _build_done_message reads document_retrieval.to_source_metadata, so
        # supply a minimal stub.

        class _StubDocRetrieval:
            def to_source_metadata(self, chunk, source_index):  # noqa: ARG002
                return {
                    "id": f"chunk-{source_index}",
                    "source_label": f"S{source_index}",
                    "filename": "f.txt",
                    "snippet": chunk.text,
                }

        engine.document_retrieval = _StubDocRetrieval()

        memories = [
            MemoryRecord(
                id=42,
                content="User likes terse answers.",
                category="preference",
                tags='["style","brief"]',
                source="chat",
                vault_id=1,
                created_at="2024-01-01",
                updated_at="2024-01-02",
            )
        ]

        done = engine._build_done_message(
            relevant_chunks=[],
            memories=memories,
            score_type="distance",
            hybrid_status="disabled",
            fts_exceptions=0,
            rerank_status="disabled",
        )

        self.assertEqual(done["type"], "done")
        self.assertIsInstance(done["memories_used"], list)
        self.assertEqual(len(done["memories_used"]), 1)
        m = done["memories_used"][0]
        self.assertEqual(m["memory_label"], "M1")
        self.assertEqual(m["content"], "User likes terse answers.")
        self.assertEqual(m["id"], "42")
        self.assertEqual(m["category"], "preference")
        self.assertEqual(m["vault_id"], 1)
        self.assertIn("score_type", m)


if __name__ == "__main__":
    unittest.main()
