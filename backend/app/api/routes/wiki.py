"""
Wiki / Knowledge Compiler API routes.

All endpoints are vault-scoped. Access follows vault access permissions.
"""

import logging
import sqlite3
from dataclasses import asdict
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.deps import evaluate_policy, get_current_active_user, get_db
from app.services.wiki_compiler import WikiCompiler
from app.services.wiki_linter import WikiLinter
from app.services.wiki_store import WikiStore

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _as_dict(obj) -> dict:
    try:
        return asdict(obj)
    except Exception:
        return obj if isinstance(obj, dict) else {}


def _page_dict(page) -> dict:
    if page is None:
        return {}
    d = _as_dict(page)
    d["claims"] = [_as_dict(c) for c in (page.claims or [])]
    d["entities"] = [_as_dict(e) for e in (page.entities or [])]
    d["lint_findings"] = [_as_dict(f) for f in (page.lint_findings or [])]
    return d


async def _require_vault_read(user: dict, vault_id: int) -> None:
    if not await evaluate_policy(user, "vault", vault_id, "read"):
        raise HTTPException(status_code=403, detail="No read access to this vault")


async def _require_vault_write(user: dict, vault_id: int) -> None:
    if not await evaluate_policy(user, "vault", vault_id, "write"):
        raise HTTPException(status_code=403, detail="No write access to this vault")


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class WikiPageCreateRequest(BaseModel):
    vault_id: int
    title: str = Field(..., min_length=1, max_length=500)
    page_type: str
    slug: Optional[str] = None
    markdown: str = ""
    summary: str = ""
    status: str = "draft"
    confidence: float = 0.0


class WikiPageUpdateRequest(BaseModel):
    title: Optional[str] = None
    page_type: Optional[str] = None
    slug: Optional[str] = None
    markdown: Optional[str] = None
    summary: Optional[str] = None
    status: Optional[str] = None
    confidence: Optional[float] = None


class WikiClaimCreateRequest(BaseModel):
    vault_id: int
    claim_text: str = Field(..., min_length=1, max_length=2000)
    source_type: str
    page_id: Optional[int] = None
    claim_type: str = "fact"
    subject: Optional[str] = None
    predicate: Optional[str] = None
    object: Optional[str] = None
    status: str = "active"
    confidence: float = 0.0


class WikiClaimUpdateRequest(BaseModel):
    claim_text: Optional[str] = None
    source_type: Optional[str] = None
    page_id: Optional[int] = None
    claim_type: Optional[str] = None
    subject: Optional[str] = None
    predicate: Optional[str] = None
    object: Optional[str] = None
    status: Optional[str] = None
    confidence: Optional[float] = None


class PromoteMemoryRequest(BaseModel):
    memory_id: int
    vault_id: int
    page_type: Optional[str] = None
    target_page_id: Optional[int] = None
    status: str = "needs_review"


class LintRunRequest(BaseModel):
    vault_id: int


# ---------------------------------------------------------------------------
# Pages endpoints
# ---------------------------------------------------------------------------

@router.get("/wiki/pages")
async def list_wiki_pages(
    vault_id: int = Query(..., description="Vault ID"),
    page_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: sqlite3.Connection = Depends(get_db),
    user: dict = Depends(get_current_active_user),
):
    await _require_vault_read(user, vault_id)
    store = WikiStore(db)
    pages = store.list_pages(vault_id, page_type=page_type, status=status, search=search, page=page, per_page=per_page)
    return {"pages": [_as_dict(p) for p in pages], "page": page, "per_page": per_page}


@router.post("/wiki/pages", status_code=201)
async def create_wiki_page(
    request: WikiPageCreateRequest,
    db: sqlite3.Connection = Depends(get_db),
    user: dict = Depends(get_current_active_user),
):
    await _require_vault_write(user, request.vault_id)
    store = WikiStore(db)
    try:
        page = store.create_page(
            vault_id=request.vault_id,
            title=request.title,
            page_type=request.page_type,
            slug=request.slug,
            markdown=request.markdown,
            summary=request.summary,
            status=request.status,
            confidence=request.confidence,
            created_by=user.get("id"),
        )
    except Exception as e:
        logger.exception("Error creating wiki page")
        raise HTTPException(status_code=400, detail=str(e))
    return _page_dict(page)


