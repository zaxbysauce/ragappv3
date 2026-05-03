"""Tests for WikiStore CRUD, search, and idempotent migrations."""

import sqlite3
import tempfile
import unittest
from pathlib import Path


class TestWikiMigration(unittest.TestCase):
    """Database migration creates all wiki tables and indexes idempotently."""

    def _make_db(self) -> str:
        td = tempfile.mkdtemp()
        return str(Path(td) / "test.db")

    def test_all_wiki_tables_created(self):
        from app.models.database import run_migrations

        db_path = self._make_db()
        run_migrations(db_path)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        tables = {
            r["name"]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        conn.close()
        expected = {
            "wiki_pages", "wiki_entities", "wiki_claims",
            "wiki_claim_sources", "wiki_relations",
            "wiki_compile_jobs", "wiki_lint_findings",
        }
        self.assertTrue(expected.issubset(tables), f"Missing tables: {expected - tables}")

    def test_fts_tables_created(self):
        from app.models.database import run_migrations

        db_path = self._make_db()
        run_migrations(db_path)
        conn = sqlite3.connect(db_path)
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        conn.close()
        for fts in ("wiki_pages_fts", "wiki_claims_fts", "wiki_entities_fts"):
            self.assertIn(fts, tables)

    def test_idempotent_double_run(self):
        from app.models.database import run_migrations

        db_path = self._make_db()
        run_migrations(db_path)
        run_migrations(db_path)  # must not raise

    def test_indexes_created(self):
        from app.models.database import run_migrations

        db_path = self._make_db()
        run_migrations(db_path)
        conn = sqlite3.connect(db_path)
        indexes = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
        }
        conn.close()
        expected_indexes = {
            "idx_wiki_pages_vault_type_status",
            "idx_wiki_pages_vault_slug",
            "idx_wiki_entities_vault_name",
            "idx_wiki_claims_vault_page_status",
            "idx_wiki_claim_sources_claim_id",
            "idx_wiki_compile_jobs_vault_status",
            "idx_wiki_lint_findings_vault_status_severity",
        }
        self.assertTrue(
            expected_indexes.issubset(indexes),
            f"Missing indexes: {expected_indexes - indexes}",
        )


def _make_store():
    """Create an in-memory SQLite connection with wiki schema and return WikiStore."""
    from app.models.database import run_migrations
    from app.services.wiki_store import WikiStore

    td = tempfile.mkdtemp()
    db_path = str(Path(td) / "test.db")
    run_migrations(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    # Insert default vault
    conn.execute("INSERT OR IGNORE INTO vaults (id, name) VALUES (1, 'Test Vault')")
    conn.commit()
    return WikiStore(conn), conn


class TestWikiStorePageCRUD(unittest.TestCase):

    def setUp(self):
        self.store, self.conn = _make_store()

    def tearDown(self):
        self.conn.close()

    def test_create_and_get_page(self):
        page = self.store.create_page(vault_id=1, title="AFOMIS Overview", page_type="overview")
        self.assertEqual(page.title, "AFOMIS Overview")
        self.assertEqual(page.slug, "afomis-overview")
        self.assertEqual(page.status, "draft")

        fetched = self.store.get_page(page.id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.id, page.id)

    def test_create_slug_normalized(self):
        page = self.store.create_page(vault_id=1, title="Air Force Systems!", page_type="system")
        self.assertNotIn("!", page.slug)
        self.assertIn("air-force-systems", page.slug)

    def test_list_pages(self):
        self.store.create_page(vault_id=1, title="Page A", page_type="entity")
        self.store.create_page(vault_id=1, title="Page B", page_type="acronym")
        pages = self.store.list_pages(vault_id=1)
        self.assertEqual(len(pages), 2)

    def test_list_pages_filter_by_type(self):
        self.store.create_page(vault_id=1, title="Page A", page_type="entity")
        self.store.create_page(vault_id=1, title="Page B", page_type="acronym")
        pages = self.store.list_pages(vault_id=1, page_type="acronym")
        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0].page_type, "acronym")

    def test_update_page(self):
        page = self.store.create_page(vault_id=1, title="Old Title", page_type="entity")
        updated = self.store.update_page(page.id, vault_id=1, title="New Title", status="verified")
        self.assertEqual(updated.title, "New Title")
        self.assertEqual(updated.status, "verified")

    def test_delete_page_nullifies_claim_page_id(self):
        page = self.store.create_page(vault_id=1, title="To Delete", page_type="entity")
        claim = self.store.create_claim(
            vault_id=1, claim_text="Test claim", source_type="manual", page_id=page.id
        )
        self.store.delete_page(page.id, vault_id=1)
        # Claim still exists with page_id = NULL (ON DELETE SET NULL)
        fetched_claim = self.store.get_claim(claim.id)
        self.assertIsNotNone(fetched_claim)
        self.assertIsNone(fetched_claim.page_id)

    def test_get_nonexistent_page(self):
        result = self.store.get_page(99999)
        self.assertIsNone(result)


