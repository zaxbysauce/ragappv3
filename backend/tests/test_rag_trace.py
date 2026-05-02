"""Tests for RAGTrace structured observability (P3.1)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.rag_trace import RAGTrace


class TestRAGTrace(unittest.TestCase):
    def test_to_dict_round_trip_keys(self):
        t = RAGTrace(original_query="hello")
        d = t.to_dict()
        # Spot-check that every required key is present.
        for key in (
            "original_query",
            "transformed_queries",
            "variants_dropped",
            "fts_status",
            "fts_exceptions",
            "fused_hits",
            "reranked_hits",
            "rerank_status",
            "filtered_hits",
            "distance_threshold",
            "distillation_before",
            "distillation_after",
            "parent_windows_expanded",
            "token_pack_included",
            "token_pack_skipped",
            "token_pack_truncated",
            "final_sources",
            "final_memories",
            "cited_sources",
            "cited_memories",
            "invalid_citations",
            "answer_supported",
            "exact_match_promoted",
            "multi_scale_used",
        ):
            self.assertIn(key, d, msg=f"missing trace key: {key}")
        self.assertEqual(d["original_query"], "hello")

    def test_to_dict_returns_lists_not_shared_references(self):
        t = RAGTrace(original_query="q")
        t.cited_sources.append("S1")
        d1 = t.to_dict()
        # Mutating the source list afterwards must not pollute prior dicts.
        t.cited_sources.append("S2")
        d2 = t.to_dict()
        self.assertEqual(d1["cited_sources"], ["S1"])
        self.assertEqual(d2["cited_sources"], ["S1", "S2"])


if __name__ == "__main__":
    unittest.main()