@router.get("/wiki/pages/{page_id}")
async def get_wiki_page(
    page_id: int,
    db: sqlite3.Connection = Depends(get_db),
    user: dict = Depends(get_current_active_user),
):
    store = WikiStore(db)
    page = store.get_page(page_id)
    if not page:
        raise HTTPException(status_code=404, detail="Wiki page not found")
    await _require_vault_read(user, page.vault_id)
    return _page_dict(page)


@router.put("/wiki/pages/{page_id}")
async def update_wiki_page(
    page_id: int,
    request: WikiPageUpdateRequest,
    db: sqlite3.Connection = Depends(get_db),
    user: dict = Depends(get_current_active_user),
):
    store = WikiStore(db)
    page = store.get_page(page_id, load_relations=False)
    if not page:
        raise HTTPException(status_code=404, detail="Wiki page not found")
    await _require_vault_write(user, page.vault_id)
    updates = request.model_dump(exclude_none=True)
    updated = store.update_page(page_id, page.vault_id, **updates)
    return _page_dict(updated)


@router.delete("/wiki/pages/{page_id}", status_code=204)
async def delete_wiki_page(
    page_id: int,
    db: sqlite3.Connection = Depends(get_db),
    user: dict = Depends(get_current_active_user),
):
    store = WikiStore(db)
    page = store.get_page(page_id, load_relations=False)
    if not page:
        raise HTTPException(status_code=404, detail="Wiki page not found")
    await _require_vault_write(user, page.vault_id)
    store.delete_page(page_id, page.vault_id)


# ---------------------------------------------------------------------------
# Entities endpoints
# ---------------------------------------------------------------------------

@router.get("/wiki/entities")
async def list_wiki_entities(
    vault_id: int = Query(...),
    search: Optional[str] = Query(None),
    db: sqlite3.Connection = Depends(get_db),
    user: dict = Depends(get_current_active_user),
):
    await _require_vault_read(user, vault_id)
    store = WikiStore(db)
    entities = store.list_entities(vault_id, search=search)
    return {"entities": [_as_dict(e) for e in entities]}


# ---------------------------------------------------------------------------
# Claims endpoints
# ---------------------------------------------------------------------------

@router.get("/wiki/claims")
async def list_wiki_claims(
    vault_id: int = Query(...),
    page_id: Optional[int] = Query(None),
    entity: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: sqlite3.Connection = Depends(get_db),
    user: dict = Depends(get_current_active_user),
):
    await _require_vault_read(user, vault_id)
    store = WikiStore(db)
    claims = store.list_claims(vault_id, page_id=page_id, entity=entity, search=search, status=status)
    return {"claims": [_as_dict(c) for c in claims]}


@router.post("/wiki/claims", status_code=201)
async def create_wiki_claim(
    request: WikiClaimCreateRequest,
    db: sqlite3.Connection = Depends(get_db),
    user: dict = Depends(get_current_active_user),
):
    await _require_vault_write(user, request.vault_id)
    store = WikiStore(db)
    claim = store.create_claim(
        vault_id=request.vault_id,
        claim_text=request.claim_text,
        source_type=request.source_type,
        page_id=request.page_id,
        claim_type=request.claim_type,
        subject=request.subject,
        predicate=request.predicate,
        object=request.object,
        status=request.status,
        confidence=request.confidence,
        created_by=user.get("id"),
    )
    return _as_dict(claim)


