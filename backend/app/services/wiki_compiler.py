"""
WikiCompiler: Deterministic entity/acronym/relation extraction and memory promotion.

All extraction is regex-based. No LLM required.
Pronoun resolution: maintains current_org_context from most recently seen acronym/org entity.
"""

import json
import logging
import re
import sqlite3
from datetime import datetime
from typing import Optional

from app.services.wiki_store import WikiStore, normalize_slug

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# "ACRONYM stands for Full Name" — e.g., "AFOMIS stands for Air Force..."
_ACRONYM_RE = re.compile(
    r"([A-Z][A-Z0-9]{1,})\s+stands\s+for\s+([A-Za-z][^.;!?\n]{3,})",
    re.IGNORECASE,
)

# "[Person] is the [ORG] [Role]" — e.g., "Justice Sakyi is the AFOMIS Chief"
# Group 2 is uppercase-only (acronym) so greedy matching can't bleed into adjacent clauses.
# No IGNORECASE: "is" and "the" are always lowercase in prose; role keywords keep exact case.
_ROLE_RE = re.compile(
    r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+is\s+(?:the\s+)?([A-Z]{2,})\s+"
    r"(Chief|Deputy|Director|Lead|Head|Manager|Officer|Coordinator|Supervisor|Chair|President|VP|Secretary|Administrator|Analyst|Specialist|Engineer)",
)

# "[Person] is [his/her/their/its] [Role]" — pronoun-subject pattern
# "Major Justin Woods is his deputy"
_PRONOUN_ROLE_RE = re.compile(
    r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\s+is\s+(?:his|her|their|its)\s+([A-Za-z]+(?:\s+[A-Za-z]+)?)",
    re.IGNORECASE,
)

# "[Person] is [Org]'s [Role]" — possessive org pattern
_ORG_POSSESSIVE_RE = re.compile(
    r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+is\s+([A-Z][A-Z0-9]{1,})'s\s+([A-Za-z]+(?:\s+[A-Za-z]+)?)",
    re.IGNORECASE,
)

# Pronouns that indicate subject coreference — skip as standalone subjects
_PRONOUN_SUBJECT_RE = re.compile(r"^(?:he|she|they|it|his|her|their|its)\b", re.IGNORECASE)

# Title prefixes to normalize person names
_TITLE_PREFIXES = re.compile(
    r"^(?:Major|Colonel|Captain|General|Dr\.?|Mr\.?|Ms\.?|Mrs\.?|Lt\.?|Sgt\.?|Cpl\.?)\s+",
    re.IGNORECASE,
)


def _strip_title(name: str) -> str:
    return _TITLE_PREFIXES.sub("", name).strip()


def _extract_name_with_title(raw: str) -> str:
    """Return name with title preserved for display."""
    return raw.strip()


# ---------------------------------------------------------------------------
# Extraction result types
# ---------------------------------------------------------------------------

class ExtractionResult:
    def __init__(self):
        self.acronyms: list[dict] = []      # {acronym, full_name}
        self.persons: list[str] = []         # canonical names
        self.role_claims: list[dict] = []    # {subject, predicate, object_org, sentence}
        self.sentences_skipped: list[str] = []


