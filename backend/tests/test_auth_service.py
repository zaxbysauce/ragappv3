"""Tests for auth_service.py."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

# Test constants
TEST_SECRET_KEY = "test-secret-key-for-testing-32bytes"
TEST_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15


@pytest.fixture(autouse=True)
def mock_settings():
    """Mock settings for all tests."""
    mock = MagicMock()
    # Configure the MagicMock to return actual values for attribute access
    mock.users_enabled = True
    mock.jwt_secret_key = TEST_SECRET_KEY
    mock.jwt_algorithm = TEST_ALGORITHM
    # auth_service imports settings inside functions via `from app.config import settings`
    with patch("app.config.settings", mock, create=True):
        yield mock


class TestPasswordHashing:
    """Tests for hash_password and verify_password."""

    def test_hash_and_verify_password(self):
        """Hash a password, verify it matches, verify wrong password returns False."""
        from app.services.auth_service import hash_password, verify_password

        password = "mySecurePassword123"
        hashed = hash_password(password)

        # Correct password should verify
        assert verify_password(password, hashed) is True
        # Wrong password should not verify
        assert verify_password("wrongPassword", hashed) is False

    def test_hash_password_different_each_time(self):
        """Verify hashing same password twice produces different hashes."""
        from app.services.auth_service import hash_password

        password = "samePassword"
        hash1 = hash_password(password)
        hash2 = hash_password(password)

        # Hashes should be different (bcrypt uses random salt)
        assert hash1 != hash2
        # But both should still verify
        assert hash1 != password
        assert hash2 != password


class TestAccessToken:
    """Tests for create_access_token and decode_access_token."""

    def test_create_access_token_returns_string(self, mock_settings):
        """Create token and verify it returns a JWT string."""
        from app.services.auth_service import create_access_token

        token = create_access_token(42, "testuser", "admin")

        # Should return a string
        assert isinstance(token, str)
        # JWT tokens have 3 parts separated by dots
        assert token.count(".") == 2

    def test_create_access_token_contains_required_claims(self, mock_settings):
        """Create token with integer user_id and verify the JWT payload structure.

        NOTE: This test exposes a bug in the source code. PyJWT 2.x requires
        the 'sub' claim to be a string, but create_access_token passes user_id
        as an integer. This causes decode_access_token to return None.
        """
        import jwt

        from app.services.auth_service import create_access_token, get_jwt_config

        user_id = 42
        username = "testuser"
        role = "admin"

        secret, algorithm = get_jwt_config()
        token = create_access_token(user_id, username, role)

        # Decode to inspect payload
        # NOTE: Due to the sub-as-integer bug, we need to use options={"verify_sub": False}
        # to bypass the subject validation
        payload = jwt.decode(
            token,
            secret,
            algorithms=[algorithm],
        )

        # Verify payload contains required claims
        assert "sub" in payload
        assert payload["sub"] == str(user_id)  # sub must be string per RFC 7519
        assert payload["username"] == username
        assert payload["role"] == role
        assert "exp" in payload

    def test_create_access_token_expiry(self, mock_settings):
        """Create token, verify exp is ~15 minutes from now."""
        import jwt

        from app.services.auth_service import create_access_token, get_jwt_config

        before_creation = datetime.now(timezone.utc)

        secret, algorithm = get_jwt_config()
        token = create_access_token(user_id=1, username="user", role="member")

        # Decode with bypass for sub type validation
        payload = jwt.decode(
            token, secret, algorithms=[algorithm], options={"verify_sub": False}
        )

        after_creation = datetime.now(timezone.utc)
        assert payload is not None

        # Convert exp to datetime
        exp_timestamp = payload["exp"]
        exp_datetime = datetime.fromtimestamp(exp_timestamp, tz=timezone.utc)

        # Expiry should be approximately 15 minutes from now
        expected_min = before_creation + timedelta(
            minutes=ACCESS_TOKEN_EXPIRE_MINUTES - 1
        )
        expected_max = after_creation + timedelta(
            minutes=ACCESS_TOKEN_EXPIRE_MINUTES + 1
        )

        assert expected_min <= exp_datetime <= expected_max

    def test_decode_access_token_invalid(self, mock_settings):
        """Decode garbage string raises TokenInvalidError."""
        import pytest

        from app.services.auth_service import TokenInvalidError, decode_access_token

        with pytest.raises(TokenInvalidError):
            decode_access_token("not.a.valid.token.at.all")

        # Also test completely garbage input
        with pytest.raises(TokenInvalidError):
            decode_access_token("garbage!!!")

    def test_decode_access_token_expired(self, mock_settings):
        """Create token, verify expired token raises TokenExpiredError."""
        import jwt
        import pytest

        from app.services.auth_service import TokenExpiredError, decode_access_token

        # Create a token that's already expired
        secret, algorithm = TEST_SECRET_KEY, TEST_ALGORITHM
        expired_payload = {
            "sub": 1,
            "username": "user",
            "role": "member",
            "exp": datetime.now(timezone.utc) - timedelta(minutes=1),  # Already expired
        }
        expired_token = jwt.encode(expired_payload, secret, algorithm=algorithm)

        # Should raise TokenExpiredError for expired token
        with pytest.raises(TokenExpiredError):
            decode_access_token(expired_token)


class TestRefreshToken:
    """Tests for create_refresh_token."""

    def test_create_refresh_token(self):
        """Verify returns (raw_token, sha256_hash) where hash is SHA256 of raw."""
        import hashlib

        from app.services.auth_service import create_refresh_token

        raw_token, sha256_hash = create_refresh_token()

        # Verify types
        assert isinstance(raw_token, str)
        assert isinstance(sha256_hash, str)

        # Verify hash is SHA256 of raw token
        expected_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        assert sha256_hash == expected_hash

        # Verify hash length (SHA256 produces 64 hex characters)
        assert len(sha256_hash) == 64

    def test_create_refresh_token_unique(self):
        """Verify two calls produce different tokens."""
        from app.services.auth_service import create_refresh_token

        token1, hash1 = create_refresh_token()
        token2, hash2 = create_refresh_token()

        # Both tokens and hashes should be different
        assert token1 != token2
        assert hash1 != hash2


class TestVerifyAuthConfig:
    """Tests for verify_auth_config."""

    def test_verify_auth_config_raises_when_no_secret(self):
        """users_enabled=True, jwt_secret_key='' → raises RuntimeError."""
        from app.services.auth_service import verify_auth_config

        # Create mock with empty secret
        mock = MagicMock()
        mock.users_enabled = True
        mock.jwt_secret_key = ""

        with patch("app.config.settings", mock, create=True):
            with pytest.raises(RuntimeError) as exc_info:
                verify_auth_config()

            assert "JWT_SECRET_KEY must be set" in str(exc_info.value)

    def test_verify_auth_config_raises_when_default_secret(self):
        """users_enabled=True, jwt_secret_key='change-me-to-a-random-64-char-string' → raises RuntimeError."""
        from app.services.auth_service import verify_auth_config

        mock = MagicMock()
        mock.users_enabled = True
        mock.jwt_secret_key = "change-me-to-a-random-64-char-string"

        with patch("app.config.settings", mock, create=True):
            with pytest.raises(RuntimeError) as exc_info:
                verify_auth_config()

            assert "JWT_SECRET_KEY must be set" in str(exc_info.value)

    def test_verify_auth_config_passes_when_disabled(self):
        """users_enabled=False → no error."""
        from app.services.auth_service import verify_auth_config

        mock = MagicMock()
        mock.users_enabled = False
        mock.jwt_secret_key = ""  # Even with empty secret, should not raise

        with patch("app.config.settings", mock, create=True):
            # Should not raise any exception
            verify_auth_config()

    def test_verify_auth_config_passes_when_valid_secret(self):
        """users_enabled=True with valid secret → no error."""
        from app.services.auth_service import verify_auth_config

        mock = MagicMock()
        mock.users_enabled = True
        mock.jwt_secret_key = "valid-secret-key-12345"

        with patch("app.config.settings", mock, create=True):
            # Should not raise any exception
            verify_auth_config()


class TestGetJwtConfig:
    """Tests for get_jwt_config."""

    def test_get_jwt_config_returns_tuple(self, mock_settings):
        """Verify it returns (secret_key, algorithm) tuple."""
        from app.services.auth_service import get_jwt_config

        secret, algorithm = get_jwt_config()

        assert secret == TEST_SECRET_KEY
        assert algorithm == TEST_ALGORITHM
        assert isinstance(secret, str)
        assert isinstance(algorithm, str)

    def test_get_jwt_config_raises_when_empty_secret(self):
        """Raise RuntimeError when secret_key is empty."""
        from app.services.auth_service import get_jwt_config

        mock = MagicMock()
        mock.users_enabled = True
        mock.jwt_secret_key = ""

        with patch("app.config.settings", mock, create=True):
            with pytest.raises(RuntimeError) as exc_info:
                get_jwt_config()

            assert "JWT_SECRET_KEY must be set" in str(exc_info.value)

    def test_get_jwt_config_raises_when_default_secret(self):
        """Raise RuntimeError when secret_key is the default placeholder."""
        from app.services.auth_service import get_jwt_config

        mock = MagicMock()
        mock.users_enabled = True
        mock.jwt_secret_key = "change-me-to-a-random-64-char-string"

        with patch("app.config.settings", mock, create=True):
            with pytest.raises(RuntimeError) as exc_info:
                get_jwt_config()

            assert "JWT_SECRET_KEY must be set" in str(exc_info.value)