@router.put("/wiki/claims/{claim_id}")
async def update_wiki_claim(
    claim_id: int,
    request: WikiClaimUpdateRequest,
    db: sqlite3.Connection = Depends(get_db),
    user: dict = Depends(get_current_active_user),
):
    store = WikiStore(db)
    claim = store.get_claim(claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    await _require_vault_write(user, claim.vault_id)
    updates = request.model_dump(exclude_none=True)
    updated = store.update_claim(claim_id, claim.vault_id, **updates)
    return _as_dict(updated)


@router.delete("/wiki/claims/{claim_id}", status_code=204)
async def delete_wiki_claim(
    claim_id: int,
    db: sqlite3.Connection = Depends(get_db),
    user: dict = Depends(get_current_active_user),
):
    store = WikiStore(db)
    claim = store.get_claim(claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    await _require_vault_write(user, claim.vault_id)
    store.delete_claim(claim_id, claim.vault_id)


# ---------------------------------------------------------------------------
# Lint endpoints
# ---------------------------------------------------------------------------

@router.get("/wiki/lint")
async def get_lint_findings(
    vault_id: int = Query(...),
    status: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    db: sqlite3.Connection = Depends(get_db),
    user: dict = Depends(get_current_active_user),
):
    await _require_vault_read(user, vault_id)
    store = WikiStore(db)
    findings = store.list_lint_findings(vault_id, status=status, severity=severity)
    return {"findings": [_as_dict(f) for f in findings]}


@router.post("/wiki/lint/run")
async def run_wiki_lint(
    request: LintRunRequest,
    db: sqlite3.Connection = Depends(get_db),
    user: dict = Depends(get_current_active_user),
):
    await _require_vault_write(user, request.vault_id)
    store = WikiStore(db)
    linter = WikiLinter(db, store)
    findings = linter.run_lint(request.vault_id)
    return {"findings": [_as_dict(f) for f in findings], "count": len(findings)}


# ---------------------------------------------------------------------------
# Promote memory endpoint
# ---------------------------------------------------------------------------

@router.post("/wiki/promote-memory")
async def promote_memory_to_wiki(
    request: PromoteMemoryRequest,
    db: sqlite3.Connection = Depends(get_db),
    user: dict = Depends(get_current_active_user),
):
    await _require_vault_write(user, request.vault_id)
    store = WikiStore(db)
    compiler = WikiCompiler(db, store)
    try:
        result = compiler.promote_memory(
            memory_id=request.memory_id,
            vault_id=request.vault_id,
            page_type=request.page_type,
            target_page_id=request.target_page_id,
            status=request.status,
            created_by=user.get("id"),
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.exception("Error promoting memory to wiki")
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "page": _page_dict(result["page"]),
        "claims": [_as_dict(c) for c in result["claims"]],
        "entities": [_as_dict(e) for e in result["entities"]],
        "relations": [_as_dict(r) for r in result["relations"]],
    }


# ---------------------------------------------------------------------------
# Jobs endpoints
# ---------------------------------------------------------------------------

@router.get("/wiki/jobs")
async def list_wiki_jobs(
    vault_id: int = Query(...),
    status: Optional[str] = Query(None),
    db: sqlite3.Connection = Depends(get_db),
    user: dict = Depends(get_current_active_user),
):
    await _require_vault_read(user, vault_id)
    store = WikiStore(db)
    jobs = store.list_jobs(vault_id, status=status)
    return {"jobs": [_as_dict(j) for j in jobs]}


# ---------------------------------------------------------------------------
# Search endpoint
# ---------------------------------------------------------------------------

@router.get("/wiki/search")
async def search_wiki(
    vault_id: int = Query(...),
    q: str = Query(..., min_length=1),
    db: sqlite3.Connection = Depends(get_db),
    user: dict = Depends(get_current_active_user),
):
    await _require_vault_read(user, vault_id)
    store = WikiStore(db)
    results = store.search(vault_id, q)
    return {
        "query": q,
        "pages": [_as_dict(p) for p in results["pages"]],
        "claims": [_as_dict(c) for c in results["claims"]],
        "entities": [_as_dict(e) for e in results["entities"]],
    }
