"""
KMSCompileProcessor: asyncio background worker that drains kms_compile_jobs.

Single worker per process. Polls every POLL_INTERVAL seconds.
On startup, resets orphaned 'running' jobs back to 'pending' (crash recovery).
All DB work runs in threads via asyncio.to_thread() since SQLite is sync.

"Compiling" a KMS entry is deterministic: for an ingested document it creates
(or refreshes) a user-curatable kms_entries row from the file's parsed_text so
the document content becomes browsable and full-text searchable in the KMS
without going through the RAG pipeline.
"""

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from app.models.database import SQLiteConnectionPool

logger = logging.getLogger(__name__)

POLL_INTERVAL = 5  # seconds between polls when queue is empty
MAX_RETRIES = 3    # max automatic retries before a job is permanently failed
SUMMARY_CHARS = 500  # leading characters of body used as the entry summary


class KMSCompileProcessor:
    """Background worker that processes kms_compile_jobs from the SQLite queue.

    One worker per process. A connection is acquired per-job and released
    before each sleep, so it never holds a connection across the idle period.
    """

    def __init__(self, pool: "SQLiteConnectionPool") -> None:
        self._pool = pool
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        await asyncio.to_thread(self._reset_orphans)
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("KMSCompileProcessor started")

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("KMSCompileProcessor stopped")

    # ------------------------------------------------------------------
    # Startup orphan recovery
    # ------------------------------------------------------------------

    def _reset_orphans(self) -> None:
        from app.services.kms_store import KMSStore

        with self._pool.connection() as conn:
            n = KMSStore(conn).reset_running_jobs()
        if n:
            logger.warning("KMSCompileProcessor: reset %d orphaned running jobs to pending", n)

    # ------------------------------------------------------------------
    # Poll loop
    # ------------------------------------------------------------------

    async def _poll_loop(self) -> None:
        while self._running:
            try:
                job = await asyncio.to_thread(self._claim_next_job)
                if job is None:
                    await asyncio.sleep(POLL_INTERVAL)
                    continue

                logger.info(
                    "KMSCompileProcessor: claimed job id=%d type=%s vault=%d",
                    job.id,
                    job.trigger_type,
                    job.vault_id,
                )

                try:
                    result = await asyncio.to_thread(self._dispatch, job)
                    await asyncio.to_thread(self._complete_job, job.id, result)
                    logger.info("KMSCompileProcessor: completed job id=%d", job.id)
                except Exception as exc:
                    logger.exception(
                        "KMSCompileProcessor: job id=%d failed: %s", job.id, exc
                    )
                    try:
                        new_retry_count = await asyncio.to_thread(
                            self._fail_job, job.id, str(exc)
                        )
                        if new_retry_count < MAX_RETRIES:
                            backoff = 2.0 ** new_retry_count
                            logger.info(
                                "KMSCompileProcessor: job id=%d will auto-retry (%d/%d) in %.0fs",
                                job.id, new_retry_count, MAX_RETRIES, backoff,
                            )
                            await asyncio.sleep(backoff)
                            await asyncio.to_thread(self._reset_job_to_pending, job.id)
                        else:
                            logger.error(
                                "KMSCompileProcessor: job id=%d permanently failed after %d retries",
                                job.id, new_retry_count,
                            )
                    except Exception as e2:
                        logger.error(
                            "KMSCompileProcessor: could not mark job id=%d failed: %s", job.id, e2
                        )

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("KMSCompileProcessor: poll loop error: %s", exc)
                await asyncio.sleep(POLL_INTERVAL)

    # ------------------------------------------------------------------
    # Synchronous helpers (run in thread)
    # ------------------------------------------------------------------

    def _claim_next_job(self):
        from app.services.kms_store import KMSStore

        with self._pool.connection() as conn:
            return KMSStore(conn).claim_next_pending_job()

    def _complete_job(self, job_id: int, result: dict) -> None:
        from app.services.kms_store import KMSStore

        with self._pool.connection() as conn:
            KMSStore(conn).complete_job(job_id, result)

    def _fail_job(self, job_id: int, error: str) -> int:
        from app.services.kms_store import KMSStore

        with self._pool.connection() as conn:
            return KMSStore(conn).fail_job(job_id, error)

    def _reset_job_to_pending(self, job_id: int) -> None:
        from app.services.kms_store import KMSStore

        with self._pool.connection() as conn:
            KMSStore(conn).reset_job_to_pending(job_id)

    def _dispatch(self, job) -> dict:
        """Dispatch a job to the appropriate handler. Runs in a thread."""
        from app.services.kms_store import KMSStore

        input_json: dict = {}
        if job.input_json:
            try:
                input_json = json.loads(job.input_json) if isinstance(job.input_json, str) else job.input_json
            except (json.JSONDecodeError, TypeError):
                input_json = {}

        with self._pool.connection() as conn:
            store = KMSStore(conn)

            if job.trigger_type == "ingest":
                file_id = input_json.get("file_id")
                if not file_id:
                    return {"skipped": True, "reason": "no file_id in input_json"}
                return self._compile_file(conn, store, job.vault_id, int(file_id))

            if job.trigger_type in ("manual", "settings_reindex"):
                file_id = input_json.get("file_id")
                if file_id:
                    return self._compile_file(conn, store, job.vault_id, int(file_id))
                return self._compile_vault(conn, store, job.vault_id)

            logger.warning(
                "KMSCompileProcessor: unknown trigger_type %r for job id=%d",
                job.trigger_type, job.id,
            )
            return {"skipped": True, "reason": f"unknown trigger_type: {job.trigger_type}"}

    # ------------------------------------------------------------------
    # Compile handlers
    # ------------------------------------------------------------------

    @staticmethod
    def _compile_file(conn, store, vault_id: int, file_id: int) -> dict:
        """Create/refresh the document-sourced KMS entry for one file."""
        row = conn.execute(
            "SELECT file_name, parsed_text FROM files WHERE id = ? AND vault_id = ?",
            (file_id, vault_id),
        ).fetchone()
        if not row:
            return {"skipped": True, "reason": f"file {file_id} not found in vault {vault_id}"}
        d = dict(row)
        body = d.get("parsed_text") or ""
        if not body.strip():
            return {"skipped": True, "reason": "no parsed_text to compile"}
        summary = body[:SUMMARY_CHARS].strip()
        entry = store.upsert_document_entry(
            vault_id=vault_id,
            file_id=file_id,
            title=d.get("file_name") or f"Document {file_id}",
            body=body,
            summary=summary,
        )
        return {"entry_id": entry.id, "file_id": file_id, "skipped": False}

    def _compile_vault(self, conn, store, vault_id: int) -> dict:
        """Recompile document entries for every indexed file in the vault."""
        rows = conn.execute(
            "SELECT id FROM files WHERE vault_id = ? AND status = 'indexed'",
            (vault_id,),
        ).fetchall()
        compiled = 0
        skipped = 0
        for r in rows:
            res = self._compile_file(conn, store, vault_id, dict(r)["id"])
            if res.get("skipped"):
                skipped += 1
            else:
                compiled += 1
        return {"compiled": compiled, "skipped": skipped, "total": len(rows)}


__all__ = ["KMSCompileProcessor"]
