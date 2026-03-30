"""User management routes (admin/superadmin only)."""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from app.api.deps import get_current_active_user, require_role
from app.config import settings
from app.models.database import get_pool

router = APIRouter(prefix="/users", tags=["users"])


class UpdateRoleRequest(BaseModel):
    role: str = Field(...)


class UpdateActiveRequest(BaseModel):
    is_active: bool = Field(...)


@router.get("/")
async def list_users(
    skip: int = 0,
    limit: int = 100,
    user: dict = Depends(require_role("admin")),
):
    """List all users (admin/superadmin only)."""
    pool = get_pool(str(settings.sqlite_path))
    conn = pool.get_connection()

    try:
        count_cursor = conn.execute("SELECT COUNT(*) FROM users")
        total = count_cursor.fetchone()[0]

        cursor = conn.execute(
            """SELECT id, username, full_name, role, is_active, created_at
               FROM users ORDER BY id LIMIT ? OFFSET ?""",
            (limit, skip),
        )
        rows = cursor.fetchall()

        users = []
        for row in rows:
            users.append(
                {
                    "id": row[0],
                    "username": row[1],
                    "full_name": row[2] or "",
                    "role": row[3],
                    "is_active": bool(row[4]),
                    "created_at": row[5],
                }
            )

        return {"users": users, "total": total}
    finally:
        pool.release_connection(conn)


@router.get("/{user_id}")
async def get_user(
    user_id: int,
    user: dict = Depends(require_role("admin")),
):
    """Get user details (admin/superadmin only)."""
    pool = get_pool(str(settings.sqlite_path))
    conn = pool.get_connection()

    try:
        cursor = conn.execute(
            "SELECT id, username, full_name, role, is_active, created_at FROM users WHERE id = ?",
            (user_id,),
        )
        row = cursor.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="User not found")

        return {
            "id": row[0],
            "username": row[1],
            "full_name": row[2] or "",
            "role": row[3],
            "is_active": bool(row[4]),
            "created_at": row[5],
        }
    finally:
        pool.release_connection(conn)


@router.patch("/{user_id}/role")
async def update_user_role(
    user_id: int,
    body: UpdateRoleRequest,
    user: dict = Depends(require_role("superadmin")),
):
    """Update user role (superadmin only). Cannot demote last superadmin."""
    valid_roles = ["superadmin", "admin", "member", "viewer"]
    if body.role not in valid_roles:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role. Must be one of: {', '.join(valid_roles)}",
        )

    pool = get_pool(str(settings.sqlite_path))
    conn = pool.get_connection()

    try:
        cursor = conn.execute("SELECT role FROM users WHERE id = ?", (user_id,))
        target_row = cursor.fetchone()

        if not target_row:
            raise HTTPException(status_code=404, detail="User not found")

        current_role = target_row[0]

        if current_role == "superadmin" and body.role != "superadmin":
            # Atomic guard: only demote if there are other active superadmins
            cursor.execute(
                """UPDATE users SET role = ?
                   WHERE id = ? AND (SELECT COUNT(*) FROM users WHERE role = 'superadmin' AND is_active = 1) > 1""",
                (body.role, user_id),
            )
            if cursor.rowcount == 0:
                raise HTTPException(
                    status_code=400, detail="Cannot demote the last superadmin"
                )
        else:
            cursor.execute(
                "UPDATE users SET role = ? WHERE id = ?", (body.role, user_id)
            )
        conn.commit()

        return {
            "message": f"User role updated to {body.role}",
            "user_id": user_id,
            "role": body.role,
        }
    finally:
        pool.release_connection(conn)


@router.patch("/{user_id}/active")
async def update_user_active(
    user_id: int,
    body: UpdateActiveRequest,
    user: dict = Depends(require_role("admin")),
):
    """Activate/deactivate user (admin/superadmin only). Cannot deactivate last superadmin.

    Note: admins can deactivate other admins and members. The last-superadmin guard
    prevents operational lockout. Self-deactivation is prevented by the superadmin check.
    """
    pool = get_pool(str(settings.sqlite_path))
    conn = pool.get_connection()

    try:
        cursor = conn.execute(
            "SELECT role, is_active FROM users WHERE id = ?", (user_id,)
        )
        target_row = cursor.fetchone()

        if not target_row:
            raise HTTPException(status_code=404, detail="User not found")

        target_role = target_row[0]
        currently_active = bool(target_row[1])

        if target_role == "superadmin" and not body.is_active and currently_active:
            # Atomic guard: only deactivate if there are other active superadmins
            cursor.execute(
                """UPDATE users SET is_active = ?
                   WHERE id = ? AND (SELECT COUNT(*) FROM users WHERE role = 'superadmin' AND is_active = 1) > 1""",
                (0, user_id),
            )
            if cursor.rowcount == 0:
                raise HTTPException(
                    status_code=400, detail="Cannot deactivate the last superadmin"
                )
        else:
            cursor.execute(
                "UPDATE users SET is_active = ? WHERE id = ?",
                (1 if body.is_active else 0, user_id),
            )
        conn.commit()

        status_str = "activated" if body.is_active else "deactivated"
        return {
            "message": f"User {status_str}",
            "user_id": user_id,
            "is_active": body.is_active,
        }
    finally:
        pool.release_connection(conn)


@router.delete("/{user_id}")
async def delete_user(
    user_id: int,
    user: dict = Depends(require_role("superadmin")),
):
    """Delete user (superadmin only). Cannot delete last superadmin or self."""
    pool = get_pool(str(settings.sqlite_path))
    conn = pool.get_connection()

    try:
        cursor = conn.execute("SELECT role FROM users WHERE id = ?", (user_id,))
        target_row = cursor.fetchone()

        if not target_row:
            raise HTTPException(status_code=404, detail="User not found")

        target_role = target_row[0]

        if user_id == user.get("id"):
            raise HTTPException(
                status_code=400, detail="Cannot delete your own account"
            )

        if target_role == "superadmin":
            # Atomic guard: only delete if there are other active superadmins
            cursor.execute(
                """DELETE FROM users
                   WHERE id = ? AND (SELECT COUNT(*) FROM users WHERE role = 'superadmin' AND is_active = 1) > 1""",
                (user_id,),
            )
            if cursor.rowcount == 0:
                raise HTTPException(
                    status_code=400, detail="Cannot delete the last superadmin"
                )
        else:
            cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()

        return {"message": "User deleted", "user_id": user_id}
    finally:
        pool.release_connection(conn)
