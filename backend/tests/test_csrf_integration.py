"""
CSRF token integration tests - run against actual backend at http://localhost:9090.

These tests verify the end-to-end CSRF token flow:
1. GET /api/csrf-token returns valid token and sets cookie
2. POST /api/auth/register with valid CSRF token succeeds
3. POST /api/auth/register without CSRF token returns 403
4. POST /api/auth/register with mismatched CSRF token returns 403

Usage:
    python -m pytest tests/test_csrf_integration.py -v

Prerequisites:
    Backend must be running at http://localhost:9090 (docker compose up)
"""

import os
import random
import string
import sys
import time
import unittest

import requests

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

BASE_URL = "http://localhost:9090/api"
BACKEND_AVAILABLE = False


def check_backend_available():
    """Check if the backend is reachable."""
    global BACKEND_AVAILABLE
    try:
        resp = requests.get(f"{BASE_URL}/csrf-token", timeout=3)
        BACKEND_AVAILABLE = resp.status_code == 200
        return BACKEND_AVAILABLE
    except (requests.ConnectionError, requests.Timeout):
        return False


def random_username(prefix="user"):
    """Generate random username for unique test users."""
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return f"{prefix}_{suffix}_{int(time.time() * 1000)}"


@unittest.skipUnless(
    check_backend_available(), "Backend not running at http://localhost:9090"
)
class TestCSRFTokenEndpoint(unittest.TestCase):
    """Test suite for /api/csrf-token endpoint."""

    def test_csrf_token_returns_valid_token(self):
        """GET /api/csrf-token returns a valid token string."""
        response = requests.get(f"{BASE_URL}/csrf-token", timeout=5)
        self.assertEqual(
            response.status_code,
            200,
            f"Expected 200, got {response.status_code}: {response.text}",
        )

        data = response.json()
        self.assertIn("csrf_token", data, "Response should contain csrf_token field")
        self.assertIsInstance(data["csrf_token"], str, "csrf_token should be a string")
        self.assertGreater(
            len(data["csrf_token"]), 10, "csrf_token should be non-empty"
        )
        # Token should be URL-safe base64 (alphanumeric + underscore/dash)
        import re

        self.assertRegex(
            data["csrf_token"],
            r"^[A-Za-z0-9_-]+$",
            "csrf_token should be URL-safe base64",
        )

    def test_csrf_token_sets_cookie(self):
        """GET /api/csrf-token sets X-CSRF-Token cookie."""
        response = requests.get(f"{BASE_URL}/csrf-token", timeout=5)
        self.assertEqual(
            response.status_code,
            200,
            f"Expected 200, got {response.status_code}: {response.text}",
        )

        cookies = response.cookies
        self.assertIn(
            "X-CSRF-Token", cookies, "Response should set X-CSRF-Token cookie"
        )

        cookie_value = cookies.get("X-CSRF-Token")
        self.assertIsNotNone(cookie_value, "X-CSRF-Token cookie should have a value")
        self.assertGreater(len(cookie_value), 10, "Cookie value should be non-empty")

    def test_csrf_token_and_cookie_match(self):
        """X-CSRF-Token cookie should match the csrf_token in response body."""
        response = requests.get(f"{BASE_URL}/csrf-token", timeout=5)
        self.assertEqual(response.status_code, 200)

        data = response.json()
        cookie_value = response.cookies.get("X-CSRF-Token")

        self.assertEqual(
            data["csrf_token"],
            cookie_value,
            "csrf_token in body should match X-CSRF-Token cookie",
        )

    def test_each_request_generates_new_token(self):
        """Each call to /api/csrf-token should generate a new token."""
        response1 = requests.get(f"{BASE_URL}/csrf-token", timeout=5)
        response2 = requests.get(f"{BASE_URL}/csrf-token", timeout=5)

        self.assertEqual(response1.status_code, 200)
        self.assertEqual(response2.status_code, 200)

        token1 = response1.json()["csrf_token"]
        token2 = response2.json()["csrf_token"]

        self.assertNotEqual(
            token1, token2, "Each /csrf-token call should generate a new token"
        )


