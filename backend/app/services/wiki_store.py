"""
WikiStore: CRUD operations for all wiki / Knowledge Compiler tables.

All operations are vault-scoped. Slug normalization is enforced on create/update.
FTS search is backed by wiki_pages_fts, wiki_claims_fts, wiki_entities_fts.
"""

import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

# ---------------------------------------------------------------------------
# DTO dataclasses
# ---------------------------------------------------------------------------

@dataclass
class WikiPage:
    id: int
    vault_id: int
    slug: str
    title: str
    page_type: str
    markdown: str
    summary: str
    status: str
    confidence: float
    created_by: Optional[int]
    created_at: str
    updated_at: str
    last_compiled_at: Optional[str]
    claims: list = field(default_factory=list)
    entities: list = field(default_factory=list)
    lint_findings: list = field(default_factory=list)


@dataclass
class WikiClaimSource:
    id: int
    claim_id: int
    source_kind: str
    file_id: Optional[int]
    chunk_id: Optional[str]
    memory_id: Optional[int]
    chat_message_id: Optional[int]
    source_label: Optional[str]
    quote: Optional[str]
    char_start: Optional[int]
    char_end: Optional[int]
    page_number: Optional[int]
    confidence: float
    created_at: str


@dataclass
class WikiClaim:
    id: int
    vault_id: int
    page_id: Optional[int]
    claim_text: str
    claim_type: str
    subject: Optional[str]
    predicate: Optional[str]
    object: Optional[str]
    source_type: str
    status: str
    confidence: float
    created_by: Optional[int]
    created_at: str
    updated_at: str
    sources: list = field(default_factory=list)


@dataclass
class WikiEntity:
    id: int
    vault_id: int
    canonical_name: str
    entity_type: str
    aliases_json: str
    description: str
    page_id: Optional[int]
    created_at: str
    updated_at: str

    @property
    def aliases(self) -> list:
        try:
            return json.loads(self.aliases_json)
        except (json.JSONDecodeError, TypeError):
            return []


@dataclass
class WikiRelation:
    id: int
    vault_id: int
    subject_entity_id: Optional[int]
    predicate: str
    object_entity_id: Optional[int]
    object_text: Optional[str]
    claim_id: Optional[int]
    confidence: float
    created_at: str


@dataclass
class WikiCompileJob:
    id: int
    vault_id: int
    trigger_type: str
    trigger_id: Optional[str]
    status: str
    error: Optional[str]
    result_json: str
    created_at: str
    started_at: Optional[str]
    completed_at: Optional[str]


