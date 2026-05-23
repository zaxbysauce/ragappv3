"""
Verification tests for ProxyPrefixMiddleware (task 3.4).

Tests verify:
1. Middleware validates and stores forwarded_prefix in request.state
2. auth.py _get_cookie_path uses request.state first, raw header fallback only if middleware absent
3. security.py issue_csrf_token uses request.state first
4. `..` is rejected by SAFE_PREFIX_RE (path traversal prevention)

NOTE: These tests specifically verify request.state (per-request), NOT app.state (shared).
"""

import re
import unittest
from unittest.mock import MagicMock

from starlette.requests import Request
from starlette.responses import Response

from app.security import SAFE_PREFIX_RE


class TestSAFE_PREFIX_RejectsPathTraversal(unittest.TestCase):
    """Verify `..` is rejected by SAFE_PREFIX_RE (requirement 4)."""

    def test_double_dot_rejected(self):
        """`..` path traversal must be rejected."""
        result = SAFE_PREFIX_RE.match("/../etc/passwd")
        self.assertIsNone(result)

    def test_double_dot_in_middle_rejected(self):
        """/foo/bar/../baz must be rejected."""
        result = SAFE_PREFIX_RE.match("/foo/bar/../baz")
        self.assertIsNone(result)

    def test_double_dot_at_start_rejected(self):
        """/../foo must be rejected."""
        result = SAFE_PREFIX_RE.match("/../foo")
        self.assertIsNone(result)

    def test_double_dot_with_special_chars_rejected(self):
        """/foo/../bar must be rejected."""
        result = SAFE_PREFIX_RE.match("/foo/../bar")
        self.assertIsNone(result)

    def test_valid_prefix_no_double_dot_passes(self):
        """Valid prefixes without `..` should pass."""
        valid_prefixes = [
            "/",
            "/api",
            "/knowledgevault",
            "/a/b/c",
            "/foo.bar",
            "/foo_bar",
            "/foo-bar",
            "/a1",
        ]
        for prefix in valid_prefixes:
            self.assertIsNotNone(
                SAFE_PREFIX_RE.match(prefix),
                f"Prefix '{prefix}' should be accepted",
            )


class TestProxyPrefixMiddlewareValidation(unittest.TestCase):
    """Test ProxyPrefixMiddleware validates and stores in request.state (requirement 1)."""

    def _make_mock_request(self, x_forwarded_prefix: str | None = None) -> MagicMock:
        """Create a mock request with x-forwarded-prefix header."""
        mock_request = MagicMock(spec=Request)
        mock_request.headers.get.return_value = x_forwarded_prefix
        return mock_request

    def test_middleware_stores_valid_prefix_in_request_state(self):
        """Valid prefix should be stored in request.state.forwarded_prefix."""
        from app.middleware.proxy_prefix import ProxyPrefixMiddleware

        middleware = ProxyPrefixMiddleware(app=MagicMock())
        mock_request = self._make_mock_request("/knowledgevault")

        captured_state = {}

        async def mock_call_next(request):
            captured_state["forwarded_prefix"] = request.state.forwarded_prefix
            return Response("ok")

        # Run middleware dispatch
        import asyncio
        asyncio.get_event_loop().run_until_complete(
            middleware.dispatch(mock_request, mock_call_next)
        )

        self.assertEqual(captured_state["forwarded_prefix"], "/knowledgevault")

    def test_middleware_stores_empty_string_for_invalid_prefix(self):
        """Invalid prefix should result in empty string in request.state.forwarded_prefix."""
        from app.middleware.proxy_prefix import ProxyPrefixMiddleware

        middleware = ProxyPrefixMiddleware(app=MagicMock())
        mock_request = self._make_mock_request("/knowledge;vault")

        captured_state = {}

        async def mock_call_next(request):
            captured_state["forwarded_prefix"] = request.state.forwarded_prefix
            return Response("ok")

        import asyncio
        asyncio.get_event_loop().run_until_complete(
            middleware.dispatch(mock_request, mock_call_next)
        )

        self.assertEqual(captured_state["forwarded_prefix"], "")

    def test_middleware_stores_empty_string_for_double_dot(self):
        """/../etc/passwd should be rejected and result in empty string."""
        from app.middleware.proxy_prefix import ProxyPrefixMiddleware

        middleware = ProxyPrefixMiddleware(app=MagicMock())
        mock_request = self._make_mock_request("/../etc/passwd")

        captured_state = {}

        async def mock_call_next(request):
            captured_state["forwarded_prefix"] = request.state.forwarded_prefix
            return Response("ok")

        import asyncio
        asyncio.get_event_loop().run_until_complete(
            middleware.dispatch(mock_request, mock_call_next)
        )

        self.assertEqual(captured_state["forwarded_prefix"], "")

    def test_middleware_stores_empty_string_when_no_header(self):
        """No x-forwarded-prefix header should result in empty string."""
        from app.middleware.proxy_prefix import ProxyPrefixMiddleware

        middleware = ProxyPrefixMiddleware(app=MagicMock())
        mock_request = self._make_mock_request(None)

        captured_state = {}

        async def mock_call_next(request):
            captured_state["forwarded_prefix"] = request.state.forwarded_prefix
            return Response("ok")

        import asyncio
        asyncio.get_event_loop().run_until_complete(
            middleware.dispatch(mock_request, mock_call_next)
        )

        self.assertEqual(captured_state["forwarded_prefix"], "")


