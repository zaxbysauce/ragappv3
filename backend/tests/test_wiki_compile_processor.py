"""Tests for WikiCompileProcessor and the new WikiCompiler job methods."""

import asyncio
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
    conn.execute(
        "INSERT OR IGNORE INTO files (id, vault_id, file_path, file_name, file_size, status) "
        "VALUES (1, 1, '/tmp/test.txt', 'test.txt', 100, 'indexed')"
    )
    conn.commit()
    store = WikiStore(conn)
    compiler = WikiCompiler(conn, store)
    return conn, store, compiler


AFOMIS_ANSWER = (
    "AFOMIS stands for Air Force Operational Medicine Information Systems. "
    "Justice Sakyi is the AFOMIS Chief and Major Justin Woods is his deputy."
)


# ---------------------------------------------------------------------------
# WikiCompiler.compile_query_job
# ---------------------------------------------------------------------------

class TestCompileQueryJob(unittest.TestCase):

    def setUp(self):
        self.conn, self.store, self.compiler = _make_env()

    def tearDown(self):
        self.conn.close()

    def test_returns_skipped_when_no_answer(self):
        result = self.compiler.compile_query_job(vault_id=1, input_json={})
        self.assertTrue(result.get("skipped"))

    def test_returns_skipped_when_no_extractable_entities(self):
        result = self.compiler.compile_query_job(
            vault_id=1,
            input_json={"assistant_answer": "The weather is fine today."},
        )
        self.assertTrue(result.get("skipped"))

    def test_creates_entities_from_answer(self):
        result = self.compiler.compile_query_job(
            vault_id=1,
            input_json={
                "assistant_answer": AFOMIS_ANSWER,
                "wiki_refs": [{"wiki_label": "W1"}],
                "doc_sources": [],
                "memories": [],
            },
        )
        self.assertFalse(result.get("skipped"))
        entity_names = {e["name"] for e in result["entities"]}
        self.assertIn("AFOMIS", entity_names)

    def test_creates_active_claims_with_citations(self):
        result = self.compiler.compile_query_job(
            vault_id=1,
            input_json={
                "assistant_answer": AFOMIS_ANSWER,
                "wiki_refs": [{"wiki_label": "W1"}],
                "doc_sources": [],
                "memories": [],
            },
        )
        statuses = {c["status"] for c in result["claims"]}
        self.assertIn("active", statuses)
        self.assertNotIn("unverified", statuses)

    def test_creates_unverified_claims_without_citations(self):
        result = self.compiler.compile_query_job(
            vault_id=1,
            input_json={
                "assistant_answer": AFOMIS_ANSWER,
                "wiki_refs": [],
                "doc_sources": [],
                "memories": [],
            },
        )
        statuses = {c["status"] for c in result["claims"]}
        self.assertIn("unverified", statuses)

    def test_creates_lint_finding_for_unverified_claim(self):
        self.compiler.compile_query_job(
            vault_id=1,
            input_json={
                "assistant_answer": AFOMIS_ANSWER,
                "wiki_refs": [],
                "doc_sources": [],
                "memories": [],
            },
        )
        rows = self.conn.execute(
            "SELECT finding_type FROM wiki_lint_findings WHERE vault_id = 1"
        ).fetchall()
        finding_types = {dict(r)["finding_type"] for r in rows}
        self.assertIn("unsupported_claim", finding_types)

    def test_no_lint_finding_with_citations(self):
        self.compiler.compile_query_job(
            vault_id=1,
            input_json={
                "assistant_answer": AFOMIS_ANSWER,
                "wiki_refs": [{"wiki_label": "W1"}],
                "doc_sources": [],
                "memories": [],
            },
        )
        rows = self.conn.execute(
            "SELECT finding_type FROM wiki_lint_findings WHERE vault_id = 1"
        ).fetchall()
        finding_types = {dict(r)["finding_type"] for r in rows}
        self.assertNotIn("unsupported_claim", finding_types)


# ---------------------------------------------------------------------------
# WikiCompiler.compile_ingest_job
# ---------------------------------------------------------------------------

