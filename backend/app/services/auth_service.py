"""Authentication service with bcrypt and JWT."""

import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

import jwt  # PyJWT
from passlib.context import CryptContext

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)

ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 30
ALGORITHM = "HS256"


def get_jwt_config() -> Tuple[str, str]:
    """Get JWT configuration from settings."""
    from app.config import settings

    secret_key = settings.jwt_secret_key
    if not secret_key or secret_key == "change-me-to-a-random-64-char-string":
        raise RuntimeError("JWT_SECRET_KEY must be set when users are enabled")
    return secret_key, ALGORITHM


def hash_password(plain_password: str) -> str:
    """Hash a password using bcrypt."""
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception:
        return False


def password_strength_check(plain_password: str) -> None:
    """Validate password strength. Raises ValueError with specific message if invalid."""
    if not plain_password:
        raise ValueError("Password cannot be empty")
    if len(plain_password) > 128:
        raise ValueError("Password cannot exceed 128 characters")
    if plain_password != plain_password.strip():
        raise ValueError("Password cannot be only whitespace")
    if len(plain_password) < 8:
        raise ValueError("Password must be at least 8 characters long")
    if not any(char.isdigit() for char in plain_password):
        raise ValueError("Password must contain at least one digit")
    if not any(char.isupper() for char in plain_password):
        raise ValueError("Password must contain at least one uppercase letter")


def create_access_token(user_id: int, username: str, role: str) -> str:
    """Create a JWT access token."""
    secret, algorithm = get_jwt_config()
    expires = datetime.now(timezone.utc) + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "exp": expires,
    }
    return jwt.encode(payload, secret, algorithm=algorithm)


def decode_access_token(token: str) -> Optional[dict]:
    """Decode and validate a JWT access token."""
    try:
        secret, algorithm = get_jwt_config()
        return jwt.decode(token, secret, algorithms=[algorithm])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
    except Exception:
        return None


def create_refresh_token() -> Tuple[str, str]:
    """
    Create a refresh token.
    Returns: (raw_token, sha256_hash)
    Store only the hash in the database.
    """
    raw_token = secrets.token_urlsafe(32)
    sha256_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    return raw_token, sha256_hash


def verify_auth_config() -> None:
    """Verify auth configuration is valid. Call at startup."""
    from app.config import settings

    if settings.users_enabled:
        if not settings.jwt_secret_key or settings.jwt_secret_key in (
            "",
            "change-me-to-a-random-64-char-string",
        ):
            raise RuntimeError(
                "JWT_SECRET_KEY must be set when USERS_ENABLED=True. "
                'Generate one with: python -c "import secrets; print(secrets.token_urlsafe(48))"'
            )
