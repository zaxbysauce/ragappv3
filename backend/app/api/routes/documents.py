"""
Documents API routes for file management and processing.

Provides endpoints for listing documents, uploading files, scanning directories,
and managing document processing status.
"""

import asyncio
import hashlib
import hmac
import logging
import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiofiles
from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Request,
    UploadFile,
    File,
    Query,
    Body,
)
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field

from app.config import settings, Settings
from app.services.document_processor import (
    DocumentProcessor,
    DocumentProcessingError,
    DuplicateFileError,
)
from app.services.vector_store import VectorStore
from app.services.upload_path import UploadPathProvider
from app.services.embeddings import EmbeddingService
from app.services.secret_manager import SecretManager
from app.models.database import SQLiteConnectionPool
from app.api.deps import (
    get_secret_manager,
    get_background_processor,
    get_vector_store,
    get_embedding_service,
    get_settings,
    get_db,
    get_db_pool,
    get_current_active_user,
    require_vault_permission,
    require_admin_role,
    evaluate_policy,
    get_user_accessible_vault_ids,
)
from app.security import csrf_protect
from app.limiter import limiter
from app.services.background_tasks import BackgroundProcessor


def secure_filename(filename: str) -> str:
    """
    Sanitize a filename to prevent security issues.

    - Strips paths using os.path.basename
    - Removes non-ASCII characters
    - Replaces spaces with underscores
    - Allows only alphanumeric, dots, hyphens, and underscores
    """
    # Strip paths
    filename = os.path.basename(filename)

    # Replace spaces with underscores
    filename = filename.replace(" ", "_")

    # Remove non-ASCII characters
    filename = filename.encode("ascii", "ignore").decode("ascii")

    # Allow only alphanumeric, dots, hyphens, and underscores
    filename = re.sub(r"[^a-zA-Z0-9._-]", "", filename)

    return filename


logger = logging.getLogger(__name__)


router = APIRouter(prefix="/documents", tags=["documents"])


async def _optional_current_user(
    authorization: str = Header(None),
    db: sqlite3.Connection = Depends(get_db),
) -> dict | None:
    """Try to get JWT user, return None if auth is disabled or token invalid."""
    if not settings.users_enabled or not authorization:
        return None
    try:
        return await get_current_active_user(authorization=authorization, db=db)
    except HTTPException:
        return None


def _record_document_action(
    file_id: int,
    action: str,
    status: str,
    user_id: str,
    secret_manager: SecretManager,
    conn: sqlite3.Connection,
) -> None:
    key, key_version = secret_manager.get_hmac_key()
    message = f"{file_id}|{action}|{status}|{user_id}"
    digest = hmac.new(key, message.encode("utf-8"), hashlib.sha256).hexdigest()
    conn.execute(
        """
        INSERT INTO document_actions(file_id, action, status, user_id, hmac_sha256)
        VALUES (?, ?, ?, ?, ?)
        """,
        (file_id, action, status, user_id, digest),
    )


@router.post("/admin/retry/{file_id}")
@limiter.limit(settings.admin_rate_limit)
async def retry_document(
    file_id: int,
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    user: dict = Depends(require_admin_role),
    csrf_token: str = Depends(csrf_protect),
    secret_manager: SecretManager = Depends(get_secret_manager),
    background_processor: BackgroundProcessor = Depends(get_background_processor),
    current_user: dict | None = Depends(_optional_current_user),
) -> dict:
    try:
        cursor = await asyncio.to_thread(
            conn.execute, "SELECT file_path FROM files WHERE id = ?", (file_id,)
        )
        row = await asyncio.to_thread(cursor.fetchone)
        if not row:
            raise HTTPException(status_code=404, detail="Document not found")

        # Ensure processor is running
        if not background_processor.is_running:
            await background_processor.start()

        await background_processor.enqueue(row["file_path"])

        user_id = (
            str(current_user["id"])
            if current_user and current_user.get("id")
            else user.get("id", "unknown")
        )
        await asyncio.to_thread(
            _record_document_action,
            file_id,
            "retry",
            "scheduled",
            user_id,
            secret_manager,
            conn,
        )
        await asyncio.to_thread(conn.commit)
        return {"file_id": file_id, "status": "scheduled"}
    except HTTPException:
        raise
    except (sqlite3.Error, OSError, RuntimeError) as exc:
        logger.exception("Error reprocessing document %d", file_id)
        user_id = (
            str(current_user["id"])
            if current_user and current_user.get("id")
            else user.get("id", "unknown")
        )
        await asyncio.to_thread(
            _record_document_action,
            file_id,
            "retry",
            "error",
            user_id,
            secret_manager,
            conn,
        )
        await asyncio.to_thread(conn.commit)
        raise HTTPException(status_code=500, detail=f"Retry failed: {exc}")


