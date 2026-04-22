"""Organization CRUD and member management routes."""

import re
import sqlite3
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.api.deps import require_role
from app.config import settings
from app.models.database import get_pool

router = APIRouter(prefix="/organizations", tags=["organizations"])


class OrganizationCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(default="", max_length=1000)


class OrganizationUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)


VALID_ORG_ROLES = ("owner", "admin", "member")


class OrgMemberRequest(BaseModel):
    user_id: int = Field(..., gt=0)
    role: str

    @field_validator("role")
    @classmethod
    def validate_role(cls, v):
        if v not in VALID_ORG_ROLES:
            raise ValueError(f"Role must be one of: {', '.join(VALID_ORG_ROLES)}")
        return v


class OrgMemberUpdateRequest(BaseModel):
    role: str

    @field_validator("role")
    @classmethod
    def validate_role(cls, v):
        if v not in VALID_ORG_ROLES:
            raise ValueError(f"Role must be one of: {', '.join(VALID_ORG_ROLES)}")
        return v


def _generate_slug(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    slug = re.sub(r"-+", "-", slug)
    return slug[:50]


def _is_org_admin_or_owner(conn: sqlite3.Connection, org_id: int, user_id: int) -> bool:
    """Check if user has admin or owner role in the organization."""
    cursor = conn.execute(
        "SELECT role FROM org_members WHERE org_id = ? AND user_id = ?",
        (org_id, user_id),
    )
    row = cursor.fetchone()
    if not row:
        return False
    return row[0] in ("owner", "admin")


@router.get("/")
async def list_organizations(user: dict = Depends(require_role("member"))):
    """List organizations. Superadmin/admin see all; others see their own."""
    pool = get_pool(str(settings.sqlite_path))
    conn = pool.get_connection()
    try:
        user_role = user.get("role", "")
        if user_role in ("superadmin", "admin"):
            cursor = conn.execute(
                """SELECT o.id, o.name, o.description, o.created_at, o.updated_at,
                          COUNT(DISTINCT om.user_id) as member_count,
                          COUNT(DISTINCT v.id) as vault_count
                   FROM organizations o
                   LEFT JOIN org_members om ON o.id = om.org_id
                   LEFT JOIN vaults v ON v.org_id = o.id
                   GROUP BY o.id
                   ORDER BY o.name""",
            )
        else:
            cursor = conn.execute(
                """SELECT o.id, o.name, o.description, o.created_at, o.updated_at,
                          COUNT(DISTINCT om2.user_id) as member_count,
                          COUNT(DISTINCT v.id) as vault_count
                   FROM organizations o
                   JOIN org_members om ON o.id = om.org_id
                   LEFT JOIN org_members om2 ON o.id = om2.org_id
                   LEFT JOIN vaults v ON v.org_id = o.id
                   WHERE om.user_id = ?
                   GROUP BY o.id
                   ORDER BY o.name""",
                (user["id"],),
            )
        rows = cursor.fetchall()
        organizations = []
        for row in rows:
            organizations.append(
                {
                    "id": row[0],
                    "name": row[1],
                    "description": row[2] or "",
                    "created_at": row[3],
                    "updated_at": row[4],
                    "member_count": row[5] or 0,
                    "vault_count": row[6] or 0,
                }
            )
        return {"organizations": organizations, "total": len(organizations)}
    finally:
        pool.release_connection(conn)


@router.post("/")
async def create_organization(
    req: OrganizationCreateRequest,
    user: dict = Depends(require_role("admin")),
):
    """Create a new organization with the current user as owner."""
    pool = get_pool(str(settings.sqlite_path))
    conn = pool.get_connection()
    try:
        slug = _generate_slug(req.name)
        try:
            # Insert organization
            cursor = conn.execute(
                """INSERT INTO organizations (name, description, slug, created_by)
                   VALUES (?, ?, ?, ?)""",
                (req.name, req.description or "", slug, user["id"]),
            )
            org_id = cursor.lastrowid

            # Add creator as owner
            conn.execute(
                "INSERT INTO org_members (org_id, user_id, role) VALUES (?, ?, 'owner')",
                (org_id, user["id"]),
            )

            conn.commit()
        except sqlite3.IntegrityError:
            conn.rollback()
            raise HTTPException(
                status_code=409,
                detail="Conflict — could not create organization. Please choose a different name.",
            )

        # Fetch created organization
        cursor = conn.execute(
            """SELECT o.id, o.name, o.description, o.slug, o.created_at, o.updated_at,
                      COUNT(DISTINCT om.user_id) as member_count,
                      COUNT(DISTINCT v.id) as vault_count
               FROM organizations o
               LEFT JOIN org_members om ON o.id = om.org_id
               LEFT JOIN vaults v ON v.org_id = o.id
               WHERE o.id = ?
               GROUP BY o.id""",
            (org_id,),
        )
        row = cursor.fetchone()
        return {
            "id": row[0],
            "name": row[1],
            "description": row[2] or "",
            "slug": row[3],
            "created_at": row[4],
            "updated_at": row[5],
            "member_count": row[6] or 0,
            "vault_count": row[7] or 0,
        }
    finally:
        pool.release_connection(conn)


@router.get("/{org_id}")
async def get_organization(
    org_id: int,
    user: dict = Depends(require_role("member")),
):
    """Get organization details with members list."""
    pool = get_pool(str(settings.sqlite_path))
    conn = pool.get_connection()
    try:
        # Check user is member
        cursor = conn.execute(
            "SELECT 1 FROM org_members WHERE org_id = ? AND user_id = ?",
            (org_id, user["id"]),
        )
        if not cursor.fetchone():
            raise HTTPException(
                status_code=403,
                detail="Access denied: not a member of this organization",
            )

        # Fetch organization details
        cursor = conn.execute(
            """SELECT o.id, o.name, o.description, o.slug, o.created_at, o.updated_at,
                      COUNT(DISTINCT om.user_id) as member_count,
                      COUNT(DISTINCT v.id) as vault_count
               FROM organizations o
               LEFT JOIN org_members om ON o.id = om.org_id
               LEFT JOIN vaults v ON v.org_id = o.id
               WHERE o.id = ?
               GROUP BY o.id""",
            (org_id,),
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Organization not found")

        org = {
            "id": row[0],
            "name": row[1],
            "description": row[2] or "",
            "slug": row[3],
            "created_at": row[4],
            "updated_at": row[5],
            "member_count": row[6] or 0,
            "vault_count": row[7] or 0,
        }

        # Fetch members
        cursor = conn.execute(
            """SELECT u.id, u.username, u.full_name, om.role, om.joined_at
               FROM org_members om JOIN users u ON om.user_id = u.id
               WHERE om.org_id = ? ORDER BY om.role DESC, u.username""",
            (org_id,),
        )
        members = []
        for member_row in cursor.fetchall():
            members.append(
                {
                    "id": member_row[0],
                    "username": member_row[1],
                    "full_name": member_row[2] or "",
                    "role": member_row[3],
                    "joined_at": member_row[4],
                }
            )

        org["members"] = members
        return org
    finally:
        pool.release_connection(conn)


@router.patch("/{org_id}")
async def update_organization(
    org_id: int,
    req: OrganizationUpdateRequest,
    user: dict = Depends(require_role("member")),
):
    """Update organization details (admin or owner only)."""
    pool = get_pool(str(settings.sqlite_path))
    conn = pool.get_connection()
    try:
        # Check organization exists
        cursor = conn.execute("SELECT id FROM organizations WHERE id = ?", (org_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Organization not found")

        # Check user is admin or owner
        cursor = conn.execute(
            "SELECT role FROM org_members WHERE org_id = ? AND user_id = ?",
            (org_id, user["id"]),
        )
        row = cursor.fetchone()
        if not row or row[0] not in ("owner", "admin"):
            raise HTTPException(
                status_code=403,
                detail="Insufficient privileges. Organization admin or owner required",
            )

        # Build partial update
        updates = []
        params = []
        if req.name is not None:
            updates.append("name = ?")
            params.append(req.name)
            # Update slug when name changes
            updates.append("slug = ?")
            params.append(_generate_slug(req.name))
        if req.description is not None:
            updates.append("description = ?")
            params.append(req.description)

        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

        updates.append("updated_at = CURRENT_TIMESTAMP")
        params.append(org_id)

        try:
            conn.execute(
                f"UPDATE organizations SET {', '.join(updates)} WHERE id = ?",
                params,
            )
            conn.commit()
        except sqlite3.IntegrityError:
            conn.rollback()
            raise HTTPException(
                status_code=409,
                detail="Conflict — could not update organization. Please choose a different name.",
            )

        # Check if organization still exists after update
        cursor = conn.execute(
            """SELECT o.id, o.name, o.description, o.slug, o.created_at, o.updated_at,
                      COUNT(DISTINCT om.user_id) as member_count,
                      COUNT(DISTINCT v.id) as vault_count
               FROM organizations o
               LEFT JOIN org_members om ON o.id = om.org_id
               LEFT JOIN vaults v ON v.org_id = o.id
               WHERE o.id = ?
               GROUP BY o.id""",
            (org_id,),
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Organization not found")

        return {
            "id": row[0],
            "name": row[1],
            "description": row[2] or "",
            "slug": row[3],
            "created_at": row[4],
            "updated_at": row[5],
            "member_count": row[6] or 0,
            "vault_count": row[7] or 0,
        }
    finally:
        pool.release_connection(conn)


@router.get("/{org_id}/members")
async def list_org_members(
    org_id: int,
    user: dict = Depends(require_role("member")),
):
    """List members of an organization."""
    pool = get_pool(str(settings.sqlite_path))
    conn = pool.get_connection()
    try:
        # Check organization exists
        cursor = conn.execute("SELECT id FROM organizations WHERE id = ?", (org_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Organization not found")

        # Check user is member (or superadmin/admin who can see all)
        user_role = user.get("role", "")
        if user_role not in ("superadmin", "admin"):
            cursor = conn.execute(
                "SELECT 1 FROM org_members WHERE org_id = ? AND user_id = ?",
                (org_id, user["id"]),
            )
            if not cursor.fetchone():
                raise HTTPException(
                    status_code=403,
                    detail="Access denied: not a member of this organization",
                )

        # Fetch members
        cursor = conn.execute(
            """SELECT u.id, u.username, u.full_name, om.role, om.joined_at
               FROM org_members om JOIN users u ON om.user_id = u.id
               WHERE om.org_id = ? ORDER BY om.role DESC, u.username""",
            (org_id,),
        )
        members = []
        for row in cursor.fetchall():
            members.append(
                {
                    "user_id": row[0],
                    "username": row[1],
                    "full_name": row[2] or "",
                    "role": row[3],
                    "joined_at": row[4],
                }
            )
        return {"members": members}
    finally:
        pool.release_connection(conn)


@router.post("/{org_id}/members")
async def add_org_member(
    org_id: int,
    req: OrgMemberRequest,
    user: dict = Depends(require_role("member")),
):
    """Add a member to organization (admin or owner only)."""
    pool = get_pool(str(settings.sqlite_path))
    conn = pool.get_connection()
    try:
        # Check organization exists
        cursor = conn.execute("SELECT id FROM organizations WHERE id = ?", (org_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Organization not found")

        # Check caller is admin or owner
        if not _is_org_admin_or_owner(conn, org_id, user["id"]):
            raise HTTPException(
                status_code=403,
                detail="Insufficient privileges. Organization admin or owner required",
            )

        # Check target user exists and is active
        cursor = conn.execute(
            "SELECT id, username, full_name FROM users WHERE id = ? AND is_active = 1",
            (req.user_id,),
        )
        target_user = cursor.fetchone()
        if not target_user:
            raise HTTPException(
                status_code=404,
                detail="User not found or inactive",
            )

        # Only org owners can add other owners
        if req.role == "owner":
            # Check if caller is actually an owner (not just admin)
            caller_role_row = conn.execute(
                "SELECT role FROM org_members WHERE org_id = ? AND user_id = ?",
                (org_id, user["id"]),
            ).fetchone()
            if not caller_role_row or caller_role_row[0] != "owner":
                raise HTTPException(
                    status_code=403,
                    detail="Only organization owners can assign the owner role",
                )

        # Check not already member
        cursor = conn.execute(
            "SELECT 1 FROM org_members WHERE org_id = ? AND user_id = ?",
            (org_id, req.user_id),
        )
        if cursor.fetchone():
            raise HTTPException(
                status_code=409,
                detail="User is already a member of this organization",
            )

        # Insert member
        cursor = conn.execute(
            "INSERT INTO org_members (org_id, user_id, role) VALUES (?, ?, ?)",
            (org_id, req.user_id, req.role),
        )
        conn.commit()

        # Fetch member details
        cursor = conn.execute(
            """SELECT u.id, u.username, u.full_name, om.role, om.joined_at
               FROM org_members om JOIN users u ON om.user_id = u.id
               WHERE om.org_id = ? AND om.user_id = ?""",
            (org_id, req.user_id),
        )
        row = cursor.fetchone()
        return {
            "id": row[0],
            "username": row[1],
            "full_name": row[2] or "",
            "role": row[3],
            "joined_at": row[4],
        }
    finally:
        pool.release_connection(conn)


@router.patch("/{org_id}/members/{member_user_id}")
async def update_org_member_role(
    org_id: int,
    member_user_id: int,
    req: OrgMemberUpdateRequest,
    user: dict = Depends(require_role("member")),
):
    """Update a member's role (admin or owner only)."""
    pool = get_pool(str(settings.sqlite_path))
    conn = pool.get_connection()
    try:
        # Check organization exists
        cursor = conn.execute("SELECT id FROM organizations WHERE id = ?", (org_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Organization not found")

        # Check caller is admin or owner
        if not _is_org_admin_or_owner(conn, org_id, user["id"]):
            raise HTTPException(
                status_code=403,
                detail="Insufficient privileges. Organization admin or owner required",
            )

        # Fetch target member's current role
        cursor = conn.execute(
            "SELECT role FROM org_members WHERE org_id = ? AND user_id = ?",
            (org_id, member_user_id),
        )
        target_row = cursor.fetchone()
        if not target_row:
            raise HTTPException(status_code=404, detail="Member not found")
        if target_row[0] == "owner":
            raise HTTPException(
                status_code=403,
                detail="Cannot change the role of the organization owner",
            )

        # Update role
        try:
            cursor.execute(
                "UPDATE org_members SET role = ? WHERE org_id = ? AND user_id = ?",
                (req.role, org_id, member_user_id),
            )
            conn.commit()
        except sqlite3.Error:
            conn.rollback()
            raise HTTPException(
                status_code=409,
                detail="Could not update member role. Please try again.",
            )

        # Fetch updated member details
        cursor = conn.execute(
            """SELECT u.id, u.username, u.full_name, om.role, om.joined_at
               FROM org_members om JOIN users u ON om.user_id = u.id
               WHERE om.org_id = ? AND om.user_id = ?""",
            (org_id, member_user_id),
        )
        row = cursor.fetchone()
        return {
            "id": row[0],
            "username": row[1],
            "full_name": row[2] or "",
            "role": row[3],
            "joined_at": row[4],
        }
    finally:
        pool.release_connection(conn)


@router.delete("/{org_id}/members/{member_user_id}")
async def remove_org_member(
    org_id: int,
    member_user_id: int,
    user: dict = Depends(require_role("member")),
):
    """Remove a member from organization (admin or owner only)."""
    pool = get_pool(str(settings.sqlite_path))
    conn = pool.get_connection()
    try:
        # Check organization exists
        cursor = conn.execute("SELECT id FROM organizations WHERE id = ?", (org_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Organization not found")

        # Check caller is admin or owner
        if not _is_org_admin_or_owner(conn, org_id, user["id"]):
            raise HTTPException(
                status_code=403,
                detail="Insufficient privileges. Organization admin or owner required",
            )

        # Check target member exists
        cursor = conn.execute(
            "SELECT role FROM org_members WHERE org_id = ? AND user_id = ?",
            (org_id, member_user_id),
        )
        target_row = cursor.fetchone()
        if not target_row:
            raise HTTPException(
                status_code=404,
                detail="Member not found in organization",
            )
        if target_row[0] == "owner":
            raise HTTPException(
                status_code=403,
                detail="Cannot remove the organization owner. Transfer ownership first.",
            )

        # Check not removing self
        if member_user_id == user.get("id"):
            raise HTTPException(
                status_code=400, detail="Cannot remove yourself from an organization"
            )

        # Delete member
        try:
            conn.execute(
                "DELETE FROM org_members WHERE org_id = ? AND user_id = ?",
                (org_id, member_user_id),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

        return {
            "message": "Member removed",
            "org_id": org_id,
            "user_id": member_user_id,
        }
    finally:
        pool.release_connection(conn)


@router.delete("/{org_id}")
async def delete_organization(
    org_id: int,
    user: dict = Depends(require_role("superadmin")),
):
    """Delete organization and all associated data (superadmin only)."""
    pool = get_pool(str(settings.sqlite_path))
    conn = pool.get_connection()
    try:
        # Check organization exists
        cursor = conn.execute(
            "SELECT 1 FROM organizations WHERE id = ?",
            (org_id,),
        )
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Organization not found")

        # Delete organization (FK cascades handle org_members, groups, group_members)
        conn.execute("DELETE FROM organizations WHERE id = ?", (org_id,))
        conn.commit()

        return {
            "message": "Organization deleted",
            "org_id": org_id,
        }
    finally:
        pool.release_connection(conn)
