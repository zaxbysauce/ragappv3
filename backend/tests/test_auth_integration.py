"""
Authentication integration tests using unittest and FastAPI TestClient.

Tests cover:
- Unauthenticated requests are rejected with 401
- Valid Bearer token authentication works
- Invalid Bearer token is rejected with 403
- Empty admin_secret_token requires authentication setup
"""
import os
import sys
import unittest
from unittest.mock import patch

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Stub missing optional dependencies
try:
    import lancedb
except ImportError:
    import types
    sys.modules['lancedb'] = types.ModuleType('lancedb')

try:
    import pyarrow
except ImportError:
    import types
    sys.modules['pyarrow'] = types.ModuleType('pyarrow')

try:
    from unstructured.partition.auto import partition
except ImportError:
    import types
    _unstructured = types.ModuleType('unstructured')
    _unstructured.__path__ = []
    _unstructured.partition = types.ModuleType('unstructured.partition')
    _unstructured.partition.__path__ = []
    _unstructured.partition.auto = types.ModuleType('unstructured.partition.auto')
    _unstructured.partition.auto.partition = lambda *args, **kwargs: []
    _unstructured.chunking = types.ModuleType('unstructured.chunking')
    _unstructured.chunking.__path__ = []
    _unstructured.chunking.title = types.ModuleType('unstructured.chunking.title')
    _unstructured.chunking.title.chunk_by_title = lambda *args, **kwargs: []
    _unstructured.documents = types.ModuleType('unstructured.documents')
    _unstructured.documents.__path__ = []
    _unstructured.documents.elements = types.ModuleType('unstructured.documents.elements')
    _unstructured.documents.elements.Element = type('Element', (), {})
    sys.modules['unstructured'] = _unstructured
    sys.modules['unstructured.partition'] = _unstructured.partition
    sys.modules['unstructured.partition.auto'] = _unstructured.partition.auto
    sys.modules['unstructured.chunking'] = _unstructured.chunking
    sys.modules['unstructured.chunking.title'] = _unstructured.chunking.title
    sys.modules['unstructured.documents'] = _unstructured.documents
    sys.modules['unstructured.documents.elements'] = _unstructured.documents.elements

from fastapi.testclient import TestClient

from app.config import settings


