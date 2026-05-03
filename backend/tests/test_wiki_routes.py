"""Tests for Wiki API routes — DTO shapes and end-to-end wiring."""

import os
import sqlite3
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from queue import Empty, Queue

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Stub optional heavy dependencies
try:
    import lancedb
except ImportError:
    import types
    sys.modules["lancedb"] = types.ModuleType("lancedb")

try:
    import pyarrow
except ImportError:
    import types
    sys.modules["pyarrow"] = types.ModuleType("pyarrow")

try:
    from unstructured.partition.auto import partition  # noqa: F401
except ImportError:
    import types
    _u = types.ModuleType("unstructured")
    _u.__path__ = []
    _u.partition = types.ModuleType("unstructured.partition")
    _u.partition.__path__ = []
    _u.partition.auto = types.ModuleType("unstructured.partition.auto")
    _u.partition.auto.partition = lambda *a, **k: []
    _u.chunking = types.ModuleType("unstructured.chunking")
    _u.chunking.__path__ = []
    _u.chunking.title = types.ModuleType("unstructured.chunking.title")
    _u.chunking.title.chunk_by_title = lambda *a, **k: []
    _u.documents = types.ModuleType("unstructured.documents")
    _u.documents.__path__ = []
    _u.documents.elements = types.ModuleType("unstructured.documents.elements")
    _u.documents.elements.Element = type("Element", (), {})
    sys.modules["unstructured"] = _u
    sys.modules["unstructured.partition"] = _u.partition
    sys.modules["unstructured.partition.auto"] = _u.partition.auto
    sys.modules["unstructured.chunking"] = _u.chunking
    sys.modules["unstructured.chunking.title"] = _u.chunking.title
    sys.modules["unstructured.documents"] = _u.documents
    sys.modules["unstructured.documents.elements"] = _u.documents.elements

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.api.deps import get_current_active_user, get_db, get_vector_store
from app.config import settings
from app.main import app

_MOCK_SUPERADMIN = {
    "id": 0,
    "username": "admin",
    "full_name": "Admin",
    "role": "superadmin",
    "is_active": True,
    "must_change_password": False,
}


class _SimplePool:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._pool: Queue = Queue(maxsize=5)
        self._closed = False

    def get(self) -> sqlite3.Connection:
        if self._closed:
            raise RuntimeError("Pool closed")
        try:
            return self._pool.get_nowait()
        except Empty:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON;")
            return conn

    def release(self, conn: sqlite3.Connection) -> None:
        if not self._closed:
            try:
                self._pool.put_nowait(conn)
            except Exception:
                conn.close()

    def close_all(self) -> None:
        self._closed = True
        while True:
            try:
                self._pool.get_nowait().close()
            except Empty:
                break


class WikiRouteTestBase(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self._temp_dir = tempfile.mkdtemp()

        # Store original settings
        self._original_data_dir = settings.data_dir

        # Point settings at our temp dir so evaluate_policy pool uses the right db
        settings.data_dir = Path(self._temp_dir)

        # DB path = settings.sqlite_path = temp_dir/app.db
        db_path = str(Path(self._temp_dir) / "app.db")

        # Clear the pool cache so a fresh pool is created for this test's db
        from app.models.database import _pool_cache, _pool_cache_lock
        with _pool_cache_lock:
            for _p in list(_pool_cache.values()):
                _p.close_all()
            _pool_cache.clear()

        from app.models.database import init_db
        init_db(db_path)

        self._pool = _SimplePool(db_path)
        self._db_path = db_path

        # Seed default vault
        conn = self._pool.get()
        conn.execute("INSERT OR IGNORE INTO vaults (id, name) VALUES (1, 'Default')")
        conn.commit()
        self._pool.release(conn)

        def _get_db_override():
            conn = self._pool.get()
            try:
                yield conn
            finally:
                self._pool.release(conn)

        mock_vs = MagicMock()
        mock_vs.delete_by_vault = MagicMock(return_value=0)

        # Override auth dependency to skip real authentication
        app.dependency_overrides[get_current_active_user] = lambda: _MOCK_SUPERADMIN
        app.dependency_overrides[get_db] = _get_db_override
        app.dependency_overrides[get_vector_store] = lambda: mock_vs

    def tearDown(self):
        app.dependency_overrides.pop(get_current_active_user, None)
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_vector_store, None)
        self._pool.close_all()

        # Restore settings and clear pool cache
        settings.data_dir = self._original_data_dir
        from app.models.database import _pool_cache, _pool_cache_lock
        with _pool_cache_lock:
            for _p in list(_pool_cache.values()):
                _p.close_all()
            _pool_cache.clear()

        import shutil
        shutil.rmtree(self._temp_dir, ignore_errors=True)

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------
    def _raw(self) -> sqlite3.Connection:
        return self._pool.get()

    def _insert_memory(self, content: str, vault_id: int = 1) -> int:
        conn = self._raw()
        cur = conn.execute(
            "INSERT INTO memories (content, vault_id) VALUES (?, ?)",
            (content, vault_id),
        )
        conn.commit()
        mem_id = cur.lastrowid
        self._pool.release(conn)
        return mem_id