class DocumentResponse(BaseModel):
    """Response model for a document record - frontend compatible."""

    id: int
    file_name: str
    filename: str  # Frontend alias
    file_path: str
    status: str
    chunk_count: int
    size: Optional[int] = None  # Frontend expects size
    created_at: Optional[str]
    processed_at: Optional[str]
    metadata: Optional[dict] = None  # Frontend expects metadata

    model_config = ConfigDict(from_attributes=True)


class DocumentListResponse(BaseModel):
    """Response model for listing documents - frontend compatible with total."""

    documents: List[DocumentResponse]
    total: int


class DocumentStatsResponse(BaseModel):
    """Response model for document statistics - frontend compatible."""

    total_documents: int  # Frontend expects this field
    total_chunks: int
    total_size_bytes: int = 0  # Frontend expects this field
    documents_by_status: dict = Field(
        default_factory=dict
    )  # Frontend expects this field
    total_files: int = 0  # Backward compatibility alias
    status: str = "success"


class UploadResponse(BaseModel):
    """Response model for file upload - frontend compatible."""

    file_id: int
    file_name: str
    id: int  # Frontend alias for file_id
    filename: str  # Frontend alias for file_name
    status: str
    message: str


class ScanResponse(BaseModel):
    """Response model for directory scan - frontend compatible."""

    files_enqueued: int
    status: str
    message: str
    added: int  # Frontend alias for files_enqueued
    scanned: int  # Frontend expects this field (total files scanned)
    errors: List[str] = Field(default_factory=list)  # Frontend expects this field


class DeleteResponse(BaseModel):
    """Response model for document deletion."""

    file_id: int
    status: str
    message: str


class BatchDeleteResponse(BaseModel):
    """Response model for batch document deletion."""

    deleted_count: int
    failed_ids: List[str]


class DeleteAllVaultResponse(BaseModel):
    """Response model for deleting all documents in a vault."""

    deleted_count: int
    vault_id: int


def _row_to_document_response(row: sqlite3.Row) -> DocumentResponse:
    """Convert a database row to a DocumentResponse."""
    file_name = row["file_name"]
    chunk_count = row["chunk_count"] or 0
    status = row["status"]
    return DocumentResponse(
        id=row["id"],
        file_name=file_name,
        filename=file_name,  # Frontend alias
        file_path=row["file_path"],
        status=status,
        chunk_count=chunk_count,
        size=row["file_size"]
        if "file_size" in row.keys() and row["file_size"] is not None
        else None,
        created_at=row["created_at"],
        processed_at=row["processed_at"],
        metadata={
            "status": status,
            "chunk_count": chunk_count,
            "chunks": chunk_count,  # Backward compatibility
        },
    )


@router.get("", response_model=DocumentListResponse)
@router.get("/", response_model=DocumentListResponse)
async def list_documents(
    vault_id: Optional[int] = Query(None, description="Filter by vault ID"),
    conn: sqlite3.Connection = Depends(get_db),
    user: dict = Depends(get_current_active_user),
):
    """
    List all documents from the files table.

    Returns a list of all files with their id, file_name, file_path, status,
    chunk_count, created_at, and processed_at fields.
    Optionally filter by vault_id.
    """
    # Check vault permissions
    if vault_id is not None:
        if not await evaluate_policy(user, "vault", vault_id, "read"):
            raise HTTPException(status_code=403, detail="Access denied to vault")
        # Query with specific vault_id
        cursor = await asyncio.to_thread(
            conn.execute,
            """
            SELECT id, file_name, file_path, status, chunk_count, file_size, created_at, processed_at
            FROM files
            WHERE vault_id = ?
            ORDER BY created_at DESC
            """,
            (vault_id,),
        )
    else:
        # For non-admins without vault_id, get accessible vaults
        if user.get("role") not in ("admin", "superadmin"):
            accessible_vaults = get_user_accessible_vault_ids(user, conn)
            if not accessible_vaults:
                return DocumentListResponse(documents=[], total=0)
            # Query with vault_id IN clause
            placeholders = ",".join("?" * len(accessible_vaults))
            cursor = await asyncio.to_thread(
                conn.execute,
                f"""
                SELECT id, file_name, file_path, status, chunk_count, file_size, created_at, processed_at
                FROM files
                WHERE vault_id IN ({placeholders})
                ORDER BY created_at DESC
                """,
                tuple(accessible_vaults),
            )
        else:
            # Admins can see all documents
            cursor = await asyncio.to_thread(
                conn.execute,
                """
                SELECT id, file_name, file_path, status, chunk_count, file_size, created_at, processed_at
                FROM files
                ORDER BY created_at DESC
                """,
            )
    rows = await asyncio.to_thread(cursor.fetchall)

    documents = [_row_to_document_response(row) for row in rows]

    return DocumentListResponse(documents=documents, total=len(documents))