class TestWikiStoreClaimCRUD(unittest.TestCase):

    def setUp(self):
        self.store, self.conn = _make_store()

    def tearDown(self):
        self.conn.close()

    def test_create_claim_with_source(self):
        page = self.store.create_page(vault_id=1, title="Test", page_type="entity")
        claim = self.store.create_claim(
            vault_id=1,
            claim_text="Justice Sakyi is the AFOMIS Chief",
            source_type="memory",
            page_id=page.id,
            subject="Justice Sakyi",
            predicate="chief",
            object="AFOMIS",
        )
        # Attach a provenance source
        self.store.attach_source(
            claim_id=claim.id,
            source_kind="memory",
            memory_id=42,
            quote="Justice Sakyi is the AFOMIS Chief",
        )
        self.conn.commit()

        fetched = self.store.get_claim(claim.id)
        self.assertEqual(fetched.claim_text, "Justice Sakyi is the AFOMIS Chief")
        self.assertEqual(len(fetched.sources), 1)
        self.assertEqual(fetched.sources[0].memory_id, 42)

    def test_claim_cascades_sources_on_delete(self):
        claim = self.store.create_claim(
            vault_id=1, claim_text="Test", source_type="manual"
        )
        self.store.attach_source(claim_id=claim.id, source_kind="manual")
        self.conn.commit()

        # Delete the claim — sources should cascade
        self.store.delete_claim(claim.id, vault_id=1)
        rows = self.conn.execute(
            "SELECT * FROM wiki_claim_sources WHERE claim_id = ?", (claim.id,)
        ).fetchall()
        self.assertEqual(len(rows), 0)

    def test_list_claims_by_page(self):
        page = self.store.create_page(vault_id=1, title="P", page_type="entity")
        self.store.create_claim(vault_id=1, claim_text="A", source_type="manual", page_id=page.id)
        self.store.create_claim(vault_id=1, claim_text="B", source_type="manual")
        claims = self.store.list_claims(vault_id=1, page_id=page.id)
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0].claim_text, "A")

    def test_update_claim(self):
        claim = self.store.create_claim(
            vault_id=1, claim_text="Original", source_type="manual"
        )
        updated = self.store.update_claim(claim.id, vault_id=1, claim_text="Updated", status="superseded")
        self.assertEqual(updated.claim_text, "Updated")
        self.assertEqual(updated.status, "superseded")


class TestWikiStoreEntityCRUD(unittest.TestCase):

    def setUp(self):
        self.store, self.conn = _make_store()

    def tearDown(self):
        self.conn.close()

    def test_upsert_entity_creates(self):
        entity = self.store.upsert_entity(
            vault_id=1,
            canonical_name="AFOMIS",
            entity_type="acronym",
            aliases=["Air Force Operational Medicine Information Systems"],
        )
        self.assertEqual(entity.canonical_name, "AFOMIS")
        self.assertIn("Air Force Operational Medicine Information Systems", entity.aliases)

    def test_upsert_entity_merges_aliases(self):
        self.store.upsert_entity(vault_id=1, canonical_name="AFOMIS", aliases=["Alias A"])
        entity = self.store.upsert_entity(vault_id=1, canonical_name="AFOMIS", aliases=["Alias B"])
        self.assertIn("Alias A", entity.aliases)
        self.assertIn("Alias B", entity.aliases)

    def test_entity_delete_cascades_relations(self):
        e1 = self.store.upsert_entity(vault_id=1, canonical_name="Org A")
        e2 = self.store.upsert_entity(vault_id=1, canonical_name="Person B")
        rel = self.store.create_relation(
            vault_id=1, predicate="chief", subject_entity_id=e1.id, object_entity_id=e2.id
        )
        # Delete entity e1 — relation should cascade
        self.conn.execute("DELETE FROM wiki_entities WHERE id = ?", (e1.id,))
        self.conn.commit()
        remaining = self.conn.execute(
            "SELECT * FROM wiki_relations WHERE id = ?", (rel.id,)
        ).fetchone()
        self.assertIsNone(remaining)


class TestWikiStoreFTSSearch(unittest.TestCase):

    def setUp(self):
        self.store, self.conn = _make_store()

    def tearDown(self):
        self.conn.close()

    def test_search_pages_by_title(self):
        self.store.create_page(vault_id=1, title="AFOMIS System Overview", page_type="overview")
        self.store.create_page(vault_id=1, title="Budget Report", page_type="manual")
        result = self.store.search(vault_id=1, query="AFOMIS")
        page_titles = [p.title for p in result["pages"]]
        self.assertIn("AFOMIS System Overview", page_titles)
        self.assertNotIn("Budget Report", page_titles)

    def test_search_claims_by_text(self):
        claim = self.store.create_claim(
            vault_id=1, claim_text="Justice Sakyi is AFOMIS Chief", source_type="manual"
        )
        result = self.store.search(vault_id=1, query="Justice Sakyi")
        claim_ids = [c.id for c in result["claims"]]
        self.assertIn(claim.id, claim_ids)

    def test_search_no_results(self):
        result = self.store.search(vault_id=1, query="xyznonexistent")
        self.assertEqual(result["pages"], [])
        self.assertEqual(result["claims"], [])
        self.assertEqual(result["entities"], [])
