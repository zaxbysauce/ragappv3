"""Authentication routes."""

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.api.deps import get_current_active_user, get_db
from app.limiter import limiter
from app.services.auth_service import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_TOKEN_COOKIE_NAME = "refresh_token"
REFRESH_TOKEN_MAX_AGE_DAYS = 30


class RegisterRequest(BaseModel):
    username: str = Field(max_length=255)
    password: str = Field(max_length=128)
    full_name: str = Field(default="", max_length=255)


class LoginRequest(BaseModel):
    username: str = Field(max_length=255)
    password: str = Field(max_length=128)


class UpdateProfileRequest(BaseModel):
    full_name: Optional[str] = Field(default=None, max_length=255)
    password: Optional[str] = Field(default=None, max_length=128)


@limiter.limit("5/hour")
@router.post("/register")
async def register(
    request: Request,
    body: RegisterRequest,
    db=Depends(get_db),
):
    """Register a new user. First user becomes superadmin."""
    if not body.username or len(body.username) < 3:
        raise HTTPException(
            status_code=400, detail="Username must be at least 3 characters"
        )
    if not body.password or len(body.password) < 8:
        raise HTTPException(
            status_code=400, detail="Password must be at least 8 characters"
        )

    # Check username uniqueness (case-insensitive)
    cursor = db.execute(
        "SELECT id FROM users WHERE username = ? COLLATE NOCASE", (body.username,)
    )
    if cursor.fetchone():
        raise HTTPException(status_code=409, detail="Username already exists")

    # First user becomes superadmin
    cursor = db.execute("SELECT COUNT(*) FROM users")
    user_count = cursor.fetchone()[0]
    role = "superadmin" if user_count == 0 else "member"

    hashed_pw = hash_password(body.password)

    try:
        cursor = db.execute(
            "INSERT INTO users (username, hashed_password, full_name, role, is_active) VALUES (?, ?, ?, ?, 1)",
            (body.username, hashed_pw, body.full_name, role),
        )
        db.commit()
        user_id = cursor.lastrowid
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create user: {str(e)}")

    return {
        "id": user_id,
        "username": body.username,
        "full_name": body.full_name,
        "role": role,
        "is_active": True,
        "message": "User registered successfully",
    }


@limiter.limit("10/minute")
@router.post("/login")
async def login(
    request: Request,
    response: Response,
    body: LoginRequest,
    db=Depends(get_db),
):
    """Login and receive access token + refresh cookie."""
    cursor = db.execute(
        "SELECT id, username, hashed_password, full_name, role, is_active FROM users WHERE username = ? COLLATE NOCASE",
        (body.username,),
    )
    row = cursor.fetchone()

    if not row:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    user_id, db_username, hashed_pw, full_name, role, is_active = row

    if not is_active:
        raise HTTPException(status_code=403, detail="User account is inactive")

    if not verify_password(body.password, hashed_pw):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    # Create tokens
    access_token = create_access_token(user_id, db_username, role)
    refresh_token_raw, refresh_token_hash = create_refresh_token()

    # Store refresh token session
    expires_at = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_MAX_AGE_DAYS)
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    try:
        db.execute(
            "INSERT INTO user_sessions (user_id, refresh_token_hash, expires_at, ip_address, user_agent) VALUES (?, ?, ?, ?, ?)",
            (
                user_id,
                refresh_token_hash,
                expires_at.isoformat(),
                ip_address,
                user_agent,
            ),
        )
        db.execute(
            "UPDATE users SET last_login_at = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), user_id),
        )
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500, detail=f"Failed to create session: {str(e)}"
        )

    # Set httpOnly refresh cookie
    response.set_cookie(
        key=REFRESH_TOKEN_COOKIE_NAME,
        value=refresh_token_raw,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=REFRESH_TOKEN_MAX_AGE_DAYS * 24 * 60 * 60,
        path="/api/auth/refresh",
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": 15 * 60,
        "user": {
            "id": user_id,
            "username": db_username,
            "full_name": full_name,
            "role": role,
        },
    }