@router.get("/stats", response_model=DocumentStatsResponse)
async def get_document_stats(
    vault_id: Optional[int] = Query(None, description="Filter by vault ID"),
    conn: sqlite3.Connection = Depends(get_db),
    user: dict = Depends(get_current_active_user),
):
    """
    Get counts of files and chunks.

    Returns total number of files in the database, total chunks,
    total size in bytes, and documents grouped by status.
    Optionally filter by vault_id.
    """
    # Determine vault filter for queries
    vault_filter_sql = ""
    vault_filter_params: tuple = ()

    # Check vault permissions
    if vault_id is not None:
        if not await evaluate_policy(user, "vault", vault_id, "read"):
            raise HTTPException(status_code=403, detail="Access denied to vault")
        vault_filter_sql = "WHERE vault_id = ?"
        vault_filter_params = (vault_id,)
    else:
        # For non-admins without vault_id, get accessible vaults
        if user.get("role") not in ("admin", "superadmin"):
            accessible_vaults = get_user_accessible_vault_ids(user, conn)
            if not accessible_vaults:
                return DocumentStatsResponse(
                    total_documents=0,
                    total_chunks=0,
                    total_size_bytes=0,
                    documents_by_status={},
                    total_files=0,
                )
            placeholders = ",".join("?" * len(accessible_vaults))
            vault_filter_sql = f"WHERE vault_id IN ({placeholders})"
            vault_filter_params = tuple(accessible_vaults)

    # Get total files count
    cursor = await asyncio.to_thread(
        conn.execute,
        f"SELECT COUNT(*) as total_files FROM files {vault_filter_sql}".strip(),
        vault_filter_params,
    )
    row = await asyncio.to_thread(cursor.fetchone)
    total_files = row["total_files"]

    # Get total chunks count
    cursor = await asyncio.to_thread(
        conn.execute,
        f"SELECT COALESCE(SUM(chunk_count), 0) as total_chunks FROM files {vault_filter_sql}".strip(),
        vault_filter_params,
    )
    row = await asyncio.to_thread(cursor.fetchone)
    total_chunks = row["total_chunks"]

    # Get total size (sum of file_size if column exists, otherwise 0)
    try:
        cursor = await asyncio.to_thread(
            conn.execute,
            f"SELECT COALESCE(SUM(file_size), 0) as total_size FROM files {vault_filter_sql}".strip(),
            vault_filter_params,
        )
        row = await asyncio.to_thread(cursor.fetchone)
        total_size_bytes = row["total_size"] or 0
    except sqlite3.OperationalError:
        total_size_bytes = 0

    # Get documents grouped by status
    cursor = await asyncio.to_thread(
        conn.execute,
        f"SELECT status, COUNT(*) as count FROM files {vault_filter_sql} GROUP BY status".strip(),
        vault_filter_params,
    )
    rows = await asyncio.to_thread(cursor.fetchall)
    documents_by_status = {row["status"]: row["count"] for row in rows}

    return DocumentStatsResponse(
        total_documents=total_files,  # Frontend field
        total_chunks=total_chunks,
        total_size_bytes=total_size_bytes,
        documents_by_status=documents_by_status,
        total_files=total_files,  # Backward compatibility
    )


@router.post("", response_model=UploadResponse)
@router.post("/", response_model=UploadResponse)
async def upload_document_root(
    request: Request,
    file: Optional[UploadFile] = None,
    vault_id: int = Query(1, description="Target vault ID"),
    settings_dep: Settings = Depends(get_settings),
    vector_store: VectorStore = Depends(get_vector_store),
    embedding_service: EmbeddingService = Depends(get_embedding_service),
    db_pool: SQLiteConnectionPool = Depends(get_db_pool),
    user: dict = Depends(require_vault_permission("write")),
):
    """
    Upload endpoint at root /documents for frontend compatibility.
    Delegates to the main upload handler.
    """
    return await _do_upload(
        request, file, settings_dep, vector_store, embedding_service, db_pool, vault_id
    )


