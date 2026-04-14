"""
Document processing service with orchestration, status tracking, and deduplication.

Provides DocumentProcessor class that coordinates parsing, chunking, and schema extraction
while tracking processing status in SQLite and handling file deduplication.
"""

import asyncio
import json
import logging
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, UTC
from pathlib import Path
from typing import List, Any, Optional, Tuple

import pandas as pd

from ..config import settings
from ..models.database import SQLiteConnectionPool, get_pool
from ..utils.file_utils import compute_file_hash
from ..utils.retry import with_retry
from .chunking import SemanticChunker, ProcessedChunk, compute_parent_windows
from .chunk_enrichment import ChunkEnrichmentService
from .contextual_chunking import ContextualChunker
from .embeddings import EmbeddingService
from .llm_client import LLMClient
from .schema_parser import SchemaParser
from .vector_store import VectorStore

logger = logging.getLogger(__name__)


@dataclass
class ProcessedDocument:
    """
    Result of processing a document file.

    Attributes:
        file_id: The database ID of the processed file
        chunks: List of processed chunks from the document
    """

    file_id: int
    chunks: List[ProcessedChunk]


class DuplicateFileError(Exception):
    """Exception raised when a file with the same hash already exists and is indexed."""

    pass


class DocumentProcessingError(Exception):
    """Exception raised when document processing fails due to database errors."""

    pass


class DocumentParseError(Exception):
    """Exception raised when document parsing fails."""

    pass


class DocumentParser:
    """
    Parser for extracting text elements from documents using unstructured.io.

    Supports various formats: PDF, DOCX, TXT, HTML, and more.
    Uses configurable strategy from settings (default: fast for speed).
    """

    def parse(self, file_path: str) -> List[Any]:
        """
        Parse a document and extract text elements.

        Args:
            file_path: Path to the document file to parse.

        Returns:
            List of extracted text elements from the document.

        Raises:
            FileNotFoundError: If the specified file does not exist.
            DocumentParseError: If parsing fails for any reason.
        """
        # Validate file exists
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Document file not found: {file_path}")

        if not path.is_file():
            raise FileNotFoundError(f"Path is not a file: {file_path}")

        try:
            # Lazy import: unstructured can hang at module level when it
            # tries to download models or reach a network resource.
            from unstructured.partition.auto import partition

            # Use unstructured with configured strategy from settings
            elements = partition(
                filename=str(path), strategy=settings.document_parsing_strategy
            )
            return elements
        except Exception as e:
            # Wrap exceptions with clear, actionable message
            raise DocumentParseError(
                f"Failed to parse document '{file_path}': {str(e)}"
            ) from e