@dataclass
class WikiLintFinding:
    id: int
    vault_id: int
    finding_type: str
    severity: str
    title: str
    details: str
    related_page_ids_json: str
    related_claim_ids_json: str
    status: str
    created_at: str
    updated_at: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def normalize_slug(text: str) -> str:
    """Lowercase, strip special chars, replace whitespace/underscores with hyphens."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text


def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


def _to_wiki_page(row: sqlite3.Row) -> WikiPage:
    d = _row_to_dict(row)
    return WikiPage(
        id=d["id"],
        vault_id=d["vault_id"],
        slug=d["slug"],
        title=d["title"],
        page_type=d["page_type"],
        markdown=d["markdown"],
        summary=d["summary"] or "",
        status=d["status"],
        confidence=d["confidence"] or 0.0,
        created_by=d.get("created_by"),
        created_at=d["created_at"],
        updated_at=d["updated_at"],
        last_compiled_at=d.get("last_compiled_at"),
    )


def _to_claim_source(row: sqlite3.Row) -> WikiClaimSource:
    d = _row_to_dict(row)
    return WikiClaimSource(
        id=d["id"],
        claim_id=d["claim_id"],
        source_kind=d["source_kind"],
        file_id=d.get("file_id"),
        chunk_id=d.get("chunk_id"),
        memory_id=d.get("memory_id"),
        chat_message_id=d.get("chat_message_id"),
        source_label=d.get("source_label"),
        quote=d.get("quote"),
        char_start=d.get("char_start"),
        char_end=d.get("char_end"),
        page_number=d.get("page_number"),
        confidence=d.get("confidence") or 0.0,
        created_at=d["created_at"],
    )


def _to_wiki_claim(row: sqlite3.Row) -> WikiClaim:
    d = _row_to_dict(row)
    return WikiClaim(
        id=d["id"],
        vault_id=d["vault_id"],
        page_id=d.get("page_id"),
        claim_text=d["claim_text"],
        claim_type=d.get("claim_type", "fact"),
        subject=d.get("subject"),
        predicate=d.get("predicate"),
        object=d.get("object"),
        source_type=d["source_type"],
        status=d["status"],
        confidence=d.get("confidence") or 0.0,
        created_by=d.get("created_by"),
        created_at=d["created_at"],
        updated_at=d["updated_at"],
    )


def _to_wiki_entity(row: sqlite3.Row) -> WikiEntity:
    d = _row_to_dict(row)
    return WikiEntity(
        id=d["id"],
        vault_id=d["vault_id"],
        canonical_name=d["canonical_name"],
        entity_type=d.get("entity_type", "unknown"),
        aliases_json=d.get("aliases_json") or "[]",
        description=d.get("description") or "",
        page_id=d.get("page_id"),
        created_at=d["created_at"],
        updated_at=d["updated_at"],
    )


def _to_wiki_relation(row: sqlite3.Row) -> WikiRelation:
    d = _row_to_dict(row)
    return WikiRelation(
        id=d["id"],
        vault_id=d["vault_id"],
        subject_entity_id=d.get("subject_entity_id"),
        predicate=d["predicate"],
        object_entity_id=d.get("object_entity_id"),
        object_text=d.get("object_text"),
        claim_id=d.get("claim_id"),
        confidence=d.get("confidence") or 0.0,
        created_at=d["created_at"],
    )


def _to_compile_job(row: sqlite3.Row) -> WikiCompileJob:
    d = _row_to_dict(row)
    return WikiCompileJob(
        id=d["id"],
        vault_id=d["vault_id"],
        trigger_type=d["trigger_type"],
        trigger_id=d.get("trigger_id"),
        status=d["status"],
        error=d.get("error"),
        result_json=d.get("result_json") or "{}",
        created_at=d["created_at"],
        started_at=d.get("started_at"),
        completed_at=d.get("completed_at"),
    )


def _to_lint_finding(row: sqlite3.Row) -> WikiLintFinding:
    d = _row_to_dict(row)
    return WikiLintFinding(
        id=d["id"],
        vault_id=d["vault_id"],
        finding_type=d["finding_type"],
        severity=d["severity"],
        title=d["title"],
        details=d.get("details") or "",
        related_page_ids_json=d.get("related_page_ids_json") or "[]",
        related_claim_ids_json=d.get("related_claim_ids_json") or "[]",
        status=d["status"],
        created_at=d["created_at"],
        updated_at=d["updated_at"],
    )


# ---------------------------------------------------------------------------
# WikiStore
# ---------------------------------------------------------------------------

class WikiStore:
    """Vault-scoped CRUD and FTS search for all wiki tables."""

    def __init__(self, db: sqlite3.Connection) -> None:
        self._db = db
        self._db.row_factory = sqlite3.Row

    # -----------------------------------------------------------------------
    # Pages
    # -----------------------------------------------------------------------

    def create_page(
        self,
        vault_id: int,
        title: str,
        page_type: str,
        slug: Optional[str] = None,
        markdown: str = "",
        summary: str = "",
        status: str = "draft",
        confidence: float = 0.0,
        created_by: Optional[int] = None,
    ) -> WikiPage:
        if not slug:
            slug = normalize_slug(title)
        else:
            slug = normalize_slug(slug)
        now = datetime.utcnow().isoformat()
        cur = self._db.execute(
            """
            INSERT INTO wiki_pages
                (vault_id, slug, title, page_type, markdown, summary, status, confidence, created_by, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (vault_id, slug, title, page_type, markdown, summary, status, confidence, created_by, now, now),
        )
        self._db.commit()
        return self.get_page(cur.lastrowid)  # type: ignore[arg-type]

    def get_page(self, page_id: int, load_relations: bool = True) -> Optional[WikiPage]:
        row = self._db.execute(
            "SELECT * FROM wiki_pages WHERE id = ?", (page_id,)
        ).fetchone()
        if not row:
            return None
        page = _to_wiki_page(row)
        if load_relations:
            page.claims = self.list_claims(page.vault_id, page_id=page_id)
            page.entities = self.list_entities(page.vault_id, page_id=page_id)
            page.lint_findings = self.list_lint_findings(page.vault_id, page_id=page_id)
        return page

    def list_pages(
        self,
        vault_id: int,
        page_type: Optional[str] = None,
        status: Optional[str] = None,
        search: Optional[str] = None,
        page: int = 1,
        per_page: int = 50,
    ) -> list[WikiPage]:
        offset = (page - 1) * per_page
        if search:
            ids = self._fts_page_ids(vault_id, search)
            if not ids:
                return []
            placeholders = ",".join("?" * len(ids))
            sql = f"SELECT * FROM wiki_pages WHERE id IN ({placeholders}) AND vault_id = ?"
            params: list[Any] = [*ids, vault_id]
            if page_type:
                sql += " AND page_type = ?"
                params.append(page_type)
            if status:
                sql += " AND status = ?"
                params.append(status)
            sql += " ORDER BY updated_at DESC LIMIT ? OFFSET ?"
            params += [per_page, offset]
            rows = self._db.execute(sql, params).fetchall()
        else:
            params = [vault_id]
            sql = "SELECT * FROM wiki_pages WHERE vault_id = ?"
            if page_type:
                sql += " AND page_type = ?"
                params.append(page_type)
            if status:
                sql += " AND status = ?"
                params.append(status)
            sql += " ORDER BY updated_at DESC LIMIT ? OFFSET ?"
            params += [per_page, offset]
            rows = self._db.execute(sql, params).fetchall()
        return [_to_wiki_page(r) for r in rows]

    def update_page(self, page_id: int, vault_id: int, **kwargs: Any) -> Optional[WikiPage]:
        allowed = {"title", "page_type", "markdown", "summary", "status", "confidence", "slug", "last_compiled_at"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return self.get_page(page_id)
        if "title" in updates and "slug" not in updates:
            updates["slug"] = normalize_slug(updates["title"])
        if "slug" in updates:
            updates["slug"] = normalize_slug(updates["slug"])
        updates["updated_at"] = datetime.utcnow().isoformat()
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [page_id, vault_id]
        self._db.execute(
            f"UPDATE wiki_pages SET {set_clause} WHERE id = ? AND vault_id = ?", values
        )
        self._db.commit()
        return self.get_page(page_id)

    def delete_page(self, page_id: int, vault_id: int) -> bool:
        cur = self._db.execute(
            "DELETE FROM wiki_pages WHERE id = ? AND vault_id = ?", (page_id, vault_id)
        )
        self._db.commit()
        return cur.rowcount > 0

    def _fts_page_ids(self, vault_id: int, query: str) -> list[int]:
        rows = self._db.execute(
            "SELECT rowid FROM wiki_pages_fts WHERE wiki_pages_fts MATCH ?", (query,)
        ).fetchall()
        return [r[0] for r in rows]

    # -----------------------------------------------------------------------
    # Entities
    # -----------------------------------------------------------------------

    def upsert_entity(
        self,
        vault_id: int,
        canonical_name: str,
        entity_type: str = "unknown",
        aliases: Optional[list] = None,
        description: str = "",
        page_id: Optional[int] = None,
    ) -> WikiEntity:
        now = datetime.utcnow().isoformat()
        aliases_json = json.dumps(aliases or [])
        existing = self._db.execute(
            "SELECT * FROM wiki_entities WHERE vault_id = ? AND canonical_name = ?",
            (vault_id, canonical_name),
        ).fetchone()
        if existing:
            existing_entity = _to_wiki_entity(existing)
            merged_aliases = list(set(existing_entity.aliases + (aliases or [])))
            merged_json = json.dumps(merged_aliases)
            new_page_id = page_id if page_id is not None else existing_entity.page_id
            new_desc = description or existing_entity.description
            self._db.execute(
                """UPDATE wiki_entities SET aliases_json = ?, description = ?, page_id = ?,
                   entity_type = ?, updated_at = ? WHERE id = ?""",
                (merged_json, new_desc, new_page_id, entity_type, now, existing_entity.id),
            )
            self._db.commit()
            row = self._db.execute("SELECT * FROM wiki_entities WHERE id = ?", (existing_entity.id,)).fetchone()
        else:
            cur = self._db.execute(
                """INSERT INTO wiki_entities
                   (vault_id, canonical_name, entity_type, aliases_json, description, page_id, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (vault_id, canonical_name, entity_type, aliases_json, description, page_id, now, now),
            )
            self._db.commit()
            row = self._db.execute("SELECT * FROM wiki_entities WHERE id = ?", (cur.lastrowid,)).fetchone()
        return _to_wiki_entity(row)

    def get_entity(self, entity_id: int) -> Optional[WikiEntity]:
        row = self._db.execute("SELECT * FROM wiki_entities WHERE id = ?", (entity_id,)).fetchone()
        return _to_wiki_entity(row) if row else None

    def list_entities(
        self,
        vault_id: int,
        search: Optional[str] = None,
        page_id: Optional[int] = None,
    ) -> list[WikiEntity]:
        if search:
            ids = self._fts_entity_ids(vault_id, search)
            if not ids:
                return []
            placeholders = ",".join("?" * len(ids))
            rows = self._db.execute(
                f"SELECT * FROM wiki_entities WHERE id IN ({placeholders}) AND vault_id = ?",
                [*ids, vault_id],
            ).fetchall()
        elif page_id is not None:
            rows = self._db.execute(
                "SELECT * FROM wiki_entities WHERE vault_id = ? AND page_id = ? ORDER BY canonical_name",
                (vault_id, page_id),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM wiki_entities WHERE vault_id = ? ORDER BY canonical_name",
                (vault_id,),
            ).fetchall()
        return [_to_wiki_entity(r) for r in rows]

    def _fts_entity_ids(self, vault_id: int, query: str) -> list[int]:
        rows = self._db.execute(
            "SELECT rowid FROM wiki_entities_fts WHERE wiki_entities_fts MATCH ?", (query,)
        ).fetchall()
        return [r[0] for r in rows]

    # -----------------------------------------------------------------------
    # Claims
    # -----------------------------------------------------------------------

    def create_claim(
        self,
        vault_id: int,
        claim_text: str,
        source_type: str,
        page_id: Optional[int] = None,
        claim_type: str = "fact",
        subject: Optional[str] = None,
        predicate: Optional[str] = None,
        object: Optional[str] = None,
        status: str = "active",
        confidence: float = 0.0,
        created_by: Optional[int] = None,
        sources: Optional[list] = None,
    ) -> WikiClaim:
        now = datetime.utcnow().isoformat()
        cur = self._db.execute(
            """INSERT INTO wiki_claims
               (vault_id, page_id, claim_text, claim_type, subject, predicate, object,
                source_type, status, confidence, created_by, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (vault_id, page_id, claim_text, claim_type, subject, predicate, object,
             source_type, status, confidence, created_by, now, now),
        )
        claim_id = cur.lastrowid
        if sources:
            for src in sources:
                self._attach_source(claim_id, src)  # type: ignore[arg-type]
        self._db.commit()
        return self.get_claim(claim_id)  # type: ignore[return-value]

    def get_claim(self, claim_id: int) -> Optional[WikiClaim]:
        row = self._db.execute("SELECT * FROM wiki_claims WHERE id = ?", (claim_id,)).fetchone()
        if not row:
            return None
        claim = _to_wiki_claim(row)
        claim.sources = self._load_sources(claim_id)
        return claim

    def list_claims(
        self,
        vault_id: int,
        page_id: Optional[int] = None,
        entity: Optional[str] = None,
        search: Optional[str] = None,
        status: Optional[str] = None,
    ) -> list[WikiClaim]:
        if search:
            ids = self._fts_claim_ids(vault_id, search)
            if not ids:
                return []
            placeholders = ",".join("?" * len(ids))
            sql = f"SELECT * FROM wiki_claims WHERE id IN ({placeholders}) AND vault_id = ?"
            params: list[Any] = [*ids, vault_id]
        else:
            sql = "SELECT * FROM wiki_claims WHERE vault_id = ?"
            params = [vault_id]
        if page_id is not None:
            sql += " AND page_id = ?"
            params.append(page_id)
        if entity:
            sql += " AND (subject = ? OR object = ?)"
            params += [entity, entity]
        if status:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY created_at DESC"
        rows = self._db.execute(sql, params).fetchall()
        claims = [_to_wiki_claim(r) for r in rows]
        for claim in claims:
            claim.sources = self._load_sources(claim.id)
        return claims

    def update_claim(self, claim_id: int, vault_id: int, **kwargs: Any) -> Optional[WikiClaim]:
        allowed = {"claim_text", "claim_type", "subject", "predicate", "object", "source_type", "status", "confidence", "page_id"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return self.get_claim(claim_id)
        updates["updated_at"] = datetime.utcnow().isoformat()
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [claim_id, vault_id]
        self._db.execute(
            f"UPDATE wiki_claims SET {set_clause} WHERE id = ? AND vault_id = ?", values
        )
        self._db.commit()
        return self.get_claim(claim_id)

    def delete_claim(self, claim_id: int, vault_id: int) -> bool:
        cur = self._db.execute(
            "DELETE FROM wiki_claims WHERE id = ? AND vault_id = ?", (claim_id, vault_id)
        )
        self._db.commit()
        return cur.rowcount > 0

    def attach_source(
        self,
        claim_id: int,
        source_kind: str,
        file_id: Optional[int] = None,
        chunk_id: Optional[str] = None,
        memory_id: Optional[int] = None,
        chat_message_id: Optional[int] = None,
        source_label: Optional[str] = None,
        quote: Optional[str] = None,
        char_start: Optional[int] = None,
        char_end: Optional[int] = None,
        page_number: Optional[int] = None,
        confidence: float = 0.0,
    ) -> WikiClaimSource:
        src = {
            "source_kind": source_kind,
            "file_id": file_id,
            "chunk_id": chunk_id,
            "memory_id": memory_id,
            "chat_message_id": chat_message_id,
            "source_label": source_label,
            "quote": quote,
            "char_start": char_start,
            "char_end": char_end,
            "page_number": page_number,
            "confidence": confidence,
        }
        return self._attach_source(claim_id, src)

    def _attach_source(self, claim_id: int, src: dict) -> WikiClaimSource:
        now = datetime.utcnow().isoformat()
        cur = self._db.execute(
            """INSERT INTO wiki_claim_sources
               (claim_id, source_kind, file_id, chunk_id, memory_id, chat_message_id,
                source_label, quote, char_start, char_end, page_number, confidence, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (claim_id,
             src.get("source_kind"), src.get("file_id"), src.get("chunk_id"),
             src.get("memory_id"), src.get("chat_message_id"), src.get("source_label"),
             src.get("quote"), src.get("char_start"), src.get("char_end"),
             src.get("page_number"), src.get("confidence", 0.0), now),
        )
        row = self._db.execute("SELECT * FROM wiki_claim_sources WHERE id = ?", (cur.lastrowid,)).fetchone()
        return _to_claim_source(row)

    def _load_sources(self, claim_id: int) -> list[WikiClaimSource]:
        rows = self._db.execute(
            "SELECT * FROM wiki_claim_sources WHERE claim_id = ? ORDER BY id", (claim_id,)
        ).fetchall()
        return [_to_claim_source(r) for r in rows]

    def _fts_claim_ids(self, vault_id: int, query: str) -> list[int]:
        rows = self._db.execute(
            "SELECT rowid FROM wiki_claims_fts WHERE wiki_claims_fts MATCH ?", (query,)
        ).fetchall()
        return [r[0] for r in rows]

    # -----------------------------------------------------------------------
    # Relations
    # -----------------------------------------------------------------------

    def create_relation(
        self,
        vault_id: int,
        predicate: str,
        subject_entity_id: Optional[int] = None,
        object_entity_id: Optional[int] = None,
        object_text: Optional[str] = None,
        claim_id: Optional[int] = None,
        confidence: float = 0.0,
    ) -> WikiRelation:
        now = datetime.utcnow().isoformat()
        cur = self._db.execute(
            """INSERT INTO wiki_relations
               (vault_id, subject_entity_id, predicate, object_entity_id, object_text, claim_id, confidence, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (vault_id, subject_entity_id, predicate, object_entity_id, object_text, claim_id, confidence, now),
        )
        self._db.commit()
        row = self._db.execute("SELECT * FROM wiki_relations WHERE id = ?", (cur.lastrowid,)).fetchone()
        return _to_wiki_relation(row)

    def list_relations(self, vault_id: int, entity_id: Optional[int] = None) -> list[WikiRelation]:
        if entity_id is not None:
            rows = self._db.execute(
                "SELECT * FROM wiki_relations WHERE vault_id = ? AND (subject_entity_id = ? OR object_entity_id = ?)",
                (vault_id, entity_id, entity_id),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM wiki_relations WHERE vault_id = ?", (vault_id,)
            ).fetchall()
        return [_to_wiki_relation(r) for r in rows]

    # -----------------------------------------------------------------------
    # Compile Jobs
    # -----------------------------------------------------------------------

    def create_job(
        self,
        vault_id: int,
        trigger_type: str,
        trigger_id: Optional[str] = None,
    ) -> WikiCompileJob:
        now = datetime.utcnow().isoformat()
        cur = self._db.execute(
            """INSERT INTO wiki_compile_jobs (vault_id, trigger_type, trigger_id, status, created_at)
               VALUES (?, ?, ?, 'pending', ?)""",
            (vault_id, trigger_type, trigger_id, now),
        )
        self._db.commit()
        row = self._db.execute("SELECT * FROM wiki_compile_jobs WHERE id = ?", (cur.lastrowid,)).fetchone()
        return _to_compile_job(row)

    def list_jobs(self, vault_id: int, status: Optional[str] = None) -> list[WikiCompileJob]:
        if status:
            rows = self._db.execute(
                "SELECT * FROM wiki_compile_jobs WHERE vault_id = ? AND status = ? ORDER BY created_at DESC",
                (vault_id, status),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM wiki_compile_jobs WHERE vault_id = ? ORDER BY created_at DESC",
                (vault_id,),
            ).fetchall()
        return [_to_compile_job(r) for r in rows]

    # -----------------------------------------------------------------------
    # Lint Findings
    # -----------------------------------------------------------------------

    def create_lint_finding(
        self,
        vault_id: int,
        finding_type: str,
        title: str,
        severity: str = "medium",
        details: str = "",
        related_page_ids: Optional[list] = None,
        related_claim_ids: Optional[list] = None,
    ) -> WikiLintFinding:
        now = datetime.utcnow().isoformat()
        cur = self._db.execute(
            """INSERT INTO wiki_lint_findings
               (vault_id, finding_type, severity, title, details,
                related_page_ids_json, related_claim_ids_json, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?, ?)""",
            (vault_id, finding_type, severity, title, details,
             json.dumps(related_page_ids or []), json.dumps(related_claim_ids or []), now, now),
        )
        self._db.commit()
        row = self._db.execute("SELECT * FROM wiki_lint_findings WHERE id = ?", (cur.lastrowid,)).fetchone()
        return _to_lint_finding(row)

    def list_lint_findings(
        self,
        vault_id: int,
        status: Optional[str] = None,
        severity: Optional[str] = None,
        page_id: Optional[int] = None,
    ) -> list[WikiLintFinding]:
        sql = "SELECT * FROM wiki_lint_findings WHERE vault_id = ?"
        params: list[Any] = [vault_id]
        if status:
            sql += " AND status = ?"
            params.append(status)
        if severity:
            sql += " AND severity = ?"
            params.append(severity)
        if page_id is not None:
            # Use json_each to check membership — avoids LIKE false-positives where
            # page_id=1 would also match arrays containing 10, 11, 21, etc.
            sql += " AND EXISTS (SELECT 1 FROM json_each(related_page_ids_json) WHERE value = ?)"
            params.append(page_id)
        sql += " ORDER BY severity DESC, created_at DESC"
        rows = self._db.execute(sql, params).fetchall()
        return [_to_lint_finding(r) for r in rows]

    def clear_open_findings(self, vault_id: int) -> None:
        self._db.execute(
            "DELETE FROM wiki_lint_findings WHERE vault_id = ? AND status = 'open'", (vault_id,)
        )
        self._db.commit()

    # -----------------------------------------------------------------------
    # Global Search
    # -----------------------------------------------------------------------

    def search(
        self,
        vault_id: int,
        query: str,
        limit: int = 20,
    ) -> dict:
        page_ids = self._fts_page_ids(vault_id, query)
        claim_ids = self._fts_claim_ids(vault_id, query)
        entity_ids = self._fts_entity_ids(vault_id, query)

        pages = []
        if page_ids:
            ph = ",".join("?" * min(len(page_ids), limit))
            rows = self._db.execute(
                f"SELECT * FROM wiki_pages WHERE id IN ({ph}) AND vault_id = ? LIMIT ?",
                [*page_ids[:limit], vault_id, limit],
            ).fetchall()
            pages = [_to_wiki_page(r) for r in rows]

        claims = []
        if claim_ids:
            ph = ",".join("?" * min(len(claim_ids), limit))
            rows = self._db.execute(
                f"SELECT * FROM wiki_claims WHERE id IN ({ph}) AND vault_id = ? LIMIT ?",
                [*claim_ids[:limit], vault_id, limit],
            ).fetchall()
            claims = [_to_wiki_claim(r) for r in rows]

        entities = []
        if entity_ids:
            ph = ",".join("?" * min(len(entity_ids), limit))
            rows = self._db.execute(
                f"SELECT * FROM wiki_entities WHERE id IN ({ph}) AND vault_id = ? LIMIT ?",
                [*entity_ids[:limit], vault_id, limit],
            ).fetchall()
            entities = [_to_wiki_entity(r) for r in rows]

        return {"pages": pages, "claims": claims, "entities": entities, "query": query}
