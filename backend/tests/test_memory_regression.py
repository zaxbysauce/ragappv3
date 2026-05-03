"""Regression tests for the AFOMIS memory retrieval bug.

Root cause: _fts_search() sent raw natural-language queries to SQLite FTS5.
"who is the afomis chief?" contains "?" which causes a FTS5 syntax error,
and stop words like "who" would cause AND-match failures on memories that
don't contain those tokens. Fixed by tokenizing and removing stop words.

Also tests the memories_used cited-only contract fix in _build_done_message.
"""

import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional, cast

# Stub optional heavy dependencies not installed in the test env.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

for _mod in ('lancedb', 'pyarrow'):
    if _mod not in sys.modules:
        try:
            __import__(_mod)
        except ImportError:
            _stub = types.ModuleType(_mod)
            sys.modules[_mod] = _stub

# lancedb.index must exist before vector_store.py is imported
if 'lancedb.index' not in sys.modules:
    _ldb_idx = types.ModuleType('lancedb.index')
    _ldb_idx.FTS = type('FTS', (), {})
    _ldb_idx.IvfPq = type('IvfPq', (), {})
    sys.modules['lancedb.index'] = _ldb_idx

try:
    from unstructured.partition.auto import partition  # noqa: F401
except ImportError:
    for _sub in ('partition', 'partition.auto', 'chunking', 'chunking.title',
                 'documents', 'documents.elements'):
        sys.modules.setdefault(f'unstructured.{_sub}', types.ModuleType(f'unstructured.{_sub}'))
    sys.modules.setdefault('unstructured', types.ModuleType('unstructured'))

from app.models.database import SQLiteConnectionPool, init_db
from app.services.memory_store import MemoryRecord, MemoryStore
from app.services.rag_engine import RAGEngine

AFOMIS_MEMORY = (
    "AFOMIS stands for Air Force Operational Medicine Information Systems. "
    "Justice Sakyi is the AFOMIS Chief and Major Justin Woods is his deputy."
)