def extract_entities_from_text(text: str) -> ExtractionResult:
    """
    Deterministically extract entities, acronyms, and role relations from text.

    Pronoun handling:
    - Tracks current_org_context (most recently extracted acronym entity).
    - When a pronoun-subject sentence is detected, uses current_org_context as
      the implied org if available.
    - Uses finditer for ROLE_RE and PRONOUN_ROLE_RE so compound sentences with
      multiple clauses (joined by "and") are handled correctly.
    """
    result = ExtractionResult()
    current_org_context: Optional[str] = None
    # (subject, predicate, object_person) tuples to avoid duplicates
    _seen: set[tuple] = set()

    sentences = re.split(r"(?<=[.!?])\s+", text.strip())

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        # 1. Acronym extraction: "X stands for Y"
        acronym_match = _ACRONYM_RE.search(sentence)
        if acronym_match:
            acronym = acronym_match.group(1).upper()
            full_name = acronym_match.group(2).strip().rstrip(".")
            result.acronyms.append({"acronym": acronym, "full_name": full_name})
            current_org_context = acronym
            logger.debug("Extracted acronym: %s = %s", acronym, full_name)
            # Continue: acronym sentences rarely contain role patterns.
            continue

        # 2. Org possessive: "Person is ORG's Role" — finditer for all matches
        for poss_match in _ORG_POSSESSIVE_RE.finditer(sentence):
            person = _extract_name_with_title(poss_match.group(1))
            org = poss_match.group(2).upper()
            role = poss_match.group(3).strip().lower()
            key = (org, role, person)
            if key not in _seen:
                _seen.add(key)
                result.persons.append(person)
                result.role_claims.append({
                    "subject": org, "predicate": role,
                    "object_person": person, "sentence": sentence,
                })
                logger.debug("Extracted possessive role: %s -[%s]-> %s", org, role, person)

        # 3. Explicit role with org acronym: "[Person] is the [ORG] [Role]"
        # Uses finditer so multiple role clauses in one sentence are all captured.
        for role_match in _ROLE_RE.finditer(sentence):
            person = _extract_name_with_title(role_match.group(1))
            org = role_match.group(2).strip()  # already uppercase-only by regex
            role = role_match.group(3).strip().lower()
            key = (org, role, person)
            if key not in _seen:
                _seen.add(key)
                result.persons.append(person)
                result.role_claims.append({
                    "subject": org, "predicate": role,
                    "object_person": person, "sentence": sentence,
                })
                logger.debug("Extracted role: %s -[%s]-> %s", org, role, person)

        # 4. Pronoun-subject role: "[Person] is his/her/their [Role]"
        # Also uses finditer; dedup prevents double-counting overlap with ROLE_RE.
        for pronoun_match in _PRONOUN_ROLE_RE.finditer(sentence):
            person = _extract_name_with_title(pronoun_match.group(1))
            role = pronoun_match.group(2).strip().lower()
            if current_org_context:
                key = (current_org_context, role, person)
                if key not in _seen:
                    _seen.add(key)
                    result.persons.append(person)
                    result.role_claims.append({
                        "subject": current_org_context, "predicate": role,
                        "object_person": person, "sentence": sentence,
                    })
                    logger.debug(
                        "Pronoun resolved via org_context=%s: %s -[%s]-> %s",
                        current_org_context, current_org_context, role, person,
                    )
            else:
                result.sentences_skipped.append(sentence)
                logger.debug("Skipped pronoun sentence (no org context): %s", sentence)

    return result


# ---------------------------------------------------------------------------
# WikiCompiler
# ---------------------------------------------------------------------------

