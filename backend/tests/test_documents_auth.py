"""Tests for documents routes authentication and RBAC protection.

This test suite verifies:
- Authentication: All document endpoints return 401 when unauthenticated
- Authorization: Permission-based access control for document operations
"""

import os
import sys
import tempfile
import threading
from pathlib import Path
import unittest
from queue import Empty, Queue
from unittest.mock import MagicMock, AsyncMock

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Stub missing optional dependencies
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
    from unstructured.partition.auto import partition
except ImportError:
    import types

    _unstructured = types.ModuleType("unstructured")
    _unstructured.__path__ = []
    _unstructured.partition = types.ModuleType("unstructured.partition")
    _unstructured.partition.__path__ = []
    _unstructured.partition.auto = types.ModuleType("unstructured.partition.auto")
    _unstructured.partition.auto.partition = lambda *args, **kwargs: []
    _unstructured.chunking = types.ModuleType("unstructured.chunking")
    _unstructured.chunking.__path__ = []
    _unstructured.chunking.title = types.ModuleType("unstructured.chunking.title")
    _unstructured.chunking.title.chunk_by_title = lambda *args, **kwargs: []
    _unstructured.documents = types.ModuleType("unstructured.documents")
    _unstructured.documents.__path__ = []
    _unstructured.documents.elements = types.ModuleType(
        "unstructured.documents.elements"
    )
    _unstructured.documents.elements.Element = type("Element", (), {})
    sys.modules["unstructured"] = _unstructured
    sys.modules["unstructured.partition"] = _unstructured.partition
    sys.modules["unstructured.partition.auto"] = _unstructured.partition.auto
    sys.modules["unstructured.chunking"] = _unstructured.chunking
    sys.modules["unstructured.chunking.title"] = _unstructured.chunking.title
    sys.modules["unstructured.documents"] = _unstructured.documents
    sys.modules["unstructured.documents.elements"] = _unstructured.documents.elements

from fastapi.testclient import TestClient

from app.main import app
from app.api.deps import (
    get_db,
    get_vector_store,
    get_embedding_service,
    get_db_pool,
    get_background_processor,
)
from app.services.auth_service import create_access_token, hash_password
from app.config import settings
import sqlite3


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
            except:
                conn.close()

    def close_all(self):
        self._closed = True
        while True:
            try:
                conn = self._pool.get_nowait()
                conn.close()
            except Empty:
                break