class TestAuthIntegration(unittest.TestCase):
    """Test suite for authentication integration."""

    def setUp(self):
        """Set up test client and store original settings."""
        self._original_token = settings.admin_secret_token
        # Import app after setting up any environment modifications
        from app.main import app
        self.client = TestClient(app)

    def tearDown(self):
        """Restore original settings after each test."""
        settings.admin_secret_token = self._original_token

    def test_unauthenticated_request_rejected_with_401(self):
        """Test that requests without auth header return 401 when token is configured."""
        # Set a valid admin secret token
        settings.admin_secret_token = "test-secret-token-123"

        # Make request without Authorization header
        response = self.client.get("/api/memories")

        self.assertEqual(response.status_code, 401)
        data = response.json()
        self.assertIn("detail", data)

    def test_valid_bearer_token_authentication_works(self):
        """Test that valid Bearer token allows access to protected endpoints."""
        # Set a valid admin secret token
        test_token = "valid-test-token-456"
        settings.admin_secret_token = test_token

        # Make request with valid Bearer token
        headers = {"Authorization": f"Bearer {test_token}"}
        response = self.client.get("/api/memories", headers=headers)

        # Should not be 401 or 403 - endpoint may return 200 or other valid status
        # but auth should pass (we're testing the auth layer here)
        self.assertNotEqual(response.status_code, 401)
        self.assertNotEqual(response.status_code, 403)

    def test_invalid_bearer_token_rejected_with_403(self):
        """Test that invalid Bearer token returns 403."""
        # Set a valid admin secret token
        settings.admin_secret_token = "correct-secret-token"

        # Make request with invalid Bearer token
        headers = {"Authorization": "Bearer wrong-token"}
        response = self.client.get("/api/memories", headers=headers)

        self.assertEqual(response.status_code, 403)
        data = response.json()
        self.assertIn("detail", data)

    def test_empty_admin_secret_token_requires_auth(self):
        """Test that empty admin_secret_token requires authentication setup."""
        # Clear the admin secret token
        settings.admin_secret_token = ""

        # Make any request - should get 401 since no token is configured
        response = self.client.get("/api/memories")

        self.assertEqual(response.status_code, 401)
        data = response.json()
        self.assertIn("detail", data)
        self.assertIn("Authentication required", data["detail"])

    def test_auth_header_case_insensitive_bearer(self):
        """Test that 'Bearer' prefix is case-insensitive."""
        test_token = "test-token-789"
        settings.admin_secret_token = test_token

        # Test lowercase 'bearer'
        headers = {"Authorization": f"bearer {test_token}"}
        response = self.client.get("/api/memories", headers=headers)

        # Should pass auth (not 401/403)
        self.assertNotEqual(response.status_code, 401)
        self.assertNotEqual(response.status_code, 403)

    def test_missing_bearer_prefix_returns_401(self):
        """Test that token without 'Bearer' prefix returns 401."""
        test_token = "test-token-abc"
        settings.admin_secret_token = test_token

        # Send token without Bearer prefix
        headers = {"Authorization": test_token}
        response = self.client.get("/api/memories", headers=headers)

        self.assertEqual(response.status_code, 401)

    def test_multiple_protected_endpoints_require_auth(self):
        """Test that various protected endpoints all require authentication."""
        settings.admin_secret_token = "protected-test-token"

        protected_endpoints = [
            ("/api/memories", "GET"),
            ("/api/documents", "GET"),
            ("/api/settings", "POST"),
            ("/api/chat", "POST"),
        ]

        for endpoint, method in protected_endpoints:
            with self.subTest(endpoint=endpoint, method=method):
                if method == "GET":
                    response = self.client.get(endpoint)
                elif method == "POST":
                    response = self.client.post(endpoint, json={})
                else:
                    continue

                self.assertEqual(response.status_code, 401)

    def test_valid_token_allows_access_to_multiple_endpoints(self):
        """Test that valid token allows access to various protected endpoints."""
        test_token = "multi-endpoint-token"
        settings.admin_secret_token = test_token
        headers = {"Authorization": f"Bearer {test_token}"}

        # Test GET endpoints that should work with valid auth
        get_endpoints = [
            "/api/memories",
            "/api/documents",
            "/api/settings",
        ]

        for endpoint in get_endpoints:
            with self.subTest(endpoint=endpoint):
                response = self.client.get(endpoint, headers=headers)
                # Should not be auth errors
                self.assertNotEqual(response.status_code, 401)
                self.assertNotEqual(response.status_code, 403)


class TestAuthEdgeCases(unittest.TestCase):
    """Test edge cases for authentication."""

    def setUp(self):
        """Set up test client and store original settings."""
        self._original_token = settings.admin_secret_token
        from app.main import app
        self.client = TestClient(app)

    def tearDown(self):
        """Restore original settings after each test."""
        settings.admin_secret_token = self._original_token

    def test_empty_authorization_header(self):
        """Test that empty Authorization header is handled correctly."""
        settings.admin_secret_token = "test-token"

        headers = {"Authorization": ""}
        response = self.client.get("/api/memories", headers=headers)

        self.assertEqual(response.status_code, 401)

    def test_bearer_with_empty_token(self):
        """Test that 'Bearer ' with empty token returns 401."""
        settings.admin_secret_token = "test-token"

        headers = {"Authorization": "Bearer "}
        response = self.client.get("/api/memories", headers=headers)

        self.assertEqual(response.status_code, 401)

    def test_whitespace_token(self):
        """Test that whitespace-only token is handled correctly."""
        settings.admin_secret_token = "test-token"

        headers = {"Authorization": "Bearer    "}
        response = self.client.get("/api/memories", headers=headers)

        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
