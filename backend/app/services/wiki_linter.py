"""
WikiLinter: Detects quality issues in wiki content and writes wiki_lint_findings rows.

run_lint() clears all open findings for the vault before inserting new ones,
preventing ghost findings from accumulating across runs.
"""

import json
import logging
import sqlite3
from typing import Optional

from app.services.wiki_store import WikiStore

logger = logging.getLogger(__name__)


class WikiLinter:
    """Detects and records wiki quality issues for a vault."""

    def __init__(self, db: sqlite3.Connection, store: Optional[WikiStore] = None) -> None:
        self._db = db
        self._store = store or WikiStore(db)

    def run_lint(self, vault_id: int) -> list:
        """
        Run all lint checks for vault_id.

        Clears existing open findings first, then inserts fresh results.
        Returns list of created WikiLintFinding objects.
        """
        self._store.clear_open_findings(vault_id)

        findings = []
        findings += self._detect_unsupported_claims(vault_id)
        findings += self._detect_orphan_claims(vault_id)
        findings += self._detect_pages_without_claims(vault_id)
        findings += self._detect_duplicate_entity_aliases(vault_id)
        findings += self._detect_conflicting_claims(vault_id)
        return findings

    def _detect_unsupported_claims(self, vault_id: int) -> list:
        """Claims with no entries in wiki_claim_sources."""
        rows = self._db.execute(
            """
            SELECT c.id, c.claim_text, c.page_id
            FROM wiki_claims c
            LEFT JOIN wiki_claim_sources cs ON cs.claim_id = c.id
            WHERE c.vault_id = ? AND cs.id IS NULL AND c.status != 'archived'
            """,
            (vault_id,),
        ).fetchall()
        findings = []
        for row in rows:
            claim_id, claim_text, page_id = row[0], row[1], row[2]
            f = self._store.create_lint_finding(
                vault_id=vault_id,
                finding_type="unsupported_claim",
                severity="high",
                title=f"Unsupported claim: {claim_text[:80]}",
                details=f"Claim id={claim_id} has no provenance sources.",
                related_page_ids=[page_id] if page_id else [],
                related_claim_ids=[claim_id],
            )
            findings.append(f)
        return findings

    def _detect_orphan_claims(self, vault_id: int) -> list:
        """Claims where page_id is NULL (orphaned when page was deleted)."""
        rows = self._db.execute(
            """
            SELECT id, claim_text FROM wiki_claims
            WHERE vault_id = ? AND page_id IS NULL AND status != 'archived'
            """,
            (vault_id,),
        ).fetchall()
        findings = []
        for row in rows:
            claim_id, claim_text = row[0], row[1]
            f = self._store.create_lint_finding(
                vault_id=vault_id,
                finding_type="orphan",
                severity="medium",
                title=f"Orphan claim: {claim_text[:80]}",
                details=f"Claim id={claim_id} has no parent page (page was deleted).",
                related_claim_ids=[claim_id],
            )
            findings.append(f)
        return findings

    def _detect_pages_without_claims(self, vault_id: int) -> list:
        """Pages with zero claims."""
        rows = self._db.execute(
            """
            SELECT p.id, p.title FROM wiki_pages p
            LEFT JOIN wiki_claims c ON c.page_id = p.id AND c.status != 'archived'
            WHERE p.vault_id = ? AND c.id IS NULL AND p.status != 'archived'
            """,
            (vault_id,),
        ).fetchall()
        findings = []
        for row in rows:
            page_id, title = row[0], row[1]
            f = self._store.create_lint_finding(
                vault_id=vault_id,
                finding_type="missing_page",
                severity="low",
                title=f"Page without claims: {title}",
                details=f"Page id={page_id} '{title}' has no associated claims.",
                related_page_ids=[page_id],
            )
            findings.append(f)
        return findings

    def _detect_duplicate_entity_aliases(self, vault_id: int) -> list:
        """Two different entities in the same vault share an alias value."""
        rows = self._db.execute(
            "SELECT id, canonical_name, aliases_json FROM wiki_entities WHERE vault_id = ?",
            (vault_id,),
        ).fetchall()

        alias_to_entities: dict[str, list[int]] = {}
        for row in rows:
            entity_id = row[0]
            try:
                aliases = json.loads(row[2] or "[]")
            except (json.JSONDecodeError, TypeError):
                aliases = []
            for alias in aliases:
                key = alias.strip().lower()
                if key:
                    alias_to_entities.setdefault(key, []).append(entity_id)

        findings = []
        for alias, entity_ids in alias_to_entities.items():
            if len(entity_ids) > 1:
                f = self._store.create_lint_finding(
                    vault_id=vault_id,
                    finding_type="duplicate_entity",
                    severity="medium",
                    title=f"Duplicate alias: '{alias}'",
                    details=f"Alias '{alias}' appears in entities: {entity_ids}",
                )
                findings.append(f)
        return findings

    def _detect_conflicting_claims(self, vault_id: int) -> list:
        """Same subject+predicate pair has different object values."""
        rows = self._db.execute(
            """
            SELECT subject, predicate, COUNT(DISTINCT object) as cnt, GROUP_CONCAT(id) as ids
            FROM wiki_claims
            WHERE vault_id = ? AND subject IS NOT NULL AND predicate IS NOT NULL
              AND object IS NOT NULL AND status = 'active'
            GROUP BY subject, predicate
            HAVING cnt > 1
            """,
            (vault_id,),
        ).fetchall()
        findings = []
        for row in rows:
            subject, predicate, _, ids_str = row[0], row[1], row[2], row[3]
            claim_ids = [int(i) for i in ids_str.split(",") if i]
            f = self._store.create_lint_finding(
                vault_id=vault_id,
                finding_type="contradiction",
                severity="high",
                title=f"Conflicting claims: {subject} — {predicate}",
                details=f"Multiple objects for subject='{subject}' predicate='{predicate}'. Claim ids: {claim_ids}",
                related_claim_ids=claim_ids,
            )
            findings.append(f)
        return findings