class TestDocumentAuthBase(unittest.TestCase):
    """Base test class for document auth tests."""

    def setUp(self):
        """Set up test client with temporary database."""
        self.client = TestClient(app)
        self._temp_dir = tempfile.mkdtemp()

        # Store original settings BEFORE modifying
        self._original_jwt_secret = settings.jwt_secret_key
        self._original_users_enabled = settings.users_enabled
        self._original_data_dir = settings.data_dir

        # CRITICAL: Update settings.data_dir so sqlite_path points to test db
        settings.data_dir = Path(self._temp_dir)
        settings.jwt_secret_key = "test-secret-key-for-testing-at-least-32-chars-long"
        settings.users_enabled = True

        # Use app.db to align with settings.sqlite_path
        self._db_path = str(Path(self._temp_dir) / "app.db")

        # Clear pool cache BEFORE setting up new database
        from app.models.database import _pool_cache, _pool_cache_lock

        with _pool_cache_lock:
            for path, pool in list(_pool_cache.items()):
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

        # Mock vector store for tests
        self._mock_vector_store = MagicMock()
        self._mock_vector_store.db = None
        self._mock_vector_store.delete_by_file = AsyncMock(return_value=1)

        # Mock embedding service
        self._mock_embedding_service = MagicMock()

        # Mock db pool
        self._mock_db_pool = self._connection_pool

        # Mock background processor
        self._mock_background_processor = MagicMock()
        self._mock_background_processor.is_running = True
        self._mock_background_processor.enqueue = AsyncMock()

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_vector_store] = lambda: self._mock_vector_store
        app.dependency_overrides[get_embedding_service] = lambda: (
            self._mock_embedding_service
        )
        app.dependency_overrides[get_db_pool] = lambda: self._mock_db_pool
        app.dependency_overrides[get_background_processor] = lambda: (
            self._mock_background_processor
        )

        # Seed test users and vaults
        conn = self._connection_pool.get_connection()
        try:
            conn.execute("PRAGMA foreign_keys = ON")

            # Clear existing data
            conn.execute("DELETE FROM files")
            conn.execute("DELETE FROM vault_members")
            conn.execute("DELETE FROM users WHERE id != 0")

            pw = hash_password("testpass")

            # User 1: superadmin
            conn.execute(
                "INSERT OR IGNORE INTO users (id, username, hashed_password, full_name, role, is_active) VALUES (?, ?, ?, ?, ?, 1)",
                (1, "superadmin", pw, "Super Admin", "superadmin"),
            )
            # User 2: admin
            conn.execute(
                "INSERT OR IGNORE INTO users (id, username, hashed_password, full_name, role, is_active) VALUES (?, ?, ?, ?, ?, 1)",
                (2, "admin1", pw, "Admin One", "admin"),
            )
            # User 3: member with vault access
            conn.execute(
                "INSERT OR IGNORE INTO users (id, username, hashed_password, full_name, role, is_active) VALUES (?, ?, ?, ?, ?, 1)",
                (3, "member1", pw, "Member One", "member"),
            )
            # User 4: member with read-only vault access
            conn.execute(
                "INSERT OR IGNORE INTO users (id, username, hashed_password, full_name, role, is_active) VALUES (?, ?, ?, ?, ?, 1)",
                (4, "member_readonly", pw, "Member Read Only", "member"),
            )
            # User 5: member without any vault access
            conn.execute(
                "INSERT OR IGNORE INTO users (id, username, hashed_password, full_name, role, is_active) VALUES (?, ?, ?, ?, ?, 1)",
                (5, "member_novault", pw, "Member No Vault", "member"),
            )

            # Create additional vaults for testing (Vault 1 is the Default vault)
            conn.execute(
                "INSERT OR IGNORE INTO vaults (id, name, description) VALUES (?, ?, ?)",
                (2, "Private Vault", "A private vault"),
            )
            conn.execute(
                "INSERT OR IGNORE INTO vaults (id, name, description) VALUES (?, ?, ?)",
                (3, "Read-Only Vault", "A read-only vault"),
            )

            # Seed vault_members
            # member1 (user 3) has WRITE access to vault 2
            conn.execute(
                "INSERT OR IGNORE INTO vault_members (vault_id, user_id, permission, granted_by) VALUES (?, ?, ?, ?)",
                (2, 3, "write", 1),
            )
            # member_readonly (user 4) has READ access to vault 3
            conn.execute(
                "INSERT OR IGNORE INTO vault_members (vault_id, user_id, permission, granted_by) VALUES (?, ?, ?, ?)",
                (3, 4, "read", 1),
            )

            # Seed a test document
            conn.execute(
                "INSERT OR IGNORE INTO files (id, file_name, file_path, file_size, status, chunk_count, vault_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (1, "test_doc.txt", "/uploads/test_doc.txt", 100, "indexed", 0, 2),
            )

            conn.commit()
        finally:
            self._connection_pool.release_connection(conn)

    def tearDown(self):
        """Clean up after each test."""
        # Clear pool cache before changing paths
        from app.models.database import _pool_cache, _pool_cache_lock

        with _pool_cache_lock:
            for path, pool in list(_pool_cache.items()):
                pool.close_all()
            _pool_cache.clear()

        # Restore original settings
        settings.jwt_secret_key = self._original_jwt_secret
        settings.users_enabled = self._original_users_enabled
        if hasattr(self, "_original_data_dir"):
            settings.data_dir = self._original_data_dir

        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_vector_store, None)
        app.dependency_overrides.pop(get_embedding_service, None)
        app.dependency_overrides.pop(get_db_pool, None)
        app.dependency_overrides.pop(get_background_processor, None)

        if hasattr(self, "_connection_pool"):
            self._connection_pool.close_all()

        import shutil

        shutil.rmtree(self._temp_dir, ignore_errors=True)

    def _get_db_conn(self):
        """Get a raw connection for test data setup."""
        return self._connection_pool.get_connection()

    def _superadmin_token(self):
        """Generate access token for superadmin user."""
        return create_access_token(1, "superadmin", "superadmin")

    def _admin_token(self):
        """Generate access token for admin user."""
        return create_access_token(2, "admin1", "admin")

    def _member_token(self):
        """Generate access token for member1 user (has vault access)."""
        return create_access_token(3, "member1", "member")

    def _member_readonly_token(self):
        """Generate access token for member_readonly user."""
        return create_access_token(4, "member_readonly", "member")

    def _member_no_access_token(self):
        """Generate access token for member_novault user (no vault access)."""
        return create_access_token(5, "member_novault", "member")

    def _auth_headers(self, token):
        """Create authorization headers with token."""
        return {"Authorization": f"Bearer {token}"}


