"""
Verification tests for _get_cookie_path helper in auth routes.

Tests verify:
1. No prefix header → returns suffix as-is
2. Prefix `/knowledgevault` + suffix `/api/auth/refresh` → `/knowledgevault/api/auth/refresh`
3. Prefix `/knowledgevault/` (trailing slash) → `/knowledgevault/api/auth/refresh`
4. Prefix `''` (empty string) → returns suffix as-is
"""

import unittest
from unittest.mock import MagicMock
from starlette.requests import Request


class TestGetCookiePath(unittest.TestCase):
    """Tests for _get_cookie_path helper function."""

    def _call_get_cookie_path(self, prefix_header_value: str, suffix: str):
        """Helper to call _get_cookie_path with a mocked request."""
        from app.api.routes.auth import _get_cookie_path

        mock_request = MagicMock(spec=Request)
        mock_request.headers.get.return_value = prefix_header_value
        # Use a plain object for state to avoid auto-creation of attributes
        # that would make hasattr() return True incorrectly
        mock_request.state = type('State', (), {})()
        return _get_cookie_path(mock_request, suffix)

    def test_no_prefix_returns_suffix_as_is(self):
        """Case 1: No x-forwarded-prefix header → returns suffix as-is."""
        result = self._call_get_cookie_path("", "/api/auth/refresh")
        self.assertEqual(result, "/api/auth/refresh")

    def test_prefix_without_trailing_slash(self):
        """Case 2: Prefix `/knowledgevault` + suffix `/api/auth/refresh` → `/knowledgevault/api/auth/refresh`."""
        result = self._call_get_cookie_path("/knowledgevault", "/api/auth/refresh")
        self.assertEqual(result, "/knowledgevault/api/auth/refresh")

    def test_prefix_with_trailing_slash(self):
        """Case 3: Prefix `/knowledgevault/` (trailing slash) → `/knowledgevault/api/auth/refresh`."""
        result = self._call_get_cookie_path("/knowledgevault/", "/api/auth/refresh")
        self.assertEqual(result, "/knowledgevault/api/auth/refresh")

    def test_empty_string_prefix_returns_suffix_as_is(self):
        """Case 4: Prefix `''` (empty string) → returns suffix as-is."""
        result = self._call_get_cookie_path("", "/api/auth/refresh")
        self.assertEqual(result, "/api/auth/refresh")

    def test_suffix_without_leading_slash_gets_added(self):
        """Suffix without leading slash gets `/` prepended."""
        result = self._call_get_cookie_path("/knowledgevault", "api/auth/refresh")
        self.assertEqual(result, "/knowledgevault/api/auth/refresh")

    def test_none_prefix_returns_suffix_as_is(self):
        """x-forwarded-prefix header returning None (not set) returns suffix as-is."""
        result = self._call_get_cookie_path(None, "/api/auth/refresh")
        self.assertEqual(result, "/api/auth/refresh")

    def test_invalid_prefix_with_semicolon_falls_back_to_suffix(self):
        """Invalid prefix containing ';' (cookie injection attempt) → falls back to suffix only."""
        result = self._call_get_cookie_path("/knowledge;vault", "/api/auth/refresh")
        self.assertEqual(result, "/api/auth/refresh")

    def test_invalid_prefix_with_semicolon_at_start(self):
        """Invalid prefix starting with ';' → falls back to suffix only."""
        result = self._call_get_cookie_path(";knowledgevault", "/api/auth/refresh")
        self.assertEqual(result, "/api/auth/refresh")

    def test_various_injection_chars_all_rejected(self):
        """Various cookie-injection characters are rejected."""
        # Test various injection characters individually
        # Note: single quote (') is allowed by SAFE_PREFIX_RE: r"^(?!.*\.\.)[/A-Za-z0-9._~!$&'()*+:@%-]+$"
        injection_chars = [";", '"', "<", ">", " ", "\n", "\r"]
        for char in injection_chars:
            prefix_with_char = f"/knowledge{char}vault"
            result = self._call_get_cookie_path(prefix_with_char, "/api/auth/refresh")
            self.assertEqual(
                result,
                "/api/auth/refresh",
                f"Prefix with char '{repr(char)}' should be rejected",
            )

    def test_invalid_prefix_with_equals_sign_falls_back_to_suffix(self):
        """Invalid prefix containing '=' (cookie injection attempt) → falls back to suffix only."""
        result = self._call_get_cookie_path("/knowledge=vault", "/api/auth/refresh")
        self.assertEqual(result, "/api/auth/refresh")

    def test_non_string_forwarded_prefix_in_state_falls_back(self):
        """Non-string forwarded_prefix in request.state (e.g., integer) → falls back to suffix."""
        from app.api.routes.auth import _get_cookie_path

        mock_request = MagicMock(spec=Request)
        mock_request.headers.get.return_value = ""  # No header prefix
        # Use a plain object for state to avoid auto-creation issues
        mock_request.state = type('State', (), {})()
        # Set forwarded_prefix to a non-string type (int)
        mock_request.state.forwarded_prefix = 123
        result = _get_cookie_path(mock_request, "/api/auth/refresh")
        self.assertEqual(result, "/api/auth/refresh")

    def test_forwarded_prefix_from_state_valid_string(self):
        """Valid forwarded_prefix from request.state (string) → uses it as prefix."""
        from app.api.routes.auth import _get_cookie_path

        mock_request = MagicMock(spec=Request)
        mock_request.headers.get.return_value = ""  # No header prefix
        mock_request.state = type('State', (), {})()
        mock_request.state.forwarded_prefix = "/knowledgevault"
        result = _get_cookie_path(mock_request, "/api/auth/refresh")
        self.assertEqual(result, "/knowledgevault/api/auth/refresh")


if __name__ == "__main__":
    unittest.main()
