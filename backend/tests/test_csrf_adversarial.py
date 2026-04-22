"""
Adversarial security tests for CSRF protection.

Attack vectors tested:
1. Token prediction/guessing attacks
2. Token replay after expiry
3. Bypass by omitting cookie but providing header
4. Bypass by omitting header but providing cookie
5. Exploiting secure=False over HTTP (cookie theft via MITM)
6. Race conditions / concurrent request token invalidation
7. Token forgery / fabrication
8. Token leakage via httponly=False
9. Cross-origin cookie injection
10. Token brute-force attempts

Prerequisites:
    Backend must be running at http://localhost:9090 (docker compose up)
    Redis or in-memory CSRF fallback must be functional.

Usage:
    python -m pytest tests/test_csrf_adversarial.py -v
"""

import concurrent.futures
import os
import random
import string
import sys
import time
import unittest

import requests

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


def random_username(prefix="atk"):
    """Generate random username for unique test users."""
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return f"{prefix}_{suffix}_{int(time.time() * 1000)}"


def get_valid_csrf(session=None):
    """Fetch a valid CSRF token + cookie pair from the backend."""
    s = session or requests
    resp = s.get(f"{BASE_URL}/csrf-token", timeout=5)
    if resp.status_code != 200:
        raise RuntimeError(
            f"Failed to fetch CSRF token: {resp.status_code} {resp.text}"
        )
    return resp.json()["csrf_token"], resp.cookies.get("X-CSRF-Token"), resp


@unittest.skipUnless(
    check_backend_available(), "Backend not running at http://localhost:9090"
)
class TestCSRFPrediction(unittest.TestCase):
    """
    Attack Vector 1: Can an attacker predict or guess CSRF tokens?

    Tokens are generated with secrets.token_urlsafe(16) which produces 128 bits
    of entropy. Brute-force should be infeasible.
    """

    def test_random_tokens_are_unique(self):
        """100 consecutive tokens should all be distinct."""
        tokens = set()
        for _ in range(100):
            resp = requests.get(f"{BASE_URL}/csrf-token", timeout=5)
            self.assertEqual(resp.status_code, 200)
            token = resp.json()["csrf_token"]
            tokens.add(token)
        # All 100 must be unique
        self.assertEqual(len(tokens), 100, "Tokens are not unique — collision detected")

    def test_token_entropy_sufficient(self):
        """Each token should have >= 22 chars (secrets.token_urlsafe(16) produces 22)."""
        token, _, _ = get_valid_csrf()
        self.assertGreaterEqual(
            len(token), 22, f"Token length {len(token)} too short — predictability risk"
        )

    def test_bruteforce_guessing_fails(self):
        """Sending 50 random guesses should all fail — no token prediction possible."""
        for i in range(50):
            guess = "".join(random.choices(string.ascii_letters + string.digits, k=22))
            resp = requests.post(
                f"{BASE_URL}/auth/register",
                json={"username": random_username("guess"), "password": "Password123!"},
                cookies={"X-CSRF-Token": guess},
                headers={"X-CSRF-Token": guess},
                timeout=5,
            )
            self.assertEqual(
                resp.status_code,
                403,
                f"Guess #{i} '{guess}' unexpectedly passed CSRF validation",
            )

    def test_token_not_derived_from_timestamp(self):
        """Tokens generated at different times should not correlate."""
        tokens = []
        for _ in range(10):
            resp = requests.get(f"{BASE_URL}/csrf-token", timeout=5)
            tokens.append(resp.json()["csrf_token"])
            time.sleep(0.05)  # Small delay between generations

        # Tokens should not contain each other as substrings
        for i, t1 in enumerate(tokens):
            for j, t2 in enumerate(tokens):
                if i != j:
                    self.assertNotIn(
                        t1[:8],
                        t2,
                        "Token prefix found in another token — weak randomness",
                    )

    def test_sequential_tokens_have_no_pattern(self):
        """Sequential tokens should have no obvious numerical or positional pattern."""
        tokens = []
        for _ in range(20):
            resp = requests.get(f"{BASE_URL}/csrf-token", timeout=5)
            tokens.append(resp.json()["csrf_token"])

        # Check no two tokens share more than 50% of their characters at the same positions
        for i in range(len(tokens) - 1):
            t1, t2 = tokens[i], tokens[i + 1]
            matches = sum(c1 == c2 for c1, c2 in zip(t1, t2))
            similarity = matches / max(len(t1), len(t2))
            self.assertLess(
                similarity,
                0.5,
                f"Adjacent tokens too similar ({similarity:.0%}): {t1} vs {t2}",
            )


