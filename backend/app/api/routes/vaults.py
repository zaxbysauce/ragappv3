"""
Vault API routes for vault management.

Provides endpoints for listing, creating, updating, and deleting vaults.
Vaults are containers for documents, memories, and chat sessions.
"""

import asyncio
import logging
import sqlite3
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.deps import (
    get_current_active_user,
    get_user_accessible_vault_ids,
    require_vault_permission,
    get_db,
    get_vector_store,
)
from app.services.vector_store import VectorStore


logger = logging.getLogger(__name__)


router = APIRouter()


class VaultCreateRequest(BaseModel):
    """Request model for creating a new vault."""

    name: str = Field(..., min_length=1, max_length=255, description="Vault name")
    description: str = Field("", max_length=1000, description="Vault description")

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, v):
        if isinstance(v, str):
            return v.strip()
        return v


class VaultUpdateRequest(BaseModel):
    """Request model for updating an existing vault."""

    name: Optional[str] = Field(
        None, min_length=1, max_length=255, description="New vault name"
    )
    description: Optional[str] = Field(
        None, max_length=1000, description="New description"
    )

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, v):
        if isinstance(v, str):
            return v.strip()
        return v


class VaultResponse(BaseModel):
    """Response model for a vault record."""

    id: int
    name: str
    description: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    file_count: int = 0
    memory_count: int = 0
    session_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class VaultListResponse(BaseModel):
    """Response model for listing vaults."""

    vaults: List[VaultResponse]


def _row_to_vault_response(row) -> VaultResponse:
    """Map a database row to VaultResponse."""
    return VaultResponse(
        id=row[0],
        name=row[1],
        description=row[2],
        created_at=row[3],
        updated_at=row[4],
        file_count=row[5] or 0,
        memory_count=row[6] or 0,
        session_count=row[7] or 0,
    )


_VAULT_WITH_COUNTS_SQL = """
    SELECT v.id, v.name, v.description, v.created_at, v.updated_at,
           COUNT(DISTINCT f.id) as file_count,
           COUNT(DISTINCT m.id) as memory_count,
           COUNT(DISTINCT cs.id) as session_count
    FROM vaults v
    LEFT JOIN files f ON f.vault_id = v.id
    LEFT JOIN memories m ON m.vault_id = v.id
    LEFT JOIN chat_sessions cs ON cs.vault_id = v.id
"""


async def _fetch_vault_with_counts(
    conn: sqlite3.Connection, vault_id: int
) -> Optional[VaultResponse]:
    """Fetch a single vault with file/memory/session counts."""
    cursor = await asyncio.to_thread(
        conn.execute,
        _VAULT_WITH_COUNTS_SQL + " WHERE v.id = ? GROUP BY v.id",
        (vault_id,),
    )
    row = await asyncio.to_thread(cursor.fetchone)
    return _row_to_vault_response(row) if row else None


async def _fetch_all_vaults(conn: sqlite3.Connection) -> List[VaultResponse]:
    """Fetch all vaults with counts, ordered by creation date."""
    cursor = await asyncio.to_thread(
        conn.execute,
        _VAULT_WITH_COUNTS_SQL + " GROUP BY v.id ORDER BY v.created_at ASC",
    )
    rows = await asyncio.to_thread(cursor.fetchall)
    return [_row_to_vault_response(row) for row in rows]


