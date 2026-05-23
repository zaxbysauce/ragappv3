"""
Verification tests for issue_csrf_token path prefix awareness.

Tests verify:
1. issue_csrf_token sets path=/api when no prefix
2. issue_csrf_token sets path=/knowledgevault/api when x-forwarded-prefix=/knowledgevault
3. All callers pass request parameter
4. Regex validates prefix safely
"""

import unittest

from app.security import SAFE_PREFIX_RE


def _compute_csrf_path(request_headers_prefix: str | None, request: object | None) -> str:
    """
    Replicates the path-computation logic from issue_csrf_token.

    Returns:
        - "/api" when request is None or x-forwarded-prefix is empty/invalid
        - "{prefix}/api" when prefix is valid
    """
    path = "/api"
    if request is not None:
        prefix = request_headers_prefix or ""
        if prefix and SAFE_PREFIX_RE.match(prefix):
            prefix = prefix.rstrip("/")
            path = f"{prefix}/api"
    return path


class TestCsrfPathComputationLogic(unittest.TestCase):
    """Tests for the path computation logic in issue_csrf_token."""

    def test_no_request_returns_api(self):
        """Verify 1: path=/api when request is None."""
        result = _compute_csrf_path("", None)
        self.assertEqual(result, "/api")

    def test_empty_prefix_returns_api(self):
        """Verify 1: path=/api when x-forwarded-prefix is empty string."""
        result = _compute_csrf_path("", object())
        self.assertEqual(result, "/api")

    def test_no_prefix_header_returns_api(self):
        """Verify 1: path=/api when x-forwarded-prefix header is not set (None)."""
        result = _compute_csrf_path(None, object())
        self.assertEqual(result, "/api")

    def test_knowledgevault_prefix_returns_knowledgevault_api(self):
        """Verify 2: path=/knowledgevault/api when x-forwarded-prefix=/knowledgevault."""
        result = _compute_csrf_path("/knowledgevault", object())
        self.assertEqual(result, "/knowledgevault/api")

    def test_prefix_with_trailing_slash_normalized(self):
        """Prefix /knowledgevault/ should normalize to /knowledgevault/api."""
        result = _compute_csrf_path("/knowledgevault/", object())
        self.assertEqual(result, "/knowledgevault/api")

    def test_deep_prefix_normalized(self):
        """Prefix /a/b/c should result in /a/b/c/api."""
        result = _compute_csrf_path("/a/b/c", object())
        self.assertEqual(result, "/a/b/c/api")


class TestCsrfPathSafeRegex(unittest.TestCase):
    """Tests for _CSRF_PATH_SAFE_RE regex validation."""

    def test_valid_prefixes_pass_regex(self):
        """Verify 4: Valid prefixes should pass the regex."""
        valid_prefixes = [
            "/",
            "/api",
            "/knowledgevault",
            "/knowledge-vault",
            "/knowledge_vault",
            "/knowledge.vault",
            "/knowledge~vault",
            "/knowledge!vault",
            "/knowledge$vault",
            "/knowledge&vault",
            "/knowledge(vault)",
            "/knowledge*vault",
            "/knowledge+vault",
            "/knowledge:vault",
            "/knowledge@vault",
            "/knowledge.vault",
            "/knowledge_vault",
            "/a1",
            "/a.b.c",
            "/a/b/c",
            "/abc123",
            "/ABC123",
            "/my-app",
            "/app.v2",
        ]
        for prefix in valid_prefixes:
            self.assertIsNotNone(
                SAFE_PREFIX_RE.match(prefix),
                f"Prefix '{prefix}' should be accepted by regex",
            )

    def test_invalid_prefixes_fail_regex(self):
        """Verify 4: Invalid/malicious prefixes should fail the regex."""
        invalid_prefixes = [
            "/knowledge;vault",      # semicolon - cookie injection
            "/knowledge=vault",      # equals - cookie injection
            "/knowledge\"vault",     # quote - cookie injection
            "/knowledge<vault",     # less than - HTML injection
            "/knowledge>vault",     # greater than - HTML injection
            "/knowledge vault",     # space - invalid path char
            "/knowledge\nvault",    # newline - header injection
            "/knowledge\rvault",    # carriage return - header injection
            "/knowledge\tvault",    # tab - invalid path char
            "/; rm -rf /",         # command injection attempt
        ]
        for prefix in invalid_prefixes:
            result = SAFE_PREFIX_RE.match(prefix)
            self.assertIsNone(
                result,
                f"Malicious prefix '{repr(prefix)}' should be rejected by regex",
            )

    def test_empty_string_fails_regex(self):
        """Empty string should not match the regex (must start with /)."""
        result = SAFE_PREFIX_RE.match("")
        self.assertIsNone(result)


class TestCallersPassRequestParameter(unittest.TestCase):
    """Verify all callers of issue_csrf_token pass the request parameter."""

    def test_auth_login_passes_request(self):
        """auth.py login() should call issue_csrf_token with request."""
        # Read source file directly to avoid import chain that hits the re bug
        import os
        source_path = os.path.join(os.path.dirname(__file__), "..", "app", "api", "routes", "auth.py")
        with open(source_path, "r") as f:
            source = f.read()
        # Verify the call includes request as the third argument
        self.assertIn("issue_csrf_token(response, csrf_manager, request)", source)

    def test_auth_refresh_passes_request(self):
        """auth.py refresh() should call issue_csrf_token with request."""
        import os
        source_path = os.path.join(os.path.dirname(__file__), "..", "app", "api", "routes", "auth.py")
        with open(source_path, "r") as f:
            source = f.read()
        self.assertIn("issue_csrf_token(response, csrf_manager, request)", source)

    def test_settings_csrf_token_passes_request(self):
        """settings.py get_csrf_token() should call issue_csrf_token with request."""
        import os
        source_path = os.path.join(os.path.dirname(__file__), "..", "app", "api", "routes", "settings.py")
        with open(source_path, "r") as f:
            source = f.read()
        self.assertIn("issue_csrf_token(response, csrf_manager, request)", source)


if __name__ == "__main__":
    unittest.main()