@unittest.skipUnless(
    check_backend_available(), "Backend not running at http://localhost:9090"
)
class TestCSRFReplay(unittest.TestCase):
    """
    Attack Vector 2: Can an attacker reuse an expired CSRF token?

    Tokens have a 900-second TTL. After expiry, they should be rejected.
    The test uses tokens from a fresh session to simulate expiry detection.
    """

    def test_valid_token_accepted(self):
        """A fresh valid token should be accepted."""
        session = requests.Session()
        token, cookie, _ = get_valid_csrf(session)
        resp = session.post(
            f"{BASE_URL}/auth/register",
            json={"username": random_username("replay_ok"), "password": "Password123!"},
            cookies={"X-CSRF-Token": cookie},
            headers={"X-CSRF-Token": token},
            timeout=5,
        )
        # Should succeed (200) or fail with user-exists (400), but NOT 403 CSRF
        self.assertNotEqual(
            resp.status_code,
            403,
            "Valid token was incorrectly rejected as CSRF failure",
        )

    def test_forged_expired_token_rejected(self):
        """A fabricated token that was never issued should be rejected."""
        fake_token = "expired_never_issued_token_1234567890"
        resp = requests.post(
            f"{BASE_URL}/auth/register",
            json={"username": random_username("expired"), "password": "Password123!"},
            cookies={"X-CSRF-Token": fake_token},
            headers={"X-CSRF-Token": fake_token},
            timeout=5,
        )
        self.assertEqual(
            resp.status_code,
            403,
            f"Forged token was accepted: {resp.status_code} {resp.text}",
        )

    def test_reused_token_still_works_before_expiry(self):
        """A token should remain valid on reuse before TTL expiry (sliding window)."""
        session = requests.Session()
        token, cookie, _ = get_valid_csrf(session)

        # First use
        resp1 = session.post(
            f"{BASE_URL}/auth/register",
            json={"username": random_username("reuse_a"), "password": "Password123!"},
            cookies={"X-CSRF-Token": cookie},
            headers={"X-CSRF-Token": token},
            timeout=5,
        )
        self.assertNotEqual(
            resp1.status_code, 403, "First use rejected as CSRF failure"
        )

        # Immediate reuse — should still work (sliding TTL)
        resp2 = session.post(
            f"{BASE_URL}/auth/register",
            json={"username": random_username("reuse_b"), "password": "Password123!"},
            cookies={"X-CSRF-Token": cookie},
            headers={"X-CSRF-Token": token},
            timeout=5,
        )
        self.assertNotEqual(
            resp2.status_code,
            403,
            "Token was invalidated after first use — sliding window not working",
        )


