"""Memory storage service backed by SQLite + FTS5."""

import re
import sqlite3
from dataclasses import dataclass
from typing import List, Optional

from app.config import settings
from app.models.database import SQLiteConnectionPool, get_pool
from app.utils.retry import with_retry


class MemoryStoreError(Exception):
    """General memory store error."""


class MemoryDetectionError(MemoryStoreError):
    """Raised when a memory pattern cannot be parsed."""


@dataclass
class MemoryRecord:
    id: int
    content: str
    category: Optional[str]
    tags: Optional[str]
    source: Optional[str]
    vault_id: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    score: Optional[float] = None


class MemoryStore:
    """Provides memory storage and retrieval backed by SQLite + FTS5."""

    MEMORY_PATTERNS = [
        re.compile(r"remember that\s+(?P<memory>.+?)(?:\.|$)", re.IGNORECASE),
        re.compile(r"don't forget\s+(?P<memory>.+?)(?:\.|$)", re.IGNORECASE),
        re.compile(r"keep in mind\s+(?P<memory>.+?)(?:\.|$)", re.IGNORECASE),
        re.compile(r"note that\s+(?P<memory>.+?)(?:\.|$)", re.IGNORECASE),
    ]

    def __init__(self, pool: Optional[SQLiteConnectionPool] = None) -> None:
        if pool is None:
            pool = get_pool(str(settings.sqlite_path), max_size=2)
        self.pool = pool

    @with_retry(max_attempts=3, retry_exceptions=(sqlite3.Error,), raise_last_exception=True)
    def add_memory(
        self,
        content: str,
        category: Optional[str] = None,
        tags: Optional[str] = None,
        source: Optional[str] = None,
        vault_id: Optional[int] = None,
    ) -> MemoryRecord:
        if not content or not content.strip():
            raise MemoryStoreError("Memory content cannot be empty")

        sql = """
        INSERT INTO memories (content, category, tags, source, vault_id)
        VALUES (?, ?, ?, ?, ?)
        """
        conn = self.pool.get_connection()
        try:
            cursor = conn.execute(sql, (content, category, tags, source, vault_id))
            conn.commit()
            memory_id = cursor.lastrowid
            if memory_id is None:
                raise MemoryStoreError("Failed to insert memory")
            # Fetch created_at, updated_at, and vault_id for the inserted row
            cursor = conn.execute(
                "SELECT created_at, updated_at, vault_id FROM memories WHERE id = ?", (memory_id,)
            )
            row = cursor.fetchone()
            created_at = row[0] if row else None
            updated_at = row[1] if row else None
            retrieved_vault_id = row[2] if row else None
        finally:
            self.pool.release_connection(conn)

        return MemoryRecord(
            id=memory_id,
            content=content,
            category=category,
            tags=tags,
            source=source,
            vault_id=retrieved_vault_id,
            created_at=created_at,
            updated_at=updated_at,
        )

    @with_retry(max_attempts=3, retry_exceptions=(sqlite3.Error,), raise_last_exception=True)
    def search_memories(self, query: str, limit: int = 5, vault_id: Optional[int] = None) -> List[MemoryRecord]:
        if not query or not query.strip():
            return []

        # Strip FTS5 special operators but preserve technical chars (+, ., -, #, @)
        sanitized_query = re.sub(r'["\'^*(){}[\]|&~<>]', ' ', query)
        sanitized_query = ' '.join(sanitized_query.split())

        if not sanitized_query.strip():
            return []

        conn = self.pool.get_connection()
        try:
            try:
                # Build SQL query based on vault_id parameter
                if vault_id is None:
                    # No vault filter - return all memories (backward compatible)
                    sql = """
                    SELECT m.id, m.content, m.category, m.tags, m.source, m.vault_id, m.created_at, m.updated_at, f.rank
                    FROM memories_fts f
                    JOIN memories m ON f.rowid = m.id
                    WHERE memories_fts MATCH ?
                    ORDER BY rank
                    LIMIT ?
                    """
                    params = (sanitized_query, limit)
                else:
                    # Filter to vault-scoped + global memories
                    sql = """
                    SELECT m.id, m.content, m.category, m.tags, m.source, m.vault_id, m.created_at, m.updated_at, f.rank
                    FROM memories_fts f
                    JOIN memories m ON f.rowid = m.id
                    WHERE memories_fts MATCH ?
                    AND (m.vault_id = ? OR m.vault_id IS NULL)
                    ORDER BY rank
                    LIMIT ?
                    """
                    params = (sanitized_query, vault_id, limit)

                cursor = conn.execute(sql, params)
                rows = cursor.fetchall()
            except sqlite3.Error as e:
                raise MemoryStoreError(f"FTS query failed: {e}")
        finally:
            self.pool.release_connection(conn)

        records: List[MemoryRecord] = []
        for row in rows:
            record = MemoryRecord(
                id=row[0],
                content=row[1],
                category=row[2],
                tags=row[3],
                source=row[4],
                vault_id=row[5],
                created_at=row[6],
                updated_at=row[7],
            )
            # Attach score as an attribute (not part of dataclass but accessible)
            record.score = row[8]
            records.append(record)
        return records

    def detect_memory_intent(self, text: str) -> Optional[str]:
        if not text or not text.strip():
            return None

        for pattern in self.MEMORY_PATTERNS:
            match = pattern.search(text)
            if match and match.groupdict().get("memory"):
                memory_content = match.group("memory").strip()
                if memory_content:
                    return memory_content
        return None