@router.get("/vaults", response_model=VaultListResponse)
async def list_vaults(
    user: dict = Depends(get_current_active_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    """List all vaults with document/memory/session counts."""
    vaults = await _fetch_all_vaults(conn)

    if user.get("role") not in ("superadmin", "admin"):
        accessible_ids = get_user_accessible_vault_ids(user, conn)
        if accessible_ids:
            vaults = [v for v in vaults if v.id in accessible_ids]
        else:
            vaults = []

    return VaultListResponse(vaults=vaults)


@router.get("/vaults/accessible", response_model=VaultListResponse)
async def list_accessible_vaults(
    user: dict = Depends(get_current_active_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    """Return vaults the current user has access to."""
    if user.get("role") in ("superadmin", "admin"):
        return VaultListResponse(vaults=await _fetch_all_vaults(conn))

    accessible_ids = get_user_accessible_vault_ids(user, conn)
    if not accessible_ids:
        return VaultListResponse(vaults=[])

    vaults = await _fetch_all_vaults(conn)
    return VaultListResponse(vaults=[v for v in vaults if v.id in accessible_ids])


@router.get("/vaults/{vault_id}", response_model=VaultResponse)
async def get_vault(
    vault_id: int,
    user: dict = Depends(get_current_active_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    """Get a single vault with counts."""
    vault = await _fetch_vault_with_counts(conn, vault_id)
    if vault is None:
        raise HTTPException(
            status_code=404, detail=f"Vault with id {vault_id} not found"
        )

    from app.api.deps import evaluate_policy

    if not await evaluate_policy(user, "vault", vault_id, "read"):
        raise HTTPException(status_code=403, detail="No read access to this vault")

    return vault


@router.post("/vaults", response_model=VaultResponse, status_code=201)
async def create_vault(
    request: VaultCreateRequest,
    conn: sqlite3.Connection = Depends(get_db),
    user: dict = Depends(get_current_active_user),
):
    """
    Create a new vault.

    Creates a new vault with the given name and description.
    Returns 409 if a vault with the same name already exists.
    """
    try:
        cursor = await asyncio.to_thread(
            conn.execute,
            "INSERT INTO vaults (name, description) VALUES (?, ?)",
            (request.name, request.description),
        )
        await asyncio.to_thread(conn.commit)
        vault_id = cursor.lastrowid
        if vault_id is None:
            raise HTTPException(status_code=500, detail="Failed to create vault")
    except sqlite3.IntegrityError:
        raise HTTPException(
            status_code=409, detail=f"Vault with name '{request.name}' already exists"
        )

    vault = await _fetch_vault_with_counts(conn, vault_id)
    return vault


@router.put("/vaults/{vault_id}", response_model=VaultResponse)
async def update_vault(
    vault_id: int,
    request: VaultUpdateRequest,
    conn: sqlite3.Connection = Depends(get_db),
    user: dict = Depends(require_vault_permission("admin")),
):
    """
    Update vault name/description.

    Updates the name and/or description of the vault with the given id.
    Returns 404 if not found.
    Returns 400 if trying to rename vault id=1 (the Default vault).
    Returns 409 if new name conflicts with an existing vault.
    """
    # Check if vault exists
    cursor = await asyncio.to_thread(
        conn.execute, "SELECT id, name FROM vaults WHERE id = ?", (vault_id,)
    )
    row = await asyncio.to_thread(cursor.fetchone)

    if row is None:
        raise HTTPException(
            status_code=404, detail=f"Vault with id {vault_id} not found"
        )

    # Prevent renaming Default vault (id=1)
    if vault_id == 1 and request.name is not None:
        raise HTTPException(
            status_code=400, detail="Cannot rename the Default vault (id=1)"
        )

    # Build update query dynamically based on provided fields
    update_fields = []
    params = []

    if request.name is not None:
        update_fields.append("name = ?")
        params.append(request.name)
    if request.description is not None:
        update_fields.append("description = ?")
        params.append(request.description)

    if not update_fields:
        # No fields to update, just fetch and return current record
        vault = await _fetch_vault_with_counts(conn, vault_id)
        if vault is None:
            raise HTTPException(
                status_code=404, detail=f"Vault with id {vault_id} not found"
            )
        return vault

    # Add vault_id to params
    params.append(vault_id)

    # Execute update with error handling for duplicate name
    try:
        sql = f"""
            UPDATE vaults
            SET {", ".join(update_fields)}, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """
        await asyncio.to_thread(conn.execute, sql, params)
        await asyncio.to_thread(conn.commit)
    except sqlite3.IntegrityError:
        raise HTTPException(
            status_code=409, detail=f"Vault with name '{request.name}' already exists"
        )

    # Rename vault folder if name changed
    if request.name is not None:
        try:
            from app.services.upload_path import _rename_vault_folder

            old_name = row[1]  # Original vault name from line 194
            new_name = request.name
            if old_name != new_name:
                await asyncio.to_thread(_rename_vault_folder, old_name, new_name)
        except (OSError, shutil.Error) as e:
            # Log but don't fail the rename - folder rename is not critical
            logging.getLogger(__name__).warning(f"Failed to rename vault folder: {e}")

    # Fetch updated record
    vault = await _fetch_vault_with_counts(conn, vault_id)

    # Race condition fix: check if vault is None after fetch
    if vault is None:
        raise HTTPException(
            status_code=404, detail=f"Vault with id {vault_id} not found"
        )

    return vault


@router.delete("/vaults/{vault_id}")
async def delete_vault(
    vault_id: int,
    conn: sqlite3.Connection = Depends(get_db),
    vector_store: VectorStore = Depends(get_vector_store),
    user: dict = Depends(require_vault_permission("admin")),
):
    """
    Delete vault with cascade cleanup.

    Deletes the vault and all associated data:
    - All files in the vault (and their chunks in vector store)
    - All chat sessions and messages (via cascade)
    - Vector chunks for this vault
    - Memories: reassign to global (SET vault_id = NULL)

    Returns 400 if trying to delete vault id=1 (the Default vault).
    Returns 404 if not found.
    """
    # Prevent deleting Default vault (id=1)
    if vault_id == 1:
        raise HTTPException(
            status_code=400, detail="Cannot delete the Default vault (id=1)"
        )

    # Check if vault exists
    cursor = await asyncio.to_thread(
        conn.execute, "SELECT id, name FROM vaults WHERE id = ?", (vault_id,)
    )
    row = await asyncio.to_thread(cursor.fetchone)

    if row is None:
        raise HTTPException(
            status_code=404, detail=f"Vault with id {vault_id} not found"
        )

    vault_name = row[1]

    try:
        # Start transaction
        await asyncio.to_thread(conn.execute, "BEGIN TRANSACTION")

        # Delete vector chunks for this vault
        try:
            deleted_chunks = await asyncio.to_thread(
                vector_store.delete_by_vault, str(vault_id)
            )
            logger.info(
                "Deleted %d chunks from vector store for vault_id %s",
                deleted_chunks,
                vault_id,
            )
        except (OSError, RuntimeError, ValueError) as e:
            logger.warning("Error deleting chunks from vector store: %s", e)
            # Continue with database deletion even if vector store fails

        # Reassign memories to global (NULL) instead of deleting
        await asyncio.to_thread(
            conn.execute,
            "UPDATE memories SET vault_id = NULL WHERE vault_id = ?",
            (vault_id,),
        )

        # Delete chat_sessions (chat_messages will cascade)
        await asyncio.to_thread(
            conn.execute, "DELETE FROM chat_sessions WHERE vault_id = ?", (vault_id,)
        )

        # Delete files
        await asyncio.to_thread(
            conn.execute, "DELETE FROM files WHERE vault_id = ?", (vault_id,)
        )

        # Delete the vault itself
        await asyncio.to_thread(
            conn.execute, "DELETE FROM vaults WHERE id = ?", (vault_id,)
        )

        # Commit transaction
        await asyncio.to_thread(conn.commit)

        return {
            "message": f"Vault '{vault_name}' (id: {vault_id}) deleted successfully"
        }

    except HTTPException:
        await asyncio.to_thread(lambda: conn.rollback())
        raise
    except (sqlite3.Error, OSError, RuntimeError) as e:
        await asyncio.to_thread(lambda: conn.rollback())
        logger.exception("Error deleting vault %d", vault_id)
        raise HTTPException(status_code=500, detail=f"Delete failed: {e}")