@limiter.limit("30/minute")
@router.post("/refresh")
async def refresh(
    request: Request,
    response: Response,
    refresh_token: Optional[str] = Cookie(None, alias=REFRESH_TOKEN_COOKIE_NAME),
    db=Depends(get_db),
):
    """Refresh access token using httpOnly refresh cookie. Rotates refresh token."""
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Refresh token missing")

    token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()

    cursor = db.execute(
        """SELECT s.id, s.user_id, s.expires_at, u.username, u.role, u.is_active
           FROM user_sessions s JOIN users u ON s.user_id = u.id
           WHERE s.refresh_token_hash = ?""",
        (token_hash,),
    )
    row = cursor.fetchone()

    if not row:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    session_id, user_id, expires_at_str, username, role, is_active = row

    # Check expiry
    expires_at = datetime.fromisoformat(expires_at_str)
    if expires_at < datetime.now(timezone.utc):
        db.execute("DELETE FROM user_sessions WHERE id = ?", (session_id,))
        db.commit()
        raise HTTPException(status_code=401, detail="Refresh token expired")

    if not is_active:
        raise HTTPException(status_code=403, detail="User account is inactive")

    # Rotate: delete old session, create new
    new_refresh_token_raw, new_refresh_token_hash = create_refresh_token()
    new_expires_at = datetime.now(timezone.utc) + timedelta(
        days=REFRESH_TOKEN_MAX_AGE_DAYS
    )

    try:
        # Insert new session FIRST, then delete old — prevents token loss on INSERT failure
        db.execute(
            "INSERT INTO user_sessions (user_id, refresh_token_hash, expires_at, last_used_at) VALUES (?, ?, ?, ?)",
            (
                user_id,
                new_refresh_token_hash,
                new_expires_at.isoformat(),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        db.execute("DELETE FROM user_sessions WHERE id = ?", (session_id,))
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500, detail=f"Failed to rotate session: {str(e)}"
        )

    access_token = create_access_token(user_id, username, role)

    response.set_cookie(
        key=REFRESH_TOKEN_COOKIE_NAME,
        value=new_refresh_token_raw,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=REFRESH_TOKEN_MAX_AGE_DAYS * 24 * 60 * 60,
        path="/api/auth/refresh",
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": 15 * 60,
    }


@router.post("/logout")
async def logout(
    response: Response,
    refresh_token: Optional[str] = Cookie(None, alias=REFRESH_TOKEN_COOKIE_NAME),
    db=Depends(get_db),
):
    """Logout and revoke refresh token."""
    if refresh_token:
        token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
        try:
            db.execute(
                "DELETE FROM user_sessions WHERE refresh_token_hash = ?", (token_hash,)
            )
            db.commit()
        except Exception:
            db.rollback()

    response.delete_cookie(key=REFRESH_TOKEN_COOKIE_NAME, path="/api/auth/refresh")
    return {"message": "Logged out successfully"}


@router.get("/setup-status")
async def setup_status(db=Depends(get_db)):
    """Check if initial setup is needed (no users exist). No auth required."""
    cursor = db.execute("SELECT COUNT(*) FROM users")
    user_count = cursor.fetchone()[0]
    return {"needs_setup": user_count == 0}


@router.get("/me")
async def get_me(user: dict = Depends(get_current_active_user)):
    """Get current user profile."""
    return {
        "id": user["id"],
        "username": user["username"],
        "full_name": user.get("full_name", ""),
        "role": user["role"],
        "is_active": user["is_active"],
    }


@router.patch("/me")
async def update_me(
    body: UpdateProfileRequest,
    user: dict = Depends(get_current_active_user),
    db=Depends(get_db),
):
    """Update current user profile (full_name and/or password)."""
    user_id = user["id"]
    updates = []
    params = []

    if body.full_name is not None:
        updates.append("full_name = ?")
        params.append(body.full_name)

    # Invalidate sessions when password changes (in same transaction)
    if body.password is not None:
        if len(body.password) < 8:
            raise HTTPException(
                status_code=400, detail="Password must be at least 8 characters"
            )
        hashed_pw = hash_password(body.password)
        updates.append("hashed_password = ?")
        params.append(hashed_pw)

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    params.append(user_id)

    try:
        db.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?", tuple(params))
        if body.password is not None:
            db.execute("DELETE FROM user_sessions WHERE user_id = ?", (user_id,))
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to update user")

    cursor = db.execute(
        "SELECT id, username, full_name, role, is_active FROM users WHERE id = ?",
        (user_id,),
    )
    row = cursor.fetchone()

    return {
        "id": row[0],
        "username": row[1],
        "full_name": row[2],
        "role": row[3],
        "is_active": bool(row[4]),
        "message": "Profile updated successfully",
    }