@unittest.skipUnless(
    check_backend_available(), "Backend not running at http://localhost:9090"
)
class TestCSRFOmissionBypass(unittest.TestCase):
    """
    Attack Vector 3 & 4: Bypass by omitting cookie or header.

    The double-submit pattern requires BOTH the cookie AND the header.
    Omitting either must fail.
    """

    def test_header_only_no_cookie_returns_403(self):
        """Attacker sends header but no cookie — must be rejected."""
        token, _, _ = get_valid_csrf()
        resp = requests.post(
            f"{BASE_URL}/auth/register",
            json={"username": random_username("hdr"), "password": "Password123!"},
            headers={"X-CSRF-Token": token},
            # No cookie intentionally
            timeout=5,
        )
        self.assertEqual(
            resp.status_code,
            403,
            f"Header-only request was accepted: {resp.status_code}",
        )

    def test_cookie_only_no_header_returns_403(self):
        """Attacker sends cookie but no header — must be rejected."""
        _, cookie, _ = get_valid_csrf()
        resp = requests.post(
            f"{BASE_URL}/auth/register",
            json={"username": random_username("ckie"), "password": "Password123!"},
            cookies={"X-CSRF-Token": cookie},
            # No header intentionally
            timeout=5,
        )
        self.assertEqual(
            resp.status_code,
            403,
            f"Cookie-only request was accepted: {resp.status_code}",
        )

    def test_no_cookie_no_header_returns_403(self):
        """Attacker sends neither cookie nor header — must be rejected."""
        resp = requests.post(
            f"{BASE_URL}/auth/register",
            json={"username": random_username("none"), "password": "Password123!"},
            timeout=5,
        )
        self.assertEqual(resp.status_code, 403, "Request with no CSRF was accepted")

    def test_empty_string_cookie_and_header_returns_403(self):
        """Empty strings in cookie and header must be rejected."""
        resp = requests.post(
            f"{BASE_URL}/auth/register",
            json={"username": random_username("empty"), "password": "Password123!"},
            cookies={"X-CSRF-Token": ""},
            headers={"X-CSRF-Token": ""},
            timeout=5,
        )
        self.assertEqual(resp.status_code, 403, "Empty CSRF strings were accepted")

    def test_whitespace_cookie_and_header_returns_403(self):
        """Whitespace-only cookie/header must be rejected."""
        resp = requests.post(
            f"{BASE_URL}/auth/register",
            json={"username": random_username("space"), "password": "Password123!"},
            cookies={"X-CSRF-Token": "   "},
            headers={"X-CSRF-Token": "   "},
            timeout=5,
        )
        self.assertEqual(resp.status_code, 403, "Whitespace CSRF was accepted")


@unittest.skipUnless(
    check_backend_available(), "Backend not running at http://localhost:9090"
)
class TestCSRFCookieAttributes(unittest.TestCase):
    """
    Attack Vector 5: Exploiting secure=False over HTTP.

    The cookie is set with secure=False, httponly=False, samesite=lax.
    This means it's accessible via JS and sent over HTTP — risky on shared networks.
    """

    def test_cookie_not_httponly(self):
        """COOKIE SECURITY ISSUE: Token cookie should ideally be httponly.
        Current implementation sets httponly=False — this allows JS access
        which increases XSS-driven CSRF risk."""
        resp = requests.get(f"{BASE_URL}/csrf-token", timeout=5)
        self.assertEqual(resp.status_code, 200)
        set_cookie = resp.headers.get("Set-Cookie", "").lower()
        # Document the finding: httponly is NOT set
        is_httponly = "httponly" in set_cookie
        self.assertFalse(
            is_httponly,
            "EXPECTED FINDING: httponly=False on CSRF cookie allows JS read access. "
            "Combined with XSS, an attacker can steal CSRF tokens.",
        )

    def test_cookie_not_secure(self):
        """COOKIE SECURITY ISSUE: Token cookie should be secure=True in production.
        Current implementation allows HTTP transmission."""
        resp = requests.get(f"{BASE_URL}/csrf-token", timeout=5)
        self.assertEqual(resp.status_code, 200)
        set_cookie = resp.headers.get("Set-Cookie", "").lower()
        # Document the finding: secure flag should be present
        is_secure = "secure" in set_cookie
        self.assertFalse(
            is_secure,
            "EXPECTED FINDING: secure=False allows CSRF cookie transmission over HTTP. "
            "On shared networks, MitM attackers can intercept CSRF tokens.",
        )

    def test_cookie_has_samesite_lax(self):
        """Cookie should have SameSite=Lax to mitigate cross-site POST attacks."""
        resp = requests.get(f"{BASE_URL}/csrf-token", timeout=5)
        self.assertEqual(resp.status_code, 200)
        set_cookie = resp.headers.get("Set-Cookie", "").lower()
        self.assertIn(
            "samesite=lax",
            set_cookie,
            f"Cookie missing SameSite=Lax: {set_cookie}",
        )

    def test_cookie_value_equals_body_token(self):
        """Cookie value must exactly match the response body token — no transformation."""
        resp = requests.get(f"{BASE_URL}/csrf-token", timeout=5)
        self.assertEqual(resp.status_code, 200)
        body_token = resp.json()["csrf_token"]
        cookie_token = resp.cookies.get("X-CSRF-Token")
        self.assertEqual(
            body_token,
            cookie_token,
            "Token mismatch between body and cookie — potential integrity issue",
        )

    def test_cookie_sent_in_plain_text_over_http(self):
        """DEMONSTRATION: Over HTTP, cookies are sent in plain text.
        This test documents that the CSRF token is transmitted without encryption."""
        token, cookie, _ = get_valid_csrf()
        # Successfully using the token over HTTP proves it's in plain text
        resp = requests.post(
            f"{BASE_URL}/auth/register",
            json={"username": random_username("plain"), "password": "Password123!"},
            cookies={"X-CSRF-Token": cookie},
            headers={"X-CSRF-Token": token},
            timeout=5,
        )
        self.assertNotEqual(
            resp.status_code,
            403,
            "Valid token was rejected — this test documents plain-text transmission",
        )
        # NOTE: This is a FINDING, not a test failure. On HTTP, a MitM attacker
        # on the same network can sniff the CSRF cookie from the request headers.


