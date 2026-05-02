"""
Semantic search API routes for document chunks.

Provides endpoints for searching document chunks using vector similarity.
"""

import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import (
    evaluate_policy,
    get_current_active_user,
    get_db,
    get_embedding_service,
    get_vector_store,
)
from app.services.embeddings import EmbeddingError, EmbeddingService
from app.services.vector_store import VectorStore, VectorStoreError

router = APIRouter()


class SearchRequest(BaseModel):
    """Request model for semantic search endpoint."""

    query: str = Field(..., min_length=1, max_length=1000)
    limit: int = Field(10, ge=1, le=100)
    vault_id: Optional[int] = None


class SearchResult(BaseModel):
    """Model for a single search result."""

    id: str
    text: str
    file_id: str
    chunk_index: int
    metadata: Dict[str, Any]
    score: float


class SearchResponse(BaseModel):
    """Response model for search endpoint.

    ``search_type`` is always ``"diagnostic"`` — this endpoint performs simple
    vector similarity search and does NOT use the full RAG retrieval pipeline
    (no reranking, no hybrid fusion, no citation generation). Use ``/chat``
    for production RAG answers.
    """

    results: List[SearchResult]
    search_type: str = "diagnostic"


@router.post("/search", response_model=SearchResponse)
async def search(
    request: SearchRequest,
    user: dict = Depends(get_current_active_user),
    db=Depends(get_db),
    embedding_service: EmbeddingService = Depends(get_embedding_service),
    vector_store: VectorStore = Depends(get_vector_store),
):
    """
    Semantic search endpoint for document chunks.

    Embeds the query text and searches the vector store for similar chunks.

    Args:
        request: SearchRequest containing query text and optional limit

    Returns:
        SearchResponse with list of matching chunks and similarity scores

    Raises:
        HTTPException: 500 if embedding or search operation fails
    """
    # Early check for whitespace-only query
    if not request.query or not request.query.strip():
        raise HTTPException(
            status_code=400, detail="Query cannot be empty or whitespace only"
        )

    # Vault permission scoping
    if request.vault_id is not None:
        # Specific vault requested — check read access
        if not await evaluate_policy(user, "vault", request.vault_id, "read"):
            raise HTTPException(status_code=403, detail="No read access to this vault")
    else:
        # No vault specified — non-admins must specify a vault
        if user.get("role") not in ("superadmin", "admin"):
            raise HTTPException(
                status_code=400, detail="vault_id is required for non-admin users"
            )

    try:
        # Generate embedding for the query
        query_embedding = await embedding_service.embed_single(request.query)

        # Initialize vector store table
        embedding_dim = len(query_embedding)
        await vector_store.init_table(embedding_dim)

        # Perform semantic search
        vault_id_str = str(request.vault_id) if request.vault_id is not None else None
        raw_results = await vector_store.search(
            embedding=query_embedding, limit=request.limit, vault_id=vault_id_str
        )

        # Transform results to response model
        results = []
        for record in raw_results:
            # Parse metadata JSON string if present
            metadata = {}
            record_metadata = (
                record.get("metadata")
                if isinstance(record, dict)
                else getattr(record, "metadata", None)
            )
            if record_metadata:
                try:
                    metadata = (
                        json.loads(record_metadata)
                        if isinstance(record_metadata, str)
                        else record_metadata
                    )
                except (json.JSONDecodeError, TypeError):
                    metadata = {}

            # Get similarity score (_distance is returned by LanceDB)
            score = (
                record.get("_distance", 0.0)
                if isinstance(record, dict)
                else getattr(record, "_distance", 0.0)
            )

            # Safe extraction from records with defaults when None
            results.append(
                SearchResult(
                    id=record.get("id", "")
                    if isinstance(record, dict)
                    else getattr(record, "id", ""),
                    text=record.get("text", "")
                    if isinstance(record, dict)
                    else getattr(record, "text", ""),
                    file_id=record.get("file_id", "")
                    if isinstance(record, dict)
                    else getattr(record, "file_id", ""),
                    chunk_index=record.get("chunk_index", 0)
                    if isinstance(record, dict)
                    else getattr(record, "chunk_index", 0),
                    metadata=metadata,
                    score=score,
                )
            )

        return SearchResponse(results=results)

    except EmbeddingError as e:
        raise HTTPException(
            status_code=500, detail=f"Embedding service error: {str(e)}"
        )
    except VectorStoreError as e:
        raise HTTPException(status_code=500, detail=f"Vector store error: {str(e)}")
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Search operation failed: {str(e)}"
        )
