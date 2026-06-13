"""Admin routes for managing feature toggles and admin operations."""

import asyncio
import hashlib
import hmac
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from app.api.deps import get_db, get_secret_manager, get_toggle_manager, require_role
from app.config import settings
from app.security import csrf_protect, require_scope
from app.services.secret_manager import SecretManager
from app.services.toggle_manager import ToggleManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


class TogglePayload(BaseModel):
    feature: str
    enabled: bool


def _compute_hmac(key: bytes, feature: str, enabled: bool, user_id: str | None, ip: str | None) -> tuple[str, str]:
    timestamp = datetime.now(timezone.utc).isoformat()
    message = f"{feature}|{int(enabled)}|{user_id or ''}|{ip or ''}|{timestamp}"
    digest = hmac.new(key, message.encode("utf-8"), hashlib.sha256).hexdigest()
    return digest, timestamp


@router.post("/toggles")
async def set_toggle(
    payload: TogglePayload,
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    toggle_manager: ToggleManager = Depends(get_toggle_manager),
    secret_manager: SecretManager = Depends(get_secret_manager),
    auth: dict = Depends(require_scope("admin:config")),
):
    await asyncio.to_thread(toggle_manager.set_toggle, payload.feature, payload.enabled)
    key, key_version = secret_manager.get_hmac_key()
    try:
        hmac_digest, timestamp = _compute_hmac(
            key,
            payload.feature,
            payload.enabled,
            auth.get("user_id"),
            request.client.host if request.client else None,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to compute audit HMAC: {exc}")
    await asyncio.to_thread(
        conn.execute,
        """
        INSERT INTO audit_toggle_log(feature, enabled, user_id, ip, timestamp, key_version, hmac_sha256)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            payload.feature,
            int(payload.enabled),
            auth.get("user_id"),
            request.client.host if request.client else None,
            timestamp,
            key_version,
            hmac_digest,
        ),
    )
    await asyncio.to_thread(conn.commit)
    request.app.state.model_validation = await asyncio.to_thread(
        toggle_manager.get_toggle, "model_validation", settings.enable_model_validation
    )
    return {"feature": payload.feature, "enabled": payload.enabled, "hmac": hmac_digest}


@router.post("/reindex")
async def reindex_documents(
    request: Request,
    vault_id: Optional[int] = Query(None, description="Reindex a single vault, or all if omitted"),
    conn: sqlite3.Connection = Depends(get_db),
    _role: dict = Depends(require_role("admin")),
    _csrf_token: str = Depends(csrf_protect),
):
    """Re-enqueue all indexed documents for re-processing.

    The existing ingestion pipeline handles re-uploads by deleting old chunks
    and re-embedding, so this endpoint simply enqueues every indexed file back
    into the BackgroundProcessor queue.

    After queueing, updates the embedding_model_info table with the current
    model config so the mismatch warning clears.
    """
    background_processor = getattr(request.app.state, "background_processor", None)
    if background_processor is None:
        raise HTTPException(status_code=503, detail="Background processor is not available")

    # Query indexed files, optionally filtered by vault
    if vault_id is not None:
        rows = await asyncio.to_thread(
            lambda: conn.execute(
                "SELECT id, file_path, vault_id FROM files WHERE status = 'indexed' AND vault_id = ?",
                (vault_id,),
            ).fetchall()
        )
    else:
        rows = await asyncio.to_thread(
            lambda: conn.execute(
                "SELECT id, file_path, vault_id FROM files WHERE status = 'indexed'"
            ).fetchall()
        )

    queued = 0
    for row in rows:
        file_id = row["id"] if hasattr(row, "keys") else row[0]
        file_path = row["file_path"] if hasattr(row, "keys") else row[1]
        row_vault_id = row["vault_id"] if hasattr(row, "keys") else row[2]

        # Reset the file status so the processor re-ingests it
        await asyncio.to_thread(
            lambda fid=file_id: (
                conn.execute(
                    "UPDATE files SET status = 'pending', phase = 'queued', "
                    "error_message = NULL WHERE id = ?",
                    (fid,),
                ),
                conn.commit(),
            )
        )

        try:
            await background_processor.enqueue(
                file_path=file_path,
                vault_id=int(row_vault_id),
                source="upload",
                file_id=int(file_id),
            )
            queued += 1
        except Exception as exc:
            logger.warning("Failed to enqueue file_id=%s for reindex: %s", file_id, exc)

    # Update the embedding model info to the current config, clearing the
    # mismatch flag so the warning disappears from the UI.
    try:
        await asyncio.to_thread(
            lambda: (
                conn.execute(
                    "INSERT OR REPLACE INTO embedding_model_info "
                    "(id, model_name, dimensions, updated_at) "
                    "VALUES (1, ?, ?, CURRENT_TIMESTAMP)",
                    (settings.embedding_model, settings.embedding_dim),
                ),
                conn.commit(),
            )
        )
        request.app.state.embedding_model_mismatch = False
    except Exception as exc:
        logger.warning("Failed to update embedding_model_info after reindex: %s", exc)

    logger.info("Reindex: queued %d documents for re-processing", queued)
    return {"queued": queued, "vault_id": vault_id}