class TestAuthentication(TestDocumentAuthBase):
    """Tests for unauthenticated access - all endpoints should return 401."""

    def test_get_documents_unauthenticated(self):
        """GET /documents without auth returns 401."""
        response = self.client.get("/api/documents")
        self.assertEqual(response.status_code, 401)

    def test_get_documents_stats_unauthenticated(self):
        """GET /documents/stats without auth returns 401."""
        response = self.client.get("/api/documents/stats")
        self.assertEqual(response.status_code, 401)

    def test_post_documents_unauthenticated(self):
        """POST /documents without auth returns 401."""
        response = self.client.post(
            "/api/documents", data={"file": (b"test content", "test.txt")}
        )
        self.assertEqual(response.status_code, 401)

    def test_post_documents_upload_unauthenticated(self):
        """POST /documents/upload without auth returns 401."""
        response = self.client.post(
            "/api/documents/upload", data={"file": (b"test content", "test.txt")}
        )
        self.assertEqual(response.status_code, 401)

    def test_post_documents_scan_unauthenticated(self):
        """POST /documents/scan without auth returns 401."""
        response = self.client.post("/api/documents/scan")
        self.assertEqual(response.status_code, 401)

    def test_delete_documents_by_id_unauthenticated(self):
        """DELETE /documents/{id} without auth returns 401."""
        response = self.client.delete("/api/documents/1")
        self.assertEqual(response.status_code, 401)

    def test_post_documents_batch_unauthenticated(self):
        """POST /documents/batch without auth returns 401."""
        response = self.client.post("/api/documents/batch", json=["1", "2"])
        self.assertEqual(response.status_code, 401)

    def test_delete_documents_vault_all_unauthenticated(self):
        """DELETE /documents/vault/{id}/all without auth returns 401."""
        response = self.client.delete("/api/documents/vault/2/all")
        self.assertEqual(response.status_code, 401)

    def test_post_documents_admin_retry_unauthenticated(self):
        """POST /documents/admin/retry/{id} without auth returns 401."""
        response = self.client.post("/api/documents/admin/retry/1")
        self.assertEqual(response.status_code, 401)