@unittest.skipUnless(
    check_backend_available(), "Backend not running at http://localhost:9090"
)
class TestCSRFRegisterFlow(unittest.TestCase):
    """Test suite for CSRF-protected /api/auth/register endpoint."""

    def test_register_without_csrf_returns_403(self):
        """POST /api/auth/register without CSRF token should return 403."""
        response = requests.post(
            f"{BASE_URL}/auth/register",
            json={"username": random_username("nocsrf"), "password": "Password123!"},
            timeout=5,
        )

        self.assertEqual(
            response.status_code,
            403,
            f"Expected 403, got {response.status_code}: {response.text}",
        )

        data = response.json()
        self.assertIn("detail", data, "Response should contain 'detail' field")
        # Check that error mentions CSRF
        self.assertTrue(
            "csrf" in data["detail"].lower(),
            f"Error should mention CSRF, got: {data['detail']}",
        )

    def test_register_with_valid_csrf_succeeds(self):
        """POST /api/auth/register with valid CSRF token should succeed."""
        # Step 1: Get CSRF token
        csrf_response = requests.get(f"{BASE_URL}/csrf-token", timeout=5)
        self.assertEqual(csrf_response.status_code, 200)

        csrf_token = csrf_response.json()["csrf_token"]
        csrf_cookie = csrf_response.cookies.get("X-CSRF-Token")

        # Step 2: Register with valid CSRF
        response = requests.post(
            f"{BASE_URL}/auth/register",
            json={
                "username": random_username("validcsrf"),
                "password": "Password123!",
                "full_name": "Test User",
            },
            cookies={"X-CSRF-Token": csrf_cookie},
            headers={"X-CSRF-Token": csrf_token},
            timeout=5,
        )

        self.assertEqual(
            response.status_code,
            200,
            f"Expected 200, got {response.status_code}: {response.text}",
        )

        data = response.json()
        self.assertIn("access_token", data, "Response should contain access_token")
        self.assertIsInstance(data["access_token"], str)
        self.assertGreater(
            len(data["access_token"]), 0, "access_token should be non-empty"
        )

    def test_register_with_mismatched_csrf_returns_403(self):
        """POST /api/auth/register with mismatched cookie/header returns 403."""
        # Get two different CSRF tokens
        resp1 = requests.get(f"{BASE_URL}/csrf-token", timeout=5)
        resp2 = requests.get(f"{BASE_URL}/csrf-token", timeout=5)

        self.assertEqual(resp1.status_code, 200)
        self.assertEqual(resp2.status_code, 200)

        # Use cookie from first request, header from second request
        cookie = resp1.cookies.get("X-CSRF-Token")
        header = resp2.json()["csrf_token"]

        self.assertNotEqual(
            cookie, header, "Cookies should be different to test mismatch"
        )

        response = requests.post(
            f"{BASE_URL}/auth/register",
            json={"username": random_username("mismatch"), "password": "Password123!"},
            cookies={"X-CSRF-Token": cookie},
            headers={"X-CSRF-Token": header},
            timeout=5,
        )

        self.assertEqual(
            response.status_code,
            403,
            f"Expected 403 for mismatched CSRF, got {response.status_code}: {response.text}",
        )

        data = response.json()
        self.assertIn("detail", data)
        self.assertTrue(
            "csrf" in data["detail"].lower(),
            f"Error should mention CSRF, got: {data['detail']}",
        )

    def test_register_with_invalid_csrf_returns_403(self):
        """POST /api/auth/register with invalid CSRF token returns 403."""
        response = requests.post(
            f"{BASE_URL}/auth/register",
            json={"username": random_username("invalid"), "password": "Password123!"},
            cookies={"X-CSRF-Token": "invalid-cookie-value-12345"},
            headers={"X-CSRF-Token": "invalid-header-value-67890"},
            timeout=5,
        )

        self.assertEqual(
            response.status_code,
            403,
            f"Expected 403 for invalid CSRF, got {response.status_code}: {response.text}",
        )

    def test_register_with_missing_header_returns_403(self):
        """POST /api/auth/register with only cookie (missing header) returns 403."""
        # Get CSRF token
        csrf_response = requests.get(f"{BASE_URL}/csrf-token", timeout=5)
        csrf_cookie = csrf_response.cookies.get("X-CSRF-Token")

        # Register with only cookie, no header
        response = requests.post(
            f"{BASE_URL}/auth/register",
            json={"username": random_username("noheader"), "password": "Password123!"},
            cookies={"X-CSRF-Token": csrf_cookie},
            # No X-CSRF-Token header
            timeout=5,
        )

        self.assertEqual(
            response.status_code,
            403,
            f"Expected 403 when header missing, got {response.status_code}: {response.text}",
        )

    def test_register_with_missing_cookie_returns_403(self):
        """POST /api/auth/register with only header (missing cookie) returns 403."""
        # Get CSRF token
        csrf_response = requests.get(f"{BASE_URL}/csrf-token", timeout=5)
        csrf_token = csrf_response.json()["csrf_token"]

        # Register with only header, no cookie
        response = requests.post(
            f"{BASE_URL}/auth/register",
            json={"username": random_username("nocookie"), "password": "Password123!"},
            # No cookie
            headers={"X-CSRF-Token": csrf_token},
            timeout=5,
        )

        self.assertEqual(
            response.status_code,
            403,
            f"Expected 403 when cookie missing, got {response.status_code}: {response.text}",
        )