class SpreadsheetParser:
    """
    Parser for CSV, XLS, and XLSX spreadsheet files.

    Converts tabular data into RAG-ready text chunks. Each chunk covers a
    configurable number of rows and always includes the column header line
    as context, so retrieved chunks are self-contained without needing
    surrounding rows for interpretation.

    Sheet name and column list are prepended to every chunk so the LLM
    can orient itself when answering questions about the data.
    """

    # Number of data rows per chunk. Tune lower for wide sheets (many columns),
    # higher for narrow sheets. 50 rows * ~5 cols * ~15 chars ≈ ~3750 chars,
    # safely under a 2000-char chunk_size_chars default with header overhead.
    ROWS_PER_CHUNK: int = 50

    def parse(self, file_path: str) -> List[dict]:
        """
        Parse a spreadsheet file and return a list of chunk dicts.

        Each returned dict has the structure:
            {
                "text": str,        # RAG-ready text block for this chunk
                "metadata": dict,   # Sheet name, row range, column count, etc.
            }

        Args:
            file_path: Absolute or relative path to the .csv, .xls, or .xlsx file.

        Returns:
            List of chunk dicts. Returns an empty list if the file has no
            readable data (empty sheets are skipped, not errored).

        Raises:
            FileNotFoundError: If the file does not exist.
            DocumentParseError: If pandas fails to read the file.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Spreadsheet file not found: {file_path}")

        ext = path.suffix.lower()

        try:
            if ext == ".csv":
                # Single-sheet: wrap in dict to unify the loop below
                df = pd.read_csv(file_path, dtype=str).fillna("")
                sheets: dict = {"Sheet1": df}
            elif ext in {".xls", ".xlsx"}:
                xf = pd.ExcelFile(file_path)
                sheets = {
                    name: xf.parse(name, dtype=str).fillna("")
                    for name in xf.sheet_names
                }
            else:
                raise DocumentParseError(
                    f"SpreadsheetParser received unsupported extension '{ext}'. "
                    f"Expected .csv, .xls, or .xlsx."
                )
        except DocumentParseError:
            raise
        except Exception as e:
            raise DocumentParseError(
                f"Failed to read spreadsheet '{file_path}': {e}"
            ) from e

        chunks: List[dict] = []

        for sheet_name, df in sheets.items():
            if df.empty:
                logger.debug(
                    "Skipping empty sheet '%s' in '%s'", sheet_name, file_path
                )
                continue

            headers = list(df.columns)
            header_str = " | ".join(str(h) for h in headers)
            total_rows = len(df)

            for start in range(0, total_rows, self.ROWS_PER_CHUNK):
                batch = df.iloc[start : start + self.ROWS_PER_CHUNK]
                rows_text_lines = []

                for _, row in batch.iterrows():
                    # Only include cells that have non-empty values to keep
                    # chunks compact. The header line already names every column.
                    row_parts = [
                        f"{col}: {val}"
                        for col, val in zip(headers, row)
                        if str(val).strip()
                    ]
                    if row_parts:
                        rows_text_lines.append(" | ".join(row_parts))

                if not rows_text_lines:
                    # All rows in this batch were entirely empty — skip
                    continue

                chunk_text = (
                    f"Sheet: {sheet_name}\n"
                    f"Columns: {header_str}\n\n"
                    + "\n".join(rows_text_lines)
                )

                chunks.append(
                    {
                        "text": chunk_text,
                        "metadata": {
                            "sheet_name": sheet_name,
                            "row_start": start,
                            "row_end": start + len(batch) - 1,
                            "total_rows": total_rows,
                            "column_count": len(headers),
                            "source_type": "spreadsheet",
                        },
                    }
                )

        return chunks


class DocumentProcessor:
    """
    Orchestrates document processing with status tracking and deduplication.

    Coordinates DocumentParser, SemanticChunker, and SchemaParser to process
    files while maintaining processing status in SQLite and handling duplicates.
    """

    # File extensions that should use SchemaParser instead of DocumentParser
    SCHEMA_EXTENSIONS = {".sql", ".ddl"}

    # File extensions that should use SpreadsheetParser
    SPREADSHEET_EXTENSIONS = {".csv", ".xls", ".xlsx"}

    def __init__(
        self,
        chunk_size_chars: int = 2000,
        chunk_overlap_chars: int = 200,
        vector_store: Optional[VectorStore] = None,
        embedding_service: Optional[EmbeddingService] = None,
        pool: Optional["SQLiteConnectionPool"] = None,
        llm_client: Optional[LLMClient] = None,
        contextual_chunker: Optional[ContextualChunker] = None,
    ):
        """
        Initialize the document processor.

        Args:
            chunk_size_chars: Target chunk size in characters for semantic chunking
            chunk_overlap_chars: Overlap between chunks in characters
            vector_store: VectorStore instance for storing chunk embeddings
            embedding_service: EmbeddingService instance for generating embeddings
            pool: SQLiteConnectionPool instance for database connections
            llm_client: LLMClient instance for contextual chunking (optional)
            contextual_chunker: Pre-configured ContextualChunker instance (optional)
        """
        self.parser = DocumentParser()
        self.chunker = SemanticChunker(
            chunk_size_chars=chunk_size_chars, chunk_overlap_chars=chunk_overlap_chars
        )
        self.schema_parser = SchemaParser()
        self.spreadsheet_parser = SpreadsheetParser()
        # Fallback to creating a pool from settings if not provided
        if pool is None:
            pool = get_pool(str(settings.sqlite_path), max_size=2)
        self.pool = pool
        self.vector_store = vector_store
        self.embedding_service = embedding_service
        self._llm_client = llm_client
        self._contextual_chunker = contextual_chunker
        self._chunk_enrichment_service: Optional[ChunkEnrichmentService] = None

    def _get_contextual_chunker(self) -> Optional[ContextualChunker]:
        """
        Lazily create a ContextualChunker when needed.

        Returns:
            ContextualChunker instance if contextual_chunking_enabled is True
            and llm_client exists, None otherwise.
        """
        if not settings.contextual_chunking_enabled:
            return None
        if self._llm_client is None:
            logger.warning("Contextual chunking enabled but no LLM client available")
            return None
        if self._contextual_chunker is None:
            self._contextual_chunker = ContextualChunker(self._llm_client)
        return self._contextual_chunker

    def _get_chunk_enrichment_service(self) -> Optional[ChunkEnrichmentService]:
        """Lazily create a ChunkEnrichmentService when needed."""
        if not settings.chunk_enrichment_enabled:
            return None
        if self._llm_client is None:
            logger.warning("Chunk enrichment enabled but no LLM client available")
            return None
        if self._chunk_enrichment_service is None:
            fields = [f.strip() for f in settings.chunk_enrichment_fields.split(",")]
            self._chunk_enrichment_service = ChunkEnrichmentService(
                llm_client=self._llm_client,
                concurrency=settings.chunk_enrichment_concurrency,
                enrichment_fields=fields,
            )
        return self._chunk_enrichment_service

    @staticmethod
    def _build_chunk_uid(file_id: int, chunk: ProcessedChunk) -> str:
        """Build a chunk_uid consistent with vector store record construction."""
        chunk_scale = chunk.metadata.get("chunk_scale", "default")
        if settings.multi_scale_indexing_enabled and chunk_scale != "default":
            chunk_index_value = chunk.metadata.get("chunk_index", chunk.chunk_index)
            if isinstance(chunk_index_value, str) and "_" in chunk_index_value:
                return f"{file_id}_{chunk_index_value}"
            return f"{file_id}_{chunk_scale}_{chunk.chunk_index}"
        return f"{file_id}_{chunk.chunk_index}"

    @with_retry(
        max_attempts=3, retry_exceptions=(sqlite3.Error,), raise_last_exception=True
    )
    def _check_duplicate(
        self, file_hash: str, conn: sqlite3.Connection, vault_id: int
    ) -> Optional[sqlite3.Row]:
        """
        Check if a file with the given hash already exists and is indexed.

        Args:
            file_hash: The hash of the file to check
            conn: Database connection
            vault_id: The vault ID to check for duplicates in (defaults to 1)

        Returns:
            The existing file row if found and indexed, None otherwise
        """
        cursor = conn.execute(
            "SELECT * FROM files WHERE file_hash = ? AND vault_id = ? AND status = 'indexed'",
            (file_hash, vault_id),
        )
        return cursor.fetchone()

    @with_retry(
        max_attempts=3, retry_exceptions=(sqlite3.Error,), raise_last_exception=True
    )
    def _insert_or_get_file_record(
        self,
        file_path: str,
        file_hash: str,
        conn: sqlite3.Connection,
        vault_id: int,
        source: str = "upload",
        email_subject: Optional[str] = None,
        email_sender: Optional[str] = None,
    ) -> int:
        """
        Insert a new file record or update existing one, returning the file ID.

        Args:
            file_path: Path to the file
            file_hash: Computed hash of the file
            conn: Database connection
            vault_id: The vault ID for the file (defaults to 1)
            source: Source of the file ('upload', 'scan', 'email')
            email_subject: Subject line for email-sourced files
            email_sender: Sender address for email-sourced files

        Returns:
            The file ID (database row ID)

        Raises:
            DocumentProcessingError: If database operations fail
        """
        path = Path(file_path)
        file_name = path.name
        file_size = path.stat().st_size
        file_type = path.suffix.lower() if path.suffix else None
        now = datetime.now(UTC).isoformat()
        path_str = str(file_path)

        try:
            # Check if file record already exists by path
            cursor = conn.execute(
                "SELECT id FROM files WHERE file_path = ?", (path_str,)
            )
            existing = cursor.fetchone()

            if existing:
                # Validate existing row id
                existing_id = existing["id"]
                if existing_id is None:
                    raise DocumentProcessingError(
                        f"Existing file record for '{path_str}' has invalid NULL id"
                    )
                file_id = int(existing_id)

                # Update existing record
                conn.execute(
                    """UPDATE files
                       SET file_hash = ?, file_size = ?, file_type = ?, vault_id = ?,
                           source = ?, email_subject = ?, email_sender = ?,
                           status = 'pending', error_message = NULL,
                           modified_at = ?, processed_at = NULL
                       WHERE id = ?""",
                    (
                        file_hash,
                        file_size,
                        file_type,
                        vault_id,
                        source,
                        email_subject,
                        email_sender,
                        now,
                        file_id,
                    ),
                )
            else:
                # Insert new record
                cursor = conn.execute(
                    """INSERT INTO files
                       (file_path, file_name, file_hash, file_size, file_type, vault_id,
                        source, email_subject, email_sender, status, created_at, modified_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)""",
                    (
                        path_str,
                        file_name,
                        file_hash,
                        file_size,
                        file_type,
                        vault_id,
                        source,
                        email_subject,
                        email_sender,
                        now,
                        now,
                    ),
                )
                lastrowid = cursor.lastrowid
                if lastrowid is None:
                    raise DocumentProcessingError(
                        f"Failed to insert file record for '{path_str}': lastrowid is None"
                    )
                file_id = int(lastrowid)

            # Commit within the context of this method
            conn.commit()
            return file_id

        except sqlite3.IntegrityError as e:
            conn.rollback()
            if "file_hash" in str(e).lower() or "unique" in str(e).lower():
                raise DuplicateFileError(
                    f"A file with the same content already exists in this vault"
                ) from e
            raise DocumentProcessingError(f"Database integrity error: {e}") from e
        except sqlite3.Error as e:
            # Rollback on error and wrap in DocumentProcessingError
            conn.rollback()
            raise DocumentProcessingError(
                f"Database error while inserting/updating file record for '{path_str}': {str(e)}"
            ) from e

    @with_retry(
        max_attempts=3, retry_exceptions=(sqlite3.Error,), raise_last_exception=True
    )
    def _update_status(
        self,
        file_id: int,
        status: str,
        conn: sqlite3.Connection,
        chunk_count: Optional[int] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """
        Update the processing status of a file.

        Args:
            file_id: The database ID of the file
            status: New status ('pending', 'processing', 'indexed', 'error')
            conn: Database connection
            chunk_count: Number of chunks produced (optional)
            error_message: Error message if status is 'error' (optional)

        Note:
            This method does not commit - caller is responsible for transaction management.
        """
        now = datetime.now(UTC).isoformat()

        if status == "indexed":
            conn.execute(
                """UPDATE files
                   SET status = ?, chunk_count = ?, processed_at = ?, modified_at = ?
                   WHERE id = ?""",
                (status, chunk_count, now, now, file_id),
            )
        elif status == "error":
            conn.execute(
                """UPDATE files
                   SET status = ?, error_message = ?, modified_at = ?
                   WHERE id = ?""",
                (status, error_message, now, file_id),
            )
        else:
            conn.execute(
                """UPDATE files
                   SET status = ?, modified_at = ?
                   WHERE id = ?""",
                (status, now, file_id),
            )
        # Note: No commit here - caller manages transactions

    def _is_schema_file(self, file_path: str) -> bool:
        """
        Check if a file should be processed as a schema file.

        Args:
            file_path: Path to the file

        Returns:
            True if the file has a schema extension (.sql, .ddl)
        """
        return Path(file_path).suffix.lower() in self.SCHEMA_EXTENSIONS

    def _is_spreadsheet_file(self, file_path: str) -> bool:
        """
        Check if a file should be processed as a spreadsheet.

        Args:
            file_path: Path to the file.

        Returns:
            True if the file has a spreadsheet extension (.csv, .xls, .xlsx).
        """
        return Path(file_path).suffix.lower() in self.SPREADSHEET_EXTENSIONS

    async def _process_spreadsheet_file(self, file_path: str) -> List[ProcessedChunk]:
        """
        Process a spreadsheet file using SpreadsheetParser.

        Runs the synchronous SpreadsheetParser.parse() in a thread pool to
        avoid blocking the event loop on large files.

        Args:
            file_path: Path to the .csv, .xls, or .xlsx file.

        Returns:
            List of ProcessedChunk objects, one per row-group per sheet.

        Raises:
            DocumentParseError: If SpreadsheetParser.parse() raises.
            DocumentProcessingError: If the file parses but produces no chunks
                (e.g., all sheets are empty).
        """
        sheet_chunks = await asyncio.to_thread(
            self.spreadsheet_parser.parse, file_path
        )

        if not sheet_chunks:
            raise DocumentProcessingError(
                f"Spreadsheet '{file_path}' contains no readable data. "
                "All sheets may be empty or all rows may be blank."
            )

        processed_chunks: List[ProcessedChunk] = []
        total = len(sheet_chunks)

        for idx, chunk_data in enumerate(sheet_chunks):
            chunk = ProcessedChunk(
                text=chunk_data["text"],
                metadata={
                    **chunk_data["metadata"],
                    "chunk_index": idx,
                    "total_chunks": total,
                    "chunk_scale": "default",  # Spreadsheet files bypass multi-scale
                },
                chunk_index=idx,
            )
            processed_chunks.append(chunk)

        return processed_chunks

    async def _process_schema_file(self, file_path: str) -> List[ProcessedChunk]:
        """
        Process a schema file using SchemaParser.

        Args:
            file_path: Path to the schema file

        Returns:
            List of ProcessedChunk objects
        """
        schema_chunks = await asyncio.to_thread(self.schema_parser.parse, file_path)

        processed_chunks = []
        for idx, chunk_data in enumerate(schema_chunks):
            chunk = ProcessedChunk(
                text=chunk_data["text"],
                metadata={
                    **chunk_data["metadata"],
                    "chunk_index": idx,
                    "total_chunks": len(schema_chunks),
                    "chunk_scale": "default",  # Schema files don't use multi-scale
                },
                chunk_index=idx,
            )
            processed_chunks.append(chunk)

        return processed_chunks

    async def _process_document_file(
        self, file_path: str, file_id: Optional[int] = None
    ) -> Tuple[List[ProcessedChunk], str]:
        """
        Process a document file using DocumentParser and SemanticChunker.

        Args:
            file_path: Path to the document file
            file_id: Database ID of the file (required for multi-scale indexing)

        Returns:
            Tuple of (List of ProcessedChunk objects, document text as string)
        """
        try:
            elements = await asyncio.wait_for(
                asyncio.to_thread(self.parser.parse, file_path),
                timeout=settings.document_parse_timeout,
            )
        except asyncio.TimeoutError:
            raise DocumentProcessingError(
                f"Document parsing timed out after {settings.document_parse_timeout}s: {file_path}"
            )
        # Join all element texts for use as context in contextual chunking
        document_text = "\n".join([str(e) for e in elements])

        # Check if multi-scale indexing is enabled
        if settings.multi_scale_indexing_enabled:
            # Parse chunk sizes from settings
            scale_strs = settings.multi_scale_chunk_sizes.split(",")
            scales = [int(s.strip()) for s in scale_strs if s.strip()]

            all_chunks = []
            for scale in scales:
                # Create chunker for this scale
                chunk_overlap = int(scale * settings.multi_scale_overlap_ratio)
                scale_chunker = SemanticChunker(
                    chunk_size_chars=scale, chunk_overlap_chars=chunk_overlap
                )

                # Chunk elements with this scale's chunker
                scale_chunks = await asyncio.to_thread(
                    scale_chunker.chunk_elements, elements
                )

                # Add chunk_scale metadata to each chunk
                for idx, chunk in enumerate(scale_chunks):
                    chunk.metadata["chunk_scale"] = str(scale)
                    # Use scale-aware index format for multi-scale
                    if file_id is not None:
                        chunk.metadata["chunk_index"] = f"{scale}_{idx}"

                all_chunks.extend(scale_chunks)

            total_chunks = len(all_chunks)
            scale_list = [str(s) for s in scales]
            logger.info(
                "Multi-scale chunking processed %d chunks across scales %s",
                total_chunks,
                scale_list,
            )

            return all_chunks, document_text
        else:
            # Existing single-scale behavior
            chunks = await asyncio.to_thread(self.chunker.chunk_elements, elements)
            return chunks, document_text

    async def process_file(
        self,
        file_path: str,
        vault_id: int,
        source: str = "upload",
        email_subject: Optional[str] = None,
        email_sender: Optional[str] = None,
    ) -> ProcessedDocument:
        """
        Process a file with status tracking and deduplication.

        Args:
            file_path: Path to the file to process
            vault_id: The vault ID to associate the file with (required — no default)
            source: Source of the file ('upload', 'scan', 'email')
            email_subject: Subject line for email-sourced files
            email_sender: Sender address for email-sourced files

        Returns:
            ProcessedDocument containing file_id and chunks

        Raises:
            FileNotFoundError: If the file does not exist
            DuplicateFileError: If a file with the same hash is already indexed
            DocumentParseError: If parsing fails
        """
        # Validate file exists
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if not path.is_file():
            raise FileNotFoundError(f"Path is not a file: {file_path}")

        # Compute file hash
        file_hash = compute_file_hash(file_path)

        # Phase 1: Quick DB operations - get connection, do quick ops, release
        conn = self.pool.get_connection()
        try:
            # Check for duplicates
            duplicate = self._check_duplicate(file_hash, conn, vault_id)
            if duplicate:
                raise DuplicateFileError(
                    f"File with hash {file_hash} already indexed as '{duplicate['file_path']}'"
                )

            # Insert or get file record (handles its own commit)
            file_id = self._insert_or_get_file_record(
                file_path,
                file_hash,
                conn,
                vault_id,
                source,
                email_subject,
                email_sender,
            )

            # Update status to processing
            self._update_status(file_id, "processing", conn)
            conn.commit()
        finally:
            # Release connection before long-running operations
            self.pool.release_connection(conn)

        # Phase 2: Long operations (NO connection held!)
        try:
            # Process the file based on type
            if self._is_schema_file(file_path):
                chunks = await self._process_schema_file(file_path)
                document_text = ""
            elif self._is_spreadsheet_file(file_path):
                chunks = await self._process_spreadsheet_file(file_path)
                document_text = " ".join(c.text for c in chunks)
            else:
                chunks, document_text = await self._process_document_file(
                    file_path, file_id
                )

            # Define source_filename here so it is available to both contextual
            # chunking and chunk enrichment below, regardless of which branches run.
            source_filename = Path(file_path).name

            # Apply contextual chunking if enabled
            if settings.contextual_chunking_enabled and chunks and document_text:
                chunker = self._get_contextual_chunker()
                if chunker is not None:
                    logger.info(
                        "Contextual chunking: processing %d chunks for %s",
                        len(chunks),
                        source_filename,
                    )
                    try:
                        await chunker.contextualize_chunks(
                            document_text=document_text,
                            chunks=chunks,
                            source_filename=source_filename,
                        )
                        logger.info(
                            "Contextual chunking: completed for %s (%d chunks contextualized)",
                            source_filename,
                            len(chunks),
                        )
                    except Exception as e:
                        logger.warning(
                            "Contextual chunking failed for %s: %s",
                            source_filename,
                            str(e),
                        )
                # else: _get_contextual_chunker already logged a warning if needed

            # Compute parent window offsets for small-to-big retrieval (Issue #12)
            # Run after contextual chunking so raw_text is the pre-enrichment text.
            # Only meaningful when document_text is available (not spreadsheets/schemas).
            if not document_text and chunks and settings.parent_retrieval_enabled:
                logger.debug(
                    "parent_retrieval_enabled but document_text unavailable for %s "
                    "(schema/spreadsheet files do not support parent windows)",
                    Path(file_path).name,
                )
            if document_text and chunks:
                try:
                    compute_parent_windows(
                        chunks,
                        document_text,
                        window_chars=settings.parent_window_chars,
                    )
                except Exception as e:
                    logger.warning(
                        "compute_parent_windows failed for %s: %s — parent offsets will be None",
                        Path(file_path).name,
                        e,
                    )

            if not chunks:
                raise DocumentProcessingError(
                    "No extractable content found in document. "
                    "The file may be empty, encrypted, or in an unsupported format."
                )

            # Chunk enrichment: generate auxiliary metadata (summary, questions, entities)
            enrichment_service = self._get_chunk_enrichment_service()
            if enrichment_service is not None:
                try:
                    chunk_dicts = [
                        {
                            "chunk_uid": self._build_chunk_uid(file_id, c),
                            "text": c.text,
                            "metadata": c.metadata,
                        }
                        for c in chunks
                    ]
                    enrichments = await enrichment_service.enrich_chunks(
                        chunk_dicts, document_title=source_filename
                    )
                    for chunk, enrichment in zip(chunks, enrichments):
                        chunk.metadata["enrichment"] = enrichment.to_dict()
                    logger.info(
                        "Chunk enrichment completed for %s: %d chunks enriched",
                        source_filename,
                        len(enrichments),
                    )
                except Exception as e:
                    logger.warning(
                        "Chunk enrichment failed for %s: %s",
                        source_filename,
                        str(e),
                    )

            # Generate embeddings and store in vector store
            if self.embedding_service is not None and self.vector_store is not None:
                # Skip embedding/indexing if no chunks (status indexed with 0 chunks is acceptable)
                if chunks:
                    # Filter out empty/whitespace-only chunks before embedding
                    chunks = [c for c in chunks if c.text and c.text.strip()]
                    if not chunks:
                        raise DocumentProcessingError(
                            "All chunks were empty after filtering. "
                            "The document may contain only whitespace or unsupported content."
                        )

                    # Extract texts from chunks
                    texts = [c.text for c in chunks]

                    # Generate dense embeddings (Harrier dense-only)
                    embeddings = await self.embedding_service.embed_batch(texts)
                    sparse_embeddings = [None] * len(chunks)

                    # Validate embeddings count matches chunks count
                    if len(embeddings) != len(chunks):
                        raise DocumentProcessingError(
                            f"Embedding count mismatch: expected {len(chunks)}, got {len(embeddings)}"
                        )
                    # Validate all embeddings are non-empty lists with consistent dimension
                    expected_dim = len(embeddings[0]) if embeddings[0] else 0
                    for i, emb in enumerate(embeddings):
                        if not emb or not isinstance(emb, list):
                            raise DocumentProcessingError(
                                f"Embedding {i} is empty or not a list"
                            )
                        if len(emb) != expected_dim:
                            raise DocumentProcessingError(
                                f"Embedding {i} has dimension {len(emb)}, expected {expected_dim}"
                            )
                    # Map chunks to records for vector store
                    records = []
                    for chunk, embedding, sparse_emb in zip(
                        chunks, embeddings, sparse_embeddings
                    ):
                        # Determine chunk_scale from metadata (set during chunking)
                        chunk_scale = chunk.metadata.get("chunk_scale", "default")

                        # Create chunk_uid for windowing support
                        chunk_uid = self._build_chunk_uid(file_id, chunk)

                        # Add chunk_uid to metadata for adjacent chunk lookups
                        chunk_metadata = chunk.metadata.copy()
                        chunk_metadata["chunk_uid"] = chunk_uid
                        chunk_metadata["file_id"] = str(file_id)
                        chunk_metadata["chunk_count"] = chunk.metadata.get(
                            "total_chunks", len(chunks)
                        )
                        # Ensure chunk_scale is included in metadata
                        chunk_metadata["chunk_scale"] = chunk_scale
                        # Preserve raw text when contextual chunking modified the text
                        if hasattr(chunk, "raw_text") and chunk.raw_text:
                            chunk_metadata["raw_text"] = chunk.raw_text

                        # Store parent window offsets + text in metadata (Issue #12)
                        if chunk.parent_window_start is not None:
                            chunk_metadata["parent_window_start"] = chunk.parent_window_start
                        if chunk.parent_window_end is not None:
                            chunk_metadata["parent_window_end"] = chunk.parent_window_end
                        if chunk.chunk_position is not None:
                            chunk_metadata["chunk_position"] = chunk.chunk_position
                        # Store parent window text for fast retrieval-time expansion
                        # (avoids re-parsing the document at query time)
                        if (
                            chunk.parent_window_start is not None
                            and chunk.parent_window_end is not None
                            and document_text
                        ):
                            chunk_metadata["parent_window_text"] = document_text[
                                chunk.parent_window_start : chunk.parent_window_end
                            ]

                        # For safe re-upload, prefix chunk IDs with the new file hash
                        # so old-generation chunks have distinguishable IDs (Issue #13)
                        if settings.reupload_safe_order:
                            record_id = f"{file_id}_{file_hash[:8]}_{chunk_scale}_{chunk.chunk_index}"
                        else:
                            record_id = chunk_uid

                        record = {
                            "id": record_id,
                            "text": chunk.text,
                            "file_id": str(file_id),
                            "chunk_index": chunk.chunk_index,
                            "vault_id": str(vault_id),
                            "chunk_scale": chunk_scale,
                            # Parent-document retrieval fields (Issue #12)
                            "parent_doc_id": str(file_id),
                            "parent_window_start": chunk.parent_window_start,
                            "parent_window_end": chunk.parent_window_end,
                            "chunk_position": chunk.chunk_position,
                            "metadata": json.dumps(chunk_metadata),
                            "embedding": embedding,
                        }
                        # Add sparse embedding if available (tri-vector mode)
                        if sparse_emb is not None:
                            try:
                                record["sparse_embedding"] = json.dumps(sparse_emb)
                            except (TypeError, ValueError) as e:
                                logger.warning(
                                    f"Failed to serialize sparse embedding: {e}"
                                )
                                record["sparse_embedding"] = None
                        records.append(record)

                    # Initialize vector table with embedding dimension and add chunks
                    embedding_dim = len(embeddings[0])
                    await self.vector_store.init_table(embedding_dim)

                    if settings.reupload_safe_order:
                        # Safe re-upload: insert new generation first, then delete old (Issue #13)
                        # Step 1+2: Insert new-generation chunks (hash-prefixed IDs)
                        await self.vector_store.add_chunks(records)
                        # Step 3: Delete old-generation chunks for this file
                        # (chunks whose IDs don't start with the new hash prefix)
                        deleted = await self.vector_store.delete_old_generation_by_file(
                            str(file_id), file_hash[:8]
                        )
                        if deleted > 0:
                            logger.info(
                                "Safe re-upload: deleted %d old-generation chunks for file_id=%s",
                                deleted,
                                file_id,
                            )
                    else:
                        # Legacy: delete-then-insert (not crash-safe, kept for compat)
                        await self.vector_store.delete_by_file(str(file_id))
                        await self.vector_store.add_chunks(records)
        except Exception as e:
            # Phase 3: Update status to error on failure
            # Get connection again to update error status
            conn = self.pool.get_connection()
            try:
                self._update_status(file_id, "error", conn, error_message=str(e))
                conn.commit()
            finally:
                self.pool.release_connection(conn)
            raise

        # Phase 3: Final DB operations - update status to indexed
        conn = self.pool.get_connection()
        try:
            self._update_status(file_id, "indexed", conn, chunk_count=len(chunks))
            conn.commit()
        finally:
            self.pool.release_connection(conn)

        return ProcessedDocument(file_id=file_id, chunks=chunks)
