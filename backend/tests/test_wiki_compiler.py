"""Tests for WikiCompiler deterministic extraction and memory promotion."""

import sqlite3
import tempfile
import unittest
from pathlib import Path


def _make_env():
    from app.models.database import run_migrations
    from app.services.wiki_compiler import WikiCompiler
    from app.services.wiki_store import WikiStore

    td = tempfile.mkdtemp()
    db_path = str(Path(td) / "test.db")
    run_migrations(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    conn.execute("INSERT OR IGNORE INTO vaults (id, name) VALUES (1, 'Test')")
    conn.commit()
    store = WikiStore(conn)
    compiler = WikiCompiler(conn, store)
    return conn, store, compiler


AFOMIS_TEXT = (
    "AFOMIS stands for Air Force Operational Medicine Information Systems. "
    "Justice Sakyi is the AFOMIS Chief and Major Justin Woods is his deputy."
)


class TestDeterministicExtraction(unittest.TestCase):

    def test_acronym_extracted(self):
        from app.services.wiki_compiler import extract_entities_from_text

        result = extract_entities_from_text(AFOMIS_TEXT)
        acronyms = {a["acronym"] for a in result.acronyms}
        self.assertIn("AFOMIS", acronyms)

    def test_full_name_extracted(self):
        from app.services.wiki_compiler import extract_entities_from_text

        result = extract_entities_from_text(AFOMIS_TEXT)
        full_names = {a["full_name"] for a in result.acronyms}
        self.assertTrue(
            any("Air Force Operational Medicine" in fn for fn in full_names),
            f"Expected full name in: {full_names}",
        )

    def test_person_entities_extracted(self):
        from app.services.wiki_compiler import extract_entities_from_text

        result = extract_entities_from_text(AFOMIS_TEXT)
        persons = set(result.persons)
        self.assertTrue(
            any("Sakyi" in p for p in persons),
            f"Justice Sakyi not found in {persons}",
        )
        self.assertTrue(
            any("Woods" in p for p in persons),
            f"Major Justin Woods not found in {persons}",
        )

    def test_role_claims_extracted(self):
        from app.services.wiki_compiler import extract_entities_from_text

        result = extract_entities_from_text(AFOMIS_TEXT)
        self.assertGreater(len(result.role_claims), 0)
        predicates = {rc["predicate"].lower() for rc in result.role_claims}
        self.assertTrue(any("chief" in p for p in predicates), f"chief not in {predicates}")

    def test_pronoun_resolved_via_org_context(self):
        from app.services.wiki_compiler import extract_entities_from_text

        result = extract_entities_from_text(AFOMIS_TEXT)
        deputy_claims = [
            rc for rc in result.role_claims if "deputy" in rc["predicate"].lower()
        ]
        self.assertGreater(len(deputy_claims), 0, "No deputy claim created")
        deputy_claim = deputy_claims[0]
        # Subject should be AFOMIS (resolved from org context)
        self.assertEqual(deputy_claim["subject"], "AFOMIS")


class TestPromoteMemory(unittest.TestCase):

    def setUp(self):
        self.conn, self.store, self.compiler = _make_env()

    def tearDown(self):
        self.conn.close()

    def _insert_memory(self, content: str, vault_id: int | None = 1) -> int:
        cur = self.conn.execute(
            "INSERT INTO memories (content, vault_id) VALUES (?, ?)",
            (content, vault_id),
        )
        self.conn.commit()
        return cur.lastrowid

    def test_afomis_promotion_creates_page(self):
        mem_id = self._insert_memory(AFOMIS_TEXT)
        result = self.compiler.promote_memory(memory_id=mem_id, vault_id=1)
        self.assertIsNotNone(result["page"])
        self.assertIn("afomis", result["page"].slug.lower())

    def test_afomis_promotion_creates_entities(self):
        mem_id = self._insert_memory(AFOMIS_TEXT)
        result = self.compiler.promote_memory(memory_id=mem_id, vault_id=1)
        entity_names = {e.canonical_name for e in result["entities"]}
        self.assertIn("AFOMIS", entity_names)

    def test_afomis_promotion_creates_person_entities(self):
        mem_id = self._insert_memory(AFOMIS_TEXT)
        result = self.compiler.promote_memory(memory_id=mem_id, vault_id=1)
        entity_names = {e.canonical_name for e in result["entities"]}
        self.assertTrue(
            any("Sakyi" in n for n in entity_names),
            f"Justice Sakyi not in {entity_names}",
        )
        self.assertTrue(
            any("Woods" in n for n in entity_names),
            f"Major Justin Woods not in {entity_names}",
        )

    def test_afomis_promotion_creates_claims(self):
        mem_id = self._insert_memory(AFOMIS_TEXT)
        result = self.compiler.promote_memory(memory_id=mem_id, vault_id=1)
        self.assertGreater(len(result["claims"]), 0)

    def test_afomis_promotion_claims_have_provenance(self):
        mem_id = self._insert_memory(AFOMIS_TEXT)
        result = self.compiler.promote_memory(memory_id=mem_id, vault_id=1)
        for claim in result["claims"]:
            self.assertGreater(
                len(claim.sources), 0,
                f"Claim {claim.id} '{claim.claim_text}' has no sources",
            )
            src = claim.sources[0]
            self.assertEqual(src.source_kind, "memory")
            self.assertEqual(src.memory_id, mem_id)

    def test_afomis_promotion_creates_relations(self):
        mem_id = self._insert_memory(AFOMIS_TEXT)
        result = self.compiler.promote_memory(memory_id=mem_id, vault_id=1)
        self.assertGreater(len(result["relations"]), 0)

    def test_promote_creates_chief_relation(self):
        mem_id = self._insert_memory(AFOMIS_TEXT)
        result = self.compiler.promote_memory(memory_id=mem_id, vault_id=1)
        predicates = {r.predicate.lower() for r in result["relations"]}
        self.assertTrue(any("chief" in p for p in predicates), f"chief not in {predicates}")

    def test_promote_creates_deputy_relation(self):
        mem_id = self._insert_memory(AFOMIS_TEXT)
        result = self.compiler.promote_memory(memory_id=mem_id, vault_id=1)
        predicates = {r.predicate.lower() for r in result["relations"]}
        self.assertTrue(any("deputy" in p for p in predicates), f"deputy not in {predicates}")

    def test_vault_scope_enforcement(self):
        """Memory with vault_id=2 must not be promoted to vault_id=1."""
        # Insert memory in a different vault
        self.conn.execute("INSERT OR IGNORE INTO vaults (id, name) VALUES (2, 'Other')")
        self.conn.commit()
        mem_id = self._insert_memory(AFOMIS_TEXT, vault_id=2)
        with self.assertRaises(PermissionError):
            self.compiler.promote_memory(memory_id=mem_id, vault_id=1)

    def test_promote_null_vault_memory_uses_request_vault(self):
        """Memory with vault_id=NULL should be promotable to any vault."""
        mem_id = self._insert_memory(AFOMIS_TEXT, vault_id=None)
        result = self.compiler.promote_memory(memory_id=mem_id, vault_id=1)
        self.assertEqual(result["page"].vault_id, 1)

    def test_promote_nonexistent_memory_raises(self):
        with self.assertRaises(ValueError):
            self.compiler.promote_memory(memory_id=99999, vault_id=1)