@router.post("/upload", response_model=UploadResponse)
async def upload_document(
    request: Request,
    file: Optional[UploadFile] = None,
    vault_id: int = Query(1, description="Target vault ID"),
    settings_dep: Settings = Depends(get_settings),
    vector_store: VectorStore = Depends(get_vector_store),
    embedding_service: EmbeddingService = Depends(get_embedding_service),
    db_pool: SQLiteConnectionPool = Depends(get_db_pool),
    user: dict = Depends(require_vault_permission("write")),
):
    """
    Upload a file and process it with strict security controls.

    Validates filename, extension, and file size before saving.
    Saves the uploaded file to settings.uploads_dir using aiofiles,
    then processes it via DocumentProcessor.process_file in asyncio.to_thread.
    """
    return await _do_upload(
        request, file, settings_dep, vector_store, embedding_service, db_pool, vault_id
    )


async def _do_upload(
    request: Request,
    file: Optional[UploadFile],
    settings_dep: Settings,
    vector_store: VectorStore,
    embedding_service: EmbeddingService,
    db_pool: SQLiteConnectionPool,
    vault_id: int,
) -> UploadResponse:
    # Validate file is provided
    if file is None:
        raise HTTPException(status_code=400, detail="No file provided")

    # Validate filename is not empty
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename cannot be empty")

    # Ensure uploads directory exists
    provider = UploadPathProvider()
    upload_dir = provider.get_upload_dir(vault_id or settings.orphan_vault_id)
    upload_dir.mkdir(parents=True, exist_ok=True)

    # Sanitize filename
    file_name = secure_filename(file.filename or "unnamed_file")
    if not file_name:
        file_name = "unnamed_file.txt"

    # Ensure file has an extension for validation
    if not Path(file_name).suffix:
        file_name = f"{file_name}.txt"

    # Validate file extension
    file_suffix = Path(file_name).suffix.lower()
    if file_suffix not in settings_dep.allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"File extension '{file_suffix}' not allowed. Allowed: {settings_dep.allowed_extensions}",
        )

    # Validate file size from content-length header
    max_size_bytes = settings_dep.max_file_size_mb * 1024 * 1024
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > max_size_bytes:
                raise HTTPException(
                    status_code=413,
                    detail=f"File too large. Max size: {settings.max_file_size_mb}MB",
                )
        except ValueError:
            pass  # Invalid content-length header, will check during streaming

    # Generate safe file path
    file_path = upload_dir / file_name

    # Handle duplicate file names
    counter = 1
    original_path = file_path
    while file_path.exists():
        stem = original_path.stem
        suffix = original_path.suffix
        file_path = upload_dir / f"{stem}_{counter}{suffix}"
        counter += 1

    # Path safety: ensure file_path is within upload_dir
    try:
        resolved_path = file_path.resolve()
        resolved_upload_dir = upload_dir.resolve()
        if not str(resolved_path).startswith(str(resolved_upload_dir)):
            raise HTTPException(status_code=400, detail="Invalid file path")
    except (OSError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid file path")

    temp_file_path = None
    try:
        # Save file using aiofiles with chunked reading and size validation
        total_bytes = 0
        temp_file_path = file_path
        async with aiofiles.open(temp_file_path, "wb") as f:
            while chunk := await file.read(1024 * 1024):  # Read 1MB chunks
                total_bytes += len(chunk)
                if total_bytes > max_size_bytes:
                    # Close and delete partial file
                    await f.close()
                    if temp_file_path.exists():
                        temp_file_path.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=413,
                        detail=f"File too large. Max size: {settings.max_file_size_mb}MB",
                    )
                await f.write(chunk)

        # Process file with injected dependencies
        processor = DocumentProcessor(
            chunk_size_chars=settings_dep.chunk_size_chars,
            chunk_overlap_chars=settings_dep.chunk_overlap_chars,
            vector_store=vector_store,
            embedding_service=embedding_service,
            pool=db_pool,
        )

        try:
            result = await processor.process_file(str(file_path), vault_id=vault_id)

            return UploadResponse(
                file_id=result.file_id,
                file_name=file_name,
                id=result.file_id,  # Frontend alias
                filename=file_name,  # Frontend alias
                status="indexed",
                message=f"File '{file_name}' uploaded and processed successfully with {len(result.chunks)} chunks",
            )
        except DuplicateFileError as e:
            # File is a duplicate, remove the uploaded file
            file_path.unlink(missing_ok=True)
            raise HTTPException(
                status_code=409, detail=f"{e} (uploaded file was cleaned up)"
            )
        except HTTPException:
            # Clean up partial file if it exists
            if temp_file_path and temp_file_path.exists():
                temp_file_path.unlink(missing_ok=True)
            raise
        except DocumentProcessingError as e:
            logger.exception("Document processing error for file: %s", file_name)
            raise HTTPException(status_code=500, detail=f"Processing error: {e}")
        except Exception as e:
            logger.exception("Unexpected error processing file: %s", file_name)
            raise HTTPException(status_code=500, detail=f"Server error: {e}")
    except Exception as e:
        logger.exception("Error uploading file: %s", file_name)
        # Clean up file if it was created
        if temp_file_path and temp_file_path.exists():
            temp_file_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Upload failed: {e}")