class TestFTSQueryNormalization(unittest.TestCase):
    """Unit tests for the FTS stop-word tokenization fix."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test.db"
        init_db(str(self.db_path))
        self.pool = SQLiteConnectionPool(str(self.db_path), max_size=2)
        self.store = MemoryStore(pool=self.pool)

    def tearDown(self):
        self.pool.close_all()
        if self.db_path.exists():
            os.remove(self.db_path)
        os.rmdir(self.temp_dir)

    def test_raw_fts_question_words_do_not_block_memory(self):
        """Natural-language question words must not prevent FTS retrieval."""
        self.store.add_memory(content=AFOMIS_MEMORY, category="facts", source="user input")
        results = self.store.search_memories("who is the afomis chief?")
        self.assertTrue(
            len(results) > 0,
            "AFOMIS memory must be retrievable with a natural-language question query"
        )
        self.assertTrue(
            any("AFOMIS" in r.content for r in results),
            "Retrieved memory must contain AFOMIS"
        )

    def test_memory_retrieved_without_dense_embedding(self):
        """FTS must retrieve memories even when embedding IS NULL."""
        from app.models.database import migrate_add_memory_embedding_column
        migrate_add_memory_embedding_column(str(self.db_path))

        self.store.add_memory(content=AFOMIS_MEMORY, category="facts", source="user input")
        # Explicitly null out any embedding that may have been written
        conn = self.pool.get_connection()
        try:
            conn.execute("UPDATE memories SET embedding = NULL")
            conn.commit()
        finally:
            self.pool.release_connection(conn)

        results = self.store.search_memories("who is the afomis chief?")
        self.assertTrue(
            len(results) > 0,
            "FTS must find the memory even when embedding IS NULL"
        )

    def test_afmedcom_query_does_not_retrieve_afomis_memory(self):
        """AND query must NOT return AFOMIS memory for AFMEDCOM query."""
        self.store.add_memory(content=AFOMIS_MEMORY, category="facts", source="user input")
        results = self.store.search_memories("who is the afmedcom chief?")
        # "afmedcom" is not in the AFOMIS memory content; AND query must return nothing.
        self.assertEqual(
            0, len(results),
            "AFOMIS memory must not be retrieved for an AFMEDCOM query"
        )

    def test_punctuation_in_query_does_not_cause_fts_syntax_error(self):
        """Punctuation like '?' must not cause a SQLite FTS5 syntax error."""
        self.store.add_memory(content=AFOMIS_MEMORY)
        try:
            self.store.search_memories("who is the afomis chief?")
        except Exception as exc:
            self.fail(f"FTS query raised an exception: {exc}")


class TestMemoriesUsedContract(unittest.TestCase):
    """Unit tests for the memories_used cited-only contract in _build_done_message."""

    def _make_engine(self):
        return RAGEngine.__new__(RAGEngine)

    def _build_done(self, memories, response_text):
        """Call _build_done_message with the cited labels parsed from response_text."""
        from app.services.citation_validator import parse_citations
        _, cited_memories = parse_citations(response_text)
        engine = self._make_engine()
        # _build_done_message only needs document_retrieval for source building;
        # we pass empty chunks so that path is bypassed.
        from app.services.document_retrieval import DocumentRetrievalService
        engine.document_retrieval = DocumentRetrievalService.__new__(DocumentRetrievalService)
        engine.document_retrieval.max_distance_threshold = None
        engine.document_retrieval.vector_metric = "cosine"
        engine.document_retrieval.retrieval_top_k = 5
        engine.document_retrieval.retrieval_window = None
        engine.max_distance_threshold = None
        engine.vector_metric = "cosine"
        engine.retrieval_top_k = 5
        engine.retrieval_window = None

        return engine._build_done_message(
            relevant_chunks=[],
            memories=memories,
            score_type="rerank",
            hybrid_status="dense_only",
            fts_exceptions=0,
            rerank_status="disabled",
            cited_labels=set(cited_memories),
        )

    def test_memories_used_contains_only_cited_memories(self):
        """memories_used must contain only memories cited in the LLM response."""
        m1 = MemoryRecord(id=1, content="Fact one", category=None, tags=None, source=None)
        m2 = MemoryRecord(id=2, content="Fact two", category=None, tags=None, source=None)

        done = self._build_done([m1, m2], response_text="Fact one [M1]")
        labels = [m["memory_label"] for m in done["memories_used"]]
        self.assertIn("M1", labels, "M1 must appear (it was cited)")
        self.assertNotIn("M2", labels, "M2 must not appear (it was not cited)")

    def test_memories_used_empty_when_no_citation(self):
        """memories_used must be empty when no [M#] appears in the response."""
        m1 = MemoryRecord(id=1, content="Fact one", category=None, tags=None, source=None)
        done = self._build_done([m1], response_text="I don't know")
        self.assertEqual([], done["memories_used"])

    def test_memories_used_preserves_original_labels(self):
        """Label numbers must not be renumbered after filtering."""
        m1 = MemoryRecord(id=1, content="First", category=None, tags=None, source=None)
        m2 = MemoryRecord(id=2, content="Second", category=None, tags=None, source=None)
        m3 = MemoryRecord(id=3, content="Third", category=None, tags=None, source=None)
        # Response cites M1 and M3 (skipping M2)
        done = self._build_done([m1, m2, m3], response_text="First [M1] and Third [M3]")
        labels = [m["memory_label"] for m in done["memories_used"]]
        self.assertEqual(["M1", "M3"], labels, "Original labels must be preserved, not renumbered")

    def test_score_type_from_memory_record(self):
        """score_type must reflect actual retrieval path, not hardcoded 'fts'."""
        m1 = MemoryRecord(id=1, content="Dense fact", category=None, tags=None,
                          source=None, score=0.85, score_type="dense")
        done = self._build_done([m1], response_text="Dense fact [M1]")
        self.assertEqual("dense", done["memories_used"][0]["score_type"])

    def test_afomis_memory_cited_contract(self):
        """AFOMIS memory cited as [M1] must appear in memories_used."""
        mem = MemoryRecord(
            id=1, content=AFOMIS_MEMORY, category="facts", tags=None, source="user input"
        )
        done = self._build_done(
            [mem],
            response_text="Based on stored memory, Justice Sakyi is the AFOMIS Chief. [M1]"
        )
        self.assertEqual(1, len(done["memories_used"]))
        self.assertEqual("M1", done["memories_used"][0]["memory_label"])
        self.assertIn("Justice Sakyi", done["memories_used"][0]["content"])


if __name__ == "__main__":
    unittest.main()