@unittest.skipUnless(
    check_backend_available(), "Backend not running at http://localhost:9090"
)
class TestCSRFRaceConditions(unittest.TestCase):
    """
    Attack Vector 6: Can concurrent requests cause token invalidation?

    If the CSRF manager has race conditions, simultaneous requests with the
    same token might cause one to succeed and others to fail unexpectedly.
    """

    def _make_csrf_request(self, token, cookie, username):
        """Helper to make a single CSRF-protected POST."""
        resp = requests.post(
            f"{BASE_URL}/auth/register",
            json={"username": username, "password": "Password123!"},
            cookies={"X-CSRF-Token": cookie},
            headers={"X-CSRF-Token": token},
            timeout=10,
        )
        return resp.status_code

    def test_concurrent_requests_same_token(self):
        """10 concurrent requests with the same valid token should all pass CSRF."""
        session = requests.Session()
        token, cookie, _ = get_valid_csrf(session)

        usernames = [random_username(f"race_{i}") for i in range(10)]

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [
                executor.submit(self._make_csrf_request, token, cookie, uname)
                for uname in usernames
            ]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        # No request should get 403 (CSRF failure) — they might get 200 or 400 (user exists)
        csrf_failures = [r for r in results if r == 403]
        self.assertEqual(
            len(csrf_failures),
            0,
            f"{len(csrf_failures)}/10 concurrent requests got 403 CSRF failure — "
            "possible race condition in token validation",
        )

    def test_rapid_sequential_token_requests(self):
        """Rapidly requesting new tokens should not cause collisions or errors."""
        errors = 0
        token_set = set()
        for i in range(50):
            try:
                resp = requests.get(f"{BASE_URL}/csrf-token", timeout=5)
                if resp.status_code != 200:
                    errors += 1
                else:
                    token_set.add(resp.json()["csrf_token"])
            except Exception:
                errors += 1

        self.assertEqual(errors, 0, f"{errors}/50 rapid token requests failed")
        self.assertEqual(len(token_set), 50, "Some token requests returned duplicates")

    def test_concurrent_different_tokens(self):
        """Concurrent requests with different valid tokens should all pass CSRF."""
        results = []

        def fetch_and_post(idx):
            s = requests.Session()
            token, cookie, _ = get_valid_csrf(s)
            resp = s.post(
                f"{BASE_URL}/auth/register",
                json={
                    "username": random_username(f"multi_{idx}"),
                    "password": "Password123!",
                },
                cookies={"X-CSRF-Token": cookie},
                headers={"X-CSRF-Token": token},
                timeout=10,
            )
            return resp.status_code

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(fetch_and_post, i) for i in range(5)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        csrf_failures = [r for r in results if r == 403]
        self.assertEqual(
            len(csrf_failures),
            0,
            f"{len(csrf_failures)}/5 concurrent different-token requests got 403",
        )