@router.post("/scan", response_model=ScanResponse)
async def scan_directories(
    request: Request,
    background_processor: BackgroundProcessor = Depends(get_background_processor),
    db_pool: SQLiteConnectionPool = Depends(get_db_pool),
    user: dict = Depends(require_vault_permission("write")),
):
    """
    Trigger a scan of configured directories for new files.

    Calls FileWatcher.scan_once() to find and enqueue new files
    from uploads_dir and library_dir that are not in the database.

    Uses the singleton BackgroundProcessor that runs continuously in the background.
    """
    from app.services.file_watcher import FileWatcher

    # Ensure processor is running (it should be from lifespan, but double-check)
    if not background_processor.is_running:
        await background_processor.start()

    try:
        watcher = FileWatcher(background_processor, pool=db_pool)

        # Perform scan
        files_enqueued = await watcher.scan_once()

        if files_enqueued > 0:
            message = (
                f"Scan complete: {files_enqueued} new files enqueued for processing"
            )
        else:
            message = "Scan complete: no new files found"

        return ScanResponse(
            files_enqueued=files_enqueued,
            status="success",
            message=message,
            added=files_enqueued,  # Frontend alias
            scanned=files_enqueued,  # Frontend expects this (at least files_enqueued)
            errors=[],  # Frontend expects this field
        )
    except Exception as e:
        logger.exception("Error during directory scan")
        raise HTTPException(status_code=500, detail=f"Scan failed: {e}")
    # Note: No finally block to stop processor - it runs continuously


@router.delete("/{file_id}", response_model=DeleteResponse)
async def delete_document(
    file_id: int,
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    user: dict = Depends(get_current_active_user),
    vector_store: VectorStore = Depends(get_vector_store),
):
    """
    Delete a document by ID.

    Deletes the file record from the database and removes all associated
    chunks from the vector store. Returns 404 if the file is not found.
    """
    # Check if file exists and get vault_id for permission check
    cursor = await asyncio.to_thread(
        conn.execute,
        "SELECT id, file_name, vault_id FROM files WHERE id = ?",
        (file_id,),
    )
    row = await asyncio.to_thread(cursor.fetchone)

    if row is None:
        raise HTTPException(
            status_code=404, detail=f"Document with id {file_id} not found"
        )

    file_name = row["file_name"]
    file_vault_id = row["vault_id"]

    # Check vault admin permission
    if not await evaluate_policy(user, "vault", file_vault_id, "admin"):
        raise HTTPException(status_code=403, detail="Insufficient vault permissions")

    try:
        # Delete from vector store first
        try:
            db = vector_store.db
            if db is not None and "chunks" in await db.table_names():
                vector_store.table = await db.open_table("chunks")
                deleted_chunks = await vector_store.delete_by_file(str(file_id))
                logger.info(
                    "Deleted %d chunks from vector store for file_id %s",
                    deleted_chunks,
                    file_id,
                )
            else:
                logger.debug(
                    "Chunks table not found, skipping vector store deletion for file_id %s",
                    file_id,
                )
        except Exception as e:
            logger.warning("Error deleting chunks from vector store: %s", e)
            # Continue with database deletion even if vector store fails

        # Delete from database
        await asyncio.to_thread(
            conn.execute, "DELETE FROM files WHERE id = ?", (file_id,)
        )
        await asyncio.to_thread(conn.commit)

        return DeleteResponse(
            file_id=file_id,
            status="success",
            message=f"Document '{file_name}' (id: {file_id}) deleted successfully",
        )
    except HTTPException:
        raise
    except Exception as e:
        await asyncio.to_thread(conn.rollback)
        logger.exception("Error deleting document %d", file_id)
        raise HTTPException(status_code=500, detail=f"Delete failed: {e}")


