"""
LanceDB vector store service for semantic search.
"""

import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, cast
import lancedb
import pyarrow as pa
import numpy as np
import logging

from app.config import settings
from app.utils.fusion import rrf_fuse
from lancedb.index import IvfPq, FTS

logger = logging.getLogger(__name__)

# Multi-scale search concurrency limit
_MULTI_SCALE_CONCURRENCY = 4

# Minimum rows before creating vector index (deferred creation)
VECTOR_INDEX_MIN_ROWS = 256


def _lance_escape(value) -> str:
    """Escape a value for use in LanceDB SQL-like where clauses.

    Uses SQL-standard doubled single-quote escaping consistently.
    """
    return str(value).replace("'", "''")


class VectorStoreError(Exception):
    """Custom exception for vector store errors."""

    pass


class VectorStoreConnectionError(VectorStoreError):
    """Exception raised when connection to LanceDB fails."""

    pass


class VectorStoreValidationError(VectorStoreError):
    """Exception raised when record validation fails."""

    pass


class VectorStore:
    """LanceDB-based vector store for document chunk embeddings."""

    def __init__(self, db_path: Optional[Path] = None):
        """
        Initialize the vector store.

        Args:
            db_path: Path to LanceDB database. Defaults to settings.lancedb_path.
        """
        self.db_path = db_path or settings.lancedb_path
        self.db: Optional[lancedb.AsyncConnection] = None
        self.table: Optional[lancedb.table.AsyncTable] = None
        self._embedding_dim: Optional[int] = None

    async def connect(self) -> "VectorStore":
        """Connect to LanceDB.

        Raises:
            VectorStoreConnectionError: If connection to LanceDB fails.
        """
        try:
            self.db = await lancedb.connect_async(str(self.db_path))
        except (OSError, RuntimeError, ValueError) as e:
            raise VectorStoreConnectionError(
                f"Failed to connect to LanceDB at {self.db_path}: {e}"
            ) from e
        return self

    async def init_table(self, embedding_dim: int) -> "VectorStore":
        """
        Initialize or open the 'chunks' table.

        Args:
            embedding_dim: Dimension of embedding vectors.

        Returns:
            Self for method chaining.

        Raises:
            VectorStoreConnectionError: If connection or table operations fail.
        """
        if self.db is None:
            await self.connect()

        if self.db is None:
            raise VectorStoreConnectionError("Database connection is not available.")

        self._embedding_dim = embedding_dim
        table_just_created = False

        # Define schema for chunks table
        schema = pa.schema(
            [
                ("id", pa.string()),
                ("text", pa.string()),
                ("file_id", pa.string()),
                ("vault_id", pa.string()),  # Vault isolation
                ("chunk_index", pa.int32()),
                (
                    "chunk_scale",
                    pa.string(),
                ),  # Scale label like "512", "1024", "default"
                (
                    "sparse_embedding",
                    pa.string(),
                ),  # JSON string for sparse vectors (BGE-M3)
                ("metadata", pa.string()),  # JSON string for flexibility
                ("embedding", pa.list_(pa.float32(), embedding_dim)),
            ]
        )

        # Create or open table with error handling
        try:
            table_names = await self.db.table_names()
            if "chunks" in table_names:
                try:
                    self.table = await self.db.open_table("chunks")
                except (OSError, RuntimeError, ValueError):
                    # Stale table reference — drop and recreate
                    try:
                        await self.db.drop_table("chunks")
                    except (OSError, RuntimeError, ValueError):
                        pass
                    self.table = await self.db.create_table(
                        "chunks", schema=schema, mode="overwrite"
                    )
                    table_just_created = True
            else:
                self.table = await self.db.create_table("chunks", schema=schema)
                table_just_created = True
        except (OSError, RuntimeError, ValueError) as e:
            raise VectorStoreConnectionError(
                f"Failed to initialize 'chunks' table: {e}"
            ) from e

        # Defer vector index creation until sufficient rows (FR-013)
        if table_just_created:
            logger.info(
                "Table created; vector index deferred until ≥%d rows",
                VECTOR_INDEX_MIN_ROWS,
            )

        # Create FTS index only if missing (FR-014)
        fts_index_exists = False
        try:
            indices = await self.table.list_indices()
            fts_index_exists = any(idx.name == "fts_text" for idx in indices)
        except (OSError, RuntimeError, ValueError):
            pass

        if not fts_index_exists:
            try:
                await self.table.create_index(
                    column="text",
                    config=FTS(),
                    replace=False,
                )
                logger.info("Full-text search index created on 'text' column")
            except (OSError, RuntimeError, ValueError) as e:
                logger.warning(
                    f"FTS index creation failed (hybrid search will be unavailable): {e}"
                )
        else:
            logger.debug("FTS index already exists, skipping creation")

        return self

    async def _get_expected_embedding_dim(self) -> Optional[int]:
        """Get the expected embedding dimension from the table schema."""
        if self.table is None:
            return self._embedding_dim

        try:
            schema = await self.table.schema()
            embedding_field = schema.field("embedding")
            if hasattr(embedding_field.type, "list_size"):
                return embedding_field.type.list_size
        except (AttributeError, KeyError, IndexError):
            # Schema access or field lookup failed
            pass
        return self._embedding_dim

    async def _maybe_create_vector_index(self) -> None:
        """Conditionally create vector ANN index if conditions are met.

        Checks:
        1. Skip if embedding_idx already exists (fast path)
        2. Skip if row count < VECTOR_INDEX_MIN_ROWS (256)
        3. Create index with num_partitions=256, num_sub_vectors=96
        """
        if self.table is None:
            return

        # Fast path: check if index already exists
        try:
            indices = await self.table.list_indices()
            if any(idx.name == "embedding_idx" for idx in indices):
                logger.debug("Vector index already exists, skipping creation")
                return
        except (OSError, RuntimeError, ValueError) as e:
            logger.debug("Could not check existing indices: %s", e)

        # Check row count
        try:
            row_count = await self.table.count_rows()
        except (OSError, RuntimeError, ValueError) as e:
            logger.debug("Could not get row count: %s", e)
            return

        if row_count < VECTOR_INDEX_MIN_ROWS:
            logger.debug(
                "Vector index deferred: %d rows < %d threshold",
                row_count,
                VECTOR_INDEX_MIN_ROWS,
            )
            return

        # Create the index
        try:
            await self.table.create_index(
                column="embedding",
                config=IvfPq(
                    distance_type=cast(
                        "Literal['l2', 'cosine', 'dot']", settings.vector_metric
                    ),
                    num_partitions=256,
                    num_sub_vectors=96,
                ),
                replace=True,
            )
            logger.info(
                "Vector index created with metric=%s (%d rows)",
                settings.vector_metric,
                row_count,
            )
        except (OSError, RuntimeError, ValueError) as e:
            logger.warning("Vector index creation failed: %s", e)

    async def add_chunks(self, records: List[Dict[str, Any]]) -> None:
        """
        Add chunk records to the vector store.

        Args:
            records: List of records with keys: id, text, file_id, chunk_index,
                     metadata, embedding, vault_id (optional, defaults to "1").

        Raises:
            RuntimeError: If table is not initialized.
            VectorStoreValidationError: If records validation fails.
        """
        if self.table is None:
            raise RuntimeError("Table not initialized. Call init_table() first.")

        # Handle empty records
        if not records:
            return

        # Get expected embedding dimension from table schema
        expected_dim = await self._get_expected_embedding_dim()

        # Required fields for validation
        required_fields = ["id", "text", "file_id", "chunk_index", "embedding"]

        # Convert records to arrow-compatible format
        processed_records = []
        for record in records:
            # Validate required fields
            missing_fields = [field for field in required_fields if field not in record]
            if missing_fields:
                raise VectorStoreValidationError(
                    f"Record missing required fields: {', '.join(missing_fields)}"
                )

            # Ensure embedding is a list (convert from numpy if needed)
            embedding = record["embedding"]
            if isinstance(embedding, np.ndarray):
                embedding = embedding.tolist()
            elif not isinstance(embedding, list):
                raise VectorStoreValidationError(
                    f"Embedding must be a list or numpy array, got {type(embedding).__name__}"
                )

            # Validate embedding dimension matches table schema
            actual_dim = len(embedding)
            if expected_dim is not None and actual_dim != expected_dim:
                raise VectorStoreValidationError(
                    f"Embedding dimension mismatch: expected {expected_dim} dimensions, "
                    f"got {actual_dim}. The table was created with a different embedding model. "
                    f"Delete the lancedb directory at {self.db_path} and restart to use the new model."
                )

            processed_record = {
                "id": record["id"],
                "text": record["text"],
                "file_id": record["file_id"],
                "vault_id": record.get("vault_id", "1"),  # Default to vault "1"
                "chunk_index": record["chunk_index"],
                "chunk_scale": record.get("chunk_scale", "default"),  # Scale label
                "sparse_embedding": record.get(
                    "sparse_embedding"
                ),  # JSON string for sparse vectors
                "metadata": record.get("metadata", "{}"),
                "embedding": embedding,
            }

            # Validate sparse_embedding JSON format if provided
            sparse_emb = processed_record.get("sparse_embedding")
            if sparse_emb is not None:
                try:
                    json.loads(sparse_emb)  # Validate it's valid JSON
                except json.JSONDecodeError:
                    raise VectorStoreValidationError(
                        "sparse_embedding must be valid JSON"
                    )
            processed_records.append(processed_record)

        await self.table.add(processed_records)

        # Check if we should create the vector index after adding chunks
        await self._maybe_create_vector_index()

    async def _search_single_scale(
        self,
        embedding: List[float],
        scale: str,
        fetch_k: int,
        filter_expr: Optional[str] = None,
        vault_id: Optional[str] = None,
        query_text: str = "",
        hybrid: bool = True,
        query_sparse: Optional[dict] = None,
        hybrid_alpha: float = 0.5,
    ) -> List[Dict[str, Any]]:
        """
        Search within a single chunk scale.

        Args:
            embedding: Query embedding vector.
            scale: The chunk_scale value to filter by (e.g., "512", "1024", "default").
            fetch_k: Number of results to fetch per search type.
            filter_expr: Optional additional filter expression.
            vault_id: Optional vault ID to filter results.
            query_text: Raw query text for BM25 FTS search.
            hybrid: If True, combine dense vector search with BM25 FTS using RRF.

        Returns:
            List of matching records for this scale with RRF scores.
        """
        if self.table is None:
            return []

        # Build scale filter
        safe_scale = _lance_escape(scale)
        scale_filter = f"chunk_scale = '{safe_scale}'"

        # Combine with vault filter if present
        if vault_id is not None:
            safe_vault_id = _lance_escape(vault_id)
            vault_filter = f"vault_id = '{safe_vault_id}'"
            if filter_expr:
                combined_filter = (
                    f"({filter_expr}) AND ({scale_filter}) AND ({vault_filter})"
                )
            else:
                combined_filter = f"{scale_filter} AND ({vault_filter})"
        elif filter_expr:
            combined_filter = f"({filter_expr}) AND ({scale_filter})"
        else:
            combined_filter = scale_filter

        # Dense vector search with scale filter
        query = await self.table.search(embedding)
        if combined_filter:
            query = query.where(combined_filter)
        dense_results = await query.limit(fetch_k).to_list()

        # If hybrid disabled, return dense results only
        if not hybrid or not query_text:
            return dense_results

        # Run search based on query_sparse availability
        if query_sparse is not None:
            # Use sparse retrieval instead of BM25 FTS
            sparse_results = await self._sparse_search(
                query_sparse=query_sparse,
                limit=fetch_k,
                vault_id=vault_id,
                filter_expr=combined_filter if filter_expr else scale_filter,
                scale=scale,
            )

            # RRF Fusion for this scale with dense + sparse
            k_rrf = 60
            rrf_scores: dict = {}
            id_to_record: dict = {}

            for rank, record in enumerate(dense_results):
                uid = record.get("id", f"dense_{rank}")
                rrf_scores[uid] = rrf_scores.get(uid, 0.0) + (1.0 - hybrid_alpha) / (
                    k_rrf + rank + 1
                )
                id_to_record[uid] = record

            for rank, record in enumerate(sparse_results):
                uid = record.get("id", f"sparse_{rank}")
                # Apply hybrid_alpha: dense gets (1-alpha), sparse gets alpha
                rrf_scores[uid] = rrf_scores.get(uid, 0.0) + hybrid_alpha * 1.0 / (
                    k_rrf + rank + 1
                )
                if uid not in id_to_record:
                    id_to_record[uid] = record

            result_list = []
            for uid in rrf_scores:
                record = dict(id_to_record[uid])
                record["_rrf_score"] = rrf_scores[uid]
                result_list.append(record)
            return result_list
        else:
            # Use BM25 FTS (existing code)
            try:
                fts_query = await self.table.search(query_text)
                fts_filter_parts = [scale_filter]
                if vault_id:
                    safe_vault_id = _lance_escape(vault_id)
                    fts_filter_parts.append(f"vault_id = '{safe_vault_id}'")
                if filter_expr:
                    fts_filter_parts.append(f"({filter_expr})")
                fts_combined_filter = " AND ".join(f"({f})" for f in fts_filter_parts)
                fts_query = fts_query.where(fts_combined_filter)
                fts_results = await fts_query.limit(fetch_k).to_list()
            except Exception as e:
                logger.warning(
                    f"FTS search failed for scale {scale} (falling back to dense-only): {e}"
                )
                fts_results = []

            # RRF Fusion for this scale
            k_rrf = 60
            rrf_scores: dict = {}
            id_to_record: dict = {}

            for rank, record in enumerate(dense_results):
                uid = record.get("id", f"dense_{rank}")
                rrf_scores[uid] = rrf_scores.get(uid, 0.0) + 1.0 / (k_rrf + rank + 1)
                id_to_record[uid] = record

            for rank, record in enumerate(fts_results):
                uid = record.get("id", f"fts_{rank}")
                rrf_scores[uid] = rrf_scores.get(uid, 0.0) + 1.0 / (k_rrf + rank + 1)
                if uid not in id_to_record:
                    id_to_record[uid] = record

            # Return results with RRF scores (unsorted, to be sorted in cross-scale RRF)
            result_list = []
            for uid in rrf_scores:
                record = dict(id_to_record[uid])
                record["_rrf_score"] = rrf_scores[uid]
                result_list.append(record)
            return result_list

    async def _sparse_search(
        self,
        query_sparse: dict,
        limit: int,
        vault_id: Optional[str] = None,
        filter_expr: Optional[str] = None,
        scale: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Compute dot-product similarity between query sparse vector and stored sparse embeddings.

        Fetches candidates from LanceDB where sparse_embedding IS NOT NULL, computes
        dot-product scores, and returns top results sorted by score descending.

        Falls back to empty list on any error (e.g. missing sparse_embedding column).
        """
        if self.table is None:
            return []

        try:
            filter_parts = ["sparse_embedding IS NOT NULL"]
            if vault_id is not None:
                safe_vault_id = _lance_escape(vault_id)
                filter_parts.append(f"vault_id = '{safe_vault_id}'")
            if scale is not None:
                safe_scale = _lance_escape(scale)
                filter_parts.append(f"chunk_scale = '{safe_scale}'")
            if filter_expr:
                filter_parts.append(f"({filter_expr})")
            combined_filter = " AND ".join(filter_parts)

            max_candidates = settings.sparse_search_max_candidates
            candidates = (
                await (await self.table.search())
                .where(combined_filter)
                .limit(max_candidates)
                .to_list()
            )

            scored = []
            for record in candidates:
                sparse_str = record.get("sparse_embedding")
                if not sparse_str:
                    continue
                try:
                    doc_sparse = json.loads(sparse_str)
                except (ValueError, TypeError):
                    continue
                score = sum(query_sparse.get(k, 0.0) * v for k, v in doc_sparse.items())
                rec = dict(record)
                rec["_sparse_score"] = score
                scored.append(rec)

            scored.sort(key=lambda r: r["_sparse_score"], reverse=True)
            return scored[:limit]
        except Exception as exc:
            logger.warning("Sparse search failed (returning empty): %s", exc)
            return []

    async def search(
        self,
        embedding: List[float],
        limit: int = 10,
        filter_expr: Optional[str] = None,
        vault_id: Optional[str] = None,
        query_text: str = "",
        hybrid: bool = True,
        hybrid_alpha: float = 0.5,
        query_sparse: Optional[dict] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search for similar chunks by embedding.

        Args:
            embedding: Query embedding vector.
            limit: Maximum number of results.
            filter_expr: Optional filter expression (LanceDB syntax).
            vault_id: Optional vault ID to filter results. If provided, only returns
                      chunks from the specified vault.
            query_text: Raw query text for BM25 FTS search (used in hybrid search).
            hybrid: If True, combine dense vector search with BM25 FTS using RRF.
            hybrid_alpha: Weight controlling the balance between dense and sparse retrieval in hybrid search (dense gets weight 1-alpha, sparse gets alpha).

        Returns:
            List of matching records with similarity scores. Each record includes:
            - All original fields (id, text, file_id, chunk_index, metadata, etc.)
            - _distance: Cosine distance from query embedding (lower = more similar)
            - _rrf_score: Reciprocal Rank Fusion score (when hybrid=True)
            Empty list if no table exists.

        Note:
            For cosine distance metric:
            - Distance of 0 = identical vectors (perfect match)
            - Distance of 1 = orthogonal vectors
            - Distance of 2 = opposite vectors (perfect mismatch)
            The _distance field is provided by LanceDB's vector search.
        """
        # Ensure DB connection exists
        if self.db is None:
            await self.connect()

        # Try to open existing table if not already loaded
        if self.table is None:
            try:
                table_names = await self.db.table_names()
            except (OSError, RuntimeError, ValueError) as e:
                raise VectorStoreConnectionError(
                    f"Failed to list table names: {e}"
                ) from e

            if "chunks" not in table_names:
                # No table exists yet - graceful no-docs behavior
                return []

            # Table exists, try to open it
            try:
                self.table = await self.db.open_table("chunks")
            except (OSError, RuntimeError, ValueError) as e:
                raise VectorStoreConnectionError(
                    f"Failed to open 'chunks' table: {e}"
                ) from e

            # Set embedding_dim from table schema if available
            if self._embedding_dim is None:
                try:
                    schema = await self.table.schema()
                    embedding_field = schema.field("embedding")
                    # Extract dimension from fixed size list type
                    if hasattr(embedding_field.type, "list_size"):
                        self._embedding_dim = embedding_field.type.list_size
                except (AttributeError, KeyError, IndexError, TypeError):
                    # If we can't determine embedding_dim, leave it as None
                    pass

        # Check if vector index should be created (deferred index creation)
        await self._maybe_create_vector_index()

        # Check for multi-scale search
        fetch_k = limit * 2

        if settings.multi_scale_indexing_enabled and settings.multi_scale_chunk_sizes:
            # Parse scale sizes
            scale_strs = [
                s.strip()
                for s in settings.multi_scale_chunk_sizes.split(",")
                if s.strip()
            ]

            if len(scale_strs) > 1:
                # Multi-scale search: query each scale with limited concurrency
                # and perform cross-scale RRF
                semaphore = asyncio.Semaphore(_MULTI_SCALE_CONCURRENCY)

                async def _sem_search_single_scale(scale: str) -> List[Dict[str, Any]]:
                    """Semaphore-guarded wrapper for _search_single_scale."""
                    async with semaphore:
                        return await self._search_single_scale(
                            embedding=embedding,
                            scale=scale,
                            fetch_k=fetch_k,
                            filter_expr=filter_expr,
                            vault_id=vault_id,
                            query_text=query_text,
                            hybrid=hybrid,
                            query_sparse=query_sparse,
                            hybrid_alpha=hybrid_alpha,
                        )

                # Create tasks for parallel execution (concurrency limited by semaphore)
                search_tasks = [_sem_search_single_scale(scale) for scale in scale_strs]

                # Execute all scale searches with limited concurrency
                scale_results_list = await asyncio.gather(
                    *search_tasks, return_exceptions=True
                )

                # Collect results from successful searches
                all_scale_results: List[Dict[str, Any]] = []
                for i, scale_results in enumerate(scale_results_list):
                    if isinstance(scale_results, list):
                        all_scale_results.extend(scale_results)
                    else:
                        logger.warning(
                            f"Search failed for scale {scale_strs[i]}: {scale_results}"
                        )

                # Cross-scale RRF fusion
                k_rrf = 60
                cross_scale_scores: dict = {}
                id_to_record: dict = {}

                # Add results from each scale with their RRF contributions
                for rank, record in enumerate(all_scale_results):
                    uid = record.get("id", f"scale_{rank}")
                    # Use the per-scale RRF score as contribution
                    scale_rrf = record.get("_rrf_score", 0.0)
                    cross_scale_scores[uid] = (
                        cross_scale_scores.get(uid, 0.0) + scale_rrf
                    )
                    if uid not in id_to_record:
                        id_to_record[uid] = record

                # Sort by cross-scale RRF score and return top limit
                sorted_uids = sorted(
                    cross_scale_scores,
                    key=lambda u: cross_scale_scores[u],
                    reverse=True,
                )
                fused = []
                for uid in sorted_uids[:limit]:
                    record = dict(id_to_record[uid])
                    record["_rrf_score"] = cross_scale_scores[uid]
                    fused.append(record)

                logger.info(
                    f"Multi-scale search: queried {len(scale_strs)} scales, "
                    f"returning {len(fused)} results"
                )
                return fused

        # Single-scale or multi-scale disabled: use existing behavior

        if self.table is None:
            return []

        # Dense vector search
        query = await self.table.search(embedding)

        # Apply vault filter if specified
        _filter_expr = filter_expr
        if vault_id is not None:
            safe_vault_id = _lance_escape(vault_id)
            vault_filter = f"vault_id = '{safe_vault_id}'"
            if _filter_expr:
                _filter_expr = f"({_filter_expr}) AND ({vault_filter})"
            else:
                _filter_expr = vault_filter

        if _filter_expr:
            query = query.where(_filter_expr)

        dense_results = await query.limit(fetch_k).to_list()

        # If hybrid disabled, return dense results only
        if not hybrid or not query_text:
            return dense_results

        # Run search based on query_sparse availability
        if query_sparse is not None:
            # Use sparse retrieval instead of BM25 FTS
            sparse_results = await self._sparse_search(
                query_sparse=query_sparse,
                limit=fetch_k,
                vault_id=vault_id,
                filter_expr=filter_expr,
            )
            # Apply hybrid_alpha weighting in RRF
            return rrf_fuse(
                [dense_results, sparse_results],
                k=60,
                limit=limit,
                weights=[1.0 - hybrid_alpha, hybrid_alpha],
            )
        else:
            # Use BM25 FTS (existing code)
            try:
                fts_query = await self.table.search(query_text)  # LanceDB FTS
                if vault_id:
                    fts_query = fts_query.where(f"vault_id = '{vault_id}'")
                if filter_expr:
                    # FTS doesn't support complex filter_expr, apply basic vault filter only
                    fts_query = fts_query.where(filter_expr)
                fts_results = await fts_query.limit(fetch_k).to_list()
            except (OSError, RuntimeError, ValueError) as e:
                logger.warning(f"FTS search failed (falling back to dense-only): {e}")
                fts_results = []

            # RRF Fusion using shared utility
            return rrf_fuse([dense_results, fts_results], k=60, limit=limit)

    async def delete_by_file(self, file_id: str) -> int:
        """
        Delete all chunks for a given file_id.

        Args:
            file_id: The file ID to delete chunks for.

        Returns:
            Number of records deleted.
        """
        # Ensure DB connection exists
        if self.db is None:
            await self.connect()

        # Try to open existing table if not already loaded
        if self.table is None:
            try:
                table_names = await self.db.table_names()
            except (OSError, RuntimeError, ValueError) as e:
                raise VectorStoreConnectionError(
                    f"Failed to list table names: {e}"
                ) from e

            if "chunks" not in table_names:
                # No table exists yet - nothing to delete
                return 0

            # Table exists, try to open it
            try:
                self.table = await self.db.open_table("chunks")
            except (OSError, RuntimeError, ValueError) as e:
                raise VectorStoreConnectionError(
                    f"Failed to open 'chunks' table: {e}"
                ) from e

            # Set embedding_dim from table schema if available
            if self._embedding_dim is None:
                try:
                    schema = await self.table.schema()
                    embedding_field = schema.field("embedding")
                    # Extract dimension from fixed size list type
                    if hasattr(embedding_field.type, "list_size"):
                        self._embedding_dim = embedding_field.type.list_size
                except (AttributeError, KeyError, IndexError, TypeError):
                    # If we can't determine embedding_dim, leave it as None
                    pass

        if self.table is None:
            return 0

        # Query count before delete to return accurate deletion count
        safe_file_id = str(file_id).replace('"', '\\"')
        try:
            count_before = await self.table.count_rows(f'file_id = "{safe_file_id}"')
        except (OSError, RuntimeError, ValueError):
            # If count_rows fails, safely default to 0
            count_before = 0

        # LanceDB delete using filter expression
        await self.table.delete(f'file_id = "{safe_file_id}"')

        return count_before

    async def delete_by_vault(self, vault_id: str) -> int:
        """
        Delete all chunks for a given vault_id.

        Args:
            vault_id: The vault ID to delete all chunks for.

        Returns:
            Number of records deleted.
        """
        # Ensure DB connection exists
        if self.db is None:
            await self.connect()

        # Try to open existing table if not already loaded
        if self.table is None:
            try:
                table_names = await self.db.table_names()
            except (OSError, RuntimeError, ValueError) as e:
                raise VectorStoreConnectionError(
                    f"Failed to list table names: {e}"
                ) from e

            if "chunks" not in table_names:
                return 0

            try:
                self.table = await self.db.open_table("chunks")
            except (OSError, RuntimeError, ValueError) as e:
                raise VectorStoreConnectionError(
                    f"Failed to open 'chunks' table: {e}"
                ) from e

        if self.table is None:
            return 0

        safe_vault_id = _lance_escape(vault_id)
        try:
            count_before = await self.table.count_rows(f"vault_id = '{safe_vault_id}'")
        except (OSError, RuntimeError, ValueError):
            count_before = 0

        await self.table.delete(f"vault_id = '{safe_vault_id}'")
        return count_before

    async def migrate_add_vault_id(self) -> int:
        """
        Migration: Backfill vault_id='1' on existing chunks that lack it.

        LanceDB doesn't support ALTER TABLE or UPDATE, so this reads all data,
        adds the vault_id field, and rewrites the table. This is idempotent —
        safe to call multiple times (no-op if all records already have vault_id).

        Returns:
            Number of records migrated. 0 if no migration was needed.
        """
        if self.db is None:
            await self.connect()

        if self.db is None:
            logger.info("LanceDB vault_id migration: no connection available")
            return 0

        try:
            table_names = await self.db.table_names()
        except (OSError, RuntimeError, ValueError) as e:
            logger.warning(f"LanceDB vault_id migration failed: {e}")
            return 0

        if "chunks" not in table_names:
            logger.info("LanceDB vault_id migration: no table exists")
            return 0

        try:
            table = await self.db.open_table("chunks")
        except (OSError, RuntimeError, ValueError) as e:
            logger.warning(f"LanceDB vault_id migration failed: {e}")
            return 0

        # Check if vault_id column exists in schema
        schema = await table.schema()
        field_names = [schema.field(i).name for i in range(len(schema))]

        if "vault_id" in field_names:
            # Column exists — check if any rows have null vault_id
            try:
                df = await table.to_pandas()
                null_count = df["vault_id"].isna().sum()
                if null_count == 0:
                    logger.info("LanceDB vault_id migration: no migration needed")
                    return 0  # All records already have vault_id

                # Backfill null vault_ids with "1"
                df["vault_id"] = df["vault_id"].fillna("1")
                count = int(null_count)

                # Drop and recreate table with updated data
                await self.db.drop_table("chunks")
                try:
                    self.table = await self.db.create_table("chunks", data=df)
                except (OSError, RuntimeError, ValueError) as create_err:
                    logger.critical(
                        f"LanceDB vault_id migration: table dropped but recreate failed: {create_err}. Data may need manual recovery from backup."
                    )
                    raise
                logger.info(f"LanceDB vault_id migration: backfilled {count} records")
                return count
            except (OSError, RuntimeError, ValueError) as e:
                logger.warning(f"LanceDB vault_id migration failed: {e}")
                return 0
        else:
            # Column doesn't exist — add it to all records
            try:
                df = await table.to_pandas()
                if len(df) == 0:
                    # Empty table — just drop and recreate with new schema
                    # Try to get embedding_dim from existing schema before dropping
                    if self._embedding_dim is None:
                        try:
                            schema = await table.schema()
                            embedding_field = schema.field("embedding")
                            if hasattr(embedding_field.type, "list_size"):
                                self._embedding_dim = embedding_field.type.list_size
                        except (AttributeError, KeyError, IndexError, TypeError):
                            # If we can't determine embedding_dim, leave it as None
                            pass

                    await self.db.drop_table("chunks")
                    try:
                        if self._embedding_dim:
                            await self.init_table(self._embedding_dim)
                    except (OSError, RuntimeError, ValueError) as create_err:
                        logger.critical(
                            f"LanceDB vault_id migration: empty table dropped but recreate failed: {create_err}"
                        )
                        raise
                    logger.info(
                        "LanceDB vault_id migration: empty table, recreated with new schema"
                    )
                    return 0

                # Add vault_id column with default "1"
                df["vault_id"] = "1"
                migrated_count = len(df)

                # Drop and recreate table with updated data
                await self.db.drop_table("chunks")
                try:
                    self.table = await self.db.create_table("chunks", data=df)
                except (OSError, RuntimeError, ValueError) as create_err:
                    logger.critical(
                        f"LanceDB vault_id migration: table dropped but recreate failed: {create_err}. Data may need manual recovery from backup."
                    )
                    raise
                logger.info(
                    f"LanceDB vault_id migration: backfilled {migrated_count} records"
                )
                return migrated_count
            except (OSError, RuntimeError, ValueError) as e:
                logger.warning(f"LanceDB vault_id migration failed: {e}")
                return 0

    async def migrate_add_chunk_scale(self) -> int:
        """
        Migration: Backfill chunk_scale='default' on existing chunks that lack it.

        LanceDB doesn't support ALTER TABLE or UPDATE, so this reads all data,
        adds the chunk_scale field, and rewrites the table. This is idempotent —
        safe to call multiple times (no-op if all records already have chunk_scale).

        Returns:
            Number of records migrated. 0 if no migration was needed.
        """
        if self.db is None:
            await self.connect()

        if self.db is None:
            logger.info("LanceDB chunk_scale migration: no connection available")
            return 0

        try:
            table_names = await self.db.table_names()
        except (OSError, RuntimeError, ValueError) as e:
            logger.warning(f"LanceDB chunk_scale migration failed: {e}")
            return 0

        if "chunks" not in table_names:
            logger.info("LanceDB chunk_scale migration: no table exists")
            return 0

        try:
            table = await self.db.open_table("chunks")
        except (OSError, RuntimeError, ValueError) as e:
            logger.warning(f"LanceDB chunk_scale migration failed: {e}")
            return 0

        # Check if chunk_scale column exists in schema
        schema = await table.schema()
        field_names = [schema.field(i).name for i in range(len(schema))]

        if "chunk_scale" in field_names:
            # Column exists — check if any rows have null chunk_scale
            try:
                df = await table.to_pandas()
                null_count = df["chunk_scale"].isna().sum()
                if null_count == 0:
                    logger.info("LanceDB chunk_scale migration: no migration needed")
                    return 0  # All records already have chunk_scale

                # Backfill null chunk_scales with "default"
                df["chunk_scale"] = df["chunk_scale"].fillna("default")
                count = int(null_count)

                # Drop and recreate table with updated data
                await self.db.drop_table("chunks")
                try:
                    self.table = await self.db.create_table("chunks", data=df)
                except (OSError, RuntimeError, ValueError) as create_err:
                    logger.critical(
                        f"LanceDB chunk_scale migration: table dropped but recreate failed: {create_err}. Data may need manual recovery from backup."
                    )
                    raise
                logger.info(
                    f"LanceDB chunk_scale migration: backfilled {count} records"
                )
                return count
            except (OSError, RuntimeError, ValueError) as e:
                logger.warning(f"LanceDB chunk_scale migration failed: {e}")
                return 0
        else:
            # Column doesn't exist — add it to all records
            try:
                df = await table.to_pandas()
                if len(df) == 0:
                    # Empty table — just drop and recreate with new schema
                    # Try to get embedding_dim from existing schema before dropping
                    if self._embedding_dim is None:
                        try:
                            schema = await table.schema()
                            embedding_field = schema.field("embedding")
                            if hasattr(embedding_field.type, "list_size"):
                                self._embedding_dim = embedding_field.type.list_size
                        except (AttributeError, KeyError, IndexError, TypeError):
                            # If we can't determine embedding_dim, leave it as None
                            pass

                    await self.db.drop_table("chunks")
                    try:
                        if self._embedding_dim:
                            await self.init_table(self._embedding_dim)
                    except (OSError, RuntimeError, ValueError) as create_err:
                        logger.critical(
                            f"LanceDB chunk_scale migration: empty table dropped but recreate failed: {create_err}"
                        )
                        raise
                    logger.info(
                        "LanceDB chunk_scale migration: empty table, recreated with new schema"
                    )
                    return 0

                # Add chunk_scale column with default "default"
                df["chunk_scale"] = "default"
                migrated_count = len(df)

                # Drop and recreate table with updated data
                await self.db.drop_table("chunks")
                try:
                    self.table = await self.db.create_table("chunks", data=df)
                except (OSError, RuntimeError, ValueError) as create_err:
                    logger.critical(
                        f"LanceDB chunk_scale migration: table dropped but recreate failed: {create_err}. Data may need manual recovery from backup."
                    )
                    raise
                logger.info(
                    f"LanceDB chunk_scale migration: backfilled {migrated_count} records"
                )
                return migrated_count
            except (OSError, RuntimeError, ValueError) as e:
                logger.warning(f"LanceDB chunk_scale migration failed: {e}")
                return 0

    async def migrate_add_sparse_embedding(self) -> int:
        """
        Migration: Add sparse_embedding column to existing chunks table.

        LanceDB doesn't support ALTER TABLE, so this reads all data,
        adds the sparse_embedding field (default null), and rewrites the table.
        This is idempotent — safe to call multiple times.

        Returns:
            Number of records migrated. 0 if no migration was needed.
        """
        if self.db is None:
            await self.connect()

        if self.db is None:
            logger.info("LanceDB sparse_embedding migration: no connection available")
            return 0

        try:
            table_names = await self.db.table_names()
        except (OSError, RuntimeError, ValueError) as e:
            logger.warning(f"LanceDB sparse_embedding migration failed: {e}")
            return 0

        if "chunks" not in table_names:
            logger.info("LanceDB sparse_embedding migration: no table exists")
            return 0

        try:
            table = await self.db.open_table("chunks")
        except (OSError, RuntimeError, ValueError) as e:
            logger.warning(f"LanceDB sparse_embedding migration failed: {e}")
            return 0

        # Check if sparse_embedding column exists in schema
        schema = await table.schema()
        field_names = [schema.field(i).name for i in range(len(schema))]

        if "sparse_embedding" in field_names:
            logger.info("LanceDB sparse_embedding migration: column already exists")
            return 0

        # Column doesn't exist — add it to all records (default None/null)
        try:
            df = await table.to_pandas()
            if len(df) == 0:
                # Empty table — just drop and recreate with new schema
                if self._embedding_dim is None:
                    try:
                        schema = await table.schema()
                        embedding_field = schema.field("embedding")
                        if hasattr(embedding_field.type, "list_size"):
                            self._embedding_dim = embedding_field.type.list_size
                    except (AttributeError, KeyError, IndexError, TypeError):
                        # If we can't determine embedding_dim, leave it as None
                        pass

                # Explicit error if embedding_dim cannot be determined
                if self._embedding_dim is None:
                    raise VectorStoreError(
                        "Cannot determine embedding dimension for migration"
                    )

                await self.db.drop_table("chunks")
                try:
                    if self._embedding_dim:
                        await self.init_table(self._embedding_dim)
                except (OSError, RuntimeError, ValueError) as create_err:
                    logger.critical(
                        f"LanceDB sparse_embedding migration: empty table dropped but recreate failed: {create_err}"
                    )
                    raise
                logger.info(
                    "LanceDB sparse_embedding migration: empty table, recreated with new schema"
                )
                return 0

            # Add sparse_embedding column with default None (null)
            df["sparse_embedding"] = None
            migrated_count = len(df)

            # Drop and recreate table with updated data
            await self.db.drop_table("chunks")
            try:
                self.table = await self.db.create_table("chunks", data=df)
                # Recreate vector index
                await self.table.create_index(
                    column="embedding",
                    config=IvfPq(
                        distance_type=cast(
                            "Literal['l2', 'cosine', 'dot']", settings.vector_metric
                        ),
                        num_partitions=256,
                        num_sub_vectors=96,
                    ),
                    replace=True,
                )
                logger.info(
                    f"Vector index recreated with metric={settings.vector_metric}"
                )
                # Recreate FTS index
                await self.table.create_index(
                    column="text",
                    config=FTS(),
                    replace=True,
                )
                logger.info("Full-text search index recreated on 'text' column")
            except (OSError, RuntimeError, ValueError) as create_err:
                logger.critical(
                    f"LanceDB sparse_embedding migration: table dropped but recreate failed: {create_err}"
                )
                raise
            logger.info(
                f"LanceDB sparse_embedding migration: added column to {migrated_count} records"
            )
            return migrated_count
        except (OSError, RuntimeError, ValueError) as e:
            logger.warning(f"LanceDB sparse_embedding migration failed: {e}")
            return 0

    async def get_chunks_by_uid(self, chunk_uids: List[str]) -> List[Dict[str, Any]]:
        """
        Fetch chunks by their unique IDs.

        Args:
            chunk_uids: List of chunk UIDs in format "{file_id}_{chunk_index}"

        Returns:
            List of matching chunk records from LanceDB.
        """
        if self.table is None:
            return []

        if not chunk_uids:
            return []

        try:
            # Build IN clause for chunk_uids
            # Each uid is in format "{file_id}_{chunk_index}"
            # Escape single quotes in uids for SQL-like syntax
            escaped_uids = [_lance_escape(uid) for uid in chunk_uids]
            quoted_uids = [f"'{uid}'" for uid in escaped_uids]
            uid_list = ", ".join(quoted_uids)

            # Query chunks where id is in the list of chunk_uids
            query = f"id IN ({uid_list})"
            results = await (await self.table.search()).where(query).to_list()

            return results
        except (OSError, RuntimeError, ValueError) as e:
            logger.warning(f"Failed to fetch chunks by UID: {e}")
            return []

    async def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the vector store.

        Returns:
            Dictionary with stats like total chunks, embedding dimension.
        """
        if self.table is None:
            return {"total_chunks": 0, "embedding_dim": self._embedding_dim}

        return {
            "total_chunks": await self.table.count_rows(),
            "embedding_dim": self._embedding_dim,
        }

    def close(self) -> None:
        """Close the database connection."""
        # LanceDB connections are typically stateless
        self.db = None
        self.table = None

    async def get_stored_metadata(self) -> Optional[Dict[str, Any]]:
        """
        Get stored metadata from the table's metadata.

        Returns:
            Dictionary with stored metadata (embedding_model_id, embedding_dim, embedding_prefix_hash)
            or None if table doesn't exist or no metadata is stored.
        """
        if self.table is None:
            return None

        try:
            # Try to get table metadata
            schema = await self.table.schema()
            table_metadata = schema.metadata
            if table_metadata:
                # Convert bytes keys/values to strings if needed
                metadata = {}
                for key, value in table_metadata.items():
                    if isinstance(key, bytes):
                        key = key.decode("utf-8")
                    if isinstance(value, bytes):
                        value = value.decode("utf-8")
                    metadata[key] = value

                # Extract our stored fields
                result = {}
                if (
                    b"embedding_model_id" in table_metadata
                    or "embedding_model_id" in metadata
                ):
                    result["embedding_model_id"] = metadata.get("embedding_model_id")
                if b"embedding_dim" in table_metadata or "embedding_dim" in metadata:
                    result["embedding_dim"] = int(metadata.get("embedding_dim", 0))
                if (
                    b"embedding_prefix_hash" in table_metadata
                    or "embedding_prefix_hash" in metadata
                ):
                    result["embedding_prefix_hash"] = metadata.get(
                        "embedding_prefix_hash"
                    )

                if result:
                    return result
        except (AttributeError, KeyError, IndexError, TypeError, ValueError) as e:
            logger.debug(f"Failed to read table metadata: {e}")

        return None

    async def validate_schema(
        self, embedding_model_id: str, embedding_dim: int
    ) -> Dict[str, Any]:
        """
        Validate that the table schema matches the current embedding configuration.

        Args:
            embedding_model_id: The embedding model identifier
            embedding_dim: The expected embedding dimension

        Returns:
            Dictionary with validation results

        Raises:
            VectorStoreValidationError: If embedding dimension mismatch is detected
        """
        # Generate a probe embedding for "dimension_probe" text
        probe_text = "dimension_probe"
        try:
            probe_embedding = self._generate_probe_embedding(probe_text, embedding_dim)
        except (ValueError, TypeError, RuntimeError) as e:
            logger.warning(f"Failed to generate probe embedding: {e}")
            probe_embedding = None

        # Get expected dimension from the provided parameter
        expected_dim = embedding_dim

        # Check if table exists
        table_exists = False
        if self.db is not None:
            try:
                table_names = await self.db.table_names()
                table_exists = "chunks" in table_names
            except (OSError, RuntimeError, ValueError) as e:
                logger.warning(f"Failed to check table existence: {e}")

        stored_metadata = None
        if table_exists:
            try:
                if self.table is None:
                    self.table = await self.db.open_table("chunks")

                # Get schema and compare vector dimension
                schema = await self.table.schema()
                embedding_field = schema.field("embedding")
                actual_dim = None
                if hasattr(embedding_field.type, "list_size"):
                    actual_dim = embedding_field.type.list_size

                if actual_dim is not None and actual_dim != expected_dim:
                    error_msg = f"Embedding dimension changed from {actual_dim} to {expected_dim}; reindex required."
                    logger.error(error_msg)
                    raise VectorStoreValidationError(error_msg)

                # Get stored metadata
                stored_metadata = await self.get_stored_metadata()

            except VectorStoreValidationError:
                raise
            except (AttributeError, KeyError, IndexError, TypeError, ValueError) as e:
                logger.warning(f"Failed to validate schema: {e}")

        # Prepare metadata to store
        import hashlib

        prefix_hash = hashlib.sha256(embedding_model_id.encode("utf-8")).hexdigest()[
            :16
        ]

        metadata_to_store = {
            "embedding_model_id": embedding_model_id,
            "embedding_dim": str(expected_dim),
            "embedding_prefix_hash": prefix_hash,
        }

        # Update table metadata if table exists
        if table_exists and self.table is not None:
            try:
                # Get existing metadata
                schema = await self.table.schema()
                current_metadata = dict(schema.metadata) if schema.metadata else {}

                # Update with our metadata
                for key, value in metadata_to_store.items():
                    if isinstance(value, str):
                        current_metadata[key.encode("utf-8")] = value.encode("utf-8")
                    else:
                        current_metadata[key.encode("utf-8")] = str(value).encode(
                            "utf-8"
                        )

                # Note: LanceDB doesn't support direct metadata update on existing table
                # We'll log the metadata that should be stored for future reference
                logger.info(f"Table metadata to store/update: {metadata_to_store}")

            except (AttributeError, KeyError, TypeError, ValueError) as e:
                logger.warning(f"Failed to update table metadata: {e}")

        return {
            "table_exists": table_exists,
            "expected_dim": expected_dim,
            "actual_dim": expected_dim if table_exists else None,
            "stored_metadata": stored_metadata,
            "probe_embedding_generated": probe_embedding is not None,
            "metadata_to_store": metadata_to_store,
        }

    def _generate_probe_embedding(self, text: str, dim: int) -> List[float]:
        """
        Generate a probe embedding for dimension validation.

        Args:
            text: The text to generate embedding for
            dim: Expected dimension

        Returns:
            Generated embedding vector
        """
        # Use a deterministic hash-based approach for probe embedding
        import hashlib
        import random

        # Create a deterministic seed from the text
        seed_value = int(hashlib.md5(text.encode("utf-8")).hexdigest(), 16) % (2**32)
        random.seed(seed_value)

        # Generate a random vector of expected dimension
        # This simulates what a real embedding would look like
        probe = [random.gauss(0, 1) for _ in range(dim)]

        # Normalize the vector (typical for embeddings)
        magnitude = sum(x * x for x in probe) ** 0.5
        if magnitude > 0:
            probe = [x / magnitude for x in probe]

        return probe
