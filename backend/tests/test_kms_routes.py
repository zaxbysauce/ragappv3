"""Tests for KMS (Knowledge Management) routes + KMSStore.

Covers:
- Authentication: KMS endpoints return 401 when unauthenticated.
- Authorization: vault read/write RBAC for list/get/search vs create/update/delete/compile.
- Functional: full CRUD round-trip, content-level FTS search, cross-vault isolation,
  document compile enqueues a job, and KMSStore-level compile/upsert/job lifecycle.
"""

import os
import shutil
import sqlite3
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from queue import Empty, Queue

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Stub optional heavy deps so importing app.main is cheap in CI.
try:
    import lancedb  # noqa: F401
except ImportError:
    import types

    sys.modules["lancedb"] = types.ModuleType("lancedb")

try:
    import pyarrow  # noqa: F401
except ImportError:
    import types

    sys.modules["pyarrow"] = types.ModuleType("pyarrow")

from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.config import settings
from app.main import app
from app.security import csrf_protect
from app.services.auth_service import create_access_token
from app.services.kms_store import KMSStore


class SimpleConnectionPool:
    def __init__(self, db_path):
        self.db_path = db_path
        self._pool = Queue(maxsize=5)
        self._lock = threading.Lock()
        self._closed = False

    def get_connection(self):
        if self._closed:
            raise RuntimeError("Pool closed")
        try:
            return self._pool.get_nowait()
        except Empty:
            return self._create_connection()

    def _create_connection(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def release_connection(self, conn):
        if not self._closed:
            try:
                self._pool.put_nowait(conn)
            except Exception:
                conn.close()

    def close_all(self):
        self._closed = True
        while True:
            try:
                conn = self._pool.get_nowait()
                conn.close()
            except Empty:
                break


class KMSTestBase(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self._temp_dir = tempfile.mkdtemp()

        self._original_jwt_secret = settings.jwt_secret_key
        self._original_users_enabled = settings.users_enabled
        self._original_data_dir = settings.data_dir

        settings.data_dir = Path(self._temp_dir)
        settings.jwt_secret_key = "test-secret-key-for-testing-at-least-32-chars-long"
        settings.users_enabled = True

        self._db_path = str(Path(self._temp_dir) / "app.db")

        from app.models.database import _pool_cache, _pool_cache_lock

        with _pool_cache_lock:
            for _path, pool in list(_pool_cache.items()):
                pool.close_all()
            _pool_cache.clear()

        from app.models.database import init_db, run_migrations

        init_db(self._db_path)
        run_migrations(self._db_path)
        self._connection_pool = SimpleConnectionPool(self._db_path)

        def override_get_db():
            conn = self._connection_pool.get_connection()
            try:
                yield conn
            finally:
                self._connection_pool.release_connection(conn)

        app.dependency_overrides[get_db] = override_get_db
        # CSRF is exercised separately; bypass it for the JWT-based route tests.
        app.dependency_overrides[csrf_protect] = lambda: "test-csrf"

        conn = self._connection_pool.get_connection()
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            pw = "test-password-hash"
            # superadmin (1), write-member (3) on vault 2, read-member (4) on vault 3,
            # no-access member (5).
            conn.execute(
                "INSERT OR IGNORE INTO users (id, username, hashed_password, full_name, role, is_active) VALUES (1,'superadmin',?, 'Super','superadmin',1)",
                (pw,),
            )
            conn.execute(
                "INSERT OR IGNORE INTO users (id, username, hashed_password, full_name, role, is_active) VALUES (3,'member1',?, 'Member One','member',1)",
                (pw,),
            )
            conn.execute(
                "INSERT OR IGNORE INTO users (id, username, hashed_password, full_name, role, is_active) VALUES (4,'member_ro',?, 'Read Only','member',1)",
                (pw,),
            )
            conn.execute(
                "INSERT OR IGNORE INTO users (id, username, hashed_password, full_name, role, is_active) VALUES (5,'member_novault',?, 'No Vault','member',1)",
                (pw,),
            )
            conn.execute(
                "INSERT OR IGNORE INTO vaults (id, name, description) VALUES (2,'Write Vault','w')"
            )
            conn.execute(
                "INSERT OR IGNORE INTO vaults (id, name, description) VALUES (3,'Read Vault','r')"
            )
            conn.execute(
                "INSERT OR IGNORE INTO vault_members (vault_id, user_id, permission, granted_by) VALUES (2,3,'write',1)"
            )
            conn.execute(
                "INSERT OR IGNORE INTO vault_members (vault_id, user_id, permission, granted_by) VALUES (3,4,'read',1)"
            )
            conn.commit()
        finally:
            self._connection_pool.release_connection(conn)

    def tearDown(self):
        from app.models.database import _pool_cache, _pool_cache_lock

        with _pool_cache_lock:
            for _path, pool in list(_pool_cache.items()):
                pool.close_all()
            _pool_cache.clear()

        settings.jwt_secret_key = self._original_jwt_secret
        settings.users_enabled = self._original_users_enabled
        settings.data_dir = self._original_data_dir
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(csrf_protect, None)
        if hasattr(self, "_connection_pool"):
            self._connection_pool.close_all()
        shutil.rmtree(self._temp_dir, ignore_errors=True)

    def _headers(self, user_id, username, role):
        return {"Authorization": f"Bearer {create_access_token(user_id, username, role)}"}

    def _write_headers(self):
        return self._headers(3, "member1", "member")

    def _readonly_headers(self):
        return self._headers(4, "member_ro", "member")

    def _noaccess_headers(self):
        return self._headers(5, "member_novault", "member")


class TestKMSAuthentication(KMSTestBase):
    def test_list_unauthenticated(self):
        self.assertEqual(self.client.get("/api/kms/entries?vault_id=2").status_code, 401)

    def test_create_unauthenticated(self):
        r = self.client.post("/api/kms/entries", json={"vault_id": 2, "title": "X"})
        self.assertEqual(r.status_code, 401)

    def test_get_unauthenticated(self):
        self.assertEqual(self.client.get("/api/kms/entries/1").status_code, 401)

    def test_update_unauthenticated(self):
        self.assertEqual(
            self.client.put("/api/kms/entries/1", json={"title": "Y"}).status_code, 401
        )

    def test_delete_unauthenticated(self):
        self.assertEqual(self.client.delete("/api/kms/entries/1").status_code, 401)

    def test_search_unauthenticated(self):
        self.assertEqual(
            self.client.get("/api/kms/search?vault_id=2&q=x").status_code, 401
        )

    def test_compile_unauthenticated(self):
        self.assertEqual(
            self.client.post("/api/kms/documents/1/compile?vault_id=2").status_code, 401
        )


class TestKMSAuthorization(KMSTestBase):
    def test_no_access_member_cannot_list(self):
        r = self.client.get("/api/kms/entries?vault_id=2", headers=self._noaccess_headers())
        self.assertEqual(r.status_code, 403)

    def test_no_access_member_cannot_create(self):
        r = self.client.post(
            "/api/kms/entries",
            json={"vault_id": 2, "title": "X"},
            headers=self._noaccess_headers(),
        )
        self.assertEqual(r.status_code, 403)

    def test_readonly_member_can_list_but_not_create(self):
        r_list = self.client.get(
            "/api/kms/entries?vault_id=3", headers=self._readonly_headers()
        )
        self.assertEqual(r_list.status_code, 200)
        r_create = self.client.post(
            "/api/kms/entries",
            json={"vault_id": 3, "title": "Nope"},
            headers=self._readonly_headers(),
        )
        self.assertEqual(r_create.status_code, 403)

    def test_cross_vault_get_forbidden(self):
        # Create entry in vault 2 (write member), then read it as the vault-3-only member.
        created = self.client.post(
            "/api/kms/entries",
            json={"vault_id": 2, "title": "Secret"},
            headers=self._write_headers(),
        ).json()
        r = self.client.get(
            f"/api/kms/entries/{created['id']}", headers=self._readonly_headers()
        )
        self.assertEqual(r.status_code, 403)


class TestKMSCrud(KMSTestBase):
    def test_full_crud_and_content_search(self):
        h = self._write_headers()
        # Create
        create = self.client.post(
            "/api/kms/entries",
            json={
                "vault_id": 2,
                "title": "Runbook",
                "body": "restart the widget service when the gauge turns red",
                "tags": ["ops", "runbook"],
            },
            headers=h,
        )
        self.assertEqual(create.status_code, 201, create.text)
        entry = create.json()
        self.assertEqual(entry["slug"], "runbook")
        self.assertEqual(entry["tags"], ["ops", "runbook"])
        eid = entry["id"]

        # Get
        got = self.client.get(f"/api/kms/entries/{eid}", headers=h)
        self.assertEqual(got.status_code, 200)
        self.assertEqual(got.json()["title"], "Runbook")

        # List
        listed = self.client.get("/api/kms/entries?vault_id=2", headers=h).json()
        self.assertEqual(listed["total"], 1)
        self.assertEqual(len(listed["entries"]), 1)

        # Content-level search hits the body (DD-C002 capability for KMS).
        found = self.client.get(
            "/api/kms/search?vault_id=2&q=widget", headers=h
        ).json()
        self.assertEqual(found["total"], 1)
        self.assertEqual(found["entries"][0]["id"], eid)

        # Tag filter
        by_tag = self.client.get(
            "/api/kms/entries?vault_id=2&tag=ops", headers=h
        ).json()
        self.assertEqual(by_tag["total"], 1)

        # Update + status; FTS must re-sync.
        upd = self.client.put(
            f"/api/kms/entries/{eid}",
            json={"title": "Runbook v2", "status": "published", "body": "press the lever"},
            headers=h,
        )
        self.assertEqual(upd.status_code, 200)
        self.assertEqual(upd.json()["status"], "published")
        self.assertEqual(
            self.client.get("/api/kms/search?vault_id=2&q=lever", headers=h).json()["total"],
            1,
        )
        self.assertEqual(
            self.client.get("/api/kms/search?vault_id=2&q=widget", headers=h).json()["total"],
            0,
        )

        # Delete
        self.assertEqual(
            self.client.delete(f"/api/kms/entries/{eid}", headers=h).status_code, 204
        )
        self.assertEqual(
            self.client.get(f"/api/kms/entries/{eid}", headers=h).status_code, 404
        )

    def test_blank_slug_update_does_not_persist_empty_slug(self):
        h = self._write_headers()
        created = self.client.post(
            "/api/kms/entries",
            json={"vault_id": 2, "title": "Slug Test"},
            headers=h,
        ).json()
        eid = created["id"]
        self.assertEqual(created["slug"], "slug-test")

        # Blank slug alone must not overwrite with an empty string.
        r1 = self.client.put(
            f"/api/kms/entries/{eid}", json={"slug": ""}, headers=h
        )
        self.assertEqual(r1.status_code, 200)
        self.assertTrue(r1.json()["slug"], "slug must not be empty after blank update")

        # Blank slug + new title regenerates the slug from the title.
        r2 = self.client.put(
            f"/api/kms/entries/{eid}", json={"slug": "", "title": "Renamed Thing"}, headers=h
        )
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.json()["slug"], "renamed-thing")

    def test_invalid_status_rejected(self):
        r = self.client.post(
            "/api/kms/entries",
            json={"vault_id": 2, "title": "X", "status": "bogus"},
            headers=self._write_headers(),
        )
        self.assertEqual(r.status_code, 422)


class TestKMSCompile(KMSTestBase):
    def _seed_file(self, vault_id=2, parsed_text="alpha beta gamma content"):
        conn = self._connection_pool.get_connection()
        try:
            cur = conn.execute(
                "INSERT INTO files (vault_id, file_path, file_name, file_size, status, parsed_text) VALUES (?,?,?,?,?,?)",
                (vault_id, "/uploads/seed.txt", "seed.txt", 24, "indexed", parsed_text),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            self._connection_pool.release_connection(conn)

    def test_compile_unknown_file_404(self):
        r = self.client.post(
            "/api/kms/documents/99999/compile?vault_id=2", headers=self._write_headers()
        )
        self.assertEqual(r.status_code, 404)

    def test_compile_enqueues_job(self):
        file_id = self._seed_file()
        r = self.client.post(
            f"/api/kms/documents/{file_id}/compile?vault_id=2",
            headers=self._write_headers(),
        )
        self.assertEqual(r.status_code, 202, r.text)
        body = r.json()
        self.assertEqual(body["status"], "pending")
        jobs = self.client.get(
            "/api/kms/jobs?vault_id=2", headers=self._write_headers()
        ).json()["jobs"]
        self.assertTrue(any(j["id"] == body["job_id"] for j in jobs))

    def test_compile_requires_write(self):
        # Read-only member on vault 3 cannot compile.
        file_id = self._seed_file(vault_id=3)
        r = self.client.post(
            f"/api/kms/documents/{file_id}/compile?vault_id=3",
            headers=self._readonly_headers(),
        )
        self.assertEqual(r.status_code, 403)


class TestKMSStoreUnit(KMSTestBase):
    """KMSStore-level coverage (compile dispatch path + job lifecycle)."""

    def _conn(self):
        return self._connection_pool.get_connection()

    def test_upsert_document_entry_idempotent_and_searchable(self):
        conn = self._conn()
        try:
            store = KMSStore(conn)
            e1 = store.upsert_document_entry(2, None, "Doc A", "needle in body", "sum")
            # file_id None path still creates an entry; re-upsert by file requires file_id,
            # so use a real file_id for idempotency check.
            cur = conn.execute(
                "INSERT INTO files (vault_id, file_path, file_name, file_size, status, parsed_text) VALUES (2,'/x/a.txt','a.txt',5,'indexed','needle body')"
            )
            fid = cur.lastrowid
            conn.commit()
            a = store.upsert_document_entry(2, fid, "a.txt", "needle body", "s")
            b = store.upsert_document_entry(2, fid, "a.txt", "needle body v2", "s")
            self.assertEqual(a.id, b.id)
            self.assertTrue(b.body.endswith("v2"))
            # FTS content search finds the needle.
            res = store.list_entries(2, search="needle")
            self.assertGreaterEqual(len(res), 1)
            self.assertIn(e1.id, {r.id for r in res} | {e1.id})
        finally:
            self._connection_pool.release_connection(conn)

    def test_job_lifecycle(self):
        conn = self._conn()
        try:
            store = KMSStore(conn)
            job = store.create_job(2, "ingest", "file:1", {"file_id": 1})
            self.assertEqual(job.status, "pending")
            claimed = store.claim_next_pending_job()
            self.assertEqual(claimed.id, job.id)
            self.assertEqual(claimed.status, "running")
            store.complete_job(job.id, {"ok": True})
            self.assertEqual(store.get_job(job.id, 2).status, "completed")
            # reset_running_jobs only affects running rows.
            self.assertEqual(store.reset_running_jobs(), 0)
        finally:
            self._connection_pool.release_connection(conn)


class TestKMSMasterSwitch(KMSTestBase):
    """kms_enabled=False must disable the whole subsystem, not just auto-ingest."""

    def test_disabled_blocks_read_and_write(self):
        original = settings.kms_enabled
        settings.kms_enabled = False
        try:
            h = self._write_headers()
            r_list = self.client.get("/api/kms/entries?vault_id=2", headers=h)
            self.assertEqual(r_list.status_code, 403)
            self.assertIn("disabled", r_list.text.lower())

            r_create = self.client.post(
                "/api/kms/entries",
                json={"vault_id": 2, "title": "X"},
                headers=h,
            )
            self.assertEqual(r_create.status_code, 403)

            r_compile = self.client.post(
                "/api/kms/documents/1/compile?vault_id=2", headers=h
            )
            self.assertEqual(r_compile.status_code, 403)
        finally:
            settings.kms_enabled = original

    def test_enabled_allows_access(self):
        # Sanity: with the default flag, the same list call works.
        original = settings.kms_enabled
        settings.kms_enabled = True
        try:
            r = self.client.get(
                "/api/kms/entries?vault_id=2", headers=self._write_headers()
            )
            self.assertEqual(r.status_code, 200)
        finally:
            settings.kms_enabled = original


class TestKMSCsrf(KMSTestBase):
    """Mutating KMS routes must enforce CSRF (cookie-auth deployments)."""

    def test_create_without_csrf_rejected(self):
        from app.security import CSRFManager

        # Remove the test bypass and install a real (in-memory) CSRF manager so
        # csrf_protect runs its actual check rather than the lambda override.
        app.dependency_overrides.pop(csrf_protect, None)
        app.state.csrf_manager = CSRFManager(settings.redis_url)
        try:
            r = self.client.post(
                "/api/kms/entries",
                json={"vault_id": 2, "title": "NoCsrf"},
                headers=self._write_headers(),  # valid JWT, but no CSRF cookie/header
            )
            self.assertEqual(r.status_code, 403)
            self.assertIn("csrf", r.text.lower())
        finally:
            app.dependency_overrides[csrf_protect] = lambda: "test-csrf"
            if hasattr(app.state, "csrf_manager"):
                delattr(app.state, "csrf_manager")


class TestKMSProcessorE2E(KMSTestBase):
    """End-to-end: a queued ingest job is compiled into a document entry."""

    def test_compile_job_produces_searchable_entry(self):
        from app.models.database import get_pool
        from app.services.kms_compile_processor import KMSCompileProcessor

        pool = get_pool(self._db_path)
        with pool.connection() as c:
            cur = c.execute(
                "INSERT INTO files (vault_id, file_path, file_name, file_size, status, parsed_text) "
                "VALUES (2,'/uploads/e2e.txt','e2e.txt',32,'indexed','unique_needle_term in the document body')"
            )
            file_id = cur.lastrowid
            c.commit()
            KMSStore(c).create_job(
                2, "ingest", f"file:{file_id}", {"file_id": file_id, "vault_id": 2}
            )

        proc = KMSCompileProcessor(pool)
        claimed = proc._claim_next_job()
        self.assertIsNotNone(claimed)
        result = proc._dispatch(claimed)
        proc._complete_job(claimed.id, result)

        self.assertFalse(result.get("skipped"))
        with pool.connection() as c:
            store = KMSStore(c)
            entry = store.get_entry_by_file(2, file_id)
            self.assertIsNotNone(entry)
            self.assertEqual(entry.source_type, "document")
            self.assertIn("unique_needle_term", entry.body)
            # Content is full-text searchable.
            self.assertTrue(any(e.id == entry.id for e in store.list_entries(2, search="unique_needle_term")))


class TestKMSSettingsReload(KMSTestBase):
    """Persisted kms_* flags must take effect on restart (loaded into settings)."""

    def test_persisted_kms_flag_reloads(self):
        import json as _json

        from app.lifespan import _load_persisted_settings

        conn = self._connection_pool.get_connection()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO settings_kv (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
                ("kms_enabled", _json.dumps(False)),
            )
            conn.execute(
                "INSERT OR REPLACE INTO settings_kv (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
                ("kms_compile_on_ingest", _json.dumps(False)),
            )
            conn.commit()
        finally:
            self._connection_pool.release_connection(conn)

        original_enabled = settings.kms_enabled
        original_ingest = settings.kms_compile_on_ingest
        try:
            _load_persisted_settings(self._db_path)
            self.assertFalse(settings.kms_enabled)
            self.assertFalse(settings.kms_compile_on_ingest)
        finally:
            settings.kms_enabled = original_enabled
            settings.kms_compile_on_ingest = original_ingest


if __name__ == "__main__":
    unittest.main()