class TestCompileIngestJob(unittest.TestCase):

    def setUp(self):
        self.conn, self.store, self.compiler = _make_env()
        # Write a temporary text file with extractable content
        self._tmpfile = tempfile.NamedTemporaryFile(
            suffix=".txt", mode="w", delete=False, encoding="utf-8"
        )
        self._tmpfile.write(AFOMIS_ANSWER)
        self._tmpfile.close()
        # Update file record to point to our temp file
        self.conn.execute(
            "UPDATE files SET file_path = ?, file_name = ? WHERE id = 1",
            (self._tmpfile.name, "afomis.txt"),
        )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        import os
        try:
            os.unlink(self._tmpfile.name)
        except OSError:
            pass

    def test_returns_skipped_when_no_file_id(self):
        result = self.compiler.compile_ingest_job(vault_id=1, input_json={})
        self.assertTrue(result.get("skipped"))

    def test_raises_when_file_not_in_vault(self):
        with self.assertRaises(ValueError):
            self.compiler.compile_ingest_job(
                vault_id=999, input_json={"file_id": 1}
            )

    def test_creates_page_for_document(self):
        result = self.compiler.compile_ingest_job(
            vault_id=1, input_json={"file_id": 1}
        )
        self.assertIsNotNone(result.get("page"))
        self.assertIn("document", result["page"]["slug"])

    def test_extracts_entities_from_file(self):
        result = self.compiler.compile_ingest_job(
            vault_id=1, input_json={"file_id": 1}
        )
        entity_names = {e["name"] for e in result["entities"]}
        self.assertIn("AFOMIS", entity_names)

    def test_creates_claims_with_document_provenance(self):
        result = self.compiler.compile_ingest_job(
            vault_id=1, input_json={"file_id": 1}
        )
        self.assertGreater(len(result["claims"]), 0)
        claim_ids = [c["id"] for c in result["claims"]]
        for cid in claim_ids:
            sources = self.conn.execute(
                "SELECT source_kind FROM wiki_claim_sources WHERE claim_id = ?", (cid,)
            ).fetchall()
            source_kinds = {dict(s)["source_kind"] for s in sources}
            self.assertIn("document", source_kinds)
            claim_row = self.conn.execute(
                "SELECT status FROM wiki_claims WHERE id = ?", (cid,)
            ).fetchone()
            self.assertEqual(dict(claim_row)["status"], "unverified")

    def test_uses_provided_text_over_file_read(self):
        result = self.compiler.compile_ingest_job(
            vault_id=1,
            input_json={
                "file_id": 1,
                "text": AFOMIS_ANSWER,
            },
        )
        self.assertFalse(result.get("skipped"))

    def test_returns_skipped_when_text_empty_and_file_missing(self):
        self.conn.execute("UPDATE files SET file_path = '/nonexistent/path.txt' WHERE id = 1")
        self.conn.commit()
        result = self.compiler.compile_ingest_job(
            vault_id=1, input_json={"file_id": 1}
        )
        self.assertTrue(result.get("skipped"))


# ---------------------------------------------------------------------------
# WikiStore concurrent claim safety
# ---------------------------------------------------------------------------

class TestClaimNextPendingJobAtomicity(unittest.TestCase):

    def _make_store_with_conn(self):
        from app.models.database import run_migrations
        from app.services.wiki_store import WikiStore

        td = tempfile.mkdtemp()
        db_path = str(Path(td) / "test.db")
        run_migrations(db_path)
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("INSERT OR IGNORE INTO vaults (id, name) VALUES (1, 'T')")
        conn.commit()
        return WikiStore(conn), conn, db_path

    def test_claim_returns_none_when_queue_empty(self):
        store, conn, _ = self._make_store_with_conn()
        job = store.claim_next_pending_job()
        self.assertIsNone(job)
        conn.close()

    def test_claim_marks_job_running(self):
        store, conn, _ = self._make_store_with_conn()
        store.create_job(vault_id=1, trigger_type="manual")
        job = store.claim_next_pending_job()
        self.assertIsNotNone(job)
        self.assertEqual(job.status, "running")
        conn.close()

    def test_second_claim_returns_none_when_only_one_job(self):
        store, conn, _ = self._make_store_with_conn()
        store.create_job(vault_id=1, trigger_type="manual")
        job1 = store.claim_next_pending_job()
        job2 = store.claim_next_pending_job()
        self.assertIsNotNone(job1)
        self.assertIsNone(job2)
        conn.close()

    def test_reset_running_jobs_reclaims_orphans(self):
        store, conn, _ = self._make_store_with_conn()
        store.create_job(vault_id=1, trigger_type="manual")
        # Simulate orphan: mark as running without going through processor
        conn.execute(
            "UPDATE wiki_compile_jobs SET status = 'running'"
        )
        conn.commit()
        n = store.reset_running_jobs()
        self.assertEqual(n, 1)
        row = conn.execute("SELECT status FROM wiki_compile_jobs").fetchone()
        self.assertEqual(dict(row)["status"], "pending")
        conn.close()


# ---------------------------------------------------------------------------
# WikiStore stale marking
# ---------------------------------------------------------------------------