class TestWritePermission(TestDocumentAuthBase):
    """Tests for write permission checks (member without write permission → 403)."""

    def test_member_without_write_permission_post_documents_returns_403(self):
        """Member with read-only access → 403 on POST /documents."""
        # member_readonly (user 4) has READ permission on vault 3, not write
        response = self.client.post(
            "/api/documents?vault_id=3",
            headers=self._auth_headers(self._member_readonly_token()),
            data={"file": (b"test content", "test.txt")},
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn("Insufficient vault permissions", response.text or "")

    def test_member_without_write_permission_post_documents_upload_returns_403(self):
        """Member with read-only access → 403 on POST /documents/upload."""
        # member_readonly (user 4) has READ permission on vault 3, not write
        response = self.client.post(
            "/api/documents/upload?vault_id=3",
            headers=self._auth_headers(self._member_readonly_token()),
            data={"file": (b"test content", "test.txt")},
        )
        self.assertEqual(response.status_code, 403)

    def test_member_without_write_permission_post_documents_scan_returns_403(self):
        """Member with read-only access → 403 on POST /documents/scan."""
        # member_readonly (user 4) has READ permission on vault 3, not write
        response = self.client.post(
            "/api/documents/scan?vault_id=3",
            headers=self._auth_headers(self._member_readonly_token()),
        )
        self.assertEqual(response.status_code, 403)

    def test_member_without_vault_access_post_documents_returns_403(self):
        """Member without vault access → 403 on POST /documents."""
        # member_novault (user 5) has no vault access
        response = self.client.post(
            "/api/documents?vault_id=2",
            headers=self._auth_headers(self._member_no_access_token()),
            data={"file": (b"test content", "test.txt")},
        )
        self.assertEqual(response.status_code, 403)


class TestAdminPermission(TestDocumentAuthBase):
    """Tests for admin permission checks on document operations."""

    def test_member_without_admin_permission_delete_document_returns_403(self):
        """Member without admin permission → 403 on DELETE /documents/{id}."""
        # member1 (user 3) has WRITE permission on vault 2, not admin
        # Delete document in vault 2 should require vault admin
        response = self.client.delete(
            "/api/documents/1", headers=self._auth_headers(self._member_token())
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn("Insufficient vault permissions", response.text or "")

    def test_member_without_admin_permission_delete_vault_all_returns_403(self):
        """Member without admin permission → 403 on DELETE /documents/vault/{id}/all."""
        # member1 (user 3) has WRITE permission on vault 2, not admin
        response = self.client.delete(
            "/api/documents/vault/2/all",
            headers=self._auth_headers(self._member_token()),
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn("Insufficient vault permissions", response.text or "")


class TestRoleAdminRequired(TestDocumentAuthBase):
    """Tests for endpoints requiring admin/superadmin role."""

    def test_regular_member_post_documents_batch_returns_403(self):
        """Regular member → 403 on POST /documents/batch (requires admin role)."""
        # member1 (user 3) is a regular member, not admin
        response = self.client.post(
            "/api/documents/batch",
            headers=self._auth_headers(self._member_token()),
            json=["1"],
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn("Admin access required", response.text or "")

    def test_regular_member_post_documents_admin_retry_returns_403(self):
        """Regular member → 403 on POST /documents/admin/retry/{id} (requires admin role)."""
        # member1 (user 3) is a regular member, not admin
        response = self.client.post(
            "/api/documents/admin/retry/1",
            headers=self._auth_headers(self._member_token()),
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn("Admin access required", response.text or "")

    def test_admin_can_post_documents_batch(self):
        """Admin can POST /documents/batch."""
        # admin1 (user 2) is an admin
        response = self.client.post(
            "/api/documents/batch",
            headers=self._auth_headers(self._admin_token()),
            json=["1"],
        )
        # Should not return 401 or 403 - might return 404 for missing file
        self.assertNotEqual(response.status_code, 401)
        self.assertNotEqual(response.status_code, 403)

    def test_superadmin_can_post_documents_admin_retry(self):
        """Superadmin can POST /documents/admin/retry/{id}."""
        # superadmin (user 1) is a superadmin
        response = self.client.post(
            "/api/documents/admin/retry/1",
            headers=self._auth_headers(self._superadmin_token()),
        )
        # Should not return 401 or 403 - might return 404 for missing file
        self.assertNotEqual(response.status_code, 401)
        self.assertNotEqual(response.status_code, 403)


class TestReadAccess(TestDocumentAuthBase):
    """Tests for read access - members with read access can list documents."""

    def test_member_with_read_access_can_list_documents(self):
        """Member with read access can GET /documents."""
        # member_readonly (user 4) has READ permission on vault 3
        response = self.client.get(
            "/api/documents?vault_id=3",
            headers=self._auth_headers(self._member_readonly_token()),
        )
        # Should succeed (200) or at least not 403
        self.assertNotEqual(response.status_code, 401)
        self.assertNotEqual(response.status_code, 403)

    def test_member_with_read_access_can_get_stats(self):
        """Member with read access can GET /documents/stats."""
        # member_readonly (user 4) has READ permission on vault 3
        response = self.client.get(
            "/api/documents/stats?vault_id=3",
            headers=self._auth_headers(self._member_readonly_token()),
        )
        # Should succeed (200) or at least not 403
        self.assertNotEqual(response.status_code, 401)
        self.assertNotEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