class WikiCompiler:
    """
    Orchestrates deterministic extraction and wiki page/claim/entity creation.

    Instantiate per-request: WikiCompiler(db) or WikiCompiler(db, wiki_store).
    """

    def __init__(self, db: sqlite3.Connection, store: Optional[WikiStore] = None) -> None:
        self._db = db
        self._store = store or WikiStore(db)

    def promote_memory(
        self,
        memory_id: int,
        vault_id: int,
        page_type: Optional[str] = None,
        target_page_id: Optional[int] = None,
        status: str = "needs_review",
        created_by: Optional[int] = None,
    ) -> dict:
        """
        Promote a memory record into wiki pages, entities, claims, and relations.

        Returns dict with keys: page, claims, entities, relations.
        """
        # Load memory — FK verify vault scope
        self._db.row_factory = sqlite3.Row
        row = self._db.execute("SELECT * FROM memories WHERE id = ?", (memory_id,)).fetchone()
        if not row:
            raise ValueError(f"Memory {memory_id} not found")

        memory = dict(row)
        memory_vault_id = memory.get("vault_id")

        # Vault scope enforcement
        if memory_vault_id is not None and memory_vault_id != vault_id:
            raise PermissionError(
                f"Memory {memory_id} belongs to vault {memory_vault_id}, not {vault_id}"
            )

        content: str = memory["content"]
        extraction = extract_entities_from_text(content)

        entities_created: list = []
        claims_created: list = []
        relations_created: list = []

        # Determine primary acronym for page slug
        primary_acronym = extraction.acronyms[0]["acronym"] if extraction.acronyms else None
        inferred_page_type = page_type or ("acronym" if primary_acronym else "entity")

        # Determine or create page
        if target_page_id:
            page = self._store.get_page(target_page_id)
            if not page or page.vault_id != vault_id:
                raise ValueError(f"Target page {target_page_id} not found in vault {vault_id}")
        else:
            if primary_acronym:
                slug = normalize_slug(f"acronym/{primary_acronym.lower()}")
                title = primary_acronym
            else:
                slug = normalize_slug(content[:60])
                title = content[:80].strip()
            # Check for existing page with same slug
            existing_row = self._db.execute(
                "SELECT id FROM wiki_pages WHERE vault_id = ? AND slug = ?", (vault_id, slug)
            ).fetchone()
            if existing_row:
                page = self._store.get_page(existing_row[0], load_relations=False)
            else:
                page = self._store.create_page(
                    vault_id=vault_id,
                    title=title,
                    page_type=inferred_page_type,
                    slug=slug,
                    markdown=content,
                    status=status,
                    created_by=created_by,
                )

        page_id = page.id  # type: ignore[union-attr]

        # Create/upsert acronym entities
        for acronym_info in extraction.acronyms:
            entity = self._store.upsert_entity(
                vault_id=vault_id,
                canonical_name=acronym_info["acronym"],
                entity_type="acronym",
                aliases=[acronym_info["full_name"]],
                page_id=page_id,
            )
            entities_created.append(entity)

        # Create person entities
        seen_persons: set[str] = set()
        person_entity_map: dict[str, int] = {}
        for person_name in extraction.persons:
            if person_name in seen_persons:
                continue
            seen_persons.add(person_name)
            entity = self._store.upsert_entity(
                vault_id=vault_id,
                canonical_name=person_name,
                entity_type="person",
            )
            entities_created.append(entity)
            person_entity_map[person_name] = entity.id

        # Build entity id map for relations
        entity_id_map: dict[str, int] = {}
        for e in entities_created:
            entity_id_map[e.canonical_name] = e.id

        # Create claims and relations from role_claims
        for role_claim in extraction.role_claims:
            subj_name = role_claim["subject"]
            pred = role_claim["predicate"]
            obj_name = role_claim["object_person"]
            sentence = role_claim["sentence"]

            claim_text = sentence
            claim = self._store.create_claim(
                vault_id=vault_id,
                claim_text=claim_text,
                source_type="memory",
                page_id=page_id,
                claim_type="fact",
                subject=subj_name,
                predicate=pred,
                object=obj_name,
                status="active",
                confidence=0.8,
                created_by=created_by,
            )
            # Attach provenance source
            self._store.attach_source(
                claim_id=claim.id,
                source_kind="memory",
                memory_id=memory_id,
                source_label=f"memory:{memory_id}",
                quote=content,
                confidence=0.8,
            )
            self._db.commit()
            claims_created.append(self._store.get_claim(claim.id))

            # Create relation if both entities are known
            subj_id = entity_id_map.get(subj_name)
            obj_id = entity_id_map.get(obj_name)
            relation = self._store.create_relation(
                vault_id=vault_id,
                predicate=pred,
                subject_entity_id=subj_id,
                object_entity_id=obj_id,
                object_text=obj_name if not obj_id else None,
                claim_id=claim.id,
                confidence=0.8,
            )
            relations_created.append(relation)

        # Reload page with all relations
        page = self._store.get_page(page_id)

        return {
            "page": page,
            "claims": claims_created,
            "entities": entities_created,
            "relations": relations_created,
        }

    def compile_query_job(self, vault_id: int, input_json: dict) -> dict:
        """
        Extract entities/claims from an assistant answer and persist to wiki.

        A claim is 'active' when the answer had citations; 'unverified' when not.
        Creates a 'unsupported_claim' lint finding for every unverified claim.
        """
        assistant_answer: str = input_json.get("assistant_answer") or ""
        wiki_refs: list = input_json.get("wiki_refs") or []
        doc_sources: list = input_json.get("doc_sources") or []
        memories: list = input_json.get("memories") or []

        if not assistant_answer:
            return {"page": None, "claims": [], "entities": [], "relations": [], "skipped": True}

        extraction = extract_entities_from_text(assistant_answer)
        if not extraction.acronyms and not extraction.role_claims:
            return {"page": None, "claims": [], "entities": [], "relations": [], "skipped": True}

        has_citations = bool(wiki_refs or doc_sources or memories)
        claim_status = "active" if has_citations else "unverified"
        confidence = 0.8 if has_citations else 0.5

        entities_created: list = []
        claims_created: list = []
        relations_created: list = []

        for acronym_info in extraction.acronyms:
            entity = self._store.upsert_entity(
                vault_id=vault_id,
                canonical_name=acronym_info["acronym"],
                entity_type="acronym",
                aliases=[acronym_info["full_name"]],
            )
            entities_created.append(entity)

        seen_persons: set[str] = set()
        for person_name in extraction.persons:
            if person_name in seen_persons:
                continue
            seen_persons.add(person_name)
            entity = self._store.upsert_entity(
                vault_id=vault_id,
                canonical_name=person_name,
                entity_type="person",
            )
            entities_created.append(entity)

        entity_id_map: dict[str, int] = {e.canonical_name: e.id for e in entities_created}
        now = datetime.utcnow().isoformat()

        for role_claim in extraction.role_claims:
            subj_name = role_claim["subject"]
            pred = role_claim["predicate"]
            obj_name = role_claim["object_person"]
            sentence = role_claim["sentence"]

            claim = self._store.create_claim(
                vault_id=vault_id,
                claim_text=sentence,
                source_type="chat_synthesis",
                claim_type="fact",
                subject=subj_name,
                predicate=pred,
                object=obj_name,
                status=claim_status,
                confidence=confidence,
            )

            for ref in wiki_refs:
                if ref.get("wiki_label"):
                    self._store.attach_source(
                        claim_id=claim.id,
                        source_kind="manual",
                        source_label=ref["wiki_label"],
                        quote=sentence,
                        confidence=confidence,
                    )
            for src in doc_sources:
                if src.get("source_label"):
                    self._store.attach_source(
                        claim_id=claim.id,
                        source_kind="document",
                        file_id=src.get("file_id"),
                        chunk_id=src.get("chunk_id"),
                        source_label=src["source_label"],
                        quote=sentence,
                        confidence=confidence,
                    )
            for mem in memories:
                if isinstance(mem, dict) and mem.get("memory_label"):
                    self._store.attach_source(
                        claim_id=claim.id,
                        source_kind="memory",
                        memory_id=mem.get("memory_id"),
                        source_label=mem["memory_label"],
                        quote=sentence,
                        confidence=confidence,
                    )

            self._db.commit()
            claims_created.append(self._store.get_claim(claim.id))

            if claim_status == "unverified":
                self._db.execute(
                    """INSERT INTO wiki_lint_findings
                       (vault_id, finding_type, severity, title, details,
                        related_page_ids_json, related_claim_ids_json, status, created_at, updated_at)
                       VALUES (?, 'unsupported_claim', 'low', ?, ?, '[]', ?, 'open', ?, ?)""",
                    (
                        vault_id,
                        "Unverified claim: extracted from query answer with no citations",
                        sentence[:200],
                        json.dumps([claim.id]),
                        now, now,
                    ),
                )
                self._db.commit()

            subj_id = entity_id_map.get(subj_name)
            obj_id = entity_id_map.get(obj_name)
            self._store.create_relation(
                vault_id=vault_id,
                predicate=pred,
                subject_entity_id=subj_id,
                object_entity_id=obj_id,
                object_text=obj_name if not obj_id else None,
                claim_id=claim.id,
                confidence=confidence,
            )

        return {
            "page": None,
            "claims": [{"id": c.id, "status": c.status} for c in claims_created],
            "entities": [{"id": e.id, "name": e.canonical_name} for e in entities_created],
            "relations_count": len(relations_created),
        }

    def compile_ingest_job(self, vault_id: int, input_json: dict) -> dict:
        """
        Extract entities/claims from a document and persist to wiki.

        input_json must contain 'file_id'. If 'text' is present it is used
        directly; otherwise the method reads from the file path recorded in
        the files table.
        """
        file_id: Optional[int] = input_json.get("file_id")
        if not file_id:
            return {"page": None, "claims": [], "entities": [], "relations_count": 0, "skipped": True}

        self._db.row_factory = sqlite3.Row
        file_row = self._db.execute(
            "SELECT * FROM files WHERE id = ? AND vault_id = ?", (file_id, vault_id)
        ).fetchone()
        if not file_row:
            raise ValueError(f"File {file_id} not found in vault {vault_id}")

        file_data = dict(file_row)
        text: str = input_json.get("text") or ""

        if not text and file_data.get("file_path"):
            try:
                with open(file_data["file_path"], "r", encoding="utf-8", errors="ignore") as fh:
                    text = fh.read(50_000)
            except OSError:
                logger.warning(
                    "compile_ingest_job: cannot read file %s, skipping", file_data["file_path"]
                )

        if not text:
            return {"page": None, "claims": [], "entities": [], "relations_count": 0, "skipped": True}

        extraction = extract_entities_from_text(text)
        if not extraction.acronyms and not extraction.role_claims:
            return {"page": None, "claims": [], "entities": [], "relations_count": 0, "skipped": True}

        file_name = file_data.get("file_name") or f"file:{file_id}"
        slug = normalize_slug(f"document/{file_name[:60]}")
        title = file_name

        existing = self._db.execute(
            "SELECT id FROM wiki_pages WHERE vault_id = ? AND slug = ?", (vault_id, slug)
        ).fetchone()
        if existing:
            page = self._store.get_page(existing[0], load_relations=False)
        else:
            page = self._store.create_page(
                vault_id=vault_id,
                title=title,
                page_type="entity",
                slug=slug,
                markdown=text[:2000],
                status="needs_review",
            )

        page_id = page.id  # type: ignore[union-attr]

        entities_created: list = []
        claims_created: list = []
        relations_count = 0

        for acronym_info in extraction.acronyms:
            entity = self._store.upsert_entity(
                vault_id=vault_id,
                canonical_name=acronym_info["acronym"],
                entity_type="acronym",
                aliases=[acronym_info["full_name"]],
                page_id=page_id,
            )
            entities_created.append(entity)

        seen_persons: set[str] = set()
        for person_name in extraction.persons:
            if person_name in seen_persons:
                continue
            seen_persons.add(person_name)
            entity = self._store.upsert_entity(
                vault_id=vault_id,
                canonical_name=person_name,
                entity_type="person",
            )
            entities_created.append(entity)

        entity_id_map: dict[str, int] = {e.canonical_name: e.id for e in entities_created}

        for role_claim in extraction.role_claims:
            subj_name = role_claim["subject"]
            pred = role_claim["predicate"]
            obj_name = role_claim["object_person"]
            sentence = role_claim["sentence"]

            claim = self._store.create_claim(
                vault_id=vault_id,
                claim_text=sentence,
                source_type="document",
                page_id=page_id,
                claim_type="fact",
                subject=subj_name,
                predicate=pred,
                object=obj_name,
                status="unverified",
                confidence=0.7,
            )
            self._store.attach_source(
                claim_id=claim.id,
                source_kind="document",
                file_id=file_id,
                source_label=f"file:{file_id}",
                quote=sentence,
                confidence=0.7,
            )
            self._db.commit()
            claims_created.append({"id": claim.id, "status": "needs_review"})

            subj_id = entity_id_map.get(subj_name)
            obj_id = entity_id_map.get(obj_name)
            self._store.create_relation(
                vault_id=vault_id,
                predicate=pred,
                subject_entity_id=subj_id,
                object_entity_id=obj_id,
                object_text=obj_name if not obj_id else None,
                claim_id=claim.id,
                confidence=0.7,
            )
            relations_count += 1

        page = self._store.get_page(page_id)
        return {
            "page": {"id": page_id, "slug": slug} if page else None,
            "claims": claims_created,
            "entities": [{"id": e.id, "name": e.canonical_name} for e in entities_created],
            "relations_count": relations_count,
        }