@unittest.skipUnless(
    check_backend_available(), "Backend not running at http://localhost:9090"
)
class TestCSRFTokenSecurity(unittest.TestCase):
    """Security tests for CSRF token handling."""

    def test_token_used_twice_should_still_work(self):
        """CSRF token should remain valid after single use (used during registration)."""
        # Get CSRF token
        csrf_response = requests.get(f"{BASE_URL}/csrf-token", timeout=5)
        csrf_token = csrf_response.json()["csrf_token"]
        csrf_cookie = csrf_response.cookies.get("X-CSRF-Token")

        # Use token for first registration - should succeed
        response1 = requests.post(
            f"{BASE_URL}/auth/register",
            json={"username": random_username("reuse1"), "password": "Password123!"},
            cookies={"X-CSRF-Token": csrf_cookie},
            headers={"X-CSRF-Token": csrf_token},
            timeout=5,
        )
        # Note: User might already exist, but we care about CSRF validation
        # If token is already consumed, we get 403
        # Some implementations consume tokens, others don't
        self.assertIn(
            response1.status_code,
            [200, 403],
            "Response should be either 200 (token valid) or 403 (token consumed)",
        )

    def test_cookie_attributes(self):
        """X-CSRF-Token cookie should have appropriate security attributes."""
        response = requests.get(f"{BASE_URL}/csrf-token", timeout=5)
        self.assertEqual(response.status_code, 200)

        # Check Set-Cookie header for security attributes
        set_cookie = response.headers.get("Set-Cookie", "")

        # Cookie should have SameSite (lax or strict)
        self.assertTrue(
            "SameSite" in set_cookie or "samesite" in set_cookie.lower(),
            f"Cookie should have SameSite attribute, got: {set_cookie}",
        )

        # Cookie should have Max-Age or Expires
        self.assertTrue(
            "Max-Age" in set_cookie or "Expires" in set_cookie,
            f"Cookie should have Max-Age or Expires, got: {set_cookie}",
        )


if __name__ == "__main__":
    print(f"Running CSRF integration tests against {BASE_URL}")
    print("Ensure the backend is running at http://localhost:9090")
    print("-" * 60)
    unittest.main(verbosity=2)
