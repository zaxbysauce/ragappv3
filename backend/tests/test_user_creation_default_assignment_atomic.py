"""Atomic default-assignment coverage for user creation paths."""

import sqlite3
import tempfile
from pathlib import Path

import pytest
from fastapi import HTTPException, Response
from starlette.requests import Request


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/auth/register",
            "headers": [],
            "client": ("testclient", 50000),
            "scheme": "http",
        }
    )


def _init_db(tmp_path: Path) -> Path:
    from app.models.database import init_db, run_migrations

    db_path = tmp_path / "app.db"
    init_db(str(db_path))
    run_migrations(str(db_path))
    return db_path


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def _assert_default_assignments(conn: sqlite3.Connection, user_id: int) -> None:
    assert (
        conn.execute(
            """
            SELECT 1
            FROM organizations o
            JOIN org_members om ON om.org_id = o.id
            WHERE o.name = 'Default' AND om.user_id = ?
            """,
            (user_id,),
        ).fetchone()
        is not None
    )
    assert (
        conn.execute(
            """
            SELECT 1
            FROM groups g
            JOIN group_members gm ON gm.group_id = g.id
            WHERE g.name = 'All Users' AND gm.user_id = ?
            """,
            (user_id,),
        ).fetchone()
        is not None
    )
    assert (
        conn.execute(
            """
            SELECT 1
            FROM vault_group_access vga
            JOIN groups g ON g.id = vga.group_id
            WHERE vga.vault_id = 1
              AND vga.permission = 'read'
              AND g.name = 'All Users'
            """
        ).fetchone()
        is not None
    )
    assert (
        conn.execute(
            """
            SELECT 1
            FROM vault_members
            WHERE vault_id = 1 AND user_id = ? AND permission = 'write'
            """,
            (user_id,),
        ).fetchone()
        is not None
    )


@pytest.mark.asyncio
async def test_registration_commits_user_and_default_assignments_together(
    tmp_path, monkeypatch
):
    from app.api.routes import auth
    from app.config import settings

    db_path = _init_db(tmp_path)
    conn = _connect(db_path)
    monkeypatch.setattr(
        settings,
        "jwt_secret_key",
        "test-secret-key-for-testing-at-least-32-chars-long",
    )
    monkeypatch.setattr(auth, "hash_password", lambda password: f"hashed:{password}")

    try:
        result = await auth.register(
            request=_request(),
            response=Response(),
            body=auth.RegisterRequest(username="firstuser", password="Password123"),
            db=conn,
            _csrf_token="csrf",
        )
        assert result["role"] == "superadmin"
        _assert_default_assignments(conn, result["id"])
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_registration_rolls_back_user_when_default_assignment_fails(
    tmp_path, monkeypatch
):
    from app.api.routes import auth
    from app.config import settings

    db_path = _init_db(tmp_path)
    conn = _connect(db_path)
    monkeypatch.setattr(
        settings,
        "jwt_secret_key",
        "test-secret-key-for-testing-at-least-32-chars-long",
    )
    monkeypatch.setattr(auth, "hash_password", lambda password: f"hashed:{password}")

    def fail_assignment(_conn, _user_id):
        raise RuntimeError("assignment failed")

    monkeypatch.setattr(auth, "_auto_assign_user_to_defaults", fail_assignment)

    try:
        with pytest.raises(HTTPException) as exc_info:
            await auth.register(
                request=_request(),
                response=Response(),
                body=auth.RegisterRequest(
                    username="rollbackuser", password="Password123"
                ),
                db=conn,
                _csrf_token="csrf",
            )
        assert exc_info.value.status_code == 500
        assert (
            conn.execute(
                "SELECT id FROM users WHERE username = ?", ("rollbackuser",)
            ).fetchone()
            is None
        )
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_admin_create_user_preserves_default_assignment_success(
    tmp_path, monkeypatch
):
    from app.api.routes import users
    from app.config import settings
    from app.models.database import _pool_cache

    db_path = _init_db(tmp_path)
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(users, "hash_password", lambda password: f"hashed:{password}")
    _pool_cache.clear()

    try:
        result = await users.create_user(
            body=users.CreateUserRequest(
                username="createduser",
                password="Password123",
                full_name="Created User",
                role="member",
            ),
            user={"id": 1, "username": "admin", "role": "admin", "is_active": True},
            _csrf_token="csrf",
        )
        conn = _connect(db_path)
        try:
            _assert_default_assignments(conn, result["id"])
        finally:
            conn.close()
    finally:
        _pool_cache.clear()


@pytest.mark.asyncio
async def test_admin_create_user_rolls_back_when_default_assignment_fails(
    tmp_path, monkeypatch
):
    from app.api.routes import users
    from app.config import settings
    from app.models.database import _pool_cache

    db_path = _init_db(tmp_path)
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(users, "hash_password", lambda password: f"hashed:{password}")

    def fail_assignment(_conn, _user_id):
        raise RuntimeError("assignment failed")

    monkeypatch.setattr(users, "_auto_assign_user_to_defaults", fail_assignment)
    _pool_cache.clear()

    try:
        with pytest.raises(HTTPException) as exc_info:
            await users.create_user(
                body=users.CreateUserRequest(
                    username="rollbackuser",
                    password="Password123",
                    full_name="Rollback User",
                    role="member",
                ),
                user={
                    "id": 1,
                    "username": "admin",
                    "role": "admin",
                    "is_active": True,
                },
                _csrf_token="csrf",
            )
        assert exc_info.value.status_code == 500
        conn = _connect(db_path)
        try:
            assert (
                conn.execute(
                    "SELECT id FROM users WHERE username = ?", ("rollbackuser",)
                ).fetchone()
                is None
            )
        finally:
            conn.close()
    finally:
        _pool_cache.clear()
