"""PR B: tests for the expanded settings backend.

Covers:
  - GET /settings exposes the new wiki + curator fields and an
    ``effective_sources`` map keyed by ALLOWED_FIELDS.
  - PUT /settings persists the new fields and they survive reload.
  - PUT /settings rejects (422) when curator is enabled but URL or model
    is missing.
  - Pydantic validators enforce numeric/enum bounds on curator fields.
  - SSRF guard: curator URLs that resolve to RFC1918 / loopback / link-
    local are rejected unless ALLOW_LOCAL_CURATOR=1.
  - POST /settings/curator/test returns the contract shape
    {ok, model, latency_ms, error?} including the explicit local-model
    UX hint when SSRF blocks.
  - effective_sources reports kv > env > default.
"""

import os
import sqlite3
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from queue import Empty, Queue
from unittest.mock import MagicMock

# Ensure backend importable.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Shared optional-dep stubs (mirrors test_documents_auth.py).
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

from app.config import settings
from app.models.database import init_db, run_migrations
from app.services.curator_ssrf import CuratorURLBlocked, assert_curator_url_safe


class _SimplePool:
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

    from contextlib import contextmanager

    @contextmanager
    def connection(self):
        conn = self.get_connection()
        try:
            yield conn
        finally:
            self.release_connection(conn)

    def close_all(self):
        self._closed = True
        while True:
            try:
                conn = self._pool.get_nowait()
                conn.close()
            except Empty:
                break


# ---------------------------------------------------------------------------
# Pure-unit tests for SSRF guard. No HTTP.
# ---------------------------------------------------------------------------


class TestCuratorSSRFGuard(unittest.TestCase):
    def setUp(self):
        # Default-deny.
        os.environ.pop("ALLOW_LOCAL_CURATOR", None)

    def tearDown(self):
        os.environ.pop("ALLOW_LOCAL_CURATOR", None)

    def test_empty_url_rejected(self):
        with self.assertRaises(CuratorURLBlocked):
            assert_curator_url_safe("")
        with self.assertRaises(CuratorURLBlocked):
            assert_curator_url_safe("   ")

    def test_non_http_scheme_rejected(self):
        for u in (
            "file:///etc/passwd",
            "ftp://example.com/",
            "javascript:alert(1)",
            "gopher://localhost/",
        ):
            with self.assertRaises(CuratorURLBlocked, msg=u):
                assert_curator_url_safe(u)

    def test_credentials_in_url_rejected(self):
        with self.assertRaises(CuratorURLBlocked):
            assert_curator_url_safe("http://user:pw@public.example.com/")

    def test_loopback_blocked_by_default(self):
        for u in (
            "http://127.0.0.1:8080/",
            "http://localhost/",
            "http://[::1]/",
        ):
            with self.assertRaises(CuratorURLBlocked, msg=u) as ctx:
                assert_curator_url_safe(u)
            # Public-facing UX hint must mention the env var so operators
            # know how to opt in.
            self.assertIn("ALLOW_LOCAL_CURATOR=1", str(ctx.exception))

    def test_rfc1918_blocked_by_default(self):
        for ip in ("10.1.2.3", "192.168.1.1", "172.16.0.5"):
            with self.assertRaises(CuratorURLBlocked, msg=ip):
                assert_curator_url_safe(f"http://{ip}/")

    def test_loopback_allowed_with_opt_in(self):
        os.environ["ALLOW_LOCAL_CURATOR"] = "1"
        # Should not raise.
        assert_curator_url_safe("http://127.0.0.1:11434/v1/chat/completions")
        assert_curator_url_safe("http://localhost:8080/")
        assert_curator_url_safe("http://[::1]:80/")

    def test_public_ip_allowed(self):
        # 1.1.1.1 is public.
        assert_curator_url_safe("https://1.1.1.1/v1/chat/completions")


# ---------------------------------------------------------------------------
# HTTP-level tests for the new settings shape and curator-test endpoint.
# ---------------------------------------------------------------------------


