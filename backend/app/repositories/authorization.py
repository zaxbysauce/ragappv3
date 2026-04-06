"""
Authorization repository — centralizes all SQL queries used for authentication
and authorization decisions. Business logic stays in deps.py; this layer is
purely data access.
"""

import asyncio
import sqlite3
from typing import Optional


class AuthorizationRepository:
    """Data access layer for authentication and authorization queries."""

    def __init__(self, db: sqlite3.Connection) -> None:
        self._db = db

    async def get_user_by_id(self, user_id: int) -> Optional[sqlite3.Row]:
        """Fetch user row by ID. Returns None if not found."""
        cursor = await asyncio.to_thread(
            self._db.execute,
            "SELECT id, username, full_name, role, is_active, must_change_password FROM users WHERE id = ?",
            (user_id,),
        )
        return await asyncio.to_thread(cursor.fetchone)

    async def get_vault_member_permission(
        self, vault_id: int, user_id: int
    ) -> Optional[sqlite3.Row]:
        """Return the vault_members row for a direct member, or None."""
        cursor = await asyncio.to_thread(
            self._db.execute,
            "SELECT permission FROM vault_members WHERE vault_id = ? AND user_id = ?",
            (vault_id, user_id),
        )
        return await asyncio.to_thread(cursor.fetchone)

    async def get_vault_group_permissions(
        self, vault_id: int, user_id: int
    ) -> list[sqlite3.Row]:
        """Return all vault_group_access rows for a user's groups in a vault."""
        cursor = await asyncio.to_thread(
            self._db.execute,
            """SELECT vga.permission FROM vault_group_access vga
               JOIN group_members gm ON vga.group_id = gm.group_id
               WHERE vga.vault_id = ? AND gm.user_id = ?""",
            (vault_id, user_id),
        )
        return await asyncio.to_thread(cursor.fetchall)

    async def get_vault_visibility(self, vault_id: int) -> Optional[sqlite3.Row]:
        """Return the vaults row (visibility column) for a vault, or None."""
        cursor = await asyncio.to_thread(
            self._db.execute,
            "SELECT visibility FROM vaults WHERE id = ?",
            (vault_id,),
        )
        return await asyncio.to_thread(cursor.fetchone)

    async def get_user_vault_ids(self, user_id: int) -> list[int]:
        """Return all vault IDs the user has direct membership in."""
        cursor = await asyncio.to_thread(
            self._db.execute,
            "SELECT vault_id FROM vault_members WHERE user_id = ?",
            (user_id,),
        )
        rows = await asyncio.to_thread(cursor.fetchall)
        return [row[0] for row in rows]

    async def get_user_group_vault_ids(self, user_id: int) -> list[int]:
        """Return all vault IDs accessible via group membership."""
        cursor = await asyncio.to_thread(
            self._db.execute,
            """SELECT DISTINCT vga.vault_id FROM vault_group_access vga
               JOIN group_members gm ON vga.group_id = gm.group_id
               WHERE gm.user_id = ?""",
            (user_id,),
        )
        rows = await asyncio.to_thread(cursor.fetchall)
        return [row[0] for row in rows]

    async def get_user_org_ids(self, user_id: int) -> list[int]:
        """Return all organization IDs the user belongs to."""
        cursor = await asyncio.to_thread(
            self._db.execute,
            "SELECT org_id FROM org_members WHERE user_id = ?",
            (user_id,),
        )
        rows = await asyncio.to_thread(cursor.fetchall)
        return [row[0] for row in rows]
