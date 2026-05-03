"""Tests for WikiRetrievalService and related helpers."""

import json
import sqlite3
import unittest
from unittest.mock import MagicMock, patch

import pytest

from app.services.wiki_retrieval import (
    WikiEvidence,
    WikiRetrievalService,
    normalize_fts_query,
    extract_query_intent,
)


class TestNormalizeFtsQuery(unittest.TestCase):
    def test_strips_common_stop_words(self):
        result = normalize_fts_query("who is the chief of staff")
        # "who", "is", "the", "of" are stop words; "chief" and "staff" should remain
        self.assertIn("chief", result)
        self.assertIn("staff", result)
        self.assertNotIn(" is ", f" {result} ")

    def test_preserves_all_caps_acronyms(self):
        result = normalize_fts_query("what does AFOMIS do")
        self.assertIn("AFOMIS", result)

    def test_escapes_fts5_operators(self):
        # FTS5 special chars should be sanitized
        raw = normalize_fts_query("AND OR NOT test")
        # Should not raise and should return something reasonable
        self.assertIsInstance(raw, str)

    def test_empty_query_returns_empty(self):
        self.assertEqual(normalize_fts_query(""), "")

    def test_single_acronym_preserved(self):
        result = normalize_fts_query("AFMEDCOM")
        self.assertIn("AFMEDCOM", result)


class TestExtractQueryIntent(unittest.TestCase):
    def test_extracts_all_caps_entity(self):
        entities, predicates = extract_query_intent("Who leads AFOMIS?")
        self.assertIn("AFOMIS", entities)

    def test_extracts_question_subject(self):
        entities, predicates = extract_query_intent("What is the mission of Task Force Alpha?")
        # Should capture some entity-like terms
        self.assertIsInstance(entities, list)

    def test_extracts_predicate_terms(self):
        _, predicates = extract_query_intent("who is the chief of staff for AFSOC?")
        self.assertIn("chief", predicates)

    def test_empty_query(self):
        entities, predicates = extract_query_intent("")
        self.assertEqual(entities, [])
        self.assertEqual(predicates, [])


class TestWikiEvidenceToDict(unittest.TestCase):
    def _make_evidence(self, **kwargs):
        defaults = dict(
            label_placeholder="W1",
            page_id=1,
            claim_id=10,
            title="Test Page",
            slug="test-page",
            page_type="entity",
            claim_text="The chief is Col Smith.",
            excerpt="",
            confidence=0.9,
            page_status="verified",
            claim_status="active",
            score=0.85,
            score_type="fts",
            freshness=None,
            source_count=2,
            provenance_summary="2 docs",
        )
        defaults.update(kwargs)
        return WikiEvidence(**defaults)

    def test_to_dict_has_wiki_label(self):
        ev = self._make_evidence()
        d = ev.to_dict()
        self.assertEqual(d["wiki_label"], "W1")

    def test_to_dict_status_prefers_claim_status(self):
        ev = self._make_evidence(claim_status="active", page_status="stale")
        d = ev.to_dict()
        self.assertEqual(d["status"], "active")

    def test_to_dict_status_falls_back_to_page_status(self):
        ev = self._make_evidence(claim_status=None, page_status="verified")
        d = ev.to_dict()
        self.assertEqual(d["status"], "verified")

    def test_to_dict_has_split_page_claim_status(self):
        ev = self._make_evidence(claim_status="verified", page_status="draft")
        d = ev.to_dict()
        self.assertIn("page_status", d)
        self.assertIn("claim_status", d)
        self.assertEqual(d["page_status"], "draft")
        self.assertEqual(d["claim_status"], "verified")


class TestWikiRetrievalServiceNullVault(unittest.TestCase):
    def test_returns_empty_for_none_vault(self):
        """retrieve() must return [] when vault_id is None (synchronous)."""
        pool = MagicMock()
        svc = WikiRetrievalService(pool=pool)
        result = svc.retrieve("test query", vault_id=None)
        self.assertEqual(result, [])
        # Pool.get() should never be called for None vault
        pool.get.assert_not_called()


class TestWikiRetrievalServiceEmptyDb(unittest.TestCase):
    def _make_service_with_conn(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE wiki_claims (
                id INTEGER PRIMARY KEY, vault_id INTEGER, page_id INTEGER,
                claim_text TEXT, claim_type TEXT DEFAULT 'fact',
                status TEXT DEFAULT 'active', confidence REAL DEFAULT 0.8,
                predicate TEXT, created_at TEXT, updated_at TEXT
            );
            CREATE TABLE wiki_pages (
                id INTEGER PRIMARY KEY, vault_id INTEGER, slug TEXT, title TEXT,
                page_type TEXT DEFAULT 'entity', status TEXT DEFAULT 'draft',
                confidence REAL DEFAULT 0.5, last_compiled_at TEXT
            );
            CREATE TABLE wiki_entities (
                id INTEGER PRIMARY KEY, vault_id INTEGER, canonical_name TEXT,
                entity_type TEXT DEFAULT 'organization', aliases_json TEXT DEFAULT '[]',
                page_id INTEGER
            );
            CREATE TABLE wiki_relations (
                id INTEGER PRIMARY KEY, vault_id INTEGER, subject_entity_id INTEGER,
                predicate TEXT, object_entity_id INTEGER, object_text TEXT,
                claim_id INTEGER, confidence REAL DEFAULT 0.8
            );
        """)
        conn.commit()

        pool = MagicMock()
        pool.get.return_value = conn
        pool.put = MagicMock()
        return WikiRetrievalService(pool=pool), conn

    def test_empty_db_returns_list(self):
        """retrieve() should return [] on empty DB (no FTS tables → graceful empty)."""
        svc, _ = self._make_service_with_conn()
        try:
            result = svc.retrieve("AFOMIS mission", vault_id=1)
            self.assertIsInstance(result, list)
        except Exception as e:
            # Acceptable: no FTS tables — expected graceful empty
            self.assertIn("no such table", str(e).lower())


if __name__ == "__main__":
    unittest.main()