@router.post("/batch", response_model=BatchDeleteResponse)
async def batch_delete_documents(
    request: Request,
    file_ids: List[str] = Body(
        ..., embed=True, description="List of file IDs to delete"
    ),
    conn: sqlite3.Connection = Depends(get_db),
    user: dict = Depends(require_admin_role),
    vector_store: VectorStore = Depends(get_vector_store),
):
    """
    Batch delete documents by IDs.

    Deletes multiple documents from the database and removes all associated
    chunks from the vector store. Returns count of successfully deleted
    documents and any failed IDs.
    """
    deleted_count = 0
    failed_ids: List[str] = []

    for file_id in file_ids:
        try:
            # Check if file exists
            cursor = await asyncio.to_thread(
                conn.execute, "SELECT id, file_name FROM files WHERE id = ?", (file_id,)
            )
            row = await asyncio.to_thread(cursor.fetchone)

            if row is None:
                failed_ids.append(file_id)
                continue

            file_name = row["file_name"]

            # Delete from vector store first
            try:
                db = vector_store.db
                if db is not None and "chunks" in await db.table_names():
                    vector_store.table = await db.open_table("chunks")
                    await vector_store.delete_by_file(str(file_id))
            except Exception as e:
                logger.warning(
                    "Error deleting chunks from vector store for file_id %d: %s",
                    file_id,
                    e,
                )

            # Delete from database
            await asyncio.to_thread(
                conn.execute, "DELETE FROM files WHERE id = ?", (file_id,)
            )
            await asyncio.to_thread(conn.commit)
            deleted_count += 1
            logger.info("Deleted document '%s' (id: %d)", file_name, file_id)

        except Exception as e:
            logger.exception("Error deleting document %d", file_id)
            failed_ids.append(file_id)

    return BatchDeleteResponse(
        deleted_count=deleted_count,
        failed_ids=failed_ids,
    )


@router.delete("/vault/{vault_id}/all", response_model=DeleteAllVaultResponse)
async def delete_all_vault_documents(
    vault_id: int,
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    user: dict = Depends(require_vault_permission("admin")),
    vector_store: VectorStore = Depends(get_vector_store),
):
    """
    Delete all documents in a vault.

    Deletes all file records from the database and removes all associated
    chunks from the vector store for the specified vault.
    """
    # Get all file IDs in the vault
    cursor = await asyncio.to_thread(
        conn.execute, "SELECT id FROM files WHERE vault_id = ?", (vault_id,)
    )
    rows = await asyncio.to_thread(cursor.fetchall)

    file_ids = [row["id"] for row in rows]
    deleted_count = 0

    for file_id in file_ids:
        try:
            # Delete from vector store first
            try:
                db = vector_store.db
                if db is not None and "chunks" in await db.table_names():
                    vector_store.table = await db.open_table("chunks")
                    await vector_store.delete_by_file(str(file_id))
            except Exception as e:
                logger.warning(
                    "Error deleting chunks from vector store for file_id %d: %s",
                    file_id,
                    e,
                )

            # Delete from database
            await asyncio.to_thread(
                conn.execute, "DELETE FROM files WHERE id = ?", (file_id,)
            )
            await asyncio.to_thread(conn.commit)
            deleted_count += 1

        except Exception as e:
            logger.exception(
                "Error deleting document %d from vault %d", file_id, vault_id
            )

    logger.info("Deleted %d documents from vault %d", deleted_count, vault_id)

    return DeleteAllVaultResponse(
        deleted_count=deleted_count,
        vault_id=vault_id,
    )


# Exception handler for validation errors (e.g., empty filename)
# This is registered at the app level in main.py
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Convert validation errors to 400 for empty filename cases only."""
    errors = exc.errors()
    for error in errors:
        if (
            error.get("loc") == ("body", "file")
            and "filename" in str(error.get("input", "")).lower()
        ):
            raise HTTPException(status_code=400, detail="Filename cannot be empty")
    # For all other validation errors, return standard 422
    # Convert errors to dict format for JSON serialization
    from fastapi.responses import JSONResponse

    error_dicts = [
        {
            "loc": error.get("loc"),
            "msg": error.get("msg"),
            "type": error.get("type"),
            "input": error.get("input"),
        }
        for error in errors
    ]
    return JSONResponse(status_code=422, content={"detail": error_dicts})