class TestMarkClaimsStale(unittest.TestCase):

    def setUp(self):
        self.conn, self.store, self.compiler = _make_env()

    def tearDown(self):
        self.conn.close()

    def _make_claim_with_file_source(self, claim_id_label="test"):
        claim = self.store.create_claim(
            vault_id=1,
            claim_text=f"Test claim {claim_id_label}",
            source_type="document",
        )
        self.store.attach_source(
            claim_id=claim.id,
            source_kind="document",
            file_id=1,
            source_label="file:1",
            confidence=0.9,
        )
        self.conn.commit()
        return claim

    def test_sole_source_claim_becomes_stale(self):
        claim = self._make_claim_with_file_source()
        result = self.store.mark_claims_stale_by_file(file_id=1, vault_id=1)
        self.assertGreaterEqual(result["stale"], 1)
        row = self.conn.execute(
            "SELECT status FROM wiki_claims WHERE id = ?", (claim.id,)
        ).fetchone()
        self.assertEqual(dict(row)["status"], "superseded")

    def test_multi_source_claim_not_stale(self):
        claim = self._make_claim_with_file_source()
        # Add a second source (memory)
        self.store.attach_source(
            claim_id=claim.id,
            source_kind="memory",
            memory_id=999,
            source_label="memory:999",
            confidence=0.5,
        )
        self.conn.commit()
        result = self.store.mark_claims_stale_by_file(file_id=1, vault_id=1)
        self.assertGreaterEqual(result["weak_provenance"], 1)
        row = self.conn.execute(
            "SELECT status FROM wiki_claims WHERE id = ?", (claim.id,)
        ).fetchone()
        self.assertNotEqual(dict(row)["status"], "superseded")

    def test_vault_scope_respected(self):
        claim = self._make_claim_with_file_source()
        result = self.store.mark_claims_stale_by_file(file_id=1, vault_id=999)
        # Wrong vault — no claims should be stale
        self.assertEqual(result["stale"], 0)
        row = self.conn.execute(
            "SELECT status FROM wiki_claims WHERE id = ?", (claim.id,)
        ).fetchone()
        self.assertNotEqual(dict(row)["status"], "superseded")


# ---------------------------------------------------------------------------
# WikiCompileProcessor lifecycle
# ---------------------------------------------------------------------------

class TestWikiCompileProcessorLifecycle(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        from app.models.database import SQLiteConnectionPool, run_migrations

        td = tempfile.mkdtemp()
        db_path = str(Path(td) / "test.db")
        run_migrations(db_path)
        self.pool = SQLiteConnectionPool(db_path, max_size=3)
        with self.pool.connection() as conn:
            conn.row_factory = None
            conn.execute("INSERT OR IGNORE INTO vaults (id, name) VALUES (1, 'T')")
            conn.commit()

    async def asyncTearDown(self):
        self.pool.close_all()

    async def test_start_and_stop(self):
        from app.services.wiki_compile_processor import WikiCompileProcessor

        proc = WikiCompileProcessor(self.pool)
        await proc.start()
        self.assertTrue(proc._running)
        await proc.stop()
        self.assertFalse(proc._running)

    async def test_second_start_is_noop(self):
        from app.services.wiki_compile_processor import WikiCompileProcessor

        proc = WikiCompileProcessor(self.pool)
        await proc.start()
        task_before = proc._task
        await proc.start()  # must not create a second task
        self.assertIs(proc._task, task_before)
        await proc.stop()

    async def test_processes_manual_job(self):
        from app.services.wiki_compile_processor import WikiCompileProcessor
        from app.services.wiki_store import WikiStore

        with self.pool.connection() as conn:
            WikiStore(conn).create_job(vault_id=1, trigger_type="manual")

        proc = WikiCompileProcessor(self.pool)
        await proc.start()
        # Give the processor a moment to claim and process the job
        await asyncio.sleep(0.5)
        await proc.stop()

        with self.pool.connection() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT status FROM wiki_compile_jobs").fetchone()
        self.assertIn(dict(row)["status"], ("completed", "failed"))

    async def test_orphan_recovery_on_start(self):
        from app.services.wiki_compile_processor import WikiCompileProcessor
        from app.services.wiki_store import WikiStore

        # Plant an orphaned running job
        with self.pool.connection() as conn:
            conn.execute(
                "INSERT INTO wiki_compile_jobs (vault_id, trigger_type, status, created_at) "
                "VALUES (1, 'manual', 'running', datetime('now'))"
            )
            conn.commit()

        proc = WikiCompileProcessor(self.pool)
        await proc.start()
        await proc.stop()

        with self.pool.connection() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT status FROM wiki_compile_jobs").fetchone()
        # After start+stop, the orphan should have been reset to pending (then possibly processed)
        self.assertNotEqual(dict(row)["status"], "running")