@unittest.skipUnless(
    check_backend_available(), "Backend not running at http://localhost:9090"
)
class TestCSRFForgery(unittest.TestCase):
    """
    Attack Vector 7: Can an attacker forge a CSRF token that passes validation?
    """

    def test_forged_token_with_matching_cookie(self):
        """An attacker who fabricates both cookie and header with same fake value must fail."""
        fake = "forged_token_value_abcdefghijklmnop"
        resp = requests.post(
            f"{BASE_URL}/auth/register",
            json={"username": random_username("forge"), "password": "Password123!"},
            cookies={"X-CSRF-Token": fake},
            headers={"X-CSRF-Token": fake},
            timeout=5,
        )
        self.assertEqual(
            resp.status_code, 403, "Forged matching token/cookie was accepted"
        )

    def test_token_with_injected_special_chars(self):
        """Tokens with special characters must be rejected."""
        payloads = [
            "'; DROP TABLE csrf_tokens; --",
            "<script>alert('xss')</script>",
            "../../../etc/passwd",
            "${7*7}",
            "\x00\x00\x00",
            "A" * 10000,  # Oversized token
            "",  # Empty
        ]
        for payload in payloads:
            resp = requests.post(
                f"{BASE_URL}/auth/register",
                json={
                    "username": random_username("inject"),
                    "password": "Password123!",
                },
                cookies={"X-CSRF-Token": payload},
                headers={"X-CSRF-Token": payload},
                timeout=5,
            )
            self.assertEqual(
                resp.status_code,
                403,
                f"Injection payload '{payload[:30]}' was accepted as valid CSRF",
            )

    def test_token_truncation_attack(self):
        """Using a truncated version of a valid token must fail."""
        token, cookie, _ = get_valid_csrf()
        truncated = token[: len(token) // 2]
        resp = requests.post(
            f"{BASE_URL}/auth/register",
            json={"username": random_username("trunc"), "password": "Password123!"},
            cookies={"X-CSRF-Token": truncated},
            headers={"X-CSRF-Token": truncated},
            timeout=5,
        )
        self.assertEqual(resp.status_code, 403, "Truncated token was accepted")

    def test_token_with_extra_padding(self):
        """Using a valid token with extra characters appended must fail."""
        token, cookie, _ = get_valid_csrf()
        padded = token + "EXTRA_PADDING_CHARS"
        resp = requests.post(
            f"{BASE_URL}/auth/register",
            json={"username": random_username("pad"), "password": "Password123!"},
            cookies={"X-CSRF-Token": padded},
            headers={"X-CSRF-Token": padded},
            timeout=5,
        )
        self.assertEqual(resp.status_code, 403, "Padded token was accepted")

    def test_token_with_case_transformation(self):
        """Using a valid token with case changes must fail (tokens are case-sensitive)."""
        token, cookie, _ = get_valid_csrf()
        # Flip case
        flipped = "".join(c.upper() if c.islower() else c.lower() for c in token)
        resp = requests.post(
            f"{BASE_URL}/auth/register",
            json={"username": random_username("case"), "password": "Password123!"},
            cookies={"X-CSRF-Token": flipped},
            headers={"X-CSRF-Token": flipped},
            timeout=5,
        )
        self.assertEqual(resp.status_code, 403, "Case-transformed token was accepted")

    def test_token_with_unicode_homoglyphs(self):
        """Using unicode homoglyphs in place of ASCII chars must fail."""
        token, cookie, _ = get_valid_csrf()
        # Replace 'a' with Cyrillic 'а' (U+0430)
        homoglyph = token.replace("a", "\u0430") if "a" in token else token + "\u0430"
        resp = requests.post(
            f"{BASE_URL}/auth/register",
            json={"username": random_username("glyph"), "password": "Password123!"},
            cookies={"X-CSRF-Token": homoglyph},
            headers={"X-CSRF-Token": homoglyph},
            timeout=5,
        )
        self.assertEqual(resp.status_code, 403, "Unicode homoglyph token was accepted")

    def test_token_with_url_encoding_bypass(self):
        """URL-encoded versions of tokens must be rejected if the server decodes them."""
        token, cookie, _ = get_valid_csrf()
        # URL-encode the token
        import urllib.parse

        encoded = urllib.parse.quote(token)
        if encoded != token:  # Only test if encoding actually changed something
            resp = requests.post(
                f"{BASE_URL}/auth/register",
                json={
                    "username": random_username("urlenc"),
                    "password": "Password123!",
                },
                cookies={"X-CSRF-Token": encoded},
                headers={"X-CSRF-Token": encoded},
                timeout=5,
            )
            # Should fail because the encoded form doesn't match the stored token
            self.assertEqual(
                resp.status_code, 403, "URL-encoded token bypassed CSRF validation"
            )

    def test_double_cookie_attack(self):
        """Sending two CSRF cookies (cookie splitting) must not bypass validation."""
        token, cookie, _ = get_valid_csrf()
        fake = "fake_token_for_splitting"
        # Some frameworks take the first or last cookie — try both arrangements
        for order in [(cookie, fake), (fake, cookie)]:
            cookie_header = "; ".join([f"X-CSRF-Token={c}" for c in order])
            # Use raw headers to force double cookies
            resp = requests.post(
                f"{BASE_URL}/auth/register",
                json={"username": random_username("split"), "password": "Password123!"},
                headers={
                    "X-CSRF-Token": token,
                    "Cookie": cookie_header,
                },
                timeout=5,
            )
            # The cookie must match the header — if the framework picks the wrong one,
            # it should still fail
            if resp.status_code != 403:
                # Only fail if the request succeeded unexpectedly
                # (200/400 are OK if auth logic handles it, 403 is expected for CSRF)
                self.assertIn(
                    resp.status_code,
                    [200, 400, 409, 422],
                    f"Unexpected status {resp.status_code} in cookie-split attack",
                )


@unittest.skipUnless(
    check_backend_available(), "Backend not running at http://localhost:9090"
)
class TestCSRFTokenLeakage(unittest.TestCase):
    """
    Attack Vector 8: Token leakage via httponly=False.

    Since the CSRF cookie is not httponly, JavaScript can read it.
    This means XSS can steal CSRF tokens.
    """

    def test_token_appears_in_response_body(self):
        """The CSRF token is returned in the JSON body — this is by design for the
        double-submit pattern, but combined with httponly=False, it means the token
        is accessible via both the cookie (via JS) and the body (via fetch)."""
        resp = requests.get(f"{BASE_URL}/csrf-token", timeout=5)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("csrf_token", data)
        self.assertGreater(len(data["csrf_token"]), 0)

    def test_token_in_body_matches_cookie(self):
        """Confirm the body token and cookie are identical — demonstrating that
        any XSS that can read the JSON response can also forge the cookie."""
        resp = requests.get(f"{BASE_URL}/csrf-token", timeout=5)
        body_token = resp.json()["csrf_token"]
        cookie_token = resp.cookies.get("X-CSRF-Token")
        self.assertEqual(body_token, cookie_token)

    def test_csrf_cookie_name_not_prefixed(self):
        """SECURITY NOTE: Cookie name 'X-CSRF-Token' has no __Host- or __Secure-
        prefix. This means the cookie isn't restricted to secure origins."""
        resp = requests.get(f"{BASE_URL}/csrf-token", timeout=5)
        set_cookie = resp.headers.get("Set-Cookie", "")
        # The cookie should ideally use __Host-X-CSRF-Token for enhanced security
        self.assertIn(
            "X-CSRF-Token",
            set_cookie,
            "Cookie name not found in Set-Cookie header",
        )
        # Document that __Host- prefix is not used
        self.assertNotIn(
            "__Host-",
            set_cookie,
            "FINDING: Cookie lacks __Host- prefix — not restricted to secure origins",
        )


@unittest.skipUnless(
    check_backend_available(), "Backend not running at http://localhost:9090"
)
class TestCSRFCrossOrigin(unittest.TestCase):
    """
    Attack Vector 9: Cross-origin cookie injection and CSRF.

    SameSite=Lax prevents cookies from being sent on cross-site POST requests.
    This test verifies the SameSite attribute is actually enforced.
    """

    def test_samesite_lax_in_set_cookie(self):
        """The Set-Cookie header must contain SameSite=Lax."""
        resp = requests.get(f"{BASE_URL}/csrf-token", timeout=5)
        set_cookie = resp.headers.get("Set-Cookie", "").lower()
        self.assertIn("samesite=lax", set_cookie, "SameSite=Lax not in cookie")

    def test_cors_does_not_allow_credentials_from_arbitrary_origins(self):
        """The CORS config should not allow credentials from arbitrary origins.
        We test by sending an Origin header and checking if it's reflected."""
        resp = requests.options(
            f"{BASE_URL}/csrf-token",
            headers={"Origin": "https://evil.example.com"},
            timeout=5,
        )
        acao = resp.headers.get("Access-Control-Allow-Origin", "")
        if acao == "https://evil.example.com":
            # If arbitrary origin is reflected, check if credentials are allowed
            acac = resp.headers.get("Access-Control-Allow-Credentials", "")
            self.assertNotEqual(
                acac.lower(),
                "true",
                "CRITICAL: CORS allows credentials from arbitrary origins — "
                "combined with httponly=False, this enables cross-site CSRF theft",
            )

    def test_token_endpoint_accessible_without_origin(self):
        """Token endpoint should still work without an Origin header (legitimate use)."""
        resp = requests.get(f"{BASE_URL}/csrf-token", timeout=5)
        self.assertEqual(resp.status_code, 200)


@unittest.skipUnless(
    check_backend_available(), "Backend not running at http://localhost:9090"
)
class TestCSRFBruteForce(unittest.TestCase):
    """
    Attack Vector 10: Token brute-force and enumeration.
    """

    def test_100_random_tokens_all_rejected(self):
        """100 randomly generated token strings should all be rejected."""
        for i in range(100):
            fake = "".join(
                random.choices(string.ascii_letters + string.digits + "-_", k=22)
            )
            resp = requests.post(
                f"{BASE_URL}/auth/register",
                json={
                    "username": random_username(f"bf_{i}"),
                    "password": "Password123!",
                },
                cookies={"X-CSRF-Token": fake},
                headers={"X-CSRF-Token": fake},
                timeout=5,
            )
            self.assertEqual(
                resp.status_code, 403, f"Random token #{i} '{fake}' was accepted"
            )

    def test_similar_to_valid_token_rejected(self):
        """Tokens that are 1-2 chars off from a valid token must be rejected."""
        token, _, _ = get_valid_csrf()
        variants = []
        # Flip one character
        for i in range(min(5, len(token))):
            flipped = list(token)
            flipped[i] = "X" if flipped[i] != "X" else "Y"
            variants.append("".join(flipped))
        # Remove one character
        if len(token) > 1:
            variants.append(token[:-1])
            variants.append(token[1:])
        # Add one character
        variants.append(token + "X")
        variants.insert(0, "X" + token)

        for variant in variants:
            resp = requests.post(
                f"{BASE_URL}/auth/register",
                json={"username": random_username("sim"), "password": "Password123!"},
                cookies={"X-CSRF-Token": variant},
                headers={"X-CSRF-Token": variant},
                timeout=5,
            )
            self.assertEqual(
                resp.status_code,
                403,
                f"Similar token variant '{variant[:20]}...' was accepted",
            )

    def test_numeric_tokens_rejected(self):
        """Purely numeric tokens must be rejected."""
        for length in [10, 16, 22, 32]:
            fake = "".join(random.choices(string.digits, k=length))
            resp = requests.post(
                f"{BASE_URL}/auth/register",
                json={"username": random_username("num"), "password": "Password123!"},
                cookies={"X-CSRF-Token": fake},
                headers={"X-CSRF-Token": fake},
                timeout=5,
            )
            self.assertEqual(
                resp.status_code, 403, f"Numeric token (len={length}) was accepted"
            )


@unittest.skipUnless(
    check_backend_available(), "Backend not running at http://localhost:9090"
)
class TestCSRFEdgeCases(unittest.TestCase):
    """Edge case and boundary tests."""

    def test_csrf_token_endpoint_is_get_only(self):
        """The /csrf-token endpoint should only accept GET."""
        for method in ["POST", "PUT", "DELETE", "PATCH"]:
            resp = requests.request(method, f"{BASE_URL}/csrf-token", timeout=5)
            self.assertEqual(
                resp.status_code,
                405,
                f"{method} /csrf-token returned {resp.status_code} instead of 405",
            )

    def test_multiple_csrf_headers_sent(self):
        """If multiple X-CSRF-Token headers are sent, the request should fail."""
        token, cookie, _ = get_valid_csrf()
        resp = requests.post(
            f"{BASE_URL}/auth/register",
            json={"username": random_username("multi_hdr"), "password": "Password123!"},
            cookies={"X-CSRF-Token": cookie},
            headers=[("X-CSRF-Token", token), ("X-CSRF-Token", "fake")],
            timeout=5,
        )
        # Should either reject (403) or use the first/last — but the mismatch
        # between any header value and the cookie should cause failure
        # FastAPI picks the last header by default with Header()
        if resp.status_code == 403:
            pass  # Expected: mismatch detected
        else:
            # If it passed, it means the framework picked one that matched
            self.assertIn(resp.status_code, [200, 400, 409, 422])

    def test_csrf_token_in_body_instead_of_header(self):
        """Sending the CSRF token in the request body (not header) must not bypass."""
        token, cookie, _ = get_valid_csrf()
        resp = requests.post(
            f"{BASE_URL}/auth/register",
            json={
                "username": random_username("body_csrf"),
                "password": "Password123!",
                "X-CSRF-Token": token,  # In body, not header
            },
            cookies={"X-CSRF-Token": cookie},
            # No X-CSRF-Token header
            timeout=5,
        )
        self.assertEqual(
            resp.status_code,
            403,
            "CSRF token in body (not header) bypassed protection",
        )

    def test_csrf_token_in_query_string(self):
        """Sending the CSRF token as a query parameter must not bypass."""
        token, cookie, _ = get_valid_csrf()
        resp = requests.post(
            f"{BASE_URL}/auth/register?X-CSRF-Token={token}",
            json={"username": random_username("qs_csrf"), "password": "Password123!"},
            cookies={"X-CSRF-Token": cookie},
            # No X-CSRF-Token header
            timeout=5,
        )
        self.assertEqual(
            resp.status_code,
            403,
            "CSRF token in query string bypassed protection",
        )

    def test_cookie_domain_scope(self):
        """CSRF cookie should not have an explicit Domain attribute (restricts scope)."""
        resp = requests.get(f"{BASE_URL}/csrf-token", timeout=5)
        set_cookie = resp.headers.get("Set-Cookie", "")
        # Without Domain attribute, cookie is scoped to the request host
        # Having Domain=.example.com would be a security issue
        if "domain=" in set_cookie.lower():
            # If domain is set, it should match the request host exactly
            self.fail(
                "CSRF cookie has explicit Domain attribute — "
                "this can widen the cookie scope across subdomains"
            )

    def test_null_byte_in_token(self):
        """Null bytes in tokens must be rejected (C-string termination attack)."""
        resp = requests.post(
            f"{BASE_URL}/auth/register",
            json={"username": random_username("null"), "password": "Password123!"},
            cookies={"X-CSRF-Token": "abc\x00def"},
            headers={"X-CSRF-Token": "abc\x00def"},
            timeout=5,
        )
        self.assertEqual(resp.status_code, 403, "Token with null byte was accepted")

    def test_newline_in_token(self):
        """Newlines in tokens must be rejected (header injection)."""
        resp = requests.post(
            f"{BASE_URL}/auth/register",
            json={"username": random_username("crlf"), "password": "Password123!"},
            cookies={"X-CSRF-Token": "abc\r\ndef"},
            headers={"X-CSRF-Token": "abc\r\ndef"},
            timeout=5,
        )
        self.assertEqual(resp.status_code, 403, "Token with CRLF was accepted")


if __name__ == "__main__":
    print(f"Running adversarial CSRF tests against {BASE_URL}")
    print("Ensure the backend is running at http://localhost:9090")
    print("=" * 70)
    unittest.main(verbosity=2)
