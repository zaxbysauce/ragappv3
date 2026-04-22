"""
Memory API routes for CRUD operations on memories.

Provides endpoints for listing, creating, updating, deleting, and searching memories.
"""

import asyncio
import json
import logging
import sqlite3
from typing import List, Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.deps import (
    evaluate_policy,
    get_current_active_user,
    get_db,
    get_memory_store,
)
from app.services.memory_store import MemoryRecord, MemoryStore, MemoryStoreError

logger = logging.getLogger(__name__)


router = APIRouter()


def _normalize_tags(tags: Optional[str]) -> Optional[str]:
    """Normalize tags to a valid JSON string."""
    if tags is None:
        return None
    tags = tags.strip()
    if not tags:
        return None
    # If it looks like a JSON array, validate it
    if tags.startswith("["):
        try:
            parsed = json.loads(tags)
            if not isinstance(parsed, list):
                raise ValueError("Tags must be a JSON array")
            return json.dumps(parsed)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON array for tags: {e}")
    # Otherwise, treat as comma-separated and convert to JSON array
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    return json.dumps(tag_list) if tag_list else None


def _normalize_tags_input(tags: Optional[Union[str, List[str]]]) -> Optional[str]:
    """Normalize tags from strings or lists into a JSON array string."""
    if tags is None:
        return None
    if isinstance(tags, list):
        cleaned = [
            str(tag).strip() for tag in tags if isinstance(tag, str) and tag.strip()
        ]
        return json.dumps(cleaned) if cleaned else None
    return _normalize_tags(tags)


class MemoryCreateRequest(BaseModel):
    """Request model for creating a new memory."""

    content: str = Field(
        ..., min_length=1, max_length=10000, description="Memory content"
    )
    category: Optional[str] = Field(
        None, max_length=255, description="Optional category"
    )
    tags: Optional[str] = Field(
        None,
        max_length=1000,
        description="Optional tags (JSON array or comma-separated)",
    )
    source: Optional[str] = Field(
        None, max_length=500, description="Optional source reference"
    )
    vault_id: Optional[int] = Field(
        None, description="Optional vault ID to scope this memory"
    )

    @field_validator("tags", mode="before")
    @classmethod
    def validate_tags(cls, v):
        return _normalize_tags_input(v)


class MemoryUpdateRequest(BaseModel):
    """Request model for updating an existing memory."""

    content: Optional[str] = Field(
        None, min_length=1, max_length=10000, description="Memory content"
    )
    category: Optional[str] = Field(
        None, max_length=255, description="Optional category"
    )
    tags: Optional[str] = Field(None, max_length=1000, description="Optional tags")
    source: Optional[str] = Field(
        None, max_length=500, description="Optional source reference"
    )

    @field_validator("tags", mode="before")
    @classmethod
    def validate_tags(cls, v):
        return _normalize_tags_input(v)


class MemoryMetadata(BaseModel):
    """Metadata object for memory responses (frontend compatibility)."""

    category: Optional[str] = None
    tags: Optional[List[str]] = None
    source: Optional[str] = None


class MemoryResponse(BaseModel):
    """Response model for a memory record (frontend compatible)."""

    id: str
    content: str
    metadata: Optional[MemoryMetadata] = None
    score: Optional[float] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class MemoryListResponse(BaseModel):
    """Response model for listing memories."""

    memories: List[MemoryResponse]


class MemorySearchResponse(BaseModel):
    """Response model for memory search results (frontend compatible)."""

    results: List[MemoryResponse]
    total: int


class MemorySearchRequest(BaseModel):
    query: Optional[str] = Field(default="", description="Search query string")
    limit: int = Field(default=5, ge=1, le=100, description="Maximum number of results")
    vault_id: Optional[int] = Field(
        None, description="Optional vault ID to filter search"
    )


def _parse_tags_to_list(tags: Optional[str]) -> Optional[List[str]]:
    """Parse tags JSON string to list."""
    if not tags:
        return None
    try:
        parsed = json.loads(tags)
        if isinstance(parsed, list):
            return parsed
        # If JSON parsed but is not a list, fallback to string split
        return [t.strip() for t in str(parsed).split(",") if t.strip()]
    except json.JSONDecodeError:
        # Try comma-separated fallback
        return [t.strip() for t in tags.split(",") if t.strip()]
    return None