class TestWikiPageRoutes(WikiRouteTestBase):

    def test_list_pages_empty(self):
        resp = self.client.get("/api/wiki/pages", params={"vault_id": 1})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("pages", data)
        self.assertEqual(data["pages"], [])

    def test_create_page_returns_201_with_dto_shape(self):
        resp = self.client.post(
            "/api/wiki/pages",
            json={
                "vault_id": 1,
                "title": "AFOMIS Overview",
                "page_type": "overview",
                "markdown": "# AFOMIS\nTest content.",
            },
        )
        self.assertEqual(resp.status_code, 201, resp.text)
        data = resp.json()
        self.assertEqual(data["title"], "AFOMIS Overview")
        self.assertEqual(data["page_type"], "overview")
        self.assertIn("slug", data)
        self.assertIn("afomis", data["slug"])
        self.assertIn("status", data)
        self.assertIn("id", data)
        self.assertEqual(data["vault_id"], 1)

    def test_get_page_returns_correct_fields(self):
        create_resp = self.client.post(
            "/api/wiki/pages",
            json={"vault_id": 1, "title": "Test Page", "page_type": "entity"},
        )
        page_id = create_resp.json()["id"]

        resp = self.client.get(f"/api/wiki/pages/{page_id}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["id"], page_id)
        self.assertEqual(data["title"], "Test Page")
        self.assertIn("claims", data)
        self.assertIn("entities", data)

    def test_get_nonexistent_page_returns_404(self):
        resp = self.client.get("/api/wiki/pages/99999")
        self.assertEqual(resp.status_code, 404)

    def test_update_page(self):
        create_resp = self.client.post(
            "/api/wiki/pages",
            json={"vault_id": 1, "title": "Old Title", "page_type": "entity"},
        )
        page_id = create_resp.json()["id"]

        resp = self.client.put(
            f"/api/wiki/pages/{page_id}",
            json={"title": "New Title", "status": "verified"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["title"], "New Title")
        self.assertEqual(data["status"], "verified")

    def test_delete_page_returns_204(self):
        create_resp = self.client.post(
            "/api/wiki/pages",
            json={"vault_id": 1, "title": "To Delete", "page_type": "entity"},
        )
        page_id = create_resp.json()["id"]

        resp = self.client.delete(f"/api/wiki/pages/{page_id}")
        self.assertEqual(resp.status_code, 204)

        # Subsequent GET must 404
        resp2 = self.client.get(f"/api/wiki/pages/{page_id}")
        self.assertEqual(resp2.status_code, 404)

    def test_list_pages_filter_by_type(self):
        self.client.post(
            "/api/wiki/pages",
            json={"vault_id": 1, "title": "Entity Page", "page_type": "entity"},
        )
        self.client.post(
            "/api/wiki/pages",
            json={"vault_id": 1, "title": "Acronym Page", "page_type": "acronym"},
        )

        resp = self.client.get("/api/wiki/pages", params={"vault_id": 1, "page_type": "entity"})
        data = resp.json()
        self.assertEqual(len(data["pages"]), 1)
        self.assertEqual(data["pages"][0]["page_type"], "entity")


class TestWikiClaimRoutes(WikiRouteTestBase):

    def test_list_claims_empty(self):
        resp = self.client.get("/api/wiki/claims", params={"vault_id": 1})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("claims", resp.json())

    def test_create_claim_returns_201(self):
        resp = self.client.post(
            "/api/wiki/claims",
            json={
                "vault_id": 1,
                "claim_text": "Justice Sakyi is the AFOMIS Chief",
                "source_type": "manual",
                "subject": "Justice Sakyi",
                "predicate": "chief",
                "object": "AFOMIS",
            },
        )
        self.assertEqual(resp.status_code, 201, resp.text)
        data = resp.json()
        self.assertEqual(data["claim_text"], "Justice Sakyi is the AFOMIS Chief")
        self.assertIn("id", data)
        self.assertIn("sources", data)

    def test_update_claim(self):
        create_resp = self.client.post(
            "/api/wiki/claims",
            json={"vault_id": 1, "claim_text": "Original", "source_type": "manual"},
        )
        claim_id = create_resp.json()["id"]

        resp = self.client.put(
            f"/api/wiki/claims/{claim_id}",
            json={"claim_text": "Updated", "status": "superseded"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["claim_text"], "Updated")
        self.assertEqual(data["status"], "superseded")

    def test_delete_claim_returns_204(self):
        create_resp = self.client.post(
            "/api/wiki/claims",
            json={"vault_id": 1, "claim_text": "Temp", "source_type": "manual"},
        )
        claim_id = create_resp.json()["id"]

        resp = self.client.delete(f"/api/wiki/claims/{claim_id}")
        self.assertEqual(resp.status_code, 204)


class TestWikiEntityRoutes(WikiRouteTestBase):

    def test_list_entities_empty(self):
        resp = self.client.get("/api/wiki/entities", params={"vault_id": 1})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("entities", resp.json())


class TestWikiLintRoutes(WikiRouteTestBase):

    def test_get_lint_findings_empty(self):
        resp = self.client.get("/api/wiki/lint", params={"vault_id": 1})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("findings", resp.json())

    def test_run_lint_returns_findings_list(self):
        resp = self.client.post("/api/wiki/lint/run", json={"vault_id": 1})
        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()
        self.assertIn("findings", data)
        self.assertIn("count", data)
        self.assertIsInstance(data["count"], int)

    def test_run_lint_detects_unsupported_claim(self):
        self.client.post(
            "/api/wiki/claims",
            json={"vault_id": 1, "claim_text": "Claim with no sources", "source_type": "manual"},
        )
        resp = self.client.post("/api/wiki/lint/run", json={"vault_id": 1})
        data = resp.json()
        types_found = {f["finding_type"] for f in data["findings"]}
        self.assertIn("unsupported_claim", types_found)


class TestWikiSearchRoute(WikiRouteTestBase):

    def test_search_returns_structure(self):
        self.client.post(
            "/api/wiki/pages",
            json={"vault_id": 1, "title": "AFOMIS Entity", "page_type": "entity"},
        )
        resp = self.client.get("/api/wiki/search", params={"vault_id": 1, "q": "AFOMIS"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("pages", data)
        self.assertIn("claims", data)
        self.assertIn("entities", data)
        self.assertIn("query", data)

    def test_search_no_results(self):
        resp = self.client.get("/api/wiki/search", params={"vault_id": 1, "q": "xyznonexistent"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["pages"], [])
        self.assertEqual(data["claims"], [])
        self.assertEqual(data["entities"], [])


class TestWikiJobsRoute(WikiRouteTestBase):

    def test_list_jobs_empty(self):
        resp = self.client.get("/api/wiki/jobs", params={"vault_id": 1})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("jobs", resp.json())


class TestWikiPromoteMemoryRoute(WikiRouteTestBase):

    AFOMIS_TEXT = (
        "AFOMIS stands for Air Force Operational Medicine Information Systems. "
        "Justice Sakyi is the AFOMIS Chief and Major Justin Woods is his deputy."
    )

    def test_promote_memory_returns_page_claims_entities_relations(self):
        mem_id = self._insert_memory(self.AFOMIS_TEXT)
        resp = self.client.post(
            "/api/wiki/promote-memory",
            json={"memory_id": mem_id, "vault_id": 1},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()
        self.assertIn("page", data)
        self.assertIn("claims", data)
        self.assertIn("entities", data)
        self.assertIn("relations", data)

    def test_promote_memory_page_has_required_fields(self):
        mem_id = self._insert_memory(self.AFOMIS_TEXT)
        resp = self.client.post(
            "/api/wiki/promote-memory",
            json={"memory_id": mem_id, "vault_id": 1},
        )
        page = resp.json()["page"]
        self.assertIn("id", page)
        self.assertIn("title", page)
        self.assertIn("slug", page)
        self.assertIn("vault_id", page)

    def test_promote_memory_creates_afomis_entity(self):
        mem_id = self._insert_memory(self.AFOMIS_TEXT)
        resp = self.client.post(
            "/api/wiki/promote-memory",
            json={"memory_id": mem_id, "vault_id": 1},
        )
        entity_names = {e["canonical_name"] for e in resp.json()["entities"]}
        self.assertIn("AFOMIS", entity_names)

    def test_promote_memory_claims_have_sources(self):
        mem_id = self._insert_memory(self.AFOMIS_TEXT)
        resp = self.client.post(
            "/api/wiki/promote-memory",
            json={"memory_id": mem_id, "vault_id": 1},
        )
        for claim in resp.json()["claims"]:
            self.assertGreater(len(claim["sources"]), 0, f"Claim has no sources: {claim}")
            self.assertEqual(claim["sources"][0]["source_kind"], "memory")
            self.assertEqual(claim["sources"][0]["memory_id"], mem_id)

    def test_promote_nonexistent_memory_returns_404(self):
        resp = self.client.post(
            "/api/wiki/promote-memory",
            json={"memory_id": 99999, "vault_id": 1},
        )
        self.assertEqual(resp.status_code, 404)

    def test_promote_wrong_vault_returns_403(self):
        conn = self._raw()
        conn.execute("INSERT OR IGNORE INTO vaults (id, name) VALUES (2, 'Other')")
        conn.commit()
        self._pool.release(conn)

        mem_id = self._insert_memory(self.AFOMIS_TEXT, vault_id=2)
        resp = self.client.post(
            "/api/wiki/promote-memory",
            json={"memory_id": mem_id, "vault_id": 1},
        )
        self.assertEqual(resp.status_code, 403)