class TestSettingsExpansion(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient

        from app.api.deps import get_db, get_db_pool
        from app.main import app
        from app.services.auth_service import create_access_token, hash_password

        self.app = app
        self.create_token = create_access_token
        self.hash_password = hash_password

        self.tmp = tempfile.mkdtemp()
        self._original_data_dir = settings.data_dir
        self._original_jwt = settings.jwt_secret_key
        self._original_users = settings.users_enabled
        settings.data_dir = Path(self.tmp)
        settings.users_enabled = True
        settings.jwt_secret_key = "test-secret-key-for-testing-at-least-32-chars-long"
        # Snapshot curator-related settings so each test is isolated.
        self._curator_snapshot = {
            f: getattr(settings, f)
            for f in (
                "wiki_llm_curator_enabled",
                "wiki_llm_curator_url",
                "wiki_llm_curator_model",
                "wiki_llm_curator_temperature",
                "wiki_llm_curator_max_input_chars",
                "wiki_llm_curator_max_output_tokens",
                "wiki_llm_curator_timeout_sec",
                "wiki_llm_curator_concurrency",
                "wiki_llm_curator_mode",
                "wiki_llm_curator_require_quote_match",
                "wiki_llm_curator_require_chunk_id",
                "wiki_llm_curator_run_on_ingest",
                "wiki_llm_curator_run_on_query",
                "wiki_llm_curator_run_on_manual",
                "wiki_enabled",
                "wiki_compile_on_ingest",
                "wiki_compile_on_query",
                "wiki_compile_after_indexing",
                "wiki_lint_enabled",
            )
        }
        os.environ.pop("ALLOW_LOCAL_CURATOR", None)

        self.db = str(Path(self.tmp) / "app.db")

        from app.models.database import _pool_cache, _pool_cache_lock

        with _pool_cache_lock:
            for _, p in list(_pool_cache.items()):
                p.close_all()
            _pool_cache.clear()

        run_migrations(self.db)
        self.pool = _SimplePool(self.db)

        def override_db():
            conn = self.pool.get_connection()
            try:
                yield conn
            finally:
                self.pool.release_connection(conn)

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_db_pool] = lambda: self.pool

        # Seed an admin user.
        conn = self.pool.get_connection()
        try:
            conn.execute("DELETE FROM users WHERE id != 0")
            pw = self.hash_password("pw")
            conn.execute(
                "INSERT INTO users (id, username, hashed_password, full_name, role, is_active) "
                "VALUES (1, 'admin1', ?, 'Admin', 'admin', 1)",
                (pw,),
            )
            conn.commit()
        finally:
            self.pool.release_connection(conn)

        self.client = TestClient(app)
        self.token = self.create_token(1, "admin1", "admin")

    def tearDown(self):
        from app.models.database import _pool_cache, _pool_cache_lock

        self.app.dependency_overrides.clear()
        with _pool_cache_lock:
            for _, p in list(_pool_cache.items()):
                p.close_all()
            _pool_cache.clear()
        self.pool.close_all()
        # Restore curator settings so tests don't bleed.
        for f, v in self._curator_snapshot.items():
            setattr(settings, f, v)
        settings.data_dir = self._original_data_dir
        settings.jwt_secret_key = self._original_jwt
        settings.users_enabled = self._original_users
        os.environ.pop("ALLOW_LOCAL_CURATOR", None)
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def _hdr(self):
        return {"Authorization": f"Bearer {self.token}"}

    def test_get_settings_includes_wiki_and_curator_fields_and_effective_sources(self):
        r = self.client.get("/api/settings", headers=self._hdr())
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        # Wiki fields
        for f in (
            "wiki_enabled",
            "wiki_compile_on_ingest",
            "wiki_compile_on_query",
            "wiki_compile_after_indexing",
            "wiki_lint_enabled",
        ):
            self.assertIn(f, body)
        # Curator fields
        for f in (
            "wiki_llm_curator_enabled",
            "wiki_llm_curator_url",
            "wiki_llm_curator_model",
            "wiki_llm_curator_temperature",
            "wiki_llm_curator_max_input_chars",
            "wiki_llm_curator_max_output_tokens",
            "wiki_llm_curator_timeout_sec",
            "wiki_llm_curator_concurrency",
            "wiki_llm_curator_mode",
            "wiki_llm_curator_require_quote_match",
            "wiki_llm_curator_require_chunk_id",
            "wiki_llm_curator_run_on_ingest",
            "wiki_llm_curator_run_on_query",
            "wiki_llm_curator_run_on_manual",
        ):
            self.assertIn(f, body)
        # Curator off by default
        self.assertFalse(body["wiki_llm_curator_enabled"])
        # effective_sources map present and well-formed
        es = body.get("effective_sources")
        self.assertIsInstance(es, dict)
        self.assertIn("wiki_llm_curator_enabled", es)
        self.assertIn(es["wiki_llm_curator_enabled"], ("kv", "env", "default"))

    def test_put_persists_curator_fields_and_round_trips(self):
        # Save curator settings (disabled) along with chosen URL/model.
        body = {
            "wiki_llm_curator_enabled": False,
            "wiki_llm_curator_url": "https://api.example.com",
            "wiki_llm_curator_model": "qwen-1b",
            "wiki_llm_curator_temperature": 0.0,
            "wiki_llm_curator_mode": "draft",
        }
        r = self.client.put("/api/settings", headers=self._hdr(), json=body)
        self.assertEqual(r.status_code, 200, r.text)
        # Reload and confirm round-trip.
        r2 = self.client.get("/api/settings", headers=self._hdr())
        self.assertEqual(r2.status_code, 200, r2.text)
        data = r2.json()
        self.assertEqual(data["wiki_llm_curator_url"], "https://api.example.com")
        self.assertEqual(data["wiki_llm_curator_model"], "qwen-1b")
        self.assertEqual(data["wiki_llm_curator_mode"], "draft")
        # effective_sources marks them as kv after PUT.
        self.assertEqual(
            data["effective_sources"]["wiki_llm_curator_url"], "kv"
        )

    def test_put_rejects_curator_enabled_without_url_or_model(self):
        body = {
            "wiki_llm_curator_enabled": True,
            # url and model intentionally omitted.
        }
        r = self.client.put("/api/settings", headers=self._hdr(), json=body)
        self.assertEqual(r.status_code, 422, r.text)
        detail = r.json().get("detail", "")
        self.assertIn("wiki_llm_curator_url", str(detail))
        self.assertIn("wiki_llm_curator_model", str(detail))

    def test_put_rejects_invalid_curator_temperature(self):
        body = {"wiki_llm_curator_temperature": 2.5}
        r = self.client.put("/api/settings", headers=self._hdr(), json=body)
        self.assertEqual(r.status_code, 422, r.text)

    def test_put_rejects_invalid_curator_mode(self):
        body = {"wiki_llm_curator_mode": "yolo"}
        r = self.client.put("/api/settings", headers=self._hdr(), json=body)
        self.assertEqual(r.status_code, 422, r.text)

    def test_put_rejects_invalid_curator_concurrency(self):
        body = {"wiki_llm_curator_concurrency": 99}
        r = self.client.put("/api/settings", headers=self._hdr(), json=body)
        self.assertEqual(r.status_code, 422, r.text)

    def test_curator_test_endpoint_blocks_loopback_without_opt_in(self):
        body = {"url": "http://127.0.0.1:11434", "model": "qwen"}
        r = self.client.post(
            "/api/settings/curator/test", headers=self._hdr(), json=body
        )
        self.assertEqual(r.status_code, 200, r.text)
        out = r.json()
        self.assertFalse(out["ok"])
        self.assertIn("ALLOW_LOCAL_CURATOR=1", out["error"])

    def test_curator_test_endpoint_requires_url_and_model(self):
        body = {"url": "", "model": ""}
        r = self.client.post(
            "/api/settings/curator/test", headers=self._hdr(), json=body
        )
        self.assertEqual(r.status_code, 200, r.text)
        out = r.json()
        self.assertFalse(out["ok"])
        self.assertIn("required", out["error"].lower())

    def test_effective_sources_treats_empty_env_var_as_default(self):
        """Critic Fix #4: ``X=""`` must NOT be labelled "env" since
        Pydantic falls back to the field default for empty strings.
        Otherwise the Models tab would mislead operators."""
        # Pick a field that has no kv override on this fresh DB.
        os.environ["RERANKER_URL"] = ""
        try:
            r = self.client.get("/api/settings", headers=self._hdr())
            self.assertEqual(r.status_code, 200, r.text)
            es = r.json()["effective_sources"]
            self.assertEqual(es["reranker_url"], "default")
        finally:
            os.environ.pop("RERANKER_URL", None)

    def test_curator_test_endpoint_requires_admin(self):
        """Reviewer Fix #2: non-admin must NOT reach the curator-test
        endpoint. Otherwise any authenticated viewer can probe outbound
        URLs and exfiltrate latency / model info."""
        # Seed a viewer-role user.
        conn = self.pool.get_connection()
        try:
            conn.execute(
                "INSERT INTO users (id, username, hashed_password, full_name, role, is_active) "
                "VALUES (9, 'viewer1', ?, 'V', 'viewer', 1)",
                (self.hash_password("pw"),),
            )
            conn.commit()
        finally:
            self.pool.release_connection(conn)
        viewer_token = self.create_token(9, "viewer1", "viewer")
        body = {"url": "https://api.example.com", "model": "qwen"}
        r = self.client.post(
            "/api/settings/curator/test",
            headers={"Authorization": f"Bearer {viewer_token}"},
            json=body,
        )
        # require_role("admin") returns 403 (forbidden) for non-admins.
        self.assertEqual(r.status_code, 403, r.text)


if __name__ == "__main__":
    unittest.main()