class TestAuthCookiePathUsesRequestStateFirst(unittest.TestCase):
    """Test auth.py _get_cookie_path uses request.state first (requirement 2).

    The fallback to raw header should ONLY occur when middleware is absent
    (i.e., when request.state doesn't have forwarded_prefix attribute).
    """

    def _call_get_cookie_path(self, mock_request: MagicMock, suffix: str):
        """Helper to call _get_cookie_path."""
        from app.api.routes.auth import _get_cookie_path
        return _get_cookie_path(mock_request, suffix)

    def _make_request_with_state(self, forwarded_prefix_value: str | None, header_value: str) -> MagicMock:
        """Create mock request with request.state.forwarded_prefix explicitly set or deleted."""
        mock_request = MagicMock(spec=Request)
        mock_request.headers.get.return_value = header_value
        if forwarded_prefix_value is not None:
            # Middleware ran and set the value
            mock_request.state.forwarded_prefix = forwarded_prefix_value
        else:
            # Middleware absent - delete the attribute so hasattr returns False
            del mock_request.state.forwarded_prefix
        return mock_request

    def test_request_state_takes_priority_over_header(self):
        """"When request.state.forwarded_prefix exists, it must be used even if header has different value."""
        mock_request = self._make_request_with_state("/state-prefix", "/header-prefix")

        result = self._call_get_cookie_path(mock_request, "/api/auth/refresh")

        # Should use request.state, NOT header
        self.assertEqual(result, "/state-prefix/api/auth/refresh")

    def test_fallback_to_header_when_middleware_absent(self):
        """When middleware absent (no forwarded_prefix in request.state), fall back to raw header."""
        mock_request = self._make_request_with_state(None, "/valid-header")

        result = self._call_get_cookie_path(mock_request, "/api/auth/refresh")

        # Should use header value since middleware didn't run
        self.assertEqual(result, "/valid-header/api/auth/refresh")

    def test_fallback_validates_raw_header(self):
        """Raw header fallback should still be validated against SAFE_PREFIX_RE."""
        mock_request = self._make_request_with_state(None, "/valid-header")

        result = self._call_get_cookie_path(mock_request, "/api/auth/refresh")

        self.assertEqual(result, "/valid-header/api/auth/refresh")

    def test_fallback_rejects_invalid_raw_header(self):
        """Raw header fallback should reject invalid prefixes (e.g., with semicolon)."""
        mock_request = self._make_request_with_state(None, "/invalid;header")

        result = self._call_get_cookie_path(mock_request, "/api/auth/refresh")

        # Should fall back to suffix only since header is invalid
        self.assertEqual(result, "/api/auth/refresh")


class TestSecurityIssueCsrfTokenUsesRequestStateFirst(unittest.TestCase):
    """Test security.py issue_csrf_token uses request.state first (requirement 3).

    The fallback to raw header should ONLY occur when middleware is absent.

    NOTE: We cannot use spec=Request because Starlette Request is falsy when empty,
    which would cause the outer `if request:` check to fail.
    """

    def _make_request_with_state(self, forwarded_prefix_value: str | None, header_value: str) -> MagicMock:
        """Create mock request with request.state.forwarded_prefix explicitly set or deleted."""
        # Don't use spec=Request because it makes the mock falsy
        mock_request = MagicMock()
        mock_request.headers.get.return_value = header_value
        if forwarded_prefix_value is not None:
            # Middleware ran and set the value
            mock_request.state.forwarded_prefix = forwarded_prefix_value
        else:
            # Middleware absent - delete the attribute so hasattr returns False
            del mock_request.state.forwarded_prefix
        return mock_request

    def test_request_state_takes_priority(self):
        """When request.state.forwarded_prefix exists, it must be used for CSRF cookie path."""
        mock_request = self._make_request_with_state("/state-prefix", "/header-prefix")
        mock_response = MagicMock()

        from app.security import issue_csrf_token, CSRFManager
        mock_manager = MagicMock(spec=CSRFManager)
        mock_manager.generate_token.return_value = "test-token"

        issue_csrf_token(mock_response, mock_manager, mock_request)

        # Check the path used in set_cookie call
        call_kwargs = mock_response.set_cookie.call_args
        # set_cookie is called with (key, value, **kwargs)
        self.assertEqual(call_kwargs[1]["path"], "/state-prefix/api")

    def test_fallback_to_header_when_middleware_absent(self):
        """When middleware absent (no forwarded_prefix in request.state), fall back to raw header."""
        mock_request = self._make_request_with_state(None, "/header-prefix")
        mock_response = MagicMock()

        from app.security import issue_csrf_token, CSRFManager
        mock_manager = MagicMock(spec=CSRFManager)
        mock_manager.generate_token.return_value = "test-token"

        issue_csrf_token(mock_response, mock_manager, mock_request)

        # Check the path used in set_cookie call
        call_kwargs = mock_response.set_cookie.call_args
        self.assertEqual(call_kwargs[1]["path"], "/header-prefix/api")

    def test_no_prefix_returns_api_path(self):
        """No prefix should result in path=/api."""
        mock_request = self._make_request_with_state(None, "")
        mock_response = MagicMock()

        from app.security import issue_csrf_token, CSRFManager
        mock_manager = MagicMock(spec=CSRFManager)
        mock_manager.generate_token.return_value = "test-token"

        issue_csrf_token(mock_response, mock_manager, mock_request)

        call_kwargs = mock_response.set_cookie.call_args
        self.assertEqual(call_kwargs[1]["path"], "/api")


if __name__ == "__main__":
    unittest.main()