def _memory_record_to_response(
    record: MemoryRecord, score: Optional[float] = None
) -> MemoryResponse:
    """Convert a MemoryRecord to a MemoryResponse (frontend compatible format)."""
    metadata = (
        MemoryMetadata(
            category=record.category,
            tags=_parse_tags_to_list(record.tags),
            source=record.source,
        )
        if any([record.category, record.tags, record.source])
        else None
    )

    return MemoryResponse(
        id=str(record.id),
        content=record.content,
        metadata=metadata,
        score=score,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


async def _perform_memory_search(
    memory_store: MemoryStore, query: str, limit: int, vault_id: Optional[int] = None
) -> List[MemoryResponse]:
    try:
        records = await asyncio.to_thread(
            memory_store.search_memories, query=query, limit=limit, vault_id=vault_id
        )
    except MemoryStoreError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return [
        _memory_record_to_response(record, getattr(record, "score", None))
        for record in records
    ]


@router.get("/memories", response_model=MemoryListResponse)
async def list_memories(
    vault_id: Optional[int] = Query(None, description="Filter by vault ID"),
    conn: sqlite3.Connection = Depends(get_db),
    user: dict = Depends(get_current_active_user),
):
    """
    List all memories.

    Returns a list of all memories with their id, content, category, tags, source,
    created_at, and updated_at fields.
    """
    if vault_id is not None:
        cursor = await asyncio.to_thread(
            conn.execute,
            """
            SELECT id, content, category, tags, source, created_at, updated_at
            FROM memories
            WHERE vault_id = ?
            ORDER BY created_at DESC
            """,
            (vault_id,),
        )
    else:
        cursor = await asyncio.to_thread(
            conn.execute,
            """
            SELECT id, content, category, tags, source, created_at, updated_at
            FROM memories
            ORDER BY created_at DESC
            """,
        )
    rows = await asyncio.to_thread(cursor.fetchall)

    memories = []
    for row in rows:
        metadata = (
            MemoryMetadata(
                category=row[2],
                tags=_parse_tags_to_list(row[3]),
                source=row[4],
            )
            if any([row[2], row[3], row[4]])
            else None
        )
        memories.append(
            MemoryResponse(
                id=str(row[0]),
                content=row[1],
                metadata=metadata,
                created_at=row[5],
                updated_at=row[6],
            )
        )

    return MemoryListResponse(memories=memories)


@router.post("/memories", response_model=MemoryResponse)
async def create_memory(
    request: MemoryCreateRequest,
    memory_store: MemoryStore = Depends(get_memory_store),
    user: dict = Depends(get_current_active_user),
):
    """
    Create a new memory.

    Uses MemoryStore.add_memory to add a new memory to the database.
    """
    if request.vault_id is not None:
        if not await evaluate_policy(user, "vault", request.vault_id, "write"):
            raise HTTPException(status_code=403, detail="No write access to this vault")
    try:
        record = await asyncio.to_thread(
            memory_store.add_memory,
            content=request.content,
            category=request.category,
            tags=request.tags,
            source=request.source,
            vault_id=request.vault_id,
        )
    except MemoryStoreError as e:
        logger.exception(
            "MemoryStoreError in create_memory (content length: %d)",
            len(request.content),
        )
        raise HTTPException(status_code=400, detail=str(e))
    except sqlite3.Error as e:
        logger.exception(
            "Database error in create_memory (content length: %d)", len(request.content)
        )
        raise HTTPException(status_code=500, detail=f"Database error: {e}")
    except (ValueError, TypeError, RuntimeError) as e:
        logger.exception(
            "Unexpected error in create_memory (content length: %d)",
            len(request.content),
        )
        raise HTTPException(status_code=500, detail=f"Server error: {e}")

    return _memory_record_to_response(record)


@router.put("/memories/{memory_id}", response_model=MemoryResponse)
async def update_memory(
    memory_id: int,
    request: MemoryUpdateRequest,
    conn: sqlite3.Connection = Depends(get_db),
    user: dict = Depends(get_current_active_user),
):
    """
    Update an existing memory.

    Updates content, category, tags, and/or source fields in the database.
    Returns 404 if the memory is not found.
    """
    try:
        # Check if memory exists and get vault_id
        cursor = await asyncio.to_thread(
            conn.execute, "SELECT id, vault_id FROM memories WHERE id = ?", (memory_id,)
        )
        row = await asyncio.to_thread(cursor.fetchone)
        if row is None:
            raise HTTPException(
                status_code=404, detail=f"Memory with id {memory_id} not found"
            )

        # Check vault write permission
        memory_vault_id = row[1]
        if memory_vault_id is not None:
            if not await evaluate_policy(user, "vault", memory_vault_id, "write"):
                raise HTTPException(
                    status_code=403, detail="No write access to this vault"
                )

        # Build update query dynamically based on provided fields
        update_fields = []
        params = []

        if request.content is not None:
            update_fields.append("content = ?")
            params.append(request.content)
        if request.category is not None:
            update_fields.append("category = ?")
            params.append(request.category)
        if request.tags is not None:
            update_fields.append("tags = ?")
            params.append(request.tags)
        if request.source is not None:
            update_fields.append("source = ?")
            params.append(request.source)

        if not update_fields:
            # No fields to update, just fetch and return current record
            cursor = await asyncio.to_thread(
                conn.execute,
                """
                SELECT id, content, category, tags, source, created_at, updated_at
                FROM memories WHERE id = ?
                """,
                (memory_id,),
            )
            row = await asyncio.to_thread(cursor.fetchone)
            if row is None:
                raise HTTPException(
                    status_code=404, detail=f"Memory with id {memory_id} not found"
                )
            metadata = (
                MemoryMetadata(
                    category=row[2],
                    tags=_parse_tags_to_list(row[3]),
                    source=row[4],
                )
                if any([row[2], row[3], row[4]])
                else None
            )
            return MemoryResponse(
                id=str(row[0]),
                content=row[1],
                metadata=metadata,
                created_at=row[5],
                updated_at=row[6],
            )

        # Add memory_id to params
        params.append(memory_id)

        # Execute update
        sql = f"""
            UPDATE memories
            SET {", ".join(update_fields)}, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """
        await asyncio.to_thread(conn.execute, sql, params)
        await asyncio.to_thread(conn.commit)

        # Fetch updated record
        cursor = await asyncio.to_thread(
            conn.execute,
            """
            SELECT id, content, category, tags, source, created_at, updated_at
            FROM memories WHERE id = ?
            """,
            (memory_id,),
        )
        row = await asyncio.to_thread(cursor.fetchone)

        # Race condition fix: check if row is None after fetch
        if row is None:
            raise HTTPException(
                status_code=404, detail=f"Memory with id {memory_id} not found"
            )

        metadata = (
            MemoryMetadata(
                category=row[2],
                tags=_parse_tags_to_list(row[3]),
                source=row[4],
            )
            if any([row[2], row[3], row[4]])
            else None
        )
        return MemoryResponse(
            id=str(row[0]),
            content=row[1],
            metadata=metadata,
            created_at=row[5],
            updated_at=row[6],
        )
    except (sqlite3.Error, OSError) as e:
        logger.error(f"Database error during memory update: {e}")
        await asyncio.to_thread(lambda: conn.rollback())
        raise HTTPException(status_code=500, detail=f"Database error: {e}")


@router.delete("/memories/{memory_id}")
async def delete_memory(
    memory_id: int,
    conn: sqlite3.Connection = Depends(get_db),
    user: dict = Depends(get_current_active_user),
):
    """
    Delete a memory.

    Deletes the memory with the given id from the database.
    Returns 404 if the memory is not found.
    """
    # Check if memory exists and get vault_id
    cursor = await asyncio.to_thread(
        conn.execute, "SELECT id, vault_id FROM memories WHERE id = ?", (memory_id,)
    )
    row = await asyncio.to_thread(cursor.fetchone)
    if row is None:
        raise HTTPException(
            status_code=404, detail=f"Memory with id {memory_id} not found"
        )

    # Check vault admin permission
    memory_vault_id = row[1]
    if memory_vault_id is not None:
        if not await evaluate_policy(user, "vault", memory_vault_id, "admin"):
            raise HTTPException(status_code=403, detail="No admin access to this vault")

    # Delete the memory
    await asyncio.to_thread(
        conn.execute, "DELETE FROM memories WHERE id = ?", (memory_id,)
    )
    await asyncio.to_thread(conn.commit)

    return {"message": f"Memory {memory_id} deleted successfully"}


@router.get("/memories/search", response_model=MemorySearchResponse)
async def search_memories(
    query: str = Query(..., min_length=1, description="Search query string"),
    limit: int = Query(5, ge=1, le=100, description="Maximum number of results"),
    vault_id: Optional[int] = Query(None, description="Filter by vault ID"),
    memory_store: MemoryStore = Depends(get_memory_store),
    user: dict = Depends(get_current_active_user),
):
    """
    Search memories using full-text search.

    Uses MemoryStore.search_memories to search memories via FTS5.
    Returns matching memories ordered by relevance.
    """
    results = await _perform_memory_search(memory_store, query, limit, vault_id)
    return MemorySearchResponse(results=results, total=len(results))


@router.post("/memories/search", response_model=MemorySearchResponse)
async def search_memories_post(
    request: MemorySearchRequest,
    memory_store: MemoryStore = Depends(get_memory_store),
    user: dict = Depends(get_current_active_user),
):
    # Handle empty or whitespace-only queries gracefully
    if not request.query or not request.query.strip():
        return MemorySearchResponse(results=[], total=0)
    results = await _perform_memory_search(
        memory_store, request.query, request.limit, request.vault_id
    )
    return MemorySearchResponse(results=results, total=len(results))
